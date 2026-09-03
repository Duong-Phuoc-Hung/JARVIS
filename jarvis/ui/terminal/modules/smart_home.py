"""
jarvis/ui/terminal/modules/smart_home.py
===========================================
Smart Home module adapter, over jarvis.smart_home.home_assistant.

WebSocket/event support is NOT claimed here -- HomeAssistantClient only
implements REST polling (urllib.request), confirmed by inspection; despite
an older module docstring mentioning WebSocket, no such connection exists
in the current implementation.

Device control (turn on/off/toggle/set temperature) is presentation-only
in this build -- it is NOT wired to actually call Home Assistant.
`HomeAssistantClient` has no backend-native authorization contract of its
own (no protected-entity list, no privilege concept -- it is a bare REST
wrapper), and no `ActionDispatcher` action for smart-home control exists
anywhere else in this codebase to route through. A terminal-side Y/N
prompt alone is presentation UX, not authorization, so executing these
calls unauthenticated behind only that prompt would be a real security
gap (audited and rejected -- see `CLAUDE.md`'s "Durable Terminal Control
Center invariant" and the removed `jarvis/ui/terminal/authority.py`
history, which took the wrong approach of inventing a private,
disconnected `ActionDispatcher` solely to make this look "authorized").
Until a real authoritative path exists (either a canonical dispatcher
action registered elsewhere in the app, or a backend-native safety
contract added to `HomeAssistantClient` itself), these actions report
`UNAVAILABLE` truthfully rather than executing.
"""
from __future__ import annotations

from jarvis.smart_home.home_assistant import HomeAssistantClient
from jarvis.ui.terminal.context import TerminalContext, run_timed
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.theme import StatusLevel

_NO_AUTHORITATIVE_PATH = (
    "No authoritative execution path exists for Smart Home control in this codebase -- "
    "no ActionDispatcher registration and no backend-native safety contract on "
    "HomeAssistantClient. This screen intentionally does not execute the call rather than "
    "run it behind only a presentation-layer Y/N prompt."
)

MODULE = "SMART_HOME"

_PROBE_ENTITY = "sun.sun"  # near-universal built-in Home Assistant entity


def _client(ctx: TerminalContext) -> HomeAssistantClient | None:
    client = ctx.state.get("ha_client")
    if client is not None:
        return client
    enabled = bool(ctx.config.get("smart_home.home_assistant.enabled", False))
    if not enabled:
        return None
    url = ctx.config.get("smart_home.home_assistant.url", "") or ""
    token = ctx.config.get("smart_home.home_assistant.token", "") or ""
    aliases = ctx.config.get("smart_home.home_assistant.entities", {}) or {}
    client = HomeAssistantClient(base_url=url, access_token=token, entity_aliases=aliases)
    ctx.state["ha_client"] = client
    return client


def _connection_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        enabled = bool(ctx.config.get("smart_home.home_assistant.enabled", False))
        if not enabled:
            return ActionOutcome(status=StatusLevel.OFFLINE, title="Connection Status",
                                  fields=[("Configured", "NO")],
                                  detail_lines=["Home Assistant is disabled in config "
                                                "(smart_home.home_assistant.enabled=false)."])
        client = _client(ctx)
        assert client is not None
        state = client.get_state(_PROBE_ENTITY)
        if state is None:
            return ActionOutcome(status=StatusLevel.OFFLINE, title="Connection Status",
                                  fields=[("Configured", "YES"), ("Reachable", "NO")],
                                  detail_lines=["No response from Home Assistant (unreachable, "
                                                "invalid token, or entity not found)."])
        return ActionOutcome(status=StatusLevel.AVAILABLE, title="Connection Status",
                              fields=[("Configured", "YES"), ("Reachable", "YES")])
    return run_timed(body)


