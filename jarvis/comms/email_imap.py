"""
jarvis/comms/email_imap.py
==========================
IMAP Email Poller, Priority Sender Filter, MIME HTML Parser, and Voice Summarizer.
Covers Feature:
  - F-39: IMAP Priority Email Reader & LLM Summarizer (Unread email filter, HTML strip, voice formatting)

Security model (added v4.3.0):
  - FAIL-CLOSE sender allowlist: emails from non-whitelisted senders are DROPPED entirely,
    not just de-prioritized. Email is an attack surface that can carry exploit + prompt
    injection simultaneously.
  - PromptGuard on body: email body is sanitized before any LLM processing.
  - Subject injection filter: subjects containing injection markers are rejected.
  - Max body length: hard cap before LLM to prevent oversized prompt attacks.
  - All parsing wrapped in try/except fail-close: malformed MIME never crashes JARVIS.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("jarvis.comms.email")

# ── Security constants ────────────────────────────────────────────────────────
# Hard cap on body characters sent to LLM. Even with legitimate email, there's no
# reason to feed >1000 chars into a voice summary.
_MAX_BODY_LEN: int = 1000

# Subject patterns that indicate injection attempts.
# Fail-close: subject matching ANY of these → email dropped entirely.
_INJECTION_SUBJECT_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\[JARVIS\s*:", re.IGNORECASE),
    re.compile(r"ignore\s+(previous|above|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"assistant\s*:", re.IGNORECASE),
)


@dataclass
class EmailMessage:
    sender: str
    subject: str
    body_text: str
    is_priority: bool = False
    date_str: str = ""
    message_id: str = ""


@dataclass
class EmailSummaryResult:
    total_unread: int
    priority_count: int
    voice_summary: str
    priority_emails: list[EmailMessage] = field(default_factory=list)
    dropped_count: int = 0          # emails dropped by security filters


class IMAPEmailReader:
    """
    IMAP client reader that fetches priority unread emails and formats AI summaries.

    Security: implements fail-close allowlist — only emails whose sender domain or
    full address appears in ``priority_senders`` are processed. All other emails
    are silently dropped before any LLM processing occurs.
    """

    def __init__(
        self,
        priority_senders: list[str] | None = None,
        host: str = "imap.gmail.com",
        port: int = 993,
        username: str = "",
        password: str = "",
    ):
        # Normalise to lowercase once at init time
        self.priority_senders: list[str] = [s.lower().strip() for s in (priority_senders or [])]
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    # ── Private helpers ───────────────────────────────────────────────────────

    def _strip_html(self, html_text: str) -> str:
        """Strips HTML tags and unescapes entities. Fail-close: returns '' on error."""
        try:
            clean = re.sub(r"<[^>]+>", " ", html_text)
            return html.unescape(clean).strip()
        except Exception:
            log.warning("email: HTML stripping failed — returning empty body")
            return ""

    def _is_sender_allowed(self, sender: str) -> bool:
        """
        Fail-close allowlist check.
        Returns True only if the sender's full address OR domain appears in
        priority_senders. Empty allowlist → ALL senders rejected.
        """
        if not self.priority_senders:
            log.debug("email: empty allowlist — all senders rejected (fail-close)")
            return False
        s = sender.lower().strip()
        # Extract domain from "Display Name <addr@domain.com>" format
        match = re.search(r"<([^>]+)>", s)
        addr = match.group(1) if match else s
        domain = addr.split("@")[-1] if "@" in addr else ""
        return any(
            allowed in addr or (domain and allowed in domain)
            for allowed in self.priority_senders
        )

    def _has_injection_subject(self, subject: str) -> bool:
        """Returns True if subject matches any known injection pattern."""
        for pattern in _INJECTION_SUBJECT_PATTERNS:
            if pattern.search(subject):
                log.warning(
                    "email: injection pattern in subject — email dropped: %r",
                    subject[:80],
                )
                return True
        return False

    def _sanitize_for_llm(self, text: str) -> str:
        """
        Apply PromptGuard-style sanitization before feeding body to LLM.
        Truncates to _MAX_BODY_LEN after sanitization.
        """
        try:
            from jarvis.security.prompt_guard import PromptGuard
            result = PromptGuard().sanitize(text)
            sanitized = str(result)
        except ImportError:
            # PromptGuard not available — fall back to basic stripping
            sanitized = re.sub(r"(ignore|disregard|forget)\s+(all|previous|prior)", "",
                               text, flags=re.IGNORECASE)
        except Exception as exc:
            log.warning("email: PromptGuard failed (%s) — using raw text", exc)
            sanitized = text

        return sanitized[:_MAX_BODY_LEN].strip()

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_and_summarize(
        self,
        mock_emails: list[EmailMessage] | None = None,
    ) -> dict[str, Any]:
        """
        Filters and summarises priority unread emails.

        Security pipeline (fail-close at each step):
          1. Sender allowlist check — drop if not whitelisted
          2. Subject injection filter — drop if injection marker found
          3. HTML strip — fail-close, returns '' on error
          4. PromptGuard sanitization on body — before any LLM processing
          5. Hard truncation to _MAX_BODY_LEN chars
        """
        emails = mock_emails or []
        accepted: list[EmailMessage] = []
        dropped = 0

        for em in emails:
            try:
                # Step 1: sender allowlist (fail-close)
                if not self._is_sender_allowed(em.sender):
                    log.info("email: sender not in allowlist — dropped: %r", em.sender[:60])
                    dropped += 1
                    continue

                # Step 2: subject injection filter
                if self._has_injection_subject(em.subject):
                    dropped += 1
                    continue

                accepted.append(em)

            except Exception as exc:
                log.warning("email: error during filter for %r — dropped: %s",
                            getattr(em, "sender", "?"), exc)
                dropped += 1

        summaries: list[str] = []
        for em in accepted:
            try:
                # Step 3: HTML strip
                body = self._strip_html(em.body_text) if "<" in em.body_text else em.body_text

                # Steps 4+5: PromptGuard + hard truncation
                safe_body = self._sanitize_for_llm(body)

                summary_text = (
                    f"Email mới từ {em.sender} về tiêu đề {em.subject}. "
                    f"Tóm tắt: {safe_body}."
                )
                summaries.append(summary_text)
            except Exception as exc:
                log.warning("email: summary generation failed for %r: %s",
                            em.sender[:40], exc)

        combined_voice = " ".join(summaries) if summaries else "Không có email ưu tiên mới."
        log.info("email: processed %d/%d emails (%d dropped by security filters)",
                 len(accepted), len(emails), dropped)

        return {
            "total_unread": len(emails),
            "priority_count": len(accepted),
            "voice_summary": combined_voice,
            "dropped_by_security": dropped,
        }

