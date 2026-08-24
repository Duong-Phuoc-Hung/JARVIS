"""
tests/unit/test_computer_use_vision.py
======================================
Comprehensive Unit Test Suite for Computer-Use Vision, Visual Verification,
and Vision-Driven GUI Actor (Milestone M4 - R4).
"""
from __future__ import annotations

import io
import json
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw
import pytest

from jarvis.automation.control import ComputerController
from jarvis.automation.gui_actor import GUIActor, GUIActionResult
from jarvis.vision.computer_use import (
    BoundingBox,
    CoordinateMapper,
    UIElement,
    UIElementDetector,
    ComputerUseVision,
)
from jarvis.vision.ocr import DesktopOCR
from jarvis.vision.screen import ScreenVisionManager
from jarvis.vision.visual_verifier import VisualDiffResult, VisualVerifier


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures & Helpers
# ──────────────────────────────────────────────────────────────────────────────

def create_synthetic_image(width: int = 400, height: int = 300, color: str = "white") -> bytes:
    """Creates in-memory JPEG bytes for testing."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def create_image_with_rectangle(
    width: int = 400,
    height: int = 300,
    rect: Tuple[int, int, int, int] = (50, 50, 150, 150),
    rect_color: str = "red",
    bg_color: str = "white",
) -> bytes:
    """Creates in-memory JPEG bytes with a colored rectangle drawn on it."""
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    draw.rectangle(rect, fill=rect_color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# 1. BoundingBox & CoordinateMapper Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_bounding_box_init_and_clamping():
    """Verify BoundingBox normalizes coordinates and clamps to [0, 1000]."""
    bbox = BoundingBox(ymin=-50, xmin=1200, ymax=600, xmax=200)
    # ymin clamped to 0, ymax is 600
    assert bbox.ymin == 0
    assert bbox.ymax == 600
    # xmin was 1200, xmax was 200 -> clamped to 1000 and 200, then min/max ordered: [200, 1000]
    assert bbox.xmin == 200
    assert bbox.xmax == 1000
    assert bbox.center_norm == (600, 300)
    assert bbox.width_norm == 800
    assert bbox.height_norm == 600


def test_bounding_box_to_and_from_pixel_coords():
    """Verify bidirectional conversion between normalized grid and screen pixels."""
    screen_w, screen_h = 1920, 1080

    # 1. Normalized to Pixel
    bbox = BoundingBox(ymin=100, xmin=100, ymax=500, xmax=500)
    left, top, right, bottom = bbox.to_pixel_coords(screen_w, screen_h)
    assert left == 192
    assert top == 108
    assert right == 960
    assert bottom == 540

    cx, cy = bbox.center_pixel(screen_w, screen_h)
    assert cx == (192 + 960) // 2
    assert cy == (108 + 540) // 2

    # 2. Pixel to Normalized
    restored = BoundingBox.from_pixel_coords(left, top, right, bottom, screen_w, screen_h)
    assert abs(restored.xmin - 100) <= 1
    assert abs(restored.ymin - 100) <= 1
    assert abs(restored.xmax - 500) <= 1
    assert abs(restored.ymax - 500) <= 1


def test_bounding_box_contains_and_iou():
    """Verify containment check and IoU calculation."""
    box_a = BoundingBox(ymin=100, xmin=100, ymax=300, xmax=300)
    box_b = BoundingBox(ymin=100, xmin=100, ymax=300, xmax=300)
    box_c = BoundingBox(ymin=200, xmin=200, ymax=400, xmax=400)
    box_disjoint = BoundingBox(ymin=500, xmin=500, ymax=600, xmax=600)

    assert box_a.contains(200, 200) is True
    assert box_a.contains(50, 50) is False

    # Exact match has IoU 1.0
    assert box_a.iou(box_b) == 1.0
    # Overlapping boxes
    assert 0.0 < box_a.iou(box_c) < 1.0
    # Disjoint boxes have IoU 0.0
    assert box_a.iou(box_disjoint) == 0.0


def test_coordinate_mapper_conversions():
    """Verify CoordinateMapper bidirectional conversion."""
    mapper = CoordinateMapper(default_width=1280, default_height=720)
    w, h = mapper.get_screen_size()
    assert w > 0 and h > 0

    x_px, y_px = mapper.norm_to_pixel(500, 500, screen_w=1000, screen_h=1000)
    assert x_px == 500
    assert y_px == 500

    x_norm, y_norm = mapper.pixel_to_norm(250, 250, screen_w=1000, screen_h=1000)
    assert x_norm == 250
    assert y_norm == 250


def test_ui_element_serialization():
    """Verify UIElement properties and dict serialization."""
    bbox = BoundingBox(ymin=10, xmin=20, ymax=50, xmax=80)
    elem = UIElement(
        name="Submit",
        element_type="button",
        bbox=bbox,
        text="Submit",
        confidence=0.95,
        source="vision_llm",
    )
    assert elem.center_norm == (50, 30)
    d = elem.to_dict()
    assert d["name"] == "Submit"
    assert d["element_type"] == "button"
    assert d["bbox"]["xmin"] == 20
    assert d["confidence"] == 0.95
    assert d["source"] == "vision_llm"


# ──────────────────────────────────────────────────────────────────────────────
# 2. UIElementDetector 4-Tier Grounding Engine Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_tier1_vision_llm_grounding():
    """Verify Tier 1 Vision LLM parses structured JSON bounding boxes."""
    mock_vm = MagicMock(spec=ScreenVisionManager)
    mock_vm.gemini_api_key = "fake-key"
    mock_vm.openai_api_key = ""

    json_response = json.dumps([
        {
            "name": "Save Button",
            "element_type": "button",
            "box_2d": [100, 200, 150, 300],
            "confidence": 0.98,
            "text": "Save",
        }
    ])
    mock_vm.analyze_screen.return_value = f"```json\n{json_response}\n```"

    detector = UIElementDetector(vision_manager=mock_vm)
    elements = detector.detect_via_vision_llm("Save", b"fake_bytes", 1920, 1080)

    assert len(elements) == 1
    el = elements[0]
    assert el.name == "Save Button"
    assert el.element_type == "button"
    assert el.bbox.ymin == 100
    assert el.bbox.xmin == 200
    assert el.bbox.ymax == 150
    assert el.bbox.xmax == 300
    assert el.confidence == 0.98
    assert el.source == "vision_llm"


def test_tier2_ocr_grounding_fallback():
    """Verify Tier 2 local OCR bounding box extraction."""
    mock_vm = MagicMock(spec=ScreenVisionManager)
    mock_ocr = MagicMock(spec=DesktopOCR)
    detector = UIElementDetector(vision_manager=mock_vm, ocr_engine=mock_ocr)

    # Patch pytesseract to simulate OCR word boxes
    fake_data = {
        "text": ["", "Cancel", "Save", "File"],
        "conf": [0, 95, 90, 85],
        "left": [0, 100, 200, 300],
        "top": [0, 50, 50, 50],
        "width": [0, 60, 50, 40],
        "height": [0, 25, 25, 25],
    }

    synthetic_img = Image.new("RGB", (1000, 1000), color="white")

    with patch("jarvis.vision.computer_use.PYTESSERACT_AVAILABLE", True), \
         patch("jarvis.vision.computer_use.pytesseract") as mock_pytess:
        mock_pytess.Output.DICT = "dict"
        mock_pytess.image_to_data.return_value = fake_data

        elements = detector.detect_via_ocr("Save", synthetic_img, 1000, 1000)
        assert len(elements) == 1
        assert elements[0].name == "Save"
        assert elements[0].source == "ocr"
        assert elements[0].bbox.xmin == 200


def test_tier3_win32_uia_grounding():
    """Verify Tier 3 Win32 child window detection."""
    mock_vm = MagicMock(spec=ScreenVisionManager)
    detector = UIElementDetector(vision_manager=mock_vm)

    with patch("jarvis.vision.computer_use.sys.platform", "win32"), \
         patch("jarvis.vision.computer_use.WIN32GUI_AVAILABLE", True), \
         patch("jarvis.vision.computer_use.win32gui") as mock_win32:

        def mock_enum(callback, _):
            # Simulate invoking callback with fake hwnd
            callback(1001, None)

        mock_win32.EnumWindows.side_effect = mock_enum
        mock_win32.IsWindowVisible.return_value = True
        mock_win32.GetWindowText.return_value = "Settings Button"
        mock_win32.GetClassName.return_value = "Button"
        mock_win32.GetWindowRect.return_value = (100, 100, 300, 150)

        elements = detector.detect_via_win32_uia("Settings", 1000, 1000)
        assert len(elements) == 1
        assert elements[0].name == "Settings Button"
        assert elements[0].element_type == "button"
        assert elements[0].source == "win32_uia"


def test_tier4_template_heuristics_fallback():
    """Verify Tier 4 heuristic and template matching for standard controls."""
    detector = UIElementDetector()

    # Close button heuristic
    close_elems = detector.detect_via_template_and_heuristics("Close Window", None, 1920, 1080)
    assert len(close_elems) >= 1
    assert "Close" in close_elems[0].name
    assert close_elems[0].bbox.xmin >= 900  # Top right

    # Search bar heuristic
    search_elems = detector.detect_via_template_and_heuristics("Search products", None, 1920, 1080)
    assert len(search_elems) >= 1
    assert "Search" in search_elems[0].name

    # Generic fallback
    gen_elems = detector.detect_via_template_and_heuristics("some_custom_widget", None, 1920, 1080)
    assert len(gen_elems) >= 1
    assert gen_elems[0].source == "synthetic"


def test_computer_use_vision_locate_cascading():
    """Verify ComputerUseVision cascades through tiers."""
    mock_vm = MagicMock(spec=ScreenVisionManager)
    mock_vm.gemini_api_key = ""
    mock_vm.openai_api_key = ""
    mock_vm.capture_screenshot.return_value = (create_synthetic_image(), "fake_b64")

    cu_vision = ComputerUseVision(vision_manager=mock_vm)
    # Tier 1 fails (no api key), Tier 2 fails (empty OCR), Tier 3 fails (no win32 mock), falls back to Tier 4
    elem = cu_vision.locate_element("close")
    assert elem is not None
    assert "Close" in elem.name


# ──────────────────────────────────────────────────────────────────────────────
# 3. VisualVerifier Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_visual_verifier_identical_images_zero_diff():
    """Verify identical images report 0.0 diff and state_changed=False."""
    verifier = VisualVerifier(diff_threshold=0.005)
    img_bytes = create_synthetic_image(200, 200, color="white")

    result = verifier.verify_action(img_bytes, img_bytes)
    assert result.state_changed is False
    assert result.diff_ratio == 0.0
    assert result.changed_roi is None


def test_visual_verifier_different_images_detected():
    """Verify pixel differences between before and after images are detected."""
    verifier = VisualVerifier(diff_threshold=0.005)
    before_bytes = create_synthetic_image(400, 400, color="white")
    # After image has 100x100 black box (10000 / 160000 = 6.25% change)
    after_bytes = create_image_with_rectangle(400, 400, rect=(50, 50, 150, 150), rect_color="black")

    result = verifier.verify_action(before_bytes, after_bytes)
    assert result.state_changed is True
    assert result.diff_ratio > 0.01
    assert result.changed_roi is not None
    assert result.changed_roi[0] <= 60
    assert result.changed_roi[1] <= 60


def test_visual_verifier_roi_overlap_check():
    """Verify ROI overlap detection."""
    verifier = VisualVerifier()
    changed_roi = (50, 50, 150, 150)
    target_roi_matching = (60, 60, 120, 120)
    target_roi_disjoint = (300, 300, 380, 380)

    assert verifier.check_roi_overlap(changed_roi, target_roi_matching) is True
    assert verifier.check_roi_overlap(changed_roi, target_roi_disjoint) is False


def test_visual_verifier_expected_effect_text_appeared():
    """Verify expected effect 'text_appeared:...' uses OCR."""
    mock_ocr = MagicMock(spec=DesktopOCR)
    mock_ocr.extract_text.return_value = "File successfully saved to disk."
    verifier = VisualVerifier(ocr_engine=mock_ocr)

    before_bytes = create_synthetic_image()
    after_bytes = create_synthetic_image()

    result = verifier.verify_action(
        before_bytes, after_bytes, expected_effect="text_appeared:saved"
    )
    assert result.expected_change_detected is True
    assert "saved" in result.semantic_verification.lower()


# ──────────────────────────────────────────────────────────────────────────────
# 4. GUIActor & Self-Healing Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_controller():
    ctrl = MagicMock(spec=ComputerController)
    ctrl.mouse_click.return_value = True
    ctrl.mouse_move.return_value = True
    ctrl.type_text.return_value = True
    ctrl.send_hotkey.return_value = True
    return ctrl


def test_gui_actor_click_element_success(mock_controller):
    """Verify successful click and visual verification."""
    mock_vm = MagicMock(spec=ScreenVisionManager)
    before_img = create_synthetic_image(400, 400, "white")
    after_img = create_image_with_rectangle(400, 400, (100, 100, 200, 200), "black")
    mock_vm.capture_screenshot.side_effect = [(before_img, ""), (after_img, "")]

    cu_vision = ComputerUseVision(vision_manager=mock_vm)
    verifier = VisualVerifier(diff_threshold=0.001, vision_manager=mock_vm)

    actor = GUIActor(
        computer_use=cu_vision,
        controller=mock_controller,
        verifier=verifier,
        vision_manager=mock_vm,
    )

    success = actor.click_element("Save", verify=True)
    assert success is True
    assert len(actor.action_history) == 1
    assert actor.action_history[0].success is True
    mock_controller.mouse_click.assert_called_once()


def test_gui_actor_self_healing_retry_on_dead_click(mock_controller):
    """Verify self-healing retry logic when no visual change is detected on first click."""
    mock_vm = MagicMock(spec=ScreenVisionManager)
    identical_img = create_synthetic_image(400, 400, "white")
    changed_img = create_image_with_rectangle(400, 400, (100, 100, 200, 200), "black")

    # Attempt 0: before & after identical (dead click)
    # Attempt 1: before & after changed (successful retry)
    mock_vm.capture_screenshot.side_effect = [
        (identical_img, ""),  # attempt 0 before
        (identical_img, ""),  # attempt 0 after
        (identical_img, ""),  # attempt 1 before
        (changed_img, ""),    # attempt 1 after
    ]

    cu_vision = ComputerUseVision(vision_manager=mock_vm)
    verifier = VisualVerifier(diff_threshold=0.001, vision_manager=mock_vm)

    actor = GUIActor(
        computer_use=cu_vision,
        controller=mock_controller,
        verifier=verifier,
        vision_manager=mock_vm,
    )

    success = actor.click_element("Submit", verify=True, max_retries=1)
    assert success is True
    assert len(actor.action_history) == 1
    assert actor.action_history[0].retries_used == 1
    assert mock_controller.mouse_click.call_count == 2


def test_gui_actor_type_into_element(mock_controller):
    """Verify type_into_element focuses, clears, types text, and verifies."""
    mock_vm = MagicMock(spec=ScreenVisionManager)
    before_img = create_synthetic_image(400, 400, "white")
    after_img = create_synthetic_image(400, 400, "white")
    mock_vm.capture_screenshot.return_value = (before_img, "")

    mock_ocr = MagicMock(spec=DesktopOCR)
    mock_ocr.extract_text.return_value = "Hello World"

    cu_vision = ComputerUseVision(vision_manager=mock_vm)
    verifier = VisualVerifier(vision_manager=mock_vm, ocr_engine=mock_ocr)

    actor = GUIActor(
        computer_use=cu_vision,
        controller=mock_controller,
        verifier=verifier,
        vision_manager=mock_vm,
    )

    success = actor.type_into_element("Search Box", "Hello World", clear_first=True, verify=True)
    assert success is True
    mock_controller.send_hotkey.assert_any_call("ctrl", "a")
    mock_controller.send_hotkey.assert_any_call("backspace")
    mock_controller.type_text.assert_called_with("Hello World")


def test_gui_actor_drag_element(mock_controller):
    """Verify drag_element grounds source and target and executes drag."""
    mock_vm = MagicMock(spec=ScreenVisionManager)
    before_img = create_synthetic_image(400, 400, "white")
    after_img = create_image_with_rectangle(400, 400, (10, 10, 50, 50), "black")
    mock_vm.capture_screenshot.side_effect = [
        (before_img, ""),
        (after_img, ""),
    ]

    cu_vision = ComputerUseVision(vision_manager=mock_vm)
    verifier = VisualVerifier(diff_threshold=0.001, vision_manager=mock_vm)

    actor = GUIActor(
        computer_use=cu_vision,
        controller=mock_controller,
        verifier=verifier,
        vision_manager=mock_vm,
    )

    success = actor.drag_element("Item 1", "Trash Bin", verify=True)
    assert success is True
    assert len(actor.action_history) == 1
    assert actor.action_history[0].action == "drag"
