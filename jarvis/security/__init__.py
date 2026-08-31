"""
jarvis/security
===============
Network Security Auditing, Packet Capture, and Vulnerability Risk Assessment Package.
Features:
  - F-23: Nmap Subnet Scanner and Port/Service Auditing.
  - F-24: TShark Live Packet Capture and Anomaly Analysis.
  - F-25: Markdown Vulnerability Risk Reports & Spoken Executive Briefings.
  - R12 / F-34: Biometric Privilege Gate Enforcement.
"""
from __future__ import annotations

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

__all__ = [
    "HostScanResult",
    "NetworkScanner",
    "NmapScannerWrapper",
    "PacketCapture",
    "PacketCaptureResult",
    "PromptGuard",
    "SanitizationResult",
    "ScanReport",
    "SecurityPrivilegeGate",
    "SecurityReportGenerator",
    "TSharkCaptureWrapper",
    "Vulnerability",
    "VulnerabilitySeverity",
]
