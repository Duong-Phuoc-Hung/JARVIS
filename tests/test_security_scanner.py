"""
tests/test_security_scanner.py
==============================
Comprehensive Test Suite for Network Scanner, Packet Capture, and Security Risk Reporting.
Covering:
  - F-23: Network Scanner Wrapper (Nmap discovery and XML/stdout parser)
  - F-24: Packet Capture Wrapper (TShark live packet capture)
  - F-25: Security Risk Report Generator (Markdown risk report & vocal summary)
  - R12 / F-34: Biometric Privilege Gate Enforcement
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from jarvis.core.models import PrivilegeLevel, RequesterContext
from jarvis.security.report import SecurityPrivilegeGate, SecurityReportGenerator
from jarvis.security.scanner import (
    HostScanResult,
    NetworkScanner,
    NmapScannerWrapper,
    PacketCapture,
    PacketCaptureResult,
    ScanReport,
    TSharkCaptureWrapper,
    Vulnerability,
    VulnerabilitySeverity,
)

# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_security_nmap_subnet_scan_wrapper_tier1(monkeypatch):
    """
    [F-23] Validate Nmap wrapper executes subnet discovery and returns HostScanResult objects.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    wrapper = NmapScannerWrapper()
    scan = wrapper.scan_subnet("192.168.1.0/24")

    assert scan.status == "SUCCESS"
    assert scan.total_hosts >= 2
    assert scan.hosts[0].ip == "192.168.1.1"
    assert 80 in scan.hosts[0].open_ports


def test_security_tshark_packet_capture_wrapper_tier1(monkeypatch):
    """
    [F-24] Validate TShark wrapper executes capture and extracts packet protocol breakdown.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Wireshark\\tshark.exe")
    wrapper = TSharkCaptureWrapper()
    capture = wrapper.capture_packets(interface="eth0", count=100)

    assert capture["packet_count"] == 100
    assert capture["protocols"]["TCP"] == 70
    assert capture["protocols"]["UDP"] == 20
    assert capture["status"] == "SUCCESS"


def test_security_risk_report_markdown_and_voice_summary_tier1(tmp_path, monkeypatch):
    """
    [F-25] Validate security report generator compiles scan findings into Markdown file and spoken summary.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: "nmap.exe")
    nmap = NmapScannerWrapper()
    scan = nmap.scan_subnet("192.168.1.0/24")

    generator = SecurityReportGenerator()
    result = generator.generate_report(scan, output_dir=tmp_path)

    report_path = result["report_path"]
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "192.168.1.1" in content
    assert "router.lan" in content

    voice_summary = result["voice_summary"]
    assert "hoàn thành" in voice_summary.lower()
    assert "phát hiện" in voice_summary.lower()


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_security_nmap_binary_not_installed_error_tier2(monkeypatch):
    """
    [F-23] Validate missing nmap executable returns TOOL_NOT_FOUND diagnostic state cleanly.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    wrapper = NmapScannerWrapper()
    scan = wrapper.scan_subnet("10.0.0.0/24")

    assert scan.status == "TOOL_NOT_FOUND"
    assert scan.total_hosts == 0


def test_security_tshark_binary_not_installed_error_tier2(monkeypatch):
    """
    [F-24] Validate missing tshark executable returns TOOL_NOT_FOUND without raising unhandled exceptions.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    wrapper = TSharkCaptureWrapper()
    capture = wrapper.capture_packets(interface="eth0", count=50)

    assert capture.status == "TOOL_NOT_FOUND" or capture["status"] == "TOOL_NOT_FOUND"
    assert capture.packet_count == 0 or capture["packet_count"] == 0


def test_security_biometric_privilege_gating_unauthenticated_tier2():
    """
    [R12, F-34] Validate unauthenticated requester context is rejected by SecurityPrivilegeGate.
    """
    unauth_ctx = RequesterContext(
        requester_id="stranger_user",
        granted_privilege=PrivilegeLevel.NORMAL,
        is_authenticated=False,
    )

    # 1. Gate verification check
    assert SecurityPrivilegeGate.verify_privilege(unauth_ctx, "security_scan") is False

    # 2. Gate enforcement raises PermissionError
    with pytest.raises(PermissionError) as exc_info:
        SecurityPrivilegeGate.enforce(unauth_ctx, "security_scan")
    assert "Biometric authentication required" in str(exc_info.value)

    # 3. Scanner rejects unauthenticated context
    scanner = NetworkScanner()
    scan = scanner.scan_subnet("192.168.1.0/24", context=unauth_ctx)
    assert scan.status == "PERMISSION_DENIED"


def test_security_biometric_privilege_gating_authenticated_tier2(monkeypatch):
    """
    [R12, F-34] Validate biometrically authenticated admin requester context is permitted to execute scan.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: "nmap.exe")

    auth_ctx = RequesterContext(
        requester_id="owner_user",
        granted_privilege=PrivilegeLevel.ADMIN,
        is_authenticated=True,
    )

    assert SecurityPrivilegeGate.verify_privilege(auth_ctx, "security_scan") is True

    scanner = NetworkScanner()
    scan = scanner.scan_subnet("192.168.1.0/24", context=auth_ctx)
    assert scan.status == "SUCCESS"
    assert scan.total_hosts >= 2


def test_security_vulnerability_risk_report_with_packet_capture_tier2(tmp_path):
    """
    [F-25] Validate Markdown report generation combining vulnerability findings and packet telemetry.
    """
    generator = SecurityReportGenerator()

    # Create scan with vulnerabilities
    vuln = Vulnerability(
        id="CVE-2023-9999",
        title="Remote Code Execution",
        severity=VulnerabilitySeverity.CRITICAL,
        description="Critical buffer overflow in daemon service.",
        port=8080,
    )
    host = HostScanResult(
        ip="192.168.1.100",
        hostname="vulnerable_server.lan",
        status="UP",
        open_ports=[8080],
        services={8080: "http-alt"},
        vulnerabilities=[vuln],
    )
    scan = ScanReport(
        target="192.168.1.100/32",
        hosts=[host],
        total_hosts=1,
        duration_s=2.5,
        status="SUCCESS",
    )

    capture = PacketCaptureResult(
        interface="Ethernet0",
        packet_count=200,
        duration_s=5.0,
        protocols={"TCP": 140, "UDP": 40, "ICMP": 20},
        anomalies_detected=0,
    )

    res = generator.generate_report(scan, output_dir=tmp_path, capture=capture, lang="vi")
    report_file = res["report_path"]
    assert report_file.exists()

    md = report_file.read_text(encoding="utf-8")
    assert "CRITICAL RISK" in md
    assert "Network Packet Telemetry" in md
    assert "192.168.1.100" in md

    # English voice summary
    voice_en = generator.get_voice_summary(scan, lang="en")
    assert "security alert" in voice_en.lower()
    assert "vulnerabilities" in voice_en.lower()
