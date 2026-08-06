"""Source-policy enforcement shared by every Linkareer transport."""

from __future__ import annotations

import random
import re
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol, TypeVar
from urllib.parse import urlparse


class SourcePolicyBlocked(RuntimeError):
    pass


MAX_CONCURRENCY = 2
REQUESTS_PER_SECOND = 1.0
MAX_RETRIES = 3
BACKOFF_POLICY = "exponential-jitter"
MIN_SUCCESS_RATE = 0.80
MAX_CONSECUTIVE_403 = 1
MAX_CONSECUTIVE_429 = 3
MAX_EMPTY_PAGE_STREAK = 2
CHECKPOINT_INTERVAL = 1


@dataclass(frozen=True)
class SourcePolicyConfig:
    max_concurrency: int = MAX_CONCURRENCY
    requests_per_second: float = REQUESTS_PER_SECOND
    max_retries: int = MAX_RETRIES
    backoff_policy: str = BACKOFF_POLICY
    min_success_rate: float = MIN_SUCCESS_RATE
    max_consecutive_403: int = MAX_CONSECUTIVE_403
    max_consecutive_429: int = MAX_CONSECUTIVE_429
    max_empty_page_streak: int = MAX_EMPTY_PAGE_STREAK
    checkpoint_interval: int = CHECKPOINT_INTERVAL
    success_window: int = 20
    minimum_success_samples: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.max_concurrency <= MAX_CONCURRENCY:
            raise ValueError("MAX_CONCURRENCY must be between 1 and 2")
        if not 0 < self.requests_per_second <= 1:
            raise ValueError("REQUESTS_PER_SECOND must be in (0, 1]")
        if self.max_retries < 0:
            raise ValueError("MAX_RETRIES must be non-negative")
        if self.backoff_policy != BACKOFF_POLICY:
            raise ValueError(f"unsupported BACKOFF_POLICY: {self.backoff_policy}")
        if not 0 < self.min_success_rate <= 1:
            raise ValueError("MIN_SUCCESS_RATE must be in (0, 1]")
        if min(self.max_consecutive_403, self.max_consecutive_429, self.max_empty_page_streak) < 1:
            raise ValueError("kill-switch thresholds must be positive")
        if self.checkpoint_interval < 1:
            raise ValueError("CHECKPOINT_INTERVAL must be positive")


class ResponseLike(Protocol):
    status_code: int
    content: bytes


class KillSwitch:
    def __init__(self) -> None:
        self._event = threading.Event()
        self.reason: str | None = None

    def trip(self, reason: str) -> None:
        self.reason = reason
        self._event.set()

    def check(self) -> None:
        if self._event.is_set():
            raise SourcePolicyBlocked(self.reason or "SOURCE_POLICY_BLOCKED")

    @property
    def tripped(self) -> bool:
        return self._event.is_set()


class SourceHealthMonitor:
    """Stateful fail-closed health policy for one production collector run."""

    def __init__(self, kill_switch: KillSwitch, config: SourcePolicyConfig) -> None:
        self.kill_switch = kill_switch
        self.config = config
        self.consecutive_403 = 0
        self.consecutive_429 = 0
        self.empty_page_streak = 0
        self.outcomes: deque[bool] = deque(maxlen=config.success_window)

    def observe_response(self, status_code: int) -> None:
        success = 200 <= status_code < 400
        self.outcomes.append(success)
        self.consecutive_403 = self.consecutive_403 + 1 if status_code == 403 else 0
        self.consecutive_429 = self.consecutive_429 + 1 if status_code == 429 else 0
        if self.consecutive_403 >= self.config.max_consecutive_403:
            self.kill_switch.trip("SOURCE_POLICY_BLOCKED: HTTP 403 MAX_CONSECUTIVE_403")
        elif self.consecutive_429 >= self.config.max_consecutive_429:
            self.kill_switch.trip("SOURCE_POLICY_BLOCKED: MAX_CONSECUTIVE_429")
        elif len(self.outcomes) >= self.config.minimum_success_samples:
            success_rate = sum(self.outcomes) / len(self.outcomes)
            if success_rate < self.config.min_success_rate:
                self.kill_switch.trip("SOURCE_POLICY_BLOCKED: MIN_SUCCESS_RATE")

    def observe_page(self, *, empty: bool, exhausted: bool = False) -> None:
        self.empty_page_streak = self.empty_page_streak + 1 if empty and not exhausted else 0
        if self.empty_page_streak >= self.config.max_empty_page_streak:
            self.kill_switch.trip("SOURCE_POLICY_BLOCKED: MAX_EMPTY_PAGE_STREAK")

    def schema_drift(self, reason: str) -> None:
        self.kill_switch.trip(f"SOURCE_POLICY_BLOCKED: SCHEMA_DRIFT: {reason}")

    def checkpoint_corruption(self, reason: str) -> None:
        self.kill_switch.trip(f"SOURCE_POLICY_BLOCKED: CHECKPOINT_CORRUPTION: {reason}")


