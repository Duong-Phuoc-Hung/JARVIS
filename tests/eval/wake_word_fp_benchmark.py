"""
tests/eval/wake_word_fp_benchmark.py
=====================================
H-06 deterministic wake-word false-positive / true-recall benchmark.

Evaluates jarvis.audio.wake_word.AcousticSpectralDetector (the Tier-2
zero-dependency acoustic fallback -- the component most exposed to false
positives now that it is no longer an unconditional supplementary check
alongside a working Tier-1 engine, see the H-06 engine-selection-policy
fix in jarvis/audio/wake_word.py) directly, in isolation from Tier-1
engine availability, using deterministic seeded synthetic audio -- no live
microphone recordings required, fully reproducible.

Positive class: generate_wake_word_signal() (the project's own synthetic
"Hey JARVIS" acoustic model) at several amplitudes, noise floors, and
source sample rates (resampled to the detector's target rate, exactly as
the real production feed_audio_block() path does).

Negative classes (all deterministic, seeded):
  - silence
  - white_noise
  - fan_rumble        (low-frequency 60-150 Hz rumble + 1/f-ish noise)
  - music_harmonic     (stacked harmonic tones + soft percussion transient)
  - speech_like        (formant-ish voiced segments, NOT the wake phonemes)
  - conversation_proxy (multiple overlapping speech-like talkers)
  - pure_tone          (single sine wave, various frequencies)
  - clap_impulse       (short broadband impulses)
  - clipping           (heavily saturated/clipped waveform)
  - tts_like_voice     (voice-like synthetic speech without "jarvis")

Run as a script to print + persist a report:
  python tests/eval/wake_word_fp_benchmark.py --out docs/eval/wake_word_fp_benchmark_results.json
"""
from __future__ import annotations

import argparse
import json
import zlib
from pathlib import Path
from typing import Any, Callable

import numpy as np

from jarvis.audio.wake_word import AcousticSpectralDetector, generate_wake_word_signal, resample_audio

ROOT = Path(__file__).resolve().parent.parent.parent
TARGET_SR = 16000


# ============================================================================
# Deterministic synthetic negative-class generators (all seeded)
# ============================================================================

def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def gen_silence(seed: int, sample_rate: int, duration_s: float = 1.2) -> np.ndarray:
    n = int(sample_rate * duration_s)
    # Not perfectly zero -- a tiny noise floor, as a real "silent" room mic still has one.
    return (_rng(seed).normal(0.0, 0.0005, n)).astype(np.float32)


def gen_white_noise(seed: int, sample_rate: int, duration_s: float = 1.2, rms: float = 0.05) -> np.ndarray:
    n = int(sample_rate * duration_s)
    noise = _rng(seed).normal(0.0, 1.0, n).astype(np.float32)
    cur = float(np.sqrt(np.mean(noise ** 2))) or 1.0
    return (noise * (rms / cur)).astype(np.float32)


def gen_fan_rumble(seed: int, sample_rate: int, duration_s: float = 1.2, rms: float = 0.04) -> np.ndarray:
    n = int(sample_rate * duration_s)
    t = np.linspace(0.0, duration_s, n, endpoint=False)
    rng = _rng(seed)
    base_freq = float(rng.uniform(60.0, 150.0))
    rumble = np.sin(2 * np.pi * base_freq * t) + 0.4 * np.sin(2 * np.pi * base_freq * 1.7 * t)
    low_noise = rng.normal(0.0, 1.0, n)
    # Crude low-pass via moving average to emphasize low-frequency content.
    kernel = np.ones(15) / 15.0
    low_noise = np.convolve(low_noise, kernel, mode="same")
    sig = rumble + 0.6 * low_noise
    cur = float(np.sqrt(np.mean(sig ** 2))) or 1.0
    return (sig * (rms / cur)).astype(np.float32)


def gen_music_harmonic(seed: int, sample_rate: int, duration_s: float = 1.2, rms: float = 0.08) -> np.ndarray:
    n = int(sample_rate * duration_s)
    t = np.linspace(0.0, duration_s, n, endpoint=False)
    rng = _rng(seed)
    f0 = float(rng.uniform(110.0, 440.0))
    sig = np.zeros(n, dtype=np.float64)
    for h, amp in ((1, 0.5), (2, 0.3), (3, 0.2), (4, 0.1)):
        sig += amp * np.sin(2 * np.pi * f0 * h * t)
    # A soft percussive transient partway through, decaying envelope.
    onset = int(n * 0.4)
    dur = int(sample_rate * 0.15)
    if onset + dur <= n:
        env = np.exp(-np.linspace(0, 8, dur))
        sig[onset:onset + dur] += 0.6 * env * rng.normal(0.0, 1.0, dur)
    cur = float(np.sqrt(np.mean(sig ** 2))) or 1.0
    return (sig * (rms / cur)).astype(np.float32)


