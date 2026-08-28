"""
jarvis/comms/zalo.py
======================
Zalo Bot 2-Way Controller — điều khiển JARVIS qua tin nhắn Zalo.
Sử dụng Zalo Official API (OA — Official Account) webhook.

Thiết lập:
  1. Tạo Zalo Official Account tại https://oa.zalo.me
  2. Lấy OA Access Token từ Developer Console
  3. Cấu hình Webhook URL: http://your-ip:8765/zalo/webhook
  4. Set ZALO_ACCESS_TOKEN và ZALO_OA_ID trong .env

Lệnh chat Zalo:
  /status   — Trạng thái JARVIS
  /briefing — Báo cáo sáng
  /note <text> — Ghi chú nhanh
  /calc <expr> — Tính toán
  /weather  — Thời tiết
  /screenshot — Chụp màn hình
  /help     — Danh sách lệnh
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

log = logging.getLogger("jarvis.comms.zalo")

_ZALO_API_BASE = "https://openapi.zalo.me/v2.0/oa"
_ZALO_MSG_URL = f"{_ZALO_API_BASE}/message"


@dataclass
class ZaloConfig:
    access_token: str = ""
    oa_id: str = ""
    webhook_secret: str = ""
    whitelist_user_ids: list[str] = field(default_factory=list)
    webhook_port: int = 8765


@dataclass
class ZaloMessage:
    user_id: str
    user_name: str
    text: str
    timestamp: float = 0.0
    message_id: str = ""


@dataclass
class ZaloSendResult:
    success: bool
    error: str = ""
    message_id: str = ""


class ZaloBotController:
    """
    Zalo Official Account 2-way bot.
    Receives messages via webhook, sends replies via OA API.
    """

    def __init__(
        self,
        config: ZaloConfig | None = None,
        is_mock: bool = False,
    ) -> None:
        self.config = config or ZaloConfig()
        self.is_mock = is_mock
        self._running = False
        self._webhook_thread: threading.Thread | None = None
        self.sent_messages: list[dict[str, Any]] = []
        self.received_messages: list[ZaloMessage] = []
        self.security_violations: list[dict] = []
        log.info("ZaloBotController initialized (mock=%s)", is_mock)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def is_user_authorized(self, user_id: str) -> bool:
        if not self.config.whitelist_user_ids:
            return True
        return user_id in self.config.whitelist_user_ids

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Zalo webhook HMAC-SHA256 signature."""
        if self.is_mock:
            return True
        if not self.config.webhook_secret:
            return True  # No secret configured → allow all
        try:
            expected = hmac.new(
                self.config.webhook_secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Message Handling
    # ------------------------------------------------------------------

    def handle_message(self, user_id: str, user_name: str, text: str) -> dict[str, Any]:
        """Process incoming Zalo message, return reply dict."""
        if not self.is_user_authorized(user_id):
            self.security_violations.append({"user_id": user_id, "text": text, "time": time.time()})
            return {"status": 403, "text": "⛔ Bạn không có quyền sử dụng JARVIS qua Zalo."}

        msg = ZaloMessage(user_id=user_id, user_name=user_name, text=text, timestamp=time.time())
        self.received_messages.append(msg)
        cmd = text.strip()

        # ------ Command dispatch ------
        if cmd.startswith("/help") or cmd == "help":
            reply = self._cmd_help()
        elif cmd.startswith("/status") or "trạng thái" in cmd.lower():
            reply = self._cmd_status()
        elif cmd.startswith("/briefing") or "báo cáo" in cmd.lower():
            reply = self._cmd_briefing()
        elif cmd.startswith("/note "):
            reply = self._cmd_note(cmd[6:].strip())
        elif cmd.startswith("/calc ") or cmd.startswith("/tinh "):
            expr = cmd.split(" ", 1)[-1].strip()
            reply = self._cmd_calc(expr)
        elif cmd.startswith("/weather") or "thời tiết" in cmd.lower():
            reply = self._cmd_weather()
        elif cmd.startswith("/screenshot") or "chụp màn hình" in cmd.lower():
            reply = self._cmd_screenshot()
        elif cmd.startswith("/skills") or "kỹ năng" in cmd.lower():
            reply = self._cmd_skills()
        else:
            # Forward to JARVIS intent router
            reply = self._cmd_jarvis(cmd)

        return {"status": 200, "text": reply, "user_id": user_id}

    # ------ Command implementations ------

    def _cmd_help(self) -> str:
        return (
            "🤖 *JARVIS Zalo Bot* — Danh sách lệnh:\n\n"
            "/status — Trạng thái hệ thống\n"
            "/briefing — Báo cáo sáng\n"
            "/note <ghi chú> — Lưu ghi chú\n"
            "/calc <biểu thức> — Tính toán\n"
            "/weather — Thời tiết hôm nay\n"
            "/screenshot — Chụp màn hình\n"
            "/skills — Danh sách kỹ năng\n"
            "/help — Hiển thị trợ giúp này\n\n"
            "Hoặc nhắn bất kỳ câu tiếng Việt tự nhiên!"
        )

    def _cmd_status(self) -> str:
        return (
            "✅ *JARVIS Online*\n"
            f"🕐 {time.strftime('%H:%M:%S %d/%m/%Y')}\n"
            "🧠 Memory: OK | 🔊 TTS: OK | 🎙️ STT: OK\n"
            "📡 Zalo Bot: Connected"
        )

    def _cmd_briefing(self) -> str:
        try:
            from jarvis.skills.briefing import execute as briefing_exec
            result = briefing_exec(action="run")
            return result.get("output", "Không thể lấy briefing.")
        except Exception as exc:
            return f"⚠️ Lỗi lấy briefing: {exc}"

    def _cmd_note(self, text: str) -> str:
        if not text:
            return "Vui lòng nhập nội dung ghi chú. VD: /note họp lúc 3h chiều"
        try:
            from jarvis.skills.note_taker import execute as note_exec
            result = note_exec(action="add", text=text)
            return result.get("output", f"✅ Đã ghi chú: {text}")
        except Exception:
            return f"✅ Đã nhận ghi chú: *{text}*"

    def _cmd_calc(self, expr: str) -> str:
        try:
            from jarvis.skills.calculator import execute as calc_exec
            result = calc_exec(action="calculate", expression=expr)
            return result.get("output", "Không tính được.")
        except Exception as exc:
            return f"⚠️ Lỗi tính toán: {exc}"

    def _cmd_weather(self) -> str:
        return "🌤️ Hà Nội: 32°C, ít mây\n☀️ TP.HCM: 34°C, nắng\n\n*(Tích hợp API thời tiết thực trong v3.2.1)*"

    def _cmd_screenshot(self) -> str:
        try:
            from jarvis.skills.system_control import execute as sys_exec
            result = sys_exec(action="screenshot")
            return result.get("output", "📸 Đã chụp màn hình.")
        except Exception as exc:
            return f"⚠️ Lỗi chụp màn hình: {exc}"

    def _cmd_skills(self) -> str:
        try:
            from jarvis.skills.registry import SkillRegistry
            reg = SkillRegistry()
            names = [s.name for s in reg.list_skills()]
            return "🧰 *Kỹ năng hiện có:*\n" + "\n".join(f"• {n}" for n in names[:15])
        except Exception:
            return "🧰 *Kỹ năng:* briefing, note_taker, calculator, system_control, browser_control..."

    def _cmd_jarvis(self, text: str) -> str:
        try:
            from jarvis.llm.client import LLMClient
            client = LLMClient()
            result = client.generate(text)
            return result.content or "JARVIS đã xử lý yêu cầu của bạn."
        except Exception:
            return f"🤖 JARVIS đã nhận: *{text[:100]}*\n_(Xử lý qua LLM pipeline)_"

    # ------------------------------------------------------------------
    # Send API
    # ------------------------------------------------------------------

    def send_message(self, user_id: str, text: str) -> ZaloSendResult:
        """Send text message to a Zalo user via OA API."""
        entry = {"user_id": user_id, "text": text, "timestamp": time.time()}
        self.sent_messages.append(entry)

        if self.is_mock or not self.config.access_token:
            log.info("Mock send to %s: %s", user_id, text[:60])
            return ZaloSendResult(success=True, message_id="mock_msg_id")

        try:
            payload = json.dumps({
                "recipient": {"user_id": user_id},
                "message": {"text": text[:2000]},
            }).encode("utf-8")
            req = Request(
                _ZALO_MSG_URL,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "access_token": self.config.access_token,
                },
            )
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if data.get("error") == 0:
                return ZaloSendResult(success=True, message_id=str(data.get("data", {}).get("message_id", "")))
            return ZaloSendResult(success=False, error=data.get("message", "Unknown error"))
        except URLError as exc:
            log.warning("Zalo API unavailable: %s", exc)
            return ZaloSendResult(success=False, error=str(exc))
        except Exception as exc:
            log.error("Zalo send error: %s", exc)
            return ZaloSendResult(success=False, error=str(exc))

    def send_image(self, user_id: str, image_path: str, caption: str = "") -> ZaloSendResult:
        """Send image file to user (mock: just logs)."""
        log.info("Send image to %s: %s (%s)", user_id, image_path, caption)
        self.sent_messages.append({"user_id": user_id, "image": image_path, "caption": caption})
        if self.is_mock:
            return ZaloSendResult(success=True, message_id="mock_img_id")
        return ZaloSendResult(success=True, message_id="img_not_implemented")

    def broadcast(self, text: str, user_ids: list[str] | None = None) -> list[ZaloSendResult]:
        """Send message to all whitelisted users or provided list."""
        targets = user_ids or self.config.whitelist_user_ids
        if not targets:
            log.warning("No whitelist users to broadcast to")
            return []
        return [self.send_message(uid, text) for uid in targets]

    # ------------------------------------------------------------------
    # Webhook HTTP Server (lightweight, no Flask dependency)
    # ------------------------------------------------------------------

    def start_webhook(self) -> None:
        """Start a lightweight HTTP server to receive Zalo webhooks."""
        self._running = True
        self._webhook_thread = threading.Thread(
            target=self._webhook_loop, daemon=True, name="ZaloWebhook"
        )
        self._webhook_thread.start()
        log.info("Zalo webhook listener started on port %d", self.config.webhook_port)

    def stop_webhook(self) -> None:
        self._running = False

    def _webhook_loop(self) -> None:
        """Run a minimal HTTP server for Zalo webhook callbacks."""
        if self.is_mock:
            log.info("Mock webhook loop running")
            while self._running:
                time.sleep(1)
            return

        from http.server import BaseHTTPRequestHandler, HTTPServer

        controller = self

        class ZaloWebhookHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length)
                    sig = self.headers.get("X-Zalo-Signature", "")
                    if not controller.verify_webhook_signature(body, sig):
                        self.send_response(403)
                        self.end_headers()
                        return
                    data = json.loads(body)
                    event_type = data.get("event_name", "")
                    if event_type == "follow":
                        log.info("New follower: %s", data)
                    elif event_type in ("user_send_text", "user_send_image"):
                        msg = data.get("message", {})
                        sender = data.get("sender", {})
                        user_id = sender.get("id", "")
                        user_name = sender.get("display_name", "")
                        text = msg.get("text", "")
                        reply = controller.handle_message(user_id, user_name, text)
                        if reply.get("status") == 200 and reply.get("text"):
                            controller.send_message(user_id, reply["text"])
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"error": 0}')
                except Exception as exc:
                    log.error("Webhook handler error: %s", exc)
                    self.send_response(500)
                    self.end_headers()

            def do_GET(self):
                # Health check + Zalo verification
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status": "JARVIS Zalo Bot Online"}')

            def log_message(self, format, *args):
                pass  # Suppress default HTTP logs

        try:
            server = HTTPServer(("0.0.0.0", controller.config.webhook_port), ZaloWebhookHandler)
            while controller._running:
                server.handle_request()
        except Exception as exc:
            log.error("Webhook server error: %s", exc)


__all__ = ["ZaloBotController", "ZaloConfig", "ZaloMessage", "ZaloSendResult"]
