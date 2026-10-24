"""
tests/unit/test_spiking_saliency.py
===================================
Unit tests for Frontier 17.0 Neuromorphic Event Saliency Engine.
Sprint 26 / Milestone v6.4.0.
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.vision.spiking_saliency import (
    DEFAULT_SPIKE_THRESHOLD,
    MACROBLOCK_SIZE,
    NeuromorphicEventSaliencyEngine,
    SaliencyROI,
    SpikingSaliencyResult,
    SpikingSaliencyStatus,
)


def test_spiking_saliency_initial_refresh() -> None:
    """Verifies that the first processed frame triggers FULL_REFRESH."""
    engine = NeuromorphicEventSaliencyEngine(width=640, height=480)
    frame1 = np.full((480, 640, 3), fill_value=50, dtype=np.uint8)

    res1 = engine.process_frame(frame1)
    assert res1.status == SpikingSaliencyStatus.FULL_REFRESH
    assert res1.active_pixel_count == 640 * 480
    assert res1.sparsity_ratio == 1.0
    assert len(res1.active_rois) == 1
    assert res1.is_screen_changed is True


def test_spiking_saliency_idle_detection() -> None:
    """Verifies that identical consecutive frames return IDLE status."""
    engine = NeuromorphicEventSaliencyEngine(width=640, height=480)
    frame = np.full((480, 640, 3), fill_value=100, dtype=np.uint8)

    # Frame 1: baseline
    engine.process_frame(frame)

    # Frame 2: identical static screen
    res2 = engine.process_frame(frame)
    assert res2.status == SpikingSaliencyStatus.IDLE
    assert res2.active_pixel_count == 0
    assert len(res2.active_rois) == 0
    assert res2.is_screen_changed is False
    assert res2.filter_latency_ms < 15.0


def test_spiking_saliency_sparse_change_roi_extraction() -> None:
    """Tests sparse dynamic change detection (e.g. blinking cursor or moving window)."""
    engine = NeuromorphicEventSaliencyEngine(width=1920, height=1080)
    frame_static = np.full((1080, 1920, 3), fill_value=40, dtype=np.uint8)

    engine.process_frame(frame_static)

    # Frame 2: Introduce a 100x100 bright white box at (500, 300)
    frame_dynamic = frame_static.copy()
    frame_dynamic[300:400, 500:600, :] = 240  # 10,000 pixels changed out of 2.07M

    res = engine.process_frame(frame_dynamic)
    assert res.status == SpikingSaliencyStatus.ACTIVE_MOTION
    assert res.active_pixel_count == 10000  # < 15,000 active pixels SLA!
    assert res.active_pixel_count < 15000
    assert res.sparsity_ratio < 0.01  # > 99% of pixels static
    assert res.is_screen_changed is True
    assert len(res.active_rois) > 0

    roi = res.active_rois[0]
    # Check that ROI covers the changed box
    assert roi.x <= 500
    assert roi.y <= 300
    assert (roi.x + roi.width) >= 600
    assert (roi.y + roi.height) >= 400

    metrics = engine.get_metrics_snapshot()
    assert metrics["vram_delta_mib"] == 0.00
    assert metrics["total_frames_processed"] == 2