def _formant_voiced_segment(rng: np.random.Generator, n: int, sample_rate: int, f0: float) -> np.ndarray:
    t = np.linspace(0.0, n / sample_rate, n, endpoint=False)
    f1 = float(rng.uniform(500.0, 900.0))
    f2 = float(rng.uniform(1100.0, 1800.0))
    env = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    voiced = (
        0.5 * np.sin(2 * np.pi * f0 * t)
        + 0.3 * np.sin(2 * np.pi * f1 * t)
        + 0.2 * np.sin(2 * np.pi * f2 * t)
    )
    return (env * voiced).astype(np.float64)


def gen_speech_like(seed: int, sample_rate: int, duration_s: float = 1.2, rms: float = 0.06) -> np.ndarray:
    """Voiced-formant-like segments at random timings/pitches -- deliberately
    NOT matching the wake phrase's specific two-syllable mid->high spectral
    order (see generate_wake_word_signal's docstring for that structure)."""
    n = int(sample_rate * duration_s)
    rng = _rng(seed)
    sig = np.zeros(n, dtype=np.float64)
    n_segments = int(rng.integers(2, 4))
    for _ in range(n_segments):
        seg_dur = int(sample_rate * rng.uniform(0.15, 0.35))
        start = int(rng.uniform(0, max(1, n - seg_dur)))
        f0 = float(rng.uniform(90.0, 220.0))
        sig[start:start + seg_dur] += _formant_voiced_segment(rng, seg_dur, sample_rate, f0)
    cur = float(np.sqrt(np.mean(sig ** 2))) or 1.0
    return (sig * (rms / cur)).astype(np.float32)


def gen_conversation_proxy(seed: int, sample_rate: int, duration_s: float = 1.2, rms: float = 0.07) -> np.ndarray:
    """Two overlapping speech-like 'talkers' at different pitches -- a crude
    background-conversation proxy."""
    a = gen_speech_like(seed, sample_rate, duration_s, rms=rms)
    b = gen_speech_like(seed + 1000, sample_rate, duration_s, rms=rms * 0.8)
    sig = a + np.roll(b, int(sample_rate * 0.2))
    cur = float(np.sqrt(np.mean(sig ** 2))) or 1.0
    return (sig * (rms / cur)).astype(np.float32)


def gen_pure_tone(seed: int, sample_rate: int, duration_s: float = 1.2, rms: float = 0.1) -> np.ndarray:
    n = int(sample_rate * duration_s)
    t = np.linspace(0.0, duration_s, n, endpoint=False)
    freq = float(_rng(seed).uniform(200.0, 4000.0))
    sig = np.sin(2 * np.pi * freq * t)
    cur = float(np.sqrt(np.mean(sig ** 2))) or 1.0
    return (sig * (rms / cur)).astype(np.float32)


def gen_clap_impulse(seed: int, sample_rate: int, duration_s: float = 1.2, peak: float = 0.9) -> np.ndarray:
    n = int(sample_rate * duration_s)
    rng = _rng(seed)
    sig = rng.normal(0.0, 0.001, n)
    n_claps = int(rng.integers(1, 3))
    for _ in range(n_claps):
        pos = int(rng.uniform(0, n - 200))
        impulse_len = 80
        env = np.exp(-np.linspace(0, 12, impulse_len))
        sig[pos:pos + impulse_len] += peak * env * rng.normal(0.0, 1.0, impulse_len)
    return np.clip(sig, -1.0, 1.0).astype(np.float32)


def gen_clipping(seed: int, sample_rate: int, duration_s: float = 1.2) -> np.ndarray:
    base = gen_music_harmonic(seed, sample_rate, duration_s, rms=0.3)
    return np.clip(base * 6.0, -1.0, 1.0).astype(np.float32)


def gen_tts_like_voice(seed: int, sample_rate: int, duration_s: float = 1.2, rms: float = 0.07) -> np.ndarray:
    """Smoother, more consistently-voiced synthetic speech (TTS-like), still
    deliberately not containing the wake phrase's phonetic structure."""
    n = int(sample_rate * duration_s)
    rng = _rng(seed)
    t = np.linspace(0.0, duration_s, n, endpoint=False)
    f0 = float(rng.uniform(120.0, 200.0))
    f0_drift = f0 + 15.0 * np.sin(2 * np.pi * 2.0 * t)
    phase = 2 * np.pi * np.cumsum(f0_drift) / sample_rate
    sig = 0.6 * np.sin(phase) + 0.25 * np.sin(2 * phase) + 0.15 * np.sin(3 * phase)
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 1.5 * t)  # slow amplitude modulation
    sig = sig * env
    cur = float(np.sqrt(np.mean(sig ** 2))) or 1.0
    return (sig * (rms / cur)).astype(np.float32)


