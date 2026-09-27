"""
jarvis/comms/discord.py
=======================
Full Discord Bot Controller with 2-way JARVIS control.
Supports text commands, rich embeds, screenshots, and security whitelist.

Commands:
  !status       — System health check
  !briefing     — Morning briefing summary
  !skills       — List available JARVIS skills
  !note <text>  — Save a quick note
  !calc <expr>  — Calculate expression
  !screenshot   — Take and send screenshot
  !macro <name> — Run a saved macro
  !help         — Command reference
  !exec <cmd>   — Execute skill/action (advanced)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jarvis.comms.rate_limiter import RateLimitConfig, TokenBucketRateLimiter

log = logging.getLogger("jarvis.comms.discord")


@dataclass
class DiscordConfig:
    bot_token: str = ""
    whitelist_user_ids: list[int] = field(default_factory=list)
    admin_user_ids: list[int] = field(default_factory=list)
    guild_id: int | None = None
    default_channel_id: int | None = None
    enabled: bool = True
    rate_limit_s: float = 1.0
    rate_limit: RateLimitConfig = field(
        default_factory=lambda: RateLimitConfig(requests_per_minute=30, burst_limit=10)
    )
    poll_interval_s: float = 2.0
    consecutive_error_threshold: int = 5


@dataclass
class DiscordEmbed:
    title: str = ""
    description: str = ""
    color: int = 0x00FF88  # JARVIS green
    fields: list[dict[str, Any]] = field(default_factory=list)

    def add_field(self, name: str, value: str, inline: bool = False) -> DiscordEmbed:
        self.fields.append({"name": name, "value": value, "inline": inline})
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "color": self.color,
            "fields": self.fields,
        }


class DiscordBotController:
    """
    Full Discord bot controller with JARVIS 2-way command processing.
    Mirrors Telegram functionality with Discord-native rich embeds and slash commands.
    """

    def __init__(
        self,
        bot_token: str = "",
        whitelist_user_ids: list[int] | None = None,
        guild_id: int | None = None,
        channel_id: int | None = None,
        dispatcher: Callable | None = None,
        http_client: Any | None = None,
        rate_limiter: Any | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        config: DiscordConfig | None = None,
        poll_interval_s: float = 2.0,
        consecutive_error_threshold: int = 5,
        message_handler: Callable | None = None,
        admin_user_ids: list[int] | None = None,
    ) -> None:
        self.enabled = config.enabled if config else True
        self.bot_token = bot_token or (config.bot_token if config else "")
        raw_whitelist = whitelist_user_ids or (config.whitelist_user_ids if config else [])
        self.whitelist: list[int] = []
        for uid in raw_whitelist:
            try:
                u_int = int(uid)
                if u_int > 0:
                    self.whitelist.append(u_int)
            except (ValueError, TypeError):
                pass
        raw_admins = (
            admin_user_ids
            if admin_user_ids is not None
            else (getattr(config, "admin_user_ids", None) if config else None)
        )
        self.admin_user_ids: list[int] = []
        if raw_admins is not None:
            for uid in raw_admins:
                try:
                    u_int = int(uid)
                    if u_int > 0:
                        self.admin_user_ids.append(u_int)
                except (ValueError, TypeError):
                    pass
        self.guild_id = guild_id or (config.guild_id if config else None)
        self.default_channel_id = channel_id or (config.default_channel_id if config else None)
        self.dispatcher = dispatcher
        self._http = http_client
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter(
            rate_limit_config
            or (
                config.rate_limit
                if config
                else RateLimitConfig(requests_per_minute=30, burst_limit=10)
            ),
            channel_name="discord",
        )
        self._transport_lock = threading.RLock()
        self._poll_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._retry_at = 0.0
        self._channel_verified = False
        self._bootstrapped = False
        self.last_poll_status = {"success": False, "error_code": "NOT_STARTED"}
        self.sent_messages: list[dict[str, Any]] = []
        self.security_violations: list[dict[str, Any]] = []
        self._running = False
        self._poll_thread: threading.Thread | None = None
        self._last_message_id: str | None = None
        self.poll_interval_s: float = float(
            poll_interval_s
            if poll_interval_s is not None
            else (config.poll_interval_s if config and config.poll_interval_s is not None else 2.0)
        )
        self.consecutive_error_threshold: int = int(
            consecutive_error_threshold
            if consecutive_error_threshold is not None
            else (
                config.consecutive_error_threshold
                if config and config.consecutive_error_threshold is not None
                else 5
            )
        )
        self.consecutive_errors: int = 0
        self._stop_event: threading.Event = threading.Event()
        self.message_handler: Callable | None = message_handler
        log.info(
            "DiscordBotController initialized (token=%s, whitelist=%d users, rate_limiter=%s)",
            "set" if bot_token else "not_set",
            len(self.whitelist),
            "set" if rate_limiter else "none",
        )

    # ------------------------------------------------------------------
    # Security (Fail-Close Model)
    # ------------------------------------------------------------------

    def is_user_authorized(self, user_id: int) -> bool:
        """
        Validate user against configured Discord whitelist.
        Enforces Fail-Close: If whitelist is unconfigured/empty, all requests are rejected.
        """
        try:
            u_int = int(user_id) if user_id is not None else 0
        except (ValueError, TypeError):
            return False
        if u_int <= 0:
            return False
        if not self.whitelist:
            log.warning("Discord security rejection: whitelist is unconfigured or empty.")
            return False
        return u_int in self.whitelist

    def is_admin(self, user_id: int) -> bool:
        """Validate if user has admin privileges for sensitive commands."""
        try:
            u_int = int(user_id) if user_id is not None else 0
        except (ValueError, TypeError):
            return False
        if self.admin_user_ids:
            return u_int in self.admin_user_ids
        return False

    # ------------------------------------------------------------------
    # Message Handling
    # ------------------------------------------------------------------

    def handle_message(
        self,
        user_id: int,
        username: str,
        content: str,
        channel_id: int = 0,
    ) -> dict[str, Any]:
        """
        Process an incoming Discord message and return a response dict.
        Response: {"status": 200, "text": str, "embed": dict|None}
        """
        if self.default_channel_id and str(channel_id) != str(self.default_channel_id):
            return {"status": 403, "text": "CHANNEL_NOT_ALLOWED", "embed": None}
        if not self.is_user_authorized(user_id):
            import hashlib

            sha256_prefix = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[
                :12
            ]
            audit_entry = {
                "event": "UNAUTHORIZED_DISCORD_ACCESS",
                "user_id": user_id,
                "username": username,
                "payload_sha256_prefix": sha256_prefix,
                "payload_length": len(content),
                "timestamp": time.time(),
            }
            self.security_violations.append(audit_entry)
            log.warning(
                "Unauthorized Discord user rejected: %s (ID=%d, len=%d, hash_prefix=%s)",
                username,
                user_id,
                len(content),
                sha256_prefix,
            )
            return {
                "status": 403,
                "text": "⛔ Bạn không có quyền điều khiển JARVIS.",
                "embed": None,
            }

        # Rate Limiting check per user_id
        if self.rate_limiter is not None:
            allowed, retry_after = self.rate_limiter.acquire(user_id)
            if not allowed:
                return {
                    "status": 429,
                    "text": f"⏳ Quá nhiều yêu cầu. Vui lòng thử lại sau {retry_after:.1f}s.",
                    "retry_after": retry_after,
                    "embed": None,
                }

        content = content.strip()

        # Command dispatch supporting both '/' and '!' prefixes
        if content.startswith(("/", "!")):
            cmd_body = content[1:].strip()
            cmd_parts = cmd_body.split(None, 1)
            cmd_name = cmd_parts[0].lower() if cmd_parts else ""
            cmd_args = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

            if cmd_name in ("help", "trogiup"):
                return self._cmd_help()
            if cmd_name in ("status", "health", "trangthai"):
                return self._cmd_status()
            if cmd_name in ("briefing", "brief"):
                return self._cmd_briefing()
            if cmd_name in ("skills", "kynang"):
                return self._cmd_skills()
            if cmd_name == "calc":
                return self._cmd_calc(cmd_args)
            if cmd_name in ("exec", "macro", "screenshot", "note"):
                if not self.is_admin(user_id):
                    return {"status": 403, "text": "PERMISSION_DENIED", "embed": None}
                if cmd_name == "exec":
                    parts = cmd_args.split(None, 1)
                    try:
                        action = parts[0]
                        payload = json.loads(parts[1]) if len(parts) > 1 else {}
                        if not isinstance(payload, dict):
                            raise ValueError()
                    except (ValueError, IndexError):
                        return {"status": 400, "text": "INVALID_COMMAND", "embed": None}
                elif cmd_name == "macro":
                    action, payload = "macro_play", {"name": cmd_args}
                elif cmd_name == "screenshot":
                    action, payload = "screenshot", {}
                else:
                    if not cmd_args:
                        return {"status": 400, "text": "EMPTY_NOTE", "embed": None}
                    action, payload = "note_add", {"content": cmd_args}
                return self._dispatch_command(user_id, action, payload)

        # Arbitrary callbacks/natural-language routes lack a verifiable safety contract.
        return {"status": 403, "text": "EXPLICIT_COMMAND_REQUIRED", "embed": None}

    def _dispatch_command(self, user_id: int, action: str, payload: dict) -> dict:
        from jarvis.core.dispatcher import ActionDispatcher
        from jarvis.core.models import RequesterContext

        dispatcher = self.dispatcher
        if not isinstance(dispatcher, ActionDispatcher):
            dispatcher = getattr(dispatcher, "__self__", None)
        if not isinstance(dispatcher, ActionDispatcher):
            return {
                "status": 503,
                "text": "DISPATCHER_UNAVAILABLE",
                "error_code": "DISPATCHER_UNAVAILABLE",
                "embed": None,
            }
        try:
            result = dispatcher.dispatch_action(
                action,
                payload,
                requester=RequesterContext.user(f"discord:{user_id}", authenticated=True),
            )
        except Exception:
            return {"status": 500, "text": "DISPATCH_FAILED", "embed": None}
        # Confirmation stays on the trusted local host. Never echo tokens, arbitrary
        # action results (screenshots/secrets), or handler exceptions to the channel.
        code = result.error_code or result.code
        return {
            "status": 200 if result.success else 409 if code == "CONFIRMATION_REQUIRED" else 503,
            "text": "ACTION_COMPLETED" if result.success else code,
            "error_code": None if result.success else code,
            "embed": None,
        }

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _cmd_help(self) -> dict[str, Any]:
        embed = DiscordEmbed(
            title="🤖 JARVIS Discord Controller", description="Danh sách lệnh điều khiển:"
        )
        embed.add_field("/status, !status", "Kiểm tra sức khỏe hệ thống", True)
        embed.add_field("/briefing, !briefing", "Báo cáo sáng tổng hợp", True)
        embed.add_field("/skills, !skills", "Danh sách kỹ năng", True)
        embed.add_field("/note <text>, !note", "Lưu ghi chú nhanh", True)
        embed.add_field("/calc <expr>, !calc", "Tính toán biểu thức", True)
        embed.add_field("/screenshot, !screenshot", "Chụp và gửi màn hình", True)
        embed.add_field("/macro <name>, !macro", "Phát lại macro đã lưu", True)
        embed.add_field("/exec <cmd>, !exec", "Thực thi kỹ năng/lệnh", True)
        return {"status": 200, "text": "📋 Danh sách lệnh JARVIS:", "embed": embed.to_dict()}

    def _cmd_status(self) -> dict[str, Any]:
        try:
            from jarvis.core.health import HealthChecker

            checker = HealthChecker()
            results = checker.run_checks()
            ready = sum(1 for r in results.values() if r.get("status") == "ready")
            total = len(results)
            text = f"✅ JARVIS Online: {ready}/{total} phân hệ sẵn sàng"
        except Exception:
            text = "✅ JARVIS Online (health check không khả dụng)"
        embed = DiscordEmbed(title="🟢 JARVIS System Status", description=text)
        return {"status": 200, "text": text, "embed": embed.to_dict()}

    def _cmd_briefing(self) -> dict[str, Any]:
        try:
            from jarvis.skills import registry

            reg = registry.SkillRegistry()
            result = reg.invoke_skill("briefing", action="full")
            text = (
                result.get("output", "Không thể tải briefing.")
                if isinstance(result, dict)
                else str(result)
            )
        except Exception as exc:
            log.warning("Briefing command failed")
            text = "Briefing hiện tại không khả dụng."
        return {"status": 200, "text": f"📰 {text[:1800]}", "embed": None}

    def _cmd_skills(self) -> dict[str, Any]:
        try:
            from jarvis.skills import registry

            reg = registry.SkillRegistry()
            skills = reg.list_skills()
            names = [s.name for s in skills]
            text = "🧰 **Kỹ năng:** " + ", ".join(f"`{n}`" for n in names)
        except Exception as exc:
            log.warning("Skills command failed")
            text = "Không thể lấy danh sách kỹ năng vào lúc này."
        return {"status": 200, "text": text[:1800], "embed": None}

    def _cmd_calc(self, expr: str) -> dict[str, Any]:
        if not expr:
            return {
                "status": 400,
                "text": "⚠️ Nhập biểu thức sau `/calc` hoặc `!calc`.",
                "embed": None,
            }
        try:
            from jarvis.skills import registry

            reg = registry.SkillRegistry()
            result = reg.invoke_skill("calculator", expression=expr)
            text = result.get("output", str(result)) if isinstance(result, dict) else str(result)
        except Exception as exc:
            log.warning("Calc command failed")
            text = "Biểu thức không hợp lệ hoặc xảy ra lỗi tính toán."
        return {"status": 200, "text": f"🔢 {text}", "embed": None}

    def summarize_channel(self, channel_name: str, messages: list[str]) -> str:
        """Summarize activity from a Discord channel."""
        if not messages:
            return f"Kênh {channel_name}: không có hoạt động mới."
        n = len(messages)
        snippet = "; ".join(str(m) for m in messages[:3])
        return f"Kênh {channel_name} có {n} tin nhắn mới: {snippet}"

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    @staticmethod
    def _snowflake(value) -> bool:
        text = str(value)
        return text.isascii() and text.isdigit() and 0 < len(text) <= 20 and 0 < int(text) < 2**64

    @staticmethod
    def _failure(code: str, http_status: int | None = None) -> dict:
        return {"success": False, "error_code": code, "http_status": http_status}

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        import requests

        with self._transport_lock:
            if not self.bot_token:
                return self._failure("NOT_CONFIGURED")
            if time.monotonic() < self._retry_at:
                return self._failure("RATE_LIMITED", 429)
            try:
                client = self._http if self._http is not None else requests
                response = client.request(
                    method,
                    "https://discord.com/api/v10" + path,
                    headers={"Authorization": f"Bot {self.bot_token}"},
                    json=payload,
                    timeout=10,
                    allow_redirects=False,
                )
                status = response.status_code
                try:
                    data = response.json()
                except Exception:
                    data = None
                if status == 429:
                    try:
                        delay = float(data.get("retry_after", 1))
                        if not 0 < delay < float("inf"):
                            delay = 60.0
                    except (ValueError, TypeError, AttributeError):
                        delay = 60.0
                    self._retry_at = time.monotonic() + max(1.0, delay)
                if not 200 <= status < 300:
                    return self._failure(
                        "RATE_LIMITED" if status == 429 else f"HTTP_{status}", status
                    )
                return {"success": True, "http_status": status, "data": data}
            except (requests.Timeout, TimeoutError):
                return self._failure("TIMEOUT")
            except Exception:
                return self._failure("CONNECTION_FAILED")

    def _ensure_channel(self, channel_id) -> dict:
        if not self.enabled:
            return self._failure("DISABLED")
        if not self.bot_token:
            return self._failure("NOT_CONFIGURED")
        if not self.guild_id or not self.default_channel_id:
            return self._failure("PENDING_GUILD_CHANNEL")
        if str(channel_id) != str(self.default_channel_id) or not self._snowflake(channel_id):
            return self._failure("CHANNEL_NOT_ALLOWED")
        if not self._channel_verified:
            result = self._request("GET", f"/channels/{channel_id}")
            if not result["success"]:
                return result
            data = result["data"]
            if (
                not isinstance(data, dict)
                or str(data.get("id")) != str(channel_id)
                or str(data.get("guild_id")) != str(self.guild_id)
            ):
                return self._failure("GUILD_CHANNEL_MISMATCH")
            self._channel_verified = True
        return {"success": True}

    def _send(self, channel_id, payload: dict) -> dict:
        with self._transport_lock:
            check = self._ensure_channel(channel_id)
            if not check["success"]:
                return check
            payload["allowed_mentions"] = {"parse": []}
            result = self._request("POST", f"/channels/{channel_id}/messages", payload)
            record = {
                "timestamp": time.time(),
                "http_status": result.get("http_status"),
                "success": False,
                "channel_id": str(channel_id),
            }
            if result["success"]:
                data = result["data"]
                if (
                    not isinstance(data, dict)
                    or not self._snowflake(data.get("id"))
                    or str(data.get("channel_id")) != str(channel_id)
                ):
                    result = self._failure("INVALID_RESPONSE", result.get("http_status"))
                else:
                    record.update(success=True, message_id=str(data["id"]))
                    result = dict(record)
            if not result["success"]:
                record["error_code"] = result["error_code"]
            self.sent_messages.append(record)
            del self.sent_messages[:-1000]
            return result

    def send_message(self, channel_id: int, content: str) -> dict[str, Any]:
        return self._send(channel_id, {"content": content})

    def send_embed(
        self,
        channel_id: int,
        title: str,
        description: str,
        fields: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self._send(
            channel_id,
            {
                "embeds": [
                    {
                        "title": title,
                        "description": description,
                        "fields": fields or [],
                        "color": 0x00FF88,
                    }
                ]
            },
        )

    def send_file(
        self, channel_id: int, file_bytes: bytes, filename: str, caption: str = ""
    ) -> dict:
        return self._failure("FILE_SEND_NOT_IMPLEMENTED" if self.bot_token else "NOT_CONFIGURED")

    def register_handler(self, handler: Callable) -> None:
        """Legacy callback is not a command execution authority.

        Inbound commands always use handle_message/ActionDispatcher. Raw callback
        execution was removed because it bypassed permissions and safety.
        """
        self.message_handler = handler

    def start_polling(self, channel_id: str | int | None = None) -> dict:
        with self._lifecycle_lock:
            if self._poll_thread and self._poll_thread.is_alive():
                return self._failure("ALREADY_RUNNING" if self._running else "STOPPING")
            channel = channel_id or self.default_channel_id
            check = self._ensure_channel(channel)
            if not check["success"]:
                self.last_poll_status = check
                return check
            if not self.whitelist:
                return self._failure("WHITELIST_REQUIRED")
            self._stop_event.clear()
            self._running = True
            self.consecutive_errors = 0
            self._poll_thread = threading.Thread(
                target=self._poll_loop, args=(channel,), name="DiscordPollThread", daemon=True
            )
            self._poll_thread.start()
            return {"success": True, "status": "STARTING"}

    def stop_polling(self, timeout: float = 2.0) -> dict:
        with self._lifecycle_lock:
            self._running = False
            self._stop_event.set()
            thread = self._poll_thread
            if thread and thread is not threading.current_thread():
                thread.join(timeout=timeout)
            if thread and thread.is_alive():
                return self._failure("STOP_TIMEOUT")
            self._poll_thread = None
            return {"success": True, "status": "STOPPED"}

    def _poll_loop(self, channel_id=None) -> None:
        try:
            while self._running and not self._stop_event.is_set():
                if not self.poll_once(channel_id):
                    break
                self._stop_event.wait(
                    max(0.05, self.poll_interval_s, self._retry_at - time.monotonic())
                )
        finally:
            self._running = False

    def poll_once(self, channel_id=None, mock_http=None) -> bool:
        """REST poll (not WebSocket Gateway). Bool means continue, not success.

        Read last_poll_status for actual outcome. First poll establishes a cursor
        without executing historical commands. Cursor is in-memory; restarting a
        new controller deliberately skips offline history. No automatic send retry.
        """
        if mock_http is not None:
            self.last_poll_status = self._failure("UNSUPPORTED_LEGACY_ADAPTER")
            return False
        with self._poll_lock:
            channel = channel_id or self.default_channel_id
            check = self._ensure_channel(channel)
            if not check["success"]:
                self.last_poll_status = check
                return False
            path = f"/channels/{channel}/messages?limit=50"
            if self._last_message_id:
                path += f"&after={self._last_message_id}"
            result = self._request("GET", path)
            self.last_poll_status = {k: v for k, v in result.items() if k != "data"}
            if not result["success"]:
                if result.get("http_status") == 429:
                    return True
                self.consecutive_errors += 1
                return (
                    result.get("http_status") not in (401, 403, 404)
                    and self.consecutive_errors < self.consecutive_error_threshold
                )
            raw = result["data"]
            if not isinstance(raw, list):
                self.last_poll_status = self._failure("INVALID_RESPONSE", result["http_status"])
                return False
            self.consecutive_errors = 0
            messages = sorted(
                (m for m in raw if isinstance(m, dict) and self._snowflake(m.get("id"))),
                key=lambda m: int(m["id"]),
            )
            bootstrap = not self._bootstrapped
            self._bootstrapped = True
            for msg in messages:
                mid = str(msg["id"])
                if self._last_message_id and int(mid) <= int(self._last_message_id):
                    continue
                self._last_message_id = mid  # at-most-once; no replay after failed reply
                if bootstrap or self._stop_event.is_set():
                    continue
                if str(msg.get("channel_id")) != str(channel) or msg.get("webhook_id"):
                    continue
                author = msg.get("author")
                if not isinstance(author, dict) or author.get("bot"):
                    continue
                uid = author.get("id")
                if not self.is_user_authorized(uid):
                    continue
                reply = self.handle_message(
                    int(uid), "remote-user", str(msg.get("content", "")), int(channel)
                )
                delivery = (
                    self.send_embed(
                        int(channel),
                        reply["embed"]["title"],
                        reply["embed"].get("description", ""),
                        reply["embed"].get("fields"),
                    )
                    if reply.get("embed")
                    else self.send_message(int(channel), reply["text"])
                )
                self.last_poll_status = {
                    "success": delivery["success"],
                    "http_status": delivery.get("http_status"),
                    "message_id": mid,
                    "reply_message_id": delivery.get("message_id"),
                    "command_status": reply["status"],
                    "timestamp": time.time(),
                    "error_code": delivery.get("error_code"),
                }
            return True


# Backward compatibility
DiscordBotClient = DiscordBotController
DiscordBotIntegration = DiscordBotController


__all__ = ["DiscordBotController", "DiscordConfig", "DiscordEmbed"]