def _entity_state_prompt(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        client = _client(ctx)
        if client is None:
            return ActionOutcome(status=StatusLevel.OFFLINE, title="Entity State",
                                  detail_lines=["Home Assistant is not configured/enabled."])
        entity = ctx.console.read_line("Enter entity id or configured alias: ")
        if not entity:
            return ActionOutcome(status=StatusLevel.SKIPPED, title="Entity State",
                                  detail_lines=["No entity entered."])
        resolved = client.resolve_entity(entity)
        state = client.get_state(resolved)
        if state is None:
            return ActionOutcome(status=StatusLevel.OFFLINE, title="Entity State",
                                  fields=[("Entity", resolved)],
                                  detail_lines=["No state returned (unreachable or entity not found)."])
        fields = [("Entity", resolved), ("State", str(state.get("state", "unknown")))]
        return ActionOutcome(status=StatusLevel.PASS, title="Entity State", fields=fields,
                              structured_data={"entity": resolved, "state": state})
    return run_timed(body)


def _control_unavailable(label: str) -> ActionOutcome:
    def body() -> ActionOutcome:
        return ActionOutcome(status=StatusLevel.LIMITED, title=label,
                              detail_lines=[_NO_AUTHORITATIVE_PATH])
    return run_timed(body)


def _entity_aliases(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        aliases = ctx.config.get("smart_home.home_assistant.entities", {}) or {}
        if not aliases:
            return ActionOutcome(status=StatusLevel.LIMITED, title="Entity Aliases",
                                  detail_lines=["No aliases configured."])
        fields = [(alias, entity_id) for alias, entity_id in aliases.items()]
        return ActionOutcome(status=StatusLevel.PASS, title="Entity Aliases", fields=fields)
    return run_timed(body)


def build_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="sh_status", key="1", label="Connection Status",
                   description="Home Assistant reachability", handler=lambda: _connection_status(ctx),
                   safe_for_batch=True, help_text="Probes a built-in entity to confirm reachability."),
        MenuAction(id="sh_entity", key="2", label="Entity State",
                   description="Look up one entity's current state",
                   handler=lambda: _entity_state_prompt(ctx), requires_target=True, safe_for_batch=False,
                   help_text="Prompts for an entity id/alias and reads its state."),
        MenuAction(id="sh_on", key="3", label="Turn On Device", description="Turn on one entity",
                   handler=lambda: _control_unavailable("Turn On Device"),
                   read_only=True, requires_confirmation=False,
                   side_effect_level="none", safe_for_batch=False,
                   available=False, unavailable_reason="No authoritative execution path wired yet.",
                   help_text="No ActionDispatcher route or backend-native safety contract exists "
                              "for Smart Home control -- see module docstring."),
        MenuAction(id="sh_off", key="4", label="Turn Off Device", description="Turn off one entity",
                   handler=lambda: _control_unavailable("Turn Off Device"),
                   read_only=True, requires_confirmation=False,
                   side_effect_level="none", safe_for_batch=False,
                   available=False, unavailable_reason="No authoritative execution path wired yet.",
                   help_text="No ActionDispatcher route or backend-native safety contract exists "
                              "for Smart Home control -- see module docstring."),
        MenuAction(id="sh_toggle", key="5", label="Toggle Device", description="Toggle one entity",
                   handler=lambda: _control_unavailable("Toggle Device"),
                   read_only=True, requires_confirmation=False,
                   side_effect_level="none", safe_for_batch=False,
                   available=False, unavailable_reason="No authoritative execution path wired yet.",
                   help_text="No ActionDispatcher route or backend-native safety contract exists "
                              "for Smart Home control -- see module docstring."),
        MenuAction(id="sh_temp", key="6", label="Set Temperature", description="Set a climate entity's target",
                   handler=lambda: _control_unavailable("Set Temperature"),
                   read_only=True, requires_confirmation=False,
                   side_effect_level="none", safe_for_batch=False,
                   available=False, unavailable_reason="No authoritative execution path wired yet.",
                   help_text="No ActionDispatcher route or backend-native safety contract exists "
                              "for Smart Home control -- see module docstring."),
        MenuAction(id="sh_aliases", key="7", label="Entity Aliases",
                   description="List configured entity aliases", handler=lambda: _entity_aliases(ctx),
                   safe_for_batch=True, help_text="Lists alias -> entity_id mappings from config."),
    ]
    return MenuScreen(
        id="smart_home", title="SMART HOME", breadcrumb=["MAIN", "SMART HOME"],
        actions=actions, batch_label="Check All Status",
        help_intro="[A] only runs read-only status checks. Control actions always require an "
                   "explicitly named entity and confirmation -- never applied to 'all devices'.",
    )
