"""
tests/unit/test_packet_capture_truthfulness.py
================================================
D-03: PacketCapture Truthfulness Regression Tests

Validates:
  - TOOL_NOT_FOUND returned when TShark binary is missing (never SUCCESS)
  - PERMISSION_DENIED returned for unauthenticated context
  - NO_TSHARK_OUTPUT returned on subprocess exception/timeout
  - packet_count derived only from real parsed data -- never fabricated
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from jarvis.security.scanner import (
    PacketCapture,
    RequesterContext,
    _parse_tshark_protocols,
)


class TestParseTsharkProtocols:
    def test_empty_stdout_returns_empty_dict(self):
        assert _parse_tshark_protocols("") == {}

    def test_whitespace_only_returns_empty_dict(self):
        assert _parse_tshark_protocols("   \n\n  ") == {}

    def test_format1_colon_chain_parses_tcp(self):
        stdout = "eth:ethertype:ip:tcp\neth:ethertype:ip:tcp\neth:ethertype:ip:udp\n"
        result = _parse_tshark_protocols(stdout)
        assert result.get("TCP") == 2
        assert result.get("UDP") == 1

    def test_format2_pipe_table_parses_counts(self):
        stdout = "| tcp | 42 | 12345 |\n| udp | 7 | 890 |\n| icmp | 3 | 456 |\n"
        result = _parse_tshark_protocols(stdout)
        assert result.get("TCP") == 42
        assert result.get("UDP") == 7
        assert result.get("ICMP") == 3

    def test_format3_frames_count_syntax(self):
        stdout = "  tcp  frames:15 bytes:9000\n  udp  frames:3 bytes:400\n"
        result = _parse_tshark_protocols(stdout)
        assert result.get("TCP") == 15
        assert result.get("UDP") == 3

    def test_unknown_protocols_ignored(self):
        stdout = "eth:ethertype:ip:somefakeprotocol\n"
        result = _parse_tshark_protocols(stdout)
        assert "SOMEFAKEPROTOCOL" not in result

    def test_malformed_line_does_not_crash(self):
        stdout = "|||broken||line|||\n:\n"
        result = _parse_tshark_protocols(stdout)
        assert isinstance(result, dict)


class TestPacketCaptureTruthfulness:
    def test_tool_not_found_when_no_tshark_binary(self):
        pc = PacketCapture(tshark_path=None)
        with patch("jarvis.security.scanner.resolve_tshark_binary", return_value=None):
            result = pc.capture_packets(interface="eth0", count=10)
        assert result.status == "TOOL_NOT_FOUND"
        assert result.packet_count == 0
        assert result.protocols == {}

    def test_permission_denied_for_unauthenticated_context(self):
        pc = PacketCapture()
        ctx = RequesterContext(requester_id="user1", is_authenticated=False)
        result = pc.capture_packets(interface="eth0", count=10, context=ctx)
        assert result.status == "PERMISSION_DENIED"
        assert result.packet_count == 0

    def test_no_tshark_output_on_subprocess_exception(self):
        pc = PacketCapture()
        with patch("jarvis.security.scanner.resolve_tshark_binary", return_value="/usr/bin/tshark"), \
             patch("subprocess.run", side_effect=OSError("tshark exec failed")):
            result = pc.capture_packets(interface="eth0", count=10)
        assert result.status == "NO_TSHARK_OUTPUT"
        assert result.packet_count == 0
        assert result.protocols == {}

    def test_no_tshark_output_on_timeout(self):
        pc = PacketCapture()
        with patch("jarvis.security.scanner.resolve_tshark_binary", return_value="/usr/bin/tshark"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="tshark", timeout=15)):
            result = pc.capture_packets(interface="eth0", count=10)
        assert result.status == "NO_TSHARK_OUTPUT"
        assert result.packet_count == 0

    def test_no_protocols_parsed_on_empty_stdout(self):
        pc = PacketCapture()
        mock_proc = MagicMock()
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        mock_proc.returncode = 0
        with patch("jarvis.security.scanner.resolve_tshark_binary", return_value="/usr/bin/tshark"), \
             patch("subprocess.run", return_value=mock_proc):
            result = pc.capture_packets(interface="eth0", count=10)
        assert result.packet_count == 0
        assert result.protocols == {}
        assert result.status in ("NO_TSHARK_OUTPUT", "NO_PROTOCOLS_PARSED")

    def test_success_with_real_parseable_output(self):
        pc = PacketCapture()
        mock_proc = MagicMock()
        mock_proc.stdout = "eth:ethertype:ip:tcp\neth:ethertype:ip:tcp\neth:ethertype:ip:udp\n"
        mock_proc.stderr = ""
        mock_proc.returncode = 0
        with patch("jarvis.security.scanner.resolve_tshark_binary", return_value="/usr/bin/tshark"), \
             patch("subprocess.run", return_value=mock_proc):
            result = pc.capture_packets(interface="eth0", count=50)
        assert result.status == "SUCCESS"
        assert result.packet_count > 0
        assert "TCP" in result.protocols
        assert result.packet_count == sum(result.protocols.values())

    def test_packet_count_never_fabricated(self):
        pc = PacketCapture()
        with patch("jarvis.security.scanner.resolve_tshark_binary", return_value=None):
            result = pc.capture_packets(interface="eth0", count=50)
        assert result.packet_count == 0
        assert result.packet_count != 50

    def test_authenticated_system_context_allowed(self):
        pc = PacketCapture()
        ctx = RequesterContext(requester_id="system", is_authenticated=True)
        with patch("jarvis.security.scanner.resolve_tshark_binary", return_value=None):
            result = pc.capture_packets(interface="eth0", count=10, context=ctx)
        assert result.status == "TOOL_NOT_FOUND"
        assert result.status != "PERMISSION_DENIED"

    def test_build_capture_result_with_none_raw_stdout(self):
        pc = PacketCapture()
        result = pc._build_capture_result("eth0", 100, 10.0, None, None)
        assert result.packet_count == 0
        assert result.protocols == {}
        assert result.status == "NO_TSHARK_OUTPUT"

    def test_build_capture_result_with_real_stdout_succeeds(self):
        pc = PacketCapture()
        real_stdout = "  tcp  frames:25 bytes:15000\n  udp  frames:5 bytes:2000\n"
        result = pc._build_capture_result("eth0", 100, 10.0, None, real_stdout)
        assert result.status == "SUCCESS"
        assert result.packet_count == 30
        assert result.protocols["TCP"] == 25
        assert result.protocols["UDP"] == 5
