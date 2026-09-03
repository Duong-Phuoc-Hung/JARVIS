"""
jarvis/ui/terminal/modules/comms.py
======================================
Communications Hub module adapter.

Known truthfulness gaps audited during this task (not fixed here, per
explicit scope instructions -- see follow-up findings):
  - TelegramBotController.send_message()/send_photo() return a synthetic
    {"ok": True, ...} success payload whenever no real http_client is
    wired -- which is always true for a bare TelegramBotController()
    constructed from this presentation layer (jarvis/comms/telegram.py).
  - DiscordBotController.send_message()/send_embed() return
    {"success": True, ...} even when the underlying HTTP POST raises an
    exception (jarvis/comms/discord.py); send_file() never attempts a
    real network call at all and still reports success.
Because neither transport can currently report a real confirmed-delivery
outcome, this module never calls those send methods -- Send Message /
Send Photo / Send Embed always report LIMITED with a truthful
explanation instead of a fabricated "SENT".

IMAPEmailReader (jarvis/comms/email_imap.py) does not connect to a real
IMAP server in this codebase at all -- it only filters/summarizes
caller-supplied EmailMessage objects. This is reported truthfully too.

[A] never sends a message/photo/embed/email under any circumstance.
"""
from __future__ import annotations

from jarvis.comms.discord import DiscordBotController
from jarvis.comms.email_imap import IMAPEmailReader
from jarvis.comms.rate_limiter import TokenBucketRateLimiter
from jarvis.comms.telegram import TelegramBotController
from jarvis.ui.terminal.context import TerminalContext, run_timed
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.theme import StatusLevel

MODULE = "COMMS"

_UNTRUSTED_SEND_DETAIL = (
    "This backend cannot currently confirm real delivery (see module docstring) -- "
    "no message was sent. Fixing the underlying transport truthfulness is tracked as "
    "follow-up work, not part of this terminal UI task."
)


def _telegram(ctx: TerminalContext) -> TelegramBotController:
    ctrl = ctx.state.get("comms_telegram")
    if ctrl is None:
        ids = ctx.config.get("comms.telegram.whitelist_chat_ids", []) or []
        ctrl = TelegramBotController(allowed_user_ids=set(ids))
        ctx.state["comms_telegram"] = ctrl
    return ctrl


def _discord(ctx: TerminalContext) -> DiscordBotController:
    ctrl = ctx.state.get("comms_discord")
    if ctrl is None:
        ids = ctx.config.get("comms.discord.channel_ids", []) or []
        ctrl = DiscordBotController(whitelist_user_ids=list(ids))
        ctx.state["comms_discord"] = ctrl
    return ctrl


def _configured(ctx: TerminalContext, channel: str) -> bool:
    return bool(ctx.config.get(f"comms.{channel}.enabled", False))


def _channel_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        tg = _configured(ctx, "telegram")
        dc = _configured(ctx, "discord")
        em = _configured(ctx, "email_imap")
        fields = [
            ("Telegram", "CONFIGURED" if tg else "NOT CONFIGURED"),
            ("Discord", "CONFIGURED" if dc else "NOT CONFIGURED"),
            ("Email / IMAP", "CONFIGURED" if em else "NOT CONFIGURED"),
        ]
        any_on = tg or dc or em
        status = StatusLevel.PARTIAL if any_on else StatusLevel.OFFLINE
        return ActionOutcome(status=status, title="Channel Status", fields=fields)
    return run_timed(body)


def _rate_limiter_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        fields = []
        for channel in ("telegram", "discord", "zalo"):
            rpm = ctx.config.get(f"comms.{channel}.rate_limit.requests_per_minute", None)
            burst = ctx.config.get(f"comms.{channel}.rate_limit.burst_limit", None)
            fields.append((channel.capitalize(), f"{rpm or 'N/A'} req/min, burst {burst or 'N/A'}"))
        return ActionOutcome(status=StatusLevel.AVAILABLE, title="Rate Limiter Status", fields=fields)
    return run_timed(body)


def _whitelist_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        tg_ids = ctx.config.get("comms.telegram.whitelist_chat_ids", []) or []
        dc_ids = ctx.config.get("comms.discord.channel_ids", []) or []
        fields = [
            ("Telegram Whitelist Size", str(len(tg_ids))),
            ("Discord Channel Allowlist Size", str(len(dc_ids))),
        ]
        empty = not tg_ids and not dc_ids
        status = StatusLevel.LIMITED if empty else StatusLevel.PASS
        detail = ["Both bots fail closed (reject everyone) while their allowlist is empty."] if empty else []
        return ActionOutcome(status=status, title="Whitelist / Security Status", fields=fields, detail_lines=detail)
    return run_timed(body)


