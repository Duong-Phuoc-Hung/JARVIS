"""
jarvis/ui/terminal/app.py
============================
J.A.R.V.I.S. Terminal Control Center -- top-level orchestrator.

This module is a thin presentation + routing layer. It does not
reimplement any business logic: every action handler in jarvis/ui/terminal
/modules/*.py calls straight into the existing product modules
(jarvis.hardware, jarvis.security, jarvis.automation, jarvis.data,
jarvis.smart_home, jarvis.vision.biometrics, jarvis.gesture, jarvis.comms,
jarvis.healing). The only "new" business logic here is presentation
(rendering, navigation, batching, report writing) -- never a second
safety/security decision. SafetyGate / ActionDispatcher / RBAC remain the
sole authorization boundary for anything side-effecting.

[J] START JARVIS delegates to the exact same jarvis.core.app.JarvisApp
used by `jarvis run` -- there is only ever one JARVIS core. Because
JarvisApp.run() blocks until shutdown and is not designed to be safely
re-constructed multiple times within one process (single-instance mutex,
global hotkeys, tray icon, etc.), pressing [J] and later shutting JARVIS
down (Ctrl+C) exits the terminal menu process entirely, exactly as if the
user had run `jarvis run` directly -- it does not attempt to resume the
interactive menu afterward. This is documented behavior, not an
oversight.
"""
from __future__ import annotations

import sys
import time
from collections.abc import Callable

from jarvis import __version__ as JARVIS_VERSION
from jarvis.core.config import ConfigManager
from jarvis.ui.terminal import logo
from jarvis.ui.terminal.console import TerminalConsole
from jarvis.ui.terminal.context import TerminalContext
from jarvis.ui.terminal.models import (
    ActionOutcome,
    BatchItemResult,
    BatchResult,
    MenuAction,
    MenuScreen,
)
from jarvis.ui.terminal.modules import (
    biometrics,
    comms,
    data,
    gesture,
    hardware,
    healing,
    infosec,
    smart_home,
    workflow,
)
from jarvis.ui.terminal.navigator import TerminalNavigator
from jarvis.ui.terminal.report import ReportWriter
from jarvis.ui.terminal.session import SessionHistory
from jarvis.ui.terminal.theme import StatusLevel, TerminalTheme

ROOT_SCREEN_ID = "main"

_MODULE_MENU_ORDER = [
    ("1", "hardware", "Hardware Diagnostics", "CPU - GPU - RAM - Storage - SMART - Sensors"),
    ("2", "infosec", "InfoSec Auditing", "LAN Security - Nmap - Packet Analysis - Security Reports"),
    ("3", "workflow", "Workflow Automation", "Windows - Workspace - Shell - GUI Automation"),
    ("4", "data", "Data Analysis", "Statistics - Dataset - Documents - Visualization"),
    ("5", "smart_home", "Smart Home", "Home Assistant - Entities - Device Control"),
    ("6", "biometrics", "Biometric Security", "Face Recognition - Verification - Surveillance"),
    ("7", "gesture", "Gesture Control", "MediaPipe - Camera - Gesture Mapping"),
    ("8", "comms", "Communications Hub", "Telegram - Discord - Email"),
    ("9", "healing", "Self-Healing", "System Health - Processes - Recovery - Telemetry"),
]

_MODULE_BUILDERS: dict[str, Callable[[TerminalContext], MenuScreen]] = {
    "hardware": hardware.build_menu,
    "hardware_storage": hardware.build_storage_menu,
    "infosec": infosec.build_menu,
    "workflow": workflow.build_menu,
    "data": data.build_menu,
    "smart_home": smart_home.build_menu,
    "biometrics": biometrics.build_menu,
    "gesture": gesture.build_menu,
    "comms": comms.build_menu,
    "comms_telegram": comms.build_telegram_menu,
    "comms_discord": comms.build_discord_menu,
    "comms_email": comms.build_email_menu,
    "healing": healing.build_menu,
}

_MODULE_LABELS = {mid: label for _, mid, label, _ in _MODULE_MENU_ORDER}


class _ExitRequested(Exception):
    pass


def _build_main_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id=f"main_{mid}", key=key, label=label, description=desc,
                   is_submenu=True, submenu_id=mid)
        for key, mid, label, desc in _MODULE_MENU_ORDER
    ]
    return MenuScreen(id=ROOT_SCREEN_ID, title="MAIN", breadcrumb=["MAIN"], actions=actions)


