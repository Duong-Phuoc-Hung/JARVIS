#!/usr/bin/env python3
"""
Generate comprehensive test coverage report for JARVIS.
Outputs terminal summary, XML (for CI), and HTML dashboard report.
Target: 80%+ codebase coverage.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    reports_dir = repo_root / "reports" / "coverage"
    reports_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/unit/",
        "--cov=jarvis",
        "--cov-report=term-missing",
        f"--cov-report=html:{reports_dir / 'html'}",
        f"--cov-report=xml:{reports_dir / 'coverage.xml'}",
        "-q",
        "--tb=short",
    ]

    print(f"Running test coverage suite against {repo_root}...")
    cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(cmd, cwd=repo_root, creationflags=cflags)
    if result.returncode == 0:
        print(f"\n[PASS] Coverage report generated successfully at: {reports_dir}")
    else:
        print(f"\n[WARN] Coverage command finished with code: {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
