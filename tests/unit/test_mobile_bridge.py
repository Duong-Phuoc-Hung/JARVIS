"""
tests/unit/test_mobile_bridge.py
==================================
Unit tests for MobileFileBridge — file validation, transfer, clipboard.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.comms.mobile_bridge import _ALLOWED_EXTENSIONS, MobileFileBridge


@pytest.fixture
def bridge(tmp_path):
    return MobileFileBridge(
        save_directory=str(tmp_path / "downloads"),
        max_file_size_mb=10,
    )


class TestReceiveFile:
    def test_valid_file_saved_to_directory(self, bridge, tmp_path):
        content = b"Hello JARVIS file content"
        result = bridge.receive_file(content, "test_doc.txt")
        assert result["success"] is True
        assert Path(result["saved_path"]).exists()

    def test_saved_file_content_intact(self, bridge):
        data = b"Test content 123"
        result = bridge.receive_file(data, "notes.txt")
        saved = Path(result["saved_path"]).read_bytes()
        assert saved == data

    def test_file_size_reported_in_kb(self, bridge):
        data = b"x" * 2048
        result = bridge.receive_file(data, "data.txt")
        assert result["success"] is True
        assert result["size_kb"] == 2

    def test_oversized_file_rejected(self, tmp_path):
        small_bridge = MobileFileBridge(
            save_directory=str(tmp_path / "dl"),
            max_file_size_mb=1,
        )
        # 2MB file → exceeds 1MB limit
        big_data = b"x" * (2 * 1024 * 1024)
        result = small_bridge.receive_file(big_data, "big.pdf")
        assert result["success"] is False
        assert "lớn" in result["error"].lower() or "size" in result["error"].lower()

    def test_disallowed_extension_rejected(self, bridge):
        result = bridge.receive_file(b"exec content", "malware.exe")
        assert result["success"] is False

    def test_allowed_extension_accepted(self, bridge):
        result = bridge.receive_file(b"# markdown", "readme.md")
        assert result["success"] is True

    def test_image_extension_accepted(self, bridge):
        # PNG magic bytes
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = bridge.receive_file(fake_png, "screenshot.png")
        assert result["success"] is True


class TestTransferHistory:
    def test_history_initially_empty(self, bridge):
        history = bridge.get_file_transfer_history()
        assert isinstance(history, list)

    def test_receive_creates_history_entry(self, bridge):
        bridge.receive_file(b"data", "file.txt")
        history = bridge.get_file_transfer_history()
        assert len(history) >= 1
        assert any(h["type"] == "receive" for h in history)

    def test_history_entry_has_timestamp(self, bridge):
        bridge.receive_file(b"data", "log.txt")
        history = bridge.get_file_transfer_history()
        entry = history[0]
        assert "timestamp" in entry


class TestValidation:
    def test_validate_rejects_bat_extension(self, bridge):
        error = bridge._validate_file("script.bat", 100)
        assert error is not None

    def test_validate_accepts_pdf(self, bridge):
        error = bridge._validate_file("doc.pdf", 100)
        assert error is None

    def test_validate_rejects_oversized(self, tmp_path):
        small = MobileFileBridge(save_directory=str(tmp_path), max_file_size_mb=1)
        error = small._validate_file("big.txt", 2 * 1024 * 1024)
        assert error is not None
