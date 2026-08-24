"""
jarvis/web/finance.py
=====================
Financial Market Intelligence Tracker for JARVIS.
Provides real-time Crypto tracking (BTC, ETH in USD and VND),
Currency exchange rates (USD/VND, EUR/VND), and Stock quotes (VN-Index, AAPL).
Integrates with TTLCache for 10-minute caching and graceful offline fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

from jarvis.web.cache import TTLCache

logger = logging.getLogger("jarvis.web.finance")


@dataclass
class CryptoQuote:
    symbol: str
    name: str
    price_usd: float
    price_vnd: float
    change_24h_pct: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "price_usd": self.price_usd,
            "price_vnd": self.price_vnd,
            "change_24h_pct": self.change_24h_pct,
            "updated_at": self.updated_at,
        }


@dataclass
class StockQuote:
    ticker: str
    price: float
    currency: str = "VND"
    change_pct: float = 0.0
    company_name: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "currency": self.currency,
            "change_pct": self.change_pct,
            "company_name": self.company_name,
            "updated_at": self.updated_at,
        }


class FinanceTracker:
    """
    Coordinates real-time financial telemetry across cryptocurrency,
    foreign exchange rates, and public equity indices.
    """

    DEFAULT_USD_VND_RATE = 25450.0

    def __init__(
        self,
        cache: Optional[TTLCache] = None,
        cache_ttl: float = 600.0,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.cache = cache or TTLCache(default_ttl_seconds=cache_ttl)
        self.cache_ttl = cache_ttl
        self.timeout_seconds = timeout_seconds

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Foreign Exchange (Forex)
    # ──────────────────────────────────────────────────────────────────────────

    def get_exchange_rate(self, base: str = "USD", target: str = "VND") -> float:
        """
        Retrieves foreign currency exchange rate (e.g. USD -> VND).
        Checks TTLCache first.
        """
        base_clean = base.upper().strip()
        target_clean = target.upper().strip()
        cache_key = self.cache.make_key("exchange_rate", base=base_clean, target=target_clean)

        cached = self.cache.get(cache_key)
        if cached is not None:
            return float(cached)

        rate = self._fetch_exchange_rate(base_clean, target_clean)
        self.cache.set(cache_key, rate, ttl=self.cache_ttl)
        return rate

    def _fetch_exchange_rate(self, base: str, target: str) -> float:
        """Queries open exchange rate API or falls back to baseline rate."""
        url = f"https://open.er-api.com/v6/latest/{base}"
        try:
            if REQUESTS_AVAILABLE and requests is not None:
                resp = requests.get(url, timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json()
            else:
                req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/2.0"})
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))

            rates = data.get("rates", {})
            if target in rates:
                return float(rates[target])
        except Exception as exc:
            logger.debug("Failed to fetch live exchange rate %s/%s: %s", base, target, exc)

        # Baseline fallback
        if base == "USD" and target == "VND":
            return self.DEFAULT_USD_VND_RATE
        elif base == "EUR" and target == "VND":
            return 27800.0
        return 1.0

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Cryptocurrency Rates
    # ──────────────────────────────────────────────────────────────────────────

    def get_crypto_price(self, symbol: str = "BTC", vs_currency: str = "USD") -> Dict[str, Any]:
        """
        Retrieves crypto price and 24h change for a given symbol (BTC, ETH, SOL).
        """
        clean_sym = symbol.upper().strip()
        clean_vs = vs_currency.upper().strip()
        cache_key = self.cache.make_key("crypto_price", symbol=clean_sym, vs=clean_vs)

        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        usd_vnd_rate = self.get_exchange_rate("USD", "VND")
        quote = self._fetch_crypto_quote(clean_sym, usd_vnd_rate)

        price = quote.price_usd if clean_vs == "USD" else quote.price_vnd
        result = {
            "symbol": quote.symbol,
            "name": quote.name,
            "price": price,
            "currency": clean_vs,
            "price_usd": quote.price_usd,
            "price_vnd": quote.price_vnd,
            "change_24h_pct": quote.change_24h_pct,
        }

        self.cache.set(cache_key, result, ttl=self.cache_ttl)
        return result

    def get_crypto_quotes(self, symbols: Optional[List[str]] = None) -> List[CryptoQuote]:
        """
        Retrieves quotes for multiple cryptocurrencies (default: BTC, ETH).
        """
        syms = symbols or ["BTC", "ETH"]
        usd_vnd = self.get_exchange_rate("USD", "VND")
        quotes: List[CryptoQuote] = []
        for s in syms:
            quotes.append(self._fetch_crypto_quote(s.upper(), usd_vnd))
        return quotes

    def _fetch_crypto_quote(self, symbol: str, usd_vnd_rate: float) -> CryptoQuote:
        """Fetches crypto ticker from Binance public API or CoinGecko fallback."""
        name_map = {
            "BTC": "Bitcoin",
            "ETH": "Ethereum",
            "SOL": "Solana",
            "BNB": "Binance Coin",
        }
        coin_name = name_map.get(symbol, symbol)

        # 1. Try Binance API
        try:
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}USDT"
            if REQUESTS_AVAILABLE and requests is not None:
                resp = requests.get(url, timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json()
            else:
                req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/2.0"})
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))

            price_usd = float(data.get("lastPrice", 0.0))
            change_pct = float(data.get("priceChangePercent", 0.0))
            if price_usd > 0:
                return CryptoQuote(
                    symbol=symbol,
                    name=coin_name,
                    price_usd=price_usd,
                    price_vnd=round(price_usd * usd_vnd_rate, 0),
                    change_24h_pct=change_pct,
                )
        except Exception as exc:
            logger.debug("Binance ticker failed for %s: %s", symbol, exc)

        # 2. Try CoinGecko API fallback
        cg_id_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
        if symbol in cg_id_map:
            try:
                cg_id = cg_id_map[symbol]
                cg_url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd,vnd&include_24hr_change=true"
                if REQUESTS_AVAILABLE and requests is not None:
                    resp = requests.get(cg_url, timeout=self.timeout_seconds)
                    resp.raise_for_status()
                    cg_data = resp.json()
                else:
                    req = urllib.request.Request(cg_url, headers={"User-Agent": "JARVIS/2.0"})
                    with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                        cg_data = json.loads(response.read().decode("utf-8"))

                coin_info = cg_data.get(cg_id, {})
                price_usd = float(coin_info.get("usd", 0.0))
                price_vnd = float(coin_info.get("vnd", price_usd * usd_vnd_rate))
                change_pct = float(coin_info.get("usd_24h_change", 0.0))

                if price_usd > 0:
                    return CryptoQuote(
                        symbol=symbol,
                        name=coin_name,
                        price_usd=price_usd,
                        price_vnd=price_vnd,
                        change_24h_pct=round(change_pct, 2),
                    )
            except Exception as exc2:
                logger.debug("CoinGecko API failed for %s: %s", symbol, exc2)

        # 3. Offline Baseline Defaults
        defaults = {
            "BTC": 64500.0,
            "ETH": 3450.0,
            "SOL": 145.0,
        }
        price_usd = defaults.get(symbol, 100.0)
        return CryptoQuote(
            symbol=symbol,
            name=coin_name,
            price_usd=price_usd,
            price_vnd=price_usd * usd_vnd_rate,
            change_24h_pct=0.5,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Stock Market Quotes
    # ──────────────────────────────────────────────────────────────────────────

    def get_stock_quote(self, ticker: str = "VNINDEX") -> StockQuote:
        """
        Retrieves equity ticker price and change percentage.
        """
        clean_ticker = ticker.upper().strip()
        cache_key = self.cache.make_key("stock_quote", ticker=clean_ticker)

        cached = self.cache.get(cache_key)
        if cached is not None:
            if isinstance(cached, dict):
                return StockQuote(**cached)
            return cached

        quote = self._fetch_stock_quote(clean_ticker)
        self.cache.set(cache_key, quote.to_dict(), ttl=self.cache_ttl)
        return quote

    def _fetch_stock_quote(self, ticker: str) -> StockQuote:
        """Queries stock ticker data from public endpoints or provides baseline."""
        # 1. Yahoo Finance chart API for US stocks / VNINDEX
        symbol_query = "^VNINDEX" if ticker == "VNINDEX" else ticker
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol_query}?interval=1d"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            if REQUESTS_AVAILABLE and requests is not None:
                resp = requests.get(url, headers=headers, timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json()
            else:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))

            meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
            price = float(meta.get("regularMarketPrice", 0.0))
            prev_close = float(meta.get("previousClose", price))
            currency = meta.get("currency", "USD")
            change_pct = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0

            if price > 0:
                return StockQuote(
                    ticker=ticker,
                    price=price,
                    currency=currency,
                    change_pct=change_pct,
                    company_name=meta.get("shortName", ticker),
                )
        except Exception as exc:
            logger.debug("Yahoo finance chart failed for %s: %s", ticker, exc)

        # Baseline Defaults
        defaults = {
            "VNINDEX": (1250.5, "VND", 0.35, "VN-Index"),
            "AAPL": (225.5, "USD", -0.15, "Apple Inc."),
            "TSLA": (210.0, "USD", 1.20, "Tesla Inc."),
        }
        def_price, def_curr, def_chg, def_name = defaults.get(ticker, (100.0, "USD", 0.0, ticker))
        return StockQuote(
            ticker=ticker,
            price=def_price,
            currency=def_curr,
            change_pct=def_chg,
            company_name=def_name,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Summary Formatters
    # ──────────────────────────────────────────────────────────────────────────

    def get_crypto_summary(self) -> str:
        """Creates a vocalizable summary of BTC and ETH prices."""
        btc = self.get_crypto_price("BTC", "USD")
        eth = self.get_crypto_price("ETH", "USD")

        btc_p = f"{btc['price']:,.0f}"
        btc_chg = f"+{btc['change_24h_pct']:.1f}%" if btc['change_24h_pct'] >= 0 else f"{btc['change_24h_pct']:.1f}%"
        eth_p = f"{eth['price']:,.0f}"
        eth_chg = f"+{eth['change_24h_pct']:.1f}%" if eth['change_24h_pct'] >= 0 else f"{eth['change_24h_pct']:.1f}%"

        return f"Bitcoin hiện ở mức ${btc_p} ({btc_chg}), Ethereum đạt ${eth_p} ({eth_chg})."

    def get_rates_summary(self) -> str:
        """Creates an exchange rate briefing sentence."""
        usd_vnd = self.get_exchange_rate("USD", "VND")
        return f"Tỷ giá USD/VND hiện ở mức {usd_vnd:,.0f} VND."
