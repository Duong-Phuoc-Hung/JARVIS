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
from unittest.mock import MagicMock

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
    validate_scan_target,
)

# ============================================================================
# Deterministic realistic Nmap -oX XML fixtures (v4.5.2 scanner-scope-
# truthfulness hotfix). Tests must prove real XML parsing -- never rely on
# a nonexistent nmap.exe silently triggering fabricated fallback data.
# ============================================================================

REALISTIC_NMAP_XML_TWO_HOSTS = """<?xml version="1.0"?>
<nmaprun>
<host>
<status state="up"/>
<address addr="192.168.1.1" addrtype="ipv4"/>
<hostnames><hostname name="test-gateway.lan"/></hostnames>
<ports>
<port portid="80" protocol="tcp"><state state="open"/><service name="http"/></port>
<port portid="443" protocol="tcp"><state state="open"/><service name="https"/></port>
</ports>
</host>
<host>
<status state="up"/>
<address addr="192.168.1.15" addrtype="ipv4"/>
<hostnames><hostname name="test-desktop.lan"/></hostnames>
<ports>
<port portid="22" protocol="tcp"><state state="open"/><service name="ssh"/></port>
</ports>
</host>
</nmaprun>
"""

REALISTIC_NMAP_XML_ZERO_HOSTS = """<?xml version="1.0"?>
<nmaprun>
</nmaprun>
"""


def _fake_nmap_run(stdout: str, returncode: int = 0, stderr: str = ""):
    """Builds a fake `subprocess.run` replacement returning deterministic Nmap-shaped output."""
    def _runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    return _runner


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_security_nmap_subnet_scan_wrapper_tier1(monkeypatch):
    """
    [F-23] Validate Nmap wrapper executes subnet discovery and returns real
    HostScanResult objects parsed from actual (mocked) Nmap XML output.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    monkeypatch.setattr(subprocess, "run", _fake_nmap_run(REALISTIC_NMAP_XML_TWO_HOSTS))
    wrapper = NmapScannerWrapper()
    scan = wrapper.scan_subnet("192.168.1.0/24")

    assert scan.status == "SUCCESS"
    assert scan.total_hosts == 2
    assert scan.hosts[0].ip == "192.168.1.1"
    assert scan.hosts[0].hostname == "test-gateway.lan"
    assert 80 in scan.hosts[0].open_ports
    assert scan.hosts[0].services[80] == "http"
    assert scan.hosts[1].ip == "192.168.1.15"
    assert 22 in scan.hosts[1].open_ports


def test_security_tshark_packet_capture_wrapper_tier1(monkeypatch):
    """
    [F-24] Validate TShark wrapper executes capture and extracts packet protocol breakdown.

    Updated (2026-09-04): removed assertion for hardcoded 70/20/10 TCP/UDP/ICMP ratios
    which were fabricated. Now provides realistic tshark frame.protocols stdout so the
    real parser (_parse_tshark_protocols) can extract truthful counts.
    """
    # Simulate tshark -T fields -e frame.protocols output: 7 TCP, 2 UDP, 1 ICMP frames
    fake_stdout = "\n".join(
        ["eth:ethertype:ip:tcp"] * 7 +
        ["eth:ethertype:ip:udp"] * 2 +
        ["eth:ethertype:ip:icmp"] * 1
    )
    fake_proc = MagicMock()
    fake_proc.stdout = fake_stdout
    fake_proc.stderr = ""
    fake_proc.returncode = 0

    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Wireshark\\tshark.exe")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_proc)

    wrapper = TSharkCaptureWrapper()
    capture = wrapper.capture_packets(interface="eth0", count=10)

    assert capture["packet_count"] == 10
    assert capture["protocols"].get("TCP", 0) == 7
    assert capture["protocols"].get("UDP", 0) == 2
    assert capture["protocols"].get("ICMP", 0) == 1
    assert capture["status"] == "SUCCESS"



def test_security_risk_report_markdown_and_voice_summary_tier1(tmp_path, monkeypatch):
    """
    [F-25] Validate security report generator compiles scan findings into Markdown file and spoken summary.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: "nmap.exe")
    monkeypatch.setattr(subprocess, "run", _fake_nmap_run(REALISTIC_NMAP_XML_TWO_HOSTS))
    nmap = NmapScannerWrapper()
    scan = nmap.scan_subnet("192.168.1.0/24")

    generator = SecurityReportGenerator()
    result = generator.generate_report(scan, output_dir=tmp_path)

    report_path = result["report_path"]
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "192.168.1.1" in content
    assert "test-gateway.lan" in content

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
    monkeypatch.setattr(subprocess, "run", _fake_nmap_run(REALISTIC_NMAP_XML_TWO_HOSTS))

    auth_ctx = RequesterContext(
        requester_id="owner_user",
        granted_privilege=PrivilegeLevel.ADMIN,
        is_authenticated=True,
    )

    assert SecurityPrivilegeGate.verify_privilege(auth_ctx, "security_scan") is True

    scanner = NetworkScanner()
    scan = scanner.scan_subnet("192.168.1.0/24", context=auth_ctx)
    assert scan.status == "SUCCESS"
    assert scan.total_hosts == 2


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


