"""
tests/eval/generate_independent_audio.py
=========================================
Synthesizes the authentic independent Vietnamese test dataset (A1, A2) for JARVIS
voice pipeline and intent routing evaluation.

Ground truth: 210 distinct Vietnamese phrases from `tests/eval/independent_test_manifest.py`
Conditions:
  - clean: 210 authentic 16kHz mono WAV files synthesized with high-fidelity neural voices.
  - noisy: 210 perturbed 16kHz mono WAV files with realistic acoustic noise (SNR ~10-15dB).
Total: 420 audio WAV files conforming to 16000 Hz, 1 channel, valid WAV headers.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import soundfile as sf
from scipy import signal

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests.eval.independent_test_manifest import INDEPENDENT_MANIFEST

DEFAULT_OUTPUT_DIR = ROOT / "tests" / "eval" / "audio_independent"
VOICES = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]


def create_ambient_noise(num_samples: int, sample_rate: int = 16000, seed: int = 42) -> np.ndarray:
    """
    Generates realistic ambient indoor / office background noise:
    - Low-frequency HVAC / computer fan rumble (low-pass filtered white noise)
    - Pink-ish ambient room reflection
    - Gentle wideband acoustic background
    """
    rng = np.random.default_rng(seed)

    # 1. White noise baseline
    white = rng.standard_normal(num_samples).astype(np.float32)

    # 2. Low-frequency HVAC/fan rumble (Butterworth low-pass at 400 Hz)
    sos_fan = signal.butter(4, 400, "lp", fs=sample_rate, output="sos")
    fan_noise = signal.sosfilt(sos_fan, white).astype(np.float32)
    fan_rms = np.sqrt(np.mean(fan_noise ** 2) + 1e-12)
    fan_noise = fan_noise / fan_rms

    # 3. Room ambient hum / mid-frequency background (band-pass 100 - 2000 Hz)
    sos_ambient = signal.butter(2, [100, 2000], "bp", fs=sample_rate, output="sos")
    ambient_noise = signal.sosfilt(sos_ambient, white).astype(np.float32)
    amb_rms = np.sqrt(np.mean(ambient_noise ** 2) + 1e-12)
    ambient_noise = ambient_noise / amb_rms

    # 4. Composite acoustic noise
    combined_noise = 0.65 * fan_noise + 0.30 * ambient_noise + 0.05 * white
    norm_rms = np.sqrt(np.mean(combined_noise ** 2) + 1e-12)
    return (combined_noise / norm_rms).astype(np.float32)


def add_acoustic_noise(clean_audio: np.ndarray, snr_db: float, seed: int = 42, sample_rate: int = 16000) -> np.ndarray:
    """
    Adds realistic acoustic noise to clean audio at target SNR in dB.
    """
    noise = create_ambient_noise(len(clean_audio), sample_rate=sample_rate, seed=seed)
    signal_power = float(np.mean(clean_audio ** 2))
    if signal_power <= 1e-9:
        return clean_audio.copy()

    # Target noise power based on target SNR
    target_noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    noise_power = float(np.mean(noise ** 2))
    scale = math.sqrt(target_noise_power / (noise_power + 1e-12))
    noisy = clean_audio + (noise * scale)

    # Prevent digital clipping
    peak = float(np.max(np.abs(noisy)))
    if peak > 0.95:
        noisy = noisy * (0.95 / peak)

    return noisy.astype(np.float32)


def resample_to_16k_mono(raw_bytes: bytes) -> np.ndarray:
    """
    Decodes audio bytes (e.g. MP3 from edge-tts or gTTS) and resamples
    to 16000 Hz 1-channel mono float32 array normalized to peak ~0.85.
    """
    audio_data, orig_sr = sf.read(io.BytesIO(raw_bytes), dtype="float32")

    # Downmix to mono if stereo or multi-channel
    if audio_data.ndim > 1:
        audio_data = np.mean(audio_data, axis=1)

    # Resample to 16000 Hz if needed
    if orig_sr != 16000:
        gcd = math.gcd(16000, orig_sr)
        up = 16000 // gcd
        down = orig_sr // gcd
        audio_16k = signal.resample_poly(audio_data, up, down).astype(np.float32)
    else:
        audio_16k = audio_data.astype(np.float32)

    # Peak normalization to ~0.85 (-1.4 dBFS)
    peak = float(np.max(np.abs(audio_16k)))
    if peak > 0:
        audio_16k = (audio_16k / peak) * 0.85

    return audio_16k


async def synthesize_edge_tts(text: str, voice: str, retries: int = 3) -> Optional[bytes]:
    """Synthesizes text using edge-tts."""
    import edge_tts

    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice)
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            if len(buf) > 0:
                return bytes(buf)
        except Exception as exc:
            if attempt == retries:
                print(f"    [edge-tts] Failed '{text}' ({voice}) attempt {attempt}: {exc}")
            await asyncio.sleep(0.5 * attempt)
    return None


def synthesize_gtts(text: str, lang: str = "vi") -> Optional[bytes]:
    """Fallback synthesizer using gTTS (Google Translate TTS)."""
    try:
        from gtts import gTTS
        fp = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.read()
    except Exception as exc:
        print(f"    [gTTS] Fallback error for '{text}': {exc}")
        return None


async def synthesize_phrase(text: str, idx: int) -> np.ndarray:
    """
    Synthesizes a Vietnamese phrase, alternating voices and falling back gracefully.
    Returns a 16kHz mono float32 numpy array.
    """
    voice = VOICES[idx % len(VOICES)]
    raw_audio = await synthesize_edge_tts(text, voice)

    if raw_audio is None:
        print(f"    Falling back to gTTS for: '{text}'")
        raw_audio = synthesize_gtts(text, lang="vi")

    if raw_audio is None:
        raise RuntimeError(f"All TTS backends failed for phrase: '{text}'")

    return resample_to_16k_mono(raw_audio)


def verify_audio_file(file_path: Path) -> bool:
    """Verifies that the audio file exists, is readable, 16kHz, mono, and non-empty."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return False
    try:
        info = sf.info(str(file_path))
        return info.samplerate == 16000 and info.channels == 1 and info.frames > 0
    except Exception:
        return False


