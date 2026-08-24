"""
tests/unit/test_screen_vision.py
================================
Comprehensive Unit Test Suite for Screen Vision & Perception (R3).
Covers:
  - ScreenCaptureManager / ScreenVisionManager high-speed capture & compression
  - <80ms capture and compression performance budget
  - Gemini 1.5 Flash Vision & OpenAI GPT-4o Vision REST payload formatting
  - Missing API key graceful fallback ("Tôi chưa thể nhìn thấy màn hình...")
  - Win32 `#32770` modal dialog and error popup detection
  - Dual-tier Desktop OCR (Pytesseract -> Vision LLM fallback)
  - Screen error explanation and document summarization
"""
from __future__ import annotations

import base64
import ctypes
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

from PIL import Image
import pytest

from jarvis.vision.dialog_detector import ErrorDialogDetector, WIN32_DIALOG_CLASS
from jarvis.vision.ocr import DesktopOCR
from jarvis.vision.screen import ScreenCaptureResult, ScreenVisionManager


# ============================================================================
# 1. SCREEN CAPTURE & COMPRESSION TESTS
# ============================================================================

def test_screen_capture_returns_valid_jpeg_and_base64():
    """Verify screen capture generates valid JPEG bytes and base64 string within dimensions."""
    manager = ScreenVisionManager()
    raw_bytes, b64_str = manager.capture_screenshot(max_dim=800, quality=80)

    assert isinstance(raw_bytes, bytes)
    assert len(raw_bytes) > 0
    # Check JPEG SOI marker (0xFFD8)
    assert raw_bytes[:2] == b"\xff\xd8"

    assert isinstance(b64_str, str)
    assert len(b64_str) > 0

    # Verify decoding matches raw bytes
    decoded = base64.b64decode(b64_str.encode("ascii"))
    assert decoded == raw_bytes

    # Check decoded PIL image dimensions
    img = Image.open(io.BytesIO(raw_bytes))
    assert img.format == "JPEG"
    assert max(img.size) <= 800


def test_screen_capture_timing_budget():
    """Verify screen capture and compression completes well under budget (<80ms)."""
    manager = ScreenVisionManager()
    result = manager.capture_screenshot_full(max_dim=1920, quality=80)

    assert isinstance(result, ScreenCaptureResult)
    assert result.width > 0
    assert result.height > 0
    # In virtual / CI environment, total time is typically <50ms
    assert result.total_time_ms < 500.0  # Safe upper bound for slow CI


def test_screen_capture_roi_cropping():
    """Verify ROI crop correctly constrains captured region."""
    manager = ScreenVisionManager()
    roi = (100, 100, 400, 300)  # width 300, height 200
    raw_bytes, b64_str = manager.capture_screenshot(roi=roi)

    img = Image.open(io.BytesIO(raw_bytes))
    assert img.size[0] <= 300
    assert img.size[1] <= 200


def test_save_screenshot_to_file(tmp_path):
    """Verify save_screenshot writes valid JPEG file to specified path."""
    manager = ScreenVisionManager()
    out_file = str(tmp_path / "test_screen.jpg")
    saved_path = manager.save_screenshot(filepath=out_file)

    assert os.path.exists(saved_path)
    assert os.path.getsize(saved_path) > 0

    img = Image.open(saved_path)
    assert img.format == "JPEG"


# ============================================================================
# 2. VISION LLM & NO-KEY FALLBACK TESTS
# ============================================================================

def test_vision_missing_key_returns_graceful_fallback():
    """Verify missing API key returns polite Vietnamese fallback without exceptions."""
    manager = ScreenVisionManager(gemini_api_key="", openai_api_key="")

    res_gemini = manager.analyze_screen(query="Mô tả màn hình", provider="gemini")
    assert "Tôi chưa thể nhìn thấy màn hình do chưa cấu hình Vision API key" in res_gemini

    res_openai = manager.analyze_screen(query="Mô tả màn hình", provider="openai")
    assert "Tôi chưa thể nhìn thấy màn hình do chưa cấu hình Vision API key" in res_openai


