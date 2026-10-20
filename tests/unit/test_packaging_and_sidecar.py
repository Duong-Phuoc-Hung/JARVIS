"""
tests/unit/test_packaging_and_sidecar.py
=========================================
Unit and regression test suite for Milestone 5:
- Entrypoints: `main_tray` in `jarvis.__main__` and `--tray` flag in `jarvis.cli`
- Sidecar Automation: `sidecar.json` structure, JSON schema, Asia/Ho_Chi_Minh 09:00 AM schedule, tasks, and fail-closed telemetry
- Standalone Packaging: `scripts/build_standalone_package.py` argument parsing, environment checks, and `--onedir` bundle specification
"""
from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ===========================================================================
# 1. Entrypoints & CLI Arguments Tests
# ===========================================================================

def test_main_tray_exists_in_dunder_all():
    """Verify main_tray is exported in jarvis.__main__.__all__."""
    import jarvis.__main__ as main_mod

    assert hasattr(main_mod, "__all__"), "jarvis.__main__ must define __all__"
    assert "main_tray" in main_mod.__all__, "main_tray must be exported in __all__"
    assert "main" in main_mod.__all__, "main must be exported in __all__"


def test_main_tray_import_and_callable():
    """Verify main_tray can be imported and is a callable function."""
    from jarvis.__main__ import main_tray

    assert callable(main_tray), "main_tray must be callable"


def test_main_tray_delegates_to_cli_main_with_tray_arg():
    """Verify main_tray() passes ['--tray'] to jarvis.cli.main."""
    from jarvis.__main__ import main_tray

    with patch("jarvis.__main__.main", return_value=0) as mock_cli_main:
        exit_code = main_tray([])
        assert exit_code == 0
        mock_cli_main.assert_called_once_with(["--tray"])


def test_main_tray_forwards_custom_arguments():
    """Verify main_tray forwards custom command-line arguments alongside --tray."""
    from jarvis.__main__ import main_tray

    with patch("jarvis.__main__.main", return_value=0) as mock_cli_main:
        exit_code = main_tray(["--config", "my_config.yaml", "--log-level", "DEBUG"])
        assert exit_code == 0
        called_args = mock_cli_main.call_args[0][0]
        assert "--tray" in called_args
        assert "--config" in called_args
        assert "my_config.yaml" in called_args
        assert "--log-level" in called_args
        assert "DEBUG" in called_args


def test_cli_build_parser_has_top_level_tray_flag():
    """Verify build_parser accepts --tray at top level."""
    from jarvis.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["--tray"])
    assert getattr(args, "tray", False) is True
    assert args.command is None


def test_cli_build_parser_run_subcommand_has_tray_flag():
    """Verify build_parser accepts --tray in the run subcommand."""
    from jarvis.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["run", "--tray"])
    assert getattr(args, "tray", False) is True
    assert args.command == "run"


def test_cli_main_tray_forces_headless_false():
    """Verify that --tray forces headless=False on JarvisApp initialization."""
    from jarvis.cli import SingleInstanceResult, main

    mock_app_instance = MagicMock()
    mock_app_instance.run.return_value = 0

    with patch("jarvis.cli._acquire_single_instance_mutex", return_value=SingleInstanceResult.ACQUIRED), \
         patch("jarvis.cli._release_single_instance_mutex"), \
         patch("jarvis.core.app.JarvisApp", return_value=mock_app_instance) as mock_app_cls:

        exit_code = main(["--tray"])
        assert exit_code == 0
        mock_app_cls.assert_called_once()
        _, kwargs = mock_app_cls.call_args
        assert kwargs.get("headless") is False


def test_cli_main_tray_overrides_headless_flag():
    """Verify that specifying --tray overrules --headless."""
    from jarvis.cli import SingleInstanceResult, main

    mock_app_instance = MagicMock()
    mock_app_instance.run.return_value = 0

    with patch("jarvis.cli._acquire_single_instance_mutex", return_value=SingleInstanceResult.ACQUIRED), \
         patch("jarvis.cli._release_single_instance_mutex"), \
         patch("jarvis.core.app.JarvisApp", return_value=mock_app_instance) as mock_app_cls:

        exit_code = main(["run", "--headless", "--tray"])
        assert exit_code == 0
        mock_app_cls.assert_called_once()
        _, kwargs = mock_app_cls.call_args
        assert kwargs.get("headless") is False


# ===========================================================================
# 2. Sidecar Automation Configuration Tests
# ===========================================================================

@pytest.fixture(scope="module")
def sidecar_config() -> dict:
    """Load and parse root sidecar.json."""
    sidecar_path = REPO_ROOT / "sidecar.json"
    assert sidecar_path.is_file(), f"sidecar.json must exist at repository root: {sidecar_path}"
    content = sidecar_path.read_text(encoding="utf-8")
    return json.loads(content)


def test_sidecar_json_schema_metadata(sidecar_config: dict):
    """Verify sidecar.json schema headers and enable state."""
    assert "$schema" in sidecar_config
    assert "version" in sidecar_config
    assert sidecar_config.get("enabled") is True


def test_sidecar_json_timezone_vietnam(sidecar_config: dict):
    """Verify sidecar.json specifies Asia/Ho_Chi_Minh timezone."""
    assert sidecar_config.get("timezone") == "Asia/Ho_Chi_Minh"


def test_sidecar_json_schedule_09_am(sidecar_config: dict):
    """Verify sidecar.json schedule is configured for 09:00 AM daily."""
    schedule = sidecar_config.get("schedule", {})
    assert schedule.get("cron") == "0 9 * * *"
    assert schedule.get("target_time") in ("09:00:00", "09:00")
    assert schedule.get("tolerance_window_minutes") is not None
    assert schedule.get("catch_up_if_missed") is True


