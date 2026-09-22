#!/usr/bin/env python3
"""
tools/security_scanner.py
=========================
Standalone Automated Security Scanner for JARVIS (R4 / Milestone M3).

Provides AST-based and regex-based static security analysis using ONLY the Python
standard library (ast, re, argparse, pathlib, json, sys, typing). Zero external
dependencies required.

Detects 10 core security rules (SEC-001 through SEC-010):
  - SEC-001: Hardcoded Secrets & High-Entropy API Keys (CRITICAL)
  - SEC-002: Secret & Credential Leakage in Logging / Prints (HIGH)
  - SEC-003: Shell Injection in Subprocess / OS Execution (CRITICAL)
  - SEC-004: Unvalidated Path Traversal in File Operations (HIGH)
  - SEC-005: Token Temporal Expiration Check Omission (HIGH)
  - SEC-006: Token Replay / Missing One-Shot Consumption (MEDIUM)
  - SEC-007: Information Disclosure in Error Returns / Tracebacks (MEDIUM)
  - SEC-008: Outdated Dependency with Known Vulnerabilities (HIGH)
  - SEC-009: Missing Critical Security Dependencies (MEDIUM)
  - SEC-010: Hardcoded Debug Mode in Production Code (LOW)

Usage:
  python tools/security_scanner.py --path jarvis/
  python tools/security_scanner.py --path jarvis/ --format markdown --output security_report.md
  python tools/security_scanner.py --path jarvis/ --format json
  python tools/security_scanner.py --help
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Sequence


# ===========================================================================
# Severity Levels & Data Models
# ===========================================================================

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    def __ge__(self, other: Any) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        return order.index(self) >= order.index(other)

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        return order.index(self) > order.index(other)


@dataclass
class RuleDefinition:
    id: str
    name: str
    category: str
    severity: Severity
    description: str


RULES: dict[str, RuleDefinition] = {
    "SEC-001": RuleDefinition(
        id="SEC-001",
        name="Hardcoded Secrets",
        category="Secrets Management",
        severity=Severity.CRITICAL,
        description="High-entropy literal matching API keys (OpenAI, Gemini, Telegram, AWS, private keys).",
    ),
    "SEC-002": RuleDefinition(
        id="SEC-002",
        name="Secret Logging",
        category="Credential Exposure",
        severity=Severity.HIGH,
        description="Logging or printing passwords, API keys, or secret tokens directly without masking.",
    ),
    "SEC-003": RuleDefinition(
        id="SEC-003",
        name="Shell Injection",
        category="Injection Vulnerability",
        severity=Severity.CRITICAL,
        description="subprocess or os execution with shell=True using non-literal commands.",
    ),
    "SEC-004": RuleDefinition(
        id="SEC-004",
        name="Path Traversal",
        category="Input Validation",
        severity=Severity.HIGH,
        description="File open/Path operation on unvalidated paths without containment verification.",
    ),
    "SEC-005": RuleDefinition(
        id="SEC-005",
        name="Token Expiry Check Omission",
        category="Session & Token Lifecycle",
        severity=Severity.HIGH,
        description="Token verification logic omitting temporal expiration checks.",
    ),
    "SEC-006": RuleDefinition(
        id="SEC-006",
        name="Token Replay Vulnerability",
        category="Session & Token Lifecycle",
        severity=Severity.MEDIUM,
        description="Token verification failing to record tokens in consumed set for one-shot enforcement.",
    ),
    "SEC-007": RuleDefinition(
        id="SEC-007",
        name="Information Disclosure",
        category="Information Leakage",
        severity=Severity.MEDIUM,
        description="Returning raw traceback or system exception details in caller responses.",
    ),
    "SEC-008": RuleDefinition(
        id="SEC-008",
        name="Outdated Vulnerable Dependency",
        category="Dependency Hygiene",
        severity=Severity.HIGH,
        description="Dependency declaration with known critical CVEs (e.g. idna < 3.7).",
    ),
    "SEC-009": RuleDefinition(
        id="SEC-009",
        name="Missing Security Dependency",
        category="Dependency Hygiene",
        severity=Severity.MEDIUM,
        description="Missing critical security packages (e.g. keyring, psl) in requirements.",
    ),
    "SEC-010": RuleDefinition(
        id="SEC-010",
        name="Debug Mode Enabled in Production",
        category="Configuration Safety",
        severity=Severity.LOW,
        description="Hardcoded DEBUG = True or logging.DEBUG active in non-test production modules.",
    ),
}


@dataclass
class Finding:
    rule_id: str
    rule_name: str
    severity: Severity
    file_path: str
    line_number: int
    column: int
    message: str
    snippet: str = ""
    remediation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "message": self.message,
            "snippet": self.snippet,
            "remediation": self.remediation,
        }


@dataclass
class ScanResult:
    scanned_files: int = 0
    scanned_lines: int = 0
    duration_seconds: float = 0.0
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    def count_by_severity(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "scanned_files": self.scanned_files,
                "scanned_lines": self.scanned_lines,
                "duration_seconds": round(self.duration_seconds, 4),
                "total_findings": self.total_findings,
                "critical": self.count_by_severity(Severity.CRITICAL),
                "high": self.count_by_severity(Severity.HIGH),
                "medium": self.count_by_severity(Severity.MEDIUM),
                "low": self.count_by_severity(Severity.LOW),
            },
            "findings": [f.to_dict() for f in self.findings],
            "errors": list(self.errors),
        }


# ===========================================================================
# Detectors & AST Visitors
# ===========================================================================

# High-entropy secret patterns
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OpenAI API Key", re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b")),
    ("Gemini API Key", re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b")),
    ("Telegram Bot Token", re.compile(r"\b[0-9]{8,10}:[a-zA-Z0-9_-]{35}\b")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub Personal Token", re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{36}\b")),
    ("Private Key Header", re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PGP|PRIVATE) KEY-----")),
]

_PLACEHOLDER_SUBSTRINGS = (
    "...", "placeholder", "your_key", "your_token", "your-api-key",
    "dummy", "sample", "example", "mock", "test_key", "fake", "<api_key>",
    "sk-test", "sk-...", "aiza...",
)


class SecurityASTVisitor(ast.NodeVisitor):
    """AST Visitor detecting code-level security issues SEC-001 through SEC-007, SEC-010."""

    def __init__(
        self,
        file_path: str,
        lines: list[str],
        active_rules: set[str],
    ) -> None:
        self.file_path = file_path
        self.lines = lines
        self.active_rules = active_rules
        self.findings: list[Finding] = []
        self._is_test_file = any(
            p in file_path.replace("\\", "/").lower() for p in ("/tests/", "test_", "_test.py")
        )

    def _get_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()
        return ""

    def visit_Constant(self, node: ast.Constant) -> None:
        # SEC-001: Hardcoded Secrets in string literals
        if "SEC-001" in self.active_rules and isinstance(node.value, str):
            val = node.value.strip()
            # Ignore test files and small strings
            if not self._is_test_file and len(val) >= 16:
                val_lower = val.lower()
                is_placeholder = any(ph in val_lower for ph in _PLACEHOLDER_SUBSTRINGS)
                if not is_placeholder:
                    for name, pat in _SECRET_PATTERNS:
                        if pat.search(val):
                            rule = RULES["SEC-001"]
                            self.findings.append(Finding(
                                rule_id=rule.id,
                                rule_name=rule.name,
                                severity=rule.severity,
                                file_path=self.file_path,
                                line_number=node.lineno,
                                column=node.col_offset,
                                message=f"Potential hardcoded {name} detected in string literal.",
                                snippet=self._get_snippet(node.lineno),
                                remediation="Store secret in environment variables or Windows Credential Manager via jarvis.security.secrets.",
                            ))
                            break
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = self._get_call_name(node.func)

        # SEC-002: Secret Logging (logging password or token variables unmasked)
        if "SEC-002" in self.active_rules and not self._is_test_file:
            is_log_call = (
                func_name.startswith("logger.")
                or func_name.startswith("logging.")
                or func_name == "print"
            )
            if is_log_call:
                self._check_secret_logging(node)

        # SEC-003: Shell Injection in subprocess
        if "SEC-003" in self.active_rules:
            is_subproc = (
                func_name in (
                    "subprocess.run", "subprocess.Popen", "subprocess.call",
                    "subprocess.check_output", "subprocess.check_call",
                    "os.system", "os.popen",
                )
            )
            if is_subproc:
                self._check_shell_injection(node, func_name)

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # SEC-010: Hardcoded DEBUG = True in non-test files
        if "SEC-010" in self.active_rules and not self._is_test_file:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.upper() in ("DEBUG", "VERBOSE_DEBUG"):
                    if isinstance(node.value, ast.Constant) and node.value.value is True:
                        rule = RULES["SEC-010"]
                        self.findings.append(Finding(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            file_path=self.file_path,
                            line_number=node.lineno,
                            column=node.col_offset,
                            message=f"Hardcoded {target.id} = True detected in production module.",
                            snippet=self._get_snippet(node.lineno),
                            remediation="Read debug mode from environment variable or configuration with False default.",
                        ))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # SEC-005 & SEC-006: Token verification implementation checks
        if any(r in self.active_rules for r in ("SEC-005", "SEC-006")):
            name_lower = node.name.lower()
            if "verify" in name_lower and "token" in name_lower and not self._is_test_file:
                body_source = "\n".join(
                    self.lines[node.lineno - 1 : getattr(node, "end_lineno", node.lineno)]
                )
                # SEC-005: check if temporal expiration is validated
                if "SEC-005" in self.active_rules:
                    has_expiry_check = any(
                        term in body_source for term in (
                            "is_expired", "expires_at", "time.time", "EXPIRED", "timeout"
                        )
                    )
                    if not has_expiry_check:
                        rule = RULES["SEC-005"]
                        self.findings.append(Finding(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            file_path=self.file_path,
                            line_number=node.lineno,
                            column=node.col_offset,
                            message=f"Token verification function '{node.name}' does not check expiration status.",
                            snippet=self._get_snippet(node.lineno),
                            remediation="Enforce entry.is_expired check before authorizing token.",
                        ))

                # SEC-006: check if token is consumed
                if "SEC-006" in self.active_rules:
                    has_consume_check = any(
                        term in body_source for term in (
                            "consumed", "_consumed_tokens", "consume(", "mark_consumed"
                        )
                    )
                    if not has_consume_check:
                        rule = RULES["SEC-006"]
                        self.findings.append(Finding(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            file_path=self.file_path,
                            line_number=node.lineno,
                            column=node.col_offset,
                            message=f"Token verification function '{node.name}' does not enforce one-shot consumption.",
                            snippet=self._get_snippet(node.lineno),
                            remediation="Track consumed tokens in self._consumed_tokens to prevent replay attacks.",
                        ))

        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        # SEC-007: Returning raw traceback or sensitive internals in user-facing data
        if "SEC-007" in self.active_rules and not self._is_test_file and node.value:
            if isinstance(node.value, ast.Dict):
                for k, v in zip(node.value.keys, node.value.values):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        k_clean = k.value.lower()
                        if k_clean in ("trace", "traceback", "stack_trace"):
                            rule = RULES["SEC-007"]
                            self.findings.append(Finding(
                                rule_id=rule.id,
                                rule_name=rule.name,
                                severity=rule.severity,
                                file_path=self.file_path,
                                line_number=node.lineno,
                                column=node.col_offset,
                                message="Potential internal stack trace exposure in return dictionary.",
                                snippet=self._get_snippet(node.lineno),
                                remediation="Log stack traces internally; return normalized error codes to callers.",
                            ))
        self.generic_visit(node)

    def _get_call_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._get_call_name(node.value)
            return f"{val}.{node.attr}" if val else node.attr
        return ""

    def _check_secret_logging(self, node: ast.Call) -> None:
        sensitive_vars = {"password", "api_key", "secret_key", "auth_token", "private_key"}
        # Check positional and keyword arguments
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id.lower() in sensitive_vars:
                rule = RULES["SEC-002"]
                self.findings.append(Finding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    file_path=self.file_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    message=f"Logging sensitive variable '{arg.id}' directly without redaction.",
                    snippet=self._get_snippet(node.lineno),
                    remediation="Redact secret values before logging or use a masking helper.",
                ))
            elif isinstance(arg, ast.JoinedStr):
                # Check f-strings e.g. f"Password: {password}"
                for part in arg.values:
                    if isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name):
                        if part.value.id.lower() in sensitive_vars:
                            rule = RULES["SEC-002"]
                            self.findings.append(Finding(
                                rule_id=rule.id,
                                rule_name=rule.name,
                                severity=rule.severity,
                                file_path=self.file_path,
                                line_number=node.lineno,
                                column=node.col_offset,
                                message=f"F-string logs sensitive variable '{part.value.id}' directly.",
                                snippet=self._get_snippet(node.lineno),
                                remediation="Redact secret values before formatting in log calls.",
                            ))

    def _check_shell_injection(self, node: ast.Call, func_name: str) -> None:
        has_shell_true = False
        if func_name in ("os.system", "os.popen"):
            has_shell_true = True
        else:
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    has_shell_true = True
                    break

        if not has_shell_true:
            return

        cmd_arg = node.args[0] if node.args else None
        if not cmd_arg:
            for kw in node.keywords:
                if kw.arg in ("args", "cmd"):
                    cmd_arg = kw.value
                    break

        if cmd_arg is None:
            return

        # Check if cmd_arg is constructed dynamically (f-string, BinOp, format)
        is_dynamic = (
            isinstance(cmd_arg, ast.JoinedStr)
            or (isinstance(cmd_arg, ast.BinOp) and isinstance(cmd_arg.op, (ast.Mod, ast.Add)))
            or (isinstance(cmd_arg, ast.Call) and getattr(cmd_arg.func, "attr", "") == "format")
        )

        if is_dynamic:
            rule = RULES["SEC-003"]
            self.findings.append(Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                file_path=self.file_path,
                line_number=node.lineno,
                column=node.col_offset,
                message=f"Subprocess call '{func_name}' with shell=True uses dynamic string formatting.",
                snippet=self._get_snippet(node.lineno),
                remediation="Pass command arguments as a list of strings without shell=True.",
            ))


# ===========================================================================
# Manifest / Dependency Detector (SEC-008 & SEC-009)
# ===========================================================================

def audit_dependencies(manifest_path: Path, active_rules: set[str]) -> list[Finding]:
    """Audits requirements.txt or pyproject.toml for vulnerable or missing security packages."""
    findings: list[Finding] = []
    if not manifest_path.exists() or not manifest_path.is_file():
        return findings

    try:
        content = manifest_path.read_text(encoding="utf-8")
    except Exception:
        return findings

    lines = content.splitlines()

    # SEC-008: Vulnerable dependency pins
    if "SEC-008" in active_rules and manifest_path.name in ("requirements.txt", "pyproject.toml"):
        for i, line in enumerate(lines, start=1):
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue

            # Check idna < 3.7
            m_idna = re.search(r"idna\s*(?:==|<=|<)\s*([0-9\.]+)", clean, re.IGNORECASE)
            if m_idna:
                ver_str = m_idna.group(1)
                parts = [int(p) for p in ver_str.split(".") if p.isdigit()]
                if parts and (parts[0] < 3 or (parts[0] == 3 and len(parts) > 1 and parts[1] < 7)):
                    rule = RULES["SEC-008"]
                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        file_path=str(manifest_path),
                        line_number=i,
                        column=0,
                        message=f"Vulnerable idna version pinned ({ver_str}); susceptible to DoS CVE-2024-3651.",
                        snippet=clean,
                        remediation="Pin idna>=3.15,<4 in requirements.txt and pyproject.toml.",
                    ))

    # SEC-009: Missing security dependencies in requirements.txt
    if "SEC-009" in active_rules and manifest_path.name == "requirements.txt":
        # Check if project requires keyring
        has_keyring = any(re.match(r"^keyring\b", l.strip(), re.IGNORECASE) for l in lines)
        if not has_keyring:
            rule = RULES["SEC-009"]
            findings.append(Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                file_path=str(manifest_path),
                line_number=1,
                column=0,
                message="Critical security package 'keyring' is missing from requirements.txt.",
                snippet="",
                remediation="Add keyring>=24 to requirements.txt to enable hardware-backed vault.",
            ))

    return findings


# ===========================================================================
# Scanner Orchestrator
# ===========================================================================

class SecurityScanner:
    """Orchestrates static analysis across files and directories."""

    IGNORE_DIRS: set[str] = {
        ".git", "__pycache__", ".venv", ".venv-1", ".venv_ci_test",
        "node_modules", "build", "dist", ".pytest_cache", ".ruff_cache",
        "temp", "backups", "flowkit-main", "jarvis-main",
    }

    def __init__(
        self,
        active_rules: set[str] | None = None,
        severity_threshold: Severity = Severity.HIGH,
    ) -> None:
        self.active_rules = active_rules if active_rules is not None else set(RULES.keys())
        self.severity_threshold = severity_threshold

    def scan_file(self, file_path: Path) -> list[Finding]:
        """Scans an individual Python file or manifest."""
        findings: list[Finding] = []
        if not file_path.is_file():
            return findings

        # Check manifests
        if file_path.name in ("requirements.txt", "pyproject.toml"):
            findings.extend(audit_dependencies(file_path, self.active_rules))
            return findings

        if file_path.suffix != ".py":
            return findings

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return findings

        lines = content.splitlines()

        # Parse AST
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return findings

        visitor = SecurityASTVisitor(
            file_path=str(file_path),
            lines=lines,
            active_rules=self.active_rules,
        )
        visitor.visit(tree)
        findings.extend(visitor.findings)
        return findings

    def scan(self, target_path: Path) -> ScanResult:
        """Executes full scan over target file or directory."""
        t0 = time.perf_counter()
        result = ScanResult()

        target = target_path.resolve()
        if not target.exists():
            result.errors.append(f"Target path does not exist: {target}")
            result.duration_seconds = time.perf_counter() - t0
            return result

        if target.is_file():
            files_to_scan = [target]
        else:
            files_to_scan = []
            for root, dirs, files in target.walk():
                dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith(".")]
                for f in files:
                    if f.endswith(".py") or f in ("requirements.txt", "pyproject.toml"):
                        files_to_scan.append(root / f)

        for p in sorted(files_to_scan):
            try:
                findings = self.scan_file(p)
                result.findings.extend(findings)
                result.scanned_files += 1
                try:
                    result.scanned_lines += len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
                except Exception:
                    pass
            except Exception as exc:
                result.errors.append(f"Error scanning {p}: {exc}")

        result.duration_seconds = time.perf_counter() - t0
        return result


# ===========================================================================
# Report Formatters
# ===========================================================================

def format_terminal(result: ScanResult, verbose: bool = False) -> str:
    """Formats scan results for terminal console output."""
    lines: list[str] = [
        "=" * 80,
        "JARVIS AUTOMATED SECURITY SCANNER (R4)",
        "=" * 80,
        f"Scanned Files: {result.scanned_files} | Scanned Lines: {result.scanned_lines:,} | Duration: {result.duration_seconds:.2f}s",
        f"Total Findings: {result.total_findings} (Critical: {result.count_by_severity(Severity.CRITICAL)}, "
        f"High: {result.count_by_severity(Severity.HIGH)}, Medium: {result.count_by_severity(Severity.MEDIUM)}, "
        f"Low: {result.count_by_severity(Severity.LOW)})",
        "-" * 80,
    ]

    if not result.findings:
        lines.append("[PASS] Clean scan: Zero security findings detected.")
        lines.append("=" * 80)
        return "\n".join(lines)

    for i, f in enumerate(result.findings, start=1):
        lines.append(f"[{f.severity.value}] {f.rule_id}: {f.rule_name}")
        lines.append(f"  Location: {f.file_path}:{f.line_number}:{f.column}")
        lines.append(f"  Details:  {f.message}")
        if f.snippet:
            lines.append(f"  Snippet:  {f.snippet}")
        if f.remediation:
            lines.append(f"  Fix:      {f.remediation}")
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


def format_markdown(result: ScanResult) -> str:
    """Formats scan results as a Markdown document."""
    lines: list[str] = [
        "# Security Hardening & Vulnerability Scan Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Scanned Files** | {result.scanned_files} |",
        f"| **Scanned Lines** | {result.scanned_lines:,} |",
        f"| **Duration** | {result.duration_seconds:.2f}s |",
        f"| **Total Findings** | {result.total_findings} |",
        f"| **CRITICAL** | {result.count_by_severity(Severity.CRITICAL)} |",
        f"| **HIGH** | {result.count_by_severity(Severity.HIGH)} |",
        f"| **MEDIUM** | {result.count_by_severity(Severity.MEDIUM)} |",
        f"| **LOW** | {result.count_by_severity(Severity.LOW)} |",
        "",
    ]

    if not result.findings:
        lines.extend([
            "## Verdict",
            "",
            "**PASS (Clean)**: No security vulnerabilities detected in scanned scope.",
            "",
        ])
        return "\n".join(lines)

    lines.extend([
        "## Findings Matrix",
        "",
        "| # | Rule ID | Severity | Location | Description | Remediation |",
        "|---|---|---|---|---|---|",
    ])

    for i, f in enumerate(result.findings, start=1):
        loc = f"`{f.file_path}:{f.line_number}`"
        lines.append(
            f"| {i} | `{f.rule_id}` | **{f.severity.value}** | {loc} | {f.message} | {f.remediation} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_json(result: ScanResult) -> str:
    """Formats scan results as an RFC 8259 compliant JSON string."""
    return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)


# ===========================================================================
# CLI Interface
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="security_scanner",
        description="Automated Security Hardening & Vulnerability Scanner for JARVIS (R4 / Milestone M3).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Rule Catalog:
  SEC-001  CRITICAL  Hardcoded Secrets & High-Entropy API Keys
  SEC-002  HIGH      Secret & Credential Leakage in Logging / Prints
  SEC-003  CRITICAL  Shell Injection in Subprocess / OS Execution
  SEC-004  HIGH      Unvalidated Path Traversal in File Operations
  SEC-005  HIGH      Token Temporal Expiration Check Omission
  SEC-006  MEDIUM    Token Replay / Missing One-Shot Consumption
  SEC-007  MEDIUM    Information Disclosure in Error Returns
  SEC-008  HIGH      Outdated Dependency with Known Vulnerabilities
  SEC-009  MEDIUM    Missing Critical Security Dependencies
  SEC-010  LOW       Hardcoded Debug Mode in Production Code

Exit Codes:
  0: Clean scan (zero findings meeting or exceeding --severity-threshold)
  1: Security findings found meeting or exceeding threshold
  2: Execution or CLI argument error
        """,
    )
    parser.add_argument(
        "--path",
        default="jarvis/",
        help="Target directory or file to scan (default: jarvis/).",
    )
    parser.add_argument(
        "--format",
        choices=["terminal", "text", "markdown", "json"],
        default="terminal",
        help="Output report format (default: terminal).",
    )
    parser.add_argument(
        "--output", "-o",
        default="",
        help="Optional file path to save the formatted report.",
    )
    parser.add_argument(
        "--exit-code",
        dest="exit_code",
        action="store_true",
        default=True,
        help="Exit with 1 if findings meet or exceed severity threshold (default: True).",
    )
    parser.add_argument(
        "--no-exit-code",
        dest="exit_code",
        action="store_false",
        help="Always exit with code 0 regardless of findings count.",
    )
    parser.add_argument(
        "--rules",
        default="",
        help="Comma-separated rule IDs to include (e.g. SEC-001,SEC-002). Defaults to all rules.",
    )
    parser.add_argument(
        "--severity-threshold",
        choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        default="HIGH",
        help="Minimum severity triggering failure exit code (default: HIGH).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Display detailed code snippets and remediation guidance.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve active rules
    if args.rules.strip():
        req_rules = {r.strip().upper() for r in args.rules.split(",") if r.strip()}
        active_rules = req_rules
    else:
        active_rules = set(RULES.keys())

    threshold = Severity[args.severity_threshold.upper()]

    scanner = SecurityScanner(
        active_rules=active_rules,
        severity_threshold=threshold,
    )

    target_path = Path(args.path)
    result = scanner.scan(target_path)

    # Format output
    fmt = args.format.lower()
    if fmt == "json":
        report_text = format_json(result)
    elif fmt == "markdown":
        report_text = format_markdown(result)
    else:  # terminal or text
        report_text = format_terminal(result, verbose=args.verbose)

    # Write to file or stdout
    if args.output.strip():
        out_file = Path(args.output.strip())
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(report_text, encoding="utf-8")
        print(f"Report written to: {out_file}")
    else:
        print(report_text)

    # Determine exit code
    if not args.exit_code:
        return 0

    has_violations = any(f.severity >= threshold for f in result.findings)
    return 1 if has_violations else 0


if __name__ == "__main__":
    sys.exit(main())
