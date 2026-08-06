from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import pytest

from p4_crawl.policy import PolicyHttpClient, RateLimiter, SourcePolicyBlocked


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class Response:
    status_code: int = 200
    content: bytes = b"ok"


def test_fake_clock_global_interval_is_at_least_one_second() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1.0, clock=clock.monotonic, sleeper=clock.sleep, random_uniform=lambda _a, _b: 0.0)
    starts = [limiter.wait(), limiter.wait(), limiter.wait()]
    assert starts == [0.0, 1.0, 2.0]
    assert clock.sleeps == [1.0, 1.0]


def test_max_concurrency_never_exceeds_two() -> None:
    lock = threading.Lock()
    active = maximum = 0

    def transport(_url: str, **_kwargs) -> Response:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return Response()

    limiter = RateLimiter(1.0, clock=lambda: 0.0, sleeper=lambda _seconds: None, random_uniform=lambda _a, _b: 0.0)
    client = PolicyHttpClient(transport, concurrency=2, limiter=limiter)
    client.run_batch([("https://linkareer.com/activity/1", {}) for _ in range(8)])
    assert maximum <= 2
    assert client.gate.max_seen <= 2


def test_403_trips_kill_switch_and_rejects_future_calls() -> None:
    calls = 0

    def transport(_url: str, **_kwargs) -> Response:
        nonlocal calls
        calls += 1
        return Response(status_code=403, content=b"forbidden")

    limiter = RateLimiter(1.0, clock=lambda: 0.0, sleeper=lambda _seconds: None, random_uniform=lambda _a, _b: 0.0)
    client = PolicyHttpClient(transport, limiter=limiter)
    with pytest.raises(SourcePolicyBlocked, match="HTTP 403"):
        client.get("https://linkareer.com/activity/1")
    with pytest.raises(SourcePolicyBlocked, match="HTTP 403"):
        client.get("https://linkareer.com/activity/2")
    assert client.kill_switch.tripped
    assert calls == 1


def test_403_cancels_queued_batch_before_transport() -> None:
    lock = threading.Lock()
    calls = 0

    def transport(_url: str, **_kwargs) -> Response:
        nonlocal calls
        with lock:
            calls += 1
            number = calls
        if number == 1:
            return Response(status_code=403, content=b"forbidden")
        time.sleep(0.02)
        return Response()

    limiter = RateLimiter(1.0, clock=lambda: 0.0, sleeper=lambda _seconds: None, random_uniform=lambda _a, _b: 0.0)
    client = PolicyHttpClient(transport, concurrency=2, limiter=limiter)
    with pytest.raises(SourcePolicyBlocked, match="HTTP 403"):
        client.run_batch([("https://linkareer.com/activity/1", {}) for _ in range(10)])
    assert calls <= 2  # at most the two already-running workers; queued work never reaches transport


def test_external_ats_is_rejected_before_transport() -> None:
    calls = 0

    def transport(_url: str, **_kwargs) -> Response:
        nonlocal calls
        calls += 1
        return Response()

    client = PolicyHttpClient(transport)
    with pytest.raises(SourcePolicyBlocked, match="EXTERNAL_ATS"):
        client.get("https://jobs.example.com/posting/1")
    assert calls == 0


def test_recent_success_rate_trips_kill_switch() -> None:
    statuses = iter([200, 500, 500, 500])

    def transport(_url: str, **_kwargs) -> Response:
        return Response(status_code=next(statuses), content=b"response")

    limiter = RateLimiter(1.0, clock=lambda: 0.0, sleeper=lambda _seconds: None, random_uniform=lambda _a, _b: 0.0)
    client = PolicyHttpClient(
        transport,
        limiter=limiter,
        success_window=4,
        success_minimum_observations=4,
        minimum_success_rate=0.5,
    )
    for suffix in (1, 2, 3):
        client.get(f"https://linkareer.com/activity/{suffix}")
    with pytest.raises(SourcePolicyBlocked, match="recent success rate"):
        client.get("https://linkareer.com/activity/4")
    assert client.kill_switch.tripped
