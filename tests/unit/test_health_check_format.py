"""
tests/unit/test_health_check_format.py
======================================
Tests for JARVIS health-check CLI argument parsing, JSON formatted diagnostics,
and scripts/health_check_report module status verification.
"""
from __future__ import annotations

import io
import json
import sys
from unittest.mock import MagicMock, patch

import scripts.health_check_report as hcr

from jarvis.cli import build_parser, run_health_check
from jarvis.core.config import ConfigManager


class TestHealthCheckCLIArgs:
    """Validate CLI argument parsing for health-check commands."""

    def test_parser_accepts_format_json(self):
        parser = build_parser()
        args = parser.parse_args(["health-check", "--format", "json"])
        assert args.command == "health-check"
        assert args.format == "json"

    def test_parser_accepts_format_text(self):
        parser = build_parser()
        args = parser.parse_args(["health-check", "--format", "text"])
        assert args.command == "health-check"
        assert args.format == "text"

    def test_parser_default_format_is_text(self):
        parser = build_parser()
        args = parser.parse_args(["health-check"])
        assert args.command == "health-check"
        assert args.format == "text"

    def test_health_alias_accepts_format_json(self):
        parser = build_parser()
        args = parser.parse_args(["health", "--format", "json"])
        assert args.command == "health"
        assert args.format == "json"


class TestHealthCheckExecutionJSON:
    """Validate that run_health_check outputs structured JSON when requested."""

    def test_run_health_check_json_output(self, monkeypatch):
        # Mock subsystems to run quickly and deterministically
        captured_out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)

        cfg = MagicMock(spec=ConfigManager)
        cfg.to_dict.return_value = {"system": {"test": True}}
        cfg.get.return_value = {}

        # Run health check with json output format
        with patch("jarvis.cli._browser_health_line", return_value="[+] Browser Automation Agent: READY (Driver=mock)"):
            code = run_health_check(config=cfg, output_format="json")

        output = captured_out.getvalue()
        # Find JSON payload
        start = output.find("{")
        end = output.rfind("}")
        assert start != -1 and end != -1, f"No JSON found in output: {output}"
        data = json.loads(output[start : end + 1])

        assert "version" in data
        assert "subsystems" in data
        assert "failure_count" in data
        assert "status" in data
        assert isinstance(data["subsystems"], dict)
        assert len(data["subsystems"]) >= 15
        assert code in (0, 1, 2)


class TestHealthCheckReportScript:
    """Verify scripts/health_check_report functions."""

    def test_get_version_returns_valid_string(self):
        ver = hcr.get_version()
        assert ver != "unknown"
        assert len(ver.split(".")) >= 3

    def test_get_new_module_status_imports_all_core(self):
        results = hcr.get_new_module_status()
        assert len(results) >= 20
        # All modules in the updated list should be READY or OPTIONAL DEP
        for item in results:
            assert "✅" in item["status"] or "⚠️" in item["status"], f"Module failed: {item}"

    def test_build_markdown_report_structure(self):
        health_data = {
            "Subsys A": {"status": "ready", "message": "all good"},
            "Subsys B": {"status": "ready", "message": "operational"},
        }
        mod_status = [
            {"module": "jarvis.audio.vad", "display": "VAD Engine", "status": "✅ READY"}
        ]
        test_info = {"raw": "3753 tests collected"}
        md = hcr.build_markdown_report(
            health_data=health_data,
            module_status=mod_status,
            test_info=test_info,
            version="9.5.1",
            ts="2026-11-13 12:00:00",
        )
        assert "# 🤖 JARVIS Health Report" in md
        assert "3753 tests collected" in md
        assert "VAD Engine" in md
        assert "Subsys A" in md
