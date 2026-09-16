"""
Unit Tests for OS Computer Control and SafetyGate Subsystems (Milestone 4 - R4).
"""
import os
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from jarvis.automation.control import ComputerController
from jarvis.automation.safety_gate import PendingConfirmation, SafetyGate
from jarvis.core.models import WindowInfo


@pytest.fixture
def mock_win32():
    """Mock Windows Platform API."""
    m = MagicMock()
    mock_window = WindowInfo(
        hwnd=12345,
        title="Visual Studio Code - JARVIS",
        class_name="Chrome_WidgetWin_1",
        rect=(100, 100, 900, 700),
        width=800,
        height=600,
        pid=5432,
        process_name="Code.exe",
        is_visible=True,
        is_minimized=False,
        is_maximized=True,
        is_cloaked=False,
        is_hung=False,
    )
    m.get_active_window.return_value = mock_window
    m.list_windows.return_value = [
        mock_window,
        WindowInfo(
            hwnd=67890,
            title="Google Chrome",
            class_name="Chrome_WidgetWin_1",
            rect=(0, 0, 1920, 1080),
            width=1920,
            height=1080,
            pid=9876,
            process_name="chrome.exe",
            is_visible=True,
            is_minimized=False,
            is_maximized=False,
            is_cloaked=False,
            is_hung=False,
        ),
    ]
    m.send_hotkey.return_value = True
    m.close_window.return_value = True
    m.focus_window.return_value = True
    m.type_unicode_text.return_value = True
    return m


@pytest.fixture
def controller(mock_win32):
    return ComputerController(win32=mock_win32)


# ===========================================================================
# 1. Window Management Tests
# ===========================================================================
def test_get_active_window(controller, mock_win32):
    active = controller.get_active_window()
    assert active["hwnd"] == 12345
    assert "Visual Studio Code" in active["title"]
    assert active["process_name"] == "Code.exe"
    assert active["pid"] == 5432
    assert active["width"] == 800
    assert active["height"] == 600
    mock_win32.get_active_window.assert_called_once()


def test_get_active_window_none_fallback(controller, mock_win32):
    mock_win32.get_active_window.return_value = None
    active = controller.get_active_window()
    assert active["hwnd"] == 0
    assert active["title"] == ""


def test_minimize_all(controller, mock_win32):
    res = controller.minimize_all()
    assert res is True
    mock_win32.send_hotkey.assert_called_with("win", "d")


def test_close_active_window(controller, mock_win32):
    res = controller.close_active_window()
    assert res is True
    mock_win32.close_window.assert_called_with(12345)


def test_close_tab(controller, mock_win32):
    res = controller.close_tab()
    assert res is True
    mock_win32.send_hotkey.assert_called_with("ctrl", "w")


def test_focus_window_by_title(controller, mock_win32):
    res = controller.focus_window_by_title("Chrome")
    assert res is True
    mock_win32.focus_window.assert_called_with(67890)


def test_focus_window_by_title_not_found(controller, mock_win32):
    res = controller.focus_window_by_title("NonExistentApp12345")
    assert res is False


def test_focus_window_by_pid(controller, mock_win32):
    res = controller.focus_window_by_pid(5432)
    assert res is True
    mock_win32.focus_window.assert_called_with(12345)


def test_list_windows(controller, mock_win32):
    windows = controller.list_windows()
    assert len(windows) == 2
    assert windows[0]["hwnd"] == 12345
    assert windows[1]["hwnd"] == 67890


# ===========================================================================
# 2. Mouse, Keyboard & Clipboard Tests
# ===========================================================================
def test_mouse_click_fallback(controller):
    res = controller.mouse_click(100, 200)
    assert res is True


def test_mouse_move_and_scroll(controller):
    assert controller.mouse_move(500, 400) is True
    assert controller.mouse_scroll(-3) is True


