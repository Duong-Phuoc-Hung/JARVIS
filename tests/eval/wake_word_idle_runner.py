"""
tests/eval/wake_word_idle_runner.py
===================================
Empirical runner for H-06: Wake-word false positive evaluation under idle conditions.
Monitors the audio input stream over extended periods (e.g. 15-60 minutes) in idle
room conditions (quiet room, fan noise, typing, background music) and counts false triggers.

Usage:
  python tests/eval/wake_word_idle_runner.py --duration 60 --out tests/eval/results_wake_word_idle.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Fix Windows console utf-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wake_word_idle")


def run_idle_evaluation(duration_seconds: float, threshold: float = 0.5, out_path: Path | None = None) -> dict:
    """Run idle audio listening session and record any false wake-word activations."""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError as e:
        logger.error(f"Missing audio dependencies: {e}")
        return {"error": "MISSING_DEPENDENCY", "detail": str(e)}

    from jarvis.audio.engine import AudioEngine
    from jarvis.audio.wake_word import WakeWordDetector

    engine = AudioEngine()
    device_idx = engine.get_active_device()
    # None means use system default input device — valid for sounddevice
    if device_idx is None:
        logger.info("  Active device: system default (None)")

    logger.info(f"Starting Wake-Word Idle Soak Test:")
    logger.info(f"  Duration: {duration_seconds:.1f}s ({duration_seconds/60:.1f} minutes)")
    logger.info(f"  Active Device Index: {device_idx}")
    logger.info(f"  Sensitivity Threshold: {threshold}")

    detector = WakeWordDetector(vad_threshold=threshold)
    false_triggers = []
    start_time = time.time()
    last_heartbeat = start_time

    sample_rate = 16000
    chunk_size = 1280  # 80ms chunks for openWakeWord / Porcupine compatibility

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device_idx,
            blocksize=chunk_size,
        ) as stream:
            logger.info("Microphone stream opened successfully. Listening for false triggers...")
            while time.time() - start_time < duration_seconds:
                data, overflowed = stream.read(chunk_size)
                if overflowed:
                    logger.warning("Audio buffer overflowed during idle listen")

                audio_chunk = data.flatten()
                detected = detector.process_audio_block(audio_chunk)
                if detected:
                    elapsed = time.time() - start_time
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    false_triggers.append({
                        "elapsed_seconds": round(elapsed, 2),
                        "timestamp": timestamp,
                        "confidence": float(getattr(detector, "last_confidence", 1.0)),
                    })
                    logger.warning(f"FALSE TRIGGER DETECTED at {elapsed:.2f}s! Total: {len(false_triggers)}")

                if time.time() - last_heartbeat >= 30:
                    logger.info(f"Idle listening heartbeat: {time.time() - start_time:.0f}/{duration_seconds:.0f}s elapsed, {len(false_triggers)} false triggers")
                    last_heartbeat = time.time()

    except Exception as exc:
        logger.error(f"Error during audio stream capture: {exc}")
        return {
            "status": "FAILED",
            "error": "AUDIO_CAPTURE_ERROR",
            "detail": str(exc),
            "duration_attempted": time.time() - start_time,
            "false_triggers": false_triggers,
        }

    total_duration = time.time() - start_time
    hours = total_duration / 3600.0
    fp_per_hour = len(false_triggers) / hours if hours > 0 else 0.0

    report = {
        "status": "COMPLETED",
        "duration_seconds": round(total_duration, 2),
        "duration_minutes": round(total_duration / 60, 2),
        "target_duration_seconds": duration_seconds,
        "sample_rate": sample_rate,
        "device_index": device_idx,
        "sensitivity_threshold": threshold,
        "total_false_triggers": len(false_triggers),
        "false_positive_rate_per_hour": round(fp_per_hour, 2),
        "events": false_triggers,
    }

    logger.info(f"Idle test completed: {len(false_triggers)} false triggers in {total_duration:.1f}s ({fp_per_hour:.2f} FP/hr)")

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Report saved to {out_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="H-06 Wake-Word Idle False-Positive Runner")
    parser.add_argument("--duration", type=float, default=60.0, help="Test duration in seconds (default: 60s)")
    parser.add_argument("--threshold", type=float, default=0.5, help="Wake-word detection threshold")
    parser.add_argument("--out", type=str, default="tests/eval/results_wake_word_idle.json", help="Output path for JSON report")
    args = parser.parse_args()

    res = run_idle_evaluation(args.duration, args.threshold, Path(args.out))
    print(json.dumps(res, indent=2))
