"""Source-policy enforcement shared by every Linkareer transport."""

from __future__ import annotations

import random
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from collections import deque
from typing import Callable, Iterable, Protocol, TypeVar
from urllib.parse import urlparse


class SourcePolicyBlocked(RuntimeError):
    pass


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


class SuccessRateMonitor:
    """Fail closed when a bounded recent response window degrades."""

    def __init__(self, window: int = 20, minimum_observations: int = 10, minimum_rate: float = 0.8) -> None:
        if window < 1 or not 1 <= minimum_observations <= window:
            raise ValueError("invalid success-rate window")
        if not 0.0 <= minimum_rate <= 1.0:
            raise ValueError("minimum success rate must be between zero and one")
        self.window = window
        self.minimum_observations = minimum_observations
        self.minimum_rate = minimum_rate
        self._observations: deque[bool] = deque(maxlen=window)
        self._lock = threading.Lock()

    def record(self, status_code: int) -> tuple[int, float, bool]:
        with self._lock:
            self._observations.append(200 <= status_code < 400)
            count = len(self._observations)
            rate = sum(self._observations) / count
            degraded = count >= self.minimum_observations and rate < self.minimum_rate
            return count, rate, degraded


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
    success_window: int = 20
    success_minimum_observations: int = 10
    minimum_success_rate: float = 0.8

    def __post_init__(self) -> None:
        self.limiter = self.limiter or RateLimiter(self.minimum_interval)
        self.gate = ConcurrencyGate(self.concurrency)
        self.kill_switch = KillSwitch()
        self.success_monitor = SuccessRateMonitor(
            self.success_window,
            self.success_minimum_observations,
            self.minimum_success_rate,
        )

    def get(self, url: str, **kwargs) -> ResponseLike:
        context = kwargs.pop("_p4_context", {})
        if not is_allowed_linkareer_url(url):
            raise SourcePolicyBlocked("EXTERNAL_ATS_TRANSPORT_REJECTED")
        self.kill_switch.check()
        with self.gate.enter(self.kill_switch):
            self.limiter.wait()
            self.kill_switch.check()
            response = self.transport(url, **kwargs)
            body = response.content
            if response.status_code == 403:
                self.kill_switch.trip("SOURCE_POLICY_BLOCKED: HTTP 403")
                raise SourcePolicyBlocked(self.kill_switch.reason)
            prefix = body[:200_000].lower()
            if any(marker in prefix for marker in (b"access denied", b"just a moment", b"captcha", b"datadome")):
                self.kill_switch.trip("SOURCE_POLICY_BLOCKED: challenge marker")
                raise SourcePolicyBlocked(self.kill_switch.reason)
            count, rate, degraded = self.success_monitor.record(response.status_code)
            if degraded:
                self.kill_switch.trip(
                    f"SOURCE_POLICY_BLOCKED: recent success rate {rate:.3f} below "
                    f"{self.minimum_success_rate:.3f} over {count} responses"
                )
                raise SourcePolicyBlocked(self.kill_switch.reason)
            if self.response_hook is not None:
                manifest = self.response_hook(url, response, context)
                try:
                    setattr(response, "p4_manifest", manifest)
                except (AttributeError, TypeError):
                    pass
            return response

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