async def generate_dataset(output_dir: Path, force: bool = False, snr_min: float = 10.0, snr_max: float = 15.0):
    clean_root = output_dir / "clean"
    noisy_root = output_dir / "noisy"

    clean_root.mkdir(parents=True, exist_ok=True)
    noisy_root.mkdir(parents=True, exist_ok=True)

    total_phrases = sum(len(phrases) for phrases in INDEPENDENT_MANIFEST.values())
    print(f"Starting audio synthesis for {total_phrases} independent utterances across {len(INDEPENDENT_MANIFEST)} intents...")
    print(f"Target conditions: 'clean' (16kHz mono) and 'noisy' (SNR {snr_min}-{snr_max}dB).")
    print(f"Output directory: {output_dir}\n")

    processed = 0
    skipped = 0
    errors = 0
    t0 = time.time()

    for intent, phrases in INDEPENDENT_MANIFEST.items():
        intent_clean_dir = clean_root / intent
        intent_noisy_dir = noisy_root / intent
        intent_clean_dir.mkdir(parents=True, exist_ok=True)
        intent_noisy_dir.mkdir(parents=True, exist_ok=True)

        for idx, phrase in enumerate(phrases):
            clean_wav = intent_clean_dir / f"variant_{idx}.wav"
            noisy_wav = intent_noisy_dir / f"variant_{idx}.wav"

            if not force and verify_audio_file(clean_wav) and verify_audio_file(noisy_wav):
                skipped += 1
                processed += 1
                continue

            try:
                # 1. Synthesize clean speech
                audio_16k = await synthesize_phrase(phrase, idx)

                # 2. Add realistic acoustic noise
                # Deterministic seed per intent & variant for reproducibility
                seed = (hash(f"{intent}_{idx}") & 0x7FFFFFFF) % 1000000
                snr_db = random.Random(seed).uniform(snr_min, snr_max)
                noisy_audio = add_acoustic_noise(audio_16k, snr_db=snr_db, seed=seed, sample_rate=16000)

                # 3. Write 16-bit PCM WAV files
                sf.write(str(clean_wav), audio_16k, 16000, subtype="PCM_16")
                sf.write(str(noisy_wav), noisy_audio, 16000, subtype="PCM_16")

                processed += 1
                if processed % 15 == 0 or processed == total_phrases:
                    elapsed = time.time() - t0
                    print(f"  [{processed:3d}/{total_phrases}] {intent}/variant_{idx}.wav ({elapsed:.1f}s) -> '{phrase}'")

                # Polite pause to avoid rate limiting
                await asyncio.sleep(0.05)

            except Exception as exc:
                print(f"  [ERROR] {intent}/variant_{idx}.wav ('{phrase}'): {exc}")
                errors += 1

    total_time = time.time() - t0
    print(f"\nSynthesis completed in {total_time:.1f}s!")
    print(f"Processed: {processed}, Skipped existing: {skipped}, Errors: {errors}")

    # Integrity verification
    clean_files = [f for f in clean_root.glob("*/*.wav")]
    noisy_files = [f for f in noisy_root.glob("*/*.wav")]
    all_files = clean_files + noisy_files

    print("\n" + "=" * 60)
    print("VERIFICATION OF INDEPENDENT DATASET")
    print("=" * 60)
    print(f"Clean WAV files: {len(clean_files)} / 210")
    print(f"Noisy WAV files: {len(noisy_files)} / 210")
    print(f"Total audio files: {len(all_files)} / 420")

    invalid = 0
    for wav_f in all_files:
        if not verify_audio_file(wav_f):
            print(f"  INVALID AUDIO: {wav_f}")
            invalid += 1

    if invalid == 0 and len(clean_files) == 210 and len(noisy_files) == 210:
        print("\nALL 420 FILES VERIFIED SUCCESSFULLY! (16000 Hz, 1 channel, valid PCM_16 WAV headers)")
        return 0
    else:
        print(f"\nVERIFICATION FAILED: {invalid} invalid files, expected 210 clean and 210 noisy.")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Generate independent Vietnamese audio test dataset")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Root directory for audio dataset (default: tests/eval/audio_independent)")
    parser.add_argument("--force", action="store_true", help="Force regenerate existing files")
    parser.add_argument("--snr-min", type=float, default=10.0, help="Minimum SNR in dB for noisy set")
    parser.add_argument("--snr-max", type=float, default=15.0, help="Maximum SNR in dB for noisy set")
    args = parser.parse_args()

    return asyncio.run(generate_dataset(args.output_dir, force=args.force, snr_min=args.snr_min, snr_max=args.snr_max))


if __name__ == "__main__":
    sys.exit(main())
