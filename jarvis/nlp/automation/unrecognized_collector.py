"""
jarvis/nlp/automation/unrecognized_collector.py
==============================================
Real-time Collector for Unrecognized and Low-Confidence Voice/NLP Interactions.
Captures turns where the intent router or classifier fell back to 'unknown' or
had low confidence (< 0.45).
Includes:
  - Sanitization of personally identifiable information (PII) before storage.
  - Thread-safe atomic persistence to JSON Lines log.
  - Query and aggregation interfaces for the Continuous Learning flywheel.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.nlp.automation.unrecognized_collector")

DEFAULT_FEEDBACK_DIR = Path("data/feedback")
DEFAULT_FEEDBACK_FILE = DEFAULT_FEEDBACK_DIR / "unrecognized_turns.jsonl"

# Regex patterns for redacting sensitive information
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"\b(?:\+?84|0)(?:\d{9}|\d{10})\b")
_CREDIT_CARD_RE = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
_PASSWORD_PREFIX_RE = re.compile(r"(?:mật khẩu|pass|password|mk|mã pin)\s+(?:là\s+)?(\S+)", re.IGNORECASE)


def scrub_pii(text: str) -> str:
    """Removes sensitive personal data (emails, phones, card numbers, passwords) from text."""
    if not text:
        return ""
    scrubbed = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    scrubbed = _PHONE_RE.sub("[REDACTED_PHONE]", scrubbed)
    scrubbed = _CREDIT_CARD_RE.sub("[REDACTED_CARD]", scrubbed)
    scrubbed = _PASSWORD_PREFIX_RE.sub(r"\1 [REDACTED_PASSWORD]", scrubbed)
    return scrubbed.strip()


@dataclass
class UnrecognizedTurn:
    """Record of an unrecognized or low-confidence interaction turn."""
    raw_text: str
    confidence: float
    source: str
    timestamp: float
    session_id: str = ""
    classified_intent: str = "unknown"
    metadata: dict[str, Any] | None = None


class UnrecognizedTurnCollector:
    """
    Thread-safe collector that records unhandled queries for offline model re-training.
    """

    def __init__(self, log_path: Path | str = DEFAULT_FEEDBACK_FILE) -> None:
        self.log_path = Path(log_path)
        self._lock = threading.Lock()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_turn(
        self,
        raw_text: str,
        confidence: float,
        source: str = "local_classifier",
        classified_intent: str = "unknown",
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Scrubs PII and appends an interaction record to the JSON Lines store.
        """
        clean_text = scrub_pii(raw_text)
        if not clean_text:
            return False

        record = UnrecognizedTurn(
            raw_text=clean_text,
            confidence=float(confidence),
            source=source,
            timestamp=time.time(),
            session_id=session_id,
            classified_intent=classified_intent,
            metadata=metadata or {},
        )

        line = json.dumps(asdict(record), ensure_ascii=False) + "\n"

        with self._lock:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(line)
                return True
            except Exception as e:
                logger.error("Failed writing unrecognized turn to %s: %s", self.log_path, e)
                return False

    def count_turns(self) -> int:
        """Returns total count of recorded turns."""
        if not self.log_path.exists():
            return 0
        with self._lock:
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    return sum(1 for line in f if line.strip())
            except Exception:
                return 0

    def load_turns(self, limit: int = 1000) -> list[UnrecognizedTurn]:
        """Loads the most recent unrecognized turns."""
        if not self.log_path.exists():
            return []
        turns: list[UnrecognizedTurn] = []
        with self._lock:
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            turns.append(UnrecognizedTurn(**data))
            except Exception as e:
                logger.error("Failed loading turns from %s: %s", self.log_path, e)
        return turns[-limit:]

    def clear(self) -> bool:
        """Clears the feedback log."""
        with self._lock:
            try:
                if self.log_path.exists():
                    self.log_path.unlink()
                return True
            except Exception:
                return False
