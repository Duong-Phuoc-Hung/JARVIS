"""
tests/unit/test_uiautomation.py
===============================
Unit tests for Native Windows UI Automation & Accessibility Integration in JARVIS.
Verifies element discovery, fail-closed handling, controller integration,
and GUIActor accessibility-first fast path.
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from jarvis.automation.control import ComputerController
from jarvis.automation.gui_actor import GUIActor
from jarvis.platform.uiautomation import UIControlElement, WindowsUIAutomation


class TestWindowsUIAutomation(unittest.TestCase):
    """Unit tests for WindowsUIAutomation and UIControlElement."""

    def test_uicontrol_element_dataclass_and_serialization(self) -> None:
        elem = UIControlElement(
            hwnd=12345,
            name="Submit Button",
            class_name="Button",
            rect=(100, 200, 300, 250),
            center=(200, 225),
            is_visible=True,
            parent_hwnd=54321,
            control_type="button",
        )
        d = elem.to_dict()
        self.assertEqual(d["hwnd"], 12345)
        self.assertEqual(d["name"], "Submit Button")
        self.assertEqual(d["class_name"], "Button")
        self.assertEqual(d["rect"], [100, 200, 300, 250])
        self.assertEqual(d["center"], [200, 225])
        self.assertTrue(d["is_visible"])
        self.assertEqual(d["parent_hwnd"], 54321)
        self.assertEqual(d["control_type"], "button")

    def test_uiautomation_initialization(self) -> None:
        uia = WindowsUIAutomation()
        if sys.platform == "win32":
            self.assertTrue(uia.is_supported)
            self.assertIsNotNone(uia._user32)
            # Ensure desktop doesn't crash
            result = uia.ensure_desktop()
            self.assertIsInstance(result, bool)
        else:
            self.assertFalse(uia.is_supported)
            self.assertIsNone(uia._user32)

    def test_non_windows_platform_fail_closed(self) -> None:
        with patch("sys.platform", "linux"):
            uia = WindowsUIAutomation()
            self.assertFalse(uia.is_supported)
            self.assertFalse(uia.ensure_desktop())
            self.assertIsNone(uia.get_foreground_window())
            self.assertEqual(uia.enumerate_windows(), [])
            self.assertEqual(uia.enumerate_controls(1234), [])
            self.assertIsNone(uia.find_element("anything"))
            self.assertFalse(uia.click_element("anything"))
            self.assertFalse(uia.type_into_element("anything", "text"))

    def test_find_element_missing_returns_none(self) -> None:
        uia = WindowsUIAutomation()
        elem = uia.find_element("nonexistent_element_random_query_z987_impossible")
        self.assertIsNone(elem)

    def test_click_element_missing_returns_false_fail_closed(self) -> None:
        uia = WindowsUIAutomation()
        res = uia.click_element("nonexistent_element_random_query_z987_impossible")
        self.assertFalse(res)

    def test_type_into_element_missing_returns_false_fail_closed(self) -> None:
        uia = WindowsUIAutomation()
        res = uia.type_into_element("nonexistent_element_random_query_z987_impossible", "test text")
        self.assertFalse(res)

    def test_mocked_click_element_button_sends_bm_click(self) -> None:
        uia = WindowsUIAutomation()
        mock_elem = UIControlElement(
            hwnd=999,
            name="Save",
            class_name="Button",
            rect=(10, 10, 50, 30),
            center=(30, 20),
            is_visible=True,
            control_type="button",
        )
        with patch.object(uia, "find_element", return_value=mock_elem):
            with patch.object(uia, "_user32") as mock_user32:
                mock_user32.SendMessageW.return_value = 0
                res = uia.click_element("Save")
                self.assertTrue(res)
                # BM_CLICK is 0x00F5 = 245
                mock_user32.SendMessageW.assert_called_with(999, 0x00F5, 0, 0)

    def test_mocked_type_into_element_edit_sends_wm_settext(self) -> None:
        uia = WindowsUIAutomation()
        mock_elem = UIControlElement(
            hwnd=888,
            name="Username",
            class_name="Edit",
            rect=(10, 10, 100, 30),
            center=(55, 20),
            is_visible=True,
            control_type="edit",
        )
        with patch.object(uia, "find_element", return_value=mock_elem):
            with patch.object(uia, "_user32") as mock_user32:
                mock_user32.SendMessageW.return_value = 1
                res = uia.type_into_element("Username", "admin")
                self.assertTrue(res)
                # WM_SETTEXT is 0x000C = 12
                self.assertEqual(mock_user32.SendMessageW.call_args[0][0], 888)
                self.assertEqual(mock_user32.SendMessageW.call_args[0][1], 0x000C)


class TestComputerControllerUIAutomation(unittest.TestCase):
    """Unit tests for ComputerController native UI Automation integration."""

    def setUp(self) -> None:
        self.controller = ComputerController()

    def test_controller_has_uiautomation_property(self) -> None:
        self.assertIsNotNone(self.controller.uiautomation)

    def test_controller_find_ui_element_missing_returns_none(self) -> None:
        res = self.controller.find_ui_element("completely_imaginary_window_element_99999")
        self.assertIsNone(res)

    def test_controller_click_ui_element_missing_returns_false(self) -> None:
        res = self.controller.click_ui_element("completely_imaginary_window_element_99999")
        self.assertFalse(res)

    def test_controller_type_into_ui_element_missing_returns_false(self) -> None:
        res = self.controller.type_into_ui_element("completely_imaginary_window_element_99999", "abc")
        self.assertFalse(res)

    def test_controller_find_ui_element_mocked(self) -> None:
        mock_elem = UIControlElement(
            hwnd=777,
            name="OK",
            class_name="Button",
            rect=(50, 50, 120, 80),
            center=(85, 65),
            is_visible=True,
            control_type="button",
        )
        with patch.object(self.controller.uiautomation, "find_element", return_value=mock_elem):
            res = self.controller.find_ui_element("OK")
            self.assertIsNotNone(res)
            self.assertEqual(res["hwnd"], 777)
            self.assertEqual(res["name"], "OK")
            self.assertEqual(res["center"], [85, 65])


class TestGUIActorUIAutomationFastPath(unittest.TestCase):
    """Unit tests verifying GUIActor native UI Automation fast path & fallback."""

    def test_gui_actor_uses_native_uia_fast_path(self) -> None:
        mock_uia = MagicMock(spec=WindowsUIAutomation)
        mock_uia.is_supported = True
        mock_uia.find_element.return_value = UIControlElement(
            hwnd=111,
            name="Submit",
            class_name="Button",
            rect=(100, 200, 300, 250),
            center=(200, 225),
            is_visible=True,
            control_type="button",
        )

        mock_controller = MagicMock(spec=ComputerController)
        mock_controller.mouse_click.return_value = True

        actor = GUIActor(controller=mock_controller, uiautomation=mock_uia)
        success = actor.click_element("Submit", verify=False)

        self.assertTrue(success)
        mock_uia.find_element.assert_called_with("Submit")
        mock_controller.mouse_click.assert_called_once_with(x=200, y=225, button="left", clicks=1)

        last_action = actor.action_history[-1]
        self.assertTrue(last_action.success)
        self.assertEqual(last_action.grounded_element.source, "win32_uia")
        self.assertEqual(last_action.target_pixel_pos, (200, 225))

    def test_gui_actor_falls_back_when_native_uia_returns_none(self) -> None:
        mock_uia = MagicMock(spec=WindowsUIAutomation)
        mock_uia.is_supported = True
        mock_uia.find_element.return_value = None

        mock_cu = MagicMock()
        mock_cu.get_screen_size.return_value = (1920, 1080)
        from jarvis.vision.computer_use import BoundingBox, UIElement
        mock_cu.locate_element.return_value = UIElement(
            name="Fallback",
            element_type="button",
            bbox=BoundingBox.from_pixel_coords(50, 50, 150, 100, 1920, 1080),
            source="vision_llm",
        )

        mock_controller = MagicMock(spec=ComputerController)
        mock_controller.mouse_click.return_value = True

        actor = GUIActor(computer_use=mock_cu, controller=mock_controller, uiautomation=mock_uia)
        success = actor.click_element("Fallback", verify=False)

        self.assertTrue(success)
        mock_uia.find_element.assert_called_with("Fallback")
        mock_cu.locate_element.assert_called_once()
        last_action = actor.action_history[-1]
        self.assertEqual(last_action.grounded_element.source, "vision_llm")


if __name__ == "__main__":
    unittest.main()
