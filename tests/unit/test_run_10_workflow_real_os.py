"""
tests/unit/test_run_10_workflow_real_os.py
===========================================
Unit test suite for scripts/run_10_workflow_real_os.py adhering to
AGENTS.md, AUDIT_FRAMEWORK.md, and workflow_10_real_os_execution_protocol.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.run_10_workflow_real_os import (
    WORKFLOW_SPECS,
    main,
    redact_evidence_data,
    redact_text,
    run_acceptance,
    validate_workflow_evidence,
)

from jarvis.core.models import ActionResult


def test_exact_10_workflow_ids_and_domains():
    """Verify runner defines exact 10 Beta workflow IDs and required domains."""
    assert len(WORKFLOW_SPECS) == 10
    expected_ids = [f"WF{i:02d}" for i in range(1, 11)]
    actual_ids = [wf["id"] for wf in WORKFLOW_SPECS]
    assert actual_ids == expected_ids

    domains = [wf["domain"].lower() for wf in WORKFLOW_SPECS]
    required_keywords = [
        "open app",
        "windows settings",
        "web search",
        "media",
        "volume",
        "weather",
        "timer",
        "reminder",
        "note",
        "screenshot",
    ]
    for kw in required_keywords:
        assert any(kw in d for d in domains), f"Missing domain keyword: {kw}"


@pytest.mark.parametrize("wf_id", [f"WF{i:02d}" for i in range(1, 11)])
def test_success_status_message_only_rejected_for_all_workflows(wf_id: str):
    """
    Verify that for EVERY workflow (WF01-WF10), a backend response carrying
    only success=True, status='success', message='OK' without objective evidence
    is rejected by validate_workflow_evidence.
    """
    weak_response = {
        "success": True,
        "status": "success",
        "code": "OK",
        "message": "Action executed successfully",
        "data": {},  # Empty data payload
    }
    valid, details = validate_workflow_evidence(wf_id, weak_response)
    assert not valid, f"{wf_id} accepted weak self-reported success evidence!"
    assert len(details) > 0


@pytest.mark.parametrize("wf_id", [f"WF{i:02d}" for i in range(1, 11)])
def test_unverified_launch_status_rejected_for_all_workflows(wf_id: str):
    """
    Verify that unverified launch or request codes (e.g. APP_LAUNCH_UNVERIFIED)
    are rejected from objective evidence validation.
    """
    unverified_response = {
        "success": True,
        "status": "success",
        "code": "APP_LAUNCH_UNVERIFIED",
        "message": "Launch requested",
        "data": {"status": "UNVERIFIED", "code": "APP_LAUNCH_UNVERIFIED", "app_name": "notepad"},
    }
    valid, details = validate_workflow_evidence(wf_id, unverified_response)
    assert not valid, f"{wf_id} accepted unverified launch status!"


def test_unknown_workflow_id_rejected():
    """Verify unknown workflow ID returns False with UNKNOWN_WORKFLOW detail."""
    valid, details = validate_workflow_evidence("WF999", {"success": True, "data": {"a": 1}})
    assert not valid
    assert "UNKNOWN_WORKFLOW" in details


def test_wf01_wf02_ghost_success_psutil_exception_rejected():
    """Verify WF01/WF02 reject PID evidence if psutil raises an exception or process is not running."""
    res_pid_wf01 = {"success": True, "status": "success", "data": {"pid": 999999}}
    with patch("psutil.pid_exists", return_value=False):
        valid, details = validate_workflow_evidence("WF01", res_pid_wf01)
        assert not valid
        assert "not running" in details.lower() or "psutil" in details.lower()

    res_pid_wf02 = {"success": True, "status": "success", "data": {"pid": 999999, "app_name": "settings"}}
    with patch("psutil.pid_exists", side_effect=RuntimeError("psutil error")):
        valid_err, details_err = validate_workflow_evidence("WF02", res_pid_wf02)
        assert not valid_err
        assert "failed" in details_err.lower() or "error" in details_err.lower() or "psutil" in details_err.lower()


def test_wf01_accepts_nested_verified_launcher_result():
    """Production app handler nests objective launcher proof under ``result``."""
    response = {
        "success": True,
        "status": "success",
        "data": {
            "success": True,
            "result": {
                "success": True,
                "hwnd": 12345,
                "title": "Notepad",
                "process_name": "notepad.exe",
            },
        },
    }
    assert validate_workflow_evidence("WF01", response)[0]


def test_wf03_web_search_strict_validation():
    """Verify WF03 requires browser launch acknowledgement and URL query parameters via urlparse."""
    # Missing launch acknowledgement
    res_no_ack = {
        "success": True,
        "data": {"url": "https://www.google.com/search?q=JARVIS", "query": "JARVIS"},
    }
    assert not validate_workflow_evidence("WF03", res_no_ack)[0]

    # Missing query parameter in URL
    res_no_q = {
        "success": True,
        "data": {"url": "https://www.google.com/about", "query": "JARVIS", "browser_launched": True},
    }
    assert not validate_workflow_evidence("WF03", res_no_q)[0]

    # Valid search with acknowledgement and URL query parameter
    res_valid = {
        "success": True,
        "data": {
            "url": "https://www.google.com/search?q=JARVIS+Python",
            "query": "JARVIS Python",
            "browser_launched": True,
        },
    }
    assert validate_workflow_evidence("WF03", res_valid)[0]


def test_wf05_volume_control_strict_validation():
    """Verify WF05 requires numeric level_before, level_after, target_level/delta, and tolerance check."""
    # Missing target level or delta
    res_no_target = {
        "success": True,
        "data": {"level_before": 30.0, "level_after": 30.0},
    }
    assert not validate_workflow_evidence("WF05", res_no_target)[0]

    # Level after deviated from target beyond tolerance (+/-2.0)
    res_dev = {
        "success": True,
        "data": {"level_before": 30.0, "level_after": 80.0, "target_level": 50.0},
    }
    assert not validate_workflow_evidence("WF05", res_dev)[0]

    # Valid level transition within tolerance
    res_valid = {
        "success": True,
        "data": {"level_before": 30.0, "level_after": 50.0, "target_level": 50.0},
    }
    assert validate_workflow_evidence("WF05", res_valid)[0]


def test_wf06_weather_query_strict_validation():
    """Verify WF06 requires non-empty provider, exact 200 http_status, numeric temp, and condition."""
    # Non-200 status code
    res_404 = {
        "success": True,
        "data": {"provider": "open_weather", "http_status": 404, "temp_c": 25.0, "condition": "Sunny"},
    }
    assert not validate_workflow_evidence("WF06", res_404)[0]

    # Valid weather response
    res_200 = {
        "success": True,
        "data": {"provider": "open_weather", "http_status": 200, "temp_c": 25.0, "condition": "Sunny"},
    }
    assert validate_workflow_evidence("WF06", res_200)[0]


def test_wf09_note_persistence_strict_validation(tmp_path: Path):
    """Verify WF09 requires exact input and stored/readback content match or valid file on disk."""
    # Mismatched stored content
    res_mismatch = {
        "success": True,
        "data": {
            "note_id": "n1",
            "content": "Original note",
            "stored_content": "Different note content",
        },
    }
    assert not validate_workflow_evidence("WF09", res_mismatch)[0]

    # Valid note storage
    res_valid = {
        "success": True,
        "data": {
            "note_id": "n1",
            "content": "Original note",
            "stored_content": "Original note",
        },
    }
    assert validate_workflow_evidence("WF09", res_valid)[0]


def test_wf10_screen_capture_strict_validation(tmp_path: Path):
    """Verify WF10 requires file_size > 10000 bytes and valid PNG/JPEG header."""
    sc_file = tmp_path / "small.png"
    sc_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    res_small = {"success": True, "data": {"filepath": str(sc_file)}}
    assert not validate_workflow_evidence("WF10", res_small)[0]


def test_secret_substring_regex_redaction():
    """Verify raw secret substrings inside freeform text and nested dicts are redacted."""
    sensitive_text = "Failed with token: sk-proj-1234567890secret and Bearer abc123token and password=mysecretpassword in /app/config/.env file"
    cleaned = redact_text(sensitive_text)
    assert "sk-proj-1234567890secret" not in cleaned
    assert "Bearer abc123token" not in cleaned
    assert "mysecretpassword" not in cleaned
    assert ".env" not in cleaned
    assert "[REDACTED]" in cleaned

    nested_dict = {
        "error_msg": "Connection error to sk-proj-1234567890secret",
        "api_key": "raw_secret_key",
        "details": ["Log output with Bearer xyz789token"],
    }
    redacted_data = redact_evidence_data(nested_dict)
    redacted_json = json.dumps(redacted_data)
    assert "sk-proj-1234567890secret" not in redacted_json
    assert "raw_secret_key" not in redacted_json
    assert "Bearer xyz789token" not in redacted_json


def test_default_mode_is_preflight_non_executing(tmp_path: Path):
    """Verify default execution mode is preflight with explicit PASS engineering message."""
    output_file = tmp_path / "test_report.json"

    mock_app = MagicMock()
    mock_dispatcher = MagicMock()
    mock_app.dispatcher = mock_dispatcher
    mock_dispatcher.list_actions.return_value = {
        wf["action"]: MagicMock() for wf in WORKFLOW_SPECS
    }

    with patch("scripts.run_10_workflow_real_os.JarvisApp", return_value=mock_app):
        report = run_acceptance(execute=False, output_path=output_file)

    assert report["mode"] == "preflight"
    assert report["release_gate_status"] == "PENDING"
    assert report["overall_status"] == "PREFLIGHT_SUCCESS"
    assert report["status"] == "SUCCESS"
    assert "PASS engineering" in report["message"]
    mock_dispatcher.dispatch_action.assert_not_called()
    assert output_file.exists()


def test_one_shot_smoke_never_claims_release_go(tmp_path: Path):
    """Verify release_gate_status stays PENDING and never claims release GO."""
    output_file = tmp_path / "smoke_report.json"

    mock_app = MagicMock()
    mock_dispatcher = MagicMock()
    mock_app.dispatcher = mock_dispatcher

    def fake_dispatch(action_name, payload=None, **kwargs):
        return ActionResult(
            action_name=action_name,
            success=True,
            code="OK",
            message="OK",
            data={},
        )

    mock_dispatcher.dispatch_action.side_effect = fake_dispatch

    with patch("scripts.run_10_workflow_real_os.JarvisApp", return_value=mock_app):
        report = run_acceptance(execute=True, output_path=output_file)

    assert report["mode"] == "live_smoke"
    assert report["release_gate_status"] == "PENDING"
    assert report["overall_status"] == "SMOKE_INCOMPLETE"
    assert report["status"] == "ERROR"
    assert "RELEASE_GO" not in report["release_gate_status"]


def test_lifecycle_app_stop_protected_by_finally(tmp_path: Path):
    """Verify JarvisApp.stop() is executed in a finally block even on errors in execute mode."""
    output_file = tmp_path / "err_report.json"
    mock_app = MagicMock()
    mock_app.initialize.side_effect = RuntimeError("App init failed")

    with patch("scripts.run_10_workflow_real_os.JarvisApp", return_value=mock_app):
        with pytest.raises(RuntimeError, match="App init failed"):
            run_acceptance(execute=True, output_path=output_file)

    mock_app.stop.assert_called_once()


def test_preflight_does_not_call_initialize_or_stop(tmp_path: Path):
    """Verify preflight mode does NOT call JarvisApp.initialize() or JarvisApp.stop()."""
    output_file = tmp_path / "preflight_no_init.json"
    mock_app = MagicMock()
    mock_dispatcher = MagicMock()
    mock_app.dispatcher = mock_dispatcher
    mock_dispatcher.list_actions.return_value = {wf["action"] for wf in WORKFLOW_SPECS}

    with patch("scripts.run_10_workflow_real_os.JarvisApp", return_value=mock_app):
        report = run_acceptance(execute=False, output_path=output_file)

    mock_app.initialize.assert_not_called()
    mock_app.stop.assert_not_called()
    mock_dispatcher.dispatch_action.assert_not_called()
    assert report["overall_status"] == "PREFLIGHT_SUCCESS"


def test_preflight_forbidden_subsystems_never_called_or_constructed(tmp_path: Path):
    """
    Verify preflight mode NEVER constructs or starts forbidden subsystems:
    - plugin_registry.initialize_all
    - Playwright/browser launch
    - hotkey registration
    - Telegram polling
    - audio / wake / STT / TTS constructors
    - thread start
    - dispatch_action
    """
    output_file = tmp_path / "preflight_forbidden.json"

    with patch("jarvis.core.plugin.PluginRegistry.initialize_all") as mock_plugin_init, \
         patch("jarvis.platform.hotkeys.GlobalHotkeyManager") as mock_hotkey, \
         patch("jarvis.comms.telegram.TelegramBotController") as mock_telegram, \
         patch("jarvis.audio.engine.AudioEngine") as mock_audio, \
         patch("jarvis.audio.wake_word.WakeWordDetector") as mock_wake, \
         patch("jarvis.stt.engine.STTEngine") as mock_stt, \
         patch("jarvis.tts.manager.TTSManager") as mock_tts, \
         patch("jarvis.browser.agent.BrowserAgent") as mock_browser, \
         patch("threading.Thread.start") as mock_thread_start, \
         patch("jarvis.core.dispatcher.ActionDispatcher.dispatch_action") as mock_dispatch:

        report = run_acceptance(execute=False, output_path=output_file)

        mock_plugin_init.assert_not_called()
        mock_hotkey.assert_not_called()
        mock_telegram.assert_not_called()
        mock_audio.assert_not_called()
        mock_wake.assert_not_called()
        mock_stt.assert_not_called()
        mock_tts.assert_not_called()
        mock_browser.assert_not_called()
        mock_thread_start.assert_not_called()
        mock_dispatch.assert_not_called()

        assert report["overall_status"] == "PREFLIGHT_SUCCESS"
        assert report["summary"]["preflight_pass"] == 10


def test_preflight_verifies_all_10_seams_without_mocking_jarvis_app(tmp_path: Path):
    """Real non-mutating preflight execution verifies all 10 seams are registered."""
    output_file = tmp_path / "preflight_real_seams.json"
    report = run_acceptance(execute=False, output_path=output_file)

    assert report["mode"] == "preflight"
    assert report["overall_status"] == "PREFLIGHT_SUCCESS"
    assert report["summary"]["preflight_pass"] == 10
    assert len(report["results"]) == 10
    for rec in report["results"]:
        assert rec["verdict"] == "PREFLIGHT_PASS"
        assert rec["status"] == "SUCCESS"
        assert rec["success"] is True


def test_custom_output_path_collision_safety(tmp_path: Path):
    """Verify custom output_path does NOT overwrite an existing file unless --overwrite is set."""
    output_file = tmp_path / "custom_report.json"
    output_file.write_text("INITIAL_CONTENT", encoding="utf-8")

    mock_app = MagicMock()
    mock_dispatcher = MagicMock()
    mock_app.dispatcher = mock_dispatcher
    mock_dispatcher.list_actions.return_value = {
        wf["action"]: MagicMock() for wf in WORKFLOW_SPECS
    }

    with patch("scripts.run_10_workflow_real_os.JarvisApp", return_value=mock_app):
        report = run_acceptance(execute=False, output_path=output_file, overwrite=False)

    assert output_file.read_text(encoding="utf-8") == "INITIAL_CONTENT"
    saved_path = Path(report["saved_report_path"])
    assert saved_path != output_file
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") != "INITIAL_CONTENT"

    with patch("scripts.run_10_workflow_real_os.JarvisApp", return_value=mock_app):
        report_overwritten = run_acceptance(execute=False, output_path=output_file, overwrite=True)

    assert Path(report_overwritten["saved_report_path"]) == output_file
    assert output_file.read_text(encoding="utf-8") != "INITIAL_CONTENT"


def test_standardized_status_values_and_top_level_schema(tmp_path: Path):
    """Verify top-level and per-record status uses standardized values ONLY."""
    output_file = tmp_path / "status_test.json"
    allowed_statuses = {"SUCCESS", "ERROR", "TIMEOUT", "BLOCKED", "UNAVAILABLE", "NOT_CONFIGURED"}

    mock_app = MagicMock()
    mock_dispatcher = MagicMock()
    mock_app.dispatcher = mock_dispatcher
    mock_dispatcher.list_actions.return_value = {
        wf["action"]: MagicMock() for wf in WORKFLOW_SPECS
    }

    with patch("scripts.run_10_workflow_real_os.JarvisApp", return_value=mock_app):
        report = run_acceptance(execute=False, output_path=output_file)

    assert report["status"] in allowed_statuses
    assert "success" in report
    assert "code" in report
    assert "message" in report
    assert "data" in report
    assert "retryable" in report

    for rec in report["results"]:
        assert rec["status"] in allowed_statuses, f"Nonstandard status: {rec['status']}"
        assert "success" in rec
        assert "code" in rec
        assert "message" in rec
        assert "data" in rec
        assert "retryable" in rec


def test_execute_exit_nonzero_when_smoke_incomplete(tmp_path: Path):
    """Verify main() returns nonzero exit code in --execute mode if any workflow is not PASS runtime_smoke."""
    output_file = tmp_path / "smoke_inc_report.json"

    mock_app = MagicMock()
    mock_dispatcher = MagicMock()
    mock_app.dispatcher = mock_dispatcher

    def fake_dispatch(action_name, payload=None, **kwargs):
        return ActionResult(
            action_name=action_name,
            success=False,
            code="NOT_CONFIGURED",
            message="Not configured",
        )

    mock_dispatcher.dispatch_action.side_effect = fake_dispatch

    with patch("scripts.run_10_workflow_real_os.JarvisApp", return_value=mock_app), \
         patch("sys.argv", ["run_10_workflow_real_os.py", "--execute", "--output", str(output_file)]):
        exit_code = main()
        assert exit_code != 0


def test_confirmation_required_maps_to_blocked(tmp_path: Path):
    """Safety confirmation is a BLOCKED outcome, never a generic error."""
    output_file = tmp_path / "blocked_report.json"
    mock_app = MagicMock()
    mock_dispatcher = MagicMock()
    mock_app.dispatcher = mock_dispatcher
    mock_dispatcher.dispatch_action.return_value = ActionResult(
        action_name="screen_capture",
        success=False,
        code="CONFIRMATION_REQUIRED",
        message="Confirmation required",
    )

    with patch("scripts.run_10_workflow_real_os.JarvisApp", return_value=mock_app):
        report = run_acceptance(execute=True, output_path=output_file)

    assert report["success"] is False
    assert {record["status"] for record in report["results"]} == {"BLOCKED"}
    assert all(record["verdict"] == "PASS fail_closed" for record in report["results"])


def test_single_definition_of_run_acceptance():
    """Verify scripts/run_10_workflow_real_os.py contains exactly ONE run_acceptance function definition."""
    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_10_workflow_real_os.py"
    content = script_path.read_text(encoding="utf-8")
    def_lines = [line for line in content.splitlines() if line.startswith("def run_acceptance")]
    assert len(def_lines) == 1, f"Expected exactly 1 definition of run_acceptance, found {len(def_lines)}: {def_lines}"
