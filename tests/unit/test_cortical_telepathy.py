"""
tests/unit/test_cortical_telepathy.py
=====================================
Unit Tests for Brain-Computer Bi-Directional Neuro-Stimulation & Phosphene Visual Feedback.
Milestone v9.0.0 ("The Transcendent Singularity", Frontier 31.0).
"""
from __future__ import annotations

import math
import os
import tempfile
import numpy as np
import pytest

from jarvis.audio.cortical_telepathy import (
    BioStimulatorHardwareBridge,
    BioStimulatorTelemetry,
    ClosedLoopSomaticReflexEngine,
    PhosphenePatternType,
    PhosphenePercept,
    PhospheneVisualGenerator,
    SomaticReflexEvent,
    TemporalInterferenceModel,
    TemporalInterferenceWaveform,
)
from jarvis.ui.terminal.theme import StatusLevel


def test_temporal_interference_electric_field_synthesis():
    """Validates Temporal Interference dual high-frequency carrier waveforms and envelope beat."""
    f1 = 2000.0  # 2.0 kHz
    delta_f = 25.0  # 25.0 Hz beta rhythm
    model = TemporalInterferenceModel(carrier_f1_hz=f1, beat_delta_f_hz=delta_f)

    assert model.carrier_f1_hz == 2000.0
    assert model.carrier_f2_hz == 2025.0
    assert model.beat_delta_f_hz == 25.0

    wf = model.synthesize_waveform(
        duration_ms=40.0,
        amplitude_1_v_m=1.0,
        amplitude_2_v_m=1.0,
    )

    assert isinstance(wf, TemporalInterferenceWaveform)
    assert len(wf.time_points_s) > 100
    assert len(wf.field_1) == len(wf.time_points_s)
    assert len(wf.field_2) == len(wf.time_points_s)
    assert len(wf.envelope) == len(wf.time_points_s)

    # For two equal carriers of amplitude 1.0, the peak constructive envelope amplitude is 2.0 V/m
    assert abs(wf.peak_envelope_amplitude_v_m - 2.0) < 0.05
    assert not np.isnan(wf.envelope).any()


def test_retinotopic_conformal_map_and_inverse():
    """Validates Schwartz's logarithmic conformal map w = k * ln(z + a) and its exact inverse."""
    gen = PhospheneVisualGenerator(k=17.0, a=0.75)

    r_orig = 5.0      # 5 degrees eccentricity
    th_orig = 0.5     # 0.5 radians

    # Map forward: visual field -> V1 cortical flat-map
    u_mm, v_mm = gen.visual_field_to_cortex(r_orig, th_orig)
    assert not math.isnan(u_mm)
    assert not math.isnan(v_mm)

    # Inverse map: V1 cortex -> visual field
    r_rec, th_rec = gen.cortex_to_visual_field(u_mm, v_mm)
    assert abs(r_rec - r_orig) < 1e-4
    assert abs(th_rec - th_orig) < 1e-4


def test_phosphene_visual_percept_generation_latency_sla():
    """Validates direct-to-cortex visual phosphene generation in < 1.0 ms (bypassing monitor lag)."""
    gen = PhospheneVisualGenerator()

    # Synthesize 100 phosphene percepts and check SLA
    latencies = []
    for _ in range(50):
        percept = gen.generate_phosphene(
            pattern_type=PhosphenePatternType.CONFIRMATION_FLASH,
            azimuth_deg=2.5,
            elevation_deg=-1.5,
            intensity=0.9,
        )
        assert isinstance(percept, PhosphenePercept)
        latencies.append(percept.generation_latency_ms)

    median_latency_ms = float(np.median(latencies))
    # SLA: Sub-millisecond direct cortical percept (< 1.0 ms)
    assert median_latency_ms < 1.0
    assert percept.cortical_target_coords_mm[2] == 1.5  # Cortical depth


