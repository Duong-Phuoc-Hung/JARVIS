"""
Browser Session and Authentication State Persistence Manager.

Manages persistent browser sessions, cookies, local storage, and authentication tokens
across session lifecycles using JSON file storage and SQLite WAL backing stores.
"""

import copy
import ipaddress
import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from jarvis.browser.cookie_utils import (
    canonical_cookie_hostname,
    canonicalize_cookie,
    canonicalize_cookie_expiry,
    cookie_domain_attribute_is_allowed,
    cookie_expiry_is_valid,
    cookie_pair_is_safe,
    cookie_prefix_is_valid,
    url_cookie_scope,
)
from jarvis.browser.driver import BaseBrowserDriver
from jarvis.browser.models import BrowserDriverType

logger = logging.getLogger(__name__)

_LOCAL_STORAGE_DRIVER_TYPES = frozenset(
    {
        BrowserDriverType.PLAYWRIGHT,
        BrowserDriverType.CDP,
        BrowserDriverType.MOCK,
    }
)

_APPLY_LOCAL_STORAGE_SCRIPT = """
(payload) => {
  /* jarvis:apply-local-storage */
  if (window.location.origin !== payload.origin) return false;
  const snapshot = [];
  const rollback = () => {
    if (window.location.origin !== payload.origin) return;
    for (let index = snapshot.length - 1; index >= 0; index -= 1) {
      const [key, existed, value] = snapshot[index];
      try {
        if (existed) window.localStorage.setItem(key, value);
        else window.localStorage.removeItem(key);
      } catch (_) {
        // Best-effort rollback; the Python seam still reports failure.
      }
    }
  };
  try {
    for (const [key, value] of payload.entries) {
      const prior = window.localStorage.getItem(key);
      snapshot.push([key, prior !== null, prior]);
      window.localStorage.setItem(key, value);
    }
    if (window.location.origin !== payload.origin) {
      rollback();
      return false;
    }
    return true;
  } catch (_) {
    rollback();
    return false;
  }
}
""".strip()

_CAPTURE_LOCAL_STORAGE_SCRIPT = """
(expectedOrigin) => {
  /* jarvis:capture-local-storage */
  const observedOrigin = window.location.origin;
  if (observedOrigin !== expectedOrigin) {
    return {origin: observedOrigin, entries: null};
  }
  const entries = [];
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (key !== null) entries.push([key, window.localStorage.getItem(key)]);
  }
  return {origin: window.location.origin, entries};
}
""".strip()