def _resolve(ctx: TerminalContext, screen_id: str) -> MenuScreen:
    if screen_id == ROOT_SCREEN_ID:
        return _build_main_menu(ctx)
    builder = _MODULE_BUILDERS.get(screen_id)
    if builder is None:
        return _build_main_menu(ctx)
    return builder(ctx)


class TerminalApp:
    """Drives the interactive session. All rendering goes through
    `console`/`theme` so a headless/no-color/narrow terminal degrades
    cleanly instead of crashing."""

    def __init__(
        self,
        config: ConfigManager | None = None,
        console: TerminalConsole | None = None,
        theme: TerminalTheme | None = None,
        start_jarvis: Callable[[], bool] | None = None,
        session_started_at: float | None = None,
    ) -> None:
        self.theme = theme or TerminalTheme()
        self.console = console or TerminalConsole(theme=self.theme)
        self.session = SessionHistory()
        self.report_writer = ReportWriter()
        cfg = config
        if cfg is None:
            cfg = ConfigManager()
            try:
                cfg.load()
            except Exception:
                pass
        self.ctx = TerminalContext(
            theme=self.theme, console=self.console, session=self.session,
            report_writer=self.report_writer, config=cfg,
            start_jarvis=start_jarvis or self._default_start_jarvis,
        )
        self.navigator = TerminalNavigator(resolve=lambda sid: _resolve(self.ctx, sid), root_id=ROOT_SCREEN_ID)
        self.session_started_at = session_started_at or time.time()

    # -- [J] delegation -------------------------------------------------
    def _default_start_jarvis(self) -> bool:
        """The one and only JarvisApp construction path. Never called more
        than once per process (see module docstring). Returns True only if
        JarvisApp actually ran (and has since shut down) -- the caller uses
        this, not a side-effect flag, to decide whether to exit the
        terminal menu afterward.

        Pre-commit review correction: `_acquire_single_instance_mutex()`
        returns a three-state `SingleInstanceResult`, not a bool -- this
        must branch on it explicitly rather than truth-testing the enum
        member directly (which would always be truthy and silently start
        JarvisApp regardless of outcome). ALREADY_RUNNING and CHECK_FAILED
        are reported with distinct, truthful messages; neither ever starts
        JarvisApp -- CHECK_FAILED is never reinterpreted as a successful
        acquisition.

        Pre-commit audit correction: a successful ACQUIRED result must be
        released exactly once when the delegated JarvisApp session ends --
        mirroring jarvis/cli.py::main()'s own acquire/try-finally/release
        pattern around JarvisApp(...).run(). Without this, the mutex handle
        acquired here stayed held by this process for the rest of its
        lifetime, so no other JARVIS instance (including a future `[J]`
        invocation in a fresh process) could ever acquire it again, even
        after the delegated JarvisApp had fully shut down."""
        from jarvis.cli import SingleInstanceResult, _acquire_single_instance_mutex, _release_single_instance_mutex
        from jarvis.core.app import JarvisApp

        result = _acquire_single_instance_mutex()
        if result == SingleInstanceResult.ALREADY_RUNNING:
            self.console.print(self.theme.warn("[!] JARVIS is already running elsewhere. Not starting a second instance."))
            return False
        if result == SingleInstanceResult.CHECK_FAILED:
            self.console.print(self.theme.warn(
                "[!] Could not verify no other JARVIS instance is running (single-instance check failed). "
                "Refusing to start for safety."
            ))
            return False
        try:
            app = JarvisApp(config_path=self.ctx.config.config_path if hasattr(self.ctx.config, "config_path") else None)
            app.run()
        finally:
            _release_single_instance_mutex()
        return True

    # -- rendering --------------------------------------------------------
    def _status_header(self) -> list[str]:
        session_elapsed = int(time.time() - self.session_started_at)
        h, rem = divmod(session_elapsed, 3600)
        m, s = divmod(rem, 60)
        t = self.theme
        return [
            f"Version        : {JARVIS_VERSION}",
            f"Platform       : {'Windows' if sys.platform == 'win32' else sys.platform}",
            f"Core           : {t.status(StatusLevel.AVAILABLE)}",
            f"Session        : {h:02d}:{m:02d}:{s:02d}",
        ]

    def _breadcrumb_line(self, screen: MenuScreen) -> str:
        t = self.theme
        prefix = t.breadcrumb_prefix("PATH // ")
        parts = screen.breadcrumb
        if not parts:
            return prefix
        path_parts = [t.breadcrumb_path(p) for p in parts[:-1]]
        current = t.breadcrumb_current(parts[-1])
        joined = " > ".join([*path_parts, current]) if path_parts else current
        return prefix + joined

    def _render_screen(self, screen: MenuScreen) -> None:
        c, t = self.console, self.theme
        if screen.id == ROOT_SCREEN_ID:
            c.print_lines(logo.render_logo(t, width=c.width()))
            c.print()
            c.print_lines(self._status_header())
            c.print()
        else:
            c.print(self._breadcrumb_line(screen))
            c.print()
        c.separator()
        for action in screen.actions:
            key_disp = t.key(f"[{action.key.upper()}]")
            if not action.available:
                label = t.dim(f"{action.label} ({action.unavailable_reason or 'unavailable'})")
            else:
                label = t.title(action.label)
            c.print(f" {key_disp} {label}")
            if action.description:
                c.print(f"     {t.desc(action.description)}")
        c.print()
        c.separator()
        self._render_global_keys(screen)

    def _render_global_keys(self, screen: MenuScreen, extra: list[str] | None = None) -> None:
        c, t = self.console, self.theme
        parts = []
        if screen.batch_visible():
            parts.append(f"{t.key_a('[A]')} {screen.batch_label}")
        parts.append(f"{t.key_j('[J]')} START JARVIS")
        parts.append(f"{t.key_r('[R]')} Refresh")
        if self._has_savable(screen):
            parts.append(f"{t.key_s('[S]')} Save")
        parts.append(f"{t.key('[H]')} Help")
        if not self.navigator.at_root:
            parts.append(f"{t.key_b('[B]')} Back")
        parts.append(f"{t.key('[0]')} Exit")
        c.print()
        for p in parts:
            c.print(f" {p}")
        c.print()

    def _has_savable(self, screen: MenuScreen) -> bool:
        return bool(self.ctx.state.get("last_outcome")) or bool(self.session.for_module(self._module_label(screen)))

    def _module_label(self, screen: MenuScreen) -> str:
        top = screen.breadcrumb[1] if len(screen.breadcrumb) > 1 else screen.breadcrumb[0]
        return top

    # -- confirmation -----------------------------------------------------
    def _confirm(self, prompt: str) -> bool:
        c, t = self.console, self.theme
        try:
            key = c.read_key({"y", "n"}, f"{prompt} [Y/N]: ")
        except (KeyboardInterrupt, EOFError):
            return False
        return key == "y"

    # -- [J] flow -----------------------------------------------------------
    def _handle_start_jarvis(self) -> bool:
        """Returns True if the whole terminal app should now exit (JARVIS
        was actually started and has since shut down)."""
        c, t = self.console, self.theme
        c.print()
        c.print(t.warn("Start JARVIS Voice Core? [Y/N]"))
        if not self._confirm("Confirm"):
            c.print(t.dim("Cancelled."))
            return False
        c.print(t.success("Starting JARVIS core... (Ctrl+C in this window stops it)"))
        started = False
        try:
            started = self.ctx.start_jarvis()
        except KeyboardInterrupt:
            started = True  # JarvisApp was running and was interrupted; it already shut down
        if started:
            c.print()
            c.print(t.header("JARVIS core has shut down. Exiting the Terminal Control Center."))
            return True
        return False

    # -- action execution ---------------------------------------------------
    def _run_action(self, action: MenuAction, module: str) -> ActionOutcome:
        if action.requires_confirmation:
            c, t = self.console, self.theme
            c.print()
            c.print(t.error("WARNING"))
            c.print(f"This operation may have real effects: {action.label}")
            if not self._confirm("Confirmation required. Proceed"):
                return ActionOutcome(status=StatusLevel.SKIPPED, title=action.label,
                                      detail_lines=["Cancelled by user."])
        assert action.handler is not None
        outcome = action.handler()
        self.session.record(module, action.label, outcome)
        self.ctx.state["last_outcome"] = (module, action, outcome)
        return outcome

    def _print_outcome(self, module: str, outcome: ActionOutcome) -> None:
        c, t = self.console, self.theme
        c.print()
        c.separator()
        c.print(f" RESULT // {module} > {outcome.title}")
        c.separator()
        c.print()
        c.print(f" STATUS       : {t.status(outcome.status)}")
        c.print(f" DURATION     : {outcome.duration_s:.2f}s")
        c.print()
        for key, value in outcome.fields:
            c.print(f" {key:<16}: {value}")
        if outcome.error_reason:
            c.print()
            c.print(t.error(" Reason:"))
            c.print(f" {outcome.error_reason}")
        for line in outcome.detail_lines:
            c.print(f" {line}")
        c.print()
        c.separator()

    def _result_loop(self, module: str, action: MenuAction, outcome: ActionOutcome) -> None:
        c, t = self.console, self.theme
        while True:
            self._print_outcome(module, outcome)
            parts = [f"{t.key_r('[R]')} Retry", f"{t.key_j('[J]')} START JARVIS",
                     f"{t.key_s('[S]')} Save Result", f"{t.key('[H]')} Help",
                     f"{t.key_b('[B]')} Back", f"{t.key('[0]')} Exit"]
            c.print()
            for p in parts:
                c.print(f" {p}")
            c.print()
            try:
                key = c.read_key({"r", "j", "s", "h", "b", "0"}, "Select > ")
            except KeyboardInterrupt:
                return
            except EOFError:
                raise _ExitRequested()
            if key == "b" or key == "":
                return
            if key == "0":
                raise _ExitRequested()
            if key == "j":
                if self._handle_start_jarvis():
                    raise _ExitRequested()
                continue
            if key == "r":
                outcome = self._run_action(action, module)
                continue
            if key == "s":
                result = self.report_writer.save_single_result(module, action.label, outcome)
                self._print_save_result(result)
                continue
            if key == "h":
                self._show_help_text([f"{action.label}: {action.help_text or action.description}"])
                continue

    def _print_save_result(self, result) -> None:
        c, t = self.console, self.theme
        c.print()
        if result.saved:
            c.print(t.success(f"[+] Saved: {result.path}"))
        else:
            c.print(t.error(f"[X] Save failed: {result.error}"))
        c.print()

    # -- batch --------------------------------------------------------------
    def _run_batch(self, screen: MenuScreen, module: str) -> BatchResult:
        eligible = screen.batch_eligible()
        started = time.time()
        items: list[BatchItemResult] = []
        c, t = self.console, self.theme
        c.print()
        c.print(f" J.A.R.V.I.S. // {module} FULL DIAGNOSTIC")
        c.separator()
        total = len(eligible)
        for i, action in enumerate(eligible, start=1):
            outcome = action.handler()  # type: ignore[misc]
            self.session.record(module, action.label, outcome)
            items.append(BatchItemResult(action=action, outcome=outcome))
            c.print(f" [{i}/{total}] {action.label:.<40} {t.status(outcome.status)}")
        duration = time.time() - started
        batch = BatchResult(module=module, operation=screen.batch_label, items=items,
                             duration_s=duration, started_at=started)
        self.ctx.state["last_batch"] = batch
        return batch

    def _print_batch_summary(self, batch: BatchResult) -> None:
        c, t = self.console, self.theme
        counts = batch.counts()
        c.print()
        c.separator()
        c.print(f" Completed : {len(batch.items)}")
        for status_name, count in sorted(counts.items()):
            c.print(f" {status_name:<10}: {count}")
        c.print(f" Duration  : {batch.duration_s:.2f} s")
        c.separator()

    def _batch_loop(self, screen: MenuScreen, module: str) -> None:
        c, t = self.console, self.theme
        batch = self._run_batch(screen, module)
        while True:
            self._print_batch_summary(batch)
            parts = [f"{t.key_r('[R]')} Run Again", f"{t.key_s('[S]')} Save Report",
                     f"{t.key_j('[J]')} Start JARVIS", f"{t.key_b('[B]')} Back", f"{t.key('[0]')} Exit"]
            c.print()
            for p in parts:
                c.print(f" {p}")
            c.print()
            try:
                key = c.read_key({"r", "j", "s", "b", "0"}, "Select > ")
            except KeyboardInterrupt:
                return
            except EOFError:
                raise _ExitRequested()
            if key == "b" or key == "":
                return
            if key == "0":
                raise _ExitRequested()
            if key == "j":
                if self._handle_start_jarvis():
                    raise _ExitRequested()
                continue
            if key == "r":
                batch = self._run_batch(screen, module)
                continue
            if key == "s":
                result = self.report_writer.save_batch_result(batch)
                self._print_save_result(result)
                continue

    # -- save flow ------------------------------------------------------------
    def _save_flow(self, screen: MenuScreen) -> None:
        module = self._module_label(screen)
        last = self.ctx.state.get("last_outcome")
        module_records = self.session.for_module(module)
        options: list[tuple[str, str]] = []
        if last:
            options.append(("1", "Save Current Result"))
        options.append(("2", "Save Current Module Session"))
        options.append(("3", "Save Entire JARVIS CLI Session"))
        c, t = self.console, self.theme
        c.print()
        c.print(t.header("SAVE REPORT"))
        for key, label in options:
            c.print(f" {t.key(f'[{key}]')} {label}")
        c.print(f" {t.key_b('[B]')} Back")
        c.print()
        valid = {opt[0] for opt in options} | {"b"}
        try:
            key = c.read_key(valid, "Select > ")
        except (KeyboardInterrupt, EOFError):
            return
        if key == "1" and last:
            _, action, outcome = last
            result = self.report_writer.save_single_result(module, action.label, outcome)
        elif key == "2":
            result = self.report_writer.save_module_session(module, module_records)
        elif key == "3":
            result = self.report_writer.save_full_session(self.session.all())
        else:
            return
        self._print_save_result(result)

    # -- help -------------------------------------------------------------
    def _show_help_text(self, lines: list[str]) -> None:
        c, t = self.console, self.theme
        c.print()
        c.print(t.header("HELP"))
        c.separator()
        for line in lines:
            c.print(f" {line}")
        c.separator()
        c.print()

    def _show_screen_help(self, screen: MenuScreen) -> None:
        lines = [f"HELP // {' > '.join(screen.breadcrumb)}", ""]
        if screen.help_intro:
            lines.append(screen.help_intro)
            lines.append("")
        for action in screen.actions:
            lines.append(f"{action.label}")
            lines.append(f"    {action.help_text or action.description or '(no description)'}")
        lines.append("")
        lines.append("[A]  Runs all diagnostics on this screen that are safe for batch execution.")
        lines.append("[S]  Saves a result/session to the JARVIS report directory.")
        lines.append("[B]  Returns to the previous menu.")
        self._show_help_text(lines)

    # -- main loop ----------------------------------------------------------
    def run(self) -> int:
        c, t = self.console, self.theme
        try:
            while not self.navigator.exited:
                screen = self.navigator.current
                self._render_screen(screen)
                valid_keys = {a.key.lower() for a in screen.actions}
                valid_keys |= {"j", "r", "h", "0"}
                if screen.batch_visible():
                    valid_keys.add("a")
                if self._has_savable(screen):
                    valid_keys.add("s")
                if not self.navigator.at_root:
                    valid_keys.add("b")
                try:
                    key = c.read_key(valid_keys, "Choose a menu option using your keyboard: ")
                except KeyboardInterrupt:
                    c.print()
                    c.print(t.warn("Interrupted. Exiting Terminal Control Center."))
                    return 0
                except EOFError:
                    return 0

                if key not in valid_keys:
                    continue  # invalid input: stay at current screen

                if key == "0":
                    return 0
                if key == "b":
                    self.navigator.pop()
                    continue
                if key == "h":
                    self._show_screen_help(screen)
                    continue
                if key == "j":
                    if self._handle_start_jarvis():
                        return 0
                    continue
                if key == "r":
                    continue  # screens are rebuilt fresh on every render
                if key == "a":
                    module = self._module_label(screen)
                    self._batch_loop(screen, module)
                    continue
                if key == "s":
                    self._save_flow(screen)
                    continue

                action = next((a for a in screen.actions if a.key.lower() == key), None)
                if action is None or not action.available:
                    continue
                if action.is_submenu and action.submenu_id:
                    self.navigator.push(action.submenu_id)
                    continue
                if action.handler is not None:
                    module = self._module_label(screen)
                    outcome = self._run_action(action, module)
                    self._result_loop(module, action, outcome)
        except _ExitRequested:
            return 0
        return 0


def run_terminal_menu(config: ConfigManager | None = None) -> int:
    """Entry point used by `jarvis menu` (jarvis/cli.py)."""
    app = TerminalApp(config=config)
    return app.run()