class RateLimiter:
    """Thread-safe global start-time limiter with injectable fake clock."""

    def __init__(
        self,
        minimum: float = 1.0,
        jitter: tuple[float, float] = (0.0, 0.0),
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if minimum < 1.0:
            raise ValueError("minimum request interval must be at least one second")
        self.minimum = minimum
        self.jitter = jitter
        self.clock = clock
        self.sleeper = sleeper
        self.random_uniform = random_uniform
        self.last_start: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> float:
        with self._lock:
            now = self.clock()
            if self.last_start is not None:
                required = self.minimum + self.random_uniform(*self.jitter)
                delay = required - (now - self.last_start)
                if delay > 0:
                    self.sleeper(delay)
                    now = self.clock()
            self.last_start = now
            return now


class ConcurrencyGate:
    def __init__(self, limit: int = 2) -> None:
        if not 1 <= limit <= 2:
            raise ValueError("source policy requires concurrency between 1 and 2")
        self.limit = limit
        self._semaphore = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self.active = 0
        self.max_seen = 0

    @contextmanager
    def enter(self, kill_switch: KillSwitch):
        kill_switch.check()
        self._semaphore.acquire()
        try:
            kill_switch.check()
            with self._lock:
                self.active += 1
                self.max_seen = max(self.max_seen, self.active)
            yield
        finally:
            with self._lock:
                self.active = max(0, self.active - 1)
            self._semaphore.release()


def is_allowed_linkareer_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and (host == "linkareer.com" or host.endswith(".linkareer.com"))


def redact_secrets(text: str) -> str:
    patterns = (
        r"(?i)(servicekey|api[_-]?key|authorization|token)=([^&\s]+)",
        r"(?i)(bearer)\s+[a-z0-9._~-]+",
    )
    redacted = text
    for pattern in patterns:
        redacted = re.sub(pattern, lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    return redacted


T = TypeVar("T")


@dataclass
class PolicyHttpClient:
    """A transport wrapper that rejects ATS hosts before any network call."""

    transport: Callable[..., ResponseLike]
    minimum_interval: float = 1.0
    concurrency: int = 2
    limiter: RateLimiter | None = None
    response_hook: Callable[[str, ResponseLike, dict], object] | None = None
    policy: SourcePolicyConfig | None = None
    backoff_sleeper: Callable[[float], None] = time.sleep
    random_uniform: Callable[[float, float], float] = random.uniform

    def __post_init__(self) -> None:
        self.policy = self.policy or SourcePolicyConfig(
            max_concurrency=self.concurrency,
            requests_per_second=1.0 / self.minimum_interval,
        )
        self.concurrency = self.policy.max_concurrency
        self.minimum_interval = 1.0 / self.policy.requests_per_second
        self.limiter = self.limiter or RateLimiter(self.minimum_interval)
        self.gate = ConcurrencyGate(self.policy.max_concurrency)
        self.kill_switch = KillSwitch()
        self.health = SourceHealthMonitor(self.kill_switch, self.policy)

    def get(self, url: str, **kwargs) -> ResponseLike:
        context = kwargs.pop("_p4_context", {})
        if not is_allowed_linkareer_url(url):
            raise SourcePolicyBlocked("EXTERNAL_ATS_TRANSPORT_REJECTED")
        self.kill_switch.check()
        with self.gate.enter(self.kill_switch):
            for attempt in range(self.policy.max_retries + 1):
                self.limiter.wait()
                self.kill_switch.check()
                response = self.transport(url, **kwargs)
                body = response.content
                self.health.observe_response(response.status_code)
                self.kill_switch.check()
                prefix = body[:200_000].lower()
                if any(marker in prefix for marker in (b"access denied", b"just a moment", b"captcha", b"datadome")):
                    self.kill_switch.trip("SOURCE_POLICY_BLOCKED: challenge marker")
                    raise SourcePolicyBlocked(self.kill_switch.reason)
                expected_types = tuple(context.get("expectedContentTypes") or ())
                headers = getattr(response, "headers", {}) or {}
                content_type = str(headers.get("content-type", "")).split(";", 1)[0].strip().lower()
                if expected_types and content_type and content_type not in expected_types:
                    self.kill_switch.trip(f"SOURCE_POLICY_BLOCKED: UNEXPECTED_CONTENT_TYPE: {content_type}")
                    raise SourcePolicyBlocked(self.kill_switch.reason)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.policy.max_retries:
                    delay = (2 ** attempt) + self.random_uniform(0.0, 0.25)
                    self.backoff_sleeper(delay)
                    continue
                if self.response_hook is not None:
                    manifest = self.response_hook(url, response, context)
                    try:
                        setattr(response, "p4_manifest", manifest)
                    except (AttributeError, TypeError):
                        pass
                return response
        raise AssertionError("unreachable HTTP retry state")

    def run_batch(self, jobs: Iterable[tuple[str, dict]]) -> list[ResponseLike]:
        futures: dict[Future, int] = {}
        results: list[ResponseLike | None] = []
        jobs = list(jobs)
        results.extend([None] * len(jobs))
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            for index, (url, kwargs) in enumerate(jobs):
                futures[executor.submit(self.get, url, **kwargs)] = index
            try:
                for future in as_completed(futures):
                    results[futures[future]] = future.result()
            except SourcePolicyBlocked:
                self.kill_switch.trip(self.kill_switch.reason or "SOURCE_POLICY_BLOCKED")
                for future in futures:
                    future.cancel()
                raise
        return [response for response in results if response is not None]
