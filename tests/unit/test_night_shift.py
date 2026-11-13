"""
tests/unit/test_night_shift.py
==============================
Unit tests for NightShiftEngine: autonomous idle sensing, memory consolidation,
cache pruning, and morning briefing pre-baking.
"""
from __future__ import annotations

import datetime
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.proactive.night_shift import NightShiftEngine, NightShiftReport


def test_night_shift_nocturnal_window() -> None:
    """Verify nocturnal hour detection (00:00 - 06:00)."""
    engine = NightShiftEngine(night_start_hour=0, night_end_hour=6)

    # 03:30 AM -> Night
    dt_night = datetime.datetime(2026, 11, 13, 3, 30, 0)
    assert engine.is_night_window(dt_night) is True

    # 00:00 AM -> Night
    dt_midnight = datetime.datetime(2026, 11, 13, 0, 0, 0)
    assert engine.is_night_window(dt_midnight) is True

    # 06:00 AM -> Day (exclusive end)
    dt_dawn = datetime.datetime(2026, 11, 13, 6, 0, 0)
    assert engine.is_night_window(dt_dawn) is False

    # 14:00 PM -> Day
    dt_day = datetime.datetime(2026, 11, 13, 14, 0, 0)
    assert engine.is_night_window(dt_day) is False


def test_night_shift_should_trigger_idle() -> None:
    """Verify trigger conditions with custom idle probe."""
    idle_val = 100.0

    def mock_idle() -> float:
        return idle_val

    engine = NightShiftEngine(
        idle_threshold_seconds=1800.0,
        get_idle_seconds_fn=mock_idle,
    )

    # 1. Idle 100s during daytime -> False
    with patch.object(engine, "is_night_window", return_value=False):
        assert engine.should_trigger_night_shift() is False

    # 2. Idle 1900s during daytime (> 1800s threshold) -> True
    idle_val = 1900.0
    with patch.object(engine, "is_night_window", return_value=False):
        assert engine.should_trigger_night_shift() is True

    # 3. Idle 400s during nighttime (> 300s night threshold) -> True
    idle_val = 400.0
    with patch.object(engine, "is_night_window", return_value=True):
        assert engine.should_trigger_night_shift() is True

    # 4. Disabled engine -> False
    engine.enabled = False
    with patch.object(engine, "is_night_window", return_value=True):
        assert engine.should_trigger_night_shift() is False


def test_night_shift_cooldown() -> None:
    """Verify cooldown prevents repeated execution within cooldown interval."""
    engine = NightShiftEngine(get_idle_seconds_fn=lambda: 2500.0)
    assert engine.should_trigger_night_shift() is True

    # Execute cycle
    report = engine.execute_night_shift()
    assert isinstance(report, NightShiftReport)

    # Immediately check again -> should be False due to cooldown
    assert engine.should_trigger_night_shift() is False


def test_night_shift_execution_flow(tmp_path: Path) -> None:
    """Verify memory consolidation and briefing pre-bake dispatch."""
    mock_app = MagicMock()
    mock_mem = MagicMock()
    mock_mem.consolidate_episodes.return_value = 14
    mock_mem.list_facts.return_value = ["Fact 1", "Fact 2"]
    mock_app.memory_manager = mock_mem

    engine = NightShiftEngine(app=mock_app)

    # Create dummy stale cache file in temp
    stale_file = tmp_path / "stale_tts.wav"
    stale_file.write_bytes(b"dummy")

    with patch.object(engine, "_prune_temporary_caches", return_value=3):
        report = engine.execute_night_shift()

    assert report.memory_facts_consolidated == 14
    assert report.cache_files_pruned == 3
    assert report.briefing_prebaked is True
    assert report.duration_seconds >= 0.0

    mock_mem.consolidate_episodes.assert_called_once()
    mock_mem.store_fact.assert_called_once()
    args, kwargs = mock_mem.store_fact.call_args
    assert kwargs.get("key") == "prebaked_morning_briefing"
    assert "Chào buổi sáng" in kwargs.get("value", "")


def test_night_shift_thread_lifecycle() -> None:
    """Verify thread start and clean stop."""
    engine = NightShiftEngine(check_interval_seconds=0.1)
    engine.start()
    assert engine._worker_thread is not None
    assert engine._worker_thread.is_alive()

    engine.stop()
    assert engine._worker_thread is None