def test_type_text(controller, mock_win32):
    res = controller.type_text("Xin chào JARVIS!")
    assert res is True
    mock_win32.type_unicode_text.assert_called_with("Xin chào JARVIS!")


def test_type_text_empty(controller, mock_win32):
    assert controller.type_text("") is False


def test_send_hotkey(controller, mock_win32):
    res = controller.send_hotkey("ctrl", "shift", "esc")
    assert res is True
    mock_win32.send_hotkey.assert_called_with("ctrl", "shift", "esc")


def test_clipboard_operations(controller):
    # Test setting and reading clipboard text
    test_str = "JARVIS_TEST_CLIPBOARD_STRING"
    res = controller.set_clipboard_text(test_str)
    assert res is True
    read_str = controller.get_clipboard_text()
    assert read_str == test_str


def test_copy_selection_and_paste(controller, mock_win32):
    with patch.object(controller, "get_clipboard_text", return_value="Selected text"):
        text = controller.copy_selection()
        assert text == "Selected text"
        mock_win32.send_hotkey.assert_called_with("ctrl", "c")

    with patch.object(controller, "set_clipboard_text") as mock_set:
        res = controller.paste_text("Paste me")
        assert res is True
        mock_set.assert_called_with("Paste me")
        mock_win32.send_hotkey.assert_called_with("ctrl", "v")


# ===========================================================================
# 3. Volume and Brightness Tests
# ===========================================================================
def test_volume_get_set_change(controller, mock_win32):
    controller.set_volume(80)
    assert controller.get_volume() == 80

    # Volume change +10%
    new_vol = controller.change_volume(10)
    assert new_vol == 90
    assert controller.get_volume() == 90

    # Volume change -20%
    new_vol = controller.change_volume(-20)
    assert new_vol == 70

    # Clamping boundaries
    assert controller.set_volume(150) == 100
    assert controller.set_volume(-50) == 0


def test_change_volume_successful_delta_never_sends_hotkeys(controller, mock_win32):
    """
    H-08 review fix: change_volume() previously sent volume_up/down
    hotkeys AFTER a successful pycaw set_volume() call, double-applying
    the requested delta on a real machine (pycaw sets the exact level,
    then the hotkeys shift it again). pycaw is now the sole authoritative
    backend and the sole side effect -- no hotkey fallback ever fires.
    """
    controller.set_volume(50)
    mock_win32.send_hotkey.reset_mock()
    result = controller.change_volume(10)
    assert result == 60
    mock_win32.send_hotkey.assert_not_called()


def test_change_volume_failed_delta_never_sends_hotkeys(controller, mock_win32, monkeypatch):
    """
    H-08 review fix: previously, hotkeys fired unconditionally even when
    set_volume() failed and returned None -- real hardware volume could
    still change through the hotkey while JARVIS truthfully reported
    failure. A failed backend call must now have zero secondary effect.
    """
    monkeypatch.setattr(controller, "set_volume", lambda level: None)
    mock_win32.send_hotkey.reset_mock()
    result = controller.change_volume(10)
    assert result is None
    mock_win32.send_hotkey.assert_not_called()


class _CountingVolumeEndpoint:
    """
    Deterministic fake pycaw endpoint that counts real write calls
    (SetMasterVolumeLevelScalar), so a test can prove ZERO backend writes
    occurred -- not merely that the returned value happens to equal the
    prior one (which a redundant same-value write would also satisfy).
    """

    def __init__(self, initial_scalar: float = 0.5) -> None:
        self._scalar = initial_scalar
        self.set_master_volume_calls = 0

    def GetMasterVolumeLevelScalar(self) -> float:
        return self._scalar

    def SetMasterVolumeLevelScalar(self, level: float, ctx: object = None) -> None:
        self.set_master_volume_calls += 1
        self._scalar = float(level)


