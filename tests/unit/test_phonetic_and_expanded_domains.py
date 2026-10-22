"""
tests/unit/test_phonetic_and_expanded_domains.py
================================================
Unit tests for Vietnamese Acoustic & Phonetic STT Normalizer and
Expanded 15-Domain Intent Classification & Slot Extraction.
"""
from __future__ import annotations

import pytest

from jarvis.nlp.phonetic_normalizer import (
    VietnamesePhoneticNormalizer,
    normalize_phonetic_stt,
)
from jarvis.llm.local_classifier import extract_slots_for_intent


def test_phonetic_normalizer_loan_words():
    # Common Vietnamese phonetic representations from Whisper
    assert normalize_phonetic_stt("mở cờ rôm lên") == "mở chrome lên"
    assert normalize_phonetic_stt("bật ét xel để làm việc") == "bật excel để làm việc"
    assert normalize_phonetic_stt("mở quốt soạn thảo") == "mở word soạn thảo"
    assert normalize_phonetic_stt("bật sì po ti phai nghe nhạc") == "bật spotify nghe nhạc"
    assert normalize_phonetic_stt("vào phây búc") == "vào facebook"
    assert normalize_phonetic_stt("mở vê ét cốt") == "mở vscode"
    assert normalize_phonetic_stt("kiểm tra wai phai") == "kiểm tra wifi"
    assert normalize_phonetic_stt("xóa cờ líp bo") == "xóa clipboard"


def test_slot_extraction_window_management():
    slots_snap_left = extract_slots_for_intent("window_management", "chia đôi màn hình sang trái")
    assert slots_snap_left.get("action") == "snap_left"

    slots_snap_right = extract_slots_for_intent("window_management", "chia màn hình sang phải")
    assert slots_snap_right.get("action") == "snap_right"

    slots_max = extract_slots_for_intent("window_management", "phóng to cửa sổ này")
    assert slots_max.get("action") == "maximize"

    slots_min = extract_slots_for_intent("window_management", "thu nhỏ tất cả cửa sổ")
    assert slots_min.get("action") == "minimize"


def test_slot_extraction_file_management():
    slots_dl = extract_slots_for_intent("file_management", "mở thư mục tải về")
    assert slots_dl.get("target") == "downloads"

    slots_trash = extract_slots_for_intent("file_management", "dọn dẹp thùng rác máy tính")
    assert slots_trash.get("target") == "recycle_bin"
    assert slots_trash.get("action") == "empty"

    slots_docs = extract_slots_for_intent("file_management", "mở thư mục tài liệu")
    assert slots_docs.get("target") == "documents"


def test_slot_extraction_clipboard():
    slots_copy = extract_slots_for_intent("clipboard_action", "sao chép đoạn văn bản này")
    assert slots_copy.get("action") == "copy"

    slots_paste = extract_slots_for_intent("clipboard_action", "dán nội dung vào đây")
    assert slots_paste.get("action") == "paste"

    slots_clear = extract_slots_for_intent("clipboard_action", "xóa bộ nhớ tạm clipboard")
    assert slots_clear.get("action") == "clear"


def test_slot_extraction_network():
    slots_wifi = extract_slots_for_intent("network_control", "kiểm tra kết nối mạng wifi")
    assert slots_wifi.get("query_type") in ("wifi_info", "status")

    slots_speed = extract_slots_for_intent("network_control", "đo tốc độ mạng internet")
    assert slots_speed.get("query_type") == "speed_test"

    slots_ip = extract_slots_for_intent("network_control", "địa chỉ ip của máy là gì")
    assert slots_ip.get("query_type") == "ip_address"


def test_slot_extraction_system_power():
    slots_lock = extract_slots_for_intent("system_power", "khóa màn hình máy tính")
    assert slots_lock.get("action") == "lock"

    slots_sleep = extract_slots_for_intent("system_power", "cho máy tính đi ngủ sleep")
    assert slots_sleep.get("action") == "sleep"

    slots_shutdown = extract_slots_for_intent("system_power", "hẹn giờ tắt máy tính sau 30 phút")
    assert slots_shutdown.get("action") == "shutdown_timer"
    assert slots_shutdown.get("delay_seconds") == 1800

    slots_cancel = extract_slots_for_intent("system_power", "hủy hẹn giờ tắt máy")
    assert slots_cancel.get("action") == "cancel_shutdown"
