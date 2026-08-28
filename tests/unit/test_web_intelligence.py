"""
tests/unit/test_web_intelligence.py
===================================
Comprehensive Unit Test Suite for Web Intelligence Subsystem (R5).
Covers:
  - TTLCache (10-minute TTL, thread-safety, eviction, deterministic key hashing)
  - WebSearcher (DuckDuckGo, HTML fallback, LLM summarization, offline handling)
  - WeatherProvider (OpenWeatherMap, wttr.in fallback, city aliases, speech synthesis)
  - NewsAggregator (RSS 2.0 & Atom XML parsing via stdlib xml.etree, CDATA cleaning)
  - FinanceTracker (BTC/ETH rates in USD & VND, USD/VND exchange, Stock lookups)
  - WebIntelligenceHub (Master coordination, Morning Briefing synthesis)
"""
from __future__ import annotations

import concurrent.futures
import datetime
import json
import threading
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from jarvis.web.cache import CacheEntry, TTLCache
from jarvis.web.finance import CryptoQuote, FinanceTracker, StockQuote
from jarvis.web.hub import WebIntelligenceHub
from jarvis.web.news import NewsAggregator, NewsArticle
from jarvis.web.search import SearchResultItem, WebSearcher
from jarvis.web.weather import WeatherData, WeatherProvider

# ============================================================================
# 1. TTL CACHE TESTS (10-Minute Caching Layer)
# ============================================================================

def test_ttl_cache_basic_hit_miss_and_overwrite():
    """Verify basic set, get, hit, miss, and delete in TTLCache."""
    cache = TTLCache(default_ttl_seconds=600.0)

    # Miss
    assert cache.get("non_existent") is None
    assert not cache.has("non_existent")

    # Set and Hit
    cache.set("weather:hanoi", {"temp": 28.5, "condition": "Sunny"})
    assert cache.has("weather:hanoi")
    cached = cache.get("weather:hanoi")
    assert cached["temp"] == 28.5
    assert cached["condition"] == "Sunny"

    # Delete
    assert cache.delete("weather:hanoi") is True
    assert cache.get("weather:hanoi") is None
    assert cache.delete("weather:hanoi") is False


def test_ttl_cache_expiration():
    """Verify cached item expires after specified TTL."""
    cache = TTLCache(default_ttl_seconds=0.05)  # 50ms TTL

    cache.set("crypto:btc", 65000.0)
    assert cache.get("crypto:btc") == 65000.0

    time.sleep(0.06)
    assert cache.get("crypto:btc") is None
    assert not cache.has("crypto:btc")


def test_ttl_cache_cleanup_expired():
    """Verify cleanup_expired removes dead entries and reports count."""
    cache = TTLCache(default_ttl_seconds=0.05)
    cache.set("k1", "v1", ttl=0.02)
    cache.set("k2", "v2", ttl=0.02)
    cache.set("k3", "v3", ttl=10.0)

    time.sleep(0.03)
    purged = cache.cleanup_expired()
    assert purged == 2
    assert cache.size() == 1
    assert cache.get("k3") == "v3"


def test_ttl_cache_deterministic_make_key():
    """Verify make_key produces consistent, deterministic hash keys."""
    key1 = TTLCache.make_key("search", query="thời tiết", limit=5)
    key2 = TTLCache.make_key("search", limit=5, query="thời tiết")
    assert key1 == key2
    assert key1.startswith("search:")


def test_ttl_cache_thread_safety_concurrency():
    """Verify TTLCache remains consistent under 30 concurrent read/write threads."""
    cache = TTLCache(default_ttl_seconds=600.0)
    num_threads = 30
    iterations_per_thread = 50

    def worker(worker_id: int):
        for i in range(iterations_per_thread):
            k = f"key_{worker_id}_{i % 5}"
            cache.set(k, f"val_{worker_id}_{i}")
            _ = cache.get(k)
            if i % 10 == 0:
                cache.cleanup_expired()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert cache.size() > 0


def test_ttl_cache_get_or_set():
    """Verify get_or_set computes value on miss and returns cached on hit."""
    cache = TTLCache(default_ttl_seconds=600.0)
    compute_count = 0

    def factory():
        nonlocal compute_count
        compute_count += 1
        return "expensive_result"

    res1 = cache.get_or_set("calc_key", factory)
    assert res1 == "expensive_result"
    assert compute_count == 1

    res2 = cache.get_or_set("calc_key", factory)
    assert res2 == "expensive_result"
    assert compute_count == 1  # Not recomputed


# ============================================================================
# 2. WEB SEARCH ENGINE TESTS
# ============================================================================

