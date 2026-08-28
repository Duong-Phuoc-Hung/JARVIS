"""
tests/test_challenger_m4_2_security.py
======================================
Comprehensive Adversarial Stress Test Suite for Milestone 4 Security Subsystem.
Written by Challenger 2.
"""

import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
    resolve_nmap_binary,
    resolve_tshark_binary,
)

# ============================================================================
# ADVERSARIAL VECTOR 1: BIOMETRIC PRIVILEGE GATING BYPASS ATTEMPTS
# ============================================================================

def test_privilege_gate_exhaustive_matrix():
    """
    Adversarially probe all permutations of authentication, privilege levels, and spoofed contexts.
    """
    # 1. None context
    assert SecurityPrivilegeGate.verify_privilege(None) is False
    with pytest.raises(PermissionError):
        SecurityPrivilegeGate.enforce(None)

    # 2. Unauthenticated NORMAL user
    ctx_unauth_normal = RequesterContext(requester_id="guest", is_authenticated=False, granted_privilege=PrivilegeLevel.NORMAL)
    assert SecurityPrivilegeGate.verify_privilege(ctx_unauth_normal) is False
    with pytest.raises(PermissionError):
        SecurityPrivilegeGate.enforce(ctx_unauth_normal)

    # 3. Unauthenticated HIGH user
    ctx_unauth_high = RequesterContext(requester_id="guest", is_authenticated=False, granted_privilege=PrivilegeLevel.HIGH)
    assert SecurityPrivilegeGate.verify_privilege(ctx_unauth_high) is False
    with pytest.raises(PermissionError):
        SecurityPrivilegeGate.enforce(ctx_unauth_high)

    # 4. Unauthenticated ADMIN (Privilege escalation attempt without auth)
    ctx_unauth_admin = RequesterContext(requester_id="intruder", is_authenticated=False, granted_privilege=PrivilegeLevel.ADMIN)
    assert SecurityPrivilegeGate.verify_privilege(ctx_unauth_admin) is False
    with pytest.raises(PermissionError):
        SecurityPrivilegeGate.enforce(ctx_unauth_admin)

    # 5. Authenticated but NORMAL privilege (Insufficient privilege)
    ctx_auth_normal = RequesterContext(requester_id="user1", is_authenticated=True, granted_privilege=PrivilegeLevel.NORMAL)
    assert SecurityPrivilegeGate.verify_privilege(ctx_auth_normal) is False
    with pytest.raises(PermissionError):
        SecurityPrivilegeGate.enforce(ctx_auth_normal)

    # 6. Authenticated but HIGH privilege (Needs ADMIN for raw security tools)
    ctx_auth_high = RequesterContext(requester_id="user1", is_authenticated=True, granted_privilege=PrivilegeLevel.HIGH)
    assert SecurityPrivilegeGate.verify_privilege(ctx_auth_high) is False
    with pytest.raises(PermissionError):
        SecurityPrivilegeGate.enforce(ctx_auth_high)

    # 7. Authenticated ADMIN
    ctx_auth_admin = RequesterContext(requester_id="owner", is_authenticated=True, granted_privilege=PrivilegeLevel.ADMIN)
    assert SecurityPrivilegeGate.verify_privilege(ctx_auth_admin) is True
    SecurityPrivilegeGate.enforce(ctx_auth_admin)

    # 8. System internal context
    ctx_sys = RequesterContext.system()
    assert SecurityPrivilegeGate.verify_privilege(ctx_sys) is True
    SecurityPrivilegeGate.enforce(ctx_sys)


def test_scanner_and_capture_reject_unauthenticated_contexts(monkeypatch):
    """
    Verify NetworkScanner and PacketCapture enforce gating when unauthenticated context is provided.
    """
    monkeypatch.setattr(shutil, "which", lambda cmd: "fake_tool.exe")
    
    scanner = NetworkScanner()
    capture = PacketCapture()

    unauth_ctx = RequesterContext.user(requester_id="intruder_123", authenticated=False)

    scan_res = scanner.scan_subnet("192.168.1.0/24", context=unauth_ctx)
    assert scan_res.status == "PERMISSION_DENIED"
    assert scan_res.total_hosts == 0
    assert "Biometric authentication required" in (scan_res.error_message or "")

    cap_res = capture.capture_packets(interface="eth0", context=unauth_ctx)
    assert cap_res.status == "PERMISSION_DENIED"
    assert cap_res.packet_count == 0
    assert "Biometric authentication required" in (cap_res.error_message or "")


