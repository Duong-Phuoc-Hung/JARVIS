"""
tests/unit/test_build_installer_version.py
============================================
Regression coverage proving the Windows installer (Inno Setup) receives the
canonical JARVIS version rather than owning its own hardcoded literal.

scripts/build_installer.py has no package __init__.py, so it is loaded here
via importlib.util.spec_from_file_location rather than a normal import.
Inno Setup itself is never required to run these tests -- the ISCC.exe
subprocess boundary is mocked; no real installer is built.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_build_installer_module():
    spec = importlib.util.spec_from_file_location(
        "jarvis_test_build_installer_module",
        REPO_ROOT / "scripts" / "build_installer.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build_installer_module():
    return _load_build_installer_module()


def test_get_canonical_version_matches_runtime_version(build_installer_module):
    """scripts/build_installer.py must read the same canonical version as
    jarvis.__version__ (via a lightweight raw-text read, not a full import
    of the jarvis package/its runtime dependencies)."""
    import jarvis

    assert build_installer_module._get_canonical_version() == jarvis.__version__


def test_build_installer_passes_canonical_version_to_iscc(build_installer_module, tmp_path):
    """build_installer() must invoke ISCC.exe with /DAppVersion=<canonical
    version> -- proving the installer's AppVersion (and everything that
    derives from it: output filename, registry Version) is plumbed from the
    single canonical source rather than a second hardcoded literal in
    installer/setup.iss."""
    import jarvis

    fake_inno = tmp_path / "ISCC.exe"
    fake_inno.write_text("", encoding="utf-8")

    with patch.object(build_installer_module, "_find_inno", return_value=fake_inno), \
         patch.object(build_installer_module.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        build_installer_module.build_installer()

    assert mock_run.called, "build_installer() did not invoke subprocess.run for ISCC"
    called_argv = mock_run.call_args[0][0]

    assert called_argv[0] == str(fake_inno)
    assert f"/DAppVersion={jarvis.__version__}" in called_argv


def test_setup_iss_has_no_hardcoded_app_version_default():
    """installer/setup.iss must not declare a hardcoded numeric AppVersion
    fallback -- it must require the value to be supplied externally (via
    ISCC /DAppVersion=..., as build_installer.py now does) and fail clearly
    if it is missing."""
    setup_iss_path = REPO_ROOT / "installer" / "setup.iss"
    text = setup_iss_path.read_text(encoding="utf-8")

    assert '#define AppVersion "' not in text, (
        "installer/setup.iss must not declare a hardcoded #define AppVersion "
        "literal -- it must be supplied via ISCC /DAppVersion=... instead."
    )
    assert "#ifndef AppVersion" in text and "#error" in text, (
        "installer/setup.iss must fail clearly (via #ifndef AppVersion / "
        "#error) when AppVersion is not supplied externally."
    )
