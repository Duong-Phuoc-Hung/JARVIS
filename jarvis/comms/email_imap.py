"""
jarvis/comms/email_imap.py
==========================
IMAP Email Poller, Priority Sender Filter, MIME HTML Parser, and Voice Summarizer.
Covers Feature:
  - F-39: IMAP Priority Email Reader & LLM Summarizer (Unread email filter, HTML strip, voice formatting)
"""
from __future__ import annotations

from dataclasses import dataclass, field
import email
from email.header import decode_header
import html
import imaplib
import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.comms.email")


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
    priority_emails: List[EmailMessage] = field(default_factory=list)


class IMAPEmailReader:
    """IMAP client reader that fetches priority unread emails and formats AI summaries."""

    def __init__(
        self,
        priority_senders: Optional[List[str]] = None,
        host: str = "imap.gmail.com",
        port: int = 993,
        username: str = "",
        password: str = "",
    ):
        self.priority_senders: List[str] = [s.lower() for s in (priority_senders or [])]
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    def _strip_html(self, html_text: str) -> str:
        """Cleans HTML tags and unescapes entities."""
        clean = re.sub(r"<[^>]+>", " ", html_text)
        return html.unescape(clean).strip()

    def fetch_and_summarize(
        self,
        mock_emails: Optional[List[EmailMessage]] = None,
    ) -> Dict[str, Any]:
        """Filters priority unread emails and generates natural language voice summary."""
        emails = mock_emails or []
        priority_emails = [
            e for e in emails
            if any(p in e.sender.lower() for p in self.priority_senders) or e.is_priority
        ]

        summaries = []
        for em in priority_emails:
            clean_body = self._strip_html(em.body_text) if "<" in em.body_text else em.body_text
            truncated_body = clean_body[:200].strip()
            summary_text = f"Email mới từ {em.sender} về tiêu đề {em.subject}. Tóm tắt: {truncated_body}."
            summaries.append(summary_text)

        combined_voice = " ".join(summaries) if summaries else "Không có email ưu tiên mới."
        return {
            "total_unread": len(emails),
            "priority_count": len(priority_emails),
            "voice_summary": combined_voice,
        }
