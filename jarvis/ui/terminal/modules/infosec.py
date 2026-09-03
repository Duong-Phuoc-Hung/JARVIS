"""
jarvis/ui/terminal/modules/infosec.py
========================================
InfoSec Auditing module adapter.

Scan scope is unchanged and enforced entirely by jarvis.security.scanner's
own validate_scan_target()/ALLOWED_SCAN_SUPERNETS -- this module never
reimplements or widens that allowlist, and never resolves hostnames.

Known truthfulness gap (audited during this task, not fixed here per
explicit scope instructions): jarvis.security.scanner.PacketCapture.
capture_packets() fabricates a fixed 70/20/10 TCP/UDP/ICMP protocol split
on BOTH the success and exception paths (scanner.py's _build_capture_result,
called unconditionally, never actually parsing tshark's real output) and
reports status="SUCCESS" even when the underlying tshark invocation failed.
This module therefore never calls capture_packets() and never presents its
output as real evidence -- see _packet_capture() below.
"""
from __future__ import annotations

from jarvis.core.models import RequesterContext
from jarvis.security.report import SecurityReportGenerator
from jarvis.security.scanner import (
    NetworkScanner,
    resolve_nmap_binary,
    resolve_tshark_binary,
    validate_scan_target,
)
from jarvis.ui.terminal.context import TerminalContext, run_timed
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.theme import StatusLevel

MODULE = "INFOSEC"

_SCAN_STATUS_MAP = {
    "SUCCESS": StatusLevel.PASS,
    "TOOL_NOT_FOUND": StatusLevel.OFFLINE,
    "TARGET_REJECTED": StatusLevel.BLOCKED,
    "PERMISSION_DENIED": StatusLevel.BLOCKED,
    "TIMEOUT": StatusLevel.LIMITED,
}


def _tools_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        nmap = resolve_nmap_binary(None)
        tshark = resolve_tshark_binary(None)
        fields = [
            ("Nmap", "AVAILABLE" if nmap else "OFFLINE"),
            ("TShark", "AVAILABLE" if tshark else "OFFLINE"),
        ]
        if nmap and tshark:
            status = StatusLevel.AVAILABLE
        elif nmap or tshark:
            status = StatusLevel.LIMITED
        else:
            status = StatusLevel.OFFLINE
        return ActionOutcome(status=status, title="Security Tools Status", fields=fields)
    return run_timed(body)


def _validate_target_prompt(ctx: TerminalContext) -> ActionOutcome:
    target = ctx.console.read_line("Enter target IP or CIDR (RFC1918 private ranges only): ")
    if not target:
        return ActionOutcome(status=StatusLevel.SKIPPED, title="Validate Scan Target",
                              detail_lines=["No target entered."])
    return _validate_target(ctx, target)


def _validate_target(ctx: TerminalContext, target: str) -> ActionOutcome:
    def body() -> ActionOutcome:
        allowed, reason = validate_scan_target(target)
        if allowed:
            ctx.state["infosec_target"] = target
            return ActionOutcome(
                status=StatusLevel.PASS, title="Validate Scan Target",
                fields=[("Target", target), ("Result", "ALLOWED")],
            )
        ctx.state.pop("infosec_target", None)
        return ActionOutcome(
            status=StatusLevel.BLOCKED, title="Validate Scan Target",
            fields=[("Target", target), ("Result", "REJECTED")],
            error_reason=reason,
        )
    return run_timed(body)


