"""
jarvis.web
==========
Web Intelligence, Real-Time Search, Weather, News, and Financial Tracking subsystem.
"""

from jarvis.web.cache import CacheEntry, TTLCache
from jarvis.web.finance import CryptoQuote, FinanceTracker, StockQuote
from jarvis.web.hub import WebIntelligenceHub
from jarvis.web.news import NewsAggregator, NewsArticle
from jarvis.web.search import SearchResultItem, WebSearcher
from jarvis.web.weather import WeatherData, WeatherProvider

__all__ = [
    "TTLCache",
    "CacheEntry",
    "WebSearcher",
    "SearchResultItem",
    "WeatherProvider",
    "WeatherData",
    "NewsAggregator",
    "NewsArticle",
    "FinanceTracker",
    "CryptoQuote",
    "StockQuote",
    "WebIntelligenceHub",
]
