"""
tests/integration/test_web_intelligence_live.py
================================================
Live Runtime Network Verification for P2-14 Web Intelligence Hub.

WARNING:
This test suite executes real, unmocked HTTP requests over the public internet to:
  1. wttr.in (Zero-config JSON weather provider)
  2. vnexpress.net (Vietnamese RSS news feeds)
  3. api.coingecko.com / exchange endpoints (Realtime crypto/forex rates)

It is BRITTLE BY NATURE (depends on external service availability, rate limits, and internet routing).
Per epistemic audit rules:
  - Marked with `@pytest.mark.live_network`
  - Pre-probes host connectivity to cleanly distinguish offline/timeout (SKIP) from parse failure (FAIL)
  - Enforces strict sanity bounds on all returned values (e.g. realistic temperatures, non-empty titles)
  - Bypasses TTLCache to guarantee every execution performs genuine network I/O
"""
from __future__ import annotations

import datetime
import socket
import urllib.error
import urllib.request
from typing import Any

import pytest

from jarvis.web.cache import TTLCache
from jarvis.web.hub import WebIntelligenceHub
from jarvis.web.news import NewsAggregator
from jarvis.web.weather import WeatherProvider


def _is_host_reachable(host: str, port: int = 80, timeout: float = 3.0) -> bool:
    """Pre-probe TCP connectivity to separate offline environment from API parser bugs."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.gaierror, socket.timeout, OSError):
        return False


@pytest.mark.live_network
class TestWebIntelligenceLiveRuntime:
    """
    Empirical runtime verification suite for P2-14 Web Intelligence.
    Requires an active internet connection.
    """

    @pytest.fixture(autouse=True)
    def record_timestamp(self):
        self.run_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def test_live_weather_wttr_in_sanity_bounds(self):
        """
        [P2-14 Live] Fetch real-time weather from wttr.in for Hanoi and verify sanity bounds.
        """
        if not _is_host_reachable("wttr.in", port=80, timeout=3.0):
            pytest.skip("wttr.in is unreachable (DNS or TCP connect failed) — skipping live test.")

        # Condition 2: Use fresh 0-TTL cache to guarantee genuine network call
        fresh_cache = TTLCache(default_ttl_seconds=0.001)
        provider = WeatherProvider(cache=fresh_cache, timeout_seconds=6.0)

        weather = provider.get_weather("Hà Nội")

        # Condition 3: Sanity bounds verification (reject parse errors, sentinel defaults, or corrupted data)
        assert weather.city in ("Hà Nội", "Hanoi"), f"Unexpected city name: {weather.city!r}"
        assert -5.0 <= weather.temp_c <= 50.0, (
            f"Temperature out of realistic bounds for Hanoi: {weather.temp_c}°C"
        )
        assert -10.0 <= weather.feels_like_c <= 55.0, (
            f"Feels-like temperature out of realistic bounds: {weather.feels_like_c}°C"
        )
        assert 0 <= weather.humidity <= 100, f"Humidity out of percentage bounds: {weather.humidity}%"
        assert weather.condition and len(weather.condition.strip()) > 0, "Condition string is empty"
        assert weather.source == "wttr.in", f"Expected wttr.in fallback, got {weather.source!r}"

    def test_live_vnexpress_rss_news_headlines(self):
        """
        [P2-14 Live] Fetch and parse real technology RSS headlines from VnExpress.
        """
        if not _is_host_reachable("vnexpress.net", port=80, timeout=3.0):
            pytest.skip("vnexpress.net is unreachable — skipping live test.")

        fresh_cache = TTLCache(default_ttl_seconds=0.001)
        aggregator = NewsAggregator(cache=fresh_cache, timeout_seconds=6.0)

        articles = aggregator.get_top_news(category="tech", limit=3)

        assert len(articles) >= 1, "VnExpress RSS feed returned 0 articles"
        for idx, article in enumerate(articles):
            assert article.title and len(article.title.strip()) >= 10, (
                f"Article #{idx} title too short or empty: {article.title!r}"
            )
            assert article.link.startswith("http://") or article.link.startswith("https://"), (
                f"Article #{idx} has invalid URL: {article.link!r}"
            )
            assert "VnExpress" in article.source, (
                f"Article #{idx} source unexpected: {article.source!r}"
            )

    def test_live_morning_briefing_end_to_end_synthesis(self):
        """
        [P2-14 Live] End-to-end synthesis of daily morning briefing combining real weather and news.
        """
        if not _is_host_reachable("wttr.in", port=80, timeout=3.0):
            pytest.skip("Internet endpoints unreachable — skipping live briefing test.")

        fresh_cache = TTLCache(default_ttl_seconds=0.001)
        from jarvis.web.finance import FinanceTracker
        finance = FinanceTracker(cache=fresh_cache, cache_ttl=0.001, timeout_seconds=2.0)
        weather = WeatherProvider(cache=fresh_cache, cache_ttl=0.001, timeout_seconds=3.0)
        news = NewsAggregator(cache=fresh_cache, cache_ttl=0.001, timeout_seconds=3.0)
        hub = WebIntelligenceHub(
            cache=fresh_cache,
            cache_ttl_seconds=0.001,
            finance_tracker=finance,
            weather_provider=weather,
            news_aggregator=news,
        )

        briefing = hub.generate_morning_briefing(city="Hà Nội")

        assert isinstance(briefing, dict), "Briefing output must be a dictionary"
        assert briefing["city"] in ("Hà Nội", "Hanoi")
        assert "weather" in briefing and briefing["weather"] is not None
        assert "news" in briefing and len(briefing["news"]) >= 1

        spoken = briefing.get("spoken_summary", "")
        assert spoken and len(spoken) > 50, f"Spoken summary is too short: {spoken!r}"
        assert "Hà Nội" in spoken or "Hanoi" in spoken, "Spoken summary does not mention target city"
        assert "Thời tiết" in spoken, "Spoken summary does not include weather section"

        bullets = briefing.get("overlay_bullets", [])
        assert len(bullets) >= 3, f"Expected at least 3 overlay bullet items, got {len(bullets)}"