def _lan_scan(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        target = ctx.state.get("infosec_target")
        if not target:
            return ActionOutcome(
                status=StatusLevel.SKIPPED, title="LAN Host / Port Scan",
                detail_lines=["No target selected. Use 'Validate Scan Target' first."],
            )
        scanner = NetworkScanner()
        report = scanner.scan_subnet(target, context=RequesterContext.system())
        ctx.state["infosec_last_scan"] = report
        status = _SCAN_STATUS_MAP.get(report.status, StatusLevel.ERROR)
        fields = [
            ("Target", report.target),
            ("Hosts Found", str(report.total_hosts)),
            ("Scan Status", report.status),
        ]
        detail = [] if not report.error_message else [f"Reason: {report.error_message}"]
        return ActionOutcome(status=status, title="LAN Host / Port Scan", fields=fields,
                              detail_lines=detail, structured_data={"target": report.target,
                                                                     "total_hosts": report.total_hosts,
                                                                     "status": report.status})
    return run_timed(body)


def _packet_capture(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        found = resolve_tshark_binary(None)
        detail = [
            "This build's packet-capture backend (jarvis.security.scanner.PacketCapture) "
            "does not parse real tshark output -- it synthesizes a fixed protocol-distribution "
            "estimate regardless of whether capture succeeded. To avoid showing fabricated "
            "evidence, this screen intentionally does not invoke it.",
        ]
        fields = [("TShark Binary", "AVAILABLE" if found else "OFFLINE"),
                  ("Real Packet Evidence", "NOT AVAILABLE")]
        return ActionOutcome(status=StatusLevel.LIMITED, title="Packet Capture", fields=fields,
                              detail_lines=detail)
    return run_timed(body)


def _security_report(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        scan = ctx.state.get("infosec_last_scan")
        if scan is None:
            return ActionOutcome(status=StatusLevel.SKIPPED, title="Security Report",
                                  detail_lines=["No scan has been run this session. Run 'LAN Host / Port Scan' first."])
        generator = SecurityReportGenerator()
        markdown = generator.format_markdown_report(scan)
        voice_summary = generator.get_voice_summary(scan, lang="vi")
        return ActionOutcome(
            status=StatusLevel.PASS, title="Security Report",
            fields=[("Target", scan.target), ("Hosts", str(scan.total_hosts))],
            detail_lines=[voice_summary],
            structured_data={"markdown_report": markdown},
        )
    return run_timed(body)


def build_menu(ctx: TerminalContext) -> MenuScreen:
    has_target = bool(ctx.state.get("infosec_target"))
    actions = [
        MenuAction(id="infosec_tools", key="1", label="Security Tools Status",
                   description="Nmap / TShark availability", handler=lambda: _tools_status(ctx),
                   safe_for_batch=True, help_text="Checks for the nmap and tshark binaries on PATH."),
        MenuAction(id="infosec_validate", key="2", label="Validate Scan Target",
                   description="Check a target against the approved RFC1918 allowlist",
                   handler=lambda: _validate_target_prompt(ctx), requires_target=True, read_only=True,
                   safe_for_batch=False,
                   help_text="Validates a target IP/CIDR against 127.0.0.0/8, 10.0.0.0/8, "
                              "172.16.0.0/12, 192.168.0.0/16. Public targets are always rejected."),
        MenuAction(id="infosec_scan", key="3", label="LAN Host / Port Scan",
                   description="Nmap discovery scan (requires a validated target)",
                   handler=lambda: _lan_scan(ctx), read_only=True,
                   safe_for_batch=has_target,
                   available=True,
                   help_text="Runs an Nmap scan against the currently validated target only."),
        MenuAction(id="infosec_capture", key="4", label="Packet Capture",
                   description="TShark availability (real capture evidence not yet trustworthy)",
                   handler=lambda: _packet_capture(ctx), safe_for_batch=False,
                   help_text="Reports TShark availability only -- does not run capture_packets(), "
                              "which is known to fabricate protocol statistics on failure."),
        MenuAction(id="infosec_report", key="5", label="Security Report",
                   description="Generate a report from the last scan this session",
                   handler=lambda: _security_report(ctx), safe_for_batch=False,
                   help_text="Builds a Markdown security report from the most recent scan result."),
    ]
    return MenuScreen(
        id="infosec", title="INFOSEC AUDITING", breadcrumb=["MAIN", "INFOSEC"],
        actions=actions, batch_label="Run All Applicable Safe Checks",
        help_intro="LAN-only scanning (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16). "
                   "Public/external scanning is forbidden and cannot be selected here.",
    )
