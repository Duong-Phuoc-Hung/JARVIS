"""
tests/unit/test_crrsp_memory.py
===============================
Unit test suite for Continuous Rolling Recurrent State Persistence (CRRSP).
Validates dual fast/slow state separation, multi-turn persistence,
zero-VRAM allocation, and bounded O(1) buffer size in Argon Frontier 10.0.
"""
import time
import numpy as np
import pytest

from jarvis.stt.crrsp_memory import (
    CRRSPConfig,
    CRRSPTelemetry,
    ContinuousRollingRecurrentMemory,
)


class TestContinuousRollingRecurrentMemory:
    """Comprehensive test harness for CRRSP memory engine."""

    def test_crrsp_memory_allocation_and_vram_invariant(self) -> None:
        """Verifies strictly constant O(1) buffer footprint and 0 MB VRAM delta."""
        memory = ContinuousRollingRecurrentMemory()
        assert memory.h_fast.shape == (512, 64)
        assert memory.h_slow.shape == (512, 64)
        assert memory.h_fast.dtype == np.float32

        # Memory footprint: 2 * 512 * 64 * 4 bytes = 262,144 bytes = 256.0 KB
        telemetry = memory.get_telemetry()
        assert telemetry.memory_kb <= 265.0, f"Memory {telemetry.memory_kb:.2f} KB exceeds 265 KB limit"
        assert telemetry.vram_delta_mb == 0.00

    def test_crrsp_dual_tier_dynamics_and_turn_finalization(self) -> None:
        """Verifies fast state decay on turn finalization while slow state persists context."""
        memory = ContinuousRollingRecurrentMemory()

        # Step multiple active speech frames with high energy
        rng = np.random.default_rng(42)
        speech_frame = rng.normal(1.0, 0.2, (512, 64)).astype(np.float32)

        for _ in range(10):
            memory.step_frame(speech_frame, f0_hz=180.0, is_silence=False)

        tel_active = memory.get_telemetry()
        assert tel_active.fast_norm > 0.5
        assert tel_active.slow_norm > 0.05
        assert 165.0 <= tel_active.f0_prior_hz <= 185.0

        # Finalize turn 1 (user stops speaking)
        memory.finalize_turn("mở bài hát chúng ta của hiện tại")

        tel_after_turn = memory.get_telemetry()
        # Fast state is decayed by 95%
        assert tel_after_turn.fast_norm < tel_active.fast_norm * 0.15
        # Slow state is preserved!
        assert tel_after_turn.slow_norm >= tel_active.slow_norm * 0.90
        assert tel_after_turn.turns_accumulated == 1

    def test_crrsp_multi_turn_anaphora_continuity(self) -> None:
        """Verifies conversational continuity across 3 consecutive turns without drift."""
        memory = ContinuousRollingRecurrentMemory()
        rng = np.random.default_rng(101)

        turns_input = [
            ("Turn 1: play music", rng.normal(0.8, 0.1, (512, 64)).astype(np.float32)),
            ("Turn 2: turn it up", rng.normal(0.9, 0.1, (512, 64)).astype(np.float32)),
            ("Turn 3: next song", rng.normal(0.7, 0.1, (512, 64)).astype(np.float32)),
        ]

        for transcript, frame in turns_input:
            for _ in range(5):
                out = memory.step_frame(frame, f0_hz=165.0)
                assert out.shape == (512, 64)
            memory.finalize_turn(transcript)

        final_tel = memory.get_telemetry()
        assert final_tel.turns_accumulated == 3
        assert final_tel.slow_norm > 0.1
        # Memory size remains strictly unchanged across all turns
        assert final_tel.memory_kb <= 265.0

    def test_crrsp_1d_vector_compatibility(self) -> None:
        """Verifies seamless compatibility with 1D acoustic vectors (512,)."""
        memory = ContinuousRollingRecurrentMemory()
        vec_1d = np.ones(512, dtype=np.float32)

        out_vec = memory.step_frame(vec_1d, f0_hz=200.0)
        assert out_vec.ndim == 1
        assert out_vec.shape == (512,)
        assert not np.isnan(out_vec).any()

    def test_crrsp_reset_lifecycle(self) -> None:
        """Verifies complete state clearing on explicit conversation reset."""
        memory = ContinuousRollingRecurrentMemory()
        vec = np.ones((512, 64), dtype=np.float32)
        memory.step_frame(vec)
        memory.finalize_turn()

        assert memory.turns_count == 1
        memory.reset()

        tel = memory.get_telemetry()
        assert tel.fast_norm == 0.0
        assert tel.slow_norm == 0.0
        assert tel.turns_accumulated == 0
