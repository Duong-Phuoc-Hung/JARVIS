"""
tests/unit/test_setup_wizard.py
===============================
Unit tests for the first-run setup wizard (H-11).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.ui.setup_wizard import SetupWizard, run_setup_wizard_auto


def test_setup_wizard_auto_runs_and_persists_config(tmp_path: Path):
    cfg_file = tmp_path / "jarvis_config.json"
    wizard = SetupWizard(interactive=False, config_path=cfg_file)
    res = wizard.run()

    assert res["saved"] is True
    assert cfg_file.exists()

    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert data["stt.sample_rate"] == 16000
    assert data["stt.model_size"] == "small"
    assert data["wake_word.enabled"] is True
    assert "audio.input_device_index" in data


def test_setup_wizard_fallback_when_audio_hardware_unavailable(tmp_path: Path):
    cfg_file = tmp_path / "fallback_config.json"
    with patch("sounddevice.rec", side_effect=RuntimeError("No audio device")):
        wizard = SetupWizard(interactive=False, config_path=cfg_file)
        res = wizard.run()

    assert res["saved"] is True
    assert res["audio.mic_tested"] is False
    assert cfg_file.exists()
