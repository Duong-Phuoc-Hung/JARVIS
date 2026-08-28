"""
jarvis/web/cache.py
===================
Thread-Safe In-Memory TTL Caching Subsystem.
Default 600.0s (10-minute) TTL to strictly safeguard against third-party API rate limits.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

logger = logging.getLogger("jarvis.web.cache")

T = TypeVar("T")


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    created_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


class TTLCache:
    """
    Thread-safe in-memory cache with configurable TTL (default: 600.0s = 10 minutes).
    Supports deterministic key generation, atomic fetch-or-compute, and expired entry eviction.
    """

    def __init__(self, default_ttl_seconds: float = 600.0, max_size: int = 1000) -> None:
        self.default_ttl = float(default_ttl_seconds)
        self.max_size = max_size
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves cached value for key if present and unexpired.
        Returns `default` if key is missing or expired.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return default
            if entry.is_expired:
                del self._cache[key]
                return default
            return entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """
        Stores value in cache with specified TTL in seconds (or default_ttl).
        """
        effective_ttl = float(ttl) if ttl is not None else self.default_ttl
        now = time.time()
        entry = CacheEntry(
            value=value,
            expires_at=now + effective_ttl,
            created_at=now,
        )
        with self._lock:
            # Enforce max size limit if exceeded
            if len(self._cache) >= self.max_size and key not in self._cache:
                self.cleanup_expired()
                if len(self._cache) >= self.max_size:
                    # Evict oldest entry
                    oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
                    del self._cache[oldest_key]

            self._cache[key] = entry

    def has(self, key: str) -> bool:
        """Checks if key is present in cache and unexpired."""
        return self.get(key) is not None

    def delete(self, key: str) -> bool:
        """Removes key from cache. Returns True if deleted, False if not found."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clears all cached entries."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """Purges all expired entries from cache. Returns count of purged items."""
        with self._lock:
            now = time.time()
            expired_keys = [k for k, entry in self._cache.items() if now >= entry.expires_at]
            for k in expired_keys:
                del self._cache[k]
            return len(expired_keys)

    def size(self) -> int:
        """Returns the number of active, unexpired cached items."""
        with self._lock:
            self.cleanup_expired()
            return len(self._cache)

    def keys(self) -> list[str]:
        """Returns list of all active, unexpired cache keys."""
        with self._lock:
            self.cleanup_expired()
            return list(self._cache.keys())

    def items(self) -> dict[str, Any]:
        """Returns copy of all active, unexpired key-value pairs."""
        with self._lock:
            self.cleanup_expired()
            return {k: v.value for k, v in self._cache.items()}

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: float | None = None,
    ) -> T:
        """
        Thread-safe fetch-or-compute: retrieves cached item or executes factory function
        to compute and cache the result.
        """
        with self._lock:
            val = self.get(key)
            if val is not None:
                return val

            computed_val = factory()
            self.set(key, computed_val, ttl=ttl)
            return computed_val

    @staticmethod
    def make_key(prefix: str, *args: Any, **kwargs: Any) -> str:
        """
        Generates a deterministic cache key based on a prefix and arbitrary arguments.
        """
        serialized = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}:{digest}"
