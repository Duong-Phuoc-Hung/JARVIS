"""
jarvis/web/search.py
====================
Real-Time Web Search Engine with DuckDuckGo and HTML Scraping Fallback.
Results are cached in TTLCache (10-minute TTL) to safeguard against rate limits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import html
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS = None  # type: ignore
    DDGS_AVAILABLE = False

from jarvis.web.cache import TTLCache

logger = logging.getLogger("jarvis.web.search")


@dataclass
class SearchResultItem:
    title: str
    url: str
    snippet: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
        }


class WebSearcher:
    """
    Coordinates multi-engine web searching with automatic fallback:
      1. DuckDuckGo Search API (DDGS)
      2. Direct DuckDuckGo HTML Scraper
      3. SerpAPI REST (if configured)
    All query results are cached for 10 minutes (600s).
    """

    OFFLINE_MESSAGE = "Xin lỗi Ngài, tôi không có kết nối mạng để thực hiện tìm kiếm."
    EMPTY_MESSAGE = "Không tìm thấy kết quả nào phù hợp với yêu cầu của Ngài."

    def __init__(
        self,
        cache: Optional[TTLCache] = None,
        cache_ttl: float = 600.0,
        serpapi_key: Optional[str] = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.cache = cache or TTLCache(default_ttl_seconds=cache_ttl)
        self.cache_ttl = cache_ttl
        self.serpapi_key = serpapi_key
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Executes a web search for the query, checking cache first.
        Returns a list of dicts with keys 'title', 'url', 'snippet'.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        cache_key = self.cache.make_key("web_search", query=clean_query.lower(), limit=max_results)
        cached_res = self.cache.get(cache_key)
        if cached_res is not None:
            logger.debug("Returning cached search results for '%s'", clean_query)
            return cached_res

        results: List[SearchResultItem] = []

        # 1. Tier 1: DDGS Python SDK
        if DDGS_AVAILABLE and DDGS is not None:
            try:
                results = self._search_ddgs(clean_query, max_results)
            except Exception as exc:
                logger.debug("DDGS search failed: %s, falling back to HTML scraper.", exc)
                results = []

        # 2. Tier 2: Direct DuckDuckGo HTML Scraper
        if not results:
            try:
                results = self._search_html(clean_query, max_results)
            except Exception as exc:
                logger.debug("DuckDuckGo HTML scraper failed: %s", exc)
                results = []

        # 3. Tier 3: SerpAPI (if key provided)
        if not results and self.serpapi_key:
            try:
                results = self._search_serpapi(clean_query, max_results)
            except Exception as exc:
                logger.debug("SerpAPI search failed: %s", exc)
                results = []

        dict_results = [r.to_dict() for r in results]
        if dict_results:
            self.cache.set(cache_key, dict_results, ttl=self.cache_ttl)

        return dict_results

    def search_and_summarize(self, query: str, max_results: int = 5) -> str:
        """
        Searches the web and formats a concise Vietnamese spoken summary.
        """
        results = self.search(query, max_results=max_results)
        return self.format_search_summary(query, results)

    def format_search_summary(self, query: str, results: List[Dict[str, str]]) -> str:
        """
        Formats search results into a clean, spoken summary and itemized list.
        """
        if not query or not query.strip():
            return "Vui lòng cung cấp nội dung cần tìm kiếm, thưa Ngài."

        if not results:
            return self.EMPTY_MESSAGE

        top_results = results[:3]
        lines = [f"Theo kết quả tìm kiếm cho '{query}':"]
        for idx, item in enumerate(top_results, start=1):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            # Clean HTML or whitespace
            cleaned_snippet = re.sub(r"\s+", " ", snippet).strip()
            if cleaned_snippet:
                lines.append(f"{idx}. {title}: {cleaned_snippet}")
            else:
                lines.append(f"{idx}. {title}")

        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────────────
    # Search Engine Implementations
    # ──────────────────────────────────────────────────────────────────────────

    def _search_ddgs(self, query: str, max_results: int) -> List[SearchResultItem]:
        """Queries DuckDuckGo via DDGS."""
        items: List[SearchResultItem] = []
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
            for r in raw_results:
                title = r.get("title", "")
                url = r.get("href", r.get("link", ""))
                snippet = r.get("body", r.get("snippet", ""))
                if title:
                    items.append(SearchResultItem(title=title, url=url, snippet=snippet))
        return items

    def _search_html(self, query: str, max_results: int) -> List[SearchResultItem]:
        """Queries DuckDuckGo HTML endpoint with lightweight regex extraction."""
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        html_content = ""
        if REQUESTS_AVAILABLE and requests is not None:
            resp = requests.get(url, headers=headers, timeout=self.timeout_seconds)
            resp.raise_for_status()
            html_content = resp.text
        else:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                html_content = response.read().decode("utf-8", errors="ignore")

        items: List[SearchResultItem] = []
        # Match result blocks: <a class="result__snippet" ...>...</a> and <a class="result__url" ...>
        # Match link & title
        link_matches = re.findall(
            r'<a[^>]+class="result__url"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            html_content,
            re.DOTALL | re.IGNORECASE,
        )
        snippet_matches = re.findall(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html_content,
            re.DOTALL | re.IGNORECASE,
        )

        # Fallback to general link extractor
        if not link_matches:
            raw_links = re.findall(
                r'<h2[^>]*>\s*<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                html_content,
                re.DOTALL | re.IGNORECASE,
            )
            for idx, (raw_url, raw_title) in enumerate(raw_links[:max_results]):
                clean_title = re.sub(r"<[^>]+>", "", html.unescape(raw_title)).strip()
                clean_url = urllib.parse.unquote(raw_url)
                if clean_url.startswith("//duckduckgo.com/l/?uddg="):
                    clean_url = urllib.parse.unquote(clean_url.split("uddg=")[-1].split("&")[0])
                snippet = ""
                if idx < len(snippet_matches):
                    snippet = re.sub(r"<[^>]+>", "", html.unescape(snippet_matches[idx])).strip()
                items.append(SearchResultItem(title=clean_title, url=clean_url, snippet=snippet))
            return items

        for idx, (raw_url, raw_title) in enumerate(link_matches[:max_results]):
            clean_title = re.sub(r"<[^>]+>", "", html.unescape(raw_title)).strip()
            clean_url = urllib.parse.unquote(raw_url).strip()
            snippet = ""
            if idx < len(snippet_matches):
                snippet = re.sub(r"<[^>]+>", "", html.unescape(snippet_matches[idx])).strip()
            if clean_title:
                items.append(SearchResultItem(title=clean_title, url=clean_url, snippet=snippet))

        return items

    def _search_serpapi(self, query: str, max_results: int) -> List[SearchResultItem]:
        """Queries SerpAPI REST endpoint."""
        if not REQUESTS_AVAILABLE or requests is None or not self.serpapi_key:
            return []

        url = "https://serpapi.com/search.json"
        params = {
            "q": query,
            "api_key": self.serpapi_key,
            "num": max_results,
        }
        resp = requests.get(url, params=params, timeout=self.timeout_seconds)
        resp.raise_for_status()
        data = resp.json()

        items: List[SearchResultItem] = []
        for r in data.get("organic_results", [])[:max_results]:
            title = r.get("title", "")
            link = r.get("link", "")
            snippet = r.get("snippet", "")
            if title:
                items.append(SearchResultItem(title=title, url=link, snippet=snippet))
        return items