# ============================================================================
# ADVERSARIAL VECTOR 2: SUBPROCESS INJECTION & COMMAND CHAINING
# ============================================================================

@pytest.mark.parametrize("malicious_target", [
    "192.168.1.1; echo INJECTED",
    "192.168.1.1 & calc.exe",
    "192.168.1.1 | whoami",
    "192.168.1.1 && net user",
    "192.168.1.1 `dir`",
    "192.168.1.1 $(id)",
    "192.168.1.1\nwhoami",
    "192.168.1.1' OR '1'='1",
    "192.168.1.1 --script=vuln --privileged",
    "192.168.1.1\0whoami",
])
def test_network_scanner_command_injection_resilience(malicious_target, monkeypatch):
    """
    Verify that arbitrary injection strings passed as subnet targets are passed as a single
    element in argument list to subprocess.run (shell=False) and do not trigger command execution.
    """
    executed_commands = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        executed_commands.append((cmd, kwargs))
        assert kwargs.get("shell") is not True, "VULNERABILITY: shell=True detected in subprocess.run!"
        assert malicious_target in cmd, f"Malicious payload was not kept intact: {cmd}"
        
        sample_xml = """<?xml version="1.0"?>
        <nmaprun>
          <host><status state="up"/><address addr="192.168.1.1" addrtype="ipv4"/></host>
        </nmaprun>"""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = sample_xml
        return mock_proc

    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    scanner = NetworkScanner()
    res = scanner.scan_subnet(malicious_target)

    assert len(executed_commands) == 1
    cmd_list, kw = executed_commands[0]
    assert cmd_list[-1] == malicious_target
    assert res.status == "SUCCESS"


@pytest.mark.parametrize("malicious_ports", [
    "80,443; calc.exe",
    "80 & whoami",
    "80 | dir",
    "-sV -O --privileged",
])
def test_network_scanner_ports_injection_resilience(malicious_ports, monkeypatch):
    """
    Verify that port parameter is safe from shell expansion.
    """
    executed_commands = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        executed_commands.append((cmd, kwargs))
        assert kwargs.get("shell") is not True
        assert f"-p{malicious_ports}" in cmd
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = """<?xml version="1.0"?><nmaprun></nmaprun>"""
        return mock_proc

    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Nmap\\nmap.exe")
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    scanner = NetworkScanner()
    res = scanner.scan_subnet("192.168.1.1", ports=malicious_ports)

    assert len(executed_commands) == 1
    assert res.status == "SUCCESS"


@pytest.mark.parametrize("malicious_bpf", [
    "tcp and port 80; calc.exe",
    "udp | whoami",
    "host 10.0.0.1 && dir C:\\",
    "`calc.exe`",
])
def test_packet_capture_injection_resilience(malicious_bpf, monkeypatch):
    """
    Verify that malicious BPF filters are passed safely without shell invocation.
    """
    executed_commands = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        executed_commands.append((cmd, kwargs))
        assert kwargs.get("shell") is not True
        assert "-f" in cmd
        filter_idx = cmd.index("-f") + 1
        assert cmd[filter_idx] == malicious_bpf
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        return mock_proc

    monkeypatch.setattr(shutil, "which", lambda cmd: "C:\\Program Files\\Wireshark\\tshark.exe")
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    capture = PacketCapture()
    res = capture.capture_packets(interface="Ethernet", count=10, bpf_filter=malicious_bpf)

    assert len(executed_commands) == 1
    assert res.status == "SUCCESS"
    assert res.packet_count == 10


# ============================================================================
# ADVERSARIAL VECTOR 3: SUBPROCESS HANG / TIMEOUT RESILIENCE
# ============================================================================

def test_nmap_subprocess_timeout_expired(monkeypatch):
    """
    Verify timeout in Nmap scanner is caught cleanly, returns TIMEOUT status, and does not crash.
    """
    def mock_hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["nmap.exe"], timeout=1.5)

    monkeypatch.setattr(shutil, "which", lambda cmd: "nmap.exe")
    monkeypatch.setattr(subprocess, "run", mock_hang)

    scanner = NetworkScanner(timeout_s=1.5)
    report = scanner.scan_subnet("10.0.0.0/8")

    assert report.status == "TIMEOUT"
    assert report.total_hosts == 0
    assert report.hosts == []
    assert "timeout" in report.error_message.lower()


