"""
tests/unit/test_executive_briefing.py
=====================================
Unit test suite for ExecutiveBriefingEngine and BriefingReport.
Tests hardware vitals gathering, Git workspace status scanning, and speech synthesis formatting.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.personalization.briefing import BriefingReport, ExecutiveBriefingEngine
from jarvis.personalization.profile import PersonaTone, UserProfile, UserProfileManager


def test_executive_briefing_generation(tmp_path: Path):
    profile_file = tmp_path / "user_profile_briefing.json"
    mgr = UserProfileManager(profile_path=profile_file)
    mgr.update_profile(
        user_name="Hưng",
        honorific="Chủ nhân",
        assistant_name="JARVIS",
        tone=PersonaTone.IRON_MAN_WITTY,
        primary_workspace=str(tmp_path),
    )

    engine = ExecutiveBriefingEngine(profile_manager=mgr)
    report = engine.generate_morning_briefing()

    assert isinstance(report, BriefingReport)
    assert "Báo Cáo Buổi Sáng" in report.summary_markdown
    assert "Chủ nhân Hưng" in report.summary_markdown
    assert "CPU" in report.summary_markdown
    assert "RAM" in report.summary_markdown
    assert len(report.speech_script) > 20
    assert "Chủ nhân" in report.speech_script


def test_executive_briefing_collect_system_vitals():
    engine = ExecutiveBriefingEngine()
    vitals = engine.collect_system_vitals()

    assert "cpu_percent" in vitals
    assert "ram_total_gb" in vitals
    assert "disk_free_gb" in vitals
    assert vitals["ram_total_gb"] > 0.0


def test_executive_briefing_scan_git_workspace(tmp_path: Path):
    # Setup dummy git repo
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo_dir), capture_output=True, text=True)

    engine = ExecutiveBriefingEngine()
    summaries = engine.scan_git_workspace(str(tmp_path))

    assert len(summaries) >= 1
    found = [s for s in summaries if s["name"] == "test_repo"]
    assert len(found) == 1
    assert found[0]["clean"] is True


def test_executive_briefing_speak(tmp_path: Path):
    profile_file = tmp_path / "user_profile_speak.json"
    mgr = UserProfileManager(profile_path=profile_file)
    engine = ExecutiveBriefingEngine(profile_manager=mgr)

    mock_tts = MagicMock()
    mock_tts.speak = MagicMock()

    ok = engine.speak_briefing(tts_manager=mock_tts)
    assert ok is True
    mock_tts.speak.assert_called_once()
