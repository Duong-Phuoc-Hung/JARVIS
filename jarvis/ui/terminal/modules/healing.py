"""
jarvis/ui/terminal/modules/healing.py
========================================
Self-Healing module adapter. Reuses jarvis.healing.terminator's existing
truthfulness contract verbatim -- reclaimed_ram is only ever an observed
delta, termination is only ever reported successful after a confirmed
backend outcome. [A] never terminates a process.

Authorization: "Run Healing Action" calls `HealingEngine.heal_hung_process()`
directly -- NOT through a private terminal-owned ActionDispatcher. There is
no canonical dispatcher registration for process termination anywhere in
this codebase to route through, and inventing a private, disconnected
ActionDispatcher+SafetyGateInterceptor instance solely for this one call
would itself be a parallel security architecture (audited and rejected --
see the repository-root CLAUDE.md's "Durable Terminal Control Center
invariant" and the removed jarvis/ui/terminal/authority.py history).
Instead this reuses HealingEngine's own backend-native, always-enforced
authoritative safety contract: `heal_hung_process()` checks
`is_protected(name, pid)` against `PROTECTED_PROCESS_WHITELIST`
INTERNALLY, before attempting anything, regardless of caller -- this is a
real, existing, non-bypassable gate, not something added here. The
terminal's own Y/N prompt remains presentation-layer UX only, deciding
whether to attempt the call at all.
"""
from __future__ import annotations

from jarvis.healing.terminator import HealingEngine
from jarvis.ui.terminal.context import TerminalContext, run_timed
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.theme import StatusLevel

MODULE = "HEALING"


def _engine(ctx: TerminalContext) -> HealingEngine:
    eng = ctx.state.get("healing_engine")
    if eng is None:
        eng = HealingEngine(auto_kill=False)
        ctx.state["healing_engine"] = eng
    return eng


def _health_snapshot(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        eng = _engine(ctx)
        try:
            ram_critical = eng.is_ram_critical()
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="System Health Snapshot", error_reason=str(e))
        fields = [("RAM Critical", "YES" if ram_critical else "NO"),
                  ("Healing Actions Logged", str(len(eng.healing_log)))]
        status = StatusLevel.LIMITED if ram_critical else StatusLevel.PASS
        return ActionOutcome(status=status, title="System Health Snapshot", fields=fields)
    return run_timed(body)


def _find_hung(ctx: TerminalContext) -> list:
    eng = _engine(ctx)
    try:
        return eng.find_hung_windows()
    except Exception:
        return []


def _process_health(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        hung = _find_hung(ctx)
        ctx.state["healing_last_hung"] = hung
        fields = [("Hung Windows Detected", str(len(hung)))]
        status = StatusLevel.LIMITED if hung else StatusLevel.PASS
        return ActionOutcome(status=status, title="Process Health", fields=fields)
    return run_timed(body)


def _detect_hung(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        hung = _find_hung(ctx)
        ctx.state["healing_last_hung"] = hung
        if not hung:
            return ActionOutcome(status=StatusLevel.PASS, title="Detect Hung Processes",
                                  detail_lines=["No hung windows detected."])
        fields = []
        for i, w in enumerate(hung[:10]):
            title = getattr(w, "title", None) or (w.get("title") if isinstance(w, dict) else str(w))
            fields.append((f"Candidate {i + 1}", str(title)[:50]))
        return ActionOutcome(status=StatusLevel.LIMITED, title="Detect Hung Processes", fields=fields)
    return run_timed(body)


def _recommendations(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        eng = _engine(ctx)
        hung = ctx.state.get("healing_last_hung")
        if hung is None:
            hung = _find_hung(ctx)
        try:
            ram_critical = eng.is_ram_critical()
        except Exception:
            ram_critical = False
        lines = []
        if ram_critical:
            lines.append("- RAM usage is critical; consider running 'Run Healing Action' on the "
                          "heaviest non-protected process.")
        if hung:
            lines.append(f"- {len(hung)} hung window(s) detected; review 'Detect Hung Processes' "
                          "and run 'Run Healing Action' if appropriate.")
        if not lines:
            lines.append("No immediate recovery actions recommended.")
        status = StatusLevel.LIMITED if (ram_critical or hung) else StatusLevel.PASS
        return ActionOutcome(status=status, title="Recovery Recommendations", detail_lines=lines)
    return run_timed(body)


def _run_healing_action(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        eng = _engine(ctx)
        pid_raw = ctx.console.read_line("Enter target PID: ")
        try:
            pid = int(pid_raw)
        except ValueError:
            return ActionOutcome(status=StatusLevel.BLOCKED, title="Run Healing Action",
                                  error_reason=f"'{pid_raw}' is not a valid PID.")
        name = ctx.console.read_line("Enter process name: ")
        if not name:
            return ActionOutcome(status=StatusLevel.SKIPPED, title="Run Healing Action",
                                  detail_lines=["No process name entered."])
        # Direct call: HealingEngine.heal_hung_process() enforces its own
        # protected-process whitelist internally (see module docstring) --
        # no dispatcher/safety-gate wrapper is needed or invented here.
        report = eng.heal_hung_process(pid, name)
        success = bool(report.get("success"))
        status = StatusLevel.PASS if success else StatusLevel.FAILED
        fields = [("PID", str(pid)), ("Process", name), ("Success", str(success))]
        reclaimed = report.get("reclaimed_ram")
        if reclaimed is not None:
            fields.append(("Reclaimed RAM", f"{reclaimed:.1f} %"))
        reason = report.get("reason")
        return ActionOutcome(status=status, title="Run Healing Action", fields=fields,
                              error_reason=reason if not success else None)
    return run_timed(body)


def _telemetry(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        eng = _engine(ctx)
        log = eng.healing_log
        if not log:
            return ActionOutcome(status=StatusLevel.LIMITED, title="Healing Telemetry",
                                  detail_lines=["No healing actions recorded this session."])
        fields = []
        for entry in log[-5:]:
            fields.append((str(entry.get("name", "?")), f"success={entry.get('success')}"))
        return ActionOutcome(status=StatusLevel.PASS, title="Healing Telemetry", fields=fields)
    return run_timed(body)


def build_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="heal_snapshot", key="1", label="System Health Snapshot",
                   handler=lambda: _health_snapshot(ctx), safe_for_batch=True),
        MenuAction(id="heal_process", key="2", label="Process Health",
                   handler=lambda: _process_health(ctx), safe_for_batch=True),
        MenuAction(id="heal_detect", key="3", label="Detect Hung Processes",
                   handler=lambda: _detect_hung(ctx), safe_for_batch=True),
        MenuAction(id="heal_recommend", key="4", label="Recovery Recommendations",
                   handler=lambda: _recommendations(ctx), safe_for_batch=True),
        MenuAction(id="heal_run", key="5", label="Run Healing Action", read_only=False,
                   requires_target=True, requires_confirmation=True, side_effect_level="destructive",
                   safe_for_batch=False, handler=lambda: _run_healing_action(ctx),
                   help_text="Terminates one explicitly named process, after confirmation. Never "
                              "run automatically or as part of [A]."),
        MenuAction(id="heal_telemetry", key="6", label="Healing Telemetry",
                   handler=lambda: _telemetry(ctx), safe_for_batch=True),
    ]
    return MenuScreen(
        id="healing", title="SELF-HEALING", breadcrumb=["MAIN", "SELF-HEALING"],
        actions=actions, batch_label="Full Safe Health Assessment",
        help_intro="[A] never terminates a process -- only inspection/telemetry checks run.",
    )
