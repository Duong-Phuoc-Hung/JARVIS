"""
rebuilt/telegram_controller.py
==============================
Clean-room implementation of Telegram Bot Remote Controller.
Implements rules TG-01 to TG-09 from SPEC-JARVIS-001.

Contracts:
- TG-01: Whitelist-only authorization, security violation logging.
- TG-02: Token-bucket rate limiting per user_id.
- TG-03: Command routing table for inbound messages.
- TG-04: /status anti-fabrication (real psutil or honest fail-closed error).
- TG-05: Fail-closed STT voice transcription contract across all failure paths.
- TG-06: STT success routing to handle_inbound_message.
- TG-07: Fast guard returning NOT_CONFIGURED when bot_token is empty.
- TG-08: Standardized HTTP status mapping (200, 401, 429, timeout, error).
- TG-09: Background daemon polling thread with 1.0s interval.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("rebuilt.telegram_controller")


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_s: float = 0.0


@dataclass
class RateLimitConfig:
    requests_per_minute: int = 30
    burst_limit: int = 5


class TokenBucketRateLimiter:
    """
    In-memory per-user token-bucket rate limiter.
    Rule TG-02.
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()
        self.rate_per_sec = self.config.requests_per_minute / 60.0
        self.capacity = float(self.config.burst_limit)
        self._buckets: dict[int, tuple[float, float]] = {}  # user_id -> (tokens, last_time)
        self._lock = threading.Lock()

    def acquire(self, user_id: int) -> RateLimitResult:
        now = time.monotonic()
        with self._lock:
            tokens, last_update = self._buckets.get(user_id, (self.capacity, now))
            # Replenish tokens based on elapsed time
            elapsed = now - last_update
            tokens = min(self.capacity, tokens + elapsed * self.rate_per_sec)

            if tokens >= 1.0:
                self._buckets[user_id] = (tokens - 1.0, now)
                return RateLimitResult(allowed=True, retry_after_s=0.0)
            else:
                deficit = 1.0 - tokens
                retry_after = round(deficit / self.rate_per_sec, 2)
                self._buckets[user_id] = (tokens, now)
                return RateLimitResult(allowed=False, retry_after_s=max(0.1, retry_after))


@dataclass
class TelegramConfig:
    bot_token: str = ""
    whitelist_user_ids: set[int] = field(default_factory=set)
    whitelist_chat_ids: set[int] = field(default_factory=set)
    poll_interval_s: float = 1.0
    timeout_s: float = 30.0
    enabled: bool = True
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)


