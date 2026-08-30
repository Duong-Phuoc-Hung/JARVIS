"""
Browser Session and Authentication State Persistence Manager.

Manages persistent browser sessions, cookies, local storage, and authentication tokens
across session lifecycles using JSON file storage and SQLite WAL backing stores.
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.browser.driver import BaseBrowserDriver

logger = logging.getLogger(__name__)


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
                            user_agent TEXT NOT NULL DEFAULT '',
                            updated_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime'))
                        );
                        """
                    )
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("Could not initialize browser_sessions table in SQLite: %s", exc)

    def _normalize_domain(self, domain_or_url: str) -> str:
        """Normalize URL or domain string into a clean hostname key."""
        domain = domain_or_url.strip().lower()
        if "://" in domain:
            from urllib.parse import urlparse
            domain = urlparse(domain).netloc
        domain = domain.split(":")[0]  # strip port
        return domain or "default"

    def save_session(
        self,
        domain: str,
        cookies: list[dict[str, Any]],
        local_storage: dict[str, Any] | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """
        Persist session data for a domain to JSON file and SQLite database.
        """
        norm_domain = self._normalize_domain(domain)
        local_storage = local_storage or {}
        user_agent = user_agent or ""
        payload = {
            "domain": norm_domain,
            "cookies": cookies,
            "local_storage": local_storage,
            "user_agent": user_agent,
            "updated_at": datetime.now().isoformat(),
        }

        with self._lock:
            # 1. Save to JSON file
            try:
                json_path = self.storage_dir / f"{norm_domain}.json"
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
            except Exception as exc:
                logger.error("Failed writing session JSON for %s: %s", norm_domain, exc)
                return False

            # 2. Save to SQLite database
            if self.db_path:
                try:
                    conn = sqlite3.connect(self.db_path, timeout=10.0)
                    try:
                        with conn:
                            conn.execute(
                                """
                                INSERT INTO browser_sessions (domain, cookies_json, local_storage_json, user_agent, updated_at)
                                VALUES (?, ?, ?, ?, DATETIME('now', 'localtime'))
                                ON CONFLICT(domain) DO UPDATE SET
                                    cookies_json=excluded.cookies_json,
                                    local_storage_json=excluded.local_storage_json,
                                    user_agent=excluded.user_agent,
                                    updated_at=DATETIME('now', 'localtime')
                                """,
                                (
                                    norm_domain,
                                    json.dumps(cookies, ensure_ascii=False),
                                    json.dumps(local_storage, ensure_ascii=False),
                                    user_agent,
                                ),
                            )
                    finally:
                        conn.close()
                except Exception as exc:
                    logger.debug("SQLite session sync notice for %s: %s", norm_domain, exc)

        logger.info("Saved browser session for %s with %d cookies.", norm_domain, len(cookies))
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
                        return json.load(f)
                except Exception as exc:
                    logger.warning("Error reading session JSON for %s: %s", norm_domain, exc)

            # Fallback to SQLite
            if self.db_path:
                try:
                    conn = sqlite3.connect(self.db_path, timeout=10.0)
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT cookies_json, local_storage_json, user_agent, updated_at FROM browser_sessions WHERE domain = ?",
                            (norm_domain,),
                        )
                        row = cursor.fetchone()
                        if row:
                            return {
                                "domain": norm_domain,
                                "cookies": json.loads(row[0]),
                                "local_storage": json.loads(row[1]),
                                "user_agent": row[2],
                                "updated_at": row[3],
                            }
                    finally:
                        conn.close()
                except Exception as exc:
                    logger.debug("SQLite session read error: %s", exc)

        return None

    def delete_session(self, domain: str) -> bool:
        """Remove stored session data for a domain."""
        norm_domain = self._normalize_domain(domain)
        json_path = self.storage_dir / f"{norm_domain}.json"
        success = True

        with self._lock:
            if json_path.exists():
                try:
                    json_path.unlink()
                except Exception as exc:
                    logger.error("Failed to delete session file for %s: %s", norm_domain, exc)
                    success = False

            if self.db_path:
                try:
                    conn = sqlite3.connect(self.db_path, timeout=10.0)
                    try:
                        with conn:
                            conn.execute("DELETE FROM browser_sessions WHERE domain = ?", (norm_domain,))
                    finally:
                        conn.close()
                except Exception as exc:
                    logger.debug("SQLite delete session error: %s", exc)

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

    def apply_to_driver(self, driver: BaseBrowserDriver, domain: str) -> bool:
        """Inject saved session cookies and state into an active browser driver."""
        session_data = self.load_session(domain)
        if not session_data or "cookies" not in session_data:
            return False

        cookies = session_data["cookies"]
        driver.set_cookies(cookies)

        # Inject local storage if supported via script
        local_storage = session_data.get("local_storage", {})
        if local_storage and driver.is_running():
            for key, val in local_storage.items():
                escaped_k = json.dumps(key)
                escaped_v = json.dumps(val if isinstance(val, str) else json.dumps(val))
                driver.evaluate_script(f"window.localStorage.setItem({escaped_k}, {escaped_v});")

        logger.info("Applied session with %d cookies to driver for %s", len(cookies), domain)
        return True

    def capture_from_driver(self, driver: BaseBrowserDriver, domain: str) -> bool:
        """Extract cookies and local storage from active driver and persist them."""
        if not driver.is_running():
            return False

        cookies = driver.get_cookies()
        local_storage = {}
        try:
            ls_data = driver.evaluate_script("JSON.stringify(window.localStorage);")
            if ls_data and isinstance(ls_data, str):
                local_storage = json.loads(ls_data)
        except Exception as exc:
            logger.debug("Could not extract localStorage: %s", exc)

        return self.save_session(
            domain=domain,
            cookies=cookies,
            local_storage=local_storage,
            user_agent=driver.config.user_agent,
        )

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
                cookies.append(
                    {
                        "domain": parts[0],
                        "path": parts[2],
                        "secure": parts[3].upper() == "TRUE",
                        "expires": int(parts[4]) if parts[4].isdigit() else 0,
                        "name": parts[5],
                        "value": parts[6],
                    }
                )
        return self.save_session(domain=domain, cookies=cookies)
