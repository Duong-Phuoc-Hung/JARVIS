"""
Two-Phase Confirmation Safety Gate for High-Risk and Destructive Actions.
Provides a 30-second tokenized state machine protecting against unintended OS operations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid


@dataclass
class PendingConfirmation:
    """Represents an action awaiting explicit confirmation."""
    token: str
    action_desc: str
    payload: Any = None
    callback: Optional[Callable[..., Any]] = None
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: str = "PENDING"  # PENDING, CONFIRMED, REJECTED, EXPIRED

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class SafetyGate:
    """
    Two-phase voice/manual confirmation gate for high-risk actions.
    Gated actions generate an expiring token and require affirmative confirmation.
    """

    AFFIRMATIVE_PHRASES = {
        "có", "co", "đồng ý", "dong y", "xác nhận", "xac nhan", "chắc chắn",
        "chac chan", "thực hiện", "thuc hien", "được", "duoc", "yes", "y",
        "confirm", "proceed", "ok", "oke", "chấp nhận", "chap nhan"
    }

    NEGATIVE_PHRASES = {
        "không", "khong", "hủy", "huy", "dừng lại", "dung lai", "thôi", "thoi",
        "bỏ qua", "bo qua", "cancel", "no", "n", "abort", "từ chối", "tu choi"
    }

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self._pending: Dict[str, PendingConfirmation] = {}
        self._lock = threading.RLock()

    def request_confirmation(
        self,
        action_desc: str,
        payload: Any = None,
        callback: Optional[Callable[..., Any]] = None,
    ) -> str:
        """
        Registers a dangerous action and returns a unique confirmation token.
        Token automatically expires after `timeout_seconds` (default 30s).
        """
        with self._lock:
            self.cleanup_expired()
            token = uuid.uuid4().hex[:8].upper()
            now = time.time()
            entry = PendingConfirmation(
                token=token,
                action_desc=action_desc,
                payload=payload,
                callback=callback,
                created_at=now,
                expires_at=now + self.timeout_seconds,
                status="PENDING",
            )
            self._pending[token] = entry
            return token

    def confirm(self, token: str) -> bool:
        """
        Confirms and executes the gated action if the token is valid and active.
        Returns True if confirmation and execution succeeded, False otherwise.
        """
        with self._lock:
            token_clean = token.strip().upper()
            entry = self._pending.get(token_clean)
            if not entry:
                return False

            if entry.status != "PENDING" or entry.is_expired:
                entry.status = "EXPIRED" if entry.is_expired else entry.status
                return False

            entry.status = "CONFIRMED"

            # Execute callback if provided
            if entry.callback and callable(entry.callback):
                try:
                    if entry.payload is not None:
                        try:
                            entry.callback(entry.payload)
                        except TypeError:
                            entry.callback()
                    else:
                        entry.callback()
                except Exception:
                    # Keep CONFIRMED status even if callback raises
                    raise

            return True

    def reject(self, token: str) -> bool:
        """Rejects and cancels a pending confirmation request."""
        with self._lock:
            token_clean = token.strip().upper()
            entry = self._pending.get(token_clean)
            if not entry:
                return False
            entry.status = "REJECTED"
            return True

    def cancel(self, token: str) -> bool:
        """Alias for reject."""
        return self.reject(token)

    def is_pending(self, token: str) -> bool:
        """Returns True if the token is active, unexpired, and pending."""
        with self._lock:
            token_clean = token.strip().upper()
            entry = self._pending.get(token_clean)
            if not entry:
                return False
            if entry.is_expired:
                entry.status = "EXPIRED"
                return False
            return entry.status == "PENDING"

    def get_pending(self, token: str) -> Optional[PendingConfirmation]:
        """Retrieves confirmation entry by token."""
        with self._lock:
            token_clean = token.strip().upper()
            return self._pending.get(token_clean)

    def get_latest_pending(self) -> Optional[PendingConfirmation]:
        """Returns the most recent active unexpired pending confirmation."""
        with self._lock:
            self.cleanup_expired()
            pending_items = [
                item for item in self._pending.values()
                if item.status == "PENDING" and not item.is_expired
            ]
            if not pending_items:
                return None
            pending_items.sort(key=lambda x: x.created_at, reverse=True)
            return pending_items[0]

    def list_pending(self) -> List[PendingConfirmation]:
        """Lists all currently active unexpired pending confirmations."""
        with self._lock:
            self.cleanup_expired()
            return [
                item for item in self._pending.values()
                if item.status == "PENDING" and not item.is_expired
            ]

    def cleanup_expired(self) -> int:
        """Marks expired pending entries and removes old records."""
        with self._lock:
            now = time.time()
            expired_count = 0
            for entry in list(self._pending.values()):
                if entry.status == "PENDING" and now > entry.expires_at:
                    entry.status = "EXPIRED"
                    expired_count += 1
            return expired_count

    def is_affirmative(self, phrase: str) -> bool:
        """Checks if a voice/text response indicates affirmative confirmation."""
        p = phrase.strip().lower()
        if p in self.AFFIRMATIVE_PHRASES:
            return True
        for aff in self.AFFIRMATIVE_PHRASES:
            if f" {aff} " in f" {p} ":
                return True
        return False

    def is_negative(self, phrase: str) -> bool:
        """Checks if a voice/text response indicates cancellation or rejection."""
        p = phrase.strip().lower()
        if p in self.NEGATIVE_PHRASES:
            return True
        for neg in self.NEGATIVE_PHRASES:
            if f" {neg} " in f" {p} ":
                return True
        return False

    def process_voice_response(
        self, phrase: str, token: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Evaluates a natural voice response against pending confirmations.
        Returns (success, message).
        """
        with self._lock:
            target = self.get_pending(token) if token else self.get_latest_pending()
            if not target:
                return False, "Không có yêu cầu xác nhận nào đang chờ hoặc yêu cầu đã hết hạn."

            if self.is_affirmative(phrase):
                success = self.confirm(target.token)
                if success:
                    return True, f"Đã xác nhận và thực thi thao tác '{target.action_desc}', thưa Ngài."
                return False, "Yêu cầu xác nhận đã hết hạn hoặc không hợp lệ."

            if self.is_negative(phrase):
                self.reject(target.token)
                return False, f"Đã hủy thao tác '{target.action_desc}' theo yêu cầu của Ngài."

            return False, f"Không nhận diện được phản hồi. Vui lòng nói 'đồng ý' hoặc 'hủy' để xử lý yêu cầu '{target.action_desc}'."
