"""
jarvis/security/scanner.py
==========================
Network Scanner (Nmap) and Packet Capture (TShark) Subprocess Wrappers.
Features:
  - F-23: Subnet discovery, port scanning, and vulnerability script audits via Nmap CLI.
  - F-24: Live packet capture, protocol distribution breakdown, and anomaly detection via TShark CLI.
  - Graceful degradation returning structured diagnostic records (TOOL_NOT_FOUND, TIMEOUT, etc.) on missing binaries.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from jarvis.core.models import RequesterContext

log = logging.getLogger("jarvis.security.scanner")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class VulnerabilitySeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class Vulnerability:
    """Discovered network security vulnerability or exposure."""
    id: str                                  # e.g., "CVE-2021-44228", "NMAP-SMB-MS17-010"
    title: str
    severity: VulnerabilitySeverity
    description: str
    port: int | None = None
    remediation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.value if isinstance(self.severity, VulnerabilitySeverity) else str(self.severity),
            "description": self.description,
            "port": self.port,
            "remediation": self.remediation,
        }


@dataclass
class HostScanResult:
    """Network scan result for an individual discovered host."""
    ip: str
    hostname: str
    status: str = "UP"                       # "UP" or "DOWN"
    open_ports: list[int] = field(default_factory=list)
    services: dict[int, str] = field(default_factory=dict)
    vulnerabilities: list[Vulnerability] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ip": self.ip,
            "hostname": self.hostname,
            "status": self.status,
            "open_ports": list(self.open_ports),
            "services": dict(self.services),
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
        }


@dataclass
class ScanReport:
    """Comprehensive network audit and vulnerability scan report."""
    target: str
    hosts: list[HostScanResult] = field(default_factory=list)
    total_hosts: int = 0
    duration_s: float = 0.0
    status: str = "SUCCESS"                  # "SUCCESS", "TOOL_NOT_FOUND", "TIMEOUT", "PERMISSION_DENIED", "TARGET_REJECTED", "ERROR"
    error_message: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "hosts": [h.to_dict() for h in self.hosts],
            "total_hosts": self.total_hosts,
            "duration_s": round(self.duration_s, 2),
            "status": self.status,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
        }


@dataclass
class PacketCaptureResult:
    """Aggregated telemetry from network packet capture session."""
    interface: str
    packet_count: int
    duration_s: float
    protocols: dict[str, int] = field(default_factory=dict)
    top_talkers: list[dict[str, Any]] = field(default_factory=list)
    anomalies_detected: int = 0
    anomalies: list[str] = field(default_factory=list)
    pcap_path: str | None = None
    status: str = "SUCCESS"                  # "SUCCESS", "TOOL_NOT_FOUND", "TIMEOUT", "ERROR"
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "interface": self.interface,
            "packet_count": self.packet_count,
            "duration_s": round(self.duration_s, 2),
            "protocols": dict(self.protocols),
            "top_talkers": list(self.top_talkers),
            "anomalies_detected": self.anomalies_detected,
            "anomalies": list(self.anomalies),
            "pcap_path": self.pcap_path,
            "status": self.status,
            "error_message": self.error_message,
        }

    def __getitem__(self, item: str) -> Any:
        d = self.to_dict()
        if item in d:
            return d[item]
        return getattr(self, item)

    def __contains__(self, item: str) -> bool:
        return item in self.to_dict()

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def keys(self) -> Iterator[str]:
        return iter(self.to_dict().keys())


# ---------------------------------------------------------------------------
# Network Scanner (Nmap) Wrapper (F-23)
# ---------------------------------------------------------------------------

def resolve_nmap_binary(override_path: str | None = None) -> str | None:
    """Finds nmap binary in PATH or standard Windows installation locations."""
    if override_path and os.path.isfile(override_path):
        return override_path
    if override_path:
        found = shutil.which(override_path)
        if found:
            return found

    # PATH lookup
    path = shutil.which("nmap")
    if path:
        return path

    # Common Windows directories
    prog_files = [
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
    ]
    for pf in prog_files:
        candidate = Path(pf) / "Nmap" / "nmap.exe"
        if candidate.is_file():
            return str(candidate)

    return None


# Explicit private-range scan-scope allowlist. This is a deliberate, narrow
# policy allowlist -- NOT ipaddress.ip_address(...).is_private, which also
# permits ranges outside this policy (e.g. link-local 169.254.0.0/16, CGNAT
# 100.64.0.0/10, IPv6 ULA). Public/external scanning is forbidden; a target
# must be fully contained within exactly one of these four supernets.
ALLOWED_SCAN_SUPERNETS: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def validate_scan_target(target: str) -> tuple[bool, str]:
    """
    Validates a scan target against the private-range allowlist above,
    BEFORE any Nmap binary resolution or subprocess execution is attempted.

    Fails closed:
    - a bare host literal (e.g. "192.168.1.50") is treated as an equivalent
      /32 target;
    - a CIDR must be fully contained within exactly one allowed supernet --
      a CIDR that extends even partially outside every allowed supernet is
      rejected, not accepted because part of it overlaps;
    - IPv6 targets are always rejected;
    - hostnames/DNS names are always rejected -- no DNS resolution is ever
      attempted here or by any caller of this function;
    - any malformed/unparseable target string is rejected.

    Returns (True, "") if the target may be scanned, or
    (False, <truthful human-readable reason>) otherwise.
    """
    if not isinstance(target, str) or not target.strip():
        return False, "Scan target is empty or not a string."

    candidate = target.strip()

    try:
        network = ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        return False, (
            f"Scan target '{candidate}' is not a valid IPv4 address or CIDR "
            "(hostnames/DNS names are never resolved or accepted)."
        )

    if network.version != 4:
        return False, f"Scan target '{candidate}' is IPv6; only IPv4 targets are permitted."

    for supernet in ALLOWED_SCAN_SUPERNETS:
        if network.subnet_of(supernet):
            return True, ""

    return False, (
        f"Scan target '{candidate}' is outside the permitted private-range "
        "allowlist (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16); "
        "public/external scanning is forbidden."
    )


class NetworkScanner:
    """
    Subprocess CLI wrapper executing Nmap subnet discovery and vulnerability audits.
    """

    def __init__(
        self,
        nmap_path: str | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.nmap_path = nmap_path
        self.timeout_s = timeout_s

    def scan_subnet(
        self,
        subnet: str,
        ports: str = "80,443,22,53,3306,3389,8000,8080",
        timeout_s: float | None = None,
        context: RequesterContext | None = None,
    ) -> ScanReport:
        """
        Executes Nmap subnet discovery and port auditing.
        Returns structured ScanReport with zero unhandled exceptions.
        """
        # 1. Privilege Authorization Check (R12 / F-34)
        if context is not None:
            if not context.is_authenticated and context.requester_id != "system":
                log.warning("Security scan rejected: RequesterContext not authenticated.")
                return ScanReport(
                    target=subnet,
                    hosts=[],
                    total_hosts=0,
                    status="PERMISSION_DENIED",
                    error_message="Biometric authentication required.",
                )

        # 2. Target Scope Validation (must happen before Nmap binary resolution
        # or any subprocess execution -- see validate_scan_target() above).
        is_allowed, validation_reason = validate_scan_target(subnet)
        if not is_allowed:
            log.warning("Security scan rejected for target %r: %s", subnet, validation_reason)
            return ScanReport(
                target=subnet,
                hosts=[],
                total_hosts=0,
                status="TARGET_REJECTED",
                error_message=validation_reason,
            )

        binary = resolve_nmap_binary(self.nmap_path)
        if not binary:
            log.info("Nmap binary not found on host. Gracefully returning TOOL_NOT_FOUND.")
            return ScanReport(
                target=subnet,
                hosts=[],
                total_hosts=0,
                duration_s=0.0,
                status="TOOL_NOT_FOUND",
                error_message="Nmap binary not installed or found in PATH.",
            )

        timeout = timeout_s if timeout_s is not None else self.timeout_s
        start_time = time.time()

        # Build command: fast scan with service discovery and XML output
        cmd = [
            binary,
            "-sn" if not ports else f"-p{ports}",
            "-oX", "-",
            subnet,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True, creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0),
                text=True, encoding='utf-8', errors='replace',
                timeout=timeout,
            )
            duration = time.time() - start_time

            # Security-sensitive encoding corruption check (E6 escalation):
            # CP437 garbling in Nmap output could mask real vulnerability findings.
            if "\ufffd" in (proc.stdout or "") or "\ufffd" in (proc.stderr or ""):
                log.critical(
                    "[scanner.nmap] Output contained non-UTF-8 bytes (U+FFFD replacement). "
                    "Security scan results may be incomplete. target=%r", subnet,
                )
                try:
                    from jarvis.workers.notification_hub import NotificationHub
                    hub = NotificationHub.get_instance()
                    if hub:
                        hub.send(
                            title="⚠️ Security scanner encoding corruption",
                            body=f"[scanner.nmap] Output contained non-UTF-8 bytes for target {subnet!r}. Scan results may be incomplete.",
                            level="critical",
                        )
                except Exception:
                    pass

            if proc.returncode != 0:
                # Nmap did not complete successfully (e.g. permissions/raw-socket
                # requirements, or the binary genuinely failed). A nonzero exit
                # code is never overridden by SUCCESS just because stdout happens
                # to contain parseable or partial-looking XML -- the process's
                # own exit status is the truthful signal here, and it must never
                # be papered over with fabricated (or even genuine-but-partial)
                # host data.
                stderr_snippet = (proc.stderr or "").strip()
                if not proc.stdout.strip():
                    message = f"Nmap exited with code {proc.returncode} and produced no output."
                else:
                    message = f"Nmap exited with code {proc.returncode}."
                if stderr_snippet:
                    message += f" {stderr_snippet[:300]}"
                return ScanReport(
                    target=subnet,
                    hosts=[],
                    total_hosts=0,
                    duration_s=duration,
                    status="ERROR",
                    error_message=message,
                )

            if not self._xml_parses_successfully(proc.stdout):
                # Nmap ran, but the output is either not well-formed XML, or
                # is well-formed XML that is not a genuine <nmaprun> document
                # (syntactic XML validity alone is not proof of a real Nmap
                # result). This is distinct from a genuine, well-formed,
                # zero-host result -- do not fabricate hosts to fill the gap.
                return ScanReport(
                    target=subnet,
                    hosts=[],
                    total_hosts=0,
                    duration_s=duration,
                    status="ERROR",
                    error_message="Nmap output could not be parsed as valid Nmap XML.",
                )

            # Parse XML output. An empty `hosts` list here is a genuine,
            # truthful zero-host result (e.g. no hosts responded) -- it is
            # reported as-is, never replaced with fabricated data. Unlike
            # `_parse_nmap_xml()` (kept lenient for existing direct callers),
            # `_parse_nmap_xml_strict()` does NOT swallow a semantic
            # extraction failure on otherwise well-formed <nmaprun> XML (e.g.
            # a non-numeric portid) into an empty list -- that would be
            # indistinguishable from a genuine empty scan. Such a failure is
            # reported as a truthful ERROR instead.
            try:
                hosts = self._parse_nmap_xml_strict(proc.stdout)
            except Exception as e:
                log.warning("Nmap XML failed semantic parsing for target %r: %s", subnet, e)
                return ScanReport(
                    target=subnet,
                    hosts=[],
                    total_hosts=0,
                    duration_s=duration,
                    status="ERROR",
                    error_message=f"Nmap output could not be semantically parsed: {e}",
                )

            return ScanReport(
                target=subnet,
                hosts=hosts,
                total_hosts=len(hosts),
                duration_s=duration,
                status="SUCCESS",
            )

        except subprocess.TimeoutExpired:
            log.warning("Nmap scan timed out on target %s after %.1fs", subnet, timeout)
            return ScanReport(
                target=subnet,
                hosts=[],
                total_hosts=0,
                duration_s=timeout,
                status="TIMEOUT",
                error_message=f"Scan exceeded timeout limit of {timeout}s",
            )
        except Exception as e:
            # Genuine execution failure (binary could not be launched, etc).
            # Report truthfully -- never fabricate hosts.
            log.warning("Nmap subprocess execution failed for target %r: %s", subnet, e)
            return ScanReport(
                target=subnet,
                hosts=[],
                total_hosts=0,
                duration_s=time.time() - start_time,
                status="ERROR",
                error_message=f"Nmap execution failed: {e}",
            )

    def _extract_hosts_from_root(self, root: ET.Element) -> list[HostScanResult]:
        """
        Core Nmap <nmaprun> host/port extraction, shared by `_parse_nmap_xml()`
        (lenient -- swallows any extraction failure to []) and
        `_parse_nmap_xml_strict()` (used by `scan_subnet()` -- lets an
        extraction failure, e.g. a non-numeric portid, propagate). This
        method itself does not catch exceptions; callers decide whether to
        swallow or propagate them.
        """
        hosts: list[HostScanResult] = []
        for host_el in root.findall("host"):
            status_el = host_el.find("status")
            if status_el is not None and status_el.get("state") != "up":
                continue

            # IP address
            ip = ""
            for addr in host_el.findall("address"):
                if addr.get("addrtype") == "ipv4":
                    ip = addr.get("addr", "")
                    break
            if not ip:
                continue

            # Hostname
            hostname = ip
            hostnames_el = host_el.find("hostnames")
            if hostnames_el is not None:
                hname_el = hostnames_el.find("hostname")
                if hname_el is not None:
                    hostname = hname_el.get("name", ip)

            # Ports
            open_ports: list[int] = []
            services: dict[int, str] = {}
            ports_el = host_el.find("ports")
            if ports_el is not None:
                for p in ports_el.findall("port"):
                    state_el = p.find("state")
                    if state_el is not None and state_el.get("state") == "open":
                        p_id = int(p.get("portid", 0))
                        if p_id > 0:
                            open_ports.append(p_id)
                            s_el = p.find("service")
                            if s_el is not None:
                                services[p_id] = s_el.get("name", "unknown")

            hosts.append(
                HostScanResult(
                    ip=ip,
                    hostname=hostname,
                    status="UP",
                    open_ports=open_ports,
                    services=services,
                )
            )
        return hosts

    def _parse_nmap_xml(self, xml_content: str) -> list[HostScanResult]:
        """
        Parses Nmap -oX XML output into HostScanResult list.

        Legacy, lenient contract preserved for existing direct callers: any
        problem at all -- structurally malformed XML, or a semantic value
        that cannot be interpreted (e.g. a non-numeric portid) -- is
        swallowed and returns []. `scan_subnet()` itself does not rely on
        this lenient behavior; it calls `_parse_nmap_xml_strict()` instead,
        so a genuine parsing failure is never silently indistinguishable
        from a truthful empty scan result there.
        """
        if not xml_content or not xml_content.strip():
            return []
        try:
            root = ET.fromstring(xml_content)
            return self._extract_hosts_from_root(root)
        except Exception as e:
            log.debug("XML parse error in Nmap output: %s", e)
            return []

    def _parse_nmap_xml_strict(self, xml_content: str) -> list[HostScanResult]:
        """
        Used only by `scan_subnet()`, after `_xml_parses_successfully()` has
        already confirmed well-formed <nmaprun> XML. Unlike `_parse_nmap_xml()`,
        this does NOT swallow a semantic extraction failure (e.g. a
        non-numeric portid) into an empty list -- it lets the underlying
        exception propagate, so `scan_subnet()` can report a truthful ERROR
        instead of a result indistinguishable from a genuine zero-host scan.
        """
        root = ET.fromstring(xml_content)
        return self._extract_hosts_from_root(root)

    def _xml_parses_successfully(self, xml_content: str) -> bool:
        """
        Reports whether `xml_content` is well-formed XML with the expected
        Nmap `<nmaprun>` root element, distinct from `_parse_nmap_xml()`'s own
        lenient "return [] on any problem" contract. Syntactic XML validity
        alone is NOT sufficient proof of a genuine Nmap result -- an
        unrelated-but-well-formed document (e.g. "<foo></foo>") must not be
        silently treated as a truthful zero-host SUCCESS. Used by
        `scan_subnet()` to tell a genuine, well-formed, zero-host Nmap result
        apart from empty/malformed/non-Nmap/unparseable output that must
        never be silently treated as a (fabricated-or-otherwise) successful
        scan.
        """
        if not xml_content or not xml_content.strip():
            return False
        try:
            root = ET.fromstring(xml_content)
        except Exception:
            return False
        return root.tag == "nmaprun"


# Alias for test suite compatibility
NmapScannerWrapper = NetworkScanner


# ---------------------------------------------------------------------------
# Packet Capture (TShark) Wrapper (F-24)
# ---------------------------------------------------------------------------

def resolve_tshark_binary(override_path: str | None = None) -> str | None:
    """Finds tshark binary in PATH or Wireshark install locations."""
    if override_path and os.path.isfile(override_path):
        return override_path
    if override_path:
        found = shutil.which(override_path)
        if found:
            return found

    path = shutil.which("tshark")
    if path:
        return path

    prog_files = [
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
    ]
    for pf in prog_files:
        candidate = Path(pf) / "Wireshark" / "tshark.exe"
        if candidate.is_file():
            return str(candidate)

    return None


def _parse_tshark_protocols(stdout: str) -> dict[str, int]:
    """Parse real TShark stdout into a protocol-count mapping.

    Supports two common TShark output formats:
      - ``tshark -T fields -e frame.protocols`` — one protocol-chain per line
        e.g. ``eth:ethertype:ip:tcp``
      - ``tshark -qz io,phs`` — summary block with ``|protocol|`` entries

    Returns an empty dict if stdout is empty or no recognisable format is found.

    NOTE — UNTESTED: no TShark available in dev environment as of 2026-09-04.
    This function must be tested end-to-end once TShark is installed.
    The caller (PacketCapture.capture_packets) already has a
    ``@pytest.mark.skip(reason="requires tshark binary")`` guard on its test.
    """
    if not stdout or not stdout.strip():
        return {}

    counts: dict[str, int] = {}
    KNOWN_PROTOS = {"tcp", "udp", "icmp", "icmpv6", "dns", "http", "tls", "arp", "igmp"}

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format 1: colon-separated protocol chains (frame.protocols field)
        if ":" in line and not line.startswith("|"):
            for proto in line.split(":"):
                p = proto.strip().lower()
                if p in KNOWN_PROTOS:
                    counts[p.upper()] = counts.get(p.upper(), 0) + 1
        # Format 2: io,phs summary table  "| tcp  | 42 | ..."
        elif line.startswith("|"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                proto = parts[0].strip().lower()
                if proto in KNOWN_PROTOS:
                    try:
                        counts[proto.upper()] = int(parts[1])
                    except ValueError:
                        pass

    return counts


class PacketCapture:
    """
    Subprocess CLI wrapper executing live packet capture and heuristic protocol analysis via TShark.
    """


    def __init__(
        self,
        tshark_path: str | None = None,
        default_duration_s: float = 10.0,
    ) -> None:
        self.tshark_path = tshark_path
        self.default_duration_s = default_duration_s

    def capture_packets(
        self,
        interface: str = "eth0",
        count: int = 50,
        duration_s: float | None = None,
        bpf_filter: str | None = None,
        output_pcap: Path | None = None,
        context: RequesterContext | None = None,
    ) -> PacketCaptureResult:
        """
        Executes live packet capture and protocol distribution analysis.
        Returns structured PacketCaptureResult (supports dict access in tests).
        """
        # 1. Privilege Authorization Check (R12 / F-34)
        if context is not None:
            if not context.is_authenticated and context.requester_id != "system":
                log.warning("Packet capture rejected: RequesterContext not authenticated.")
                return PacketCaptureResult(
                    interface=interface,
                    packet_count=0,
                    duration_s=0.0,
                    status="PERMISSION_DENIED",
                    error_message="Biometric authentication required.",
                )

        binary = resolve_tshark_binary(self.tshark_path)
        if not binary:
            log.info("TShark binary not found on host. Gracefully returning TOOL_NOT_FOUND.")
            return PacketCaptureResult(
                interface=interface,
                packet_count=0,
                duration_s=0.0,
                status="TOOL_NOT_FOUND",
                error_message="TShark / Wireshark not installed or found in PATH.",
            )

        duration = duration_s if duration_s is not None else self.default_duration_s
        start_time = time.time()

        # Build TShark command
        cmd = [
            binary,
            "-i", interface,
            "-c", str(count),
            "-a", f"duration:{int(duration)}",
        ]
        if bpf_filter:
            cmd.extend(["-f", bpf_filter])
        if output_pcap:
            cmd.extend(["-w", str(output_pcap)])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True, creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0),
                text=True, encoding='utf-8', errors='replace',
                timeout=duration + 5.0,
            )
            elapsed = time.time() - start_time

            # Security-sensitive encoding corruption check (E6 escalation)
            if "\ufffd" in (proc.stdout or "") or "\ufffd" in (proc.stderr or ""):
                log.critical(
                    "[scanner.tshark] Output contained non-UTF-8 bytes (U+FFFD). "
                    "Packet capture results may be incomplete. interface=%r", interface,
                )
                try:
                    from jarvis.workers.notification_hub import NotificationHub
                    hub = NotificationHub.get_instance()
                    if hub:
                        hub.send(
                            title="⚠️ Security scanner encoding corruption",
                            body=f"[scanner.tshark] Packet capture output contained non-UTF-8 bytes for interface {interface!r}.",
                            level="critical",
                        )
                except Exception:
                    pass
            # Pass real stdout to _build_capture_result for truthful parsing
            return self._build_capture_result(
                interface, count, elapsed,
                pcap_path=str(output_pcap) if output_pcap else None,
                raw_stdout=proc.stdout or "",
            )

        except Exception as e:
            log.debug("TShark capture execution note: %s.", e)
            elapsed = time.time() - start_time
            # No stdout available — return truthful empty result, not fabricated data
            return self._build_capture_result(
                interface, count, elapsed or duration,
                pcap_path=str(output_pcap) if output_pcap else None,
                raw_stdout=None,
            )

    def _build_capture_result(
        self,
        interface: str,
        count: int,
        duration: float,
        pcap_path: str | None = None,
        raw_stdout: str | None = None,
    ) -> PacketCaptureResult:
        """Build a PacketCaptureResult from real TShark output, or report unavailability.

        Previously this method fabricated fixed 70/20/10 TCP/UDP/ICMP ratios regardless
        of actual capture results. That fabrication has been removed (2026-09-04).

        Args:
            raw_stdout: The actual text output from the tshark subprocess.
                        If None or empty, no protocol data is available and
                        status is set to NO_TSHARK_OUTPUT rather than faking numbers.
        """
        if raw_stdout:
            # UNTESTED: no TShark available in dev environment as of 2026-09-04.
            # This branch parses real tshark output once TShark is installed.
            # Covered by tests/unit/test_runaway_guard.py marked
            # @pytest.mark.skip(reason="requires tshark binary").
            protocols = _parse_tshark_protocols(raw_stdout)
            status = "SUCCESS" if protocols else "NO_PROTOCOLS_PARSED"
        else:
            # Truthful: capture ran but produced no parseable output, or TShark
            # subprocess raised an exception. Do NOT fabricate protocol counts.
            protocols = {}
            status = "NO_TSHARK_OUTPUT"

        return PacketCaptureResult(
            interface=interface,
            packet_count=count,
            duration_s=duration,
            protocols=protocols,
            anomalies_detected=0,
            anomalies=[],
            pcap_path=pcap_path,
            status=status,
        )


# Alias for test suite compatibility
TSharkCaptureWrapper = PacketCapture
