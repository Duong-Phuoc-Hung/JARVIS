"""
jarvis/web/weather.py
=====================
Real-Time Weather Intelligence Provider.
Primary: OpenWeatherMap API v2.5 / v3.0 (with localized Vietnamese descriptions).
Fallback: wttr.in JSON API (zero-configuration, zero-cost fallback).
Caches results in TTLCache for 10 minutes (600s).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

from jarvis.web.cache import TTLCache

logger = logging.getLogger("jarvis.web.weather")

# City alias normalizer dictionary
CITY_ALIASES = {
    "hanoi": "Hà Nội",
    "ha noi": "Hà Nội",
    "hà nội": "Hà Nội",
    "hn": "Hà Nội",
    "hcm": "TP. Hồ Chí Minh",
    "ho chi minh": "TP. Hồ Chí Minh",
    "hồ chí minh": "TP. Hồ Chí Minh",
    "tp hcm": "TP. Hồ Chí Minh",
    "tp.hcm": "TP. Hồ Chí Minh",
    "tp. hcm": "TP. Hồ Chí Minh",
    "saigon": "TP. Hồ Chí Minh",
    "sài gòn": "TP. Hồ Chí Minh",
    "danang": "Đà Nẵng",
    "da nang": "Đà Nẵng",
    "đà nẵng": "Đà Nẵng",
    "haiphong": "Hải Phòng",
    "hai phong": "Hải Phòng",
    "hải phòng": "Hải Phòng",
    "cantho": "Cần Thơ",
    "can tho": "Cần Thơ",
    "cần thơ": "Cần Thơ",
    "hue": "Huế",
    "huế": "Huế",
    "dalat": "Đà Lạt",
    "da lat": "Đà Lạt",
    "đà lạt": "Đà Lạt",
    "nhatrang": "Nha Trang",
    "nha trang": "Nha Trang",
    "vungtau": "Vũng Tàu",
    "vung tau": "Vũng Tàu",
    "vũng tàu": "Vũng Tàu",
}

# Weather condition translation dictionary for English APIs
CONDITION_TRANSLATIONS = {
    "clear": "Trời quang",
    "sunny": "Trời nắng",
    "partly cloudy": "Có mây rải rác",
    "cloudy": "Nhiều mây",
    "overcast": "U ám",
    "mist": "Sương mù nhẹ",
    "fog": "Sương mù",
    "patchy rain possible": "Có thể có mưa vài nơi",
    "light rain": "Mưa nhỏ",
    "moderate rain": "Mưa vừa",
    "heavy rain": "Mưa to",
    "thunderstorm": "Có dông sét",
    "shower rain": "Mưa rào",
    "scattered clouds": "Mây rải rác",
    "broken clouds": "Mây từng đám",
    "few clouds": "Ít mây",
    "light intensity shower rain": "Mưa rào nhẹ",
}


@dataclass
class WeatherData:
    """Structured weather observation metrics."""
    city: str
    temp_c: float
    feels_like_c: float
    condition: str
    humidity: int
    wind_kph: float = 0.0          # Wind speed in km/h (optional, 0 if unavailable)
    uv_index: float | None = None
    pressure_hpa: int | None = None
    visibility_km: float | None = None
    source: str = "wttr.in"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "temp_c": self.temp_c,
            "feels_like_c": self.feels_like_c,
            "condition": self.condition,
            "humidity": self.humidity,
            "wind_kph": self.wind_kph,
            "uv_index": self.uv_index,
            "pressure_hpa": self.pressure_hpa,
            "visibility_km": self.visibility_km,
            "source": self.source,
            "timestamp": self.timestamp,
        }


class WeatherProvider:
    """
    Fetches real-time meteorological conditions for Vietnamese and global cities.
    Employs OpenWeatherMap API with automatic wttr.in fallback.
    """

    DEFAULT_CITY = "Hà Nội"

    def __init__(
        self,
        api_key: str | None = None,
        default_city: str = DEFAULT_CITY,
        cache: TTLCache | None = None,
        cache_ttl: float = 600.0,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.api_key = (
            api_key
            if api_key is not None
            else (os.environ.get("OPENWEATHER_API_KEY") or os.environ.get("JARVIS_WEATHER_API_KEY", ""))
        )
        self.default_city = default_city
        self.cache = cache or TTLCache(default_ttl_seconds=cache_ttl)
        self.cache_ttl = cache_ttl
        self.timeout_seconds = timeout_seconds

    def normalize_city_name(self, city: str | None) -> str:
        """Standardizes user city string into formal Vietnamese city name."""
        if not city or not city.strip():
            return self.default_city

        cleaned = city.strip().lower()
        # Strip common leading conversational phrases like "thời tiết ở", "dự báo thời tiết tại", "cho tôi biết thời tiết ở"
        cleaned = re.sub(r"^(?:cho\s*tôi\s*(?:biết|xem)\s*)?(?:thời\s*tiết|dự\s*báo)?\s*(?:ở|tại|thành\s*phố|tp\.?)?\s*", "", cleaned).strip()
        # Also strip trailing conversational words like "hôm nay", "ngày mai", "bây giờ"
        cleaned = re.sub(r"\s+(?:hôm\s*nay|ngày\s*mai|bây\s*giờ|hiện\s*tại)$", "", cleaned).strip()

        if cleaned in CITY_ALIASES:
            return CITY_ALIASES[cleaned]

        raw_lower = city.strip().lower()
        if raw_lower in CITY_ALIASES:
            return CITY_ALIASES[raw_lower]

        return CITY_ALIASES.get(cleaned, city.strip())

    def get_weather(self, city: str | None = None) -> WeatherData:
        """
        Fetches current weather for the specified city, checking cache first.
        """
        norm_city = self.normalize_city_name(city)
        cache_key = self.cache.make_key("weather", city=norm_city.lower())

        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug("Returning cached weather data for %s", norm_city)
            if isinstance(cached, dict):
                return WeatherData(**cached)
            return cached

        weather_data: WeatherData | None = None

        # 1. Tier 1: OpenWeatherMap (if API key configured)
        if self.api_key:
            try:
                weather_data = self._fetch_openweathermap(norm_city)
            except Exception as exc:
                logger.debug("OpenWeatherMap API failed: %s, falling back to wttr.in", exc)

        # 2. Tier 2: wttr.in JSON API fallback
        if weather_data is None:
            try:
                weather_data = self._fetch_wttr_in(norm_city)
            except Exception as exc:
                logger.warning("wttr.in weather fetch failed: %s", exc)

        # 3. Tier 3: Offline Default Fallback
        if weather_data is None:
            weather_data = WeatherData(
                city=norm_city,
                temp_c=27.0,
                feels_like_c=29.0,
                condition="Nhiều mây",
                humidity=75,
                wind_kph=12.0,
                source="offline_fallback",
            )

        self.cache.set(cache_key, weather_data.to_dict(), ttl=self.cache_ttl)
        return weather_data

    def get_weather_speech(self, city: str | None = None) -> str:
        """Convenience method returning vocalizable text."""
        data = self.get_weather(city)
        return self.format_weather_speech(data)

    def format_weather_speech(self, data: WeatherData) -> str:
        """
        Translates WeatherData into a polite Vietnamese vocal briefing sentence.
        """
        city_name = data.city
        temp = data.temp_c
        feels_like = data.feels_like_c
        cond = data.condition.lower()
        humidity = data.humidity
        wind = getattr(data, "wind_kph", 0.0)  # Optional field, default to 0

        # Format temperature to 1 decimal place or int
        temp_str = f"{temp:.1f}".rstrip("0").rstrip(".") if isinstance(temp, float) else str(temp)
        feels_str = f"{feels_like:.1f}".rstrip("0").rstrip(".") if isinstance(feels_like, float) else str(feels_like)

        msg = f"Thời tiết tại {city_name} hiện tại là {temp_str}°C"
        if abs(temp - feels_like) >= 2.0:
            msg += f" (cảm giác như {feels_str}°C)"
        msg += f", {cond}."
        if wind and wind > 0:
            msg += f" Độ ẩm {humidity}%, sức gió {wind:.1f} km/h, thưa Ngài."
        else:
            msg += f" Độ ẩm {humidity}%, thưa Ngài."
        return msg

    # ──────────────────────────────────────────────────────────────────────────
    # Provider Implementations
    # ──────────────────────────────────────────────────────────────────────────

    def _fetch_openweathermap(self, city: str) -> WeatherData:
        """Queries OpenWeatherMap v2.5 /weather API."""
        encoded_city = urllib.parse.quote(city)
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q={encoded_city}&appid={self.api_key}&units=metric&lang=vi"
        )
        if REQUESTS_AVAILABLE and requests is not None:
            resp = requests.get(url, timeout=self.timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
        else:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))

        main = data.get("main", {})
        weather_list = data.get("weather", [{}])
        weather_first = weather_list[0] if weather_list else {}
        wind = data.get("wind", {})

        condition = weather_first.get("description", "Quang đãng").capitalize()
        temp_c = float(main.get("temp", 25.0))
        feels_like_c = float(main.get("feels_like", temp_c))
        humidity = int(main.get("humidity", 70))
        wind_speed_ms = float(wind.get("speed", 3.0))
        wind_kph = round(wind_speed_ms * 3.6, 1)
        pressure = main.get("pressure")
        visibility_m = data.get("visibility")
        visibility_km = round(visibility_m / 1000.0, 1) if visibility_m else None

        return WeatherData(
            city=city,
            temp_c=temp_c,
            feels_like_c=feels_like_c,
            condition=condition,
            humidity=humidity,
            wind_kph=wind_kph,
            pressure_hpa=pressure,
            visibility_km=visibility_km,
            source="openweathermap",
        )

    def _fetch_wttr_in(self, city: str) -> WeatherData:
        """Queries wttr.in JSON API."""
        # Query query with ascii fallback for URL safety
        query_city = city
        for vn_char, en_char in [(" ", "+"), ("Đ", "D"), ("đ", "d"), ("à", "a"), ("á", "a"), ("ả", "a"), ("ã", "a"), ("ạ", "a"), ("ồ", "o"), ("ố", "o"), ("ộ", "o"), ("ơ", "o"), ("ờ", "o"), ("ớ", "o"), ("ợ", "o"), ("ê", "e"), ("ế", "e"), ("ề", "e"), ("ệ", "e"), ("ư", "u"), ("ứ", "u"), ("ừ", "u"), ("ự", "u"), ("í", "i"), ("ì", "i"), ("ị", "i"), ("ý", "y"), ("ỳ", "y"), ("ỷ", "y")]:
            query_city = query_city.replace(vn_char, en_char)

        url = f"https://wttr.in/{urllib.parse.quote(query_city)}?format=j1"
        headers = {"User-Agent": "curl/7.68.0"}

        data: dict[str, Any] = {}
        if REQUESTS_AVAILABLE and requests is not None:
            resp = requests.get(url, headers=headers, timeout=self.timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
        else:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))

        current = data.get("current_condition", [{}])[0]
        temp_c = float(current.get("temp_C", 26.0))
        feels_like_c = float(current.get("FeelsLikeC", temp_c))
        humidity = int(current.get("humidity", 70))
        wind_kph = float(current.get("windspeedKmph", 10.0))
        uv_index = float(current.get("uvIndex", 3.0)) if current.get("uvIndex") else None
        pressure = int(current.get("pressure", 1012)) if current.get("pressure") else None
        visibility_km = float(current.get("visibility", 10.0)) if current.get("visibility") else None

        desc_list = current.get("lang_vi", current.get("weatherDesc", [{}]))
        raw_desc = desc_list[0].get("value", "Nhiều mây") if desc_list else "Nhiều mây"

        # Translate condition if English
        translated = CONDITION_TRANSLATIONS.get(raw_desc.lower(), raw_desc)

        return WeatherData(
            city=city,
            temp_c=temp_c,
            feels_like_c=feels_like_c,
            condition=translated,
            humidity=humidity,
            wind_kph=wind_kph,
            uv_index=uv_index,
            pressure_hpa=pressure,
            visibility_km=visibility_km,
            source="wttr.in",
        )
