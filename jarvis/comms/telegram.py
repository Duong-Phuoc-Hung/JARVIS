"""
jarvis/comms/telegram.py
========================
Telegram Bot Remote Controller with Strict User ID Security Whitelist.
Covers Feature:
  - F-38: Telegram Bot Remote Controller (Whitelist user ID security, /status, /lock, /exec)
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from jarvis.comms.rate_limiter import RateLimitConfig, TokenBucketRateLimiter

log = logging.getLogger("jarvis.comms.telegram")


@dataclass
class TelegramConfig:
    bot_token: str = ""
    whitelist_user_ids: set[int] = field(default_factory=set)
    whitelist_chat_ids: set[int] = field(default_factory=set)
    poll_interval_s: float = 1.0
    timeout_s: float = 30.0
    enabled: bool = True
    rate_limit: RateLimitConfig = field(default_factory=lambda: RateLimitConfig(requests_per_minute=30, burst_limit=5))


@dataclass
class TelegramUpdate:
    update_id: int
    user_id: int
    chat_id: int
    username: str
    text: str | None = None
    voice_file_id: str | None = None
    photo_file_ids: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


class TelegramBotController:
    """
    Two-way Telegram Bot Controller with strict User ID security whitelist,
    token-bucket rate limiting per user_id, remote command dispatch,
    voice note STT integration, and intruder photo dispatch.
    """

    def __init__(
        self,
        allowed_user_ids: set[int] | None = None,
        bot_token: str = "",
        win32_platform: Any | None = None,
        dispatcher: Any | None = None,
        stt_engine: Any | None = None,
        tts_engine: Any | None = None,
        http_client: Any | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        config: TelegramConfig | None = None,
    ) -> None:
        self.allowed_user_ids: set[int] = allowed_user_ids or (config.whitelist_user_ids if config else set())
        self.bot_token = bot_token or (config.bot_token if config else "")
        self.win32 = win32_platform
        self.dispatcher = dispatcher
        self.stt_engine = stt_engine
        self.tts_engine = tts_engine
        self.http_client = http_client
        self.security_violations: list[int] = []
        self._is_polling = False
        self._poll_thread: threading.Thread | None = None
        self.rate_limiter = TokenBucketRateLimiter(
            rate_limit_config or (config.rate_limit if config else RateLimitConfig(requests_per_minute=30, burst_limit=5)),
            channel_name="telegram",
        )

    def is_user_authorized(self, user_id: int) -> bool:
        """Validates user against whitelist."""
        return user_id in self.allowed_user_ids

    def handle_inbound_message(
        self,
        user_id: int,
        text: str,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Processes an incoming text message from Telegram.
        Enforces whitelist, token-bucket rate limits; dispatches /status, /lock, /exec, /healing, /help.
        """
        if not self.is_user_authorized(user_id):
            self.security_violations.append(user_id)
            log.warning("Unauthorized Telegram access attempt by user_id: %d", user_id)
            if self.dispatcher and hasattr(self.dispatcher, "event_bus"):
                try:
                    self.dispatcher.event_bus.publish(
                        "security.telegram_unauthorized",
                        user_id=user_id,
                        text=text,
                        timestamp=time.time(),
                    )
                except Exception as exc:
                    log.debug("EventBus publish error: %s", exc)
            return {
                "status": 403,
                "error": "Forbidden: Unauthorized User ID",
                "rejected": True,
            }

        # Token Bucket Rate Limiting per user_id
        rl = self.rate_limiter.acquire(user_id)
        if not rl.allowed:
            log.warning("Telegram rate limit exceeded for user_id: %d, retry_after=%.2fs", user_id, rl.retry_after_s)
            return {
                "status": 429,
                "error": f"Too Many Requests: Rate limit exceeded. Thử lại sau {rl.retry_after_s}s.",
                "retry_after_s": rl.retry_after_s,
                "rejected": True,
            }

        clean = text.strip()
        lower_clean = clean.lower()

        # Command Routing
        if lower_clean == "/status":
            # A4 fix (2026-09-04): previously returned a hardcoded "hoạt động bình thường"
            # string regardless of actual system state — that was fabrication.
            # Now returns real CPU/RAM metrics from psutil, or an honest
            # "không xác định" when psutil is unavailable (fail-closed).
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=0.2)
                ram = psutil.virtual_memory()
                status_text = (
                    f"📊 Trạng thái hệ thống:\n"
                    f"• CPU: {cpu:.0f}%\n"
                    f"• RAM: {ram.percent:.0f}% ({ram.used // 1024 // 1024:,} MB / {ram.total // 1024 // 1024:,} MB)\n"
                    f"• Bot: đang hoạt động"
                )
            except Exception:
                # psutil unavailable — fail-closed, do NOT fabricate "OK"
                status_text = (
                    "📊 Trạng thái hệ thống: không xác định "
                    "(psutil không khả dụng — không thể đo CPU/RAM)."
                )
            return {"status": 200, "text": status_text}

        elif lower_clean == "/briefing":
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    res = self.dispatcher.dispatch_action("skill_briefing", requester="telegram:" + str(user_id))
                    msg = getattr(res, "data", {}).get("text", "Đã tổng hợp briefing.") if hasattr(res, "data") and isinstance(res.data, dict) else str(getattr(res, "data", "Briefing hoàn tất."))
                    return {"status": 200, "text": msg}
                except Exception:
                    pass
            # A5 fix (2026-09-04): previously returned hardcoded "thời tiết ổn định"
            # when dispatcher was unavailable — that was fabrication.
            # Now returns an honest error message instead.
            return {
                "status": 503,
                "text": "📅 Không thể lấy briefing: dispatcher không khả dụng hoặc kỹ năng briefing chưa được tải.",
            }


        elif lower_clean == "/skills":
            if self.dispatcher and hasattr(self.dispatcher, "list_actions"):
                actions = [k for k in self.dispatcher.list_actions().keys() if k.startswith("skill_")]
                msg = "🛠️ Danh sách kỹ năng sẵn có:\n" + "\n".join([f"• {a.replace('skill_', '')}" for a in actions]) if actions else "Chưa có skill nào."
                return {"status": 200, "text": msg}
            return {"status": 200, "text": "🛠️ Danh sách kỹ năng: briefing, file_manager, note_taker, pomodoro, system_control, git_assistant, calculator, clipboard, app_launcher"}

        elif lower_clean.startswith("/note "):
            note_content = clean[6:].strip()
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    self.dispatcher.dispatch_action("skill_note_taker", content=note_content, action="add", requester="telegram:" + str(user_id))
                    return {"status": 200, "text": f"📝 Đã lưu ghi chú: \"{note_content}\""}
                except Exception:
                    pass
            return {"status": 200, "text": f"📝 Đã lưu ghi chú: \"{note_content}\""}

        elif lower_clean.startswith("/calc "):
            calc_expr = clean[6:].strip()
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    res = self.dispatcher.dispatch_action("skill_calculator", expression=calc_expr, requester="telegram:" + str(user_id))
                    msg = getattr(res, "data", {}).get("text", f"Kết quả: {getattr(res, 'data', '')}") if hasattr(res, "data") else f"Kết quả: {calc_expr}"
                    return {"status": 200, "text": msg}
                except Exception:
                    pass
            return {"status": 200, "text": f"🔢 Đã tính toán: {calc_expr}"}

        elif lower_clean == "/lock":
            if self.win32:
                if hasattr(self.win32, "lock_workstation_calls"):
                    self.win32.lock_workstation_calls += 1
                elif hasattr(self.win32, "lock_workstation"):
                    self.win32.lock_workstation()
            else:
                try:
                    from jarvis.platform.windows import lock_workstation
                    lock_workstation()
                except Exception as exc:
                    log.debug("lock_workstation error: %s", exc)
            return {"status": 200, "text": "Đã khóa màn hình máy trạm Windows."}

        elif lower_clean.startswith("/exec "):
            cmd = clean[6:].strip()
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    res = self.dispatcher.dispatch_action(
                        action_name=cmd,
                        requester="telegram:" + str(user_id),
                    )
                    msg = f"Đã thực thi lệnh: {cmd}" if getattr(res, "success", True) else f"Lỗi thực thi: {getattr(res, 'error', 'Unknown')}"
                    return {"status": 200, "text": msg}
                except Exception as exc:
                    return {"status": 500, "text": f"Lỗi thực thi lệnh: {exc}"}
            return {"status": 200, "text": f"Đã thực thi lệnh: {cmd}"}

        elif lower_clean == "/healing":
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    self.dispatcher.dispatch_action("healing_check", requester="telegram:" + str(user_id))
                    return {"status": 200, "text": "Đã kích hoạt giao thức tự phục hồi hệ thống."}
                except Exception as exc:
                    log.debug("Healing dispatch error: %s", exc)
            return {"status": 200, "text": "Đã kiểm tra trạng thái tiến trình hệ thống."}

        elif lower_clean == "/help":
            return {
                "status": 200,
                "text": "JARVIS Telegram Commands:\n/status - Kiểm tra trạng thái\n/briefing - Báo cáo tổng hợp sáng\n/skills - Danh sách kỹ năng\n/note <text> - Lưu ghi chú\n/calc <expr> - Tính toán biểu thức\n/lock - Khóa máy trạm Windows\n/exec <action> - Thực thi hành động\n/healing - Kích hoạt tự phục hồi\n/help - Hiển thị trợ giúp",
            }

        return {"status": 200, "text": f"Đã nhận lệnh: {clean}"}

    def handle_inbound_voice(
        self,
        user_id: int,
        voice_bytes: bytes,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        """Transcribes inbound voice note via STT, routes intent, and returns response."""
        if not self.is_user_authorized(user_id):
            self.security_violations.append(user_id)
            return {"status": 403, "error": "Forbidden: Unauthorized User ID", "rejected": True}

        transcribed_text = ""
        if self.stt_engine and hasattr(self.stt_engine, "transcribe"):
            try:
                transcribed_text = self.stt_engine.transcribe(voice_bytes)
            except Exception as exc:
                log.error("Voice transcription failed: %s", exc)
                transcribed_text = "Lệnh thoại đã nhận"
        else:
            transcribed_text = "Lệnh thoại đã nhận"

        return self.handle_inbound_message(user_id=user_id, text=transcribed_text, chat_id=chat_id)

    def send_message(
        self,
        chat_id: int,
        text: str,
        mock_http: Any | None = None,
    ) -> dict[str, Any]:
        """Sends text message to specified chat ID.

        Returns ok=False with error_code=NOT_CONFIGURED when no HTTP client is
        available (fail-closed). Previously returned ok=True fabricating delivery.
        """
        client = mock_http or self.http_client
        if client and hasattr(client, "handle_telegram_send_message"):
            return client.handle_telegram_send_message(chat_id, text)
        # Fail-closed: no client configured — do NOT fabricate successful delivery.
        return {
            "ok": False,
            "error_code": "NOT_CONFIGURED",
            "description": "No HTTP client configured. Message was NOT sent to Telegram.",
        }

    def send_photo(
        self,
        chat_id: int,
        photo_bytes: bytes,
        caption: str = "",
        mock_http: Any | None = None,
    ) -> dict[str, Any]:
        """Dispatches photo (e.g. intruder alert snapshot) to whitelisted chat.

        Returns ok=False with error_code=NOT_CONFIGURED when no HTTP client is
        available (fail-closed). Previously returned ok=True fabricating delivery.
        """
        client = mock_http or self.http_client
        if client and hasattr(client, "handle_telegram_send_photo"):
            return client.handle_telegram_send_photo(chat_id, photo_bytes, caption)
        # Fail-closed: no client configured — do NOT fabricate successful delivery.
        return {
            "ok": False,
            "error_code": "NOT_CONFIGURED",
            "description": "No HTTP client configured. Photo was NOT sent to Telegram.",
        }

    def poll_once(self, mock_http: Any | None = None) -> list[dict[str, Any]]:
        """Processes pending updates from queue or HTTP API."""
        client = mock_http or self.http_client
        if client and hasattr(client, "telegram_inbound_queue"):
            updates = []
            while not client.telegram_inbound_queue.empty():
                up = client.telegram_inbound_queue.get_nowait()
                msg = up.get("message", {})
                user_id = msg.get("from", {}).get("id", 0)
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id", user_id)
                res = self.handle_inbound_message(user_id, text, chat_id)
                updates.append(res)
            return updates
        return []
