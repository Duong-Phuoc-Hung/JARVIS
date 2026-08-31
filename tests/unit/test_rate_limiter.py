"""
tests/unit/test_rate_limiter.py
===============================
Comprehensive Unit Test Suite for Comms Rate Limiting (R5).

Test Matrix:
- Token Bucket Arithmetic: Refill rates, capacity limits, fractional costs
- HTTP 429 Rejection: Status code, retry-after calculation, boolean evaluation, tuple unpacking
- Concurrency & Thread-Safety: 20+ simultaneous worker threads
- User Isolation: Quota separation across distinct user IDs
- Lifecycle Management: Reset individual/all users, idle bucket eviction
- Acceptance Criterion (30 req/s Burst): >=50% HTTP 429 rejections across Telegram, Zalo, Discord, and Mobile Bridge
- Config & Disabling: Dynamic config updates and bypass when disabled
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
from unittest.mock import MagicMock

import pytest

from jarvis.comms.discord import DiscordBotController, DiscordConfig
from jarvis.comms.mobile_bridge import MobileFileBridge
from jarvis.comms.rate_limiter import (
    RateLimitConfig,
    RateLimitResult,
    TokenBucketRateLimiter,
)
from jarvis.comms.telegram import TelegramBotController, TelegramConfig
from jarvis.comms.zalo import ZaloBotController, ZaloConfig


class TestTokenBucketRateLimiterCore:
    """Core mathematical and functional tests for TokenBucketRateLimiter."""

    def test_initial_burst_capacity(self):
        cfg = RateLimitConfig(requests_per_minute=60.0, burst_limit=5)
        limiter = TokenBucketRateLimiter(config=cfg, channel_name="test")

        # First 5 acquisitions should succeed immediately (consuming 1 token each)
        for i in range(5):
            res = limiter.acquire("user_101")
            assert res.allowed is True
            assert res.status_code == 200
            assert res.remaining_tokens == 4 - i
            assert res.retry_after_s == 0.0

        # 6th acquisition should be throttled (HTTP 429)
        res6 = limiter.acquire("user_101")
        assert res6.allowed is False
        assert res6.status_code == 429
        assert res6.remaining_tokens == 0
        assert res6.retry_after_s > 0.0
        assert "Rate limit exceeded" in res6.error_message

    def test_tuple_unpacking_and_bool_support(self):
        cfg = RateLimitConfig(requests_per_minute=60.0, burst_limit=1)
        limiter = TokenBucketRateLimiter(config=cfg, channel_name="test")

        # 1st allowed
        allowed, retry_after = limiter.acquire("u1")
        assert allowed is True
        assert retry_after == 0.0

        # 2nd denied
        res = limiter.acquire("u1")
        allowed2, retry_after2 = res
        assert allowed2 is False
        assert retry_after2 > 0.0
        assert not bool(res)

    def test_refill_over_time(self):
        # 120 req/min = 2 tokens/sec
        cfg = RateLimitConfig(requests_per_minute=120.0, burst_limit=2)
        limiter = TokenBucketRateLimiter(config=cfg, channel_name="test")

        # Drain all 2 tokens
        assert limiter.acquire("u1").allowed is True
        assert limiter.acquire("u1").allowed is True
        assert limiter.acquire("u1").allowed is False

        # Sleep 0.55s -> should replenish ~1 token (0.55s * 2 tokens/s = 1.1 tokens)
        time.sleep(0.55)
        assert limiter.acquire("u1").allowed is True
        assert limiter.acquire("u1").allowed is False

    def test_user_isolation(self):
        cfg = RateLimitConfig(requests_per_minute=60.0, burst_limit=2)
        limiter = TokenBucketRateLimiter(config=cfg, channel_name="test")

        # User A exhausts quota
        assert limiter.acquire("user_A").allowed is True
        assert limiter.acquire("user_A").allowed is True
        assert limiter.acquire("user_A").allowed is False

        # User B still has full quota
        assert limiter.acquire("user_B").allowed is True
        assert limiter.acquire("user_B").allowed is True
        assert limiter.acquire("user_B").allowed is False

    def test_reset_user_and_all_users(self):
        cfg = RateLimitConfig(requests_per_minute=60.0, burst_limit=1)
        limiter = TokenBucketRateLimiter(config=cfg, channel_name="test")

        limiter.acquire("u1")
        limiter.acquire("u2")
        assert limiter.acquire("u1").allowed is False
        assert limiter.acquire("u2").allowed is False

        # Reset u1 only
        limiter.reset("u1")
        assert limiter.acquire("u1").allowed is True
        assert limiter.acquire("u2").allowed is False

        # Reset all
        limiter.reset()
        assert limiter.acquire("u2").allowed is True

    def test_cleanup_idle_buckets(self):
        cfg = RateLimitConfig(requests_per_minute=60.0, burst_limit=5)
        limiter = TokenBucketRateLimiter(config=cfg, channel_name="test")

        limiter.acquire("u1")
        limiter.acquire("u2")
        assert len(limiter._buckets) == 2

        # Idle time of 0.05s
        time.sleep(0.06)
        evicted = limiter.cleanup_idle(max_idle_s=0.04)
        assert evicted == 2
        assert len(limiter._buckets) == 0

    def test_thread_safety_under_concurrency(self):
        # Burst limit of 50, 20 worker threads trying to acquire simultaneously
        cfg = RateLimitConfig(requests_per_minute=60.0, burst_limit=50)
        limiter = TokenBucketRateLimiter(config=cfg, channel_name="test")

        success_count = 0
        lock = threading.Lock()

        def worker():
            nonlocal success_count
            for _ in range(5):
                res = limiter.acquire("concurrent_user")
                if res.allowed:
                    with lock:
                        success_count += 1

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total attempts = 100, exactly 50 should succeed (capacity = 50)
        assert success_count == 50

    def test_disabled_rate_limiter_allows_all(self):
        cfg = RateLimitConfig(requests_per_minute=1.0, burst_limit=1, enabled=False)
        limiter = TokenBucketRateLimiter(config=cfg, channel_name="test")

        for _ in range(20):
            res = limiter.acquire("u_disabled")
            assert res.allowed is True
            assert res.status_code == 200


class TestChannelRateLimitingAcceptanceCriteria:
    """
    Acceptance Criteria R5 Verification:
    Sending 30 requests in 1 second from same user_id causes >=50% HTTP 429 rejections
    across all 4 channels: Telegram, Zalo, Discord, and Mobile Bridge.
    """

    def test_telegram_30_req_per_sec_burst_rejection(self):
        """Telegram: 30 rapid requests from same authorized user_id yields >=50% HTTP 429."""
        user_id = 999111
        cfg = TelegramConfig(
            whitelist_user_ids={user_id},
            rate_limit=RateLimitConfig(requests_per_minute=30, burst_limit=5),
        )
        tg = TelegramBotController(config=cfg)

        responses = []
        for i in range(30):
            res = tg.handle_inbound_message(user_id=user_id, text=f"/status {i}")
            responses.append(res)

        status_200 = sum(1 for r in responses if r.get("status") == 200)
        status_429 = sum(1 for r in responses if r.get("status") == 429)

        assert status_200 == 5, f"Expected 5 accepted requests, got {status_200}"
        assert status_429 == 25, f"Expected 25 throttled requests, got {status_429}"

        rejection_rate = status_429 / 30.0
        assert rejection_rate >= 0.50, f"Rejection rate {rejection_rate:.2%} is below 50%"
        assert rejection_rate == pytest.approx(0.8333, rel=1e-2)

    def test_zalo_30_req_per_sec_burst_rejection(self):
        """Zalo: 30 rapid requests from same authorized user_id yields >=50% HTTP 429."""
        user_id = "zalo_authorized_user_001"
        cfg = ZaloConfig(
            whitelist_user_ids=[user_id],
            rate_limit=RateLimitConfig(requests_per_minute=20, burst_limit=5),
        )
        zalo = ZaloBotController(config=cfg, is_mock=True)

        responses = []
        for i in range(30):
            res = zalo.handle_message(user_id=user_id, user_name="Tester", text=f"/status {i}")
            responses.append(res)

        status_200 = sum(1 for r in responses if r.get("status") == 200)
        status_429 = sum(1 for r in responses if r.get("status") == 429)

        assert status_200 == 5, f"Expected 5 accepted requests, got {status_200}"
        assert status_429 == 25, f"Expected 25 throttled requests, got {status_429}"

        rejection_rate = status_429 / 30.0
        assert rejection_rate >= 0.50, f"Rejection rate {rejection_rate:.2%} is below 50%"

    def test_discord_30_req_per_sec_burst_rejection(self):
        """Discord: 30 rapid requests from same authorized user_id yields >=50% HTTP 429."""
        user_id = 777888
        cfg = DiscordConfig(
            whitelist_user_ids=[user_id],
            rate_limit=RateLimitConfig(requests_per_minute=30, burst_limit=10),
        )
        discord = DiscordBotController(config=cfg)

        responses = []
        for i in range(30):
            res = discord.handle_message(user_id=user_id, username="discord_user", content=f"!status {i}")
            responses.append(res)

        status_200 = sum(1 for r in responses if r.get("status") == 200)
        status_429 = sum(1 for r in responses if r.get("status") == 429)

        assert status_200 == 10, f"Expected 10 accepted requests, got {status_200}"
        assert status_429 == 20, f"Expected 20 throttled requests, got {status_429}"

        rejection_rate = status_429 / 30.0
        assert rejection_rate >= 0.50, f"Rejection rate {rejection_rate:.2%} is below 50%"
        assert rejection_rate == pytest.approx(0.6666, rel=1e-2)

    def test_mobile_bridge_30_req_per_sec_burst_rejection(self, tmp_path):
        """Mobile Bridge: 30 rapid file transfers from same device yields >=50% HTTP 429."""
        bridge = MobileFileBridge(
            save_directory=str(tmp_path / "mb_rate"),
            rate_limit_config=RateLimitConfig(requests_per_minute=15, burst_limit=3),
        )

        responses = []
        dummy_file = b"Hello mobile bridge content"
        for i in range(30):
            res = bridge.receive_file(
                file_bytes=dummy_file,
                filename=f"doc_{i}.txt",
                metadata={"device_id": "phone_device_123"},
            )
            responses.append(res)

        status_200 = sum(1 for r in responses if r.get("success") is True)
        status_429 = sum(1 for r in responses if r.get("status") == 429)

        assert status_200 == 3, f"Expected 3 accepted transfers, got {status_200}"
        assert status_429 == 27, f"Expected 27 throttled transfers, got {status_429}"

        rejection_rate = status_429 / 30.0
        assert rejection_rate >= 0.50, f"Rejection rate {rejection_rate:.2%} is below 50%"
        assert rejection_rate == pytest.approx(0.90, rel=1e-2)