def test_closed_loop_somatic_reflex_engine():
    """Validates pairing of incoming sEMG motor intentions with instantaneous cortical feedback."""
    engine = ClosedLoopSomaticReflexEngine()

    # Trigger reflex for confirmation
    event_yes = engine.trigger_reflex("SEM_INTENT_CONFIRM", confidence=0.98)
    assert isinstance(event_yes, SomaticReflexEvent)
    assert event_yes.phosphene.pattern_type == PhosphenePatternType.CONFIRMATION_FLASH
    assert event_yes.ti_waveform_summary["peak_envelope_amplitude_v_m"] > 0.0
    assert event_yes.total_reflex_loop_ms < 5.0

    # Trigger reflex for navigation
    event_nav = engine.trigger_reflex("SEM_INTENT_NAVIGATE_RIGHT", confidence=0.92, target_azimuth_deg=10.0)
    assert event_nav.phosphene.pattern_type == PhosphenePatternType.DIRECTION_ARROW
    assert len(engine.history) == 2


def test_fail_closed_bio_stimulator_hardware_bridge():
    """Validates AGENTS.md Rule 2: Returns StatusLevel.LIMITED when physical stimulator is absent."""
    bridge = BioStimulatorHardwareBridge()
    telem = bridge.get_telemetry()

    assert isinstance(telem, BioStimulatorTelemetry)
    assert telem.status == StatusLevel.LIMITED
    assert telem.is_physical_hardware is False
    assert telem.vram_delta_mib == 0.00
    assert "NOT_FOUND" in telem.probe_reason or "INITIALIZED" in telem.probe_reason


def test_bio_stimulator_windows_atomic_persistence():
    """Validates thread-safe Windows Atomic Persistence save/load for stimulator state."""
    bridge = BioStimulatorHardwareBridge()
    bridge.reflex_engine.trigger_reflex("CONFIRM_ACTION", confidence=0.95)
    bridge.reflex_engine.trigger_reflex("SWITCH_WINDOW", confidence=0.88)
    bridge.reflex_engine.trigger_reflex("CANCEL_TASK", confidence=0.90)

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = os.path.join(tmpdir, "stimulator_calibration.json")
        bridge.save(save_path)
        assert os.path.exists(save_path)

        restored = BioStimulatorHardwareBridge.load(save_path)
        assert isinstance(restored, BioStimulatorHardwareBridge)
        assert restored._status == StatusLevel.LIMITED
        # Verify complete history restoration
        assert len(restored.reflex_engine.history) == 3
        assert restored.reflex_engine.history[0].intent_label == "CONFIRM_ACTION"
        assert restored.reflex_engine.history[0].phosphene.pattern_type == PhosphenePatternType.CONFIRMATION_FLASH
        assert restored.reflex_engine.history[1].intent_label == "SWITCH_WINDOW"
        assert restored.reflex_engine.history[1].phosphene.pattern_type == PhosphenePatternType.DIRECTION_ARROW
        assert restored.reflex_engine.history[2].intent_label == "CANCEL_TASK"
        assert restored.reflex_engine.history[2].phosphene.pattern_type == PhosphenePatternType.TACTILE_PULSE


def test_temporal_interference_edge_cases():
    """Validates parameter bounds and boundary handling."""
    # Carrier frequency too low (< 500 Hz) raises ValueError
    with pytest.raises(ValueError):
        TemporalInterferenceModel(carrier_f1_hz=200.0)

    # Beat frequency out of range raises ValueError
    with pytest.raises(ValueError):
        TemporalInterferenceModel(carrier_f1_hz=2000.0, beat_delta_f_hz=-5.0)

    with pytest.raises(ValueError):
        TemporalInterferenceModel(carrier_f1_hz=2000.0, beat_delta_f_hz=250.0)

    # Waveform synthesis invalid duration or amplitude
    model = TemporalInterferenceModel()
    with pytest.raises(ValueError):
        model.synthesize_waveform(duration_ms=0.0)

    with pytest.raises(ValueError):
        model.synthesize_waveform(duration_ms=-10.0)

    with pytest.raises(ValueError):
        model.synthesize_waveform(amplitude_1_v_m=-1.0)


def test_retinotopic_singularity_guard():
    """Validates conformal map singularity handling at z = -a."""
    gen = PhospheneVisualGenerator(k=17.0, a=0.75)
    # Singularity occurs when r = a and theta = pi (z = -a)
    u_sing, v_sing = gen.visual_field_to_cortex(r_deg=0.75, theta_rad=math.pi)
    assert not math.isnan(u_sing)
    assert not math.isinf(u_sing)
    assert not math.isnan(v_sing)
    assert not math.isinf(v_sing)