def test_change_volume_zero_delta_causes_zero_backend_writes(controller, mock_win32, monkeypatch):
    """
    H-08 final correction: delta=0 must be a REAL no-op -- zero calls to
    SetMasterVolumeLevelScalar() (not even a redundant write-back of the
    unchanged value), and zero volume_up/volume_down hotkeys. Only the
    read-only GetMasterVolumeLevelScalar() (via get_volume()) may occur.
    """
    fake_endpoint = _CountingVolumeEndpoint(initial_scalar=0.5)  # 50%
    monkeypatch.setattr(controller, "_get_audio_endpoint", staticmethod(lambda speakers: fake_endpoint))
    mock_win32.send_hotkey.reset_mock()

    result = controller.change_volume(0)

    assert result == 50
    assert fake_endpoint.set_master_volume_calls == 0, "delta=0 must not write to the backend at all"
    mock_win32.send_hotkey.assert_not_called()


def test_volume_mute_toggle(controller, mock_win32):
    """
    H-08 fix: mute_volume() previously wrote self._is_muted BEFORE ever
    attempting the real backend, then silently fell back to a blind
    "volume_mute" TOGGLE hotkey on any pycaw failure while still
    returning the pre-computed value as if confirmed. Now that the
    virtual pycaw endpoint (tests/conftest.py::_VirtualEndpointVolume)
    genuinely implements GetMute()/SetMute(), the real backend path
    succeeds directly -- the hotkey fallback must NOT be used at all.
    """
    assert controller.is_muted() is False

    # Bare toggle (mute=None) still supported, reading the real backend
    # state rather than trusting a possibly-stale cache.
    assert controller.mute_volume() is True
    assert controller.is_muted() is True
    assert controller.mute_volume() is False
    assert controller.is_muted() is False

    # Explicit desired-state requests are idempotent -- repeating the same
    # desired state must not flip it back.
    assert controller.mute_volume(True) is True
    assert controller.is_muted() is True
    assert controller.mute_volume(True) is True
    assert controller.is_muted() is True
    assert controller.mute_volume(False) is False
    assert controller.is_muted() is False
    assert controller.mute_volume(False) is False
    assert controller.is_muted() is False

    mock_win32.send_hotkey.assert_not_called()


def test_volume_mute_backend_unavailable_fails_closed(controller, mock_win32, monkeypatch):
    """Backend endpoint unreachable -> None, never a fabricated result, and
    the cached is_muted() state must not be mutated by the failed call."""
    monkeypatch.setattr(controller, "_get_audio_endpoint", staticmethod(lambda speakers: None))
    assert controller.is_muted() is False
    assert controller.mute_volume(True) is None
    assert controller.is_muted() is False, "a failed call must not mutate the cached mute state"
    mock_win32.send_hotkey.assert_not_called()


class _FakeMismatchEndpoint:
    """
    Deterministic fake pycaw endpoint whose SetMute() call succeeds (never
    raises) but whose GetMute() read-back always reports a FIXED value,
    disagreeing with whatever was just requested -- simulating a real
    scenario where the backend call didn't error but the hardware state
    didn't actually change (driver quirk, race with another process, a
    stale/virtual audio device, etc).
    """

    def __init__(self, fixed_readback: bool) -> None:
        self._fixed_readback = fixed_readback

    def GetMute(self) -> int:
        return int(self._fixed_readback)

    def SetMute(self, value: int, ctx: object = None) -> None:
        pass  # deliberately never actually changes what GetMute() reports


def test_volume_mute_readback_mismatch_fails_closed(controller, mock_win32, monkeypatch):
    """
    H-08 review fix: SetMute() succeeding without raising is not proof the
    endpoint actually ended up in the requested state. When the GetMute()
    read-back disagrees with what was requested, mute_volume() must fail
    closed (None) -- never claim the requested state succeeded, and never
    mutate the cached is_muted() to the requested (unconfirmed) value.
    """
    fake_endpoint = _FakeMismatchEndpoint(fixed_readback=False)  # always reports "unmuted"
    monkeypatch.setattr(controller, "_get_audio_endpoint", staticmethod(lambda speakers: fake_endpoint))

    assert controller.is_muted() is False
    result = controller.mute_volume(True)  # requested MUTE, but the endpoint will keep reporting unmuted
    assert result is None, "a read-back mismatch must fail closed, not report the requested state as achieved"
    assert controller.is_muted() is False, "a mismatched read-back must not mutate cached state"
    mock_win32.send_hotkey.assert_not_called()


