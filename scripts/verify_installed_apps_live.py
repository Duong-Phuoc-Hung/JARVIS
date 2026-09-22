"""Opt-in live Windows probe. Opens only Calculator/Notepad, never closes apps.

Run from repository root: python -m scripts.verify_installed_apps_live --run
Evidence is local, count-only inventory and process/window IDs; no window titles,
mail, document contents, credentials or full application list are collected.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Allow opening Calculator and Notepad on this Windows desktop")
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required; no application was opened")
    if sys.platform != "win32":
        parser.error("This probe requires Windows")

    from jarvis.automation.control import ComputerController
    from jarvis.core.app import JarvisApp
    from jarvis.core.dispatcher import ActionDispatcher
    from jarvis.llm.router import LLMIntentRouter

    controller = ComputerController()
    start = monotonic()
    entries = controller.app_catalog.refresh()
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "text router -> real dispatcher -> real app handler -> Windows; not microphone/full startup/installer",
        "inventory": {"entries": len(entries), "errors": controller.app_catalog.errors,
                      "elapsed_seconds": round(monotonic() - start, 3)},
        "cases": [],
    }
    app = object.__new__(JarvisApp)
    app.computer_controller = controller
    dispatcher = ActionDispatcher()
    dispatcher.register_action("app_open", app._handle_app_open)
    router = LLMIntentRouter(llm_client=None, dispatcher=dispatcher)
    cases = [
        ("mở ứng dụng Calculator", "Calculator", True, None),
        ("mở Calculator", "Calculator", False, "LAUNCH_RATE_LIMITED"),
        ("mở ứng dụng Notepad", "Notepad", True, None),
        ("mở Notepad", "Notepad", False, "LAUNCH_RATE_LIMITED"),
        ("mở ứng dụng JarvisMissingApp_LiveProbe_20260922", None, False, "APP_NOT_FOUND"),
    ]
    for command, name, expected_success, expected_code in cases:
        intent = router.parse_intent(command)
        started = monotonic()
        # No LLM and only app_open is registered: arbitrary tools cannot execute.
        result = router.execute_intent(intent)
        observed = []
        if name:
            observed = [controller.app_launcher.probe.find(entry) for entry in controller.app_catalog.resolve(name)]
        outcome = {
            "command": command, "action": intent.action_name,
            "installed_only": intent.parameters.get("installed_only"),
            "success": result.success, "status": result.status.value, "code": result.error_code,
            "observed_windows": observed, "elapsed_seconds": round(monotonic() - started, 3),
            "passed": (intent.parameters.get("installed_only") is True and
                       result.success == expected_success and result.error_code == expected_code and
                       (not expected_success or any(observed))),
        }
        # Include verification from real handler, not a reconstructed success.
        if isinstance(result.data, dict):
            backend = result.data.get("result", {})
            if isinstance(backend, dict):
                outcome["backend_verification"] = backend.get("verification")
                outcome["already_running"] = backend.get("already_running")
        report["cases"].append(outcome)
    for command in ("đừng mở ứng dụng Calculator", "mở ứng dụng Notepad và Calculator"):
        intent = router.parse_intent(command)
        report["cases"].append({"command": command, "parse_only": True,
                                "action": intent.action_name, "passed": intent.action_name == "unknown_intent"})
    # Check reuse inside this same desktop session; never close a user process.
    calculator = controller.app_catalog.resolve("Calculator")
    before = controller.app_launcher.probe.find(calculator[0]) if len(calculator) == 1 else None
    reuse_case = {"command": "mở Calculator (existing minimized window)", "passed": False}
    if before:
        from jarvis.core.runaway_guard import launch_dedupe_guard
        sleep(launch_dedupe_guard.default_cooldown_s + 0.1)
        try:
            controller.win32.minimize_window(before["hwnd"])
            state = [w for w in controller.win32.list_windows(min_size=(0, 0)) if w.hwnd == before["hwnd"]]
            minimized_before = bool(state and state[0].is_minimized)
            result = router.execute_intent(router.parse_intent("mở Calculator"))
            backend = result.data.get("result", {}) if isinstance(result.data, dict) else {}
            state = [w for w in controller.win32.list_windows(min_size=(0, 0)) if w.hwnd == before["hwnd"]]
            reuse_case.update({"minimized_before": minimized_before, "success": result.success,
                               "already_running": backend.get("already_running"),
                               "same_hwnd": backend.get("hwnd") == before["hwnd"],
                               "restored": bool(state and not state[0].is_minimized),
                               "backend_verification": backend.get("verification")})
            reuse_case["passed"] = bool(result.success and minimized_before and backend.get("already_running")
                                       and reuse_case["same_hwnd"] and reuse_case["restored"])
        finally:
            controller.win32.focus_window(before["hwnd"])
    report["cases"].append(reuse_case)
    report["passed"] = not report["inventory"]["errors"] and all(case["passed"] for case in report["cases"])
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    output = Path(__file__).resolve().parents[1] / "reports" / "evidence" / (
        "app_catalog_runtime_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
    print(f"Evidence: {output}", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