# ============================================================================
# TARGET SCOPE VALIDATION (v4.5.2 scanner-scope-truthfulness hotfix)
# Policy: 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 only.
# ============================================================================

@pytest.mark.parametrize("target", [
    "127.0.0.1",                # A: allowed 127/8 host
    "127.0.0.1/32",              # B: allowed 127/8 CIDR
    "10.1.2.3",                  # A: allowed 10/8 host
    "10.20.0.0/16",              # B: allowed 10/8 CIDR
    "172.16.5.0/24",             # B: allowed 172.16/12 lower example
    "172.31.255.0/24",           # B: allowed 172.16/12 upper example
    "192.168.1.50",              # A: allowed 192.168/16 host
    "192.168.1.0/24",            # B: allowed 192.168/16 CIDR
])
def test_validate_scan_target_accepts_allowed_ranges(target):
    is_allowed, reason = validate_scan_target(target)
    assert is_allowed is True
    assert reason == ""


@pytest.mark.parametrize("target", [
    "8.8.8.8",                   # C: reject public host
    "1.1.1.0/24",                 # C: reject public CIDR
    "172.32.0.0/16",              # C: reject just-outside-172.16/12
    "172.15.255.255",             # C: reject just-below-172.16/12
    "192.169.0.0/16",             # C: reject just-outside-192.168/16
    "172.16.0.0/11",              # D: CIDR extends outside the /12 supernet
])
def test_validate_scan_target_rejects_public_or_out_of_scope_targets(target):
    is_allowed, reason = validate_scan_target(target)
    assert is_allowed is False
    assert reason  # truthful, non-empty explanation


@pytest.mark.parametrize("target", ["example.com", "localhost", "router.lan"])
def test_validate_scan_target_rejects_hostnames(target):
    """[F] Hostnames/DNS names are always rejected -- never resolved then scanned."""
    is_allowed, reason = validate_scan_target(target)
    assert is_allowed is False
    assert reason


@pytest.mark.parametrize("target", ["::1", "fe80::1", "2001:db8::/32"])
def test_validate_scan_target_rejects_ipv6(target):
    """[E] IPv6 targets are rejected for this implementation."""
    is_allowed, reason = validate_scan_target(target)
    assert is_allowed is False
    assert "IPv6" in reason


@pytest.mark.parametrize("target", [
    "",
    "   ",
    "not an ip",
    "192.168.1.1; cat /etc/passwd && whoami",
    "300.300.300.300",
    "192.168.1.0/99",
])
def test_validate_scan_target_rejects_malformed(target):
    """[G] Malformed targets are rejected, fail-closed."""
    is_allowed, reason = validate_scan_target(target)
    assert is_allowed is False
    assert reason