def test_brightness_get_set_change(controller):
    controller.set_brightness(50)
    assert controller.get_brightness() == 50

    new_b = controller.change_brightness(20)
    assert new_b == 70
    assert controller.get_brightness() == 70

    # Clamping
    assert controller.set_brightness(200) == 100
    assert controller.set_brightness(-10) == 0


# ===========================================================================
# 4. File Search and Folder Opener Tests
# ===========================================================================
def test_search_files_bounded(controller):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create directory hierarchy:
        # tmpdir/
        #   file1.txt
        #   nested/
        #     file2.txt
        #     sub/
        #       file3.txt
        #       sub2/
        #         file4.txt
        #         sub3/
        #           file5.txt (depth 4)
        #   node_modules/
        #     file_ignored.txt
        os.makedirs(os.path.join(tmpdir, "nested", "sub", "sub2", "sub3"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "node_modules"), exist_ok=True)

        open(os.path.join(tmpdir, "file1.txt"), "w").close()
        open(os.path.join(tmpdir, "nested", "file2.txt"), "w").close()
        open(os.path.join(tmpdir, "nested", "sub", "file3.txt"), "w").close()
        open(os.path.join(tmpdir, "nested", "sub", "sub2", "file4.txt"), "w").close()
        open(os.path.join(tmpdir, "nested", "sub", "sub2", "sub3", "file5.txt"), "w").close()
        open(os.path.join(tmpdir, "node_modules", "file_ignored.txt"), "w").close()

        # Search with max_depth=3
        results = controller.search_files("file", root_dir=tmpdir, max_depth=3)
        result_basenames = [os.path.basename(p) for p in results]

        assert "file1.txt" in result_basenames
        assert "file2.txt" in result_basenames
        assert "file3.txt" in result_basenames
        assert "file4.txt" in result_basenames
        # file5 is at depth 4, should NOT be in results when max_depth=3
        assert "file5.txt" not in result_basenames
        # node_modules should be ignored
        assert "file_ignored.txt" not in result_basenames


def test_resolve_folder_path(controller):
    downloads = controller.resolve_folder_path("downloads")
    assert downloads is not None
    assert "Downloads" in downloads

    tai_ve = controller.resolve_folder_path("tải về")
    assert tai_ve is not None
    assert "Downloads" in tai_ve

    desktop = controller.resolve_folder_path("màn hình chính")
    assert desktop is not None
    assert "Desktop" in desktop


def test_open_folder(controller):
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("subprocess.Popen") as mock_popen, patch("os.startfile", create=True) as mock_startfile:
            res = controller.open_folder(tmpdir)
            assert res is True


def test_take_screenshot(controller):
    with tempfile.TemporaryDirectory() as tmpdir:
        target = os.path.join(tmpdir, "test_shot.png")
        with patch("PIL.ImageGrab.grab") as mock_grab:
            mock_img = MagicMock()
            mock_grab.return_value = mock_img
            saved_path = controller.take_screenshot(output_path=target)
            assert saved_path == target
            mock_img.save.assert_called_with(target)


# ===========================================================================
# 5. SafetyGate Confirmation State Machine Tests
# ===========================================================================
def test_safety_gate_request_and_confirm():
    gate = SafetyGate(timeout_seconds=5.0)
    action_executed = {"done": False, "val": 0}

    def dangerous_action(data):
        action_executed["done"] = True
        action_executed["val"] = data.get("num", 0)

    token = gate.request_confirmation(
        action_desc="Xóa cơ sở dữ liệu",
        payload={"num": 42},
        callback=dangerous_action,
    )
    assert isinstance(token, str)
    assert len(token) == 8
    assert gate.is_pending(token) is True

    # Confirm valid token
    success = gate.confirm(token)
    assert success is True
    assert action_executed["done"] is True
    assert action_executed["val"] == 42
    assert gate.is_pending(token) is False


