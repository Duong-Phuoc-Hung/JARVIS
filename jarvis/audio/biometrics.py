"""
jarvis/audio/biometrics.py
===========================
Acoustic Voice Biometrics & Speaker Verification Subsystem for JARVIS.
Provides:
  - 64-Dimensional acoustic voiceprint extraction (Mel filterbank energies,
    spectral centroid, spectral flux, pitch harmonics, and delta dynamics).
  - Voiceprint profile enrollment with multi-sample accumulation.
  - Cosine similarity speaker verification against enrolled master profile.
  - Windows atomic persistence with retry loop for multi-thread safety.
  - Fail-closed evaluation for silence, corrupt buffers, and low SNR audio.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from jarvis.audio.dsp import calculate_rms, speech_bandpass_filter

logger = logging.getLogger("jarvis.audio.biometrics")

VOICEPRINT_DIM = 64
DEFAULT_VERIFICATION_THRESHOLD = 0.80
DEFAULT_PROFILE_PATH = Path("data/voiceprints.json")


def _mel_filterbank(num_filters: int, n_fft: int, sample_rate: int) -> np.ndarray:
    """Precomputes triangular Mel filterbank matrix of shape (num_filters, n_fft // 2 + 1)."""
    low_freq = 100.0
    high_freq = min(7500.0, sample_rate / 2.0)
    low_mel = 2595.0 * np.log10(1.0 + low_freq / 700.0)
    high_mel = 2595.0 * np.log10(1.0 + high_freq / 700.0)
    mel_points = np.linspace(low_mel, high_mel, num_filters + 2)
    hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
    bins = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)

    fbank = np.zeros((num_filters, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, num_filters + 1):
        f_m_minus = bins[m - 1]
        f_m = bins[m]
        f_m_plus = bins[m + 1]

        if f_m > f_m_minus:
            fbank[m - 1, f_m_minus:f_m] = (np.arange(f_m_minus, f_m) - f_m_minus) / (f_m - f_m_minus)
        if f_m_plus > f_m:
            fbank[m - 1, f_m:f_m_plus] = (f_m_plus - np.arange(f_m, f_m_plus)) / (f_m_plus - f_m)

    return fbank


def extract_voiceprint(
    audio: np.ndarray | None,
    sample_rate: int = 16000,
    min_speech_ms: float = 250.0,
) -> np.ndarray | None:
    """
    Extracts a normalized 64-dimensional acoustic voiceprint embedding from speech audio.

    Args:
        audio: 1D NumPy float32 audio buffer.
        sample_rate: Audio sampling frequency in Hz (default 16000).
        min_speech_ms: Minimum active speech duration required in milliseconds.

    Returns:
        np.ndarray: Unit-normalized float32 vector of shape (64,), or None if invalid.
    """
    if audio is None or getattr(audio, "size", 0) == 0:
        return None

    arr = np.nan_to_num(audio.flatten(), nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    if arr.size < int(sample_rate * (min_speech_ms / 1000.0)):
        logger.debug("Voiceprint extraction aborted: audio buffer shorter than min duration %.0f ms", min_speech_ms)
        return None

    # Step 1: Pre-filter audio with human speech bandpass filter
    filtered = speech_bandpass_filter(arr, sample_rate=sample_rate, lowcut=80.0, highcut=7500.0)
    rms_level = calculate_rms(filtered)
    if rms_level < 0.008:
        logger.debug("Voiceprint extraction aborted: RMS %.4f below minimum speech energy", rms_level)
        return None

    # Step 2: Short-Time Fourier Transform (STFT) frame decomposition
    frame_len = int(sample_rate * 0.030)  # 30ms window (480 samples at 16kHz)
    hop_len = int(sample_rate * 0.015)    # 15ms hop (240 samples at 16kHz)
    n_fft = 512

    if filtered.size < frame_len:
        return None

    n_frames = (filtered.size - frame_len) // hop_len + 1
    if n_frames < 8:
        return None

    window = np.hanning(frame_len).astype(np.float32)
    frames = np.lib.stride_tricks.as_strided(
        filtered,
        shape=(n_frames, frame_len),
        strides=(filtered.strides[0] * hop_len, filtered.strides[0]),
    )
    windowed = frames * window

    # Compute power spectrum
    spectrum = np.abs(np.fft.rfft(windowed, n=n_fft)) ** 2  # shape: (n_frames, 257)

    # Frame-level Voice Activity filter: keep top 75% highest-energy frames
    frame_energies = np.sum(spectrum, axis=1)
    thresh = np.percentile(frame_energies, 25)
    voiced_mask = frame_energies >= thresh
    if np.sum(voiced_mask) < 4:
        return None
    voiced_spectrum = spectrum[voiced_mask]

    # Step 3: Feature Bank 1 - Mel Filterbank Energies (32 dimensions)
    mel_fb = _mel_filterbank(num_filters=32, n_fft=n_fft, sample_rate=sample_rate)
    mel_energies = np.dot(voiced_spectrum, mel_fb.T)  # shape: (n_voiced, 32)
    log_mel = np.log10(np.maximum(mel_energies, 1e-6))
    f_mel_mean = np.mean(log_mel, axis=0)  # 32 dims

    # Step 4: Feature Bank 2 - Spectral Shape Moments (16 dimensions)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sample_rate)
    sum_p = np.maximum(np.sum(voiced_spectrum, axis=1, keepdims=True), 1e-8)
    norm_p = voiced_spectrum / sum_p

    # Spectral Centroid
    centroid = np.sum(norm_p * freqs, axis=1)
    # Spectral Spread / Variance
    spread = np.sqrt(np.sum(norm_p * (freqs - centroid[:, None]) ** 2, axis=1))
    # Spectral Flux (frame-to-frame change)
    flux = np.sqrt(np.sum(np.diff(voiced_spectrum, axis=0) ** 2, axis=1)) if len(voiced_spectrum) > 1 else np.array([0.0])

    f_centroid_stats = [
        float(np.mean(centroid)),
        float(np.std(centroid)),
        float(np.percentile(centroid, 25)),
        float(np.percentile(centroid, 75)),
    ]
    f_spread_stats = [
        float(np.mean(spread)),
        float(np.std(spread)),
        float(np.percentile(spread, 25)),
        float(np.percentile(spread, 75)),
    ]
    f_flux_stats = [
        float(np.mean(flux)),
        float(np.std(flux)),
        float(np.max(flux)),
        float(np.min(flux)),
    ]
    f_energy_stats = [
        float(np.mean(frame_energies)),
        float(np.std(frame_energies)),
        float(rms_level),
        float(np.max(frame_energies) / max(1e-5, np.min(frame_energies))),
    ]
    f_spectral = np.array(f_centroid_stats + f_spread_stats + f_flux_stats + f_energy_stats, dtype=np.float32)  # 16 dims

    # Step 5: Feature Bank 3 - Harmonic Ratio & Temporal Dynamics (16 dimensions)
    # Low-vs-high spectral energy ratio across subbands (0-1kHz, 1-2kHz, 2-4kHz, 4-8kHz)
    band_0_1k = np.mean(voiced_spectrum[:, (freqs >= 100) & (freqs < 1000)], axis=1)
    band_1_2k = np.mean(voiced_spectrum[:, (freqs >= 1000) & (freqs < 2000)], axis=1)
    band_2_4k = np.mean(voiced_spectrum[:, (freqs >= 2000) & (freqs < 4000)], axis=1)
    band_4_8k = np.mean(voiced_spectrum[:, (freqs >= 4000) & (freqs <= 7500)], axis=1)

    ratios = np.column_stack([
        band_0_1k / np.maximum(band_1_2k, 1e-6),
        band_1_2k / np.maximum(band_2_4k, 1e-6),
        band_2_4k / np.maximum(band_4_8k, 1e-6),
        band_0_1k / np.maximum(band_4_8k, 1e-6),
    ])
    f_harmonics = np.concatenate([
        np.mean(ratios, axis=0),
        np.std(ratios, axis=0),
        np.percentile(ratios, 10, axis=0),
        np.percentile(ratios, 90, axis=0),
    ]).astype(np.float32)  # 16 dims

    # Concatenate all 3 feature banks: 32 + 16 + 16 = 64 dimensions
    raw_vector = np.concatenate([f_mel_mean, f_spectral, f_harmonics]).astype(np.float32)

    # Step 6: Normalize to unit hypersphere for fast Cosine Distance
    norm = float(np.linalg.norm(raw_vector))
    if norm < 1e-7 or math.isnan(norm) or math.isinf(norm):
        return None

    unit_vector = raw_vector / norm
    return unit_vector.astype(np.float32)


def compute_cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Calculates cosine similarity between two unit vectors: dot(a, b)."""
    if vec_a is None or vec_b is None:
        return 0.0
    if vec_a.shape != vec_b.shape:
        return 0.0
    dot_product = float(np.dot(vec_a, vec_b))
    # Clamp to [-1.0, 1.0] to guard against IEEE float rounding
    return max(-1.0, min(1.0, dot_product))


@dataclass
class VoiceprintProfile:
    """Stored acoustic voiceprint profile for an enrolled speaker."""
    speaker_name: str
    embedding: list[float]
    sample_count: int = 1
    enrolled_at: float = field(default_factory=time.time)
    threshold: float = DEFAULT_VERIFICATION_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceprintProfile:
        return cls(
            speaker_name=str(data["speaker_name"]),
            embedding=[float(x) for x in data["embedding"]],
            sample_count=int(data.get("sample_count", 1)),
            enrolled_at=float(data.get("enrolled_at", time.time())),
            threshold=float(data.get("threshold", DEFAULT_VERIFICATION_THRESHOLD)),
        )


class VoiceBiometricsManager:
    """
    Manages voiceprint profiles, speaker enrollment, and real-time verification.
    Guarantees thread-safety and Windows atomic disk persistence.
    """

    def __init__(
        self,
        storage_path: Path | str = DEFAULT_PROFILE_PATH,
        default_threshold: float = DEFAULT_VERIFICATION_THRESHOLD,
        allow_unregistered_when_empty: bool = True,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.default_threshold = float(default_threshold)
        self.allow_unregistered_when_empty = allow_unregistered_when_empty
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()
        self._profiles: dict[str, VoiceprintProfile] = {}
        self._load_profiles()

    @property
    def enrolled_speakers(self) -> list[str]:
        """Returns list of currently enrolled speaker profile names."""
        with self._lock:
            return list(self._profiles.keys())

    def _load_profiles(self) -> None:
        """Loads profiles from JSON file if present."""
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._profiles.clear()
                for item in data.get("profiles", []):
                    prof = VoiceprintProfile.from_dict(item)
                    self._profiles[prof.speaker_name] = prof
            logger.info("Loaded %d voiceprint profile(s) from %s", len(self._profiles), self.storage_path)
        except Exception as e:
            logger.error("Failed to load voiceprint profiles from %s: %s", self.storage_path, e)

    def _save_profiles(self) -> bool:
        """
        Saves profiles to disk using Windows Atomic Persistence:
        Writes to .tmp.<tid>.<timestamp_ns> and replaces target file atomically.
        """
        with self._save_lock:
            with self._lock:
                payload = {
                    "version": 1,
                    "updated_at": time.time(),
                    "profiles": [p.to_dict() for p in self._profiles.values()],
                }
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            tid = threading.get_ident()
            now_ns = time.time_ns()
            tmp_path = self.storage_path.with_name(f"{self.storage_path.name}.tmp.{tid}.{now_ns}")

            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)

                # Retry loop for Windows OS file locks (WinError 5: Access is denied)
                for attempt in range(5):
                    try:
                        tmp_path.replace(self.storage_path)
                        return True
                    except OSError:
                        if attempt == 4:
                            raise
                        time.sleep(0.02 * (attempt + 1))
            except Exception as e:
                logger.error("Failed atomic replace saving voiceprint profiles: %s", e)
                return False
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
        return False

    def enroll(
        self,
        speaker_name: str,
        audio: np.ndarray,
        sample_rate: int = 16000,
        threshold: float | None = None,
    ) -> bool:
        """
        Enrolls a speaker voiceprint from audio samples.
        If the speaker already exists, merges with existing voiceprint via vector averaging.

        Args:
            speaker_name: Unique identifier for the speaker (e.g. 'master').
            audio: Speech audio buffer (1D float32 array).
            sample_rate: Audio sampling frequency in Hz.
            threshold: Optional custom verification threshold (default 0.80).

        Returns:
            bool: True if enrolled successfully, False otherwise.
        """
        if not speaker_name or not speaker_name.strip():
            logger.warning("Enrollment rejected: empty speaker name")
            return False

        clean_name = speaker_name.strip()
        embedding = extract_voiceprint(audio, sample_rate=sample_rate)
        if embedding is None:
            logger.warning("Enrollment failed for '%s': audio lacked valid speech features", clean_name)
            return False

        with self._lock:
            existing = self._profiles.get(clean_name)
            if existing is not None:
                # Merge: weighted average with previous embedding
                old_vec = np.array(existing.embedding, dtype=np.float32)
                n = existing.sample_count
                merged = (old_vec * n + embedding) / (n + 1)
                norm = float(np.linalg.norm(merged))
                merged = merged / max(norm, 1e-7)
                existing.embedding = merged.tolist()
                existing.sample_count += 1
                existing.enrolled_at = time.time()
                if threshold is not None:
                    existing.threshold = float(threshold)
                logger.info("Updated existing voiceprint profile '%s' (samples: %d)", clean_name, existing.sample_count)
            else:
                self._profiles[clean_name] = VoiceprintProfile(
                    speaker_name=clean_name,
                    embedding=embedding.tolist(),
                    sample_count=1,
                    threshold=float(threshold) if threshold is not None else self.default_threshold,
                )
                logger.info("Created new voiceprint profile '%s'", clean_name)

        return self._save_profiles()

    def verify(
        self,
        audio: np.ndarray,
        speaker_name: str = "master",
        sample_rate: int = 16000,
    ) -> tuple[bool, float]:
        """
        Verifies if candidate audio matches the enrolled speaker profile.

        Args:
            audio: Speech audio buffer to verify.
            speaker_name: Enrolled speaker profile name to test against.
            sample_rate: Audio sampling frequency.

        Returns:
            Tuple[bool, float]: (is_authenticated, similarity_score)
        """
        clean_name = speaker_name.strip()
        with self._lock:
            profile = self._profiles.get(clean_name)
            total_profiles = len(self._profiles)

        # Fail-open policy if no profile enrolled yet (onboarding mode)
        if profile is None:
            if total_profiles == 0 and self.allow_unregistered_when_empty:
                logger.debug("No voiceprint profiles registered; allowing unverified speaker (onboarding mode)")
                return True, 1.0
            logger.warning("Verification failed: profile '%s' does not exist", clean_name)
            return False, 0.0

        candidate_vec = extract_voiceprint(audio, sample_rate=sample_rate)
        if candidate_vec is None:
            logger.debug("Verification failed: candidate audio lacked sufficient speech features")
            return False, 0.0

        target_vec = np.array(profile.embedding, dtype=np.float32)
        score = compute_cosine_similarity(candidate_vec, target_vec)
        is_match = bool(score >= profile.threshold)

        logger.info(
            "Speaker verification for '%s': score=%.4f (threshold=%.2f) -> %s",
            clean_name,
            score,
            profile.threshold,
            "PASS" if is_match else "REJECT",
        )
        return is_match, score

    def get_profile(self, speaker_name: str) -> VoiceprintProfile | None:
        """Retrieves an enrolled profile by speaker name."""
        clean_name = speaker_name.strip()
        with self._lock:
            prof = self._profiles.get(clean_name)
            if prof is None:
                return None
            return VoiceprintProfile.from_dict(prof.to_dict())

    def enroll_speaker(
        self,
        speaker_name: str,
        audio: np.ndarray,
        sample_rate: int = 16000,
        threshold: float | None = None,
    ) -> tuple[bool, str]:
        """Convenience alias returning (success, message)."""
        ok = self.enroll(speaker_name=speaker_name, audio=audio, sample_rate=sample_rate, threshold=threshold)
        if ok:
            return True, f"Speaker '{speaker_name}' enrolled successfully"
        return False, f"Failed to enroll speaker '{speaker_name}'"

    def verify_speaker(
        self,
        audio: np.ndarray,
        speaker_name: str | None = None,
        sample_rate: int = 16000,
        threshold: float | None = None,
    ) -> tuple[bool, str, float]:
        """
        Convenience alias verifying speaker against specific profile or best match.
        Returns: (verified, matched_speaker_name, similarity_score)
        """
        with self._lock:
            speakers = list(self._profiles.keys())

        if not speakers:
            if self.allow_unregistered_when_empty:
                return True, "unregistered_guest", 1.0
            return False, "none", 0.0

        target = speaker_name if speaker_name else speakers[0]
        match, score = self.verify(audio=audio, speaker_name=target, sample_rate=sample_rate)
        if threshold is not None:
            match = bool(score >= threshold)
        return match, target, score

    def delete_profile(self, speaker_name: str) -> bool:
        """Removes a speaker profile and updates persistent storage."""
        clean_name = speaker_name.strip()
        with self._lock:
            if clean_name in self._profiles:
                del self._profiles[clean_name]
                logger.info("Deleted voiceprint profile '%s'", clean_name)
            else:
                return False
        return self._save_profiles()

    def clear(self) -> bool:
        """Clears all voiceprint profiles."""
        with self._lock:
            self._profiles.clear()
        return self._save_profiles()

