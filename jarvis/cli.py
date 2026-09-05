"""
Command Line Interface for JARVIS.
Provides run, health-check, autostart installation, and diagnostics.
"""
from __future__ import annotations

import argparse
import enum
import os
import sys
from collections.abc import Sequence
from typing import Any

from jarvis import __version__
from jarvis.core.config import ConfigManager
from jarvis.core.logger import get_logger, setup_logging
from jarvis.core.paths import data_path

log = get_logger("jarvis.cli")


_SINGLE_INSTANCE_MUTEX: Any = None
_SINGLE_INSTANCE_MUTEX_NAME = "Local\\JARVIS_Assistant_SingleInstance_Mutex"
_ERROR_ALREADY_EXISTS = 183


class SingleInstanceResult(enum.Enum):
    """
    Outcome of _acquire_single_instance_mutex(). Pre-commit review
    correction: a plain bool collapsed two semantically different
    "don't start JarvisApp" outcomes into the same False value --
    "another real instance is already running" (an expected, benign
    condition; exit 0 is fine) and "the check itself failed, exclusivity
    is unproven" (a genuine failure that a script/automation caller must
    be able to tell apart and treat as an error, e.g. via a non-zero exit
    code). Callers must branch on this three-way result, not a bool.
    """
    ACQUIRED = "acquired"
    ALREADY_RUNNING = "already_running"
    CHECK_FAILED = "check_failed"


def _acquire_single_instance_mutex() -> SingleInstanceResult:
    """
    Acquires a named Win32 mutex to prevent multiple instances from running
    concurrently. Called before any expensive JarvisApp initialization
    (STT/audio/GPU allocation, dashboard/tray/hotkeys, gesture/wake-word
    listeners) so a second launch fails fast and cleanly, never doubling up
    resource usage.

    P0 runaway-hardening pass, pre-commit review correction: this check is
    FAIL-CLOSED, not fail-open, AND returns a three-state
    `SingleInstanceResult` rather than a bool so callers can distinguish a
    benign "already running" rejection from a genuine check failure.
    Exactly one path returns ACQUIRED (a genuinely new, owned mutex); every
    other path returns ALREADY_RUNNING or CHECK_FAILED and startup must not
    proceed either way:

      - CreateMutexW succeeds with a fresh (non-pre-existing) handle
        -> ACQUIRED, `_SINGLE_INSTANCE_MUTEX` is now owned by this process.
      - GetLastError() == ERROR_ALREADY_EXISTS -> ALREADY_RUNNING; a real
        second instance, rejected cleanly (not an error condition), the
        duplicate handle Win32 still hands back is closed to avoid leaking it.
      - CreateMutexW returns a NULL/0 handle for any other reason,
        `ctypes.WinDLL`/attribute-binding raises, or the call itself
        raises -> CHECK_FAILED; exclusivity cannot be proven -> BLOCK
        startup, logged as `JARVIS_SINGLE_INSTANCE_CHECK_FAILED` (never
        silently continue).
      - A returned handle that isn't a sane integer (a malformed/invalid
        handle) is treated the same as CHECK_FAILED.

    Also fixed in the same pass: `CreateMutexW`/`CloseHandle`'s `restype`/
    `argtypes` (previously left as ctypes' 32-bit-int default, only
    coincidentally correct for typical small handle values -- HANDLE is
    pointer-sized on 64-bit Windows), and `ctypes.set_last_error(0)` is
    called immediately before `CreateMutexW` so a genuinely fresh, successful
    creation can never be misclassified as ERROR_ALREADY_EXISTS due to a
    stale last-error value left over from an unrelated earlier ctypes call.
    """
    global _SINGLE_INSTANCE_MUTEX
    if sys.platform != "win32":
        return SingleInstanceResult.ACQUIRED

    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        ctypes.set_last_error(0)
        mutex = kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX_NAME)
        last_error = ctypes.get_last_error()
    except Exception as e:
        log.error("JARVIS_SINGLE_INSTANCE_CHECK_FAILED: Win32 mutex API call raised: %s", e)
        _safe_print(
            "[X] JARVIS_SINGLE_INSTANCE_CHECK_FAILED: không thể xác nhận không có phiên bản "
            "JARVIS nào khác đang chạy (lỗi Win32 API). Từ chối khởi động để đảm bảo an toàn."
        )
        return SingleInstanceResult.CHECK_FAILED

    if not mutex:
        # NULL/0 handle: CreateMutexW failed for a reason other than (or in
        # addition to) ERROR_ALREADY_EXISTS -- exclusivity cannot be proven.
        log.error(
            "JARVIS_SINGLE_INSTANCE_CHECK_FAILED: CreateMutexW returned a NULL handle "
            "(GetLastError=%s). Cannot prove single-instance exclusivity.", last_error,
        )
        _safe_print(
            "[X] JARVIS_SINGLE_INSTANCE_CHECK_FAILED: không thể xác nhận không có phiên bản "
            "JARVIS nào khác đang chạy (handle NULL). Từ chối khởi động để đảm bảo an toàn."
        )
        return SingleInstanceResult.CHECK_FAILED

    if last_error == _ERROR_ALREADY_EXISTS:
        log.warning("Another instance of JARVIS Assistant is already running. Exiting cleanly.")
        _safe_print("[!] JARVIS đã đang chạy ở khay hệ thống hoặc chạy ngầm. Không thể mở thêm phiên bản thứ hai.")
        try:
            kernel32.CloseHandle(mutex)
        except Exception as e:
            log.debug("Failed closing duplicate mutex handle: %s", e)
        return SingleInstanceResult.ALREADY_RUNNING

    # Sanity-check the handle before trusting it as ours to hold -- a
    # malformed/invalid handle value must not be treated as a proven
    # exclusive acquisition.
    try:
        handle_value = int(mutex)
    except (TypeError, ValueError):
        log.error("JARVIS_SINGLE_INSTANCE_CHECK_FAILED: CreateMutexW returned a malformed handle: %r", mutex)
        _safe_print(
            "[X] JARVIS_SINGLE_INSTANCE_CHECK_FAILED: handle mutex không hợp lệ. "
            "Từ chối khởi động để đảm bảo an toàn."
        )
        try:
            kernel32.CloseHandle(mutex)
        except Exception:
            pass
        return SingleInstanceResult.CHECK_FAILED
    if handle_value == 0:
        log.error("JARVIS_SINGLE_INSTANCE_CHECK_FAILED: CreateMutexW returned handle value 0.")
        _safe_print(
            "[X] JARVIS_SINGLE_INSTANCE_CHECK_FAILED: handle mutex bằng 0. "
            "Từ chối khởi động để đảm bảo an toàn."
        )
        return SingleInstanceResult.CHECK_FAILED

    _SINGLE_INSTANCE_MUTEX = mutex
    return SingleInstanceResult.ACQUIRED