NEGATIVE_CLASSES: dict[str, Callable[..., np.ndarray]] = {
    "silence": gen_silence,
    "white_noise": gen_white_noise,
    "fan_rumble": gen_fan_rumble,
    "music_harmonic": gen_music_harmonic,
    "speech_like": gen_speech_like,
    "conversation_proxy": gen_conversation_proxy,
    "pure_tone": gen_pure_tone,
    "clap_impulse": gen_clap_impulse,
    "clipping": gen_clipping,
    "tts_like_voice": gen_tts_like_voice,
}

# How many deterministic seeded variants per negative class.
VARIANTS_PER_NEGATIVE_CLASS = 8

# Positive class parameter sweep: (amplitude, noise_floor_rms, source_sample_rate).
POSITIVE_SWEEP: list[tuple[float, float, int]] = [
    (0.80, 0.002, 16000),
    (0.80, 0.002, 44100),
    (0.50, 0.002, 16000),
    (0.95, 0.002, 16000),
    (0.80, 0.010, 16000),
    (0.80, 0.020, 16000),
    (0.35, 0.002, 16000),
    (0.80, 0.002, 8000),
    (0.80, 0.002, 48000),
]


def _make_detector(sensitivity: float = 0.5) -> AcousticSpectralDetector:
    return AcousticSpectralDetector(sample_rate=TARGET_SR)


def run_benchmark(sensitivity: float = 0.5) -> dict[str, Any]:
    detector = _make_detector(sensitivity)

    # --- Positives ---
    positive_rows = []
    tp = fn = 0
    for i, (amp, noise_floor, src_sr) in enumerate(POSITIVE_SWEEP):
        np.random.seed(1000 + i)  # generate_wake_word_signal uses np.random internally
        sig = generate_wake_word_signal(sample_rate=src_sr, peak_amp=amp, noise_floor_rms=noise_floor)
        buf = resample_audio(sig, src_sr, TARGET_SR)
        detected, keyword, confidence = detector.analyze_window(buf, sensitivity=sensitivity)
        positive_rows.append({
            "amplitude": amp, "noise_floor_rms": noise_floor, "source_sample_rate": src_sr,
            "detected": detected, "confidence": confidence,
        })
        if detected:
            tp += 1
        else:
            fn += 1

    # --- Negatives ---
    negative_rows = []
    fp_by_class: dict[str, int] = {}
    fp = tn = 0
    for class_name, gen_fn in NEGATIVE_CLASSES.items():
        class_fp = 0
        for variant in range(VARIANTS_PER_NEGATIVE_CLASS):
            # zlib.crc32 (NOT Python's built-in hash(), which is salted per
            # process via PYTHONHASHSEED for strings and therefore NOT
            # reproducible across runs/processes) -- this must be genuinely
            # deterministic for the benchmark's "reproducible" claim to hold.
            seed = zlib.crc32(f"{class_name}:{variant}".encode("utf-8"))
            buf = gen_fn(seed, TARGET_SR)
            detected, keyword, confidence = detector.analyze_window(buf, sensitivity=sensitivity)
            negative_rows.append({
                "class": class_name, "variant": variant, "detected": detected, "confidence": confidence,
            })
            if detected:
                fp += 1
                class_fp += 1
            else:
                tn += 1
        fp_by_class[class_name] = class_fp

    n_pos = tp + fn
    n_neg = fp + tn
    recall = tp / n_pos if n_pos else 0.0
    fpr = fp / n_neg if n_neg else 0.0

    return {
        "sensitivity": sensitivity,
        "target_sample_rate": TARGET_SR,
        "positive": {
            "n": n_pos, "tp": tp, "fn": fn, "recall": recall,
            "rows": positive_rows,
        },
        "negative": {
            "n": n_neg, "fp": fp, "tn": tn, "false_positive_rate": fpr,
            "fp_by_class": fp_by_class,
            "variants_per_class": VARIANTS_PER_NEGATIVE_CLASS,
            "rows": negative_rows,
        },
    }


def print_report(result: dict[str, Any]) -> None:
    pos, neg = result["positive"], result["negative"]
    print(f"Wake-word acoustic detector benchmark (sensitivity={result['sensitivity']})")
    print(f"  Positives: {pos['tp']}/{pos['n']} TP (recall={pos['recall']:.1%}), {pos['fn']} FN")
    print(f"  Negatives: {neg['fp']}/{neg['n']} FP (FPR={neg['false_positive_rate']:.1%}), {neg['tn']} TN")
    print("  FP by class:")
    for cls, count in neg["fp_by_class"].items():
        print(f"    {cls:20s}: {count}/{neg['variants_per_class']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="H-06 deterministic wake-word FP/recall benchmark")
    parser.add_argument("--sensitivity", type=float, default=0.5)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    result = run_benchmark(sensitivity=args.sensitivity)
    print_report(result)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