class BrowserSessionManager:
    """
    Coordinates browser session persistence across both JSON files and SQLite tables.
    Allows automated authentication state preservation, netscape cookie exports,
    and automatic session injection into active browser drivers.
    """

    def __init__(
        self,
        storage_dir: str = "",  # auto-resolved to AppData/JARVIS/browser_sessions
        db_path: str | None = None,  # auto-resolved to AppData/JARVIS/memory.db
    ) -> None:
        import os as _os

        if not storage_dir:
            _apd = _os.environ.get("LOCALAPPDATA") or _os.environ.get("APPDATA")
            _base = Path(_apd) / "JARVIS" if _apd else Path.home() / ".jarvis"
            storage_dir = str(_base / "browser_sessions")
        if db_path is None:
            _apd2 = _os.environ.get("LOCALAPPDATA") or _os.environ.get("APPDATA")
            _base2 = Path(_apd2) / "JARVIS" if _apd2 else Path.home() / ".jarvis"
            db_path = str(_base2 / "memory.db")
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.RLock()
        self._save_lock = threading.Lock()
        self._init_sqlite_schema()

    def _init_sqlite_schema(self) -> None:
        """Initialize SQLite browser_sessions table if database is configured."""
        if not self.db_path:
            return
        try:
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            try:
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS browser_sessions (
                            domain TEXT PRIMARY KEY,
                            cookies_json TEXT NOT NULL,
                            local_storage_json TEXT NOT NULL DEFAULT '{}',
                            local_storage_origin TEXT NOT NULL DEFAULT '',
                            user_agent TEXT NOT NULL DEFAULT '',
                            updated_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime'))
                        );
                        """
                    )
                    columns = {
                        str(row[1]) for row in conn.execute("PRAGMA table_info(browser_sessions)")
                    }
                    if "local_storage_origin" not in columns:
                        conn.execute(
                            "ALTER TABLE browser_sessions "
                            "ADD COLUMN local_storage_origin TEXT NOT NULL DEFAULT ''"
                        )
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(
                "Could not initialize browser_sessions table in SQLite (%s).",
                type(exc).__name__,
            )

    def _normalize_domain(self, domain_or_url: str) -> str:
        """Normalize a URL/domain into a hostname key that is safe as a filename."""
        raw_domain = domain_or_url.strip().lower()
        if not raw_domain:
            return "default"

        parse_target = raw_domain if "://" in raw_domain else f"//{raw_domain}"
        try:
            hostname = urlsplit(parse_target).hostname or ""
        except ValueError:
            hostname = ""

        hostname = unquote(hostname).strip()
        original_hostname = hostname
        has_leading_dot = hostname.startswith(".")
        has_trailing_dot = hostname.endswith(".")
        bare_hostname = hostname.lstrip(".")
        if has_trailing_dot:
            bare_hostname = bare_hostname[:-1]
        try:
            address = ipaddress.ip_address(bare_hostname)
        except ValueError:
            address = None
        if address is not None and address.version == 6:
            hostname = f"ipv6-{address.compressed.replace(':', '_')}"
            has_leading_dot = False
            has_trailing_dot = False
        else:
            try:
                hostname = canonical_cookie_hostname(bare_hostname)
            except ValueError:
                hostname = original_hostname.lower()
                has_leading_dot = False
                has_trailing_dot = False
            else:
                if has_leading_dot:
                    hostname = f".{hostname}"
                if has_trailing_dot:
                    hostname = f"{hostname}."

        # Keep common hostname spelling stable while removing every path separator,
        # drive delimiter, control character, and other Windows-unsafe character.
        safe_domain = re.sub(r"[^a-z0-9._-]+", "_", hostname)
        safe_domain = re.sub(r"_+", "_", safe_domain).strip("_-")
        safe_domain = re.sub(r"^\.+", ".", safe_domain)
        if not safe_domain or safe_domain == ".":
            return "default"

        reserved_windows_names = {
            "con",
            "prn",
            "aux",
            "nul",
            "clock$",
            *(f"com{number}" for number in range(1, 10)),
            *(f"lpt{number}" for number in range(1, 10)),
        }
        if safe_domain.lstrip(".").split(".", 1)[0] in reserved_windows_names:
            safe_domain = f"domain-{safe_domain}"
        return safe_domain

    @staticmethod
    def _target_hostname(domain_or_url: str) -> str | None:
        """Return the canonical network host, separate from its safe file key."""

        if not isinstance(domain_or_url, str) or not domain_or_url.strip():
            return None
        parse_target = (
            domain_or_url.strip() if "://" in domain_or_url else f"//{domain_or_url.strip()}"
        )
        try:
            parsed = urlsplit(parse_target)
            return canonical_cookie_hostname((parsed.hostname or "").lstrip("."))
        except (AttributeError, TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_origin(url: str) -> tuple[str, str, int] | None:
        """Return an exact web origin with default ports made explicit."""

        try:
            parsed = urlsplit(url.strip())
            scheme = parsed.scheme.lower()
            hostname = canonical_cookie_hostname(parsed.hostname or "")
            if scheme not in {"http", "https"} or not hostname:
                return None
            port = parsed.port
        except (AttributeError, TypeError, ValueError):
            return None
        if port is None:
            port = 443 if scheme == "https" else 80
        return scheme, hostname, port

    @classmethod
    def _canonical_origin(cls, url: str) -> str:
        """Serialize an exact web origin for durable comparison."""

        origin = cls._normalize_origin(url)
        if origin is None:
            return ""
        scheme, hostname, port = origin
        rendered_host = f"[{hostname}]" if ":" in hostname else hostname
        return f"{scheme}://{rendered_host}:{port}"

    @classmethod
    def _browser_origin(cls, url: str) -> str:
        """Render an origin exactly as the browser `location.origin` API does."""

        origin = cls._normalize_origin(url)
        if origin is None:
            return ""
        scheme, hostname, port = origin
        rendered_host = f"[{hostname}]" if ":" in hostname else hostname
        default_port = 443 if scheme == "https" else 80
        suffix = "" if port == default_port else f":{port}"
        return f"{scheme}://{rendered_host}{suffix}"

    @staticmethod
    def supports_local_storage(driver: BaseBrowserDriver) -> bool:
        """Return whether the driver can execute an atomic storage operation."""

        return driver.driver_type in _LOCAL_STORAGE_DRIVER_TYPES

    def save_session(
        self,
        domain: str,
        cookies: list[dict[str, Any]],
        local_storage: dict[str, Any] | None = None,
        user_agent: str | None = None,
        local_storage_origin: str | None = None,
    ) -> bool:
        """
        Persist session data for a domain to JSON file and SQLite database.
        """
        norm_domain = self._normalize_domain(domain)

        with self._save_lock:
            try:
                with self._lock:
                    cookies_snapshot = copy.deepcopy(cookies)
                    local_storage_snapshot = copy.deepcopy(local_storage or {})
                    origin_source = domain if local_storage_origin is None else local_storage_origin
                    local_storage_origin_snapshot = (
                        self._canonical_origin(origin_source) if local_storage_snapshot else ""
                    )
                    user_agent_snapshot = user_agent or ""
                    payload = {
                        "domain": norm_domain,
                        "cookies": cookies_snapshot,
                        "local_storage": local_storage_snapshot,
                        "local_storage_origin": local_storage_origin_snapshot,
                        "user_agent": user_agent_snapshot,
                        "updated_at": datetime.now().isoformat(),
                    }
                    validated_payload = self._validate_session_payload(
                        payload,
                        norm_domain,
                    )
                    if validated_payload is None:
                        logger.error(
                            "Refusing to persist an invalid browser session for %s.",
                            norm_domain,
                        )
                        return False
                    payload = validated_payload
            except Exception as exc:
                logger.error(
                    "Failed snapshotting browser session for %s (%s).",
                    norm_domain,
                    type(exc).__name__,
                )
                return False

            # 1. Save to JSON file
            json_path = self.storage_dir / f"{norm_domain}.json"
            tmp_path = json_path.with_name(
                f"{json_path.name}.tmp.{threading.get_ident()}.{time.time_ns()}"
            )
            try:
                json_text = json.dumps(payload, indent=2, ensure_ascii=False)
                tmp_path.write_text(json_text, encoding="utf-8")
                for attempt in range(1, 6):
                    try:
                        tmp_path.replace(json_path)
                        break
                    except OSError as exc:
                        is_windows_access_denied = getattr(exc, "winerror", None) == 5
                        if (
                            not isinstance(exc, PermissionError) and not is_windows_access_denied
                        ) or attempt == 5:
                            raise
                        time.sleep(0.02 * attempt)
            except Exception as exc:
                logger.error(
                    "Failed writing session JSON for %s (%s).",
                    norm_domain,
                    type(exc).__name__,
                )
                return False
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    logger.debug("Could not clean a browser session temp file.")

            # 2. Save to SQLite database
            if self.db_path:
                try:
                    conn = sqlite3.connect(self.db_path, timeout=10.0)
                    try:
                        with conn:
                            conn.execute(
                                """
                                INSERT INTO browser_sessions (
                                    domain,
                                    cookies_json,
                                    local_storage_json,
                                    local_storage_origin,
                                    user_agent,
                                    updated_at
                                )
                                VALUES (?, ?, ?, ?, ?, DATETIME('now', 'localtime'))
                                ON CONFLICT(domain) DO UPDATE SET
                                    cookies_json=excluded.cookies_json,
                                    local_storage_json=excluded.local_storage_json,
                                    local_storage_origin=excluded.local_storage_origin,
                                    user_agent=excluded.user_agent,
                                    updated_at=DATETIME('now', 'localtime')
                                """,
                                (
                                    norm_domain,
                                    json.dumps(cookies_snapshot, ensure_ascii=False),
                                    json.dumps(local_storage_snapshot, ensure_ascii=False),
                                    local_storage_origin_snapshot,
                                    user_agent_snapshot,
                                ),
                            )
                    finally:
                        conn.close()
                except Exception as exc:
                    logger.error(
                        "Failed writing session SQLite row for %s (%s).",
                        norm_domain,
                        type(exc).__name__,
                    )
                    return False

        logger.info(
            "Saved browser session for %s with %d cookies.",
            norm_domain,
            len(cookies_snapshot),
        )
        return True

    def load_session(self, domain: str) -> dict[str, Any] | None:
        """
        Load stored session payload for a domain from JSON file or SQLite fallback.
        """
        norm_domain = self._normalize_domain(domain)
        json_path = self.storage_dir / f"{norm_domain}.json"

        with self._lock:
            # Try JSON file first
            if json_path.exists():
                try:
                    with open(json_path, encoding="utf-8") as f:
                        payload = self._validate_session_payload(
                            json.load(f),
                            norm_domain,
                        )
                    if payload is not None:
                        return payload
                    logger.warning(
                        "Browser session JSON has an invalid schema for %s.",
                        norm_domain,
                    )
                except Exception as exc:
                    logger.warning(
                        "Error reading session JSON for %s (%s).",
                        norm_domain,
                        type(exc).__name__,
                    )

            # Fallback to SQLite
            if self.db_path:
                try:
                    conn = sqlite3.connect(self.db_path, timeout=10.0)
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT cookies_json, local_storage_json, "
                            "local_storage_origin, user_agent, updated_at "
                            "FROM browser_sessions WHERE domain = ?",
                            (norm_domain,),
                        )
                        row = cursor.fetchone()
                        if row:
                            return self._validate_session_payload(
                                {
                                    "domain": norm_domain,
                                    "cookies": json.loads(row[0]),
                                    "local_storage": json.loads(row[1]),
                                    "local_storage_origin": row[2],
                                    "user_agent": row[3],
                                    "updated_at": row[4],
                                },
                                norm_domain,
                            )
                    finally:
                        conn.close()
                except Exception as exc:
                    logger.debug(
                        "SQLite session read failed (%s).",
                        type(exc).__name__,
                    )

        return None

    @staticmethod
    def _validate_session_payload(
        payload: Any,
        norm_domain: str,
    ) -> dict[str, Any] | None:
        """Validate persisted types before they reach browser/session seams."""

        if not isinstance(payload, dict):
            return None
        cookies = payload.get("cookies")
        local_storage = payload.get("local_storage", {})
        local_storage_origin = payload.get("local_storage_origin", "")
        user_agent = payload.get("user_agent", "")
        if not isinstance(cookies, list):
            return None
        validated_cookies: list[dict[str, Any]] = []
        for cookie in cookies:
            if not isinstance(cookie, dict):
                return None
            name = cookie.get("name")
            value = cookie.get("value")
            if not cookie_pair_is_safe(name, value):
                return None
            if any(
                flag in cookie and not isinstance(cookie.get(flag), bool)
                for flag in ("secure", "httpOnly", "_crHasCrossSiteAncestor")
            ):
                return None
            has_scope = any(key in cookie for key in ("url", "domain", "path"))
            if has_scope:
                candidate_input = dict(cookie)
                if (
                    not candidate_input.get("url")
                    and candidate_input.get("domain") is not None
                    and candidate_input.get("path") is None
                ):
                    candidate_input["path"] = "/"
                try:
                    candidate = canonicalize_cookie(candidate_input)
                except ValueError:
                    return None
                if set(candidate) - {
                    "name",
                    "value",
                    "domain",
                    "path",
                    "expires",
                    "httpOnly",
                    "secure",
                    "sameSite",
                    "partitionKey",
                    "_crHasCrossSiteAncestor",
                }:
                    return None
            else:
                # Preserve legacy name/value-only records. They remain inert
                # until an explicit scope is supplied at the driver seam.
                candidate = dict(cookie)
            if "expires" in candidate:
                try:
                    candidate["expires"] = canonicalize_cookie_expiry(candidate["expires"])
                except ValueError:
                    return None
            same_site = candidate.get("sameSite")
            if same_site is not None:
                same_site = {
                    "strict": "Strict",
                    "lax": "Lax",
                    "none": "None",
                }.get(str(same_site).strip().lower())
                if same_site is None:
                    return None
                candidate["sameSite"] = same_site
            if (
                same_site is not None
                and same_site == "None"
                and candidate.get("secure") is not True
            ):
                return None
            domain = candidate.get("domain")
            path = candidate.get("path")
            if not cookie_prefix_is_valid(
                str(name),
                secure=candidate.get("secure") is True,
                http_only=candidate.get("httpOnly") is True,
                host_only=not str(domain or "").startswith("."),
                path=str(path or "/"),
                scheme="https" if candidate.get("secure") is True else "http",
            ):
                return None
            if "partitionKey" in candidate and (
                not isinstance(candidate.get("partitionKey"), str)
                or not candidate.get("partitionKey")
            ):
                return None
            if candidate.get("partitionKey") is not None and candidate.get("secure") is not True:
                return None
            if "_crHasCrossSiteAncestor" in candidate and candidate.get("partitionKey") is None:
                return None
            validated_cookies.append(candidate)
        if not isinstance(local_storage, dict):
            return None
        if not isinstance(local_storage_origin, str) or not isinstance(user_agent, str):
            return None
        validated = dict(payload)
        validated.update(
            {
                "domain": norm_domain,
                "cookies": validated_cookies,
                "local_storage": local_storage,
                "local_storage_origin": local_storage_origin,
                "user_agent": user_agent,
            }
        )
        return validated

    def delete_session(self, domain: str) -> bool:
        """Remove stored session data for a domain."""
        norm_domain = self._normalize_domain(domain)
        json_path = self.storage_dir / f"{norm_domain}.json"
        success = True

        with self._save_lock:
            with self._lock:
                if json_path.exists():
                    try:
                        json_path.unlink()
                    except Exception:
                        logger.error("Failed to delete browser session file.")
                        success = False

                if self.db_path:
                    try:
                        conn = sqlite3.connect(self.db_path, timeout=10.0)
                        try:
                            with conn:
                                conn.execute(
                                    "DELETE FROM browser_sessions WHERE domain = ?",
                                    (norm_domain,),
                                )
                        finally:
                            conn.close()
                    except Exception:
                        logger.error("SQLite browser session deletion failed.")
                        success = False

        return success

    def list_sessions(self) -> list[str]:
        """List all saved domain session keys."""
        domains = set()
        with self._lock:
            for file in self.storage_dir.glob("*.json"):
                domains.add(file.stem)

            if self.db_path and os.path.exists(self.db_path):
                try:
                    with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT domain FROM browser_sessions")
                        for (d,) in cursor.fetchall():
                            domains.add(d)
                except Exception:
                    pass

        return sorted(list(domains))

    def apply_to_driver(
        self,
        driver: BaseBrowserDriver,
        domain: str,
        *,
        apply_cookies: bool = True,
        apply_local_storage: bool = True,
    ) -> bool:
        """Inject saved session cookies and state into an active browser driver."""
        if not driver.is_running():
            return False
        session_data = self.load_session(domain)
        if not session_data or "cookies" not in session_data:
            return False

        cookies = session_data["cookies"]
        target_cookie_domain = self._target_hostname(domain)
        if target_cookie_domain is None:
            return False
        validated_by_identity: dict[
            tuple[str, str, str, str | None, bool | None], dict[str, Any]
        ] = {}
        for cookie in cookies:
            if not isinstance(cookie, dict):
                return False
            try:
                candidate = canonicalize_cookie(cookie)
            except ValueError:
                return False
            name = candidate.get("name")
            value = candidate.get("value")
            normalized_domain = str(candidate.get("domain") or "").strip().lower()
            if not cookie_pair_is_safe(name, value) or not normalized_domain:
                return False
            try:
                cookie_domain = canonical_cookie_hostname(normalized_domain.lstrip(".").rstrip("."))
            except ValueError:
                return False
            is_domain_cookie = normalized_domain.startswith(".")
            domain_matches_target = (
                cookie_domain_attribute_is_allowed(
                    target_cookie_domain,
                    cookie_domain,
                )
                if is_domain_cookie
                else target_cookie_domain == cookie_domain
            )
            if not domain_matches_target:
                return False
            candidate["domain"] = normalized_domain
            same_site = candidate.get("sameSite")
            if same_site is not None:
                canonical_same_site = {
                    "strict": "Strict",
                    "lax": "Lax",
                    "none": "None",
                }.get(str(same_site).strip().lower())
                if canonical_same_site is None:
                    return False
                candidate["sameSite"] = canonical_same_site
                if canonical_same_site == "None" and candidate.get("secure") is not True:
                    return False
            target_scheme = (urlsplit(domain).scheme or "https").lower()
            if not cookie_prefix_is_valid(
                str(candidate.get("name")),
                secure=candidate.get("secure") is True,
                http_only=candidate.get("httpOnly") is True,
                host_only=not is_domain_cookie,
                path=str(candidate.get("path") or "/"),
                scheme=target_scheme,
            ):
                return False
            identity = (
                str(candidate["name"]),
                str(candidate["domain"]),
                str(candidate["path"]),
                (
                    str(candidate["partitionKey"])
                    if candidate.get("partitionKey") is not None
                    else None
                ),
                (
                    bool(candidate["_crHasCrossSiteAncestor"])
                    if candidate.get("partitionKey") is not None
                    and "_crHasCrossSiteAncestor" in candidate
                    else None
                ),
            )
            validated_by_identity[identity] = candidate
        validated_cookies = list(validated_by_identity.values())
        local_storage = session_data.get("local_storage", {})
        if apply_local_storage and local_storage and not self.supports_local_storage(driver):
            return False
        if apply_cookies:
            try:
                driver.set_cookies(validated_cookies)
            except Exception:
                return False
            if driver.last_error_status is not None:
                return False
            observed_cookies = driver.get_cookies()
            if driver.last_error_status is not None:
                return False
            for expected in validated_cookies:
                same_identity = [
                    observed
                    for observed in observed_cookies
                    if str(observed.get("name") or "") == expected["name"]
                    and str(observed.get("domain") or "").strip().lower().rstrip(".")
                    == str(expected.get("domain") or "").strip().lower().rstrip(".")
                    and str(observed.get("path") or "/") == expected["path"]
                    and observed.get("partitionKey") == expected.get("partitionKey")
                    and (
                        "_crHasCrossSiteAncestor" not in expected
                        or observed.get("_crHasCrossSiteAncestor")
                        == expected.get("_crHasCrossSiteAncestor")
                    )
                ]
                expires = expected.get("expires")
                expired = expires is not None and (
                    float(expires) == 0 or (float(expires) > 0 and float(expires) <= time.time())
                )
                if expired:
                    if same_identity:
                        return False
                    continue
                matching = [
                    observed
                    for observed in same_identity
                    if str(observed.get("value") or "") == expected["value"]
                ]
                if not matching:
                    return False
                observed = matching[0]
                for flag in ("secure", "httpOnly"):
                    if flag in expected and bool(observed.get(flag)) != bool(expected[flag]):
                        return False
                if "sameSite" in expected and observed.get("sameSite") != expected["sameSite"]:
                    return False
                if "expires" in expected:
                    observed_expiry = observed.get("expires")
                    if (
                        not cookie_expiry_is_valid(observed_expiry)
                        or abs(float(observed_expiry) - float(expected["expires"])) > 2.0
                    ):
                        return False

        # Inject local storage if supported via script
        if (
            apply_local_storage
            and local_storage
            and driver.is_running()
            and self.supports_local_storage(driver)
        ):
            active_origin = self._normalize_origin(driver.get_current_url())
            target_origin = self._normalize_origin(domain)
            source_origin = self._normalize_origin(
                str(session_data.get("local_storage_origin") or "")
            )
            if (
                source_origin is None
                or target_origin is None
                or source_origin != target_origin
                or active_origin != target_origin
            ):
                return False
            expected_origin = self._browser_origin(domain)
            if not expected_origin:
                return False
            entries = [
                [str(key), value if isinstance(value, str) else json.dumps(value)]
                for key, value in local_storage.items()
            ]
            applied = driver.evaluate_script(
                _APPLY_LOCAL_STORAGE_SCRIPT,
                {"origin": expected_origin, "entries": entries},
            )
            if driver.last_error_status is not None or applied is not True:
                return False

        logger.info(
            "Applied browser session state for %s",
            self._normalize_domain(domain),
        )
        return True

    def capture_from_driver(self, driver: BaseBrowserDriver, domain: str) -> bool:
        """Extract cookies and local storage from active driver and persist them."""
        if not driver.is_running():
            return False

        try:
            cookies = driver.get_cookies()
        except Exception:
            logger.debug("Could not read browser cookies.")
            return False
        if driver.last_error_status is not None:
            return False

        target_domain = self._target_hostname(domain)
        if target_domain is None:
            return False
        cookies = [
            dict(cookie)
            for cookie in cookies
            if self._cookie_belongs_to_domain(cookie, target_domain)
        ]
        existing = self.load_session(domain)
        current_url = driver.get_current_url() or domain
        current_origin = self._normalize_origin(current_url)
        target_origin = self._normalize_origin(domain)
        if self.supports_local_storage(driver) and (
            current_origin is None or target_origin is None or current_origin != target_origin
        ):
            return False
        existing_storage = (
            existing.get("local_storage")
            if existing and isinstance(existing.get("local_storage"), dict)
            else {}
        )
        existing_origin = self._normalize_origin(
            str(existing.get("local_storage_origin") or "") if existing else ""
        )
        local_storage: dict[str, Any] = {}
        local_storage_origin: str | None = None
        capture_complete = True
        if self.supports_local_storage(driver):
            if (
                existing_storage
                and existing_origin is not None
                and existing_origin != current_origin
            ):
                # The hostname-keyed session format has one localStorage slot. Never
                # overwrite evidenced state from a different exact origin.
                local_storage = copy.deepcopy(existing_storage)
                local_storage_origin = str(existing.get("local_storage_origin") or "")
                capture_complete = False
            else:
                try:
                    expected_origin = self._browser_origin(current_url)
                    if not expected_origin:
                        return False
                    ls_data = driver.evaluate_script(
                        _CAPTURE_LOCAL_STORAGE_SCRIPT,
                        expected_origin,
                    )
                    if driver.last_error_status is not None:
                        return False
                    if not isinstance(ls_data, dict):
                        return False
                    if ls_data.get("origin") != expected_origin:
                        return False
                    raw_entries = ls_data.get("entries")
                    if not isinstance(raw_entries, list):
                        return False
                    parsed_storage: dict[str, Any] = {}
                    for entry in raw_entries:
                        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                            return False
                        key, value = entry
                        if not isinstance(key, str) or not isinstance(value, str):
                            return False
                        parsed_storage[key] = value
                    local_storage = parsed_storage
                    local_storage_origin = current_url
                except Exception:
                    logger.debug("Could not extract browser localStorage.")
                    return False
        else:
            # A read-only HTTP driver can still persist its observed cookie jar,
            # but it must not call an unsupported JS capability or erase state
            # previously captured by a real browser.
            if existing_storage:
                local_storage = copy.deepcopy(existing_storage)
                local_storage_origin = str(existing.get("local_storage_origin") or "")
                capture_complete = False

        saved = self.save_session(
            domain=domain,
            cookies=cookies,
            local_storage=local_storage,
            user_agent=driver.config.user_agent,
            local_storage_origin=local_storage_origin,
        )
        return saved and capture_complete

    @staticmethod
    def _cookie_belongs_to_domain(cookie: dict[str, Any], target_domain: str) -> bool:
        """Return true only for cookies scoped to the captured host or a parent domain."""
        if cookie.get("url") and not cookie.get("domain"):
            try:
                _scheme, cookie_domain, _path = url_cookie_scope(str(cookie["url"]))
            except ValueError:
                return False
            try:
                target = canonical_cookie_hostname(target_domain.lstrip("."))
            except ValueError:
                return False
            return cookie_domain == target
        raw_domain = str(cookie.get("domain") or "").strip().lower()
        is_domain_cookie = raw_domain.startswith(".")
        try:
            cookie_domain = canonical_cookie_hostname(raw_domain.lstrip("."))
            target = canonical_cookie_hostname(target_domain.strip().lstrip("."))
        except ValueError:
            return False
        if is_domain_cookie:
            return cookie_domain_attribute_is_allowed(target, cookie_domain)
        return target == cookie_domain

    def export_cookies_netscape(
        self,
        domain: str,
        output_path: str | Path | None = None,
    ) -> str | bool:
        """Export stored domain cookies in Netscape format (compatible with curl / wget)."""
        session_data = self.load_session(domain)
        if not session_data:
            return False if output_path else ""

        lines = [
            "# Netscape HTTP Cookie File",
            "# http://curl.haxx.se/rfc/cookie_spec.html",
            "# This is a generated file!  Do not edit.",
            "",
        ]
        for c in session_data.get("cookies", []):
            d = c.get("domain", domain)
            include_sub = "TRUE" if d.startswith(".") else "FALSE"
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure", False) else "FALSE"
            expires = str(int(c.get("expires", 0) or 0))
            name = c.get("name", "")
            value = c.get("value", "")
            lines.append(f"{d}\t{include_sub}\t{path}\t{secure}\t{expires}\t{name}\t{value}")

        content = "\n".join(lines) + "\n"
        if output_path:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(content, encoding="utf-8")
            return True
        return content

    # Alias for method name compatibility
    export_netscape_cookies = export_cookies_netscape

    def import_cookies_netscape(self, domain: str, netscape_text: str) -> bool:
        """Parse Netscape cookie format string and store into domain session."""
        cookies: list[dict[str, Any]] = []
        for line in netscape_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                try:
                    expires = int(parts[4])
                except ValueError:
                    return False
                cookie: dict[str, Any] = {
                    "domain": parts[0],
                    "path": parts[2],
                    "secure": parts[3].upper() == "TRUE",
                    "name": parts[5],
                    "value": parts[6],
                }
                # Netscape uses zero specifically to encode a session cookie.
                if expires != 0:
                    cookie["expires"] = expires
                cookies.append(cookie)
        return self.save_session(domain=domain, cookies=cookies)
