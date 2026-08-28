"""
Unit tests for structured rotating logger, ANSI color formatting, and domain adapters.
"""
from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from jarvis.core.logger import (
    ColoredConsoleFormatter,
    JarvisLoggerAdapter,
    LogColors,
    StructuredFileFormatter,
    get_logger,
    setup_logging,
    shutdown_logging,
)


class TestLogger(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        shutdown_logging()
        self.temp_dir.cleanup()

    def test_logger_setup_and_file_creation(self) -> None:
        """Verify setup_logging creates the log directory and writes UTF-8 logs."""
        setup_logging(
            level="DEBUG",
            log_dir=self.log_dir,
            log_file_name="test_jarvis.log",
            force_reinit=True,
        )

        logger = logging.getLogger("test_module")
        logger.info("Hello logging world")

        log_file = self.log_dir / "test_jarvis.log"
        self.assertTrue(log_file.exists())
        content = log_file.read_text(encoding="utf-8")
        self.assertIn("Hello logging world", content)
        self.assertIn("[test_module]", content)

    def test_logger_file_rotation(self) -> None:
        """Verify log rotation occurs when file size exceeds max_bytes."""
        setup_logging(
            level="DEBUG",
            log_dir=self.log_dir,
            log_file_name="rotating.log",
            max_bytes=500,
            backup_count=2,
            force_reinit=True,
        )

        logger = logging.getLogger("rotation_test")
        for i in range(50):
            logger.info("A" * 50 + f" message {i}")

        log_file = self.log_dir / "rotating.log"
        rotated_file = self.log_dir / "rotating.log.1"

        self.assertTrue(log_file.exists())
        self.assertTrue(rotated_file.exists())

    def test_colored_console_formatter(self) -> None:
        """Verify ANSI color codes are applied per log level."""
        formatter = ColoredConsoleFormatter()

        record_info = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Info message", args=(), exc_info=None
        )
        record_error = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="Error message", args=(), exc_info=None
        )

        formatted_info = formatter.format(record_info)
        formatted_error = formatter.format(record_error)

        self.assertIn(LogColors.INFO, formatted_info)
        self.assertIn(LogColors.ERROR, formatted_error)
        self.assertIn(LogColors.RESET, formatted_info)

    def test_structured_file_formatter(self) -> None:
        """Verify structured format includes timestamp, TID, and module."""
        formatter = StructuredFileFormatter()
        record = logging.LogRecord(
            name="jarvis.core.test", level=logging.INFO, pathname="", lineno=0,
            msg="Structured event message", args=(), exc_info=None
        )
        formatted = formatter.format(record)

        self.assertIn("[INFO ]", formatted)
        self.assertIn("[TID:", formatted)
        self.assertIn("[jarvis.core.test]", formatted)
        self.assertIn("Structured event message", formatted)

    def test_jarvis_logger_adapter(self) -> None:
        """Verify log_trigger and log_action helper methods."""
        setup_logging(
            level="DEBUG",
            log_dir=self.log_dir,
            log_file_name="adapter.log",
            force_reinit=True,
        )

        adapter = get_logger("domain.test")
        adapter.log_trigger("DOUBLE_CLAP", {"confidence": 0.95, "gap_ms": 150})
        adapter.log_action("spotify_play", "SUCCESS", duration_ms=45.2)
        adapter.log_action("cursor_focus", "FAILED", duration_ms=12.0, error="Window not found")

        content = (self.log_dir / "adapter.log").read_text(encoding="utf-8")
        self.assertIn("[TRIGGER:DOUBLE_CLAP]", content)
        self.assertIn("[ACTION:spotify_play] [RESULT:SUCCESS] [TIME:45.2ms]", content)
        self.assertIn("[ACTION:cursor_focus] [RESULT:FAILED] [TIME:12.0ms] Error: Window not found", content)

    def test_log_interaction_format_and_persistence(self) -> None:
        """Verify structured [INTERACTION] log formatting and persistence to custom file."""
        from jarvis.core.logger import log_interaction

        custom_log_file = self.log_dir / "custom_interaction.log"
        line = log_interaction(
            trigger="VOICE",
            input_text="bật đèn phòng khách",
            action="home_assistant_call",
            response="Đã bật đèn phòng khách.",
            status="success",
            log_file=custom_log_file,
        )

        self.assertTrue(line.startswith("[INTERACTION]"))
        self.assertIn("| TRIGGER: VOICE", line)
        self.assertIn("| INPUT: bật đèn phòng khách", line)
        self.assertIn("| ACTION: home_assistant_call", line)
        self.assertIn("| RESPONSE: Đã bật đèn phòng khách.", line)
        self.assertIn("| STATUS: success", line)

        self.assertTrue(custom_log_file.exists())
        file_content = custom_log_file.read_text(encoding="utf-8")
        self.assertIn(line, file_content)


if __name__ == "__main__":
    unittest.main()
