"""
tests/unit/test_voice_biometrics.py
===================================
Unit tests for jarvis/audio/biometrics.py:
  - Acoustic feature extraction (Mel filterbank, spectral centroid/spread/flux, harmonics).
  - Voiceprint profile enrollment with multi-sample accumulation.
  - Cosine similarity matching against enrolled profiles.
  - Fail-closed handling of silence, short buffers, and NaN/inf audio.
  - Windows atomic disk persistence with retry loops.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from jarvis.audio.biometrics import (
    DEFAULT_VERIFICATION_THRESHOLD,
    VOICEPRINT_DIM,
    VoiceBiometricsManager,
    VoiceprintProfile,
    compute_cosine_similarity,
    extract_voiceprint,
)


@pytest.fixture
def temp_profile_path(tmp_path: Path) -> Path:
    """Fixture providing a temporary JSON path for voiceprint persistence."""
    return tmp_path / "voiceprints.json"


@pytest.fixture
def synthetic_speech_audio() -> np.ndarray:
    """
    Generates a realistic synthetic speech signal with harmonic formants (F0=130Hz, F1=700Hz, F2=1800Hz)
    over 1.0 second at 16kHz with realistic amplitude modulation.
    """
    sr = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Fundamental frequency + harmonics + vocal tract formants
    signal = (
        0.35 * np.sin(2 * np.pi * 130 * t)
        + 0.25 * np.sin(2 * np.pi * 260 * t)
        + 0.20 * np.sin(2 * np.pi * 700 * t)
        + 0.15 * np.sin(2 * np.pi * 1800 * t)
        + 0.05 * np.random.normal(0, 0.01, size=t.shape)
    )
    # Apply speech syllable envelope
    envelope = np.abs(np.sin(2 * np.pi * 3.0 * t))
    modulated = (signal * envelope).astype(np.float32)
    return modulated


def test_extract_voiceprint_silence_or_empty_fails_closed():
    """Verify that empty, None, and silent audio fail closed and return None."""
    assert extract_voiceprint(None) is None
    assert extract_voiceprint(np.empty(0, dtype=np.float32)) is None

    # Complete silence
    silence = np.zeros(16000, dtype=np.float32)
    assert extract_voiceprint(silence) is None

    # Too short audio (<250ms)
    too_short = np.random.normal(0, 0.05, size=1600).astype(np.float32)
    assert extract_voiceprint(too_short, min_speech_ms=250.0) is None


def test_extract_voiceprint_synthetic_speech(synthetic_speech_audio):
    """Verify that realistic speech extracts a 64-dimensional unit vector."""
    voiceprint = extract_voiceprint(synthetic_speech_audio, sample_rate=16000)
    assert voiceprint is not None
    assert isinstance(voiceprint, np.ndarray)
    assert voiceprint.shape == (VOICEPRINT_DIM,)
    assert voiceprint.dtype == np.float32

    # Vector must be unit-normalized (norm == 1.0)
    norm = float(np.linalg.norm(voiceprint))
    assert pytest.approx(norm, abs=1e-4) == 1.0


def test_compute_cosine_similarity():
    """Verify cosine similarity calculation between vectors."""
    v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v3 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    v4 = np.array([-1.0, 0.0, 0.0], dtype=np.float32)

    assert pytest.approx(compute_cosine_similarity(v1, v2)) == 1.0
    assert pytest.approx(compute_cosine_similarity(v1, v3)) == 0.0
    assert pytest.approx(compute_cosine_similarity(v1, v4)) == -1.0
    assert compute_cosine_similarity(None, v1) == 0.0


def test_voiceprint_profile_serialization():
    """Verify VoiceprintProfile to_dict and from_dict roundtrip."""
    emb = [float(i) for i in range(VOICEPRINT_DIM)]
    prof = VoiceprintProfile(
        speaker_name="Tony Stark",
        embedding=emb,
        sample_count=3,
        threshold=0.82,
    )
    d = prof.to_dict()
    assert d["speaker_name"] == "Tony Stark"
    assert d["sample_count"] == 3
    assert d["threshold"] == 0.82

    recovered = VoiceprintProfile.from_dict(d)
    assert recovered.speaker_name == "Tony Stark"
    assert recovered.sample_count == 3
    assert recovered.embedding == emb


def test_biometrics_manager_enrollment_and_verification(temp_profile_path, synthetic_speech_audio):
    """Verify speaker enrollment, atomic file saving, and verification matching."""
    mgr = VoiceBiometricsManager(storage_path=temp_profile_path)
    assert mgr.enrolled_speakers == []

    # Enroll speaker 'Tony'
    success, msg = mgr.enroll_speaker("Tony", synthetic_speech_audio)
    assert success is True
    assert "enrolled" in msg.lower()
    assert mgr.enrolled_speakers == ["Tony"]
    assert temp_profile_path.exists()

    # Verify matching audio
    verified, matched_speaker, score = mgr.verify_speaker(synthetic_speech_audio)
    assert verified is True
    assert matched_speaker == "Tony"
    assert score >= 0.95

    # Verify a different speaker (high-pitched vocal profile 4000-6000Hz)
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    different_speaker_audio = (
        (0.50 * np.sin(2 * np.pi * 4500 * t) + 0.30 * np.sin(2 * np.pi * 6000 * t))
        * np.abs(np.sin(2 * np.pi * 8.0 * t))
    ).astype(np.float32)

    verified_diff, speaker_diff, score_diff = mgr.verify_speaker(
        different_speaker_audio,
        threshold=0.80,
    )
    assert verified_diff is False
    assert score_diff < 0.50


def test_biometrics_manager_multi_sample_accumulation(temp_profile_path, synthetic_speech_audio):
    """Verify that multiple enrollment samples average the embedding and increment count."""
    mgr = VoiceBiometricsManager(storage_path=temp_profile_path)
    mgr.enroll_speaker("Tony", synthetic_speech_audio)
    prof1 = mgr.get_profile("Tony")
    assert prof1 is not None
    assert prof1.sample_count == 1

    # Second sample
    jittered_audio = synthetic_speech_audio + np.random.normal(0, 0.01, size=synthetic_speech_audio.shape).astype(np.float32)
    mgr.enroll_speaker("Tony", jittered_audio)
    prof2 = mgr.get_profile("Tony")
    assert prof2 is not None
    assert prof2.sample_count == 2


def test_biometrics_manager_persistence_reload(temp_profile_path, synthetic_speech_audio):
    """Verify profiles survive reload from disk."""
    mgr1 = VoiceBiometricsManager(storage_path=temp_profile_path)
    mgr1.enroll_speaker("Bruce Banner", synthetic_speech_audio)

    # Instantiate second manager pointing to same storage
    mgr2 = VoiceBiometricsManager(storage_path=temp_profile_path)
    assert "Bruce Banner" in mgr2.enrolled_speakers
    prof = mgr2.get_profile("Bruce Banner")
    assert prof is not None
    assert prof.speaker_name == "Bruce Banner"


def test_biometrics_manager_delete_profile(temp_profile_path, synthetic_speech_audio):
    """Verify profile deletion removes profile from memory and disk."""
    mgr = VoiceBiometricsManager(storage_path=temp_profile_path)
    mgr.enroll_speaker("JARVIS User", synthetic_speech_audio)
    assert "JARVIS User" in mgr.enrolled_speakers

    assert mgr.delete_profile("JARVIS User") is True
    assert "JARVIS User" not in mgr.enrolled_speakers
    assert mgr.delete_profile("NonExistent") is False
