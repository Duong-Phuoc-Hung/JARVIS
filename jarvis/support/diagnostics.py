"""
jarvis/support/diagnostics.py
================================
D-15: Support Diagnostics + Log Redaction

Provides:
- Structured environment summary (Python, OS, JARVIS version, config)
- Redaction of tokens, passwords, API keys, cookies from logs/config
- Crash marker detection
- One-command support bundle zip export
- Fail-Closed: credential values never appear in bundle plaintext

Per AGENTS.md Anti-Fabrication: only real data reported, never mocked.
Per AGENTS.md: secret scan must find no credential plaintext in bundle.
"""
from __future__ import annotations

import io
import json
import logging
import os
import platform
import re
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.support.diagnostics")

# ── Redaction patterns ─────────────────────────────────────────────────────
_SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+"), r"\1=<REDACTED>"),
    (re.compile(r"(?i)(bot[_-]?token|token)\s*[=:]\s*\S+"), r"\1=<REDACTED>"),
    (re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+"), r"\1=<REDACTED>"),
    (re.compile(r"(?i)(secret|client[_-]?secret)\s*[=:]\s*\S+"), r"\1=<REDACTED>"),
    (re.compile(r"(?i)(cookie|session[_-]?id)\s*[=:]\s*\S+"), r"\1=<REDACTED>"),
    (re.compile(r"(?i)(access[_-]?token|refresh[_-]?token)\s*[=:]\s*\S+"), r"\1=<REDACTED>"),
    # Bare values that look like real keys (32+ hex chars or long base64)
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"), "<REDACTED_LONG_TOKEN>"),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "<REDACTED_HEX_TOKEN>"),
]