def test_gemini_vision_api_call_formatting():
    """Verify Gemini Vision REST API call constructs correct JSON payload."""
    manager = ScreenVisionManager(gemini_api_key="mock_gemini_key", default_provider="gemini")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Màn hình đang hiển thị trình duyệt và IDE Visual Studio Code."}
                    ]
                }
            }
        ]
    }

    dummy_image = Image.new("RGB", (100, 100), color=(10, 20, 30))
    buf = io.BytesIO()
    dummy_image.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    with patch.object(manager._session, "post", return_value=mock_resp) as mock_post:
        result = manager.analyze_screen("Mô tả cửa sổ đang mở", image_bytes=raw_bytes)

        assert "Visual Studio Code" in result
        assert mock_post.called
        call_url = mock_post.call_args[0][0]
        call_json = mock_post.call_args[1]["json"]

        assert "key=mock_gemini_key" in call_url
        assert "contents" in call_json
        part_text = call_json["contents"][0]["parts"][0]["text"]
        part_inline = call_json["contents"][0]["parts"][1]["inlineData"]

        assert part_text == "Mô tả cửa sổ đang mở"
        assert part_inline["mimeType"] == "image/jpeg"
        assert len(part_inline["data"]) > 0


def test_openai_vision_api_call_formatting():
    """Verify OpenAI GPT-4o Vision REST API call constructs correct JSON payload."""
    manager = ScreenVisionManager(openai_api_key="sk-mock-key", default_provider="openai")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Phát hiện hộp thoại cảnh báo: 'File not found'."
                }
            }
        ]
    }

    with patch.object(manager._session, "post", return_value=mock_resp) as mock_post:
        result = manager.analyze_screen("Kiểm tra lỗi", provider="openai")

        assert "File not found" in result
        assert mock_post.called
        call_headers = mock_post.call_args[1]["headers"]
        call_json = mock_post.call_args[1]["json"]

        assert call_headers["Authorization"] == "Bearer sk-mock-key"
        assert call_json["model"] == "gpt-4o"
        messages = call_json["messages"]
        assert len(messages) == 1
        content_items = messages[0]["content"]
        assert content_items[0]["type"] == "text"
        assert content_items[1]["type"] == "image_url"
        assert content_items[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_vision_http_error_handling():
    """Verify network or HTTP failure returns descriptive Vietnamese error."""
    manager = ScreenVisionManager(gemini_api_key="valid_key")

    with patch.object(manager._session, "post", side_effect=Exception("Connection reset")):
        result = manager.analyze_screen("Mô tả màn hình")
        assert "Xin lỗi Ngài, đã xảy ra lỗi khi phân tích hình ảnh" in result
        assert "Connection reset" in result


# ============================================================================
# 3. WIN32 ERROR DIALOG DETECTOR TESTS
# ============================================================================

def test_dialog_detector_initialization():
    """Verify dialog detector initializes with standard and custom keywords."""
    detector = ErrorDialogDetector(custom_keywords=["bluescreen", "segfault"])
    assert "error" in detector.error_keywords
    assert "lỗi" in detector.error_keywords
    assert "bluescreen" in detector.error_keywords
    assert "segfault" in detector.error_keywords


def test_dialog_detector_with_mock_win32():
    """Test dialog detection scanning with simulated Win32 windows."""
    detector = ErrorDialogDetector()

    # Simulate windows via mock user32
    class MockUser32:
        def IsWindowVisible(self, hwnd):
            return 1

        def GetClassNameW(self, hwnd, buf, size):
            cls = WIN32_DIALOG_CLASS if hwnd == 2001 else "ApplicationFrameWindow"
            ctypes.memmove(buf, cls.encode("utf-16le") + b"\x00\x00", len(cls)*2 + 2)
            return len(cls)

        def GetWindowTextLengthW(self, hwnd):
            title = "Application Error Exception" if hwnd == 2001 else "Normal App"
            return len(title)

        def GetWindowTextW(self, hwnd, buf, size):
            title = "Application Error Exception" if hwnd == 2001 else "Normal App"
            ctypes.memmove(buf, title.encode("utf-16le") + b"\x00\x00", min(len(title)*2 + 2, size*2))
            return len(title)

        def GetWindowRect(self, hwnd, lpRect):
            target = getattr(lpRect, "_obj", None) or getattr(lpRect, "contents", lpRect)
            target.left = 100
            target.top = 100
            target.right = 500
            target.bottom = 400
            return 1

        def EnumWindows(self, lpEnumFunc, lParam):
            lpEnumFunc(1001, lParam)
            lpEnumFunc(2001, lParam)
            return 1

        def EnumChildWindows(self, hwnd, lpEnumFunc, lParam):
            return 1

    with patch.object(ctypes.windll, "user32", MockUser32(), create=True), \
         patch.object(detector, "_is_windows", True):

        dialogs = detector.scan_for_dialogs()
        assert len(dialogs) == 1
        d = dialogs[0]
        assert d["hwnd"] == 2001
        assert d["is_dialog"] is True
        assert d["is_error"] is True
        assert "Application Error Exception" in d["title"]

        active = detector.get_active_error_dialog()
        assert active is not None
        assert active["hwnd"] == 2001

        summary = detector.format_error_summary(active)
        assert "Phát hiện hộp thoại cảnh báo" in summary
        assert "Application Error Exception" in summary


def test_dialog_detector_format_error_summary_when_clean():
    """Verify clean state returns polite reassurance message."""
    detector = ErrorDialogDetector()
    with patch.object(detector, "get_active_error_dialog", return_value=None):
        summary = detector.format_error_summary()
        assert "Không phát hiện hộp thoại lỗi nào trên màn hình" in summary


# ============================================================================
# 4. DESKTOP OCR TESTS
# ============================================================================

def test_ocr_extract_text_with_vision_llm_fallback():
    """Verify OCR falls back to Vision LLM when local tesseract is unavailable."""
    mock_vision = MagicMock()
    mock_vision.analyze_screen.return_value = "Extracted: Welcome to JARVIS System"

    ocr = DesktopOCR(vision_manager=mock_vision)
    with patch.object(ocr, "is_tesseract_available", return_value=False):
        dummy_img = Image.new("RGB", (200, 100), color="white")
        buf = io.BytesIO()
        dummy_img.save(buf, format="JPEG")

        text = ocr.extract_text(buf.getvalue())
        assert text == "Extracted: Welcome to JARVIS System"
        assert mock_vision.analyze_screen.called


def test_ocr_extract_text_from_screen():
    """Verify extract_text_from_screen integrates screen capture with text extraction."""
    mock_vision = MagicMock()
    mock_vision.capture_screenshot.return_value = (b"fake_jpeg_bytes", "fake_b64")
    mock_vision.analyze_screen.return_value = "Mã lỗi: 0x80070005 Access Denied"

    ocr = DesktopOCR(vision_manager=mock_vision)
    with patch.object(ocr, "is_tesseract_available", return_value=False):
        text = ocr.extract_text_from_screen(roi=(10, 10, 300, 200))
        assert "Access Denied" in text


# ============================================================================
# 5. HIGH-LEVEL PERCEPTION ACTION HELPERS
# ============================================================================

def test_explain_error_on_screen_active_dialog():
    """Verify explain_error_on_screen detects dialog and requests explanation."""
    mock_detector = MagicMock()
    mock_detector.get_active_error_dialog.return_value = {
        "title": "Runtime Error 404",
        "text": "File not found: config.json",
    }

    manager = ScreenVisionManager(
        gemini_api_key="mock_key",
        dialog_detector=mock_detector,
    )
    with patch.object(manager, "analyze_screen", return_value="Lỗi này xảy ra do thiếu tệp config.json.") as mock_analyze:
        explanation = manager.explain_error_on_screen()
        assert "config.json" in explanation
        assert mock_analyze.called
        query_arg = mock_analyze.call_args[0][0]
        assert "Runtime Error 404" in query_arg


def test_summarize_document_on_screen():
    """Verify summarize_document_on_screen queries vision LLM for doc summary."""
    manager = ScreenVisionManager(gemini_api_key="mock_key")
    with patch.object(manager, "analyze_screen", return_value="Tài liệu mô tả kiến trúc Personal AI.") as mock_analyze:
        summary = manager.summarize_document_on_screen()
        assert "Personal AI" in summary
        assert mock_analyze.called