def test_tshark_subprocess_timeout_or_error_handling(monkeypatch):
    """
    Verify TShark subprocess timeout/error degrades gracefully without unhandled exception.
    """
    def mock_error(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["tshark.exe"], timeout=2.0)

    monkeypatch.setattr(shutil, "which", lambda cmd: "tshark.exe")
    monkeypatch.setattr(subprocess, "run", mock_error)

    capture = PacketCapture(default_duration_s=2.0)
    res = capture.capture_packets(interface="eth0", count=50)

    assert res is not None
    assert res.packet_count == 50
    assert "TCP" in res.protocols


# ============================================================================
# ADVERSARIAL VECTOR 4: MALFORMED NMAP XML & OUTPUT PARSING
# ============================================================================

@pytest.mark.parametrize("malformed_xml", [
    "",
    "   \n\t  ",
    "<not_xml><unclosed_tag>",
    "<?xml version='1.0'?><nmaprun></nmaprun>",
    "<?xml version='1.0'?><nmaprun><host><status state='down'/><address addr='10.0.0.1' addrtype='ipv4'/></host></nmaprun>",
    "<?xml version='1.0'?><nmaprun><host><status state='up'/><address addr='10.0.0.2' addrtype='mac'/></host></nmaprun>",
    "<?xml version='1.0'?><nmaprun><host><status state='up'/><address addr='10.0.0.3' addrtype='ipv4'/><ports><port portid='invalid'><state state='open'/></port></ports></host></nmaprun>",
    "<?xml version='1.0'?><nmaprun><host><status state='up'/><address addr='10.0.0.4' addrtype='ipv4'/><ports><port portid='80'><state state='closed'/></port><port portid='443'><state state='filtered'/></port></ports></host></nmaprun>",
    "<!DOCTYPE foo [<!ELEMENT foo ANY ><!ENTITY xxe SYSTEM 'file:///c:/windows/win.ini'>]><nmaprun><host><status state='up'/><address addr='1.2.3.4' addrtype='ipv4'/></host></nmaprun>",
])
def test_nmap_xml_parser_malformed_inputs(malformed_xml):
    """
    Verify XML parser does not throw uncaught exceptions on malformed, truncated, empty, or hostile XML.
    """
    scanner = NetworkScanner()
    hosts = scanner._parse_nmap_xml(malformed_xml)
    assert isinstance(hosts, list)
    if hosts and hosts[0].ip == "10.0.0.4":
        assert hosts[0].open_ports == []


def test_nmap_xml_parser_large_scale_hosts():
    """
    Verify parser handles large subnet result with 300 hosts without degradation.
    """
    xml_hosts = []
    for i in range(1, 301):
        xml_hosts.append(f"""
        <host>
            <status state="up"/>
            <address addr="10.0.1.{i}" addrtype="ipv4"/>
            <hostnames><hostname name="host-{i}.local"/></hostnames>
            <ports>
                <port portid="80"><state state="open"/><service name="http"/></port>
                <port portid="443"><state state="open"/><service name="https"/></port>
            </ports>
        </host>
        """)
    large_xml = f"<?xml version='1.0'?><nmaprun>{''.join(xml_hosts)}</nmaprun>"

    scanner = NetworkScanner()
    t0 = time.time()
    hosts = scanner._parse_nmap_xml(large_xml)
    t_parse = time.time() - t0

    assert len(hosts) == 300
    assert hosts[0].ip == "10.0.1.1"
    assert hosts[0].hostname == "host-1.local"
    assert hosts[0].open_ports == [80, 443]
    assert hosts[0].services[80] == "http"
    assert t_parse < 1.0, f"Parsing 300 hosts took too long: {t_parse:.3f}s"


# ============================================================================
# ADVERSARIAL VECTOR 5: SECURITY REPORT GENERATION EDGE CASES
# ============================================================================

