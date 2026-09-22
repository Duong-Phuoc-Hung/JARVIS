"""
tests/unit/test_security_scanner_tool.py
========================================
Unit tests verifying tools/security_scanner.py functionality, rule detections,
CLI flags, report formats, and exit code policies (R4 / Milestone M3).
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any
import unittest

from tools.security_scanner import (
    RULES,
    SecurityScanner,
    Severity,
    audit_dependencies,
    format_json,
    format_markdown,
    format_terminal,
    main,
)


class TestSecurityScannerTool(unittest.TestCase):
    """Test suite for tools/security_scanner.py standalone CLI and AST detection rules."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.scratch = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_help_flag_exits_clean(self) -> None:
        """Verify that running --help exits with code 0."""
        with self.assertRaises(SystemExit) as ctx:
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_clean_scan_of_jarvis_codebase_exits_zero(self) -> None:
        """Verify that scanning the production jarvis/ directory produces 0 violations and exits 0."""
        code = main(["--path", "jarvis/", "--format", "terminal"])
        self.assertEqual(code, 0, "Security scanner reported unexpected findings on clean jarvis/ codebase.")

    def test_sec_001_hardcoded_secret_detection(self) -> None:
        """Verify SEC-001 detects production API keys and private key blocks."""
        vuln_file = self.scratch / "vuln_secrets.py"
        vuln_file.write_text(
            '# Production file with secret\n'
            'API_KEY = "AIzaSyD9xK81q9Z2w4e5r6t7y8u9i0o1p2a3s4d"\n'
            'def get_auth():\n'
            '    return API_KEY\n',
            encoding="utf-8",
        )

        scanner = SecurityScanner(active_rules={"SEC-001"})
        result = scanner.scan(vuln_file)

        self.assertEqual(result.total_findings, 1)
        finding = result.findings[0]
        self.assertEqual(finding.rule_id, "SEC-001")
        self.assertEqual(finding.severity, Severity.CRITICAL)
        self.assertIn("Gemini API Key", finding.message)

    def test_sec_002_secret_logging_detection(self) -> None:
        """Verify SEC-002 detects unmasked logging of sensitive credentials."""
        vuln_file = self.scratch / "vuln_logging.py"
        vuln_file.write_text(
            'import logging\n'
            'logger = logging.getLogger(__name__)\n'
            'def login(password, user):\n'
            '    logger.info("Login attempt for %s with password %s", user, password)\n',
            encoding="utf-8",
        )

        scanner = SecurityScanner(active_rules={"SEC-002"})
        result = scanner.scan(vuln_file)

        self.assertGreaterEqual(result.total_findings, 1)
        finding = result.findings[0]
        self.assertEqual(finding.rule_id, "SEC-002")
        self.assertEqual(finding.severity, Severity.HIGH)
        self.assertIn("password", finding.message)

    def test_sec_003_shell_injection_detection(self) -> None:
        """Verify SEC-003 detects subprocess calls with shell=True using dynamic formatting."""
        vuln_file = self.scratch / "vuln_shell.py"
        vuln_file.write_text(
            'import subprocess\n'
            'def run_user_cmd(cmd_str):\n'
            '    subprocess.run(f"echo {cmd_str}", shell=True)\n',
            encoding="utf-8",
        )

        scanner = SecurityScanner(active_rules={"SEC-003"})
        result = scanner.scan(vuln_file)

        self.assertEqual(result.total_findings, 1)
        finding = result.findings[0]
        self.assertEqual(finding.rule_id, "SEC-003")
        self.assertEqual(finding.severity, Severity.CRITICAL)
        self.assertIn("shell=True", finding.message)

    def test_sec_005_and_006_token_lifecycle_defects(self) -> None:
        """Verify SEC-005 and SEC-006 detect missing expiry checks and missing consumption tracking."""
        vuln_file = self.scratch / "vuln_tokens.py"
        vuln_file.write_text(
            'class VulnerableAuth:\n'
            '    def verify_token(self, token, action):\n'
            '        if token == "valid":\n'
            '            return True\n'
            '        return False\n',
            encoding="utf-8",
        )

        scanner = SecurityScanner(active_rules={"SEC-005", "SEC-006"})
        result = scanner.scan(vuln_file)

        rule_ids = {f.rule_id for f in result.findings}
        self.assertIn("SEC-005", rule_ids)
        self.assertIn("SEC-006", rule_ids)

    def test_sec_010_debug_mode_detection(self) -> None:
        """Verify SEC-010 flags hardcoded DEBUG = True in non-test modules."""
        vuln_file = self.scratch / "prod_config.py"
        vuln_file.write_text(
            '# Production config\n'
            'DEBUG = True\n'
            'APP_NAME = "JARVIS"\n',
            encoding="utf-8",
        )

        scanner = SecurityScanner(active_rules={"SEC-010"})
        result = scanner.scan(vuln_file)

        self.assertEqual(result.total_findings, 1)
        self.assertEqual(result.findings[0].rule_id, "SEC-010")
        self.assertEqual(result.findings[0].severity, Severity.LOW)

    def test_output_formats_markdown_and_json(self) -> None:
        """Verify JSON and Markdown report formatters generate valid structured content."""
        vuln_file = self.scratch / "sample_vuln.py"
        vuln_file.write_text(
            'import os\n'
            'def exec_cmd(c):\n'
            '    os.system(f"echo {c}")\n',
            encoding="utf-8",
        )

        scanner = SecurityScanner(active_rules={"SEC-003"})
        result = scanner.scan(vuln_file)

        # JSON format
        json_str = format_json(result)
        data = json.loads(json_str)
        self.assertIn("summary", data)
        self.assertIn("findings", data)
        self.assertEqual(data["summary"]["critical"], 1)

        # Markdown format
        md_str = format_markdown(result)
        self.assertIn("# Security Hardening & Vulnerability Scan Report", md_str)
        self.assertIn("| Metric | Value |", md_str)
        self.assertIn("SEC-003", md_str)

        # Terminal format
        term_str = format_terminal(result)
        self.assertIn("JARVIS AUTOMATED SECURITY SCANNER", term_str)
        self.assertIn("SEC-003", term_str)

    def test_cli_exit_code_policy_and_threshold(self) -> None:
        """Verify exit code policy: 1 on violations >= threshold, 0 on --no-exit-code or clean."""
        vuln_file = self.scratch / "test_exit.py"
        vuln_file.write_text(
            'import subprocess\n'
            'def run_it(cmd):\n'
            '    subprocess.run(f"cat {cmd}", shell=True)\n',
            encoding="utf-8",
        )

        # 1. With exit-code default (True), should return 1
        code_fail = main(["--path", str(vuln_file), "--rules", "SEC-003"])
        self.assertEqual(code_fail, 1)

        # 2. With --no-exit-code, should return 0
        code_suppressed = main(["--path", str(vuln_file), "--rules", "SEC-003", "--no-exit-code"])
        self.assertEqual(code_suppressed, 0)

        # 3. With severity threshold higher than finding (e.g. finding is MEDIUM, threshold is CRITICAL)
        code_threshold = main([
            "--path", str(vuln_file),
            "--rules", "SEC-010",
            "--severity-threshold", "CRITICAL",
        ])
        self.assertEqual(code_threshold, 0)


if __name__ == "__main__":
    unittest.main()
