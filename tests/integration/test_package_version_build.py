"""
tests/integration/test_package_version_build.py
=================================================
Verifies the built wheel's distribution metadata version matches the
canonical runtime jarvis.__version__ single source (see
[tool.setuptools.dynamic] in pyproject.toml, and jarvis/__init__.py).

Deliberately NOT part of tests/unit/ (and thus not part of the CI Unit Tests
job's fast baseline): it shells out to build a real wheel via setuptools,
which is slower and more environment-dependent than the rest of the fast
suite -- consistent with tests/integration/test_sandbox_os_boundaries.py's
existing precedent for this directory.

Run explicitly:
    python -m pytest tests/integration/test_package_version_build.py -v
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.integration


def test_built_wheel_version_matches_runtime_version():
    """Build jarvis-assistant as a real wheel (no network needed --
    --no-build-isolation reuses this environment's already-installed
    setuptools/wheel) and assert its filename-embedded distribution version
    equals jarvis.__version__."""
    import jarvis

    expected_version = jarvis.__version__

    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis-wheel-build-"))
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pip", "wheel", ".",
                "--no-deps", "--no-build-isolation",
                "-w", str(tmp_dir),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, (
            f"wheel build failed (exit {result.returncode}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        wheels = list(tmp_dir.glob("jarvis_assistant-*.whl"))
        assert len(wheels) == 1, f"Expected exactly one built wheel, found: {wheels}"

        wheel_name = wheels[0].name
        match = re.match(r"jarvis_assistant-([^-]+)-", wheel_name)
        assert match is not None, f"Could not parse version from wheel filename: {wheel_name}"

        wheel_version = match.group(1)
        assert wheel_version == expected_version, (
            f"Built wheel version {wheel_version!r} does not match "
            f"jarvis.__version__ {expected_version!r}"
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
