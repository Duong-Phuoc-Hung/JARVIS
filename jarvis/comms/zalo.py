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
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from jarvis.comms.rate_limiter import RateLimitConfig, TokenBucketRateLimiter


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urlopen(req, timeout):
    # Never forward the access_token header to a redirect destination.
    return build_opener(_NoRedirect()).open(req, timeout=timeout)


log = logging.getLogger("jarvis.comms.zalo")

_ZALO_API_BASE = "https://openapi.zalo.me/v2.0/oa"
_ZALO_MSG_URL = "https://openapi.zalo.me/v3.0/oa/message/cs"


@dataclass
class ZaloConfig:
    access_token: str = ""
    oa_id: str = ""
    webhook_secret: str = ""
    app_id: str = ""
    webhook_max_age_s: float = 300.0
    timeout_s: float = 10.0
    whitelist_user_ids: list[str] = field(default_factory=list)
    webhook_port: int = 8765
    host: str = "127.0.0.1"
    rate_limit: RateLimitConfig = field(
        default_factory=lambda: RateLimitConfig(requests_per_minute=20, burst_limit=5)
    )


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
    http_status: int | None = None
    provider_code: int | None = None
    retry_after_s: float = 0.0


class ZaloBotController:
    """
    Zalo Official Account 2-way bot.
    Receives messages via webhook, sends replies via OA API.
    Enforces strict Fail-Close authorization and HMAC-SHA256 signature verification.
    """

    def __init__(
        self,
        config: ZaloConfig | None = None,
        is_mock: bool = False,
        rate_limit_config: RateLimitConfig | None = None,
        dispatcher: Any | None = None,
    ) -> None:
        self.config = config or ZaloConfig()
        self.is_mock = is_mock
        self.dispatcher = dispatcher
        self._running = False
        self._webhook_thread: threading.Thread | None = None
        self.sent_messages: list[dict[str, Any]] = []
        self.received_messages: list[ZaloMessage] = []
        self.evidence: list[dict[str, Any]] = []
        self._seen_events: dict[tuple, float] = {}
        self._webhook_lock = threading.Lock()
        self._server = None
        self.webhook_address = None
        self._retry_at = 0.0
        self.outbound_limiter = TokenBucketRateLimiter(
            self.config.rate_limit, channel_name="zalo_outbound"
        )
        self.security_violations: list[dict] = []
        self.rate_limiter = TokenBucketRateLimiter(
            rate_limit_config
            or (
                self.config.rate_limit
                if hasattr(self.config, "rate_limit")
                else RateLimitConfig(requests_per_minute=20, burst_limit=5)
            ),
            channel_name="zalo",
        )
        log.info("ZaloBotController initialized (mock=%s)", is_mock)

    # ------------------------------------------------------------------
    # Authorization (Fail-Close Security Model)
    # ------------------------------------------------------------------

    def is_user_authorized(self, user_id: str) -> bool:
        """
        Validate user against configured whitelist.
        Enforces Fail-Close: If whitelist is empty, all access is denied.
        """
        if not user_id:
            return False
        if not self.config.whitelist_user_ids:
            log.warning("Zalo security rejection: whitelist_user_ids is unconfigured or empty.")
            return False
        return user_id in self.config.whitelist_user_ids

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Zalo's mac=SHA256(app_id + raw body + timestamp + OA secret).

        No HMAC/base64 compatibility fallback: those are not OA signatures.
        App identity and timestamp are bound before any message is processed.
        """
        if self.is_mock:
            return True  # Explicit unit-test adapter; never used by HTTP listener.
        secret = self.config.webhook_secret.strip()
        if (
            not secret
            or not self.config.app_id
            or not isinstance(signature, str)
            or not signature.startswith("mac=")
        ):
            return False
        try:
            data = json.loads(payload)
            if not isinstance(data, dict) or data.get("app_id") != self.config.app_id:
                return False
            timestamp = data.get("timestamp")
            if not isinstance(timestamp, str) or not timestamp.isascii() or not timestamp.isdigit():
                return False
            age = time.time() - int(timestamp) / 1000.0
            if not -30 <= age <= self.config.webhook_max_age_s:
                return False
            expected = (
                "mac="
                + hashlib.sha256(
                    self.config.app_id.encode() + payload + timestamp.encode() + secret.encode()
                ).hexdigest()
            )
            return hmac.compare_digest(expected, signature)
        except (ValueError, TypeError, OverflowError):
            return False

    # ------------------------------------------------------------------
    # Message Handling
    # ------------------------------------------------------------------

    def handle_inbound_message(
        self, user_id: str, text: str, user_name: str = "User"
    ) -> dict[str, Any]:
        """Convenience method for processing inbound webhook messages with standard user info."""
        return self.handle_message(user_id=user_id, user_name=user_name, text=text)

    def handle_message(self, user_id: str, user_name: str, text: str) -> dict[str, Any]:
        """Process incoming Zalo message with redacted security audit logging and rate limiting."""
        if not self.is_user_authorized(user_id):
            sha256_prefix = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
            audit_entry = {
                "event": "UNAUTHORIZED_ZALO_ACCESS",
                "user_id": user_id,
                "user_name": user_name,
                "payload_sha256_prefix": sha256_prefix,
                "payload_length": len(text),
                "timestamp": time.time(),
            }
            self.security_violations.append(audit_entry)
            log.warning(
                "Unauthorized Zalo access rejected: user_id=%s, len=%d, hash_prefix=%s",
                user_id,
                len(text),
                sha256_prefix,
            )
            return {"status": 403, "text": "⛔ Bạn không có quyền sử dụng JARVIS qua Zalo."}

        # Token Bucket Rate Limiting per user_id
        rl = self.rate_limiter.acquire(user_id)
        if not rl.allowed:
            log.warning(
                "Zalo rate limit exceeded for user_id=%s, retry_after=%.2fs",
                user_id,
                rl.retry_after_s,
            )
            return {
                "status": 429,
                "text": f"⚠️ Yêu cầu quá nhanh. Vui lòng thử lại sau {rl.retry_after_s} giây.",
                "error": "Too Many Requests",
                "retry_after_s": rl.retry_after_s,
                "user_id": user_id,
            }

        msg = ZaloMessage(user_id=user_id, user_name=user_name, text=text, timestamp=time.time())
        if self.is_mock:
            self.received_messages.append(msg)
        else:
            self.received_messages.append(
                ZaloMessage(
                    user_id="REDACTED", user_name="REDACTED", text="", timestamp=msg.timestamp
                )
            )
        del self.received_messages[:-1000]
        cmd = text.strip()

        # ------ Command dispatch ------
        if cmd.startswith("/help") or cmd == "help":
            reply = self._cmd_help()
        elif cmd.startswith("/status") or "trạng thái" in cmd.lower():
            reply = self._cmd_status()
            if reply is None:
                return {
                    "status": 503,
                    "error_code": "STATUS_UNAVAILABLE",
                    "text": "Không thể đo trạng thái hệ thống.",
                    "user_id": user_id,
                }
        elif cmd.startswith("/briefing") or "báo cáo" in cmd.lower():
            return self._dispatch_command(user_id, "skill_briefing", {"action": "run"})
        elif cmd.startswith("/note "):
            return self._dispatch_command(user_id, "skill_note_taker", {"action": "add", "text": cmd[6:].strip()})
        elif cmd.startswith("/calc ") or cmd.startswith("/tinh "):
            expr = cmd.split(" ", 1)[-1].strip()
            return self._dispatch_command(user_id, "skill_calculator", {"action": "calculate", "expression": expr})
        elif cmd.startswith("/weather") or "thời tiết" in cmd.lower():
            return {"status": 503, "error_code": "WEATHER_UNAVAILABLE", "text": self._cmd_weather()}
        elif cmd.startswith("/screenshot") or "chụp màn hình" in cmd.lower():
            return self._dispatch_command(user_id, "skill_system_control", {"action": "screenshot"})
        elif cmd.startswith("/skills") or "kỹ năng" in cmd.lower():
            reply = self._cmd_skills()
            if reply is None:
                return {"status": 503, "error_code": "SKILLS_UNAVAILABLE", "text": "Danh sách kỹ năng chưa khả dụng."}
        else:
            # Forward to JARVIS intent router
            return self._cmd_jarvis(cmd)

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

    def _cmd_status(self) -> str | None:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            listener = "LISTENING" if self.webhook_address else "NOT_LISTENING"
            return (
                f"JARVIS CPU: {cpu:.1f}% | RAM: {ram:.1f}%\n"
                f"Webhook: {listener}; Zalo server round-trip: NOT_VERIFIED"
            )
        except Exception:
            return None




    def _cmd_weather(self) -> str:
        return "🌤️ Dịch vụ thời tiết chưa được cấu hình hoặc chưa khả dụng."


    def _cmd_skills(self) -> str | None:
        try:
            from jarvis.skills.registry import SkillRegistry

            reg = SkillRegistry()
            names = [s.name for s in reg.list_skills()]
            return "🧰 *Kỹ năng hiện có:*\n" + "\n".join(f"• {n}" for n in names[:15])
        except Exception:
            return None

    def _dispatch_command(self, user_id: str, action: str, payload: dict) -> dict[str, Any]:
        from jarvis.core.dispatcher import ActionDispatcher
        from jarvis.core.models import RequesterContext

        if not isinstance(self.dispatcher, ActionDispatcher):
            return {"status": 503, "error_code": "DISPATCHER_UNAVAILABLE", "text": "DISPATCHER_UNAVAILABLE"}
        try:
            result = self.dispatcher.dispatch_action(
                action, payload, requester=RequesterContext.user(f"zalo:{user_id}", authenticated=True)
            )
        except Exception:
            return {"status": 503, "error_code": "DISPATCH_FAILED", "text": "DISPATCH_FAILED"}
        code = result.error_code or result.code
        # Never send local confirmation tokens or raw exception/action data to a channel.
        if not result.success:
            return {"status": 409 if code == "CONFIRMATION_REQUIRED" else 503,
                    "error_code": code, "text": code}
        text = "ACTION_COMPLETED"
        if action in {"skill_calculator", "skill_briefing"} and isinstance(result.data, dict):
            text = str(result.data.get("output") or result.data.get("text") or text)[:2000]
        return {"status": 200, "text": text, "user_id": user_id}

    def _cmd_jarvis(self, text: str) -> dict[str, Any]:
        try:
            from jarvis.llm.client import LLMClient

            result = LLMClient().generate(text)
            if result.success and result.content and not result.error:
                return {"status": 200, "text": result.content}
        except Exception:
            pass
        return {"status": 503, "error_code": "LLM_UNAVAILABLE", "text": "LLM_UNAVAILABLE"}

    # ------------------------------------------------------------------
    # Send API
    # ------------------------------------------------------------------

    def send_message(self, user_id: str, text: str) -> ZaloSendResult:
        if self.is_mock:
            self.sent_messages.append({"user_id": user_id, "text": text, "timestamp": time.time()})
            return ZaloSendResult(success=True, message_id="mock_msg_id")
        result = self._send_text(user_id, text)
        evidence = {
            "direction": "outbound",
            "timestamp": time.time(),
            "http_status": result.http_status,
            "success": result.success,
            "error_code": result.error,
            "provider_code": result.provider_code,
            "message_id": result.message_id,
        }
        self.sent_messages.append(evidence)
        self.evidence.append(evidence)
        del self.sent_messages[:-1000]
        del self.evidence[:-1000]
        return result

    def _send_text(self, user_id: str, text: str) -> ZaloSendResult:
        token = self.config.access_token.strip()
        if not token:
            return ZaloSendResult(False, "NOT_CONFIGURED")
        if not self.is_user_authorized(user_id):
            return ZaloSendResult(False, "RECIPIENT_NOT_ALLOWED")
        if not isinstance(text, str) or not text or len(text) > 2000:
            return ZaloSendResult(False, "INVALID_TEXT")
        if time.monotonic() < self._retry_at:
            return ZaloSendResult(
                False, "RATE_LIMITED", retry_after_s=self._retry_at - time.monotonic()
            )
        limit = self.outbound_limiter.acquire(user_id)
        if not limit.allowed:
            return ZaloSendResult(False, "RATE_LIMITED", retry_after_s=limit.retry_after_s)
        status = None
        try:
            payload = json.dumps(
                {"recipient": {"user_id": user_id}, "message": {"text": text}}, ensure_ascii=False
            ).encode("utf-8")
            req = Request(
                _ZALO_MSG_URL,
                data=payload,
                headers={"Content-Type": "application/json", "access_token": token},
            )
            with urlopen(req, timeout=self.config.timeout_s) as resp:
                status = resp.status
                data = json.loads(resp.read())
            if status != 200 or not isinstance(data, dict) or type(data.get("error")) is not int:
                return ZaloSendResult(False, "INVALID_RESPONSE", http_status=status)
            code = data["error"]
            if code != 0:
                return ZaloSendResult(
                    False,
                    "AUTH_FAILED" if code == -124 else "API_ERROR",
                    http_status=status,
                    provider_code=code,
                )
            msg = data.get("data", {}).get("message_id")
            if not isinstance(msg, str) or not msg.strip():
                return ZaloSendResult(False, "INVALID_RESPONSE", http_status=status)
            return ZaloSendResult(True, message_id=msg, http_status=status, provider_code=0)
        except HTTPError as exc:
            status = exc.code
            if status == 429:
                try:
                    delay = max(1.0, min(float(exc.headers.get("Retry-After", 1)), 3600.0))
                except (ValueError, TypeError, AttributeError):
                    delay = 1.0
                self._retry_at = time.monotonic() + delay
                return ZaloSendResult(
                    False, "RATE_LIMITED", http_status=status, retry_after_s=delay
                )
            return ZaloSendResult(
                False, "AUTH_FAILED" if status in (401, 403) else "HTTP_ERROR", http_status=status
            )
        except TimeoutError:
            return ZaloSendResult(False, "TIMEOUT", http_status=status)
        except URLError as exc:
            return ZaloSendResult(
                False,
                "TIMEOUT" if isinstance(exc.reason, TimeoutError) else "OFFLINE",
                http_status=status,
            )
        except (ValueError, TypeError, AttributeError):
            return ZaloSendResult(False, "INVALID_RESPONSE", http_status=status)
        except Exception:
            return ZaloSendResult(False, "TRANSPORT_ERROR", http_status=status)

    def send_image(self, user_id: str, image_path: str, caption: str = "") -> ZaloSendResult:
        """Send image file to user (mock: just logs)."""
        if self.is_mock:
            self.sent_messages.append({"user_id": user_id, "image": image_path, "caption": caption})
            return ZaloSendResult(success=True, message_id="mock_img_id")
        token = (self.config.access_token or "").strip()
        if not token:
            log.warning("Zalo send_image rejected: access_token not configured")
            return ZaloSendResult(success=False, error="NOT_CONFIGURED")
        log.warning("Zalo send_image rejected: image upload API is not implemented")
        return ZaloSendResult(success=False, error="IMAGE_SEND_NOT_IMPLEMENTED")

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

    def handle_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        """Authenticate before routing. Duplicate events never re-run commands."""
        if len(payload) > 1_048_576:
            return {"status": 413, "error_code": "PAYLOAD_TOO_LARGE"}
        if self.is_mock or not self.verify_webhook_signature(payload, signature):
            return {"status": 403, "error_code": "INVALID_SIGNATURE"}
        data = json.loads(payload)
        recipient = data.get("recipient") or {}
        sender = data.get("sender") or {}
        message = data.get("message") or {}
        if not all(isinstance(v, dict) for v in (recipient, sender, message)):
            return {"status": 400, "error_code": "INVALID_PAYLOAD"}
        if not self.config.oa_id or recipient.get("id") != self.config.oa_id:
            return {"status": 403, "error_code": "WRONG_OA"}
        if data.get("event_name") != "user_send_text":
            return {"status": 200, "ignored": True}
        uid = sender.get("id")
        text = message.get("text")
        mid = message.get("msg_id")
        if not self.is_user_authorized(uid):
            return {"status": 403, "error_code": "SENDER_NOT_ALLOWED"}
        if not isinstance(text, str) or not isinstance(mid, str) or not mid:
            return {"status": 400, "error_code": "INVALID_MESSAGE"}
        with self._webhook_lock:
            now = time.time()
            self._seen_events = {
                k: v
                for k, v in self._seen_events.items()
                if now - v <= self.config.webhook_max_age_s + 30
            }
            key = (uid, mid)
            if key in self._seen_events:
                return {"status": 200, "duplicate": True}
            if len(self._seen_events) >= 10000:
                return {"status": 503, "error_code": "REPLAY_CACHE_FULL"}
            self._seen_events[key] = now
            outcome = self.handle_message(uid, "", text)
            outcome["message_id"] = mid
            self.evidence.append(
                {
                    "direction": "inbound",
                    "timestamp": now,
                    "http_status": outcome["status"],
                    "message_id": mid,
                    "processing_status": outcome["status"],
                    "signature_verified": True,
                }
            )
            del self.evidence[:-1000]
            return outcome

    def start_webhook(self) -> bool:
        """Bind synchronously so READY is reported only for a listening socket."""
        if self._running:
            return True
        if self.is_mock:
            self._running = True
            return True  # No listening socket in explicit mock mode.
        if (
            not self.config.app_id
            or not self.config.oa_id
            or not self.config.webhook_secret.strip()
        ):
            return False
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        controller = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.path != "/zalo/webhook":
                    self.send_error(404)
                    return
                try:
                    self.connection.settimeout(5)
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1_048_576:
                        self.send_error(413)
                        return
                    body = self.rfile.read(length)
                    outcome = controller.handle_webhook(
                        body, self.headers.get("X-ZEvent-Signature", "")
                    )
                    status = outcome["status"]
                    if status == 200 and outcome.get("text"):
                        sent = controller.send_message(outcome["user_id"], outcome["text"])
                        if not sent.success:
                            status = 503
                    response = json.dumps(
                        {
                            "status": status,
                            "duplicate": outcome.get("duplicate", False),
                            "error_code": outcome.get("error_code"),
                        }
                    ).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
                except (ValueError, OSError, TypeError):
                    self.send_error(400)

        try:
            self._server = ThreadingHTTPServer(
                (self.config.host, self.config.webhook_port), Handler
            )
            self.webhook_address = self._server.server_address
            self._running = True
            self._webhook_thread = threading.Thread(
                target=self._server.serve_forever, daemon=True, name="ZaloWebhook"
            )
            self._webhook_thread.start()
            return True
        except OSError:
            self._running = False
            return False

    def stop_webhook(self) -> None:
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._webhook_thread:
            self._webhook_thread.join(timeout=2)
        self.webhook_address = None


__all__ = ["ZaloBotController", "ZaloConfig", "ZaloMessage", "ZaloSendResult"]