def test_report_generator_with_empty_and_error_scans(tmp_path):
    """
    Verify report generator handles scans with zero hosts, error statuses, and missing fields.
    """
    generator = SecurityReportGenerator()

    # 1. Error scan
    error_scan = ScanReport(
        target="10.0.0.0/24",
        hosts=[],
        total_hosts=0,
        status="ERROR",
        error_message="Raw socket permission required",
    )
    res_err = generator.generate_report(error_scan, output_dir=tmp_path / "err")
    assert res_err["report_path"].exists()
    content = res_err["report_path"].read_text(encoding="utf-8")
    assert "ERROR" in content
    assert "Total Active Hosts: **0**" in content

    # 2. Tool not found scan
    not_found_scan = ScanReport(
        target="192.168.1.0/24",
        hosts=[],
        total_hosts=0,
        status="TOOL_NOT_FOUND",
        error_message="Nmap binary not installed",
    )
    res_nf = generator.generate_report(not_found_scan, output_dir=tmp_path / "nf", lang="vi")
    assert "Không thể thực hiện quét" in res_nf["voice_summary"]
    res_nf_en = generator.generate_report(not_found_scan, output_dir=tmp_path / "nf_en", lang="en")
    assert "not found" in res_nf_en["voice_summary"].lower()


def test_report_generator_severity_rankings(tmp_path):
    """
    Verify critical vs high risk classification and markdown generation.
    """
    generator = SecurityReportGenerator()

    # Low risk (no vulns)
    scan_clean = ScanReport(
        target="192.168.1.1",
        hosts=[HostScanResult(ip="192.168.1.1", hostname="gw", status="UP", open_ports=[53], services={53: "dns"})],
        total_hosts=1,
        status="SUCCESS",
    )
    res_clean = generator.generate_report(scan_clean, output_dir=tmp_path / "clean")
    md_clean = res_clean["report_path"].read_text(encoding="utf-8")
    assert "LOW RISK" in md_clean

    # High risk (Medium/High vuln)
    vuln_high = Vulnerability(id="CVE-1", title="TLS 1.0 Enabled", severity=VulnerabilitySeverity.HIGH, description="Outdated TLS")
    scan_high = ScanReport(
        target="192.168.1.1",
        hosts=[HostScanResult(ip="192.168.1.1", hostname="gw", status="UP", vulnerabilities=[vuln_high])],
        total_hosts=1,
        status="SUCCESS",
    )
    res_high = generator.generate_report(scan_high, output_dir=tmp_path / "high")
    md_high = res_high["report_path"].read_text(encoding="utf-8")
    assert "HIGH RISK" in md_high

    # Critical risk
    vuln_crit = Vulnerability(id="CVE-2", title="Log4Shell RCE", severity=VulnerabilitySeverity.CRITICAL, description="Unauthenticated RCE")
    scan_crit = ScanReport(
        target="192.168.1.1",
        hosts=[HostScanResult(ip="192.168.1.1", hostname="gw", status="UP", vulnerabilities=[vuln_crit])],
        total_hosts=1,
        status="SUCCESS",
    )
    res_crit = generator.generate_report(scan_crit, output_dir=tmp_path / "crit")
    md_crit = res_crit["report_path"].read_text(encoding="utf-8")
    assert "CRITICAL RISK" in md_crit


def test_packet_capture_result_container_semantics():
    """
    Verify PacketCaptureResult satisfies both dataclass attribute and dict-like subscript access.
    """
    cap = PacketCaptureResult(
        interface="Ethernet",
        packet_count=100,
        duration_s=5.0,
        protocols={"TCP": 70, "UDP": 20, "ICMP": 10},
        anomalies_detected=1,
        anomalies=["SYN flood suspected"],
        status="SUCCESS",
    )
    # Dataclass attr access
    assert cap.interface == "Ethernet"
    assert cap.packet_count == 100
    assert cap.protocols["TCP"] == 70

    # Subscript dict access
    assert cap["interface"] == "Ethernet"
    assert cap["packet_count"] == 100
    assert cap["protocols"]["UDP"] == 20
    assert "anomalies" in cap
    assert cap.get("anomalies_detected") == 1
    assert cap.get("non_existent", "default") == "default"
    assert "protocols" in list(cap.keys())


def test_concurrent_scanning_and_report_generation(tmp_path):
    """
    Verify multi-threaded execution safety when multiple concurrent scans generate reports.
    """
    generator = SecurityReportGenerator()

    def run_worker(idx: int):
        scan = ScanReport(
            target=f"10.0.{idx}.0/24",
            hosts=[
                HostScanResult(
                    ip=f"10.0.{idx}.1",
                    hostname=f"router-{idx}",
                    status="UP",
                    open_ports=[80, 443],
                )
            ],
            total_hosts=1,
            status="SUCCESS",
        )
        res = generator.generate_report(scan, output_dir=tmp_path / f"worker_{idx}")
        assert res["report_path"].exists()
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(run_worker, i) for i in range(16)]
        results = [f.result() for f in futures]
    assert all(results)
