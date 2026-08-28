"""
jarvis/web/hub.py
=================
Master Web Intelligence Hub for JARVIS.
Coordinates Web Search, Weather, News Aggregation, and Financial Tracking.
Implements unified 10-minute TTL caching and Morning Briefing generation.
"""
from __future__ import annotations

import datetime
import logging
import socket
from typing import Any

from jarvis.web.cache import TTLCache
from jarvis.web.finance import FinanceTracker
from jarvis.web.news import NewsAggregator
from jarvis.web.search import WebSearcher
from jarvis.web.weather import WeatherProvider

logger = logging.getLogger("jarvis.web.hub")


class WebIntelligenceHub:
    """
    Central Coordinator for real-time web intelligence and daily briefings.
    """

    def __init__(
        self,
        cache_ttl_seconds: float = 600.0,
        weather_api_key: str | None = None,
        default_city: str = "Hà Nội",
        search_engine: WebSearcher | None = None,
        weather_provider: WeatherProvider | None = None,
        news_aggregator: NewsAggregator | None = None,
        finance_tracker: FinanceTracker | None = None,
        cache: TTLCache | None = None,
    ) -> None:
        self.cache = cache or TTLCache(default_ttl_seconds=cache_ttl_seconds)
        self.searcher = search_engine or WebSearcher(cache=self.cache, cache_ttl=cache_ttl_seconds)
        self.weather = weather_provider or WeatherProvider(
            api_key=weather_api_key,
            default_city=default_city,
            cache=self.cache,
            cache_ttl=cache_ttl_seconds,
        )
        self.news = news_aggregator or NewsAggregator(cache=self.cache, cache_ttl=cache_ttl_seconds)
        self.finance = finance_tracker or FinanceTracker(cache=self.cache, cache_ttl=cache_ttl_seconds)
        self.default_city = default_city

    def is_online(self, host: str = "1.1.1.1", port: int = 53, timeout: float = 1.5) -> bool:
        """
        Performs a lightweight DNS socket reachability test.
        """
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            return True
        except Exception:
            return False

    def clear_cache(self) -> None:
        """Flushes all cached web data."""
        self.cache.clear()

    # ──────────────────────────────────────────────────────────────────────────
    # Core Interfaces (Specified in PROJECT.md Interface Contracts)
    # ──────────────────────────────────────────────────────────────────────────

    def search(self, query: str) -> str:
        """
        Executes web search and returns concise Vietnamese summary.
        """
        return self.searcher.search_and_summarize(query)

    def get_weather(self, city: str = "Hanoi") -> str:
        """
        Returns vocalizable weather briefing for the requested city.
        """
        return self.weather.get_weather_speech(city)

    def get_top_news(self, limit: int = 3) -> list[str]:
        """
        Returns top technology news headline strings.
        """
        return self.news.get_news_headlines(category="tech", limit=limit)

    def get_crypto_rates(self) -> dict[str, float]:
        """
        Returns realtime cryptocurrency prices in USD.
        """
        btc = self.finance.get_crypto_price("BTC", "USD")
        eth = self.finance.get_crypto_price("ETH", "USD")
        return {
            "BTC": float(btc.get("price", 0.0)),
            "ETH": float(eth.get("price", 0.0)),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Morning Briefing Synthesis ("JARVIS, briefing sáng nay")
    # ──────────────────────────────────────────────────────────────────────────

    def generate_morning_briefing(self, city: str | None = None) -> dict[str, Any]:
        """
        Synthesizes a daily briefing composed of:
          - Weather forecast
          - Top 3 headlines
          - Crypto rates (BTC, ETH)
          - USD/VND currency rate
          - Spoken summary for TTS vocalization
          - Structured bullet list for Overlay UI display
        """
        target_city = city or self.default_city

        # 1. Weather
        weather_data = self.weather.get_weather(target_city)
        weather_speech = self.weather.format_weather_speech(weather_data)

        # 2. News
        top_news_articles = self.news.get_top_news(category="tech", limit=3)
        news_headlines = [f"{a.title} ({a.source})" if a.source else a.title for a in top_news_articles]

        # 3. Crypto & Currency
        crypto_rates = self.get_crypto_rates()
        btc_price = crypto_rates.get("BTC", 0.0)
        eth_price = crypto_rates.get("ETH", 0.0)
        usd_vnd_rate = self.finance.get_exchange_rate("USD", "VND")
        crypto_speech = self.finance.get_crypto_summary()

        # 4. Spoken Summary Formulation
        now = datetime.datetime.now()
        greeting = "Chào buổi sáng thưa Ngài." if now.hour < 12 else "Chào buổi chiều thưa Ngài."

        spoken_parts = [
            f"{greeting} Sau đây là bản tin tổng hợp hôm nay:",
            weather_speech,
            f"Về thị trường tài chính: {crypto_speech}",
            "Điểm qua 3 tin tức công nghệ nổi bật:",
        ]
        for idx, art in enumerate(top_news_articles, start=1):
            spoken_parts.append(f"Thứ {idx}: {art.title}.")

        spoken_summary = " ".join(spoken_parts)

        # 5. Overlay UI Bullet Points
        overlay_bullets = [
            f"🌤️ **Thời tiết {weather_data.city}**: {weather_data.temp_c:.1f}°C, {weather_data.condition} (Độ ẩm {weather_data.humidity}%)",
            f"💰 **Thị trường**: BTC ${btc_price:,.0f} | ETH ${eth_price:,.0f} | USD/VND {usd_vnd_rate:,.0f}",
            "📰 **Tin tức nổi bật**:",
        ]
        for idx, art in enumerate(top_news_articles, start=1):
            overlay_bullets.append(f"  • {art.title}")

        return {
            "city": weather_data.city,
            "weather": weather_data.to_dict(),
            "weather_speech": weather_speech,
            "news": news_headlines,
            "news_articles": [a.to_dict() for a in top_news_articles],
            "crypto": crypto_rates,
            "usd_vnd_rate": usd_vnd_rate,
            "crypto_speech": crypto_speech,
            "spoken_summary": spoken_summary,
            "overlay_bullets": overlay_bullets,
            "timestamp": now.isoformat(),
        }
