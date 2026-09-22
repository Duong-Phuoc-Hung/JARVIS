"""
tests/unit/test_automation_fixes_m2.py
======================================
Regression test suite for Milestone 2: Automation & Safety Gate Remediation.
Covers:
  - BUG-AUTO-01: ComputerController.set_brightness() fail-closed
  - BUG-AUTO-02 & BUG-AUTO-03: SafetyGate negation priority & Whisper punctuation
  - BUG-AUTO-04: SafetyGate._pending memory leak cleanup
  - BUG-AUTO-05: VMOrchestrator missing hypervisor fail-closed
  - BUG-AUTO-06: WorkspaceManager.prepare_workspace recipe dataclass support & launching
  - BUG-AUTO-07: ShellAssistant Windows cmd.exe compatibility (docker_restart & clear_temp)
  - BUG-AUTO-08: ComputerController.take_screenshot() fail-closed
  - BUG-AUTO-09: ComputerController.send_hotkey() compound key flattening
  - BUG-AUTO-10: ComputerController.search_files() glob & pattern matching
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from unittest.mock import MagicMock, call, patch

import pytest

from jarvis.automation.control import ComputerController
from jarvis.automation.safety_gate import SafetyGate
from jarvis.automation.shell_assistant import ShellAssistant
from jarvis.automation.vm import VMOrchestrator
from jarvis.automation.workspace import WorkspaceRecipe, WorkspaceRecipeManager
from jarvis.core.models import ActionStatus


# ===========================================================================
# 1. BUG-AUTO-01: ComputerController.set_brightness() Fail-Closed
# ===========================================================================
def test_set_brightness_fails_closed_when_hardware_fails():
    ctrl = ComputerController()
    initial_brightness = ctrl._current_brightness

    # Simulate screen_brightness_control unavailable/failing and WMI returning error code 1
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock(returncode=1, stderr="MethodNotFound", stdout="")
        mock_run.return_value = mock_proc

        result = ctrl.set_brightness(50)
        assert result is None, "set_brightness must return None when hardware adjustments fail"
        assert ctrl._current_brightness == initial_brightness, (
            "Cached brightness must not mutate when hardware adjustment fails"
        )


def test_change_brightness_fails_closed_when_hardware_fails():
    ctrl = ComputerController()
    initial_brightness = ctrl._current_brightness

    with patch.object(ctrl, "set_brightness", return_value=None) as mock_set:
        result = ctrl.change_brightness(10)
        assert result is None
        mock_set.assert_called_once()
        assert ctrl._current_brightness == initial_brightness


def test_set_brightness_succeeds_when_wmi_returns_zero():
    ctrl = ComputerController()

    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock(returncode=0, stderr="", stdout="")
        mock_run.return_value = mock_proc

        result = ctrl.set_brightness(75)
        assert result == 75
        assert ctrl._current_brightness == 75


# ===========================================================================
# 2. BUG-AUTO-02 & BUG-AUTO-03: SafetyGate Negation Priority & Punctuation
# ===========================================================================
@pytest.mark.parametrize(
    "neg_phrase",
    [
        "không đồng ý",
        "khong dong y",
        "không được",
        "khong duoc",
        "không ok",
        "đừng làm",
        "dung lam",
        "chớ thực hiện",
        "không xác nhận",
        "hủy",
        "cancel",
    ],
)
def test_safety_gate_negation_priority(neg_phrase):
    gate = SafetyGate()
    token = gate.request_confirmation("Xóa toàn bộ dữ liệu C:")

    assert gate.is_negative(neg_phrase) is True
    assert gate.is_affirmative(neg_phrase) is False

    ok, msg = gate.process_voice_response(neg_phrase, token)
    assert ok is False
    assert "Đã hủy" in msg
    pending = gate.get_pending(token)
    assert pending is not None
    assert pending.status == "REJECTED"


@pytest.mark.parametrize(
    "phrase,expected_ok,expected_status",
    [
        ("đồng ý.", True, "CONFIRMED"),
        ("có!", True, "CONFIRMED"),
        ("xác nhận?", True, "CONFIRMED"),
        ("ok,", True, "CONFIRMED"),
        ("hủy.", False, "REJECTED"),
        ("không!", False, "REJECTED"),
        ("thôi...", False, "REJECTED"),
    ],
)
def test_safety_gate_whisper_punctuation_normalization(phrase, expected_ok, expected_status):
    gate = SafetyGate()
    token = gate.request_confirmation("Cập nhật hệ thống")

    ok, msg = gate.process_voice_response(phrase, token)
    assert ok is expected_ok
    pending = gate.get_pending(token)
    assert pending is not None
    assert pending.status == expected_status


# ===========================================================================
# 3. BUG-AUTO-04: SafetyGate._pending Memory Leak Cleanup
# ===========================================================================
def test_safety_gate_cleanup_expired_purges_old_finished_tokens():
    gate = SafetyGate()
    now = time.time()

    # Active pending token (keep)
    t_active = gate.request_confirmation("Active action")

    # Expired pending token (should mark EXPIRED)
    t_expired = gate.request_confirmation("Expired pending")

    # Old confirmed token > 1 hour old (should purge)
    t_old_conf = gate.request_confirmation("Old confirmed")
    gate._pending[t_old_conf].status = "CONFIRMED"
    gate._pending[t_old_conf].created_at = now - 4000

    # Recent confirmed token 10s old (keep)
    t_recent_conf = gate.request_confirmation("Recent confirmed")
    gate._pending[t_recent_conf].status = "CONFIRMED"
    gate._pending[t_recent_conf].created_at = now - 10

    # Old rejected token > 1 hour old (should purge)
    t_old_rej = gate.request_confirmation("Old rejected")
    gate._pending[t_old_rej].status = "REJECTED"
    gate._pending[t_old_rej].created_at = now - 5000

    gate._pending[t_expired].expires_at = now - 10
    expired_count = gate.cleanup_expired(max_history_age_seconds=3600.0)
    assert expired_count >= 1

    # Check active & recent are preserved
    assert t_active in gate._pending
    assert t_recent_conf in gate._pending
    assert gate._pending[t_expired].status == "EXPIRED"

    # Check old tokens are removed from memory
    assert t_old_conf not in gate._pending
    assert t_old_rej not in gate._pending


# ===========================================================================
# 4. BUG-AUTO-05: VMOrchestrator Missing Hypervisor Fail-Closed
# ===========================================================================
def test_vm_orchestrator_fails_closed_when_binaries_missing():
    orchestrator = VMOrchestrator(
        dry_run=False,
        vmrun_path="nonexistent_vmrun_exe",
        vboxmanage_path="nonexistent_vboxmanage_exe",
    )

    # start_vm
    res_start = orchestrator.start_vm("UbuntuDev", hypervisor="vmware")
    assert res_start.success is False
    assert res_start.status == ActionStatus.ERROR
    assert res_start.code == "TOOL_NOT_FOUND"

    # stop_vm
    res_stop = orchestrator.stop_vm("UbuntuDev", hypervisor="virtualbox")
    assert res_stop.success is False
    assert res_stop.status == ActionStatus.ERROR
    assert res_stop.code == "TOOL_NOT_FOUND"

    # suspend_vm
    res_susp = orchestrator.suspend_vm("UbuntuDev", hypervisor="vmware")
    assert res_susp.success is False
    assert res_susp.status == ActionStatus.ERROR
    assert res_susp.code == "TOOL_NOT_FOUND"

    # snapshot_vm
    res_snap = orchestrator.snapshot_vm("UbuntuDev", "snap1", hypervisor="virtualbox")
    assert res_snap.success is False
    assert res_snap.status == ActionStatus.ERROR
    assert res_snap.code == "TOOL_NOT_FOUND"


def test_vm_orchestrator_allows_dry_run_simulation():
    orchestrator = VMOrchestrator(
        dry_run=True,
        vmrun_path="nonexistent_vmrun_exe",
        vboxmanage_path="nonexistent_vboxmanage_exe",
    )
    res_start = orchestrator.start_vm("UbuntuDev", hypervisor="vmware")
    assert res_start.success is True
    assert res_start.status == ActionStatus.SUCCESS


# ===========================================================================
# 5. BUG-AUTO-06: WorkspaceManager.prepare_workspace Dataclass & Launching
# ===========================================================================
def test_workspace_prepare_supports_workspace_recipe_dataclass():
    manager = WorkspaceRecipeManager()

    recipe_obj = WorkspaceRecipe(
        name="custom_ai",
        description="Custom Workspace",
        ide="cursor.exe",
        background_apps=["spotify.exe"],
        browser_urls=[{"url": "https://github.com"}],
        vm_to_start=None,
    )

    with patch("webbrowser.open") as mock_web_open, patch("subprocess.Popen") as mock_popen, patch("os.startfile", create=True) as mock_startfile:
        res = manager.prepare_workspace(recipe_obj)
        assert res["success"] is True
        assert res["recipe"] == "custom_ai"
        assert "cursor.exe" in res["launched_apps"]
        assert "spotify.exe" in res["launched_apps"]
        assert "https://github.com" in res["urls"]
        assert mock_web_open.called or mock_popen.called or mock_startfile.called


def test_workspace_prepare_supports_dict_and_string():
    manager = WorkspaceRecipeManager()

    with patch("webbrowser.open"), patch("subprocess.Popen"), patch("os.startfile", create=True):
        res = manager.prepare_workspace("ai_development")
        assert res["success"] is True
        assert res["recipe"] == "ai_development"
        assert len(res["launched_apps"]) > 0


# ===========================================================================
# 6. BUG-AUTO-07: ShellAssistant Windows cmd.exe Compatibility
# ===========================================================================
def test_shell_assistant_docker_restart_no_bash_substitution():
    assistant = ShellAssistant()

    # Case 1: Docker ps -q returns containers
    with patch("subprocess.run") as mock_run:
        ps_mock = MagicMock(returncode=0, stdout="c101\nc102\n")
        restart_mock = MagicMock(returncode=0, stdout="c101\nc102\n", stderr="")
        mock_run.side_effect = [ps_mock, restart_mock]

        msg = assistant.docker_restart()
        assert "thành công" in msg
        # Ensure docker restart was called with list of IDs, not $(docker ps -q)
        assert mock_run.call_count == 2
        second_call = mock_run.call_args_list[1]
        args = second_call[0][0]
        assert isinstance(args, list)
        assert "$(docker ps -q)" not in args
        assert "c101" in args
        assert "c102" in args

    # Case 2: Docker ps -q returns no running containers
    with patch("subprocess.run") as mock_run:
        ps_mock = MagicMock(returncode=0, stdout="\n")
        mock_run.side_effect = [ps_mock]

        msg = assistant.docker_restart()
        assert "không có container" in msg.lower()
        assert mock_run.call_count == 1


def test_shell_assistant_translate_nl_command_windows_temp_cleanup():
    assistant = ShellAssistant()
    cmd, tag = assistant.translate_nl_command("dọn dẹp temp")
    assert tag == "clear_temp"
    if sys.platform == "win32":
        assert "powershell" in cmd.lower()
        assert "Remove-Item" in cmd


# ===========================================================================
# 7. BUG-AUTO-08: ComputerController.take_screenshot() Fail-Closed
# ===========================================================================
def test_take_screenshot_fails_closed_when_capture_fails(tmp_path):
    ctrl = ComputerController()
    target = str(tmp_path / "screenshot.png")

    mock_mss_mod = MagicMock()
    mock_mss_mod.mss.side_effect = Exception("MSS capture failed")

    with patch("PIL.ImageGrab.grab", side_effect=Exception("Display capture failed")):
        with patch.dict(sys.modules, {"mss": mock_mss_mod}):
            res = ctrl.take_screenshot(output_path=target)
            assert res is None, "take_screenshot must return None when all backends fail"
            assert not os.path.exists(target)


def test_take_screenshot_succeeds_when_file_written(tmp_path):
    ctrl = ComputerController()
    target = str(tmp_path / "screenshot.png")

    # Mock ImageGrab to actually write a valid file
    def fake_grab():
        mock_img = MagicMock()
        def fake_save(fp):
            with open(fp, "wb") as f:
                f.write(b"PNGDATA")
        mock_img.save.side_effect = fake_save
        return mock_img

    with patch("PIL.ImageGrab.grab", side_effect=fake_grab):
        res = ctrl.take_screenshot(output_path=target)
        assert res == target
        assert os.path.exists(target)
        assert os.path.getsize(target) > 0


# ===========================================================================
# 8. BUG-AUTO-09: ComputerController.send_hotkey() Flattening
# ===========================================================================
def test_send_hotkey_flattens_compound_strings():
    ctrl = ComputerController()

    with patch.object(ctrl.win32, "send_hotkey", return_value=True) as mock_send:
        # Compound string "ctrl+t"
        ok = ctrl.send_hotkey("ctrl+t")
        assert ok is True
        mock_send.assert_called_with("ctrl", "t")

        # Multi-key compound "ctrl+shift+esc"
        mock_send.reset_mock()
        ok = ctrl.send_hotkey("ctrl+shift+esc")
        assert ok is True
        mock_send.assert_called_with("ctrl", "shift", "esc")

        # Mixed arguments ("ctrl", "shift+n")
        mock_send.reset_mock()
        ok = ctrl.send_hotkey("ctrl", "shift+n")
        assert ok is True
        mock_send.assert_called_with("ctrl", "shift", "n")


# ===========================================================================
# 9. BUG-AUTO-10: ComputerController.search_files() Glob Support
# ===========================================================================
def test_search_files_glob_matching(tmp_path):
    ctrl = ComputerController()

    # Create test files
    (tmp_path / "document.txt").write_text("doc", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("note", encoding="utf-8")
    (tmp_path / "script.py").write_text("py", encoding="utf-8")
    sub = tmp_path / "subfolder"
    sub.mkdir()
    (sub / "archive.zip").write_text("zip", encoding="utf-8")

    # Glob *.txt
    results_txt = ctrl.search_files("*.txt", root_dir=str(tmp_path))
    names_txt = [os.path.basename(p) for p in results_txt]
    assert "document.txt" in names_txt
    assert "notes.txt" in names_txt
    assert "script.py" not in names_txt

    # Glob *.*
    results_all = ctrl.search_files("*.*", root_dir=str(tmp_path))
    names_all = [os.path.basename(p) for p in results_all]
    assert "document.txt" in names_all
    assert "notes.txt" in names_all
    assert "script.py" in names_all

    # Substring search (without glob char)
    results_sub = ctrl.search_files("doc", root_dir=str(tmp_path))
    names_sub = [os.path.basename(p) for p in results_sub]
    assert "document.txt" in names_sub
    assert "script.py" not in names_sub