# -- Telegram submenu -----------------------------------------------------

def _telegram_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        configured = _configured(ctx, "telegram")
        ctrl = _telegram(ctx)
        fields = [
            ("Configured", "YES" if configured else "NO"),
            ("Whitelist Size", str(len(ctrl.allowed_user_ids))),
            ("Security Violations Logged", str(len(getattr(ctrl, "security_violations", [])))),
        ]
        status = StatusLevel.PARTIAL if configured else StatusLevel.OFFLINE
        return ActionOutcome(status=status, title="Telegram Status", fields=fields)
    return run_timed(body)


def _telegram_whitelist(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        ctrl = _telegram(ctx)
        ids = sorted(ctrl.allowed_user_ids)
        if not ids:
            return ActionOutcome(status=StatusLevel.LIMITED, title="Telegram Whitelist",
                                  detail_lines=["Whitelist is empty -- all users are rejected (fail-closed)."])
        fields = [(f"Chat {i + 1}", str(cid)) for i, cid in enumerate(ids)]
        return ActionOutcome(status=StatusLevel.PASS, title="Telegram Whitelist", fields=fields)
    return run_timed(body)


def _telegram_rate_limiter(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        ctrl = _telegram(ctx)
        limiter: TokenBucketRateLimiter = ctrl.rate_limiter
        fields = [("Capacity", str(limiter.capacity)), ("Refill Rate", f"{limiter.refill_rate}/min")]
        return ActionOutcome(status=StatusLevel.AVAILABLE, title="Telegram Rate Limiter", fields=fields)
    return run_timed(body)


def _telegram_send_blocked(label: str) -> ActionOutcome:
    def body() -> ActionOutcome:
        return ActionOutcome(status=StatusLevel.LIMITED, title=label, detail_lines=[_UNTRUSTED_SEND_DETAIL])
    return run_timed(body)


def build_telegram_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="tg_status", key="1", label="Status", handler=lambda: _telegram_status(ctx), safe_for_batch=True),
        MenuAction(id="tg_whitelist", key="2", label="Whitelist", handler=lambda: _telegram_whitelist(ctx), safe_for_batch=True),
        MenuAction(id="tg_ratelimit", key="3", label="Rate Limiter", handler=lambda: _telegram_rate_limiter(ctx), safe_for_batch=True),
        MenuAction(id="tg_send_msg", key="4", label="Send Message", read_only=False,
                   requires_confirmation=True, side_effect_level="external_send", safe_for_batch=False,
                   handler=lambda: _telegram_send_blocked("Send Message")),
        MenuAction(id="tg_send_photo", key="5", label="Send Photo", read_only=False,
                   requires_confirmation=True, side_effect_level="external_send", safe_for_batch=False,
                   handler=lambda: _telegram_send_blocked("Send Photo")),
    ]
    return MenuScreen(id="comms_telegram", title="TELEGRAM", breadcrumb=["MAIN", "COMMUNICATIONS", "TELEGRAM"],
                       actions=actions, batch_label="Check All", help_intro="Send actions never fabricate delivery.")


# -- Discord submenu --------------------------------------------------------

def _discord_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        configured = _configured(ctx, "discord")
        ctrl = _discord(ctx)
        fields = [
            ("Configured", "YES" if configured else "NO"),
            ("Channel Allowlist Size", str(len(ctrl.whitelist))),
        ]
        status = StatusLevel.PARTIAL if configured else StatusLevel.OFFLINE
        return ActionOutcome(status=status, title="Discord Status", fields=fields)
    return run_timed(body)


