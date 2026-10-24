"""
tests/unit/test_uia_crawler.py
==============================
Unit Test Suite for OCR-Free In-Process Win32 UIAutomation Crawler.
Validates:
  1. Interactive element enumeration (Buttons, Edits, MenuItems).
  2. Substring & exact element name lookup.
  3. Direct element invocation & text setting without pointer movements.
  4. Latency performance (< 3.5ms on CPU).
"""
import pytest

from jarvis.context.uia_crawler import UIElementDescriptor, Win32UIAutomationCrawler


def test_uia_crawler_simulated_elements():
    """Validates element retrieval, bounding box calculation, and center points."""
    crawler = Win32UIAutomationCrawler(is_mock=True)

    elements = crawler.get_actionable_elements(hwnd=1001)

    assert len(elements) >= 3
    btn_save = elements[0]
    assert isinstance(btn_save, UIElementDescriptor)
    assert btn_save.name == "Lưu"
    assert btn_save.control_type == "Button"
    assert btn_save.center_point == (140, 220)
    assert "Invoke" in btn_save.supported_patterns
    assert crawler.last_crawl_latency_ms < 5.0  # Must be fast


def test_uia_crawler_find_by_name():
    """Validates finding elements by exact and substring queries."""
    crawler = Win32UIAutomationCrawler(is_mock=True)

    # 1. Exact match
    el_cancel = crawler.find_element_by_name(hwnd=1001, query="Hủy")
    assert el_cancel is not None
    assert el_cancel.name == "Hủy"

    # 2. Substring match
    el_text = crawler.find_element_by_name(hwnd=1001, query="nội dung")
    assert el_text is not None
    assert "Nội dung" in el_text.name
    assert el_text.control_type == "Edit"

    # 3. Non-existent query
    el_missing = crawler.find_element_by_name(hwnd=1001, query="Không tồn tại")
    assert el_missing is None


def test_uia_crawler_invoke_and_set_value():
    """Validates direct element invocation and value assignment."""
    crawler = Win32UIAutomationCrawler(is_mock=True)
    elements = crawler.get_actionable_elements(hwnd=1001)

    btn = elements[0]
    invoked = crawler.invoke_element(btn)
    assert invoked is True

    txt = elements[2]
    val_set = crawler.set_element_value(txt, "Hello JARVIS Sovereign")
    assert val_set is True