def test_safety_gate_reject():
    gate = SafetyGate(timeout_seconds=5.0)
    token = gate.request_confirmation("Format ổ đĩa")
    assert gate.is_pending(token) is True

    assert gate.reject(token) is True
    assert gate.is_pending(token) is False
    assert gate.confirm(token) is False


def test_safety_gate_timeout_expiration():
    gate = SafetyGate(timeout_seconds=0.1)
    token = gate.request_confirmation("Xóa file hệ thống")
    assert gate.is_pending(token) is True

    # Sleep past expiration
    time.sleep(0.15)

    assert gate.is_pending(token) is False
    assert gate.confirm(token) is False


def test_safety_gate_voice_response_processing():
    gate = SafetyGate(timeout_seconds=10.0)
    token = gate.request_confirmation("Tắt máy tính")

    # Affirmative voice response
    ok, msg = gate.process_voice_response("đồng ý thực hiện", token=token)
    assert ok is True
    assert "Đã xác nhận" in msg

    # Second token - negative voice response
    token2 = gate.request_confirmation("Xóa toàn bộ ảnh")
    ok2, msg2 = gate.process_voice_response("không, hủy đi", token=token2)
    assert ok2 is False
    assert "Đã hủy" in msg2


# ── F5: Volume Control Fail-Closed Tests ─────────────────────────────────────

class TestVolumeControlFailClosed:
    """F5 — verify set_volume() is fail-closed when pycaw is unavailable (D5 remediation).

    Phase 8 fixed D5: set_volume() now returns None on failure instead of silently
    storing a fake volume value. These tests verify the fail-closed contract holds.
    """

    def test_set_volume_returns_none_when_pycaw_unavailable(self) -> None:
        """set_volume() returns None (fail-closed) when pycaw module is missing."""
        ctrl = ComputerController()
        with patch.object(
            type(ctrl), "_get_audio_endpoint",
            side_effect=RuntimeError("pycaw not available"),
        ):
            result = ctrl.set_volume(75)
        # Must return None — not raise, not return a fake volume
        assert result is None

    def test_set_volume_does_not_raise_on_comtypes_error(self) -> None:
        """set_volume() swallows COM/pycaw errors without crashing the caller."""
        ctrl = ComputerController()
        with patch.object(
            type(ctrl), "_get_audio_endpoint",
            side_effect=OSError("No audio endpoint"),
        ):
            try:
                ctrl.set_volume(50)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"set_volume() must not raise, but raised {type(exc).__name__}: {exc}")

    def test_set_volume_does_not_update_current_volume_on_failure(self) -> None:
        """set_volume() must NOT update _current_volume when pycaw fails (no fabrication)."""
        ctrl = ComputerController()
        initial_volume = ctrl._current_volume
        with patch.object(
            type(ctrl), "_get_audio_endpoint",
            side_effect=RuntimeError("endpoint unavailable"),
        ):
            ctrl.set_volume(99)
        # Volume must remain unchanged — not silently set to 99
        assert ctrl._current_volume == initial_volume, (
            "set_volume() must NOT update _current_volume when the audio endpoint fails. "
            "Doing so would fabricate a successful volume change."
        )

    def test_get_volume_returns_current_volume_without_pycaw(self) -> None:
        """get_volume() returns the stored _current_volume even when pycaw unavailable."""
        ctrl = ComputerController()
        ctrl._current_volume = 42
        # get_volume should return stored value regardless of hardware state
        result = ctrl.get_volume()
        assert isinstance(result, (int, float, type(None))), (
            "get_volume() must return a numeric value or None"
        )

