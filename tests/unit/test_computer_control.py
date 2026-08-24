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


def test_volume_mute_toggle(controller, mock_win32):
    assert controller.is_muted() is False
    assert controller.mute_volume() is True
    assert controller.is_muted() is True
    assert controller.mute_volume() is False
    assert controller.is_muted() is False
    mock_win32.send_hotkey.assert_called_with("volume_mute")


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