def _discord_whitelist(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        ctrl = _discord(ctx)
        ids = sorted(ctrl.whitelist)
        if not ids:
            return ActionOutcome(status=StatusLevel.LIMITED, title="Discord Whitelist",
                                  detail_lines=["Allowlist is empty -- all users are rejected (fail-closed)."])
        fields = [(f"Channel {i + 1}", str(cid)) for i, cid in enumerate(ids)]
        return ActionOutcome(status=StatusLevel.PASS, title="Discord Whitelist", fields=fields)
    return run_timed(body)


def _discord_send_blocked(label: str) -> ActionOutcome:
    def body() -> ActionOutcome:
        return ActionOutcome(status=StatusLevel.LIMITED, title=label, detail_lines=[_UNTRUSTED_SEND_DETAIL])
    return run_timed(body)


def build_discord_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="dc_status", key="1", label="Status", handler=lambda: _discord_status(ctx), safe_for_batch=True),
        MenuAction(id="dc_whitelist", key="2", label="Whitelist", handler=lambda: _discord_whitelist(ctx), safe_for_batch=True),
        MenuAction(id="dc_send_msg", key="3", label="Send Message", read_only=False,
                   requires_confirmation=True, side_effect_level="external_send", safe_for_batch=False,
                   handler=lambda: _discord_send_blocked("Send Message")),
        MenuAction(id="dc_send_embed", key="4", label="Send Embed", read_only=False,
                   requires_confirmation=True, side_effect_level="external_send", safe_for_batch=False,
                   handler=lambda: _discord_send_blocked("Send Embed")),
    ]
    return MenuScreen(id="comms_discord", title="DISCORD", breadcrumb=["MAIN", "COMMUNICATIONS", "DISCORD"],
                       actions=actions, batch_label="Check All", help_intro="Send actions never fabricate delivery.")


# -- Email / IMAP submenu ----------------------------------------------------

def _email_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        configured = _configured(ctx, "email_imap")
        fields = [("Configured", "YES" if configured else "NO"), ("Real IMAP Connection", "NOT IMPLEMENTED")]
        detail = ["jarvis.comms.email_imap.IMAPEmailReader does not connect to a real IMAP "
                  "server in this codebase -- it only summarizes caller-supplied messages."]
        return ActionOutcome(status=StatusLevel.LIMITED, title="Email / IMAP Status", fields=fields, detail_lines=detail)
    return run_timed(body)


def _email_senders(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        username = ctx.config.get("comms.email_imap.username", "") or ""
        fields = [("Configured Username", username or "(none)")]
        return ActionOutcome(status=StatusLevel.PASS if username else StatusLevel.LIMITED,
                              title="Priority Senders", fields=fields)
    return run_timed(body)


def build_email_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="em_status", key="1", label="Status", handler=lambda: _email_status(ctx), safe_for_batch=True),
        MenuAction(id="em_senders", key="2", label="Priority Senders", handler=lambda: _email_senders(ctx), safe_for_batch=True),
    ]
    return MenuScreen(id="comms_email", title="EMAIL / IMAP", breadcrumb=["MAIN", "COMMUNICATIONS", "EMAIL"],
                       actions=actions, batch_label="Check All",
                       help_intro="This backend does not fetch real email in the current codebase.")


def build_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="comms_channel_status", key="1", label="Channel Status",
                   description="Configured/not configured for each channel", handler=lambda: _channel_status(ctx),
                   safe_for_batch=True, help_text="Reports config-enabled status per channel."),
        MenuAction(id="comms_telegram", key="2", label="Telegram", description="Telegram channel submenu",
                   is_submenu=True, submenu_id="comms_telegram", safe_for_batch=False,
                   help_text="Status, whitelist, rate limiter, and send actions for Telegram."),
        MenuAction(id="comms_discord", key="3", label="Discord", description="Discord channel submenu",
                   is_submenu=True, submenu_id="comms_discord", safe_for_batch=False,
                   help_text="Status, whitelist, and send actions for Discord."),
        MenuAction(id="comms_email", key="4", label="Email / IMAP", description="Email channel submenu",
                   is_submenu=True, submenu_id="comms_email", safe_for_batch=False,
                   help_text="Status and priority-sender configuration for Email/IMAP."),
        MenuAction(id="comms_ratelimit", key="5", label="Rate Limiter Status",
                   description="Configured rate limits per channel", handler=lambda: _rate_limiter_status(ctx),
                   safe_for_batch=True, help_text="Shows configured requests-per-minute/burst per channel."),
        MenuAction(id="comms_whitelist", key="6", label="Whitelist / Security Status",
                   description="Allowlist sizes across channels", handler=lambda: _whitelist_status(ctx),
                   safe_for_batch=True, help_text="Reports allowlist sizes; empty allowlists fail closed."),
    ]
    return MenuScreen(
        id="comms", title="COMMUNICATIONS HUB", breadcrumb=["MAIN", "COMMUNICATIONS"],
        actions=actions, batch_label="Check All Channels",
        help_intro="[A] never sends a message/photo/embed/email under any circumstance.",
    )
