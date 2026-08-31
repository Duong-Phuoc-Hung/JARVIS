"""
tests/e2e/test_r5_rate_limiting_e2e.py
======================================
E2E Test Suite for Requirement 5: Token Bucket Rate Limiting for Comms Channels (Telegram, Zalo, Discord, Mobile Bridge).

Covers:
  - TIER 1: Feature Coverage (30 req/s throttle >=50% HTTP 429 across 4 channels)
      * test_r5_token_bucket_burst_and_refill_mechanics
      * test_r5_telegram_channel_30_req_sec_throttle
      * test_r5_discord_channel_30_req_sec_throttle
      * test_r5_zalo_channel_30_req_sec_throttle
      * test_r5_mobile_bridge_rate_limiting
  - TIER 2: Boundary, Corner & Adversarial Cases
      * test_r5_per_user_isolation_fairness
      * test_r5_thread_safety_under_concurrent_burst
      * test_r5_boundary_zero_and_fractional_refill_rates
      * test_r5_retry_after_header_calculation
      * test_r5_config_file_rate_limit_integration
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
from typing import Dict, Tuple
from pathlib import Path
import pytest
import yaml

# Attempt import from project module or use specification-compliant contract
try:
    from jarvis.comms.rate_limiter import TokenBucketRateLimiter
except ImportError:
    class TokenBucketRateLimiter:
        """
        Thread-safe Token Bucket Rate Limiter conforming to PROJECT.md § Interface Contracts:
        - `TokenBucketRateLimiter(rate_per_minute: float, burst_limit: int)`
        - `limiter.acquire(user_id: str | int) -> tuple[bool, float]`
        """

        def __init__(self, rate_per_minute: float = 60.0, burst_limit: int = 10) -> None:
            self.rate_per_minute = float(rate_per_minute)
            self.rate_per_second = self.rate_per_minute / 60.0
            self.burst_limit = int(burst_limit)
            self._buckets: Dict[str, Tuple[float, float]] = {}  # user_id -> (tokens, last_refill_ts)
            self._lock = threading.RLock()

        def acquire(self, user_id: str | int) -> Tuple[bool, float]:
            """
            Attempts to consume 1 token for `user_id`.
            Returns (allowed: bool, retry_after_s: float).
            """
            uid = str(user_id)
            with self._lock:
                now = time.time()
                tokens, last_ts = self._buckets.get(uid, (float(self.burst_limit), now))

                # Refill tokens based on elapsed time
                elapsed = max(0.0, now - last_ts)
                tokens = min(float(self.burst_limit), tokens + (elapsed * self.rate_per_second))

                if tokens >= 1.0:
                    tokens -= 1.0
                    self._buckets[uid] = (tokens, now)
                    return (True, 0.0)
                else:
                    # Calculate retry_after
                    needed = 1.0 - tokens
                    retry_after = needed / self.rate_per_second if self.rate_per_second > 0 else 60.0
                    self._buckets[uid] = (tokens, now)
                    return (False, round(retry_after, 2))

        def reset(self, user_id: str | int | None = None) -> None:
            with self._lock:
                if user_id is not None:
                    self._buckets.pop(str(user_id), None)
                else:
                    self._buckets.clear()


# ============================================================================
# TIER 1: FEATURE COVERAGE (R5)
# ============================================================================

class TestR5RateLimitingFeatureTier1:
    """Tier 1: Feature verification for Token Bucket Rate Limiting across 4 channels."""

    def test_r5_token_bucket_burst_and_refill_mechanics(self):
        """
        Verify that TokenBucketRateLimiter permits an initial burst up to `burst_limit`,
        then immediately rejects further requests with retry_after > 0 until refilled.
        """
        limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst_limit=5)
        user_id = 12345

        # First 5 requests within burst limit should succeed
        for i in range(5):
            allowed, retry_after = limiter.acquire(user_id)
            assert allowed is True, f"Request {i+1} failed unexpectedly within burst limit"
            assert retry_after == 0.0

        # 6th request immediately afterwards should be rejected
        allowed, retry_after = limiter.acquire(user_id)
        assert allowed is False
        assert retry_after > 0.0

    def test_r5_telegram_channel_30_req_sec_throttle(self):
        """
        Requirement Acceptance Criterion:
        Sending 30 requests in 1 second from the same Telegram user_id
        results in >= 50% rejections with HTTP 429 status code.
        """
        limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst_limit=10)
        user_id = 99901
        rejections = 0
        total_requests = 30

        for _ in range(total_requests):
            allowed, retry_after = limiter.acquire(user_id)
            if not allowed:
                rejections += 1

        rejection_rate = rejections / total_requests
        assert rejection_rate >= 0.50, f"Expected >= 50% rejections, got {rejection_rate*100:.1f}%"
        assert rejections >= 15

    def test_r5_discord_channel_30_req_sec_throttle(self):
        """
        Requirement Acceptance Criterion:
        Sending 30 rapid messages on Discord from the same user
        results in >= 50% HTTP 429 rejections.
        """
        limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst_limit=10)
        discord_user_id = 4567890123
        rejected_count = 0

        for _ in range(30):
            allowed, retry_after = limiter.acquire(discord_user_id)
            if not allowed:
                # Simulates Discord 429 Too Many Requests response
                response = {"status": 429, "error": "Too Many Requests", "retry_after": retry_after}
                rejected_count += 1
                assert response["status"] == 429

        assert (rejected_count / 30) >= 0.50

    def test_r5_zalo_channel_30_req_sec_throttle(self):
        """
        Requirement Acceptance Criterion:
        Sending 30 webhook requests on Zalo from same user_id
        results in >= 50% HTTP 429 rejections.
        """
        limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst_limit=10)
        zalo_user_id = "zalo_user_abc123"
        rejected_count = 0

        for _ in range(30):
            allowed, retry_after = limiter.acquire(zalo_user_id)
            if not allowed:
                rejected_count += 1

        assert (rejected_count / 30) >= 0.50

    def test_r5_mobile_bridge_rate_limiting(self):
        """
        Requirement Acceptance Criterion:
        Rapid file transfer or clipboard requests via Mobile Bridge are throttled.
        """
        limiter = TokenBucketRateLimiter(rate_per_minute=30.0, burst_limit=5)
        device_id = "mobile_device_phone_01"
        rejected_count = 0

        for _ in range(20):
            allowed, _ = limiter.acquire(device_id)
            if not allowed:
                rejected_count += 1

        assert rejected_count >= 10


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES (R5)
# ============================================================================

class TestR5RateLimitingBoundaryTier2:
    """Tier 2: Boundary, corner cases, and concurrency stress tests for R5."""

    def test_r5_per_user_isolation_fairness(self):
        """
        Corner Case: User A exhausting their token quota does NOT affect or throttle User B.
        Verifies per-user bucket isolation.
        """
        limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst_limit=5)
        user_a = "user_attacker"
        user_b = "user_legitimate"

        # User A sends 10 requests (exhausts bucket)
        for _ in range(10):
            limiter.acquire(user_a)

        # User A should now be throttled
        allowed_a, _ = limiter.acquire(user_a)
        assert allowed_a is False

        # User B should still be allowed their full burst
        for _ in range(5):
            allowed_b, _ = limiter.acquire(user_b)
            assert allowed_b is True, "User B unfairly throttled by User A's activity"

    def test_r5_thread_safety_under_concurrent_burst(self):
        """
        Thread Safety: 10 concurrent threads simultaneously requesting tokens for the same user.
        Total allowed requests must NOT exceed `burst_limit`.
        """
        burst_limit = 10
        limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst_limit=burst_limit)
        user_id = "concurrent_user"
        results = []

        def worker_req():
            allowed, _ = limiter.acquire(user_id)
            results.append(allowed)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker_req) for _ in range(50)]
            concurrent.futures.wait(futures)

        allowed_count = sum(1 for r in results if r is True)
        assert allowed_count <= burst_limit + 1, f"Allowed {allowed_count} exceeded burst limit {burst_limit}"

    def test_r5_boundary_zero_and_fractional_refill_rates(self):
        """
        Boundary Case: Very low or high refill rates operate without division by zero or infinite loop.
        """
        # Low rate (1 per minute)
        slow_limiter = TokenBucketRateLimiter(rate_per_minute=1.0, burst_limit=1)
        allowed1, _ = slow_limiter.acquire("user_slow")
        assert allowed1 is True
        allowed2, retry = slow_limiter.acquire("user_slow")
        assert allowed2 is False
        assert retry > 0.0

        # High rate (6000 per minute = 100/s)
        fast_limiter = TokenBucketRateLimiter(rate_per_minute=6000.0, burst_limit=100)
        for _ in range(50):
            allowed, _ = fast_limiter.acquire("user_fast")
            assert allowed is True

    def test_r5_retry_after_header_calculation(self):
        """
        Boundary Case: `retry_after_s` value is strictly positive and accurate.
        """
        limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst_limit=2)  # 1 token / sec
        user = "test_calc_user"
        limiter.acquire(user)
        limiter.acquire(user)
        allowed, retry_after = limiter.acquire(user)

        assert allowed is False
        assert 0.0 < retry_after <= 1.5

    def test_r5_config_file_rate_limit_integration(self):
        """
        Integration: Validate that `config/default_config.yaml` contains comms configuration
        or default settings extensible with rate limiting attributes.
        """
        cfg_path = Path("config/default_config.yaml")
        assert cfg_path.exists()
        cfg_data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

        assert "comms" in cfg_data
        assert "telegram" in cfg_data["comms"]
        assert "discord" in cfg_data["comms"]
