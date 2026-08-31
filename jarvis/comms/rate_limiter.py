"""
jarvis/comms/rate_limiter.py
============================
Thread-safe Token Bucket Rate Limiter per user_id (R5).
Supports configurable refill rates (requests/minute), burst capacities, and HTTP 429 Too Many Requests responses.

Mathematical Model:
- Capacity B (burst_limit)
- Refill rate r = requests_per_minute / 60.0 tokens/second
- State per user: (tokens, last_updated)
- Allowed: tokens >= cost -> tokens -= cost -> HTTP 200
- Denied: tokens < cost -> retry_after = ceil((cost - tokens)/r) -> HTTP 429
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

log = logging.getLogger("jarvis.comms.rate_limiter")


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a communications channel."""
    requests_per_minute: float = 30.0
    burst_limit: int = 5
    enabled: bool = True


@dataclass
class TokenBucket:
    """State of an individual token bucket."""
    tokens: float
    last_updated: float
    capacity: float
    refill_rate: float  # tokens per second


@dataclass
class RateLimitResult:
    """Result of an acquire operation."""
    allowed: bool
    status_code: int = 200  # 200 (OK) or 429 (Too Many Requests)
    remaining_tokens: int = 0
    retry_after_s: float = 0.0
    error_message: str = ""

    def __iter__(self) -> Iterator[Any]:
        """Allows tuple unpacking: allowed, retry_after = limiter.acquire(user_id)"""
        yield self.allowed
        yield self.retry_after_s

    def __bool__(self) -> bool:
        return self.allowed


class TokenBucketRateLimiter:
    """
    Thread-safe Token Bucket rate limiter tracking request quotas per user_id.
    """

    def __init__(
        self,
        config: RateLimitConfig | None = None,
        channel_name: str = "default",
        rate_per_minute: float | None = None,
        requests_per_minute: float | None = None,
        burst_limit: int | None = None,
        **kwargs: Any,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            rpm = (
                rate_per_minute
                if rate_per_minute is not None
                else (requests_per_minute if requests_per_minute is not None else 30.0)
            )
            burst = burst_limit if burst_limit is not None else 5
            self.config = RateLimitConfig(requests_per_minute=float(rpm), burst_limit=int(burst))
        self.channel_name = channel_name
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    @property
    def refill_rate(self) -> float:
        """Tokens refilled per second."""
        return max(0.001, float(self.config.requests_per_minute) / 60.0)

    @property
    def capacity(self) -> float:
        """Maximum token burst capacity."""
        return float(max(1, self.config.burst_limit))

    def acquire(self, user_id: str | int, cost: float = 1.0) -> RateLimitResult:
        """
        Attempt to acquire `cost` tokens for `user_id`.
        Returns RateLimitResult with allowed=True (HTTP 200) or allowed=False (HTTP 429).
        """
        if not self.config.enabled:
            return RateLimitResult(
                allowed=True,
                status_code=200,
                remaining_tokens=999,
                retry_after_s=0.0,
                error_message="",
            )

        uid = str(user_id)
        now = time.time()

        with self._lock:
            if uid not in self._buckets:
                self._buckets[uid] = TokenBucket(
                    tokens=self.capacity,
                    last_updated=now,
                    capacity=self.capacity,
                    refill_rate=self.refill_rate,
                )

            bucket = self._buckets[uid]

            # Dynamic config synchronization
            bucket.capacity = self.capacity
            bucket.refill_rate = self.refill_rate

            # Refill tokens based on elapsed time since last request
            elapsed = max(0.0, now - bucket.last_updated)
            bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
            bucket.last_updated = now

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                remaining = int(bucket.tokens)
                return RateLimitResult(
                    allowed=True,
                    status_code=200,
                    remaining_tokens=remaining,
                    retry_after_s=0.0,
                    error_message="",
                )
            else:
                needed = cost - bucket.tokens
                retry_after = round(needed / bucket.refill_rate, 2)
                if retry_after <= 0.0:
                    retry_after = 0.01
                err = f"Rate limit exceeded on channel '{self.channel_name}'. Retry after {retry_after}s."
                log.warning(
                    "Rate limit exceeded: channel=%s, user_id=%s, retry_after=%.2fs, status=429",
                    self.channel_name,
                    uid,
                    retry_after,
                )
                return RateLimitResult(
                    allowed=False,
                    status_code=429,
                    remaining_tokens=0,
                    retry_after_s=retry_after,
                    error_message=err,
                )

    def reset(self, user_id: str | int | None = None) -> None:
        """Reset quota for a specific user_id, or all users if user_id is None."""
        with self._lock:
            if user_id is None:
                self._buckets.clear()
            else:
                self._buckets.pop(str(user_id), None)

    def cleanup_idle(self, max_idle_s: float = 3600.0) -> int:
        """Evict buckets that haven't been accessed for max_idle_s to reclaim memory."""
        now = time.time()
        evicted = 0
        with self._lock:
            for uid in list(self._buckets.keys()):
                if now - self._buckets[uid].last_updated > max_idle_s:
                    del self._buckets[uid]
                    evicted += 1
        return evicted

    def get_token_count(self, user_id: str | int) -> float:
        """Inspect current available tokens for user_id without consuming."""
        uid = str(user_id)
        now = time.time()
        with self._lock:
            if uid not in self._buckets:
                return self.capacity
            bucket = self._buckets[uid]
            elapsed = max(0.0, now - bucket.last_updated)
            return min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