def test_web_search_ddgs_mock():
    """Test DuckDuckGo search integration with mock DDGS client."""
    mock_ddgs_results = [
        {"title": "OpenAI ra mắt GPT-5", "href": "https://tech.com/gpt5", "body": "Mô hình mới với khả năng vượt trội."},
        {"title": "Google nâng cấp Gemini 1.5", "href": "https://google.com/gemini", "body": "Mở rộng ngữ cảnh 2M tokens."},
    ]

    class MockDDGS:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def text(self, query, max_results=5):
            return mock_ddgs_results[:max_results]

    cache = TTLCache()
    searcher = WebSearcher(cache=cache)

    with patch("jarvis.web.search.DDGS_AVAILABLE", True), \
         patch("jarvis.web.search.DDGS", MockDDGS):
        results = searcher.search("công nghệ AI mới nhất", max_results=2)
        assert len(results) == 2
        assert results[0]["title"] == "OpenAI ra mắt GPT-5"
        assert results[0]["url"] == "https://tech.com/gpt5"

        # Verify cached
        cached_res = cache.get(cache.make_key("web_search", query="công nghệ ai mới nhất", limit=2))
        assert cached_res is not None
        assert len(cached_res) == 2


def test_web_search_html_scraper_fallback():
    """Test HTML parsing fallback when DDGS is unavailable."""
    sample_html = """
    <html>
      <body>
        <h2><a class="result__a" href="https://vnexpress.net/ai-article">Trí tuệ nhân tạo phát triển vượt bậc</a></h2>
        <a class="result__snippet">Các ứng dụng AI đang thay đổi cuộc sống hàng ngày của con người.</a>
      </body>
    </html>
    """

    searcher = WebSearcher()
    with patch("jarvis.web.search.DDGS_AVAILABLE", False), \
         patch("jarvis.web.search.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.text = sample_html
        mock_get.return_value = mock_resp

        results = searcher.search("AI phát triển")
        assert len(results) >= 1
        assert "Trí tuệ nhân tạo" in results[0]["title"]
        assert "https://vnexpress.net/ai-article" in results[0]["url"]


def test_web_search_and_summarize():
    """Test search result formatting into natural Vietnamese speech summary."""
    searcher = WebSearcher()
    mock_results = [
        {"title": "Dự báo kinh tế Việt Nam 2026", "snippet": "Tăng trưởng GDP dự kiến đạt 6.8%."},
        {"title": "Chỉ số lạm phát duy trì ổn định", "snippet": "Lạm phát được kiểm soát dưới 4%."},
    ]

    with patch.object(searcher, "search", return_value=mock_results):
        summary = searcher.search_and_summarize("kinh tế việt nam")
        assert "Theo kết quả tìm kiếm cho 'kinh tế việt nam':" in summary
        assert "1. Dự báo kinh tế Việt Nam 2026" in summary
        assert "Tăng trưởng GDP dự kiến đạt 6.8%" in summary


# ============================================================================
# 3. WEATHER PROVIDER TESTS
# ============================================================================

def test_weather_city_normalization():
    """Verify city name aliases are properly normalized."""
    provider = WeatherProvider()
    assert provider.normalize_city_name("hanoi") == "Hà Nội"
    assert provider.normalize_city_name("thời tiết ở Hà Nội") == "Hà Nội"
    assert provider.normalize_city_name("tp hcm") == "TP. Hồ Chí Minh"
    assert provider.normalize_city_name("saigon") == "TP. Hồ Chí Minh"
    assert provider.normalize_city_name("đà nẵng") == "Đà Nẵng"
    assert provider.normalize_city_name("da lat") == "Đà Lạt"


def test_weather_openweathermap_parsing():
    """Test parsing OpenWeatherMap API JSON response."""
    provider = WeatherProvider(api_key="mock_weather_key")

    mock_owm_response = {
        "name": "Hanoi",
        "main": {
            "temp": 29.4,
            "feels_like": 32.1,
            "humidity": 82,
            "pressure": 1008,
        },
        "weather": [
            {"description": "mưa rào rải rác"}
        ],
        "wind": {
            "speed": 4.5,
        },
        "visibility": 8000,
    }

    with patch("jarvis.web.weather.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_owm_response
        mock_get.return_value = mock_resp

        data = provider.get_weather("Hà Nội")
        assert isinstance(data, WeatherData)
        assert data.city == "Hà Nội"
        assert data.temp_c == 29.4
        assert data.feels_like_c == 32.1
        assert "Mưa rào rải rác" in data.condition
        assert data.humidity == 82
        assert data.wind_kph == 16.2  # 4.5 * 3.6
        assert data.source == "openweathermap"

        # Check speech format
        speech = provider.format_weather_speech(data)
        assert "Thời tiết tại Hà Nội hiện tại là 29.4°C" in speech
        assert "cảm giác như 32.1°C" in speech
        assert "Độ ẩm 82%" in speech


def test_weather_wttr_in_fallback_parsing():
    """Test wttr.in JSON fallback parsing when OpenWeatherMap key is absent."""
    provider = WeatherProvider(api_key="")  # No key -> wttr.in

    mock_wttr_response = {
        "current_condition": [
            {
                "temp_C": "26",
                "FeelsLikeC": "27",
                "humidity": "70",
                "windspeedKmph": "14",
                "weatherDesc": [{"value": "Partly cloudy"}],
            }
        ]
    }

    with patch("jarvis.web.weather.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_wttr_response
        mock_get.return_value = mock_resp

        data = provider.get_weather("Đà Nẵng")
        assert data.city == "Đà Nẵng"
        assert data.temp_c == 26.0
        assert data.condition == "Có mây rải rác"
        assert data.humidity == 70
        assert data.source == "wttr.in"


# ============================================================================
# 4. RSS NEWS AGGREGATOR TESTS
# ============================================================================

def test_news_rss_20_xml_parsing():
    """Verify RSS 2.0 XML parsing with CDATA stripping via stdlib xml.etree."""
    rss_xml = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <title>VnExpress Số Hóa</title>
        <item>
          <title><![CDATA[Chip AI thế hệ mới đạt hiệu năng đột phá]]></title>
          <link>https://vnexpress.net/chip-ai-moi-12345.html</link>
          <description><![CDATA[<a href="..."><img src="..." /></a>Thế hệ chip xử lý mới tối ưu cho suy luận cục bộ.]]></description>
          <pubDate>Mon, 24 Aug 2026 08:00:00 +0700</pubDate>
        </item>
        <item>
          <title>Công bố giải pháp an ninh mạng tự động</title>
          <link>https://vnexpress.net/cybersecurity-67890.html</link>
          <description>Hệ thống tự động phát hiện và ngăn chặn mã độc.</description>
          <pubDate>Mon, 24 Aug 2026 07:30:00 +0700</pubDate>
        </item>
      </channel>
    </rss>
    """

    aggregator = NewsAggregator()
    articles = aggregator.parse_feed_xml(rss_xml, source_name="VnExpress")

    assert len(articles) == 2
    assert articles[0].title == "Chip AI thế hệ mới đạt hiệu năng đột phá"
    assert articles[0].link == "https://vnexpress.net/chip-ai-moi-12345.html"
    assert "<img" not in articles[0].description
    assert "Thế hệ chip xử lý mới" in articles[0].description
    assert articles[0].source == "VnExpress"

    assert articles[1].title == "Công bố giải pháp an ninh mạng tự động"


def test_news_atom_xml_parsing():
    """Verify Atom XML feed parsing."""
    atom_xml = """<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Tech News Atom</title>
      <entry>
        <title>Open Source AI Model Released</title>
        <link href="https://tech.com/open-ai-model" />
        <summary>New open weight model outperforms previous benchmarks.</summary>
        <published>2026-08-24T06:00:00Z</published>
      </entry>
    </feed>
    """

    aggregator = NewsAggregator()
    articles = aggregator.parse_feed_xml(atom_xml)

    assert len(articles) == 1
    assert articles[0].title == "Open Source AI Model Released"
    assert articles[0].link == "https://tech.com/open-ai-model"
    assert "outperforms previous benchmarks" in articles[0].description


def test_news_headlines_and_summary_formatting():
    """Test news headlines extraction and spoken summary formatting."""
    aggregator = NewsAggregator()
    mock_articles = [
        NewsArticle(title="Tin 1: Ra mắt robot hình người mới", link="url1", source="TechCrunch"),
        NewsArticle(title="Tin 2: Đột phá pin thể rắn", link="url2", source="VnExpress"),
        NewsArticle(title="Tin 3: Mở rộng mạng 6G thử nghiệm", link="url3", source="VnExpress"),
    ]

    with patch.object(aggregator, "get_top_news", return_value=mock_articles):
        headlines = aggregator.get_news_headlines(limit=3)
        assert len(headlines) == 3
        assert "Tin 1: Ra mắt robot hình người mới (TechCrunch)" in headlines

        summary = aggregator.format_news_summary()
        assert "Dưới đây là 3 tin tức công nghệ nổi bật:" in summary
        assert "1. Tin 1: Ra mắt robot hình người mới (TechCrunch)" in summary


# ============================================================================
# 5. FINANCE & CRYPTO TRACKER TESTS
# ============================================================================

def test_finance_exchange_rate_usd_vnd():
    """Test USD/VND exchange rate querying and fallback."""
    tracker = FinanceTracker()

    with patch("jarvis.web.finance.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rates": {"VND": 25520.0}}
        mock_get.return_value = mock_resp

        rate = tracker.get_exchange_rate("USD", "VND")
        assert rate == 25520.0


def test_finance_crypto_price_binance():
    """Test crypto pricing from Binance ticker API."""
    tracker = FinanceTracker()

    with patch("jarvis.web.finance.requests.get") as mock_get, \
         patch.object(tracker, "get_exchange_rate", return_value=25000.0):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"lastPrice": "68500.50", "priceChangePercent": "2.45"}
        mock_get.return_value = mock_resp

        btc = tracker.get_crypto_price("BTC", "USD")
        assert btc["symbol"] == "BTC"
        assert btc["price"] == 68500.50
        assert btc["change_24h_pct"] == 2.45
        assert btc["price_vnd"] == 68500.50 * 25000.0


def test_finance_stock_quote_yahoo():
    """Test stock ticker quote parsing for VN-Index and US stocks."""
    tracker = FinanceTracker()

    mock_chart_data = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": 1285.4,
                        "previousClose": 1275.0,
                        "currency": "VND",
                        "shortName": "VN-Index",
                    }
                }
            ]
        }
    }

    with patch("jarvis.web.finance.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_chart_data
        mock_get.return_value = mock_resp

        quote = tracker.get_stock_quote("VNINDEX")
        assert quote.ticker == "VNINDEX"
        assert quote.price == 1285.4
        assert quote.change_pct == 0.82  # (1285.4 - 1275) / 1275 * 100


def test_finance_crypto_summary_speech():
    """Test crypto summary speech formulation."""
    tracker = FinanceTracker()
    with patch.object(tracker, "get_crypto_price", side_effect=[
        {"price": 68000.0, "change_24h_pct": 1.5},
        {"price": 3500.0, "change_24h_pct": -0.8},
    ]):
        summary = tracker.get_crypto_summary()
        assert "Bitcoin hiện ở mức $68,000 (+1.5%)" in summary
        assert "Ethereum đạt $3,500 (-0.8%)" in summary


# ============================================================================
# 6. MASTER WEB INTELLIGENCE HUB & MORNING BRIEFING TESTS
# ============================================================================

def test_web_hub_generate_morning_briefing():
    """Verify generate_morning_briefing aggregates weather, top 3 news, and crypto."""
    hub = WebIntelligenceHub(default_city="Hà Nội")

    mock_weather = WeatherData(
        city="Hà Nội",
        temp_c=28.0,
        feels_like_c=30.0,
        condition="Nhiều mây, có nắng nhẹ",
        humidity=78,
        wind_kph=12.0,
    )
    mock_articles = [
        NewsArticle(title="Công bố chip AI 3nm thế hệ mới", link="url1", source="VnExpress"),
        NewsArticle(title="Đầu tư năng lượng tái tạo tăng trưởng mạnh", link="url2", source="VnExpress"),
        NewsArticle(title="Hạ tầng 5G phủ sóng toàn quốc", link="url3", source="TechCrunch"),
    ]

    with patch.object(hub.weather, "get_weather", return_value=mock_weather), \
         patch.object(hub.news, "get_top_news", return_value=mock_articles), \
         patch.object(hub.finance, "get_crypto_price", side_effect=lambda sym, vs="USD": {
             "BTC": {"price": 68000.0, "change_24h_pct": 2.0},
             "ETH": {"price": 3500.0, "change_24h_pct": 1.2},
         }.get(sym, {"price": 100.0, "change_24h_pct": 0.0})), \
         patch.object(hub.finance, "get_exchange_rate", return_value=25450.0):

        briefing = hub.generate_morning_briefing("Hà Nội")

        assert briefing["city"] == "Hà Nội"
        assert briefing["weather"]["temp_c"] == 28.0
        assert len(briefing["news"]) == 3
        assert briefing["crypto"]["BTC"] == 68000.0
        assert briefing["crypto"]["ETH"] == 3500.0
        assert briefing["usd_vnd_rate"] == 25450.0

        # Verify spoken summary
        spoken = briefing["spoken_summary"]
        assert "bản tin tổng hợp hôm nay" in spoken
        assert "Thời tiết tại Hà Nội" in spoken
        assert "Công bố chip AI 3nm thế hệ mới" in spoken

        # Verify Overlay bullets
        bullets = briefing["overlay_bullets"]
        assert len(bullets) >= 4
        assert any("Thời tiết Hà Nội" in b for b in bullets)
        assert any("BTC $68,000" in b for b in bullets)
        assert any("Công bố chip AI 3nm thế hệ mới" in b for b in bullets)


def test_web_hub_is_online_probe():
    """Verify is_online DNS connectivity probe."""
    hub = WebIntelligenceHub()
    # Should not raise exception
    res = hub.is_online(timeout=0.2)
    assert isinstance(res, bool)


def test_web_hub_clear_cache():
    """Verify clear_cache empties the shared cache."""
    hub = WebIntelligenceHub()
    hub.cache.set("test_key", "test_val")
    assert hub.cache.has("test_key")

    hub.clear_cache()
    assert not hub.cache.has("test_key")
