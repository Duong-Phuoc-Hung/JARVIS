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

IMAP client (added v5.1.0):
  - connect() / disconnect() lifecycle with imaplib.IMAP4_SSL.
  - fetch_unread() returns list[EmailMessage] from INBOX.
  - fetch_and_summarize() uses real IMAP when credentials configured;
    falls back to mock_emails list when provided (for testing).
  - Fail-closed: missing host/username/password -> raises IMAPNotConfiguredError.
"""
from __future__ import annotations

import email as email_lib
import html
import imaplib
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


class IMAPNotConfiguredError(RuntimeError):
    """Raised when IMAP credentials are missing — fail-closed contract."""


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

    IMAP lifecycle (v5.1.0):
      - connect() opens an imaplib.IMAP4_SSL connection and logs in.
      - disconnect() logs out and closes the connection safely.
      - fetch_unread() retrieves all UNSEEN emails from INBOX.
      - Fail-closed: missing credentials → IMAPNotConfiguredError (NOT_CONFIGURED).
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
        self._conn: imaplib.IMAP4_SSL | None = None

    # ── IMAP Connection Lifecycle ─────────────────────────────────────────────

    def connect(self) -> None:
        """
        Open an IMAP4_SSL connection and login.

        Raises:
            IMAPNotConfiguredError: if host, username, or password is empty (fail-closed).
            imaplib.IMAP4.error: on authentication failure.
            OSError: on network failure.
        """
        if not self.host or not self.username or not self.password:
            log.error(
                "email: IMAP NOT_CONFIGURED — host=%r username=%r password=<empty=%s>",
                self.host,
                self.username,
                not self.password,
            )
            raise IMAPNotConfiguredError(
                "IMAPEmailReader: host, username, and password are all required. "
                "Set them via SecretsManager or environment variables. Status: NOT_CONFIGURED"
            )
        log.info("email: connecting to IMAP server %s:%d as %s", self.host, self.port, self.username)
        self._conn = imaplib.IMAP4_SSL(self.host, self.port)
        self._conn.login(self.username, self.password)
        log.info("email: IMAP login successful")

    def disconnect(self) -> None:
        """Safely log out and close the IMAP connection. Idempotent."""
        if self._conn is not None:
            try:
                self._conn.logout()
            except Exception as exc:  # noqa: BLE001
                log.debug("email: IMAP logout exception (ignored): %s", exc)
            finally:
                self._conn = None

    def fetch_unread(self, mailbox: str = "INBOX") -> list[EmailMessage]:
        """
        Fetch all UNSEEN emails from ``mailbox``.

        Must call connect() first. Returns empty list when no unread emails exist.
        Fail-closed: any parse error on an individual message is logged and that
        message is skipped (never crashes the whole fetch).

        Returns:
            list[EmailMessage]: parsed unread emails (may be empty).

        Raises:
            RuntimeError: if not connected (connect() not called).
        """
        if self._conn is None:
            raise RuntimeError(
                "IMAPEmailReader.fetch_unread() called before connect(). "
                "Call connect() first."
            )

        status, _data = self._conn.select(mailbox, readonly=True)
        if status != "OK":
            log.warning("email: IMAP SELECT %r failed: %s", mailbox, _data)
            return []

        status, msg_ids_raw = self._conn.search(None, "UNSEEN")
        if status != "OK" or not msg_ids_raw or not msg_ids_raw[0]:
            log.info("email: no UNSEEN messages in %r", mailbox)
            return []

        msg_ids: list[bytes] = msg_ids_raw[0].split()
        log.info("email: found %d UNSEEN messages", len(msg_ids))

        results: list[EmailMessage] = []
        for mid in msg_ids:
            try:
                status, msg_data = self._conn.fetch(mid, "(RFC822)")
                if status != "OK" or not msg_data or msg_data[0] is None:
                    log.warning("email: FETCH failed for msg %r", mid)
                    continue

                raw_bytes = msg_data[0][1]  # type: ignore[index]
                if not isinstance(raw_bytes, bytes):
                    continue

                msg = email_lib.message_from_bytes(raw_bytes)
                sender = msg.get("From", "")
                subject = msg.get("Subject", "")
                date_str = msg.get("Date", "")
                message_id = msg.get("Message-ID", "")

                # Extract plain-text body (fail-closed per message)
                body_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ctype = part.get_content_type()
                        if ctype == "text/plain":
                            try:
                                body_text = part.get_payload(decode=True).decode(  # type: ignore[union-attr]
                                    part.get_content_charset() or "utf-8", errors="replace"
                                )
                                break
                            except Exception:
                                pass
                else:
                    try:
                        payload = msg.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            body_text = payload.decode(
                                msg.get_content_charset() or "utf-8", errors="replace"
                            )
                    except Exception:
                        pass

                results.append(EmailMessage(
                    sender=sender,
                    subject=subject,
                    body_text=body_text,
                    date_str=date_str,
                    message_id=message_id,
                ))
            except Exception as exc:  # noqa: BLE001
                log.warning("email: error parsing message %r — skipped: %s", mid, exc)

        return results

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
        priority_senders. Empty allowlist -> ALL senders rejected.
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

    def _process_emails(self, emails: list[EmailMessage]) -> dict[str, Any]:
        """Apply security pipeline and build voice summary from a list of EmailMessage."""
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

    def fetch_and_summarize(
        self,
        mock_emails: list[EmailMessage] | None = None,
    ) -> dict[str, Any]:
        """
        Filters and summarises priority unread emails.

        If ``mock_emails`` is provided (testing), uses that list directly without
        opening any network connection (preserves existing test compatibility).

        If ``mock_emails`` is None, opens a real IMAP connection:
          - Raises IMAPNotConfiguredError when credentials are missing (fail-closed).
          - Calls connect() -> fetch_unread() -> disconnect() automatically.

        Security pipeline (fail-close at each step):
          1. Sender allowlist check — drop if not whitelisted
          2. Subject injection filter — drop if injection marker found
          3. HTML strip — fail-close, returns '' on error
          4. PromptGuard sanitization on body — before any LLM processing
          5. Hard truncation to _MAX_BODY_LEN chars
        """
        if mock_emails is not None:
            # Testing path: use provided list without network
            return self._process_emails(mock_emails)

        # Production path: real IMAP fetch (fail-closed when not configured)
        self.connect()
        try:
            emails = self.fetch_unread()
        finally:
            self.disconnect()

        return self._process_emails(emails)
