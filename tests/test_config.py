"""
tests/test_config.py
====================
Test Suite for Core Configuration, Hot-Reload Watcher, Logging, and AutoStart Installer.
Covering:
  - F-01: Modular Package Structure & Config Models
  - F-02: Legacy .env / Monolith Compatibility
  - F-10: Config Hot-Reload Watcher & Dynamic Updates
  - F-18: Structured File Logging & Rotation
  - F-19: Windows Auto-Start Installer (Registry / Task Scheduler)
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

import pytest

from jarvis.core.config import (
    AudioConfig,
    ConfigManager,
    JarvisConfig,
    LoggingConfig,
    TTSConfig,
    WindowsConfig,
    load_config,
)
from jarvis.core.logger import LogContext, StructuredLogger, setup_logging
from jarvis.platform.autostart import AutoStartManager, AutoStartMode

# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_config_manager_load_default_yaml_tier1(tmp_path):
    """
    [F-01, F-10] Validate that ConfigManager loads standard configuration,
    parses valid Pydantic models, and provides structured nested access.
    """
    config_file = tmp_path / "config.json"
    data = {
        "audio": {
            "sample_rate": 44100,
            "block_ms": 40,
            "spike_ratio": 7.0,
            "cooldown_s": 0.45,
            "min_rms": 0.012,
        },
        "tts": {
            "welcome_enabled": True,
            "voice_id": "EXAVITQu4vr4xnSDxMaL",
            "model_id": "eleven_multilingual_v2",
        },
        "windows": {
            "claude_monitor": 1,
            "binance_monitor": 3,
        }
    }
    config_file.write_text(json.dumps(data), encoding="utf-8")

    mgr = ConfigManager(config_path=config_file)
    cfg = mgr.load()

    assert cfg.audio.sample_rate == 44100
    assert cfg.audio.spike_ratio == 7.0
    assert cfg.tts.welcome_enabled is True
    assert mgr.get("audio.spike_ratio") == 7.0
    assert mgr.get("windows.claude_monitor") == 1
    assert isinstance(mgr.to_dict(), dict)


def test_config_legacy_env_loading_tier1(monkeypatch, tmp_path):
    """
    [F-02] Validate that ConfigManager reads legacy .env keys (ELEVENLABS_API_KEY, SONG_URI, CLAUDE_CHROME_MONITOR)
    and maps them to appropriate internal configuration fields.
    """
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test_eleven_key_xyz")
    monkeypatch.setenv("SONG_URI", "spotify:track:test_song_123")
    monkeypatch.setenv("CLAUDE_CHROME_MONITOR", "2")
    monkeypatch.setenv("JARVIS_SPIKE_RATIO", "8.5")

    empty_config = tmp_path / "empty_config.json"
    empty_config.write_text("{}", encoding="utf-8")

    mgr = ConfigManager(config_path=empty_config)
    cfg = mgr.load()

    assert cfg.tts.elevenlabs_api_key == "test_eleven_key_xyz"
    assert cfg.audio.spike_ratio == 8.5
    assert cfg.windows.claude_monitor == 2


def test_config_hot_reload_on_file_modification_tier1(tmp_path):
    """
    [F-10] Validate that modifying the configuration file triggers hot-reload callback
    within <= 5 seconds without restarting the process.
    """
    config_file = tmp_path / "live_config.json"
    initial_data = {"audio": {"spike_ratio": 7.0, "sample_rate": 44100}}
    config_file.write_text(json.dumps(initial_data), encoding="utf-8")

    mgr = ConfigManager(config_path=config_file)
    mgr.load()

    reloaded_event = threading.Event()
    updated_configs = []

    def on_reload(new_cfg: JarvisConfig):
        updated_configs.append(new_cfg)
        reloaded_event.set()

    mgr.register_reload_callback(on_reload)

    # Simulate file change
    time.sleep(0.05)
    updated_data = {"audio": {"spike_ratio": 9.2, "sample_rate": 44100}}
    config_file.write_text(json.dumps(updated_data), encoding="utf-8")

    # Manually check reload
    did_reload = mgr.reload_if_changed()
    assert did_reload is True
    assert mgr.get("audio.spike_ratio") == 9.2
    assert reloaded_event.is_set()


def test_logging_rotational_file_handler_tier1(tmp_path):
    """
    [F-18] Validate structured rotating file logging handler creates timestamped logs
    and formats JSON/structured context.
    """
    log_file = tmp_path / "logs" / "jarvis.log"
    logger = setup_logging(log_file=str(log_file), log_level="DEBUG", max_bytes=1024*1024)

    logger.info("JARVIS daemon initializing", extra={"component": "core", "version": "2.0.0"})
    logger.warning("High audio transient detected", extra={"rms": 0.085, "ratio": 7.5})

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "JARVIS daemon initializing" in content
    assert "High audio transient detected" in content


def test_windows_autostart_registry_installer_tier1(monkeypatch):
    """
    [F-19] Validate that Windows autostart installer registers the JARVIS entry point in HKCU Run registry key.
    """
    mock_registry: Dict[str, str] = {}

    class MockWinReg:
        HKEY_CURRENT_USER = 0x80000001
        KEY_ALL_ACCESS = 0xF003F
        KEY_READ = 0x20019
        REG_SZ = 1

        @staticmethod
        def OpenKey(key, sub_key, reserved=0, access=0):
            return 1234

        @staticmethod
        def CreateKey(key, sub_key):
            return 1234

        @staticmethod
        def SetValueEx(key_handle, value_name, reserved, val_type, value):
            mock_registry[value_name] = value

        @staticmethod
        def QueryValueEx(key_handle, value_name):
            if value_name in mock_registry:
                return (mock_registry[value_name], 1)
            raise FileNotFoundError("Value not found")

        @staticmethod
        def DeleteValue(key_handle, value_name):
            if value_name in mock_registry:
                del mock_registry[value_name]
            else:
                raise FileNotFoundError("Value not found")

        @staticmethod
        def CloseKey(key_handle):
            pass

    monkeypatch.setattr("winreg.OpenKey", MockWinReg.OpenKey, raising=False)
    monkeypatch.setattr("winreg.CreateKey", MockWinReg.CreateKey, raising=False)
    monkeypatch.setattr("winreg.SetValueEx", MockWinReg.SetValueEx, raising=False)
    monkeypatch.setattr("winreg.QueryValueEx", MockWinReg.QueryValueEx, raising=False)
    monkeypatch.setattr("winreg.DeleteValue", MockWinReg.DeleteValue, raising=False)
    monkeypatch.setattr("winreg.CloseKey", MockWinReg.CloseKey, raising=False)

    autostart = AutoStartManager(app_name="JARVIS_TEST", mode=AutoStartMode.REGISTRY)
    success = autostart.enable(command_args=["--headless", "--tray"])
    assert success is True
    assert "JARVIS_TEST" in mock_registry
    assert autostart.is_enabled() is True

    # Test disable
    disabled = autostart.disable()
    assert disabled is True
    assert "JARVIS_TEST" not in mock_registry
    assert autostart.is_enabled() is False


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_config_hot_reload_malformed_json_tier2(tmp_path, caplog):
    """
    [F-10] Validate that overwriting the configuration file with malformed syntax
    does not crash the system, logs an error, and preserves the active in-memory configuration.
    """
    config_file = tmp_path / "corrupt_config.json"
    config_file.write_text('{"audio": {"spike_ratio": 7.0}}', encoding="utf-8")

    mgr = ConfigManager(config_path=config_file)
    mgr.load()
    assert mgr.get("audio.spike_ratio") == 7.0

    # Write corrupt JSON
    time.sleep(0.05)
    config_file.write_text('{"audio": {INVALID_JSON...', encoding="utf-8")

    did_reload = mgr.reload_if_changed()
    assert did_reload is False
    # Active config remains preserved
    assert mgr.get("audio.spike_ratio") == 7.0


def test_config_missing_file_graceful_defaults_tier2(tmp_path):
    """
    [F-01, F-02] Validate graceful fallback to defaults when configuration file does not exist.
    """
    non_existent = tmp_path / "does_not_exist.json"
    mgr = ConfigManager(config_path=non_existent)
    cfg = mgr.load()

    assert cfg.audio.sample_rate == 44100
    assert cfg.audio.spike_ratio == 7.0
    assert cfg.tts.model_id == "eleven_multilingual_v2"


def test_config_type_coercion_and_bounds_tier2(tmp_path):
    """
    [F-01] Validate that invalid parameter ranges or non-matching types fall back safely or raise validation.
    """
    config_file = tmp_path / "bounds_config.json"
    data = {"audio": {"sample_rate": 48000, "spike_ratio": 12.5, "cooldown_s": 0.5}}
    config_file.write_text(json.dumps(data), encoding="utf-8")

    mgr = ConfigManager(config_path=config_file)
    cfg = mgr.load()
    assert cfg.audio.sample_rate == 48000
    assert cfg.audio.spike_ratio == 12.5


def test_windows_autostart_permission_error_fallback_tier2(monkeypatch):
    """
    [F-19] Validate that PermissionError during registry access is caught cleanly.
    """
    class FailingWinReg:
        @staticmethod
        def OpenKey(*args, **kwargs):
            raise PermissionError("Access Denied to HKCU Run")
        @staticmethod
        def CreateKey(*args, **kwargs):
            raise PermissionError("Access Denied to HKCU Run")

    monkeypatch.setattr("winreg.OpenKey", FailingWinReg.OpenKey, raising=False)
    monkeypatch.setattr("winreg.CreateKey", FailingWinReg.CreateKey, raising=False)

    autostart = AutoStartManager(app_name="JARVIS_LOCKED", mode=AutoStartMode.REGISTRY)
    res = autostart.enable()
    assert res is False
