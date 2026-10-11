"""
tests/unit/test_ci_coverage_gate.py
===================================
TDD Unit test suite for Task 11: CI-COVERAGE-GATE-FIX1.
Enforces that GitHub Actions Main CI pipeline (.github/workflows/ci.yml):
1. Includes an automated security scanner job (Bandit AST / dependency audit / security probes).
2. Executes non-unit regression test suites (tests/integration/ and core boundary test suites).
3. Connects security and integration jobs into the final pipeline summary and failure gate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


class TestCICoverageGate:
    """Verifies CI workflow definitions satisfy engineering and security standards."""

    @pytest.fixture
    def ci_config(self) -> dict[str, Any]:
        root_dir = Path(__file__).parents[2]
        ci_path = root_dir / ".github" / "workflows" / "ci.yml"
        assert ci_path.exists(), "ci.yml must exist"
        content = ci_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)
        return parsed

    def test_ci_includes_security_scanner_job(self, ci_config: dict[str, Any]) -> None:
        """
        Main CI must define a dedicated security scanner job (e.g. security_scan)
        running automated security checks (bandit / security probes / audit).
        """
        jobs = ci_config.get("jobs", {})
        assert "security_scan" in jobs, "CI workflow must include a 'security_scan' job."
        sec_job = jobs["security_scan"]
        steps_str = yaml.dump(sec_job.get("steps", []))
        # Must execute security scanner / audit
        assert ("bandit" in steps_str or "security" in steps_str.lower()), (
            "security_scan job must invoke security scanning tools or tests."
        )

    def test_ci_includes_non_unit_regression_tests(self, ci_config: dict[str, Any]) -> None:
        """
        Main CI must execute regression tests outside tests/unit/ (such as tests/integration/).
        """
        jobs = ci_config.get("jobs", {})
        integration_job = jobs.get("integration_regression") or jobs.get("integration")
        assert integration_job is not None, (
            "CI workflow must include an 'integration_regression' job."
        )
        steps_str = yaml.dump(integration_job.get("steps", []))
        assert "tests/integration" in steps_str, (
            "integration_regression job must execute tests under tests/integration/."
        )

    def test_ci_summary_gates_on_security_and_integration(self, ci_config: dict[str, Any]) -> None:
        """
        The pipeline summary job must depend on both security_scan and integration_regression,
        failing the pipeline if either job fails.
        """
        jobs = ci_config.get("jobs", {})
        summary_job = jobs.get("summary", {})
        needs = summary_job.get("needs", [])
        assert "security_scan" in needs, "Summary job must depend on 'security_scan'."
        assert ("integration_regression" in needs or "integration" in needs), (
            "Summary job must depend on integration regression job."
        )

    def test_ci_workflow_step_failure_propagation(self, ci_config: dict[str, Any]) -> None:
        """
        Verifies that pytest and bandit execution steps in ci.yml check LASTEXITCODE
        to ensure failure propagation across job gates.
        """
        jobs = ci_config.get("jobs", {})

        # Check 'test' job
        test_job = jobs.get("test", {})
        test_steps = test_job.get("steps", [])
        run_unit_step = next(s for s in test_steps if s.get("name") == "Run unit tests")
        assert "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" in run_unit_step["run"], (
            "ci.yml 'Run unit tests' step must check $LASTEXITCODE after Tee-Object."
        )

        # Check 'security_scan' job bandit step
        sec_job = jobs.get("security_scan", {})
        sec_steps = sec_job.get("steps", [])
        bandit_step = next(s for s in sec_steps if "Bandit" in s.get("name", ""))
        assert "exit $LASTEXITCODE" in bandit_step["run"] or "exit 1" in bandit_step["run"], (
            "ci.yml Bandit step must exit non-zero when security issues are found."
        )

        # Check 'integration_regression' job pytest step
        int_job = jobs.get("integration_regression", {})
        int_steps = int_job.get("steps", [])
        int_pytest_step = next(s for s in int_steps if s.get("name") == "Run integration test suite")
        assert "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" in int_pytest_step["run"], (
            "ci.yml 'Run integration test suite' step must check $LASTEXITCODE."
        )

    def test_ci_workflow_referenced_paths_exist(self, ci_config: dict[str, Any]) -> None:
        """
        Parses all pytest and script targets referenced in ci.yml run blocks
        and asserts that every single referenced local path exists in the repository.
        """
        import re
        root_dir = Path(__file__).parents[2]
        ci_path = root_dir / ".github" / "workflows" / "ci.yml"
        content = ci_path.read_text(encoding="utf-8")

        # Find pytest targets like tests/...
        pytest_matches = re.findall(r"tests/[a-zA-Z0-9_\-/\.]+", content)
        assert len(pytest_matches) > 0, "ci.yml must reference pytest test paths"
        for p in pytest_matches:
            target = root_dir / p
            assert target.exists(), f"Referenced path '{p}' in ci.yml does not exist in repository!"