def test_scan_subnet_rejects_forbidden_target_without_touching_nmap(monkeypatch):
    """
    A forbidden target must never reach resolve_nmap_binary() or
    subprocess.run() -- validation happens strictly first.
    """
    def _fail_which(cmd):
        raise AssertionError("shutil.which must not be called for a rejected target")

    def _fail_run(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called for a rejected target")

    monkeypatch.setattr(shutil, "which", _fail_which)
    monkeypatch.setattr(subprocess, "run", _fail_run)

    scanner = NetworkScanner()
    report = scanner.scan_subnet("8.8.8.8")

    assert report.status == "TARGET_REJECTED"
    assert report.total_hosts == 0
    assert report.hosts == []
    assert report.error_message


def test_scan_subnet_rejects_malformed_target_without_touching_nmap(monkeypatch):
    """A malformed target must also never reach Nmap resolution/execution."""
    def _fail_which(cmd):
        raise AssertionError("shutil.which must not be called for a malformed target")

    monkeypatch.setattr(shutil, "which", _fail_which)

    scanner = NetworkScanner()
    report = scanner.scan_subnet("not-a-valid-target; whoami")

    assert report.status == "TARGET_REJECTED"
    assert report.total_hosts == 0
    assert report.hosts == []


# ============================================================================
# TRUTHFUL NMAP EXECUTION -- no fabricated hosts on any failure path
# ============================================================================

def test_scan_subnet_valid_zero_host_xml_is_truthful_success(monkeypatch):
    """A genuine, well-formed, zero-host Nmap result is a valid SUCCESS, not fabricated data."""
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    monkeypatch.setattr(subprocess, "run", _fake_nmap_run(REALISTIC_NMAP_XML_ZERO_HOSTS))

    scanner = NetworkScanner()
    report = scanner.scan_subnet("192.168.1.0/24")

    assert report.status == "SUCCESS"
    assert report.total_hosts == 0
    assert report.hosts == []


def test_scan_subnet_nonzero_exit_no_output_is_truthful_error(monkeypatch):
    """Nmap returncode != 0 with no usable output must not fabricate hosts."""
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    monkeypatch.setattr(
        subprocess, "run",
        _fake_nmap_run("", returncode=1, stderr="requires root privileges for raw socket scan"),
    )

    scanner = NetworkScanner()
    report = scanner.scan_subnet("192.168.1.0/24")

    assert report.status != "SUCCESS"
    assert report.total_hosts == 0
    assert report.hosts == []
    assert report.error_message
    assert "router.lan" not in str(report.error_message)


def test_scan_subnet_nonzero_exit_with_valid_looking_xml_is_still_truthful_error(monkeypatch):
    """
    A nonzero Nmap exit code must NEVER become SUCCESS merely because stdout
    happens to contain parseable, otherwise-valid-looking Nmap XML -- the
    process's own exit status is the truthful signal, not the presence of
    parseable output.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    monkeypatch.setattr(
        subprocess, "run",
        _fake_nmap_run(REALISTIC_NMAP_XML_TWO_HOSTS, returncode=1, stderr="partial results before failure"),
    )

    scanner = NetworkScanner()
    report = scanner.scan_subnet("192.168.1.0/24")

    assert report.status != "SUCCESS"
    assert report.total_hosts == 0
    assert report.hosts == []
    assert report.error_message


def test_scan_subnet_syntactically_valid_non_nmap_xml_is_truthful_error(monkeypatch):
    """
    Syntactically valid XML that is NOT a genuine Nmap <nmaprun> document
    (e.g. an unrelated "<foo></foo>" document) must not be silently accepted
    as a truthful zero-host SUCCESS -- syntactic XML validity alone is not
    proof of a real Nmap result.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    monkeypatch.setattr(subprocess, "run", _fake_nmap_run("<foo></foo>", returncode=0))

    scanner = NetworkScanner()
    report = scanner.scan_subnet("192.168.1.0/24")

    assert report.status != "SUCCESS"
    assert report.total_hosts == 0
    assert report.hosts == []
    assert report.error_message


def test_scan_subnet_semantic_parse_failure_is_truthful_error_not_zero_hosts(monkeypatch):
    """
    Well-formed <nmaprun> XML that fails during SEMANTIC extraction (e.g. a
    non-numeric portid) must not be silently indistinguishable from a
    genuine zero-host scan -- it must be reported as a truthful ERROR with
    zero hosts, not a fabricated-looking empty SUCCESS.
    """
    bad_portid_xml = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="192.168.1.10" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="not-a-number">
        <state state="open"/>
      </port>
    </ports>
  </host>
</nmaprun>
"""
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    monkeypatch.setattr(subprocess, "run", _fake_nmap_run(bad_portid_xml, returncode=0))

    scanner = NetworkScanner()
    report = scanner.scan_subnet("192.168.1.0/24")

    assert report.status != "SUCCESS"
    assert report.status == "ERROR"
    assert report.hosts == []
    assert report.total_hosts == 0
    assert report.error_message


def test_scan_subnet_subprocess_exception_is_truthful_error(monkeypatch):
    """A genuine subprocess execution exception must not fabricate hosts."""
    def _raise_oserror(cmd, **kwargs):
        raise OSError("nmap.exe could not be executed")

    monkeypatch.setattr(shutil, "which", lambda cmd: "nmap.exe")
    monkeypatch.setattr(subprocess, "run", _raise_oserror)

    scanner = NetworkScanner()
    report = scanner.scan_subnet("192.168.1.0/24")

    assert report.status != "SUCCESS"
    assert report.total_hosts == 0
    assert report.hosts == []
    assert report.error_message
    assert not any(h.hostname in ("router.lan", "desktop.lan") for h in report.hosts)


def test_scan_subnet_malformed_xml_is_truthful_error_not_fabricated(monkeypatch):
    """Malformed/unparseable Nmap XML output must not silently become a fabricated SUCCESS."""
    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    monkeypatch.setattr(
        subprocess, "run",
        _fake_nmap_run("<nmaprun><host><status state='up'", returncode=0),
    )

    scanner = NetworkScanner()
    report = scanner.scan_subnet("192.168.1.0/24")

    assert report.status != "SUCCESS"
    assert report.total_hosts == 0
    assert report.hosts == []
    assert not any(h.hostname in ("router.lan", "desktop.lan") for h in report.hosts)