def redact_text(text: str) -> str:
    """Apply all redaction patterns to a string. Returns redacted version."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_dict(data: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """Recursively redact sensitive values in a dict."""
    if depth > 10:
        return data
    result: dict[str, Any] = {}
    SECRET_KEYS = frozenset({
        "api_key", "apikey", "token", "bot_token", "password", "passwd", "pwd",
        "secret", "client_secret", "cookie", "session_id", "access_token",
        "refresh_token", "auth", "credential", "private_key", "webhook_url",
    })
    for k, v in data.items():
        k_lower = k.lower().replace("-", "_")
        if any(sk in k_lower for sk in SECRET_KEYS):
            result[k] = "<REDACTED>"
        elif isinstance(v, dict):
            result[k] = redact_dict(v, depth + 1)
        elif isinstance(v, str):
            result[k] = redact_text(v)
        else:
            result[k] = v
    return result


@dataclass
class EnvironmentInfo:
    python_version: str
    platform_info: str
    jarvis_version: str
    install_dir: str
    config_keys: list[str] = field(default_factory=list)  # key names only, not values
    env_vars_present: list[str] = field(default_factory=list)  # names of JARVIS_ vars set
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "python_version": self.python_version,
            "platform": self.platform_info,
            "jarvis_version": self.jarvis_version,
            "install_dir": self.install_dir,
            "config_keys_present": self.config_keys,
            "env_vars_present": self.env_vars_present,
            "timestamp": self.timestamp,
        }


@dataclass
class SupportBundle:
    """Result of create_support_bundle()."""
    zip_path: str
    env_info: EnvironmentInfo
    crash_markers: list[str]
    log_files_included: list[str]
    redaction_applied: bool = True


class SupportDiagnostics:
    """
    One-command support diagnostics + bundle export for JARVIS beta testers.

    Usage::
        diag = SupportDiagnostics()
        bundle = diag.create_support_bundle(output_dir=Path("C:/Users/X/Desktop"))
        print(f"Support bundle: {bundle.zip_path}")
    """

    # Env vars to check for presence (values are NEVER included)
    TRACKED_ENV_VARS = [
        "GOOGLE_API_KEY", "JARVIS_HEADLESS", "JARVIS_MOCK_AUDIO",
        "TELEGRAM_BOT_TOKEN", "ZALO_ACCESS_TOKEN", "DISCORD_BOT_TOKEN",
        "IMAP_PASSWORD", "HA_TOKEN",
    ]

    def __init__(
        self,
        log_dir: Path | None = None,
        install_dir: Path | None = None,
    ) -> None:
        self.log_dir = log_dir or self._default_log_dir()
        self.install_dir = install_dir or Path(".").resolve()

    @staticmethod
    def _default_log_dir() -> Path:
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(appdata) / "JARVIS" / "logs"

    def collect_env_info(self) -> EnvironmentInfo:
        """Collect environment facts. Values of secrets never included."""
        try:
            import jarvis
            jv = jarvis.__version__
        except Exception:
            jv = "unknown"

        env_vars_present = [
            v for v in self.TRACKED_ENV_VARS if os.environ.get(v)
        ]

        return EnvironmentInfo(
            python_version=sys.version,
            platform_info=platform.platform(),
            jarvis_version=jv,
            install_dir=str(self.install_dir),
            env_vars_present=env_vars_present,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def find_crash_markers(self) -> list[str]:
        """Find crash marker files in log directory."""
        markers = []
        if not self.log_dir.exists():
            return markers
        for path in self.log_dir.glob("crash_*.txt"):
            markers.append(str(path))
        for path in self.log_dir.glob("*.crash"):
            markers.append(str(path))
        return markers

    def collect_log_files(self, max_size_mb: float = 5.0) -> list[Path]:
        """Return list of log files, excluding those over max_size_mb."""
        if not self.log_dir.exists():
            return []
        result = []
        for path in sorted(self.log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
            if path.stat().st_size <= max_size_mb * 1024 * 1024:
                result.append(path)
        return result

    def redact_log_content(self, content: str) -> str:
        """Apply credential redaction to log content."""
        return redact_text(content)

    def create_support_bundle(
        self,
        output_dir: Path | None = None,
        include_logs: bool = True,
    ) -> SupportBundle:
        """
        Create a zip support bundle with:
          - environment_info.json (no secret values)
          - redacted log files
          - crash markers list

        Returns SupportBundle with zip_path.
        """
        output_dir = output_dir or Path(".")
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S")
        zip_name = f"jarvis_support_{ts}.zip"
        zip_path = output_dir / zip_name

        env_info = self.collect_env_info()
        crash_markers = self.find_crash_markers()
        log_files = self.collect_log_files() if include_logs else []
        included_logs: list[str] = []

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Environment info (no secrets)
            env_json = json.dumps(env_info.to_dict(), indent=2, ensure_ascii=False)
            zf.writestr("environment_info.json", env_json)

            # Crash markers list
            crash_json = json.dumps({"crash_markers": crash_markers}, indent=2)
            zf.writestr("crash_markers.json", crash_json)

            # Redacted log files
            for lf in log_files:
                try:
                    raw = lf.read_text(encoding="utf-8", errors="replace")
                    redacted = self.redact_log_content(raw)
                    zf.writestr(f"logs/{lf.name}", redacted)
                    included_logs.append(lf.name)
                except Exception as exc:
                    log.warning("Support bundle: could not include %s: %s", lf.name, exc)

            # Readme
            readme = (
                "JARVIS Support Bundle\n"
                f"Generated: {env_info.timestamp}\n"
                f"Version: {env_info.jarvis_version}\n\n"
                "This bundle contains redacted diagnostic information.\n"
                "All API keys, tokens, and passwords have been replaced with <REDACTED>.\n"
                "Please send this file to the JARVIS support team.\n"
            )
            zf.writestr("README.txt", readme)

        log.info("Support bundle created: %s", zip_path)
        return SupportBundle(
            zip_path=str(zip_path),
            env_info=env_info,
            crash_markers=crash_markers,
            log_files_included=included_logs,
            redaction_applied=True,
        )

    def verify_no_secrets_in_bundle(self, zip_path: str) -> tuple[bool, list[str]]:
        """
        Scan bundle for credential plaintext. Returns (clean, violations).
        Used to verify D-15 acceptance criteria: 'secret scan finds no credential plaintext'.
        """
        violations: list[str] = []
        LEAK_PATTERNS = [
            re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*(?!<REDACTED>)\S{8,}"),
        ]

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    content = zf.read(name).decode("utf-8", errors="replace")
                    for pat in LEAK_PATTERNS:
                        for m in pat.finditer(content):
                            violations.append(f"{name}: {m.group(0)[:60]}")
        except Exception as exc:
            violations.append(f"scan_error: {exc}")

        return len(violations) == 0, violations
