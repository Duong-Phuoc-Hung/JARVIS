"""
jarvis/security/report.py
=========================
Security Risk Report Generator and Biometric Privilege Gating (R12 / F-25).
Features:
  - F-25: Compiles scan findings into structured Markdown documents and spoken summaries.
  - R12 / F-34: Enforces Biometric Privilege Gate before executing security audits or packet captures.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from jarvis.core.models import PrivilegeLevel, RequesterContext
from jarvis.security.scanner import (
    PacketCaptureResult,
    ScanReport,
    VulnerabilitySeverity,
)

log = logging.getLogger("jarvis.security.report")


class SecurityPrivilegeGate:
    """
    Enforces biometric authorization barrier for sensitive security actions (R12 / F-34).
    """

    @staticmethod
    def verify_privilege(context: RequesterContext | None, action_name: str = "security_scan") -> bool:
        """
        Validates if requester context possesses verified biometric authentication and admin privilege.
        """
        if context is None:
            return False
        # System internal calls or authenticated Admin contexts are allowed
        if context.requester_id == "system":
            return True
        return bool(context.is_authenticated and context.granted_privilege >= PrivilegeLevel.ADMIN)

    @staticmethod
    def enforce(context: RequesterContext | None, action_name: str = "security_scan") -> None:
        """
        Raises PermissionError if requester is not biometrically authorized.
        """
        if not SecurityPrivilegeGate.verify_privilege(context, action_name):
            raise PermissionError(
                f"Biometric authentication required to execute privileged action '{action_name}'."
            )


class SecurityReportGenerator:
    """
    Compiles scan findings and packet telemetry into structured Markdown reports and spoken briefings.
    """

    def generate_report(
        self,
        scan: ScanReport,
        output_dir: Path,
        capture: PacketCaptureResult | None = None,
        lang: str = "vi",
    ) -> dict[str, Any]:
        """
        Builds Markdown report file and returns summary dictionary.
        Returns: {"report_path": Path, "voice_summary": str, "total_hosts": int}
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_file = output_dir / "security_report.md"

        md_content = self.format_markdown_report(scan, capture=capture)
        report_file.write_text(md_content, encoding="utf-8")

        voice_text = self.get_voice_summary(scan, lang=lang)

        return {
            "report_path": report_file,
            "voice_summary": voice_text,
            "total_hosts": scan.total_hosts,
        }

    def format_markdown_report(
        self,
        scan: ScanReport,
        capture: PacketCaptureResult | None = None,
    ) -> str:
        """Formats full Markdown security assessment document."""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(scan.timestamp))

        # Assess risk level
        vuln_count = sum(len(h.vulnerabilities) for h in scan.hosts)
        risk_label = "✅ LOW RISK (SECURE)"
        if vuln_count > 0:
            has_crit = any(any(v.severity == VulnerabilitySeverity.CRITICAL for v in h.vulnerabilities) for h in scan.hosts)
            risk_label = "🚨 CRITICAL RISK" if has_crit else "⚠️ HIGH RISK"

        lines = [
            f"# Security Audit Report for {scan.target}",
            "",
            f"- **Target Subnet**: `{scan.target}`",
            f"- **Scan Timestamp**: `{now_str}`",
            f"- **Duration**: `{scan.duration_s:.2f}s`",
            f"- **Audit Status**: `{scan.status}`",
            f"- **Overall Risk Level**: `{risk_label}`",
            "",
            "## 1. Executive Summary",
            f"- Total Active Hosts: **{scan.total_hosts}**",
            f"- Total Open Ports: **{sum(len(h.open_ports) for h in scan.hosts)}**",
            f"- Discovered Vulnerabilities: **{vuln_count}**",
            "",
            "## 2. Active Host Matrix",
        ]

        for h in scan.hosts:
            ports_str = ", ".join(str(p) for p in h.open_ports) if h.open_ports else "None"
            services_str = ", ".join(f"{p}:{s}" for p, s in h.services.items()) if h.services else "None"
            lines.append(f"- `{h.ip}` ({h.hostname}): Open Ports {h.open_ports}")
            lines.append(f"  - Services: `{services_str}`")

        if capture is not None and capture.packet_count > 0:
            lines.extend([
                "",
                "## 3. Network Packet Telemetry",
                f"- **Capture Interface**: `{capture.interface}`",
                f"- **Packets Analyzed**: `{capture.packet_count}` ({capture.duration_s:.1f}s)",
                f"- **Protocol Distribution**: `TCP: {capture.protocols.get('TCP', 0)}`, `UDP: {capture.protocols.get('UDP', 0)}`, `ICMP: {capture.protocols.get('ICMP', 0)}`",
                f"- **Anomalies Detected**: `{capture.anomalies_detected}`",
            ])

        return "\n".join(lines) + "\n"

    def get_voice_summary(self, scan: ScanReport, lang: str = "vi") -> str:
        """Generates localized spoken executive briefing."""
        is_en = (lang or "vi").lower().startswith("en")
        vuln_count = sum(len(h.vulnerabilities) for h in scan.hosts)

        if is_en:
            if scan.status == "TOOL_NOT_FOUND":
                return "Security scan failed: Nmap binary not found on host."
            if vuln_count > 0:
                return (
                    f"Security Alert: Audit completed for network {scan.target}. "
                    f"Found {scan.total_hosts} active hosts and {vuln_count} potential vulnerabilities. "
                    f"Detailed report saved."
                )
            return (
                f"Security audit completed for network {scan.target}. "
                f"Found {scan.total_hosts} active devices. "
                f"All systems secure."
            )

        # Vietnamese voice summary matching R8, F-25 and test suite assertions
        if scan.status == "TOOL_NOT_FOUND":
            return "Không thể thực hiện quét: Công cụ Nmap chưa được cài đặt trên hệ thống."

        if vuln_count > 0:
            return (
                f"Cảnh báo bảo mật: Đã quét mạng {scan.target}. "
                f"Phát hiện {scan.total_hosts} thiết bị và {vuln_count} lỗ hổng bảo mật. "
                f"Đã lưu báo cáo chi tiết vào file."
            )

        return (
            f"Đã hoàn thành quét bảo mật mạng {scan.target}. "
            f"Phát hiện {scan.total_hosts} thiết bị đang hoạt động. "
            f"Trạng thái an toàn."
        )