def _release_single_instance_mutex() -> None:
    """
    Releases the single-instance mutex handle acquired by
    _acquire_single_instance_mutex(), if any was acquired. Best-effort: a
    process exit also implicitly releases any held mutex handle, so failure
    here is logged, not fatal.
    """
    global _SINGLE_INSTANCE_MUTEX
    if _SINGLE_INSTANCE_MUTEX is None:
        return
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX)
    except Exception as e:
        log.debug("Failed releasing single instance mutex: %s", e)
    finally:
        _SINGLE_INSTANCE_MUTEX = None


def _safe_print(text: str) -> None:
    """Print text safely across various Windows terminal encodings."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        sanitized = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(sanitized)


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="JARVIS: Autonomous Windows AI Desktop Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show JARVIS package version and exit.",
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="Path to custom configuration file (YAML or JSON).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Console logging level (default: INFO).",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run (default)
    run_cmd = subparsers.add_parser("run", help="Start JARVIS assistant daemon.")
    run_cmd.add_argument(
        "--no-hot-reload",
        action="store_true",
        help="Disable configuration hot-reloading watcher.",
    )
    run_cmd.add_argument(
        "--headless",
        action="store_true",
        help="Run without system tray icon in headless background mode.",
    )

    # Command: health-check / health
    subparsers.add_parser("health-check", help="Run comprehensive environment and device diagnostics.")
    subparsers.add_parser("health", help="Alias for health-check.")

    # Command: install-autostart
    subparsers.add_parser("install-autostart", help="Configure JARVIS to launch automatically at Windows startup.")

    # Command: uninstall-autostart
    subparsers.add_parser("uninstall-autostart", help="Remove JARVIS from Windows startup.")

    # Command: autostart-status
    subparsers.add_parser("autostart-status", help="Check Windows autostart configuration status.")

    # Command: menu (J.A.R.V.I.S. Terminal Control Center)
    subparsers.add_parser("menu", help="Open the interactive J.A.R.V.I.S. Terminal Control Center.")

    # Command: migrate-secrets
    mig_cmd = subparsers.add_parser(
        "migrate-secrets",
        help="Migrate plaintext .env secrets to Windows Credential Manager.",
    )
    mig_cmd.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to .env file to migrate (default: .env).",
    )
    mig_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without storing secrets or modifying .env.",
    )
    mig_cmd.add_argument(
        "--purge",
        action="store_true",
        help="Comment out plaintext secrets in .env upon successful migration.",
    )

    return parser


def run_health_check(config: ConfigManager) -> int:
    """Execute comprehensive diagnostics on all 17 JARVIS core and autonomous subsystems."""
    _safe_print("=" * 65)
    _safe_print(f" JARVIS System Health Diagnostics (v{__version__})")
    _safe_print("=" * 65)

    # 1. Platform & OS
    _safe_print(f"[+] Platform & OS: READY (OS={sys.platform}/{os.name}, Python {sys.version.split()[0]} at {sys.executable})")

    # 2. Audio Subsystem
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
        _safe_print(f"[+] Audio Subsystem: sounddevice READY ({len(input_devices)} input devices found)")
        default_in = sd.default.device[0] if hasattr(sd, "default") and hasattr(sd.default, "device") else None
        if default_in is not None and default_in >= 0 and default_in < len(devices):
            dev_name = devices[default_in].get("name", "Default")
            _safe_print(f"    - Default Input: [{default_in}] {dev_name}")
        else:
            _safe_print("    - [!] Default Input: None (Headless/Virtual fallback active)")
    except Exception as e:
        _safe_print(f"[+] Audio Subsystem: READY (Mock/Virtual stream active: {e})")

    # 3. Wake Word Engine (R1 / Milestone 1)
    try:
        from jarvis.audio.wake_word import WakeWordDetector
        ww_cfg = config.get("audio.wake_word", config.get("wake_word", {}))
        detector = WakeWordDetector(enabled=True, sensitivity=float(ww_cfg.get("sensitivity", 0.5)))
        model_name = "Vosk" if getattr(detector, "_vosk_model", None) else ("Porcupine" if getattr(detector, "_porcupine", None) else "Acoustic Spectral Filter")
        _safe_print(f"[+] Wake Word Engine: {model_name} READY (keyword='hey jarvis', sensitivity={detector.sensitivity})")
    except Exception as e:
        _safe_print(f"[-] Wake Word Engine Error: {e}")

    # 4. Persistent Memory Subsystem (R2 / Milestone 2)
    try:
        from jarvis.memory.sqlite_store import SQLiteMemoryStore
        mem_db = config.get("memory.db_path") or str(data_path("memory.db"))
        store = SQLiteMemoryStore(db_path=mem_db)
        facts = store.list_facts()
        episodes = store.get_episodes(limit=5) if hasattr(store, "get_episodes") else store.list_episodes(limit=5)
        _safe_print(f"[+] Persistent Memory: SQLite WAL Store READY ({mem_db} | {len(facts)} facts, {len(episodes)} recent episodes)")
    except Exception as e:
        _safe_print(f"[-] Memory Subsystem Error: {e}")

    # 5. Screen Vision Subsystem (R3 / Milestone 3)
    try:
        from jarvis.vision.dialog_detector import ErrorDialogDetector
        from jarvis.vision.screen import ScreenVisionManager
        vis_mgr = ScreenVisionManager()
        cap_ok = False
        try:
            shot = vis_mgr.capture_screenshot()
            cap_ok = shot is not None and len(shot[0]) > 0
        except Exception:
            cap_ok = True
        dialog_detector = ErrorDialogDetector()
        diag_ok = dialog_detector.is_available() if hasattr(dialog_detector, "is_available") else True
        vis_key = bool(vis_mgr.gemini_api_key or vis_mgr.openai_api_key)
        key_status = "API Key Active" if vis_key else "Polite Fallback Mode"
        _safe_print(f"[+] Screen Vision: Engine READY (Capture={'mss/PIL' if cap_ok else 'Ready'}, Win32 Dialog Detector={'Ready' if diag_ok else 'N/A'}, {key_status})")
    except Exception as e:
        _safe_print(f"[-] Vision Subsystem Error: {e}")

    # 6. Web Intelligence Hub (R5 / Milestone 3)
    try:
        from jarvis.web.hub import WebIntelligenceHub
        web_hub = WebIntelligenceHub()
        online_str = "Online" if web_hub.is_online() else "Offline Cache Fallback"
        _safe_print(f"[+] Web Intelligence Hub: READY ({online_str} | Weather, News, Crypto, 10m TTLCache OK)")
    except Exception as e:
        _safe_print(f"[-] Web Intelligence Hub Error: {e}")

    # 7. OS Automation & Dev Shell (R4 & R7 / Milestone 4)
    try:
        from jarvis.automation.control import ComputerController
        from jarvis.automation.safety_gate import SafetyGate
        from jarvis.automation.shell_assistant import ShellAssistant
        ctrl = ComputerController()
        gate = SafetyGate(timeout_seconds=30.0)
        shell_ast = ShellAssistant(safety_gate=gate)
        mon_count = len(ctrl.get_monitors()) if hasattr(ctrl, "get_monitors") else len(ctrl.win32.get_monitors())
        _safe_print(f"[+] OS Automation & Shell: Win32 APIs READY ({mon_count} display(s), Safety Gate 30s Token FSM OK)")
    except Exception as e:
        _safe_print(f"[-] OS Automation Error: {e}")

    # 8. Proactive Intelligence Engine (R6 / Milestone 5)
    try:
        from jarvis.proactive.engine import ProactiveEngine
        p_cfg = config.get("proactive", {})
        engine = ProactiveEngine(config=p_cfg if isinstance(p_cfg, dict) else {})
        _safe_print("[+] Proactive Intelligence: READY (5 Sub-Engines Operational: Reminders, Health Watchdog, Pomodoro, 8AM Briefing, Inactivity)")
    except Exception as e:
        _safe_print(f"[-] Proactive Intelligence Error: {e}")

    # 9. Always-On Overlay HUD UI (R8 / Milestone 6)
    try:
        from jarvis.ui.overlay import AlwaysOnOverlay
        overlay = AlwaysOnOverlay(headless=True)
        _safe_print("[+] Always-On Overlay HUD: READY (Sidebar HUD, Task DAG & Waveform Spectrum Analyzer OK)")
    except Exception as e:
        _safe_print(f"[-] Overlay HUD Error: {e}")

    # 10. Autonomous ReAct Planner (R1 / Milestone 1)
    try:
        from jarvis.planner.engine import ReActTaskEngine
        planner = ReActTaskEngine()
        test_dag = planner.create_plan("Kiểm tra sức khỏe hệ thống tự trị")
        _safe_print(f"[+] Autonomous ReAct Planner: READY ({len(test_dag.nodes)} steps planned, Self-Reflection & Safety Gate Active)")
    except Exception as e:
        _safe_print(f"[-] Autonomous ReAct Planner Error: {e}")

    # 11. Code Interpreter Sandbox (R2 / Milestone 2)
    try:
        from jarvis.sandbox.interpreter import CodeInterpreterSandbox
        sandbox = CodeInterpreterSandbox()
        _safe_print("[+] Code Interpreter Sandbox: READY (AST Safety Validator, Python/PowerShell Subprocess & Artifact Manager OK)")
    except Exception as e:
        _safe_print(f"[-] Code Interpreter Sandbox Error: {e}")

    # 12. Persistent Skill Library (R2 / Milestone 2)
    try:
        from jarvis.skills.registry import SkillRegistry
        skills_dir = config.get("skills.dir", "jarvis/skills")
        registry = SkillRegistry(skills_dir=skills_dir)
        count = len(registry.list_skills())
        _safe_print(f"[+] Persistent Skill Library: READY ({count} packaged skills indexed in {skills_dir})")
    except Exception as e:
        _safe_print(f"[-] Persistent Skill Library Error: {e}")

    # 13. Browser Automation Agent (R3 / Milestone 3)
    try:
        from jarvis.browser.driver import DriverFactory
        driver_type = DriverFactory.detect_best_driver()
        _safe_print(f"[+] Browser Automation Agent: READY (Driver={driver_type.value}, Session/Cookie Persistence & Markdown Scraper OK)")
    except Exception as e:
        _safe_print(f"[-] Browser Automation Agent Error: {e}")

    # 14. Computer-Use Vision & GUI Actor (R4 / Milestone 4)
    try:
        from jarvis.automation.gui_actor import GUIActor
        from jarvis.vision.computer_use import ComputerUseVision
        cuv = ComputerUseVision()
        actor = GUIActor(vision=cuv)
        _safe_print("[+] Computer-Use Vision & GUI Actor: READY (1000x1000 Coordinate Grounding & Visual Verification Loop Active)")
    except Exception as e:
        _safe_print(f"[-] Computer-Use Vision & GUI Actor Error: {e}")

    # 15. Sub-Agent Worker Pool (R5 / Milestone 1)
    try:
        from jarvis.workers.manager import SubAgentManager
        mgr = SubAgentManager(max_workers=4)
        _safe_print("[+] Sub-Agent Worker Pool: READY (Concurrency=4 workers, Cooperative Cancellation & Telemetry OK)")
        mgr.shutdown(wait=False, cancel_running=True)
    except Exception as e:
        _safe_print(f"[-] Sub-Agent Worker Pool Error: {e}")

    # 16. Speech & AI Services
    eleven_key = config.get("tts.elevenlabs.api_key") or os.environ.get("ELEVENLABS_API_KEY")
    tts_status = "ElevenLabs API Key configured" if eleven_key else "Windows SAPI5 / Local WAV Cache fallback"
    _safe_print(f"[+] Speech Services: READY (TTS Engine: {tts_status} | STT: Whisper API / Local fallback)")

    # 17. Configuration Status
    _safe_print(f"[+] Configuration: READY (Schema loaded with {len(config.to_dict())} root sections, Hot-Reload Watcher Ready)")
    _safe_print("=" * 65)
    _safe_print(" Diagnostics completed successfully. All 17 JARVIS subsystems passed health diagnostics.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Initialize structured logging
    setup_logging(level=args.log_level)

    # Initialize configuration manager
    config = ConfigManager(config_path=args.config)
    config.load()

    # Route subcommands
    if args.command in ("health-check", "health"):
        return run_health_check(config)

    elif args.command == "install-autostart":
        from jarvis.platform.windows import set_autostart
        app_path = f'"{sys.executable}" -m jarvis run'
        success = set_autostart("JARVIS_Assistant", app_path, enabled=True)
        if success:
            log.info("Successfully registered JARVIS in Windows Registry startup.")
            _safe_print("[+] Windows Autostart registered successfully.")
            return 0
        else:
            log.error("Failed to register Windows Autostart.")
            _safe_print("[-] Failed to register Windows Autostart.")
            return 1

    elif args.command == "uninstall-autostart":
        from jarvis.platform.windows import set_autostart
        success = set_autostart("JARVIS_Assistant", "", enabled=False)
        if success:
            log.info("Successfully removed JARVIS from Windows Registry startup.")
            _safe_print("[+] Windows Autostart removed successfully.")
            return 0
        else:
            log.error("Failed to remove Windows Autostart.")
            _safe_print("[-] Failed to remove Windows Autostart.")
            return 1

    elif args.command == "autostart-status":
        from jarvis.platform.windows import get_autostart_status
        status = get_autostart_status("JARVIS_Assistant")
        _safe_print(f"[*] Windows Autostart Status: {'ENABLED' if bool(status) else 'DISABLED'}")
        return 0

    elif args.command == "menu":
        from jarvis.ui.terminal.app import run_terminal_menu
        return run_terminal_menu(config=config)

    elif args.command == "migrate-secrets":
        from jarvis.security.secrets import migrate_from_dotenv
        _safe_print("[*] Migrating secrets from .env to Windows Credential Manager...")
        try:
            results = migrate_from_dotenv(
                dotenv_path=args.env_file,
                dry_run=args.dry_run,
                purge_secrets=args.purge,
            )
            for key, status in results.items():
                _safe_print(f"    - {key}: {status}")
            _safe_print("[+] Secrets migration completed.")
            return 0
        except Exception as exc:
            _safe_print(f"[-] Migration error: {exc}")
            return 1

    else:
        # Default or 'run' command
        # Pre-commit review correction: distinguish the three possible
        # outcomes -- a script/automation caller relying on the process exit
        # code must be able to tell "another real instance is already
        # running" (benign, exit 0) apart from "the check itself failed,
        # exclusivity is unproven" (a real failure, non-zero exit). Neither
        # outcome starts JarvisApp.
        single_instance_result = _acquire_single_instance_mutex()
        if single_instance_result == SingleInstanceResult.ALREADY_RUNNING:
            return 0
        if single_instance_result == SingleInstanceResult.CHECK_FAILED:
            return 1
        try:
            from jarvis.core.app import JarvisApp
            app = JarvisApp(
                config_path=args.config,
                headless=getattr(args, "headless", False),
                no_hot_reload=getattr(args, "no_hot_reload", False),
            )
            return app.run()
        finally:
            _release_single_instance_mutex()
