"""
jarvis/ui/terminal/session.py
================================
In-memory session history + centralized redaction for the Terminal Control
Center.

Redaction is centralized here rather than relying on every module adapter to
remember which field names are secret: `redact_structured()` is applied to
every ActionOutcome.structured_data before it is placed into a SessionRecord
or written to a saved report.
"""
from __future__ import annotations

import re
import time
from typing import Any

from jarvis.ui.terminal.models import ActionOutcome, SessionRecord

# Substring match, case-insensitive, against dict keys.
_SECRET_KEY_MARKERS = (
    "token", "api_key", "apikey", "password", "passwd", "secret",
    "cookie", "authorization", "auth_header", "oauth", "credential",
    "bot_token", "access_token", "private_key", "embedding",
    "biometric_vector", "face_encoding", "face_vector",
)

_REDACTED = "<REDACTED>"

# Defense-in-depth for secrets accidentally embedded in free-form text
# (e.g. a raw "Bearer xxxx" or "sk-xxxx" style token leaking into an error
# message string rather than a dedicated field).
_INLINE_SECRET_PATTERNS = (
    re.compile(r"bearer\s+[A-Za-z0-9\-_.=]{10,}", re.IGNORECASE),
    re.compile(r"\b\d{9,10}:[A-Za-z0-9_-]{30,}\b"),  # Telegram bot token shape
)


def _redact_text(text: str) -> str:
    redacted = text
    for pattern in _INLINE_SECRET_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def redact_structured(data: Any) -> Any:
    """Recursively redacts secret-shaped keys/values. Safe to call on any
    JSON-ish structure (dict / list / tuple / scalar)."""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for k, v in data.items():
            if _is_secret_key(str(k)):
                out[k] = _REDACTED
            else:
                out[k] = redact_structured(v)
        return out
    if isinstance(data, (list, tuple)):
        return [redact_structured(v) for v in data]
    if isinstance(data, str):
        return _redact_text(data)
    return data


def redact_fields(fields: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out = []
    for key, value in fields:
        if _is_secret_key(key):
            out.append((key, _REDACTED))
        else:
            out.append((key, _redact_text(str(value))))
    return out


class SessionHistory:
    """Bounded, safe, in-memory record of completed terminal operations for
    this `jarvis menu` process. Never persisted automatically -- only via an
    explicit [S] Save."""

    MAX_RECORDS = 500

    def __init__(self) -> None:
        self._records: list[SessionRecord] = []

    def record(self, module: str, action: str, outcome: ActionOutcome) -> SessionRecord:
        rec = SessionRecord(
            timestamp=outcome.started_at or time.time(),
            module=module,
            action=action,
            status=outcome.status.value,
            duration_s=outcome.duration_s,
            summary=outcome.title,
            structured_data=redact_structured(outcome.structured_data),
        )
        self._records.append(rec)
        if len(self._records) > self.MAX_RECORDS:
            self._records = self._records[-self.MAX_RECORDS:]
        return rec

    def all(self) -> list[SessionRecord]:
        return list(self._records)

    def for_module(self, module: str) -> list[SessionRecord]:
        return [r for r in self._records if r.module == module]

    def clear(self) -> None:
        self._records.clear()