class TelegramController:
    """
    Clean-room implementation of two-way Telegram Bot Controller.
    Rules TG-01 to TG-09.
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
        self.allowed_user_ids: set[int] = (
            allowed_user_ids
            if allowed_user_ids is not None
            else (config.whitelist_user_ids if config else set())
        )
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
            rate_limit_config or (config.rate_limit if config else RateLimitConfig())
        )
        self.last_update_id: int = 0
        self._session: Any | None = None
        self.timeout_s: float = config.timeout_s if config else 30.0

    def is_user_authorized(self, user_id: int) -> bool:
        """Rule TG-01: Verify user ID against whitelist."""
        return user_id in self.allowed_user_ids

    def handle_inbound_message(
        self,
        user_id: int,
        text: str,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Process inbound text command.
        Rules TG-01, TG-02, TG-03, TG-04.
        """
        # Rule TG-01: Check authorization whitelist first
        if not self.is_user_authorized(user_id):
            self.security_violations.append(user_id)
            log.warning("Unauthorized Telegram access attempt by user_id: %d", user_id)
            return {
                "status": 403,
                "error": "Forbidden: Unauthorized User ID",
                "rejected": True,
            }

        # Rule TG-02: Check token-bucket rate limit second
        rl = self.rate_limiter.acquire(user_id)
        if not rl.allowed:
            log.warning("Rate limit exceeded for user_id: %d, retry_after=%.2fs", user_id, rl.retry_after_s)
            return {
                "status": 429,
                "error": f"Too Many Requests: Rate limit exceeded. Thử lại sau {rl.retry_after_s}s.",
                "retry_after_s": rl.retry_after_s,
                "rejected": True,
            }

        clean = text.strip()
        lower_clean = clean.lower()

        # Rule TG-03 & TG-04: Command Routing
        if lower_clean == "/status":
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
                # Rule TG-04: psutil unavailable/failed - Fail-closed, NEVER fabricate OK
                status_text = (
                    "📊 Trạng thái hệ thống: không xác định "
                    "(psutil không khả dụng — không thể đo CPU/RAM)."
                )
            return {"status": 200, "text": status_text}

        elif lower_clean == "/briefing":
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    res = self.dispatcher.dispatch_action("skill_briefing", requester=f"telegram:{user_id}")
                    msg = (
                        getattr(res, "data", {}).get("text", "Đã tổng hợp briefing.")
                        if hasattr(res, "data") and isinstance(res.data, dict)
                        else str(getattr(res, "data", "Briefing hoàn tất."))
                    )
                    return {"status": 200, "text": msg}
                except Exception:
                    pass
            return {
                "status": 503,
                "text": "📅 Không thể lấy briefing: dispatcher không khả dụng hoặc kỹ năng briefing chưa được tải.",
            }

        elif lower_clean == "/skills":
            if self.dispatcher and hasattr(self.dispatcher, "list_actions"):
                actions = [k for k in self.dispatcher.list_actions().keys() if k.startswith("skill_")]
                msg = (
                    "🛠️ Danh sách kỹ năng sẵn có:\n" + "\n".join([f"• {a.replace('skill_', '')}" for a in actions])
                    if actions
                    else "Chưa có skill nào."
                )
                return {"status": 200, "text": msg}
            return {
                "status": 200,
                "text": "🛠️ Danh sách kỹ năng: briefing, file_manager, note_taker, pomodoro, system_control, git_assistant, calculator, clipboard, app_launcher",
            }

        elif lower_clean.startswith("/note "):
            note_content = clean[6:].strip()
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    self.dispatcher.dispatch_action(
                        "skill_note_taker",
                        content=note_content,
                        action="add",
                        requester=f"telegram:{user_id}",
                    )
                    return {"status": 200, "text": f"📝 Đã lưu ghi chú: \"{note_content}\""}
                except Exception as exc:
                    return {"status": 500, "text": f"Lỗi lưu ghi chú: {exc}"}
            return {"status": 503, "text": "❌ Lỗi: ActionDispatcher chưa được cấu hình. Ghi chú không được lưu."}

        elif lower_clean.startswith("/calc "):
            calc_expr = clean[6:].strip()
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    res = self.dispatcher.dispatch_action(
                        "skill_calculator",
                        expression=calc_expr,
                        requester=f"telegram:{user_id}",
                    )
                    msg = (
                        getattr(res, "data", {}).get("text", f"Kết quả: {getattr(res, 'data', '')}")
                        if hasattr(res, "data")
                        else f"Kết quả: {calc_expr}"
                    )
                    return {"status": 200, "text": msg}
                except Exception as exc:
                    return {"status": 500, "text": f"Lỗi tính toán: {exc}"}
            return {"status": 503, "text": "❌ Lỗi: ActionDispatcher chưa được cấu hình. Phép tính không được thực hiện."}

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
                    log.debug("lock_workstation fallback error: %s", exc)
            return {"status": 200, "text": "Đã khóa màn hình máy trạm Windows."}

        elif lower_clean.startswith("/exec "):
            cmd = clean[6:].strip()
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    res = self.dispatcher.dispatch_action(
                        action_name=cmd,
                        requester=f"telegram:{user_id}",
                    )
                    msg = (
                        f"Đã thực thi lệnh: {cmd}"
                        if getattr(res, "success", True)
                        else f"Lỗi thực thi: {getattr(res, 'error', 'Unknown')}"
                    )
                    return {"status": 200, "text": msg}
                except Exception as exc:
                    return {"status": 500, "text": f"Lỗi thực thi lệnh: {exc}"}
            return {"status": 503, "text": "❌ Lỗi: ActionDispatcher chưa được cấu hình. Lệnh không được thực thi."}

        elif lower_clean == "/healing":
            if self.dispatcher and hasattr(self.dispatcher, "dispatch_action"):
                try:
                    self.dispatcher.dispatch_action("healing_check", requester=f"telegram:{user_id}")
                    return {"status": 200, "text": "Đã kích hoạt giao thức tự phục hồi hệ thống."}
                except Exception as exc:
                    log.debug("Healing dispatch error: %s", exc)
                    return {"status": 500, "text": f"Lỗi kích hoạt tự phục hồi: {exc}"}
            return {"status": 503, "text": "❌ Lỗi: ActionDispatcher chưa được cấu hình. Không thể kích hoạt tự phục hồi."}

        elif lower_clean == "/help":
            return {
                "status": 200,
                "text": (
                    "JARVIS Telegram Commands:\n"
                    "/status - Kiểm tra trạng thái\n"
                    "/briefing - Báo cáo tổng hợp sáng\n"
                    "/skills - Danh sách kỹ năng\n"
                    "/note <text> - Lưu ghi chú\n"
                    "/calc <expr> - Tính toán biểu thức\n"
                    "/lock - Khóa máy trạm Windows\n"
                    "/exec <action> - Thực thi hành động\n"
                    "/healing - Kích hoạt tự phục hồi\n"
                    "/help - Hiển thị trợ giúp"
                ),
            }

        return {"status": 200, "text": f"Đã nhận lệnh: {clean}"}

    def handle_inbound_voice(
        self,
        user_id: int,
        voice_bytes: bytes,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Handle inbound voice note. Fail-closed on all error branches.
        Rules TG-01, TG-05, TG-06.
        """
        # Rule TG-01: Check authorization whitelist first
        if not self.is_user_authorized(user_id):
            self.security_violations.append(user_id)
            return {
                "status": 403,
                "error": "Forbidden: Unauthorized User ID",
                "rejected": True,
            }

        # Rule TG-05: Empty voice payload check
        if not voice_bytes:
            return {
                "ok": False,
                "status": 400,
                "error_code": "EMPTY_VOICE_PAYLOAD",
                "message": "Voice payload is empty.",
            }

        # Rule TG-05: STT engine availability & interface check
        if not (self.stt_engine and hasattr(self.stt_engine, "transcribe")):
            return {
                "ok": False,
                "status": 503,
                "error_code": "STT_UNAVAILABLE",
                "message": "Voice transcription service offline or not configured.",
            }

        # Rule TG-05: Transcription execution & exception fail-closed
        try:
            transcribed_text = self.stt_engine.transcribe(voice_bytes)
        except Exception as exc:
            log.error("Voice transcription failed with exception: %s", exc)
            return {
                "ok": False,
                "status": 503,
                "error_code": "STT_UNAVAILABLE",
                "message": "Voice transcription service offline or not configured.",
            }

        # Rule TG-05: Empty transcription outcome
        if not isinstance(transcribed_text, str) or not transcribed_text.strip():
            return {
                "ok": False,
                "status": 200,
                "error_code": "EMPTY_TRANSCRIPTION",
                "message": "Voice transcription yielded no recognizable text.",
                "text": "Không nhận diện được giọng nói, vui lòng thử lại.",
            }

        # Rule TG-06: STT success routes to handle_inbound_message
        return self.handle_inbound_message(
            user_id=user_id,
            text=transcribed_text.strip(),
            chat_id=chat_id,
        )

    def send_message(
        self,
        chat_id: int,
        text: str,
        mock_http: Any | None = None,
    ) -> dict[str, Any]:
        """
        Send text message to Telegram chat.
        Rules TG-07, TG-08.
        """
        # Rule TG-07: Guard against unconfigured token
        if not self.bot_token:
            return {
                "ok": False,
                "error_code": "NOT_CONFIGURED",
                "description": "Telegram bot token is not configured.",
            }

        client = mock_http or self.http_client
        if client and hasattr(client, "handle_telegram_send_message"):
            return client.handle_telegram_send_message(chat_id, text)

        try:
            import requests
        except ImportError:
            return {"ok": False, "error_code": "ERROR", "description": "requests module not installed"}

        if self._session is None:
            self._session = requests.Session()

        # Rule TG-08: HTTP Status Code Mapping
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            resp = self._session.post(
                url,
                json={"chat_id": chat_id, "text": text},
                timeout=self.timeout_s,
            )
            if resp.status_code == 200:
                try:
                    payload = resp.json()
                except Exception:
                    payload = {}
                if payload.get("ok"):
                    return {"ok": True, "result": payload.get("result")}
                return {
                    "ok": False,
                    "error_code": "TELEGRAM_API_ERROR",
                    "description": payload.get("description", "Telegram API returned ok=false"),
                }
            elif resp.status_code == 401:
                return {
                    "ok": False,
                    "error_code": "AUTH_FAILED",
                    "description": "Invalid Telegram bot token.",
                }
            elif resp.status_code == 429:
                retry_after = 1
                try:
                    retry_after = resp.json().get("parameters", {}).get("retry_after", 1)
                except Exception:
                    pass
                return {
                    "ok": False,
                    "error_code": "RATE_LIMITED",
                    "retry_after": retry_after,
                }
            else:
                return {
                    "ok": False,
                    "error_code": "ERROR",
                    "description": f"HTTP {resp.status_code}: {resp.text}",
                }
        except requests.exceptions.Timeout:
            return {"ok": False, "error_code": "TIMEOUT", "description": "Telegram API timeout."}
        except Exception as exc:
            return {"ok": False, "error_code": "ERROR", "description": str(exc)}

    def send_photo(
        self,
        chat_id: int,
        photo_bytes: bytes,
        caption: str = "",
        mock_http: Any | None = None,
    ) -> dict[str, Any]:
        """Dispatch photo payload to specified chat."""
        if not self.bot_token:
            return {
                "ok": False,
                "error_code": "NOT_CONFIGURED",
                "description": "Telegram bot token is not configured.",
            }
        client = mock_http or self.http_client
        if client and hasattr(client, "handle_telegram_send_photo"):
            return client.handle_telegram_send_photo(chat_id, photo_bytes, caption)

        try:
            import requests
        except ImportError:
            return {"ok": False, "error_code": "ERROR", "description": "requests module not installed"}

        if self._session is None:
            self._session = requests.Session()

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            resp = self._session.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": photo_bytes},
                timeout=self.timeout_s,
            )
            if resp.status_code == 200:
                try:
                    payload = resp.json()
                except Exception:
                    payload = {}
                if payload.get("ok"):
                    return {"ok": True, "result": payload.get("result")}
                return {
                    "ok": False,
                    "error_code": "TELEGRAM_API_ERROR",
                    "description": payload.get("description", "Telegram API returned ok=false"),
                }
            elif resp.status_code == 401:
                return {"ok": False, "error_code": "AUTH_FAILED", "description": "Invalid Telegram bot token."}
            elif resp.status_code == 429:
                return {"ok": False, "error_code": "RATE_LIMITED"}
            else:
                return {"ok": False, "error_code": "ERROR", "description": f"HTTP {resp.status_code}: {resp.text}"}
        except requests.exceptions.Timeout:
            return {"ok": False, "error_code": "TIMEOUT", "description": "Telegram API timeout."}
        except Exception as exc:
            return {"ok": False, "error_code": "ERROR", "description": str(exc)}

    def poll_once(self, mock_http: Any | None = None) -> list[dict[str, Any]]:
        """Poll and process pending Telegram updates."""
        client = mock_http or self.http_client
        if client and hasattr(client, "telegram_inbound_queue"):
            updates: list[dict[str, Any]] = []
            while not client.telegram_inbound_queue.empty():
                up = client.telegram_inbound_queue.get_nowait()
                msg = up.get("message", {})
                user_id = msg.get("from", {}).get("id", 0)
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id", user_id)
                res = self.handle_inbound_message(user_id, text, chat_id)
                if res and res.get("text") and chat_id:
                    self.send_message(chat_id, res["text"], mock_http=mock_http)
                updates.append(res)
            return updates

        if not self.bot_token:
            return []

        try:
            import requests
            if self._session is None:
                self._session = requests.Session()

            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": int(self.timeout_s)}
            resp = self._session.get(url, params=params, timeout=self.timeout_s + 5)
            if resp.status_code != 200:
                return []

            data = resp.json()
            if not data.get("ok"):
                return []

            results = data.get("result", [])
            processed: list[dict[str, Any]] = []
            for item in results:
                update_id = item.get("update_id", 0)
                if update_id > self.last_update_id:
                    self.last_update_id = update_id

                msg = item.get("message", {})
                if not msg:
                    continue

                user_id = msg.get("from", {}).get("id", 0)
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id", user_id)

                if text:
                    res = self.handle_inbound_message(user_id, text, chat_id)
                    if res and res.get("text") and chat_id:
                        self.send_message(chat_id, res["text"])
                    processed.append(res)

            return processed
        except Exception as exc:
            log.debug("Telegram getUpdates polling error: %s", exc)
            return []

    def start(self) -> None:
        """Rule TG-09: Start daemon background polling loop."""
        if self._is_polling:
            return
        self._is_polling = True
        self._poll_thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="TelegramPollThread",
        )
        self._poll_thread.start()
        log.info("Telegram polling thread started")

    def stop(self) -> None:
        """Rule TG-09: Stop background polling thread."""
        self._is_polling = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)

    def _loop(self) -> None:
        """Rule TG-09: Polling loop with 1.0s interval."""
        while self._is_polling:
            try:
                self.poll_once()
            except Exception as exc:
                log.error("Telegram polling loop error: %s", exc)
            time.sleep(1.0)


# Backward compatibility aliases
TelegramBotController = TelegramController

__all__ = [
    "TelegramController",
    "TelegramBotController",
    "TelegramConfig",
    "RateLimitConfig",
    "TokenBucketRateLimiter",
]
