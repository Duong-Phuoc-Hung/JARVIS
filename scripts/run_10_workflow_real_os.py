#!/usr/bin/env python3
"""
scripts/run_10_workflow_real_os.py
==================================
Empirical Real-OS 10-Workflow Acceptance Runner for JARVIS.
Directly checks or executes the 10 core desktop & OS workflows against Windows,
adhering strictly to AUDIT_FRAMEWORK.md, AGENTS.md, and
docs/eval/workflow_10_real_os_execution_protocol.md.

Required 10 Workflows (Beta Protocol):
  WF01: Open App (App Launch)
  WF02: Windows Settings (Settings App)
  WF03: Web Search (URL / Browser Search)
  WF04: Media Playback (Spotify / Media Control)
  WF05: Volume Control (Master Output Volume)
  WF06: Weather Query (Live Weather REST API)
  WF07: Timer Registration (Proactive Timer Engine)
  WF08: Reminder Schedule (Proactive Reminder Storage)
  WF09: Note Persistence (Note Taker Skill)
  WF10: Screen Capture (Desktop Screenshot)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.core.app import JarvisApp  # noqa: E402
from jarvis.core.models import ActionResult  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("10_workflow_acceptance")


WORKFLOW_SPECS: list[dict[str, Any]] = [
    {
        "id": "WF01",
        "domain": "open app (App Launch)",
        "action": "open_app",
        "payload": {"app_name": "notepad"},
        "description": "Launches desktop application via Windows subprocess",
    },
    {
        "id": "WF02",
        "domain": "windows settings (Settings App)",
        "action": "open_app",
        "payload": {"app_name": "settings"},
        "description": "Launches Windows Settings page (ms-settings:)",
    },
    {
        "id": "WF03",
        "domain": "web search (URL Search)",
        "action": "web_search",
        "payload": {"query": "JARVIS Python 3.13"},
        "description": "Executes web search query and opens browser",
    },
    {
        "id": "WF04",
        "domain": "media playback (Spotify/Media)",
        "action": "spotify_play",
        "payload": {"query": "chill beats"},
        "description": "Controls Spotify playback or Windows media keys",
    },
    {
        "id": "WF05",
        "domain": "volume control (Master Output Volume)",
        "action": "system_volume",
        "payload": {"action": "set", "level": 50},
        "description": "Sets master output volume with before/after readback",
    },
    {
        "id": "WF06",
        "domain": "weather query (Live Weather API)",
        "action": "weather_query",
        "payload": {"location": "Hanoi"},
        "description": "Queries current weather forecast REST endpoint",
    },
    {
        "id": "WF07",
        "domain": "timer registration (Countdown Timer)",
        "action": "proactive_reminder",
        "payload": {"message": "acceptance timer", "delay_seconds": 300, "action": "set_timer"},
        "description": "Registers countdown timer in proactive engine",
    },
    {
        "id": "WF08",
        "domain": "reminder schedule (Timed Reminder)",
        "action": "proactive_reminder",
        "payload": {"message": "acceptance reminder", "delay_minutes": 60, "action": "add_reminder"},
        "description": "Schedules timed reminder record in storage",
    },
    {
        "id": "WF09",
        "domain": "note persistence (Note Taking)",
        "action": "note_add",
        "payload": {"content": "Acceptance test note content", "text": "Acceptance test note content"},
        "description": "Persists text note record to disk storage",
    },
    {
        "id": "WF10",
        "domain": "screenshot (Screen Capture)",
        "action": "screen_capture",
        "payload": {},
        "description": "Captures desktop screenshot to disk file",
    },
]

SECRET_REGEXES = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.~+/=]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9\-_]+"),
    re.compile(r"AIza[A-Za-z0-9\-_]+"),
    re.compile(r"(password|pwd)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(token|api_key|secret)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"[^\s'\"]*\.env[^\s'\"]*", re.IGNORECASE),
]

SENSITIVE_KEYS = {
    "api_key", "key", "token", "secret", "password", "pwd", "auth",
    "credential", "cookie", "clip", "clipboard", "env", "access_token"
}


def redact_text(text: str) -> str:
    """Redacts secret patterns from freeform text or exception strings."""
    if not isinstance(text, str):
        return text
    cleaned = text
    for regex in SECRET_REGEXES:
        cleaned = regex.sub("[REDACTED]", cleaned)
    return cleaned


def redact_evidence_data(data: Any) -> Any:
    """Recursively redacts secrets, raw tokens, clipboard, and .env entries from reports."""
    if isinstance(data, dict):
        cleaned_dict: dict[str, Any] = {}
        for k, v in data.items():
            k_str = str(k)
            k_lower = k_str.lower()
            if any(sk in k_lower for sk in SENSITIVE_KEYS):
                cleaned_dict[k_str] = "[REDACTED]"
            else:
                cleaned_dict[k_str] = redact_evidence_data(v)
        return cleaned_dict
    elif isinstance(data, list):
        return [redact_evidence_data(item) for item in data]
    elif isinstance(data, str):
        return redact_text(data)
    return data


def validate_workflow_evidence(wf_id: str, raw_result: Any) -> tuple[bool, str]:
    """
    Validates strict objective OS side-effect evidence for a given workflow result.
    Backend success flag, status, or message alone is NEVER objective evidence.
    """
    if raw_result is None:
        return False, "No response returned from dispatcher handler"

    # Extract properties from ActionResult or dict
    success = False
    data: dict[str, Any] = {}
    code = "UNKNOWN"
    status_str = "FAILED"

    if isinstance(raw_result, ActionResult):
        success = raw_result.success
        data = raw_result.data if isinstance(raw_result.data, dict) else {}
        code = raw_result.code or ("OK" if success else "FAILED")
        status_str = str(raw_result.status or ("SUCCESS" if success else "FAILED"))
    elif isinstance(raw_result, dict):
        success = bool(raw_result.get("success", raw_result.get("status") in ("success", "ok")))
        raw_data_field = raw_result.get("data")
        data = raw_data_field if isinstance(raw_data_field, dict) else raw_result
        code = str(raw_result.get("code") or raw_result.get("error_code") or ("OK" if success else "FAILED"))
        status_str = str(raw_result.get("status") or ("SUCCESS" if success else "FAILED"))

    if not success:
        return False, redact_text(f"Backend reported unsuccessful status ({status_str}, code={code})")

    if not isinstance(data, dict) or not data:
        return False, f"Workflow {wf_id} returned empty or non-dict data payload"

    # The production app handler preserves the verified launcher payload under
    # ``result`` when the dispatcher wraps its response.  Unwrap only for the
    # two app workflows, and never unwrap a nested failure.
    if wf_id in ("WF01", "WF02") and isinstance(data.get("result"), dict):
        nested_result = data["result"]
        if nested_result.get("success") is False:
            return False, f"Workflow {wf_id} nested launcher result reported failure"
        data = nested_result

    # Check for unverified launch/request statuses
    data_code = str(data.get("code") or data.get("error_code") or "").upper()
    data_status = str(data.get("status") or "").upper()
    if "UNVERIFIED" in data_code or "UNVERIFIED" in data_status or "LAUNCH_REQUESTED" in data_code:
        return False, f"Workflow {wf_id} returned unverified launch status ({data_code or data_status})"

    if wf_id == "WF01":  # Open App
        pid = data.get("pid")
        hwnd = data.get("hwnd")
        title = str(data.get("window_title") or data.get("title") or "").strip()
        pname = str(data.get("process_name") or data.get("process") or "").strip()

        if isinstance(hwnd, int) and hwnd > 0 and (title or pname):
            return True, f"Verified window handle hwnd={hwnd} (title='{title or pname}')"
        if isinstance(pid, int) and pid > 0:
            try:
                import psutil
                if psutil.pid_exists(pid) and psutil.Process(pid).is_running():
                    return True, f"Verified running process PID {pid}"
                return False, f"Process PID {pid} is not running or does not exist according to psutil"
            except Exception as e:
                return False, f"psutil inspection failed for PID {pid}: {e}"
        return False, "Missing objective window handle (hwnd>0 with title) or running process proof (pid>0 verified by psutil)"

    elif wf_id == "WF02":  # Windows Settings
        pid = data.get("pid")
        hwnd = data.get("hwnd")
        title = str(data.get("window_title") or data.get("title") or "").strip()
        pname = str(data.get("process_name") or data.get("process") or "").strip()
        app_name = str(data.get("app_name") or "").strip().lower()

        is_settings_title = any(kw in title.lower() for kw in ("settings", "cài đặt"))
        is_settings_proc = any(kw in pname.lower() or kw in app_name for kw in ("systemsettings", "settings", "cài đặt"))

        if isinstance(hwnd, int) and hwnd > 0 and (is_settings_title or is_settings_proc):
            return True, f"Verified Settings window handle hwnd={hwnd} (title='{title}')"
        if isinstance(pid, int) and pid > 0 and (is_settings_title or is_settings_proc):
            try:
                import psutil
                if psutil.pid_exists(pid) and psutil.Process(pid).is_running():
                    return True, f"Verified Settings process PID {pid}"
                return False, f"Settings PID {pid} is not running or does not exist according to psutil"
            except Exception as e:
                return False, f"psutil inspection failed for Settings PID {pid}: {e}"
        return False, "Missing verified Settings window handle (hwnd>0 with Settings title) or running process proof (pid>0 verified by psutil)"

    elif wf_id == "WF03":  # Web Search
        url_raw = str(data.get("url") or data.get("search_url") or "").strip()
        ack = (
            data.get("browser_launched") is True
            or data.get("verification") == "browser_launch_acknowledged"
        )
        if not ack:
            return False, "Missing explicit authoritative browser launch acknowledgement"

        parsed = urlparse(url_raw)
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid URL scheme in search result: '{url_raw}'"

        qs = parse_qs(parsed.query)
        query_val = ""
        for param in ("q", "query", "search_query"):
            if param in qs and len(qs[param]) > 0:
                query_val = qs[param][0]
                break

        if not query_val:
            return False, f"Search URL '{url_raw}' missing expected q/query/search_query parameter"

        expected_q = str(data.get("query") or "JARVIS").strip()
        first_term = expected_q.split()[0].lower() if expected_q else "jarvis"
        if first_term not in query_val.lower() and first_term not in parsed.path.lower():
            return False, f"Search URL query parameter '{query_val}' does not contain expected query term '{first_term}'"

        return True, f"Verified browser search URL '{url_raw}' with query parameter '{query_val}'"

    elif wf_id == "WF04":  # Media Playback
        state = str(data.get("playback_state") or "").strip().upper()
        if state in ("PLAYING", "PAUSED", "STOPPED"):
            return True, f"Verified authoritative Spotify/media playback state '{state}'"
        return False, "Missing explicit authoritative playback_state (PLAYING/PAUSED/STOPPED) readback"

    elif wf_id == "WF05":  # Volume Control
        lvl_before = data.get("level_before")
        lvl_after = data.get("level_after")
        target_lvl = data.get("target_level") if data.get("target_level") is not None else data.get("level")
        delta = data.get("delta")

        if not (isinstance(lvl_before, (int, float)) and isinstance(lvl_after, (int, float))):
            return False, "Missing numeric level_before and level_after in volume response"

        lvl_b = float(lvl_before)
        lvl_a = float(lvl_after)

        if isinstance(target_lvl, (int, float)):
            expected = float(target_lvl)
        elif isinstance(delta, (int, float)):
            expected = max(0.0, min(100.0, lvl_b + float(delta)))
        else:
            return False, "Missing numeric target_level or delta in volume command response"

        if abs(lvl_a - expected) > 2.0:
            return False, f"Volume level_after ({lvl_a}) deviated from expected level ({expected}) beyond tolerance (+/-2.0)"

        return True, f"Verified master output volume transition (before={lvl_b}, after={lvl_a}, expected={expected})"

    elif wf_id == "WF06":  # Weather Query
        provider = str(data.get("provider") or "").strip()
        status_code = data.get("http_status") if data.get("http_status") is not None else data.get("status_code")
        temp = data.get("temp_c") if data.get("temp_c") is not None else data.get("temp")
        cond = data.get("condition") or data.get("condition_text") or data.get("weather_desc")

        if not provider:
            return False, "Missing non-empty provider string in weather response"
        if status_code not in (200, "200"):
            return False, f"Weather HTTP status code must be exactly 200 (got {status_code})"
        if not isinstance(temp, (int, float)):
            return False, "Missing scalar numeric temperature (temp_c/temp) in weather response"
        if not cond or not isinstance(cond, str):
            return False, "Missing non-empty weather condition text in response"

        return True, f"Verified weather response (provider='{provider}', temp={temp}°C, condition='{cond}', status=200)"

    elif wf_id == "WF07":  # Timer Registration
        timer_id = str(data.get("timer_id") or "").strip()
        duration = data.get("duration_seconds") or data.get("duration")
        target_ts = data.get("target_timestamp") or data.get("target_time")

        if not timer_id:
            return False, "Missing timer_id in timer registration response"
        if not (isinstance(duration, (int, float)) and duration > 0):
            return False, "Missing positive numeric duration_seconds in timer response"
        if not target_ts:
            return False, "Missing target_timestamp in timer response"
        return True, f"Verified timer registration (timer_id='{timer_id}', duration={duration}s)"

    elif wf_id == "WF08":  # Reminder Schedule
        reminder_id = str(data.get("reminder_id") or "").strip()
        msg = str(data.get("message") or data.get("text") or "").strip()
        sched_time = str(data.get("target_time") or data.get("scheduled_time") or data.get("target_timestamp") or "").strip()

        if not reminder_id:
            return False, "Missing reminder_id in reminder schedule response"
        if not msg:
            return False, "Missing scheduled message in reminder response"
        if not sched_time:
            return False, "Missing target scheduled timestamp/time in reminder response"
        return True, f"Verified reminder schedule record (reminder_id='{reminder_id}', target_time='{sched_time}')"

    elif wf_id == "WF09":  # Note Persistence
        note_id = str(data.get("note_id") or "").strip()
        note_path = str(data.get("filepath") or data.get("path") or "").strip()
        stored_content = str(data.get("stored_content") or data.get("readback_content") or "").strip()
        input_content = str(data.get("content") or data.get("text") or "").strip()

        if not (note_id or note_path):
            return False, "Missing note_id or filepath in note persistence response"
        if not input_content:
            return False, "Missing input content in note request payload"

        if note_path:
            p = Path(note_path)
            if not p.exists():
                return False, f"Specified note file path '{note_path}' does not exist on disk"
            disk_text = p.read_text(encoding="utf-8", errors="ignore").strip()
            if input_content != disk_text and input_content not in disk_text:
                return False, f"Disk file '{note_path}' content does not match input note text"
            return True, f"Verified note file persistence on disk ('{note_path}')"

        if not stored_content:
            return False, "Missing stored/readback content for note persistence verification"
        if stored_content != input_content:
            return False, f"Stored note readback content ('{stored_content}') does not match input content ('{input_content}')"

        return True, f"Verified note persistence (note_id='{note_id}', exact content match)"

    elif wf_id == "WF10":  # Screen Capture
        filepath = str(data.get("filepath") or data.get("path") or "").strip()
        if not filepath:
            return False, "Missing screenshot output filepath"
        p = Path(filepath)
        if not p.exists():
            return False, f"Screenshot file '{filepath}' does not exist on disk"
        size = p.stat().st_size
        if size <= 10000:
            return False, f"Screenshot file size ({size} bytes) is <= 10000 bytes threshold"
        try:
            with p.open("rb") as f:
                header = f.read(8)
                is_png = header.startswith(b"\x89PNG\r\n\x1a\n")
                is_jpeg = header.startswith(b"\xff\xd8\xff")
                if not (is_png or is_jpeg):
                    return False, f"Screenshot file '{filepath}' header is not valid PNG or JPEG"
        except Exception as e:
            return False, f"Error inspecting screenshot header bytes: {e}"
        return True, f"Verified desktop screenshot file '{filepath}' ({size} bytes, valid header)"

    return False, f"UNKNOWN_WORKFLOW: No validator registered for {wf_id}"


def run_acceptance(
    execute: bool = False,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Executes the 10-workflow acceptance runner.

    Args:
        execute: If True, executes live OS side-effects (live smoke mode).
                 If False (default), performs non-mutating preflight checks only.
        output_path: Custom JSON report output path.
        overwrite: If True, permits overwriting existing report file.

    Returns:
        Structured acceptance report dictionary with standardized fields.
    """
    mode = "live_smoke" if execute else "preflight"
    log.info("Running mode: %s (execute=%s)", mode, execute)

    results: list[dict[str, Any]] = []

    if not execute:
        # Preflight non-mutating path: inspect in-memory action seams without launching runtime subsystems
        log.info("Inspecting in-memory action seams for preflight...")
        app = JarvisApp(headless=True, no_hot_reload=True)

        if hasattr(app, "dispatcher") and app.dispatcher is not None:
            if hasattr(app, "_register_core_actions"):
                app._register_core_actions()

            try:
                from jarvis.plugins.spotify import SpotifyPlugin
                spotify_plugin = SpotifyPlugin()
                spotify_plugin.initialize({}, app.dispatcher)
            except Exception as exc:
                log.warning("SpotifyPlugin seam registration warning: %s", exc)

            registered_actions = app.dispatcher.list_actions()
        else:
            registered_actions = set()

        log.info("Evaluating 10 core Beta workflows (preflight mode)...")

        for wf in WORKFLOW_SPECS:
            wf_id = wf["id"]
            action_name = wf["action"]
            domain = wf["domain"]

            t0 = time.monotonic()
            is_registered = action_name in registered_actions
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)

            if is_registered:
                status_val = "SUCCESS"
                verdict_val = "PREFLIGHT_PASS"
                evidence_tier_val = "T3 — Preflight Seam Only"
                code_val = "OK"
                msg_val = redact_text(f"Action seam '{action_name}' registered and ready for preflight")
                success_val = True
            else:
                status_val = "UNAVAILABLE"
                verdict_val = "UNAVAILABLE"
                evidence_tier_val = "T3 — Action Seam Missing"
                code_val = "ACTION_NOT_REGISTERED"
                msg_val = redact_text(f"Action seam '{action_name}' is not registered in ActionDispatcher")
                success_val = False

            rec = {
                "id": wf_id,
                "domain": domain,
                "action": action_name,
                "success": success_val,
                "status": status_val,
                "code": code_val,
                "message": msg_val,
                "retryable": False,
                "elapsed_ms": elapsed_ms,
                "verdict": verdict_val,
                "evidence_tier": evidence_tier_val,
                "data": {},
                "evidence_validation": {
                    "valid": success_val,
                    "details": msg_val,
                },
            }
            results.append(rec)
            log.info("  -> %s [%s] in %sms", wf_id, verdict_val, elapsed_ms)

    else:
        # Live execution opt-in mode
        log.info("Initializing JarvisApp in headless acceptance mode...")
        app = JarvisApp(headless=True, no_hot_reload=True)
        try:
            app.initialize()
            dispatcher = app.dispatcher
            if not dispatcher:
                raise RuntimeError("ActionDispatcher failed to initialize.")

            log.info("Evaluating 10 core Beta workflows (live execution mode)...")

            for wf in WORKFLOW_SPECS:
                wf_id = wf["id"]
                action_name = wf["action"]
                domain = wf["domain"]
                payload = wf["payload"]

                t0 = time.monotonic()
                log.info("Executing %s (%s) via action '%s'...", wf_id, domain, action_name)
                try:
                    res = dispatcher.dispatch_action(action_name, payload=payload)
                    elapsed_ms = round((time.monotonic() - t0) * 1000, 2)

                    raw_data = None
                    if hasattr(res, "data"):
                        raw_data = res.data
                    elif isinstance(res, dict):
                        raw_data = res.get("data", res)

                    ev_valid, ev_details = validate_workflow_evidence(wf_id, res)
                    clean_data = redact_evidence_data(raw_data) if raw_data else {}
                    clean_ev_details = redact_text(ev_details)

                    backend_success = False
                    code_str = "ACTION_FAILED"
                    msg_str = "Execution completed"
                    status_str = "FAILED"
                    retryable_bool = False

                    if isinstance(res, ActionResult):
                        backend_success = res.success
                        code_str = res.code or ("OK" if backend_success else "ACTION_FAILED")
                        msg_str = res.error or res.message or "Action completed"
                        status_str = str(res.status.name if hasattr(res.status, "name") else (res.status or "FAILED"))
                        retryable_bool = res.retryable
                    elif isinstance(res, dict):
                        backend_success = bool(res.get("success", res.get("status") in ("success", "ok")))
                        code_str = str(res.get("code") or res.get("error_code") or ("OK" if backend_success else "ACTION_FAILED"))
                        msg_str = str(res.get("error") or res.get("message") or "Action completed")
                        status_str = str(res.get("status") or ("SUCCESS" if backend_success else "FAILED"))
                        retryable_bool = bool(res.get("retryable", False))

                    clean_msg = redact_text(msg_str)
                    code_clean = code_str.upper()
                    status_clean = status_str.upper()

                    if backend_success and ev_valid:
                        verdict = "PASS runtime_smoke"
                        status_name = "SUCCESS"
                        evidence_tier = "T1 — Real OS Objective Evidence"
                        final_success = True
                    elif code_clean == "TIMEOUT" or status_clean == "TIMEOUT":
                        verdict = "FAIL"
                        status_name = "TIMEOUT"
                        evidence_tier = "T3 — Handler Timeout"
                        final_success = False
                    elif (
                        code_clean == "BLOCKED"
                        or status_clean == "BLOCKED"
                        or code_clean == "RATE_LIMITED"
                        or code_clean.startswith("CONFIRMATION_")
                    ):
                        verdict = "PASS fail_closed"
                        status_name = "BLOCKED"
                        evidence_tier = "T2 — Truthful Fail-Closed"
                        final_success = False
                    elif code_clean == "NOT_CONFIGURED" or status_clean == "NOT_CONFIGURED":
                        verdict = "PASS fail_closed"
                        status_name = "NOT_CONFIGURED"
                        evidence_tier = "T2 — Truthful Fail-Closed"
                        final_success = False
                    elif code_clean in ("UNAVAILABLE", "LABS_DISABLED", "LIMITED") or status_clean in ("UNAVAILABLE", "LABS_DISABLED", "LIMITED"):
                        verdict = "PASS fail_closed"
                        status_name = "UNAVAILABLE"
                        evidence_tier = "T2 — Truthful Fail-Closed"
                        final_success = False
                    else:
                        verdict = "FAIL"
                        status_name = "ERROR"
                        evidence_tier = "T3 — Evidence Invalid"
                        final_success = False
                        if backend_success and not ev_valid:
                            code_str = "EVIDENCE_INVALID"
                            clean_msg = redact_text(f"Backend reported success but objective evidence validation failed: {ev_details}")

                    rec = {
                        "id": wf_id,
                        "domain": domain,
                        "action": action_name,
                        "success": final_success,
                        "status": status_name,
                        "code": code_str,
                        "message": clean_msg,
                        "retryable": retryable_bool,
                        "elapsed_ms": elapsed_ms,
                        "verdict": verdict,
                        "evidence_tier": evidence_tier,
                        "data": clean_data,
                        "evidence_validation": {
                            "valid": ev_valid,
                            "details": clean_ev_details,
                        },
                    }
                    results.append(rec)
                    log.info("  -> %s [%s] in %sms: %s", wf_id, verdict, elapsed_ms, clean_ev_details)

                except Exception as exc:
                    elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
                    clean_err = redact_text(str(exc))
                    log.error("  -> %s EXCEPTION: %s", wf_id, clean_err)
                    results.append({
                        "id": wf_id,
                        "domain": domain,
                        "action": action_name,
                        "success": False,
                        "status": "ERROR",
                        "code": "HANDLER_EXCEPTION",
                        "message": clean_err,
                        "retryable": False,
                        "elapsed_ms": elapsed_ms,
                        "verdict": "FAIL",
                        "evidence_tier": "T3 — Exception Raised",
                        "data": {},
                        "evidence_validation": {
                            "valid": False,
                            "details": redact_text(f"Exception raised: {exc}"),
                        },
                    })

        finally:
            # Protect JarvisApp lifecycle cleanup in live execution mode
            try:
                log.info("Stopping JarvisApp instance...")
                app.stop()
            except Exception as exc:
                log.warning("Error stopping JarvisApp: %s", exc)

    # Calculate summaries
    preflight_pass = sum(1 for r in results if r["verdict"] == "PREFLIGHT_PASS")
    pass_runtime_smoke = sum(1 for r in results if r["verdict"] == "PASS runtime_smoke")
    pass_fail_closed = sum(1 for r in results if r["verdict"] == "PASS fail_closed")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")
    unavailable = sum(1 for r in results if r["status"] in ("UNAVAILABLE", "NOT_CONFIGURED", "BLOCKED", "TIMEOUT"))

    if mode == "preflight":
        overall_success = (preflight_pass == len(WORKFLOW_SPECS))
        overall_status = "PREFLIGHT_SUCCESS" if overall_success else "PREFLIGHT_FAILED"
        overall_msg = (
            "PASS engineering (preflight seam verification only, runtime evidence pending)"
            if overall_success else "Preflight seam verification failed for one or more workflows"
        )
    else:
        # Live smoke mode requires ALL 10 to be PASS runtime_smoke
        overall_success = (pass_runtime_smoke == len(WORKFLOW_SPECS))
        overall_status = "SMOKE_SUCCESS" if overall_success else "SMOKE_INCOMPLETE"
        overall_msg = (
            "All 10 workflows achieved PASS runtime_smoke with objective T1 evidence"
            if overall_success else "Runtime smoke incomplete: 1 or more workflows missing objective runtime evidence"
        )

    # Output path handling with unique path collision loop
    out_dir = ROOT / "docs" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)

    if output_path is not None:
        base_file = output_path
    else:
        base_file = out_dir / ("10_workflow_real_os_report.json" if overwrite else "10_workflow_real_os_report_smoke.json")

    if base_file.exists() and not overwrite:
        stem = base_file.stem
        suffix = base_file.suffix
        while True:
            ts_ns = time.time_ns()
            cand = base_file.parent / f"{stem}_{ts_ns}{suffix}"
            if not cand.exists():
                target_report_file = cand
                break
    else:
        target_report_file = base_file

    target_report_file.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "protocol_version": "5.2.0",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": sys.platform,
        "python_version": sys.version,
        "mode": mode,
        "success": overall_success,
        "status": "SUCCESS" if overall_success else "ERROR",
        "code": "OK" if overall_success else "ACCEPTANCE_INCOMPLETE",
        "message": overall_msg,
        "data": {
            "saved_report_path": str(target_report_file.resolve()),
            "preflight_pass": preflight_pass,
            "pass_runtime_smoke": pass_runtime_smoke,
            "pass_fail_closed": pass_fail_closed,
            "failed": failed,
            "unavailable": unavailable,
        },
        "retryable": False,
        "total_workflows": len(results),
        "summary": {
            "preflight_pass": preflight_pass,
            "pass_runtime_smoke": pass_runtime_smoke,
            "pass_fail_closed": pass_fail_closed,
            "failed": failed,
            "unavailable": unavailable,
        },
        "overall_status": overall_status,
        "release_gate_status": "PENDING",
        "release_gate_reason": (
            "One-shot text-dispatch runner cannot satisfy 200-trial "
            "real-voice FasterWhisper CUDA STT execution protocol gate."
        ),
        "saved_report_path": str(target_report_file.resolve()),
        "results": results,
    }

    target_report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote acceptance report to: %s", target_report_file)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Empirical 10-Workflow Real-OS Acceptance Runner for JARVIS")
    parser.add_argument("--execute", action="store_true", help="Opt-in to execute live OS side-effects (live smoke mode)")
    parser.add_argument("--output", "-o", type=Path, help="Custom report output JSON path")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing report file")

    args = parser.parse_args()

    try:
        report = run_acceptance(
            execute=args.execute,
            output_path=args.output,
            overwrite=args.overwrite,
        )

        mode = report.get("mode")
        overall = report.get("overall_status")
        summary = report.get("summary", {})
        saved_path = report.get("saved_report_path")

        log.info("=== 10-Workflow Acceptance Summary (%s) ===", mode)
        log.info("Overall Status:       %s", overall)
        log.info("Message:              %s", report.get("message"))
        log.info("Release Gate Status:  %s", report.get("release_gate_status"))
        log.info("Saved Report Path:    %s", saved_path)
        log.info("Preflight Pass:       %d/10", summary.get("preflight_pass", 0))
        log.info("PASS runtime_smoke:   %d/10", summary.get("pass_runtime_smoke", 0))
        log.info("PASS fail_closed:     %d/10", summary.get("pass_fail_closed", 0))
        log.info("FAILED:               %d/10", summary.get("failed", 0))
        log.info("UNAVAILABLE:          %d/10", summary.get("unavailable", 0))

        if mode == "preflight":
            return 0 if overall == "PREFLIGHT_SUCCESS" else 1
        else:
            # Exit 0 ONLY IF all 10 achieve PASS runtime_smoke
            return 0 if summary.get("pass_runtime_smoke", 0) == 10 else 1

    except Exception as exc:
        log.error("Acceptance runner failed with error: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
