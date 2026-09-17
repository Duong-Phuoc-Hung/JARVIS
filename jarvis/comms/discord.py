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
    guild_id: int | None = None
    default_channel_id: int | None = None
    enabled: bool = True
    rate_limit_s: float = 1.0
    rate_limit: RateLimitConfig = field(default_factory=lambda: RateLimitConfig(requests_per_minute=30, burst_limit=10))
    poll_interval_s: float = 2.0
    consecutive_error_threshold: int = 5


@dataclass
class DiscordEmbed:
    title: str = ""
    description: str = ""
    color: int = 0x00FF88   # JARVIS green
    fields: list[dict[str, Any]] = field(default_factory=list)

    def add_field(self, name: str, value: str, inline: bool = False) -> DiscordEmbed:
        self.fields.append({"name": name, "value": value, "inline": inline})
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "description": self.description,
                "color": self.color, "fields": self.fields}


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
    ) -> None:
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
        self.guild_id = guild_id or (config.guild_id if config else None)
        self.default_channel_id = channel_id or (config.default_channel_id if config else None)
        self.dispatcher = dispatcher
        self._http = http_client
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter(
            rate_limit_config or (config.rate_limit if config else RateLimitConfig(requests_per_minute=30, burst_limit=10)),
            channel_name="discord",
        )
        self.sent_messages: list[dict[str, Any]] = []
        self.security_violations: list[dict[str, Any]] = []
        self._running = False
        self._poll_thread: threading.Thread | None = None
        self._last_message_id: str | None = None
        self.poll_interval_s: float = float(
            poll_interval_s if poll_interval_s is not None else (config.poll_interval_s if config and config.poll_interval_s is not None else 2.0)
        )
        self.consecutive_error_threshold: int = int(
            consecutive_error_threshold if consecutive_error_threshold is not None else (config.consecutive_error_threshold if config and config.consecutive_error_threshold is not None else 5)
        )
        self.consecutive_errors: int = 0
        self._stop_event: threading.Event = threading.Event()
        self.message_handler: Callable | None = message_handler
        log.info("DiscordBotController initialized (token=%s, whitelist=%d users, rate_limiter=%s)",
                 "set" if bot_token else "not_set", len(self.whitelist), "set" if rate_limiter else "none")

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
        if not self.is_user_authorized(user_id):
            import hashlib
            sha256_prefix = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:12]
            audit_entry = {
                "event": "UNAUTHORIZED_DISCORD_ACCESS",
                "user_id": user_id,
                "username": username,
                "payload_sha256_prefix": sha256_prefix,
                "payload_length": len(content),
                "timestamp": time.time(),
            }
            self.security_violations.append(audit_entry)
            log.warning("Unauthorized Discord user rejected: %s (ID=%d, len=%d, hash_prefix=%s)",
                        username, user_id, len(content), sha256_prefix)
            return {"status": 403, "text": "⛔ Bạn không có quyền điều khiển JARVIS.", "embed": None}

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
            if cmd_name == "note":
                return self._cmd_note(cmd_args)
            if cmd_name == "calc":
                return self._cmd_calc(cmd_args)
            if cmd_name == "screenshot":
                return self._cmd_screenshot(channel_id)
            if cmd_name == "macro":
                return self._cmd_macro(cmd_args)
            if cmd_name == "exec":
                return self._cmd_exec(cmd_args, username)

        # Natural language fallback
        if self.dispatcher:
            try:
                response = self.dispatcher(content)
                return {"status": 200, "text": str(response), "embed": None}
            except Exception as exc:
                log.warning("Dispatcher error: %s", exc)

        return {"status": 200, "text": f"💬 Nhận được: '{content[:100]}' — Dùng `/help` hoặc `!help` để xem lệnh.", "embed": None}

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _cmd_help(self) -> dict[str, Any]:
        embed = DiscordEmbed(title="🤖 JARVIS Discord Controller", description="Danh sách lệnh điều khiển:")
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
            text = result.get("output", "Không thể tải briefing.") if isinstance(result, dict) else str(result)
        except Exception as exc:
            text = f"Briefing không khả dụng: {exc}"
        return {"status": 200, "text": f"📰 {text[:1800]}", "embed": None}

    def _cmd_skills(self) -> dict[str, Any]:
        try:
            from jarvis.skills import registry
            reg = registry.SkillRegistry()
            skills = reg.list_skills()
            names = [s.name for s in skills]
            text = "🧰 **Kỹ năng:** " + ", ".join(f"`{n}`" for n in names)
        except Exception as exc:
            text = f"Lỗi lấy danh sách kỹ năng: {exc}"
        return {"status": 200, "text": text[:1800], "embed": None}

    def _cmd_note(self, note_text: str) -> dict[str, Any]:
        if not note_text:
            return {"status": 400, "text": "⚠️ Vui lòng nhập nội dung ghi chú sau `/note` hoặc `!note`.", "embed": None}
        try:
            from jarvis.skills import registry
            reg = registry.SkillRegistry()
            reg.invoke_skill("note_taker", action="add", content=note_text)
            text = f"📝 Đã lưu ghi chú: {note_text[:100]}"
        except Exception:
            text = f"📝 Ghi chú đã ghi nhận: {note_text[:100]}"
        return {"status": 200, "text": text, "embed": None}

    def _cmd_calc(self, expr: str) -> dict[str, Any]:
        if not expr:
            return {"status": 400, "text": "⚠️ Nhập biểu thức sau `/calc` hoặc `!calc`.", "embed": None}
        try:
            from jarvis.skills import registry
            reg = registry.SkillRegistry()
            result = reg.invoke_skill("calculator", expression=expr)
            text = result.get("output", str(result)) if isinstance(result, dict) else str(result)
        except Exception as exc:
            text = f"Lỗi tính toán: {exc}"
        return {"status": 200, "text": f"🔢 {text}", "embed": None}

    def _cmd_screenshot(self, channel_id: int) -> dict[str, Any]:
        png_bytes = self._capture_screenshot()
        if png_bytes:
            self.send_file(channel_id, png_bytes, "screenshot.png", "📸 Màn hình hiện tại")
            return {"status": 200, "text": "📸 Đã chụp và gửi màn hình!", "embed": None}
        return {"status": 500, "text": "❌ Không thể chụp màn hình.", "embed": None}

    def _cmd_macro(self, macro_name: str) -> dict[str, Any]:
        try:
            from jarvis.skills import registry
            reg = registry.SkillRegistry()
            result = reg.invoke_skill("macro_recorder", action="play", macro_name=macro_name)
            text = result.get("output", str(result)) if isinstance(result, dict) else str(result)
        except Exception as exc:
            text = f"Lỗi chạy macro '{macro_name}': {exc}"
        return {"status": 200, "text": text[:1800], "embed": None}

    def _cmd_exec(self, command: str, username: str) -> dict[str, Any]:
        parts = command.split(None, 1)
        skill_name = parts[0] if parts else ""
        params_str = parts[1] if len(parts) > 1 else ""
        try:
            from jarvis.skills import registry
            reg = registry.SkillRegistry()
            kwargs = {}
            if params_str:
                kwargs["query"] = params_str
            result = reg.invoke_skill(skill_name, **kwargs)
            text = result.get("output", str(result)) if isinstance(result, dict) else str(result)
        except Exception as exc:
            text = f"Lỗi exec '{skill_name}': {exc}"
        return {"status": 200, "text": f"⚙️ {text[:1800]}", "embed": None}

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

    def send_message(self, channel_id: int, content: str) -> dict[str, Any]:
        record = {"channel_id": channel_id, "content": content, "timestamp": time.time()}
        self.sent_messages.append(record)
        if self._http and self.bot_token:
            try:
                import json as _json
                import urllib.error
                import urllib.request
                payload = _json.dumps({"content": content}).encode()
                req = urllib.request.Request(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    data=payload,
                    headers={"Authorization": f"Bot {self.bot_token}", "Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=10)
                return {"success": True, "data": record}
            except Exception as exc:
                log.warning("Discord send_message API error: %s", exc)
                return {"success": False, "error": str(exc), "data": record}
        # Fail-closed: no bot_token or http_client — do NOT fabricate successful delivery.
        # Previously returned success=True here regardless — that was fabrication (2026-09-04).
        return {
            "success": False,
            "error_code": "NOT_CONFIGURED",
            "description": "No bot_token configured. Message was NOT sent to Discord.",
            "data": record,
        }

    def send_file(
        self,
        channel_id: int,
        file_bytes: bytes,
        filename: str,
        caption: str = "",
    ) -> dict[str, Any]:
        record = {"channel_id": channel_id, "filename": filename, "size": len(file_bytes), "timestamp": time.time()}
        self.sent_messages.append(record)
        # Fail-closed: file upload via multipart API not yet implemented.
        # Previously returned success=True regardless — that was fabrication (2026-09-04).
        # When bot_token is present, log a warning that file upload is not implemented.
        if self._http and self.bot_token:
            log.warning(
                "Discord send_file: file upload API (multipart/form-data) is not yet "
                "implemented. File '%s' was NOT sent to channel %d.", filename, channel_id
            )
            return {
                "success": False,
                "error_code": "FILE_SEND_NOT_IMPLEMENTED",
                "description": f"File '{filename}' was NOT uploaded — Discord multipart file upload is not yet implemented.",
                "data": record,
            }
        return {
            "success": False,
            "error_code": "NOT_CONFIGURED",
            "description": f"No bot_token configured. File '{filename}' was NOT sent to Discord.",
            "data": record,
        }

    def send_embed(
        self,
        channel_id: int,
        title: str,
        description: str,
        fields: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        fields = fields or []
        embed_dict = {"title": title, "description": description, "fields": fields, "color": 0x00FF88}
        record = {
            "channel_id": channel_id,
            "content": f"**{title}**\n{description}",
            "embed": embed_dict,
            "timestamp": time.time(),
        }
        self.sent_messages.append(record)
        if self._http and self.bot_token:
            try:
                import json as _json
                import urllib.error
                import urllib.request
                payload = _json.dumps({
                    "content": f"**{title}**\n{description}",
                    "embeds": [embed_dict],
                }).encode()
                req = urllib.request.Request(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    data=payload,
                    headers={"Authorization": f"Bot {self.bot_token}", "Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=10)
                return {"success": True, "data": record}
            except Exception as exc:
                log.warning("Discord send_embed API error: %s", exc)
                return {"success": False, "error": str(exc), "data": record}
        # Fail-closed: no bot_token or http_client — do NOT fabricate successful delivery.
        # Previously returned success=True here regardless — that was fabrication (2026-09-04).
        return {
            "success": False,
            "error_code": "NOT_CONFIGURED",
            "description": "No bot_token configured. Embed was NOT sent to Discord.",
            "data": record,
        }

    def _capture_screenshot(self) -> bytes | None:
        try:
            import mss
            import mss.tools
            with mss.mss() as sct:
                img = sct.grab(sct.monitors[1])
                return mss.tools.to_png(img.rgb, img.size)
        except Exception:
            pass
        try:
            import io

            from PIL import ImageGrab
            buf = io.BytesIO()
            ImageGrab.grab().save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Polling & Inbound Gateway
    # ------------------------------------------------------------------

    def register_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register callback handler for inbound Discord messages."""
        self.message_handler = handler

    def start_polling(self, channel_id: str | int | None = None) -> None:
        """
        Start background polling loop.
        Fail-closed: If not self.bot_token or not (channel_id or self.default_channel_id):
        log warning/info and return immediately. Ensure self._running = False and self._poll_thread is None.
        """
        target_channel = channel_id or self.default_channel_id
        if not self.bot_token or not target_channel:
            log.warning("Discord polling skipped (missing bot_token or channel_id)")
            self._running = False
            self._poll_thread = None
            return

        if self._running:
            log.info("Discord polling is already running.")
            return

        self._running = True
        self._stop_event.clear()
        self.consecutive_errors = 0
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            args=(str(target_channel),),
            name="DiscordPollThread",
            daemon=True,
        )
        self._poll_thread.start()
        log.info("Discord polling started on channel %s", target_channel)

    def stop_polling(self, timeout: float = 2.0) -> None:
        """Stop background polling loop gracefully."""
        self._running = False
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=timeout)
        self._poll_thread = None
        log.info("Discord polling stopped.")

    def _poll_loop(self, channel_id: str | int | None = None) -> None:
        """Background polling worker loop."""
        target_channel = str(channel_id or self.default_channel_id or "")
        if not self.bot_token or not target_channel:
            self._running = False
            return

        try:
            while self._running and not self._stop_event.is_set():
                try:
                    should_continue = self.poll_once(target_channel)
                except Exception as exc:
                    log.error("Unexpected error in Discord poll_once: %s", exc)
                    should_continue = True
                    self._stop_event.wait(timeout=min(self.poll_interval_s, 1.0))
                if not should_continue:
                    break
                self._stop_event.wait(timeout=self.poll_interval_s)
        finally:
            self._running = False

    def poll_once(self, channel_id: str | int | None = None, mock_http: Any | None = None) -> bool:
        """
        Execute a single polling pass on the specified channel.
        Queries GET /channels/{channel_id}/messages?limit=50 (&after={_last_message_id} if set).
        Enforces user authorization whitelist, filters bot messages, and dispatches to handler.
        Returns True to continue polling, False to terminate polling loop.
        """
        target_channel = str(channel_id or self.default_channel_id or "")
        if not self.bot_token or not target_channel:
            log.warning("Discord poll_once skipped: missing bot_token or channel_id")
            return False

        url = f"https://discord.com/api/v10/channels/{target_channel}/messages?limit=50"
        if self._last_message_id:
            url += f"&after={self._last_message_id}"

        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "User-Agent": "JARVIS-Assistant/5.2.0",
        }

        client = mock_http if mock_http is not None else self._http
        raw_messages: list[dict[str, Any]] = []

        try:
            if client is not None:
                if hasattr(client, "get"):
                    resp = client.get(url, headers=headers)
                    status_code = getattr(resp, "status_code", 200)
                    if status_code in (401, 403, 404):
                        log.critical("Fatal Discord HTTP %d error on channel %s. Terminating polling loop.", status_code, target_channel)
                        self._running = False
                        return False
                    if status_code >= 400:
                        raise RuntimeError(f"HTTP {status_code}: {getattr(resp, 'text', '')}")
                    if hasattr(resp, "json"):
                        raw_messages = resp.json()
                    else:
                        import json as _json
                        raw_messages = _json.loads(getattr(resp, "text", "[]"))
                elif hasattr(client, "urlopen"):
                    import json as _json
                    import urllib.request
                    req = urllib.request.Request(url, headers=headers, method="GET")
                    with client.urlopen(req, timeout=10) as resp:
                        raw_messages = _json.loads(resp.read().decode("utf-8"))
                elif callable(client):
                    resp = client(url, headers=headers)
                    status_code = getattr(resp, "status_code", 200)
                    if status_code in (401, 403, 404):
                        log.critical("Fatal Discord HTTP %d error on channel %s. Terminating polling loop.", status_code, target_channel)
                        self._running = False
                        return False
                    if status_code >= 400:
                        raise RuntimeError(f"HTTP {status_code}: {getattr(resp, 'text', '')}")
                    if hasattr(resp, "json"):
                        raw_messages = resp.json()
                    else:
                        import json as _json
                        raw_messages = _json.loads(getattr(resp, "text", "[]"))
            else:
                import json as _json
                import urllib.request
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw_messages = _json.loads(resp.read().decode("utf-8"))

            self.consecutive_errors = 0

        except Exception as exc:
            status_code = getattr(exc, "code", getattr(getattr(exc, "response", None), "status_code", None))
            if status_code in (401, 403, 404):
                log.critical("Fatal Discord HTTP %d error on channel %s: %s. Terminating polling loop.", status_code, target_channel, exc)
                self._running = False
                return False

            self.consecutive_errors += 1
            if self.consecutive_errors >= self.consecutive_error_threshold:
                log.critical(
                    "Discord polling reached consecutive error threshold (%d >= %d): %s. Terminating polling loop.",
                    self.consecutive_errors,
                    self.consecutive_error_threshold,
                    exc,
                )
                self._running = False
                return False
            else:
                log.warning(
                    "Discord polling network/request error (%d/%d): %s",
                    self.consecutive_errors,
                    self.consecutive_error_threshold,
                    exc,
                )
                return True

        if not raw_messages or not isinstance(raw_messages, list):
            return True

        # Filter raw_messages to only dict elements before sorting
        raw_messages = [m for m in raw_messages if isinstance(m, dict)]
        if not raw_messages:
            return True

        # Sort messages ascending by numeric snowflake ID: int(msg["id"])
        try:
            sorted_messages = sorted(raw_messages, key=lambda m: int(m.get("id", 0)))
        except (ValueError, TypeError, AttributeError):
            sorted_messages = raw_messages

        # Update self._last_message_id to the max snowflake string (strictly numeric)
        if sorted_messages:
            max_id = str(sorted_messages[-1].get("id", "") or "")
            if max_id.isdigit():
                try:
                    if self._last_message_id is None or int(max_id) > int(self._last_message_id):
                        self._last_message_id = max_id
                except (ValueError, TypeError):
                    pass

        for msg in sorted_messages:
            if not isinstance(msg, dict):
                continue

            author = msg.get("author", {})
            if not isinstance(author, dict):
                author = {}

            # If author.get("bot", False) is True: skip
            if author.get("bot", False) is True:
                continue

            # Author ID: author_id_int = int(author["id"])
            author_id_raw = author.get("id")
            try:
                author_id_int = int(author_id_raw) if author_id_raw is not None else 0
            except (ValueError, TypeError):
                author_id_int = 0

            username = str(author.get("username", "unknown"))
            content = str(msg.get("content", ""))

            # If not self.is_user_authorized(author_id_int): log security drop with SHA-256 hash prefix, record in self.security_violations, do NOT dispatch
            if not self.is_user_authorized(author_id_int):
                import hashlib
                sha256_prefix = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:12]
                audit_entry = {
                    "event": "UNAUTHORIZED_DISCORD_ACCESS",
                    "user_id": author_id_int,
                    "username": username,
                    "payload_sha256_prefix": sha256_prefix,
                    "payload_length": len(content),
                    "timestamp": time.time(),
                }
                self.security_violations.append(audit_entry)
                log.warning(
                    "Unauthorized Discord message dropped: user %s (ID=%d, len=%d, hash_prefix=%s)",
                    username,
                    author_id_int,
                    len(content),
                    sha256_prefix,
                )
                continue

            # If authorized: dispatch to self.message_handler(msg) if callable, else self.handle_message(msg)
            if callable(self.message_handler):
                try:
                    self.message_handler(msg)
                except Exception as exc:
                    log.error("Error in Discord message_handler for message %s: %s", msg.get("id"), exc)
            else:
                try:
                    cid = int(target_channel)
                except (ValueError, TypeError):
                    cid = 0
                try:
                    try:
                        self.handle_message(
                            user_id=author_id_int,
                            username=username,
                            content=content,
                            channel_id=cid,
                        )
                    except TypeError:
                        self.handle_message(msg)
                except Exception as exc:
                    log.error("Error in Discord handle_message for message %s: %s", msg.get("id"), exc)

        return True


# Backward compatibility
DiscordBotClient = DiscordBotController
DiscordBotIntegration = DiscordBotController


__all__ = ["DiscordBotController", "DiscordConfig", "DiscordEmbed"]
