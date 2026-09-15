"""
tests/eval/wake_word_idle_runner.py
===================================
H-06 empirical runner: wake-word false-positive evaluation under idle
background conditions (quiet room, fan, music, YouTube, background
conversation). Monitors the real audio input stream over an extended period
and records every wake-word trigger truthfully.

CORRECTED (H-06 measurement-harness audit) -- the previous version of this
runner had two confirmed defects that invalidated any evidence it produced:

1. It opened a 16kHz sd.InputStream but constructed WakeWordDetector with
   its DEFAULT sample_rate=44100 -- every incoming 16kHz block was
   mislabeled and resampled as if it were 44.1kHz audio (a ~2.75x
   time-compression/pitch-shift of the real signal). Fixed: the detector's
   sample_rate is now always set explicitly from the SAME value used to
   open the stream (--sample-rate, default 16000), never left to default.

2. --threshold was described/logged as a wake/sensitivity threshold but was
   actually passed into WakeWordDetector(vad_threshold=...) -- an unrelated
   RMS energy pre-filter gate, not the acoustic confidence threshold.
   Passing a sensitivity-range value (e.g. 0.5) into vad_threshold set an
   absurdly high energy gate that would silence the detector almost
   entirely, making any "0 false triggers" result meaningless (an artifact
   of the detector barely running at all, not evidence of good tuning).
   Fixed: --sensitivity and --vad-threshold are now two distinct,
   independently-documented CLI flags mapped to their real, separate
   WakeWordDetector parameters.

The historical result at docs/eval/wake_word_idle_results.json was produced
by the OLD, defective version of this script and must not be trusted as
genuine evidence of the system's false-positive rate -- see
docs/eval/wake_word_idle_runner_audit_note.md for the full account. It is
left unmodified (not rewritten) as historical record of what was actually
run; a corrected re-run must be a NEW, separately-named result.

Usage (see the bottom of this file / --help for the full flag list):

  Quiet room, 30 minutes:
    python tests/eval/wake_word_idle_runner.py --duration 1800 --condition quiet \
        --out docs/eval/wake_word_idle_quiet_results.json

  Fan noise, 30 minutes:
    python tests/eval/wake_word_idle_runner.py --duration 1800 --condition fan \
        --out docs/eval/wake_word_idle_fan_results.json

  Music playing, 30 minutes:
    python tests/eval/wake_word_idle_runner.py --duration 1800 --condition music \
        --out docs/eval/wake_word_idle_music_results.json

  YouTube video playing, 30 minutes:
    python tests/eval/wake_word_idle_runner.py --duration 1800 --condition youtube \
        --out docs/eval/wake_word_idle_youtube_results.json

  Background conversation, 30 minutes:
    python tests/eval/wake_word_idle_runner.py --duration 1800 --condition conversation \
        --out docs/eval/wake_word_idle_conversation_results.json

  Full 60-minute quiet-room soak (matches the original H-06 acceptance target):
    python tests/eval/wake_word_idle_runner.py --duration 3600 --condition quiet \
        --out docs/eval/wake_word_idle_quiet_60min_results.json

This module does NOT run or claim any live result on its own -- it only
provides the corrected harness. Live acceptance requires an operator with
real microphone hardware to actually execute these commands.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Fix Windows console utf-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wake_word_idle")

VALID_CONDITIONS = ("quiet", "fan", "music", "youtube", "conversation", "custom")


def run_idle_evaluation(
    duration_seconds: float,
    *,
    sensitivity: float = 0.5,
    vad_threshold: float = 0.003,
    sample_rate: int = 16000,
    condition: str = "quiet",
    condition_label: str | None = None,
    acoustic_fallback_policy: str = "auto",
    engine_override: str | None = None,
    device_index: int | None = None,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """
    Run an idle audio listening session and record every wake-word trigger
    truthfully, using the SAME sample rate for both the real input stream
    and the detector, and the real WakeWordResult from feed_audio_block()
    for every trigger's engine/confidence/keyword.
    """
    try:
        import sounddevice as sd
    except ImportError as e:
        logger.error(f"Missing audio dependencies: {e}")
        return {"error": "MISSING_DEPENDENCY", "detail": str(e)}

    from jarvis.audio.engine import AudioEngine
    from jarvis.audio.wake_word import WakeWordDetector

    if condition not in VALID_CONDITIONS:
        return {"error": "INVALID_CONDITION", "detail": f"condition must be one of {VALID_CONDITIONS}"}

    resolved_device = device_index
    if resolved_device is None:
        engine_probe = AudioEngine()
        resolved_device = engine_probe.get_active_device()
    if resolved_device is None:
        logger.info("  Active device: system default (None)")

    detector_config: dict[str, Any] = {"acoustic_fallback_policy": acoustic_fallback_policy}
    if engine_override:
        detector_config["engine"] = engine_override

    # H-06 fix: sample_rate is ALWAYS the exact value the real InputStream
    # below is opened with -- never left to WakeWordDetector's own default,
    # which previously silently mismatched a 16kHz stream against a 44.1kHz
    # detector.
    detector = WakeWordDetector(
        sample_rate=sample_rate,
        sensitivity=sensitivity,
        vad_threshold=vad_threshold,
        config=detector_config,
    )
    actual_engine = detector.engine_type

    logger.info("Starting Wake-Word Idle Soak Test (H-06):")
    logger.info(f"  Duration: {duration_seconds:.1f}s ({duration_seconds / 60:.1f} minutes)")
    logger.info(f"  Condition: {condition}" + (f" ({condition_label})" if condition_label else ""))
    logger.info(f"  Active Device Index: {resolved_device}")
    logger.info(f"  Configured sample_rate: {sample_rate} Hz (matches InputStream)")
    logger.info(f"  Sensitivity: {sensitivity}")
    logger.info(f"  VAD threshold (RMS energy gate): {vad_threshold}")
    logger.info(f"  Acoustic fallback policy: {acoustic_fallback_policy}")
    logger.info(f"  Detector engine actually selected: {actual_engine}")

    false_triggers: list[dict[str, Any]] = []
    start_time = time.time()
    start_monotonic = time.monotonic()
    last_heartbeat = start_time

    chunk_size = 1280  # 80ms chunks at 16kHz; scales proportionally at other rates below
    chunk_size = max(160, int(round(chunk_size * (sample_rate / 16000.0))))

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=resolved_device,
            blocksize=chunk_size,
        ) as stream:
            logger.info("Microphone stream opened successfully. Listening for false triggers...")
            while time.time() - start_time < duration_seconds:
                data, overflowed = stream.read(chunk_size)
                if overflowed:
                    logger.warning("Audio buffer overflowed during idle listen")

                audio_chunk = data.flatten()
                now_monotonic = time.monotonic()
                # H-06 fix: use the real WakeWordResult from feed_audio_block()
                # instead of the boolean-only process_audio_block() wrapper +
                # a nonexistent detector.last_confidence attribute -- engine/
                # confidence/keyword below are the detector's own truthful
                # values for THIS specific trigger, not a fabricated default.
                result = detector.feed_audio_block(audio_chunk, timestamp=now_monotonic)
                if result is not None:
                    elapsed = time.time() - start_time
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    false_triggers.append({
                        "elapsed_seconds": round(elapsed, 2),
                        "timestamp": timestamp,
                        "engine": result.engine,
                        "confidence": float(result.confidence),
                        "keyword": result.keyword,
                    })
                    logger.warning(
                        f"FALSE TRIGGER DETECTED at {elapsed:.2f}s! engine={result.engine} "
                        f"confidence={result.confidence:.3f} Total: {len(false_triggers)}"
                    )

                if time.time() - last_heartbeat >= 30:
                    logger.info(
                        f"Idle listening heartbeat: {time.time() - start_time:.0f}/{duration_seconds:.0f}s "
                        f"elapsed, {len(false_triggers)} false triggers"
                    )
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
        "condition": condition,
        "condition_label": condition_label,
        # Reproducibility metadata -- enough to re-run this exact configuration.
        "sample_rate": sample_rate,
        "chunk_size": chunk_size,
        "device_index": resolved_device,
        "sensitivity": sensitivity,
        "vad_threshold": vad_threshold,
        "acoustic_fallback_policy": acoustic_fallback_policy,
        "engine_override_requested": engine_override,
        "engine_selected": actual_engine,
        "cooldown_s": detector.cooldown_s,
        "total_false_triggers": len(false_triggers),
        "false_positive_rate_per_hour": round(fp_per_hour, 2),
        "events": false_triggers,
    }

    logger.info(
        f"Idle test completed: {len(false_triggers)} false triggers in {total_duration:.1f}s "
        f"({fp_per_hour:.2f} FP/hr), engine={actual_engine}, condition={condition}"
    )

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Report saved to {out_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="H-06 Wake-Word Idle False-Positive Runner (corrected)")
    parser.add_argument("--duration", type=float, default=60.0, help="Test duration in seconds (default: 60s)")
    parser.add_argument("--sensitivity", type=float, default=0.5, help="Wake-word acoustic sensitivity, 0.0-1.0 (default: 0.5)")
    parser.add_argument("--vad-threshold", type=float, default=0.003, help="VAD RMS energy pre-filter gate (default: 0.003)")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Sample rate for BOTH the InputStream and the detector (default: 16000)")
    parser.add_argument("--condition", type=str, default="quiet", choices=list(VALID_CONDITIONS), help="Named background condition")
    parser.add_argument("--condition-label", type=str, default=None, help="Free-text detail for --condition custom (e.g. 'window AC unit')")
    parser.add_argument("--acoustic-fallback-policy", type=str, default="auto", choices=["auto", "always"], help="Tier-2 acoustic fallback policy (default: auto)")
    parser.add_argument("--engine", type=str, default=None, help="Force a specific Tier-1 engine (e.g. 'whisper', 'mock') via WakeWordDetector config")
    parser.add_argument("--device", type=int, default=None, help="Explicit input device index (default: AudioEngine's active device)")
    parser.add_argument("--out", type=str, default="tests/eval/results_wake_word_idle.json", help="Output path for JSON report")
    args = parser.parse_args()

    res = run_idle_evaluation(
        args.duration,
        sensitivity=args.sensitivity,
        vad_threshold=args.vad_threshold,
        sample_rate=args.sample_rate,
        condition=args.condition,
        condition_label=args.condition_label,
        acoustic_fallback_policy=args.acoustic_fallback_policy,
        engine_override=args.engine,
        device_index=args.device,
        out_path=Path(args.out),
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
