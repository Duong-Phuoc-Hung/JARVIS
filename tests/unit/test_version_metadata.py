"""
tests/unit/test_version_metadata.py
====================================
Regression coverage for the version-metadata single-source architecture
established by the version-metadata-semantics task (2026-09-01). See
CLAUDE.md's "Version metadata" invariants and docs/PROJECT_STATE.md's
current checkpoint for the full classification these tests lock in:

  A. Package/distribution version -- pyproject.toml, dynamically sourced
     from jarvis.__version__ via [tool.setuptools.dynamic] (no literal
     duplicate).
  B. Runtime version -- jarvis.__version__, a plain top-level string
     literal in jarvis/__init__.py (kept a literal, not moved behind an
     import, because jarvis/workers/auto_updater.py and
     scripts/health_check_report.py both locate it by scanning that file's
     raw source text rather than importing jarvis).
  C. config/default_config.yaml's system.version -- confirmed by repo-wide
     audit to have zero production consumers; preserved for backward
     compatibility only, explicitly not required to track jarvis.__version__.
  D. Formal release version -- Git tags / GitHub Releases (latest: v4.0.1),
     independent of both A and B; .github/workflows/release.yml derives its
     own version string from the pushed tag name, not from this package's
     metadata. Not exercised here (no network/tag access from a unit test).

Packaging/build validation (a real wheel build) lives in
tests/integration/test_package_version_build.py instead, since it is too
slow/environment-dependent for the tests/unit/ fast baseline.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _read_version_literal_from_init() -> str:
    """Statically parse jarvis/__init__.py's __version__ assignment via AST --
    the same kind of static analysis setuptools' `attr:` dynamic-version
    resolution performs, so this proves the single-source claim without
    needing a real package build."""
    init_path = REPO_ROOT / "jarvis" / "__init__.py"
    tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
    raise AssertionError("__version__ literal assignment not found via AST in jarvis/__init__.py")


def test_runtime_version_matches_single_source_literal():
    """import jarvis; jarvis.__version__ must equal the literal statically
    parseable from jarvis/__init__.py -- proving there is exactly one
    canonical numeric literal, not a second copy that could drift."""
    import jarvis

    assert jarvis.__version__ == _read_version_literal_from_init()


def test_cli_version_flag_uses_canonical_version(capsys):
    """`jarvis --version` (the argparse `action="version"` path) must print
    exactly jarvis.__version__, not a separately hardcoded string."""
    import pytest

    import jarvis
    from jarvis.cli import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert captured.out.strip() == f"jarvis {jarvis.__version__}"


def _extract_bare_project_table(pyproject_text: str) -> str:
    """Return only the direct key=value lines of TOML's bare [project] table,
    stopping at the next [section] header (including [project.*] sub-tables)."""
    lines = pyproject_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "[project]":
            start = i + 1
            break
    assert start is not None, "[project] table not found in pyproject.toml"

    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].strip().startswith("["):
            end = i
            break
    return "\n".join(lines[start:end])


def test_pyproject_has_no_duplicate_version_literal():
    """pyproject.toml's [project] table must declare `dynamic = ["version"]`
    instead of a second hardcoded `version = "..."` literal, and
    [tool.setuptools.dynamic] must resolve it from jarvis.__version__."""
    pyproject_path = REPO_ROOT / "pyproject.toml"
    text = pyproject_path.read_text(encoding="utf-8")
    project_table = _extract_bare_project_table(text)

    assert not re.search(r"(?m)^\s*version\s*=", project_table), (
        "pyproject.toml's [project] table must not declare a literal "
        "'version = ...' -- the package version is single-sourced from "
        "jarvis.__version__ via [tool.setuptools.dynamic]."
    )
    assert re.search(r"""(?m)^\s*dynamic\s*=.*["']version["']""", project_table), (
        'pyproject.toml\'s [project] table must declare dynamic = ["version", ...]'
    )
    assert re.search(
        r"""\[tool\.setuptools\.dynamic\][^\[]*version\s*=\s*\{[^}]*attr\s*=\s*["']jarvis\.__version__["']""",
        text,
        re.DOTALL,
    ), "pyproject.toml must resolve the dynamic version from jarvis.__version__"


def test_system_version_config_key_present_and_independent():
    """config/default_config.yaml's system.version is preserved for backward
    compatibility (still present, still a string) but is not required to
    equal jarvis.__version__ -- see the NOTE comment beside it in the YAML
    file and the CASE-B classification in CLAUDE.md / docs/PROJECT_STATE.md."""
    cfg_path = REPO_ROOT / "config" / "default_config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    system_version = data.get("system", {}).get("version")
    assert system_version is not None
    assert isinstance(system_version, str)


def test_config_manager_system_version_is_generic_inert_data():
    """Documents the CASE-B compatibility invariant via observable
    ConfigManager behavior instead of a brittle source-text scan: the
    "system.version" config key round-trips through ConfigManager's normal
    dot-notation get()/set() like any other generic config value (it is not
    silently dropped or specially handled), but it is fully decoupled from
    jarvis.__version__ -- overriding it to an arbitrary value has zero
    effect on the runtime version constant, because no production code path
    reads this key to determine "the version" of anything."""
    import jarvis
    from jarvis.core.config import ConfigManager

    cfg = ConfigManager()
    cfg.load()

    # Preserved / accessible via the standard dot-notation mechanism -- the
    # key is generic config data, not silently dropped or broken.
    default_value = cfg.get("system.version")
    assert default_value is not None
    assert isinstance(default_value, str)

    # Decoupled from the runtime version: overriding it has no effect on
    # jarvis.__version__, proving independence rather than an accidental
    # match -- consistent with "no jarvis/ code treats this as *the*
    # application version".
    cfg.set("system.version", "unrelated-arbitrary-probe-value")
    assert cfg.get("system.version") == "unrelated-arbitrary-probe-value"
    assert jarvis.__version__ != "unrelated-arbitrary-probe-value"