def test_sidecar_json_three_core_tasks(sidecar_config: dict):
    """Verify the three required tasks exist with proper IDs and actions."""
    tasks = sidecar_config.get("tasks", [])
    assert len(tasks) >= 3, "sidecar.json must define at least 3 tasks"

    task_map = {t["id"]: t for t in tasks if "id" in t}

    # 1. autonomous_tech_radar_sync
    assert "autonomous_tech_radar_sync" in task_map
    radar_task = task_map["autonomous_tech_radar_sync"]
    assert radar_task.get("action") == "jarvis.web.tech_radar.TechRadarAggregator.sync_all"
    assert radar_task.get("enabled") is True
    assert "arxiv" in radar_task.get("parameters", {}).get("sources", [])
    assert "github_trending" in radar_task.get("parameters", {}).get("sources", [])

    # 2. system_health_check
    assert "system_health_check" in task_map
    health_task = task_map["system_health_check"]
    assert health_task.get("action") == "system_health_check"
    assert health_task.get("enabled") is True
    health_params = health_task.get("parameters", {})
    assert health_params.get("verify_database_integrity") is True
    assert health_params.get("verify_vector_store_status") is True
    assert health_params.get("verify_disk_persistence_health") is True

    # 3. learning_vault_consolidation
    assert "learning_vault_consolidation" in task_map
    vault_task = task_map["learning_vault_consolidation"]
    assert vault_task.get("action") == "learning_vault_consolidation"
    assert vault_task.get("enabled") is True
    vault_params = vault_task.get("parameters", {})
    assert vault_params.get("consolidate_blips") is True
    assert vault_params.get("memory_graph_sync") is True


def test_sidecar_json_fail_closed_error_handling(sidecar_config: dict):
    """Verify sidecar.json configures fail-closed error handling and logging."""
    error_cfg = sidecar_config.get("error_handling", {})
    assert error_cfg.get("policy") == "fail_closed"
    assert error_cfg.get("notify_on_failure") is True

    telemetry_cfg = sidecar_config.get("telemetry", {})
    assert "sidecar.log" in telemetry_cfg.get("log_file", "")


# ===========================================================================
# 3. Standalone Packaging Script Tests
# ===========================================================================

def _load_packaging_module():
    spec = importlib.util.spec_from_file_location(
        "jarvis_build_standalone_pkg_test",
        REPO_ROOT / "scripts" / "build_standalone_package.py",
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def packaging_module():
    return _load_packaging_module()


def test_packaging_module_canonical_version(packaging_module):
    """Verify packaging script resolves the exact version from jarvis.__init__."""
    import jarvis

    assert packaging_module.get_canonical_version() == jarvis.__version__


def test_packaging_module_arg_parser(packaging_module):
    """Verify packaging script argument parser handles all required flags."""
    parser_fn = packaging_module.parse_args

    args_dry = parser_fn(["--dry-run"])
    assert args_dry.dry_run is True

    args_chk = parser_fn(["--check"])
    assert args_chk.check is True

    args_custom = parser_fn(["--output-dir", "build/out", "--no-clean", "--console"])
    assert args_custom.output_dir == "build/out"
    assert args_custom.clean is False
    assert args_custom.console is True


def test_packaging_module_clean_machine_environment_checks(packaging_module):
    """Verify clean-machine environment check returns required contract fields."""
    env_res = packaging_module.check_clean_machine_environment()

    assert "python_version_ok" in env_res
    assert "pyinstaller_ok" in env_res
    assert "msvc_runtime_ok" in env_res
    assert "audio_runtime_ok" in env_res
    assert "entry_point_ok" in env_res
    assert "icon_ok" in env_res
    assert "config_schema_ok" in env_res
    assert "details" in env_res

    # On this development host, entry point, icon, config schema, and python must be ok
    assert env_res["python_version_ok"] is True
    assert env_res["entry_point_ok"] is True
    assert env_res["icon_ok"] is True
    assert env_res["config_schema_ok"] is True


def test_packaging_module_onedir_spec_generation(packaging_module, tmp_path):
    """Verify generated PyInstaller spec enforces onedir COLLECT architecture."""
    spec_out = tmp_path / "test_bundle.spec"
    spec_text = packaging_module.generate_onedir_spec(spec_path=spec_out, output_dir=tmp_path / "out")

    assert spec_out.is_file()
    # Must use COLLECT for --onedir
    assert "COLLECT(" in spec_text
    assert "exclude_binaries=True" in spec_text

    # Must contain essential hidden imports
    for imp in ["sounddevice", "numpy", "sqlite3", "win32gui", "pystray", "PIL", "rich", "pydantic", "fastapi", "uvicorn"]:
        assert imp in spec_text, f"Missing hidden import: {imp}"

    # Must bundle required assets and config
    assert "assets" in spec_text
    assert "config" in spec_text

    # Must NOT exclude tkinter
    assert "tkinter" not in spec_text or "# NOTE: tkinter must NOT be excluded" in spec_text
    assert '"tkinter"' not in spec_text.split("excludes=")[1].split("]")[0]


def test_packaging_module_dry_run_executes_successfully(packaging_module):
    """Verify main(['--dry-run']) completes cleanly with exit code 0."""
    exit_code = packaging_module.main(["--dry-run"])
    assert exit_code == 0


def test_packaging_module_check_executes_successfully(packaging_module):
    """Verify main(['--check']) completes cleanly with exit code 0."""
    exit_code = packaging_module.main(["--check"])
    assert exit_code == 0
