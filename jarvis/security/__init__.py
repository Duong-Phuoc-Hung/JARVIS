"""
jarvis/security
===============
Network Security Auditing, Packet Capture, and Vulnerability Risk Assessment Package.
Features:
  - F-23: Nmap Subnet Scanner and Port/Service Auditing.
  - F-24: TShark Live Packet Capture and Anomaly Analysis.
  - F-25: Markdown Vulnerability Risk Reports & Spoken Executive Briefings.
  - R12 / F-34: Biometric Privilege Gate Enforcement.
  - SEC-004: Path Traversal Defense & Canonical Containment.
"""
from __future__ import annotations

from jarvis.core.models import SecurityConfigurationError
from jarvis.security.path_guard import validate_safe_path
from jarvis.security.prompt_guard import PromptGuard, SanitizationResult
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
from jarvis.security.secrets import (
    KNOWN_SECRETS,
    delete_secret,
    get_secret,
    set_secret,
)

__all__ = [
    "HostScanResult",
    "KNOWN_SECRETS",
    "NetworkScanner",
    "NmapScannerWrapper",
    "PacketCapture",
    "PacketCaptureResult",
    "PromptGuard",
    "SanitizationResult",
    "ScanReport",
    "SecurityConfigurationError",
    "SecurityPrivilegeGate",
    "SecurityReportGenerator",
    "TSharkCaptureWrapper",
    "Vulnerability",
    "VulnerabilitySeverity",
    "delete_secret",
    "get_secret",
    "set_secret",
    "validate_safe_path",
]
