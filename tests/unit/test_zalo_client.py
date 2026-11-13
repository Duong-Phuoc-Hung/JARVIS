"""
tests/unit/test_zalo_client.py
==============================
Unit tests for Zalo PC Client Native Automation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from jarvis.automation.zalo_client import ZaloPCAutomation, _find_zalo_executable
from jarvis.platform.uiautomation import UIControlElement


def test_find_zalo_executable_resolution():
    with patch("shutil.which", return_value="C:\\Fake\\Zalo.exe"), \
         patch("pathlib.Path.is_file", return_value=True):
        assert _find_zalo_executable() == "C:\\Fake\\Zalo.exe"

    with patch("shutil.which", return_value=None), \
         patch("pathlib.Path.is_file", return_value=False):
        assert _find_zalo_executable() is None


def test_send_message_validation_fail_closed():
    client = ZaloPCAutomation(controller=MagicMock(), uia=MagicMock())

    # Empty recipient
    res_empty_rec = client.send_message(recipient="", message="Hello")
    assert res_empty_rec["success"] is False
    assert res_empty_rec["error"] == "RECIPIENT_EMPTY"

    # Empty payload
    res_empty_body = client.send_message(recipient="Hưng", message="", attachment_path=None)
    assert res_empty_body["success"] is False
    assert res_empty_body["error"] == "PAYLOAD_EMPTY"


def test_send_message_zalo_not_available_fail_closed():
    mock_ctrl = MagicMock()
    mock_uia = MagicMock()
    client = ZaloPCAutomation(controller=mock_ctrl, uia=mock_uia)

    with patch.object(client, "launch_or_activate", return_value=False):
        res = client.send_message(recipient="Hưng", message="Test message")
        assert res["success"] is False
        assert res["error"] == "ZALO_NOT_AVAILABLE"


def test_send_message_success_flow():
    mock_ctrl = MagicMock()
    mock_uia = MagicMock()
    mock_ctrl.send_hotkey.return_value = True
    mock_ctrl.send_keys.return_value = True
    mock_ctrl.set_clipboard_text.return_value = True

    client = ZaloPCAutomation(controller=mock_ctrl, uia=mock_uia)

    with patch.object(client, "launch_or_activate", return_value=True):
        res = client.send_message(recipient="Anh Hưng", message="Báo cáo tiến độ hoàn tất.")
        assert res["success"] is True
        assert res["recipient"] == "Anh Hưng"
        assert "thành công" in res["message"]

        # Verify hotkeys triggered: Ctrl+F for search, Ctrl+V for paste, Enter to send
        mock_ctrl.send_hotkey.assert_any_call("ctrl", "f")
        mock_ctrl.send_hotkey.assert_any_call("ctrl", "v")
        mock_ctrl.send_keys.assert_any_call("{ENTER}")


def test_launch_or_activate_when_already_running():
    mock_ctrl = MagicMock()
    mock_uia = MagicMock()
    mock_win = UIControlElement(
        hwnd=12345,
        name="Zalo",
        class_name="ZaloMainWindow",
        rect=(0, 0, 800, 600),
        center=(400, 300),
    )
    mock_uia.is_supported = True
    mock_uia.ensure_desktop.return_value = True
    mock_uia._user32 = MagicMock()

    client = ZaloPCAutomation(controller=mock_ctrl, uia=mock_uia)
    with patch.object(client, "find_zalo_window", return_value=mock_win):
        ok = client.launch_or_activate()
        assert ok is True
        mock_uia._user32.SetForegroundWindow.assert_called_once_with(12345)
