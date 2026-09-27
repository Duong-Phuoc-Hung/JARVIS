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
import ssl
from dataclasses import dataclass, field
from email import policy
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


class IMAPTransportError(imaplib.IMAP4.error):
    """Redacted transport failure; never an empty-mailbox success."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


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
    dropped_count: int = 0  # emails dropped by security filters


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
        timeout: float = 10.0,
        ssl_context: ssl.SSLContext | None = None,
    ):
        # Normalise to lowercase once at init time
        self.priority_senders: list[str] = [s.lower().strip() for s in (priority_senders or [])]
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.ssl_context = ssl_context or ssl.create_default_context()
        if not self.ssl_context.check_hostname or self.ssl_context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("TLS_VERIFICATION_REQUIRED")
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
            raise IMAPNotConfiguredError("NOT_CONFIGURED")
        self.disconnect()
        try:
            self._conn = imaplib.IMAP4_SSL(
                self.host, self.port, timeout=self.timeout, ssl_context=self.ssl_context
            )
            self._command("login", self.username, self.password)
        except IMAPTransportError:
            raise
        except Exception as exc:
            self._fail(exc)

    def _fail(self, exc: Exception, stage: str = "connect") -> None:
        code = (
            "TIMEOUT"
            if isinstance(exc, TimeoutError)
            else "DISCONNECTED"
            if isinstance(exc, (imaplib.IMAP4.abort, EOFError))
            else "AUTH_FAILED"
            if stage == "login"
            else "PROTOCOL_ERROR"
            if isinstance(exc, imaplib.IMAP4.error)
            else "CONNECTION_FAILED"
        )
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.shutdown()
            except Exception:
                pass
        raise IMAPTransportError(code) from None

    def _command(self, name: str, *args, **kwargs):
        try:
            status, data = getattr(self._conn, name)(*args, **kwargs)
            if status != "OK":
                raise imaplib.IMAP4.error("PROTOCOL_ERROR")
            return data
        except Exception as exc:
            self._fail(exc, name)

    def disconnect(self) -> None:
        """Idempotent logout without expunging or logging server response/body."""
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                try:
                    conn.shutdown()
                except Exception:
                    pass

    def fetch_unread(self, mailbox: str = "INBOX") -> list[EmailMessage]:
        """Read allowed UNSEEN messages over verified TLS without changing Seen.

        Transport/protocol errors raise IMAPTransportError and invalidate the
        session; reconnect explicitly or use fetch_and_summarize on the next poll.
        The sender header allowlist is filtering, not cryptographic sender identity.
        Returned email is untrusted data, never an instruction or authorization.
        """
        if self._conn is None:
            raise RuntimeError("NOT_CONNECTED: Call connect() first")
        self._command("select", mailbox, readonly=True)
        ids = self._command("search", None, "UNSEEN")
        if not ids or not ids[0]:
            return []
        results = []
        for mid in ids[0].split():
            data = self._command("fetch", mid, "(BODY.PEEK[])")
            raw = next(
                (
                    item[1]
                    for item in data or []
                    if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes)
                ),
                None,
            )
            if raw is None:
                self._fail(imaplib.IMAP4.error("MALFORMED_FETCH"), "fetch")
            try:
                msg = email_lib.message_from_bytes(raw, policy=policy.default)
                sender = str(msg.get("From", ""))
                subject = str(msg.get("Subject", ""))
                if not self._is_sender_allowed(sender) or self._has_injection_subject(subject):
                    continue
                part = msg.get_body(preferencelist=("plain", "html")) if msg.is_multipart() else msg
                body = part.get_content() if part is not None else ""
                if not isinstance(body, str):
                    continue
                if part.get_content_type() == "text/html":
                    body = self._strip_html(body)
                results.append(
                    EmailMessage(
                        sender,
                        subject,
                        body,
                        date_str=str(msg.get("Date", "")),
                        message_id=str(msg.get("Message-ID", "")),
                    )
                )
            except Exception:
                log.warning("email: malformed MIME dropped")
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
        addresses = email_lib.utils.getaddresses([sender])
        if len(addresses) != 1:
            return False
        addr = addresses[0][1].lower().strip()
        if addr.count("@") != 1:
            return False
        domain = addr.rsplit("@", 1)[1]
        return any(
            addr == allowed if "@" in allowed else domain == allowed
            for allowed in self.priority_senders
        )

    def _has_injection_subject(self, subject: str) -> bool:
        """Returns True if subject matches any known injection pattern."""
        for pattern in _INJECTION_SUBJECT_PATTERNS:
            if pattern.search(subject):
                log.warning("email: injection subject dropped")
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
        except Exception:
            log.warning("email: sanitizer unavailable; body withheld")
            sanitized = ""

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
                    log.info("email: sender not in allowlist — dropped")
                    dropped += 1
                    continue

                # Step 2: subject injection filter
                if self._has_injection_subject(em.subject):
                    dropped += 1
                    continue

                accepted.append(em)

            except Exception as exc:
                log.warning("email: invalid message dropped")
                dropped += 1

        summaries: list[str] = []
        for em in accepted:
            try:
                # Step 3: HTML strip
                body = self._strip_html(em.body_text) if "<" in em.body_text else em.body_text

                # Steps 4+5: PromptGuard + hard truncation
                safe_body = self._sanitize_for_llm(body)

                summary_text = (
                    f"Email mới từ {em.sender} về tiêu đề {em.subject}. Tóm tắt: {safe_body}."
                )
                summaries.append(summary_text)
            except Exception as exc:
                log.warning("email: summary unavailable")

        combined_voice = " ".join(summaries) if summaries else "Không có email ưu tiên mới."
        log.info(
            "email: processed %d/%d emails (%d dropped by security filters)",
            len(accepted),
            len(emails),
            dropped,
        )

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
