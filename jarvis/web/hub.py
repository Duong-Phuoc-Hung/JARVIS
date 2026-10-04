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
        unavailable_sections = []
        try:
            crypto_rates = self.get_crypto_rates()
            crypto_speech = f"BTC ${crypto_rates['BTC']:,.0f} | ETH ${crypto_rates['ETH']:,.0f}"
        except (RuntimeError, ValueError, KeyError):
            crypto_rates = {}
            crypto_speech = "Không lấy được giá tiền mã hóa hiện tại."
            unavailable_sections.append("crypto")
        try:
            usd_vnd_rate = self.finance.get_exchange_rate("USD", "VND")
            rate_speech = f"USD/VND {usd_vnd_rate:,.0f}"
        except (RuntimeError, ValueError):
            usd_vnd_rate = None
            rate_speech = "Không lấy được tỷ giá hiện tại."
            unavailable_sections.append("exchange_rate")

        # 4. Spoken Summary Formulation
        now = datetime.datetime.now()
        greeting = "Chào buổi sáng thưa Ngài." if now.hour < 12 else "Chào buổi chiều thưa Ngài."

        spoken_parts = [
            f"{greeting} Sau đây là bản tin tổng hợp hôm nay:",
            weather_speech,
            f"Về thị trường tài chính: {crypto_speech}. {rate_speech}.",
            "Điểm qua 3 tin tức công nghệ nổi bật:",
        ]
        for idx, art in enumerate(top_news_articles, start=1):
            spoken_parts.append(f"Thứ {idx}: {art.title}.")

        spoken_summary = " ".join(spoken_parts)

        # 5. Overlay UI Bullet Points
        overlay_bullets = [
            f"🌤️ **Thời tiết {weather_data.city}**: {weather_data.temp_c:.1f}°C, {weather_data.condition} (Độ ẩm {weather_data.humidity}%)",
            f"💰 **Thị trường**: {crypto_speech} | {rate_speech}",
            "📰 **Tin tức nổi bật**:",
        ]
        for idx, art in enumerate(top_news_articles, start=1):
            overlay_bullets.append(f"  • {art.title}")

        return {
            "success": not unavailable_sections,
            "status": "LIMITED" if unavailable_sections else "SUCCESS",
            "unavailable_sections": unavailable_sections,
            "city": weather_data.city,
            "weather": weather_data.to_dict(),
            "weather_speech": weather_speech,
            "news": news_headlines,
            "news_articles": [a.to_dict() for a in top_news_articles],
            "crypto": crypto_rates,
            "usd_vnd_rate": usd_vnd_rate,
            "crypto_speech": crypto_speech,
            "spoken_summary": spoken_summary,
            # Backward-compatible public key used by integrations that call
            # the hub directly instead of going through the dispatcher.
            "speech_text": spoken_summary,
            "overlay_bullets": overlay_bullets,
            "timestamp": now.isoformat(),
        }

    def conduct_deep_research(self, topic: str, max_sources: int = 3) -> dict[str, Any]:
        """
        Conducts deep multi-source research on a topic, compiles an executive report,
        and saves it to Desktop/JARVIS_Research_{slug}.md.
        """
        import datetime
        import os
        from pathlib import Path
        clean_topic = topic.strip()
        search_results = self.searcher.search(clean_topic, max_results=max_sources)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"# 📑 Báo Cáo Nghiên Cứu Chuyên Sâu: {clean_topic}",
            f"*Thời gian thực hiện: {now_str}*",
            "",
            "## 1. Tóm Tắt Tổng Quan (Executive Summary)",
        ]

        if not search_results:
            lines.append("Không tìm thấy đủ dữ liệu công khai trên Internet cho chủ đề này.")
        else:
            snippets = [getattr(r, "snippet", "") for r in search_results if getattr(r, "snippet", "")]
            combined_snippet = " ".join(snippets[:2])[:300]
            lines.append(f"Chủ đề **{clean_topic}** đã được tổng hợp từ {len(search_results)} nguồn thông tin uy tín. {combined_snippet}")

            lines.append("\n## 2. Các Luận Điểm Then Chốt (Key Findings)")
            for i, item in enumerate(search_results, 1):
                t = getattr(item, "title", f"Nguồn {i}")
                s = getattr(item, "snippet", "")
                lines.append(f"- **{t}**: {s}")

            lines.append("\n## 3. Danh Mục Nguồn Tham Khảo (References)")
            for i, item in enumerate(search_results, 1):
                t = getattr(item, "title", f"Nguồn {i}")
                u = getattr(item, "url", "")
                lines.append(f"{i}. [{t}]({u})")

        report_md = "\n".join(lines)
        file_path_str = ""
        try:
            desktop = Path.home() / "Desktop"
            if desktop.exists():
                safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in clean_topic)[:30] or "report"
                target_file = desktop / f"JARVIS_Research_{safe_name}.md"
                target_file.write_text(report_md, encoding="utf-8")
                file_path_str = str(target_file)
        except Exception as exc:
            logger.debug("Failed to write research report to Desktop: %s", exc)

        if not search_results:
            spoken_summary = f"Tôi đã tìm kiếm về {clean_topic} nhưng chưa thấy dữ liệu trực tuyến phù hợp, thưa Ngài."
        elif file_path_str:
            spoken_summary = f"Đã hoàn thành báo cáo nghiên cứu về {clean_topic} từ {len(search_results)} nguồn. Tôi đã lưu chi tiết ra màn hình Desktop cho Ngài."
        else:
            spoken_summary = f"Đã hoàn thành báo cáo nghiên cứu về {clean_topic} từ {len(search_results)} nguồn, thưa Ngài."

        return {
            "success": bool(search_results),
            "topic": clean_topic,
            "sources_count": len(search_results),
            "spoken_summary": spoken_summary,
            "report_path": file_path_str,
            "report_markdown": report_md,
        }
