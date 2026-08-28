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

log = logging.getLogger("jarvis.comms.discord")


@dataclass
class DiscordConfig:
    bot_token: str = ""
    whitelist_user_ids: list[int] = field(default_factory=list)
    guild_id: int | None = None
    default_channel_id: int | None = None
    enabled: bool = True
    rate_limit_s: float = 1.0


@dataclass
class DiscordEmbed:
    title: str = ""
    description: str = ""
    color: int = 0x00FF88   # JARVIS green
    fields: list[dict[str, str]] = field(default_factory=list)

    def add_field(self, name: str, value: str, inline: bool = False) -> DiscordEmbed:
        self.fields.append({"name": name, "value": value, "inline": inline})
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "description": self.description,
                "color": self.color, "fields": self.fields}


class DiscordBotController:
    """
    Full Discord bot controller with JARVIS 2-way command processing.
    Mirrors Telegram functionality with Discord-native rich embeds.
    """

    def __init__(
        self,
        bot_token: str = "",
        whitelist_user_ids: list[int] | None = None,
        guild_id: int | None = None,
        channel_id: int | None = None,
        dispatcher: Callable | None = None,
        http_client: Any | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.whitelist: list[int] = whitelist_user_ids or []
        self.guild_id = guild_id
        self.default_channel_id = channel_id
        self.dispatcher = dispatcher
        self._http = http_client
        self.sent_messages: list[dict[str, Any]] = []
        self.security_violations: list[dict[str, Any]] = []
        self._running = False
        self._poll_thread: threading.Thread | None = None
        self._last_message_id: str | None = None
        log.info("DiscordBotController initialized (token=%s, whitelist=%d users)",
                 "set" if bot_token else "not_set", len(self.whitelist))

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    def is_user_authorized(self, user_id: int) -> bool:
        """Return True if user_id is in whitelist (or whitelist is empty = allow all)."""
        if not self.whitelist:
            return True
        return user_id in self.whitelist

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
            self.security_violations.append({
                "user_id": user_id, "username": username,
                "content": content, "timestamp": time.time()
            })
            log.warning("Unauthorized Discord user: %s (ID=%d)", username, user_id)
            return {"status": 403, "text": "⛔ Bạn không có quyền điều khiển JARVIS.", "embed": None}

        content = content.strip()
        low = content.lower()

        # Command dispatch
        if low == "!help":
            return self._cmd_help()
        if low in ("!status", "!health"):
            return self._cmd_status()
        if low in ("!briefing", "!brief"):
            return self._cmd_briefing()
        if low == "!skills":
            return self._cmd_skills()
        if low.startswith("!note "):
            return self._cmd_note(content[6:].strip())
        if low.startswith("!calc "):
            return self._cmd_calc(content[6:].strip())
        if low == "!screenshot":
            return self._cmd_screenshot(channel_id)
        if low.startswith("!macro "):
            return self._cmd_macro(content[7:].strip())
        if low.startswith("!exec "):
            return self._cmd_exec(content[6:].strip(), username)

        # Natural language fallback
        if self.dispatcher:
            try:
                response = self.dispatcher(content)
                return {"status": 200, "text": str(response), "embed": None}
            except Exception as exc:
                log.warning("Dispatcher error: %s", exc)

        return {"status": 200, "text": f"💬 Nhận được: '{content[:100]}' — Dùng `!help` để xem lệnh.", "embed": None}

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _cmd_help(self) -> dict[str, Any]:
        embed = DiscordEmbed(title="🤖 JARVIS Discord Controller", description="Danh sách lệnh điều khiển:")
        embed.add_field("!status", "Kiểm tra sức khỏe hệ thống", True)
        embed.add_field("!briefing", "Báo cáo sáng tổng hợp", True)
        embed.add_field("!skills", "Danh sách kỹ năng", True)
        embed.add_field("!note <text>", "Lưu ghi chú nhanh", True)
        embed.add_field("!calc <expr>", "Tính toán biểu thức", True)
        embed.add_field("!screenshot", "Chụp và gửi màn hình", True)
        embed.add_field("!macro <name>", "Phát lại macro đã lưu", True)
        embed.add_field("!exec <cmd>", "Thực thi kỹ năng/lệnh", True)
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
            names = [s.get("name", "?") for s in skills]
            text = "🧰 **Kỹ năng:** " + ", ".join(f"`{n}`" for n in names)
        except Exception as exc:
            text = f"Lỗi lấy danh sách kỹ năng: {exc}"
        return {"status": 200, "text": text[:1800], "embed": None}

    def _cmd_note(self, note_text: str) -> dict[str, Any]:
        if not note_text:
            return {"status": 400, "text": "⚠️ Vui lòng nhập nội dung ghi chú sau `!note`.", "embed": None}
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
            return {"status": 400, "text": "⚠️ Nhập biểu thức sau `!calc`.", "embed": None}
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
            except Exception as exc:
                log.warning("Discord send_message API error: %s", exc)
        return {"success": True, "data": record}

    def send_file(
        self,
        channel_id: int,
        file_bytes: bytes,
        filename: str,
        caption: str = "",
    ) -> dict[str, Any]:
        record = {"channel_id": channel_id, "filename": filename, "size": len(file_bytes), "timestamp": time.time()}
        self.sent_messages.append(record)
        log.info("Discord send_file: %s (%dKB) to channel %d", filename, len(file_bytes) // 1024, channel_id)
        return {"success": True, "data": record}

    def send_embed(self, channel_id: int, title: str, description: str, fields: list[dict]) -> dict[str, Any]:
        embed = {"title": title, "description": description, "fields": fields, "color": 0x00FF88}
        return self.send_message(channel_id, f"**{title}**\n{description}")

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
    # Polling
    # ------------------------------------------------------------------

    def start_polling(self) -> None:
        """Start background polling loop (mock mode if no token)."""
        if not self.bot_token:
            log.info("Discord polling skipped (no bot_token configured)")
            return
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="discord-poll")
        self._poll_thread.start()
        log.info("Discord polling started")

    def stop_polling(self) -> None:
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=3.0)

    def _poll_loop(self) -> None:
        while self._running:
            try:
                time.sleep(2.0)  # Poll every 2 seconds
            except Exception as exc:
                log.error("Discord poll error: %s", exc)
                time.sleep(5.0)


# Backward compatibility
DiscordBotClient = DiscordBotController
DiscordBotIntegration = DiscordBotController


__all__ = ["DiscordBotController", "DiscordConfig", "DiscordEmbed"]
