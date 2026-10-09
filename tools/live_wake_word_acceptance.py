#!/usr/bin/env python3
"""
tools/live_wake_word_acceptance.py
==================================
Empirical Live Human Voice Wake-Word Acceptance Harness for JARVIS.
Directly tests the two-stage wake-word detector (OpenWakeWord Tier 1 + Whisper Tier 2 Verifier)
against real microphone audio, adhering strictly to AUDIT_FRAMEWORK.md and RULE[AGENTS.md].

Usage:
  # 1. Non-interactive dry run / device probe:
  python tools/live_wake_word_acceptance.py --probe-only

  # 2. Live true wake trial capture (10 spaced trials with 2.0s cooldown = min 25s duration):
  python tools/live_wake_word_acceptance.py --duration 25 --label true_wake --expected-wakes 10 --min-recall 0.95

  # 3. Ambient false alarm soak (minimum 120s duration floor):
  python tools/live_wake_word_acceptance.py --duration 120 --label ambient --min-ambient-seconds 120

Note on Trial Protocol:
  `expected_wakes` is operator-declared (minimum 10). The operator must utter 'Hey JARVIS' clearly in discrete
  trials spaced by at least (cooldown_s + 0.5s) to allow complete verifier reset between utterances.
  Observed trigger ratio is evaluated against credited detections capped at expected_wakes.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("wake_word_acceptance")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live Human Voice Wake-Word Acceptance Harness")
    parser.add_argument("--probe-only", action="store_true", help="Probe audio input devices and exit")
    parser.add_argument("--duration", type=float, default=25.0, help="Listening duration in seconds")
    parser.add_argument("--label", type=str, default="true_wake", choices=["true_wake", "ambient"])
    parser.add_argument(
        "--sensitivity",
        type=float,
        default=None,
        help="Optional wake-word sensitivity override [0.0 - 1.0]; defaults to production config",
    )
    parser.add_argument(
        "--expected-wakes",
        type=int,
        default=10,
        help="Expected wake count for true_wake label (must be >= 10)",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.95,
        help="Minimum required recall threshold for true_wake [0.95 - 1.0]",
    )
    parser.add_argument(
        "--min-ambient-seconds",
        type=float,
        default=120.0,
        help="Minimum required duration floor for ambient acceptance (must be >= 120.0 seconds)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output report file instead of generating a unique path",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "docs" / "eval" / "live_wake_word_acceptance_report.json",
    )

    args = parser.parse_args(argv)
    if args.expected_wakes < 10:
        parser.error("--expected-wakes cannot be lower than 10")
    if not (0.95 <= args.min_recall <= 1.0):
        parser.error("--min-recall cannot be lower than 0.95")
    if args.duration <= 0:
        parser.error("--duration must be positive (> 0)")
    if args.min_ambient_seconds < 120.0:
        parser.error("--min-ambient-seconds cannot be lower than 120.0 seconds")
    if args.sensitivity is not None and not (0.0 <= args.sensitivity <= 1.0):
        parser.error("--sensitivity must be between 0.0 and 1.0")
    return args


def get_production_wake_word_config() -> dict[str, Any] | None:
    """
    Load production wake_word configuration via jarvis.core.config.get_config.
    Returns the wake_word config dictionary if successfully loaded, or None if loading fails.
    """
    try:
        from jarvis.core.config import get_config

        cfg = get_config()
        if hasattr(cfg, "get"):
            wake_cfg = cfg.get("wake_word")
            if isinstance(wake_cfg, dict) and wake_cfg:
                return dict(wake_cfg)
            elif hasattr(wake_cfg, "to_dict"):
                d = wake_cfg.to_dict()
                if isinstance(d, dict) and d:
                    return d
    except Exception as exc:
        log.warning("Could not load production config via ConfigManager: %s", exc)
    return None


def _save_report(report: dict[str, Any], out_path: Path | None, overwrite: bool = False) -> Path | None:
    if not out_path:
        return None

    target_path = out_path
    if target_path.exists() and not overwrite:
        timestamp_ns = time.time_ns()
        target_path = out_path.with_name(f"{out_path.stem}_{timestamp_ns}{out_path.suffix}")
        while target_path.exists():
            timestamp_ns += 1
            target_path = out_path.with_name(f"{out_path.stem}_{timestamp_ns}{out_path.suffix}")
        log.warning("Output file %s exists and --overwrite is False. Writing to unique path: %s", out_path, target_path)

    report["saved_report_path"] = str(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Saved live wake-word report to: %s", target_path)
    return target_path


def run_wake_word_acceptance(
    args: argparse.Namespace,
    time_func: Callable[[], float] = time.monotonic,
    sleep_func: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    log.info("Starting Live Human Voice Wake-Word Acceptance Harness...")

    # 1. Load production config & verify configuration presence
    wake_config = get_production_wake_word_config()
    if not wake_config:
        log.error("[NOT_CONFIGURED] Failed to load production wake_word configuration.")
        report = {
            "status": "NOT_CONFIGURED",
            "success": False,
            "code": "CONFIG_LOAD_FAILED",
            "message": "Failed to load production wake_word configuration from ConfigManager.",
            "data": {},
            "retryable": False,
            "verdict": "PASS fail-closed, runtime evidence PENDING (CONFIG_LOAD_FAILED)",
        }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    try:
        production_sensitivity = float(wake_config["sensitivity"])
    except (KeyError, TypeError, ValueError):
        report = {
            "status": "NOT_CONFIGURED",
            "success": False,
            "code": "INVALID_PRODUCTION_SENSITIVITY",
            "message": "Production wake_word.sensitivity is missing or invalid.",
            "data": {},
            "retryable": False,
            "verdict": "PASS fail-closed, runtime evidence PENDING (INVALID_PRODUCTION_SENSITIVITY)",
        }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    applied_sensitivity = args.sensitivity if args.sensitivity is not None else production_sensitivity
    wake_config["sensitivity"] = applied_sensitivity
    cooldown_s = float(wake_config.get("cooldown_s", 2.0))
    trial_spacing_s = cooldown_s + 0.5

    # 2. Pre-check duration feasibility & acceptance floors
    if args.label == "true_wake":
        min_req_duration = args.expected_wakes * trial_spacing_s
        if args.duration < min_req_duration:
            log.error("[BLOCKED] True-wake duration is insufficient for expected wakes and cooldown.")
            report = {
                "status": "BLOCKED",
                "success": False,
                "code": "INSUFFICIENT_TRUE_WAKE_DURATION",
                "message": (
                    f"True-wake duration ({args.duration:.1f}s) is insufficient for {args.expected_wakes} "
                    f"trials spaced by {trial_spacing_s:.1f}s (minimum {min_req_duration:.1f}s required)."
                ),
                "data": {
                    "duration": args.duration,
                    "expected_wakes": args.expected_wakes,
                    "cooldown_s": cooldown_s,
                    "trial_spacing_s": trial_spacing_s,
                    "required_duration": min_req_duration,
                },
                "retryable": True,
                "verdict": "BLOCKED (INSUFFICIENT_TRUE_WAKE_DURATION)",
            }
            _save_report(report, args.out, overwrite=args.overwrite)
            return report
    elif args.label == "ambient":
        if args.duration < args.min_ambient_seconds:
            log.error("[BLOCKED] Ambient duration is below minimum acceptance floor.")
            report = {
                "status": "BLOCKED",
                "success": False,
                "code": "INSUFFICIENT_AMBIENT_DURATION",
                "message": (
                    f"Ambient duration ({args.duration:.1f}s) is below minimum acceptance floor "
                    f"({args.min_ambient_seconds:.1f}s)."
                ),
                "data": {
                    "duration": args.duration,
                    "min_ambient_seconds": args.min_ambient_seconds,
                },
                "retryable": True,
                "verdict": "BLOCKED (INSUFFICIENT_AMBIENT_DURATION)",
            }
            _save_report(report, args.out, overwrite=args.overwrite)
            return report

    # 3. Check sounddevice availability
    try:
        import sounddevice as sd
    except ImportError as exc:
        log.error("sounddevice is not installed: %s", exc)
        report = {
            "status": "UNAVAILABLE",
            "success": False,
            "code": "MISSING_SOUNDDEVICE",
            "message": f"sounddevice library is not installed: {exc}",
            "data": {"missing_dependency": "sounddevice"},
            "retryable": False,
            "verdict": "PASS fail-closed (MISSING_SOUNDDEVICE)",
            "evidence": {"missing_dependency": "sounddevice"},
        }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    # 4. Probe audio devices
    try:
        devices = sd.query_devices()
        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
        default_in = sd.default.device[0] if hasattr(sd.default, "device") else None
    except Exception as exc:
        log.warning("Could not query audio devices: %s", exc)
        devices = []
        input_devices = []
        default_in = None

    log.info("Found %d audio input devices. Default input device index: %s", len(input_devices), default_in)

    if args.probe_only:
        probe_success = len(input_devices) > 0 and default_in is not None and default_in >= 0
        if probe_success:
            report = {
                "status": "SUCCESS",
                "success": True,
                "code": "PROBE_SUCCESS",
                "message": f"Successfully probed {len(input_devices)} audio input devices.",
                "data": {
                    "input_device_count": len(input_devices),
                    "default_input_device": default_in,
                    "input_devices": [
                        {"index": d.get("index", idx), "name": d.get("name"), "channels": d.get("max_input_channels")}
                        for idx, d in enumerate(input_devices)
                    ],
                },
                "retryable": False,
                "verdict": "PASS engineering",
                "evidence": {"input_device_count": len(input_devices)},
            }
        else:
            report = {
                "status": "UNAVAILABLE",
                "success": False,
                "code": "NO_MICROPHONE",
                "message": "Physical microphone device is unavailable or unconfigured.",
                "data": {"input_device_count": len(input_devices)},
                "retryable": True,
                "verdict": "PASS fail-closed, runtime evidence PENDING (NO_MICROPHONE)",
                "evidence": {"input_device_count": len(input_devices)},
            }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    if not input_devices or default_in is None or default_in < 0:
        log.warning("[UNAVAILABLE] No physical microphone available on this host.")
        report = {
            "status": "UNAVAILABLE",
            "success": False,
            "code": "NO_MICROPHONE",
            "message": "Physical microphone device is unavailable for live human voice test.",
            "data": {"input_device_count": len(input_devices)},
            "retryable": True,
            "verdict": "PASS fail-closed, runtime evidence PENDING (NO_MICROPHONE)",
            "evidence": {"input_device_count": len(input_devices)},
        }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    # 5. Instantiate detector & verify cascade prerequisites
    from jarvis.audio.wake_word import WakeWordDetector

    detections: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []

    def on_detect(phrase: str, score: float = 1.0) -> None:
        log.info("[WAKE WORD TRIGGERED] Detected phrase: %s (score=%.4f)", phrase, score)
        detections.append({"timestamp": time.time(), "phrase": phrase, "score": score})

    def on_score(event: Any) -> None:
        event_dict = event.to_dict() if hasattr(event, "to_dict") else {}
        scores.append(event_dict)

    try:
        detector = WakeWordDetector(
            sample_rate=16000,
            sensitivity=applied_sensitivity,
            on_wake_word=on_detect,
            on_score=on_score,
            config=wake_config,
        )
    except Exception as exc:
        log.error("[UNAVAILABLE] Wake-word detector initialization failed: %s", exc)
        report = {
            "status": "UNAVAILABLE",
            "success": False,
            "code": "DETECTOR_UNAVAILABLE",
            "message": f"Wake-word detector initialization failed: {exc}",
            "data": {"error_type": type(exc).__name__},
            "retryable": True,
            "verdict": "PASS fail-closed, runtime evidence PENDING (DETECTOR_UNAVAILABLE)",
            "evidence": {"error_type": type(exc).__name__},
        }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    engine_type = detector.engine_type
    log.info("WakeWordDetector initialized (engine=%s). Listening for %ss...", engine_type, args.duration)

    # Harness requires OpenWakeWord + Whisper cascade
    if engine_type != "openwakeword":
        log.error("[NOT_CONFIGURED] Engine mismatch: active engine '%s' != required 'openwakeword'", engine_type)
        report = {
            "status": "NOT_CONFIGURED",
            "success": False,
            "code": "ENGINE_MISMATCH",
            "message": f"Active wake-word engine '{engine_type}' does not match required cascade engine 'openwakeword'.",
            "data": {"engine_type": engine_type, "required_engine": "openwakeword"},
            "retryable": False,
            "verdict": "PASS fail-closed, runtime evidence PENDING (ENGINE_MISMATCH)",
            "evidence": {"engine_type": engine_type},
        }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    verification_enabled = wake_config.get("openwakeword_verification_enabled", False)
    whisper_detector = getattr(detector, "_whisper_detector", None)
    try:
        verifier_model = whisper_detector._get_model() if whisper_detector else None
    except Exception as exc:
        log.error("[UNAVAILABLE] Wake-word verifier model initialization failed: %s", exc)
        verifier_model = None

    if not verification_enabled or verifier_model is None:
        log.error("[UNAVAILABLE] Production two-stage verifier (Faster-Whisper) is disabled or model is unavailable.")
        report = {
            "status": "UNAVAILABLE",
            "success": False,
            "code": "VERIFIER_UNAVAILABLE",
            "message": "Production two-stage verifier (Faster-Whisper) is disabled or model cannot be loaded.",
            "data": {"verification_enabled": verification_enabled, "verifier_model_loaded": verifier_model is not None},
            "retryable": False,
            "verdict": "PASS fail-closed, runtime evidence PENDING (VERIFIER_UNAVAILABLE)",
            "evidence": {"verification_enabled": verification_enabled, "verifier_model_loaded": False},
        }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    # 6. Record audio loop
    if args.label == "true_wake":
        log.info(
            ">>> Operator trial protocol: Speak 'Hey JARVIS' clearly %d times, allowing at least %.1fs between trials...",
            args.expected_wakes,
            trial_spacing_s,
        )

    frames_processed = 0
    t_start = time_func()

    def audio_callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
        nonlocal frames_processed
        if status:
            log.warning("Audio callback status: %s", status)
        frames_processed += frames
        detector.process_audio_block(indata)

    try:
        with sd.InputStream(
            channels=1,
            samplerate=16000,
            dtype="int16",
            callback=audio_callback,
        ):
            while time_func() - t_start < args.duration:
                if sleep_func is not None:
                    sleep_func(0.1)
                else:
                    sd.sleep(100)
    except Exception as exc:
        log.error("Live audio stream error: %s", exc)
        report = {
            "status": "ERROR",
            "success": False,
            "code": "STREAM_ERROR",
            "message": f"Live audio stream capture failed: {exc}",
            "data": {"error": str(exc)},
            "retryable": True,
            "verdict": "PASS fail-closed (STREAM_ERROR)",
            "evidence": {"error": str(exc)},
        }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    elapsed = round(time_func() - t_start, 2)
    scores_recorded = len(scores)
    log.info(
        "Finished listening. Duration: %ss, frames processed: %d, scores recorded: %d, detections: %d",
        elapsed,
        frames_processed,
        scores_recorded,
        len(detections),
    )

    # 7. Reject no audio evidence
    if frames_processed == 0 or scores_recorded == 0:
        log.error("[ERROR] No real audio evidence captured (frames=%d, scores=%d).", frames_processed, scores_recorded)
        report = {
            "status": "ERROR",
            "success": False,
            "code": "NO_AUDIO_EVIDENCE",
            "message": f"Captured {frames_processed} frames and {scores_recorded} score events; real audio evidence required.",
            "data": {"frames_processed": frames_processed, "scores_recorded": scores_recorded},
            "retryable": True,
            "verdict": "FAIL runtime (NO_AUDIO_EVIDENCE)",
            "evidence": {"frames_processed": frames_processed, "scores_recorded": scores_recorded},
        }
        _save_report(report, args.out, overwrite=args.overwrite)
        return report

    raw_detection_count = len(detections)

    # 8. Evaluate results against acceptance criteria
    if args.label == "true_wake":
        expected_wakes = args.expected_wakes
        min_recall = args.min_recall
        credited_detections = min(raw_detection_count, expected_wakes)
        observed_trigger_ratio = round(credited_detections / expected_wakes, 4) if expected_wakes > 0 else 0.0

        if credited_detections == 0:
            status_val = "ERROR"
            success_val = False
            code_val = "ZERO_DETECTIONS"
            message_val = "Zero wake word triggers observed during true_wake session."
            verdict_val = "FAIL runtime (0 detections for true_wake)"
            retryable_val = True
        elif observed_trigger_ratio < min_recall:
            status_val = "ERROR"
            success_val = False
            code_val = "LOW_TRIGGER_RATIO"
            message_val = (
                f"Observed trigger ratio ({observed_trigger_ratio:.4f}) is below min_recall ({min_recall:.4f})."
            )
            verdict_val = (
                f"FAIL runtime (observed_trigger_ratio {observed_trigger_ratio:.4f} < min_recall {min_recall:.4f})"
            )
            retryable_val = True
        else:
            status_val = "SUCCESS"
            success_val = True
            code_val = "OK"
            message_val = "True-wake acceptance criteria satisfied."
            verdict_val = "PASS runtime"
            retryable_val = False

        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status_val,
            "success": success_val,
            "code": code_val,
            "message": message_val,
            "data": {
                "expected_wakes": expected_wakes,
                "raw_detection_count": raw_detection_count,
                "credited_detections": credited_detections,
                "observed_trigger_ratio": observed_trigger_ratio,
                "min_recall": min_recall,
                "frames_processed": frames_processed,
                "scores_recorded": scores_recorded,
                "duration_seconds": elapsed,
                "engine_type": engine_type,
                "sensitivity": applied_sensitivity,
            },
            "retryable": retryable_val,
            "verdict": verdict_val,
            "label": args.label,
            "duration_seconds": elapsed,
            "engine_type": engine_type,
            "frames_processed": frames_processed,
            "raw_detection_count": raw_detection_count,
            "credited_detections": credited_detections,
            "detection_count": raw_detection_count,
            "detections": detections,
            "scores_recorded": scores_recorded,
            "expected_wakes": expected_wakes,
            "min_recall": min_recall,
            "observed_trigger_ratio": observed_trigger_ratio,
            "evidence": {
                "expected_wakes": expected_wakes,
                "raw_detection_count": raw_detection_count,
                "credited_detections": credited_detections,
                "observed_trigger_ratio": observed_trigger_ratio,
                "min_recall": min_recall,
                "sensitivity": applied_sensitivity,
            },
        }

    else:  # args.label == "ambient"
        false_alarm_count = raw_detection_count
        false_alarms_per_hour = (
            round((false_alarm_count / elapsed) * 3600.0, 2) if elapsed > 0 else 0.0
        )

        if false_alarm_count == 0:
            status_val = "SUCCESS"
            success_val = True
            code_val = "OK"
            message_val = "Ambient wake acceptance criteria satisfied (0 false alarms)."
            verdict_val = "PASS runtime (0 false alarms)"
            retryable_val = False
        else:
            status_val = "ERROR"
            success_val = False
            code_val = "FALSE_ALARMS"
            message_val = f"Detected {false_alarm_count} false alarms during ambient session."
            verdict_val = f"FAIL runtime ({false_alarm_count} false alarms detected)"
            retryable_val = True

        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status_val,
            "success": success_val,
            "code": code_val,
            "message": message_val,
            "data": {
                "false_alarm_count": false_alarm_count,
                "false_alarms_per_hour": false_alarms_per_hour,
                "frames_processed": frames_processed,
                "scores_recorded": scores_recorded,
                "duration_seconds": elapsed,
                "engine_type": engine_type,
                "sensitivity": applied_sensitivity,
            },
            "retryable": retryable_val,
            "verdict": verdict_val,
            "label": args.label,
            "duration_seconds": elapsed,
            "engine_type": engine_type,
            "frames_processed": frames_processed,
            "detection_count": false_alarm_count,
            "raw_detection_count": false_alarm_count,
            "detections": detections,
            "scores_recorded": scores_recorded,
            "false_alarm_count": false_alarm_count,
            "false_alarms_per_hour": false_alarms_per_hour,
            "evidence": {
                "false_alarm_count": false_alarm_count,
                "false_alarms_per_hour": false_alarms_per_hour,
                "sensitivity": applied_sensitivity,
            },
        }

    _save_report(report, args.out, overwrite=args.overwrite)
    return report


def main() -> int:
    try:
        args = parse_args()
        rep = run_wake_word_acceptance(args)
        log.info("Harness Verdict: %s", rep.get("verdict"))
        return 0 if rep.get("success", False) else 1
    except Exception as exc:
        log.error("Fatal error in live wake word acceptance harness: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
