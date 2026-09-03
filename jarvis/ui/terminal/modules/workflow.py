"""
jarvis/ui/terminal/modules/workflow.py
=========================================
Workflow Automation module adapter. Presents backend AVAILABILITY only --
no shell command execution, window manipulation, or GUI actions are
performed from this screen. All checks are read-only capability probes.
"""
from __future__ import annotations

from jarvis.automation.control import ComputerController
from jarvis.automation.shell_assistant import ShellAssistant
from jarvis.ui.terminal.context import TerminalContext, run_timed
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.theme import StatusLevel

MODULE = "WORKFLOW"


def _windows_control(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            controller = ComputerController()
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="Windows Control", error_reason=str(e))
        fields: list[tuple[str, str]] = []
        limited = False
        try:
            monitors = controller.get_monitors()
            fields.append(("Monitors", str(len(monitors))))
        except Exception:
            fields.append(("Monitors", "N/A"))
            limited = True
        try:
            fields.append(("Volume", f"{controller.get_volume()} %"))
        except Exception:
            fields.append(("Volume", "N/A"))
            limited = True
        try:
            active = controller.get_active_window()
            fields.append(("Active Window", str(active.get("title", "N/A"))[:40]))
        except Exception:
            fields.append(("Active Window", "N/A"))
            limited = True
        status = StatusLevel.LIMITED if limited else StatusLevel.PASS
        return ActionOutcome(status=status, title="Windows Control", fields=fields)
    return run_timed(body)


def _workspace_management(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        return ActionOutcome(
            status=StatusLevel.OFFLINE, title="Workspace Management",
            detail_lines=["NOT CONFIGURED -- no dedicated workspace-management backend exists in "
                          "this codebase. Project/workspace assistance is currently routed through "
                          "the LLM intent router's rule fast-path, not a standalone module."],
        )
    return run_timed(body)


def _shell_assistant(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            assistant = ShellAssistant()
            is_dest = assistant.is_destructive("echo test")
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="Shell Assistant", error_reason=str(e))
        fields = [("Backend", "AVAILABLE"), ("Destructive-command detection", "ACTIVE")]
        detail = ["Live command execution is intentionally not exposed from this menu -- "
                  "see follow-up findings in docs/PROJECT_STATE.md."]
        return ActionOutcome(status=StatusLevel.AVAILABLE, title="Shell Assistant", fields=fields,
                              detail_lines=detail)
    return run_timed(body)


def _gui_automation(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            from jarvis.automation.gui_actor import GUIActor
            actor = GUIActor()
        except Exception as e:
            return ActionOutcome(status=StatusLevel.LIMITED, title="GUI Automation",
                                  detail_lines=[f"Backend unavailable: {e}"])
        history_len = len(actor.action_history) if hasattr(actor, "action_history") else 0
        fields = [("Backend", "AVAILABLE"), ("Actions this session", str(history_len))]
        return ActionOutcome(status=StatusLevel.AVAILABLE, title="GUI Automation", fields=fields)
    return run_timed(body)


def _lab_workflow(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        return ActionOutcome(
            status=StatusLevel.OFFLINE, title="Lab Workflow",
            detail_lines=["NOT CONFIGURED -- automatic VM (VMware/VirtualBox) launch and network "
                          "bridging described in early planning documents has no mature "
                          "implementation in this codebase."],
        )
    return run_timed(body)


def _automation_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        win = _windows_control(ctx)
        shell = _shell_assistant(ctx)
        gui = _gui_automation(ctx)
        fields = [
            ("Windows Control", win.status.value),
            ("Shell Assistant", shell.status.value),
            ("GUI Automation", gui.status.value),
            ("Workspace Management", "OFFLINE"),
            ("Lab Workflow", "OFFLINE"),
        ]
        worst = StatusLevel.PASS
        for s in (win.status, shell.status, gui.status):
            if s in (StatusLevel.ERROR, StatusLevel.FAILED):
                worst = StatusLevel.ERROR
                break
            if s == StatusLevel.LIMITED:
                worst = StatusLevel.LIMITED
        return ActionOutcome(status=worst, title="Automation Status", fields=fields)
    return run_timed(body)


def build_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="wf_windows", key="1", label="Windows Control",
                   description="Monitors, volume, active window (read-only)",
                   handler=lambda: _windows_control(ctx), safe_for_batch=True,
                   help_text="Read-only status via jarvis.automation.control.ComputerController."),
        MenuAction(id="wf_workspace", key="2", label="Workspace Management",
                   description="Project/workspace assistant status",
                   handler=lambda: _workspace_management(ctx), safe_for_batch=False,
                   available=False, unavailable_reason="No dedicated backend implemented.",
                   help_text="No dedicated workspace-management module exists yet."),
        MenuAction(id="wf_shell", key="3", label="Shell Assistant",
                   description="Natural-language shell backend status",
                   handler=lambda: _shell_assistant(ctx), safe_for_batch=True,
                   help_text="Reports availability only -- does not execute shell commands."),
        MenuAction(id="wf_gui", key="4", label="GUI Automation",
                   description="Computer-use / GUI actor backend status",
                   handler=lambda: _gui_automation(ctx), safe_for_batch=True,
                   help_text="Reports availability only -- does not click or type."),
        MenuAction(id="wf_lab", key="5", label="Lab Workflow",
                   description="VM/lab automation status",
                   handler=lambda: _lab_workflow(ctx), safe_for_batch=False,
                   available=False, unavailable_reason="No dedicated backend implemented.",
                   help_text="No VM/lab-automation backend exists yet."),
        MenuAction(id="wf_status", key="6", label="Automation Status",
                   description="Aggregate status of all workflow backends",
                   handler=lambda: _automation_status(ctx), safe_for_batch=False,
                   help_text="Summarizes the checks above in one view."),
    ]
    return MenuScreen(
        id="workflow", title="WORKFLOW AUTOMATION", breadcrumb=["MAIN", "WORKFLOW"],
        actions=actions, batch_label="Check All Safe Backends",
        help_intro="Read-only capability checks only. No shell commands, window actions, VM "
                   "launches, or network reconfiguration are ever run from this menu or from [A].",
    )
