"""Collect real wake-word classifier scores for threshold calibration.

This tool deliberately requires an explicit opt-in environment variable and
never labels a sample as a true/false wake automatically.  Run one session
while saying the phrase and a separate session while not saying it, then
compare the recorded score distributions before changing a threshold.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

# Running ``python tools/...`` puts only ``tools/`` on sys.path; make the
# repository package importable without requiring an editable install.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wake_word_score_probe")


def collect_scores(
    duration_seconds: float,
    *,
    label: str,
    sample_rate: int = 16000,
    sensitivity: float = 0.5,
    vad_threshold: float = 0.003,
    device_index: int | None = None,
    engine_override: str | None = None,
    allow_acoustic_fallback: bool = False,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Capture one bounded, operator-labelled score session from a real mic."""
    if os.environ.get("JARVIS_RUN_LIVE_WAKE_PROBE") != "1":
        return {
            "status": "BLOCKED",
            "code": "LIVE_WAKE_PROBE_OPT_IN_REQUIRED",
            "message": "Set JARVIS_RUN_LIVE_WAKE_PROBE=1 to access a real microphone.",
            "retryable": False,
        }
    if label not in {"true_wake", "ambient"}:
        return {"status": "ERROR", "code": "INVALID_LABEL", "retryable": False}
    try:
        import sounddevice as sd
    except ImportError as exc:
        return {"status": "UNAVAILABLE", "code": "MISSING_SOUNDDEVICE", "message": str(exc), "retryable": False}

    from jarvis.audio.engine import AudioEngine
    from jarvis.audio.wake_word import WakeWordDetector

    if device_index is None:
        device_index = AudioEngine().get_active_device()
    observations: list[dict[str, Any]] = []
    start = time.monotonic()

    def on_score(event: Any) -> None:
        item = event.to_dict()
        item["elapsed_seconds"] = round(time.monotonic() - start, 4)
        item["label"] = label
        observations.append(item)

    config: dict[str, Any] = {"acoustic_fallback_policy": "auto"}
    if not engine_override:
        try:
            import importlib.util
            spec = importlib.util.find_spec("openwakeword")
            if spec and spec.origin:
                packaged_model = Path(spec.origin).parent / "resources" / "models" / "hey_jarvis_v0.1.onnx"
                if packaged_model.is_file():
                    config["openwakeword_model_paths"] = [str(packaged_model)]
        except Exception:
            pass
    if engine_override:
        config["engine"] = engine_override
    detector = WakeWordDetector(
        sample_rate=sample_rate,
        sensitivity=sensitivity,
        vad_threshold=vad_threshold,
        config=config,
        on_score=on_score,
    )
    if detector.engine_type == "acoustic_fallback" and not allow_acoustic_fallback:
        result = {
            "status": "NOT_CONFIGURED",
            "code": "WAKE_CLASSIFIER_NOT_CONFIGURED",
            "message": "No configured Tier-1 wake-word model is available; install/configure OpenWakeWord, Vosk, or Porcupine before calibration.",
            "engine_selected": detector.engine_type,
            "retryable": False,
        }
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return result
    chunk_size = max(160, int(round(1280 * sample_rate / 16000.0)))
    started_at = time.time()
    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device_index,
            blocksize=chunk_size,
        ) as stream:
            logger.info("Listening for %.1fs; operator label=%s; engine=%s", duration_seconds, label, detector.engine_type)
            while time.monotonic() - start < duration_seconds:
                data, overflowed = stream.read(chunk_size)
                if overflowed:
                    logger.warning("Audio buffer overflowed")
                detector.feed_audio_block(data.flatten(), timestamp=time.monotonic())
    except Exception as exc:
        return {
            "status": "ERROR",
            "code": "AUDIO_CAPTURE_ERROR",
            "message": str(exc),
            "label": label,
            "events": observations,
            "retryable": True,
        }
    report = {
        "status": "COMPLETED",
        "label": label,
        "duration_seconds": round(time.time() - started_at, 3),
        "sample_rate": sample_rate,
        "chunk_size": chunk_size,
        "device_index": device_index,
        "sensitivity": sensitivity,
        "vad_threshold": vad_threshold,
        "engine_selected": detector.engine_type,
        "event_count": len(observations),
        "events": observations,
        "calibration_note": "Operator label only; no threshold recommendation is inferred by this tool.",
    }
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Record real wake-word confidence scores (explicit opt-in required)")
    parser.add_argument("--label", required=True, choices=("true_wake", "ambient"))
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--sensitivity", type=float, default=0.5)
    parser.add_argument("--vad-threshold", type=float, default=0.003)
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--engine", default=None)
    parser.add_argument("--allow-acoustic-fallback", action="store_true", help="Allow fallback diagnostics; not valid classifier calibration")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = collect_scores(
        args.duration,
        label=args.label,
        sample_rate=args.sample_rate,
        sensitivity=args.sensitivity,
        vad_threshold=args.vad_threshold,
        device_index=args.device,
        engine_override=args.engine,
        allow_acoustic_fallback=args.allow_acoustic_fallback,
        out_path=args.out,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "COMPLETED" else 2


if __name__ == "__main__":
    sys.exit(main())
