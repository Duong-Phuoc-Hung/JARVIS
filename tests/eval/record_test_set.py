"""
tests/eval/record_test_set.py
==============================
Guided recording tool for JARVIS STT Intent Misrouting Rate evaluation.

Converts manual recording (error-prone, inconsistent) into a scripted process:
  - Reads INTENT_TEST_SET from stt_intent_eval.py
  - Prompts for each phrase in each condition (clean, noisy)
  - Records at exactly 16kHz mono (matches Whisper input spec)
  - Auto-trims leading/trailing silence (threshold configurable)
  - Saves to correct directory structure automatically
  - Allows playback + re-record before accepting

Output structure:
  tests/eval/audio/
    clean/open_app/variant_0.wav, variant_1.wav ...
    noisy/open_app/variant_0.wav ...

Usage:
  python tests/eval/record_test_set.py
  python tests/eval/record_test_set.py --conditions clean    # one condition only
  python tests/eval/record_test_set.py --resume              # skip already-recorded files
  python tests/eval/record_test_set.py --variants 3          # 3 variants per phrase

Requirements:
  pip install sounddevice soundfile numpy
"""
from __future__ import annotations
import argparse, os, sys, time, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# ── Attempt to import audio libraries ────────────────────────────────────────
try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    AUDIO_OK = True
except ImportError:
    AUDIO_OK = False

# ── Config ────────────────────────────────────────────────────────────────────
SAMPLE_RATE   = 16000   # 16kHz mono — matches Whisper input
CHANNELS      = 1
RECORD_SECS   = 5       # Max recording length per utterance
TRIM_SILENCE_THRESHOLD = 0.01   # RMS threshold for silence trimming
MIN_SPEECH_SECS = 0.5   # Reject if speech < 0.5s after trimming

# ── Intent phrases ────────────────────────────────────────────────────────────
# Imported directly from the eval framework
INTENT_TEST_SET: dict[str, list[str]] = {
    "open_app":       ["mở chrome", "mở ứng dụng chrome", "mở notepad", "mở spotify", "khởi động chrome"],
    "system_shutdown":["tắt máy tính", "shutdown máy", "tắt nguồn"],
    "system_restart": ["khởi động lại máy", "restart máy tính", "reboot"],
    "volume_control": ["tăng âm lượng", "giảm âm lượng", "điều chỉnh âm lượng", "tắt tiếng", "mute"],
    "weather_query":  ["thời tiết hôm nay", "thời tiết ngày mai", "dự báo thời tiết", "trời hôm nay thế nào"],
    "timer_set":      ["hẹn giờ 5 phút", "đặt timer 10 phút", "nhắc tôi sau 15 phút"],
    "reminder_set":   ["nhắc nhở lúc 3 giờ", "đặt nhắc lúc 8 giờ sáng"],
    "screenshot":     ["chụp màn hình", "chụp ảnh màn hình", "screenshot"],
    "stop":           ["dừng lại", "stop", "thôi", "hủy"],
    "search":         ["tìm kiếm google", "tìm file word", "search chrome", "tìm kiếm youtube"],
    "music_play":     ["mở nhạc", "phát nhạc", "play music"],
    "screen_off":     ["tắt màn hình", "turn off monitor"],
    "note_take":      ["ghi chú", "tạo ghi chú mới"],
    "settings_open":  ["mở cài đặt", "open settings"],
}

CONDITION_INSTRUCTIONS = {
    "clean": """
  ĐIỀU KIỆN: CLEAN (phòng yên tĩnh)
  - Tắt quạt, TV, nguồn tiếng ồn xung quanh
  - Nói bình thường, micro cách miệng ~30cm
  - Đây là baseline — giọng rõ, phát âm chuẩn
""",
    "noisy": """
  ĐIỀU KIỆN: NOISY (có tiếng ồn nền)
  - Bật quạt HOẶC TV ở mức âm lượng vừa phải
  - Hoặc: nói xa micro hơn (60-80cm) hoặc nói hơi nhỏ hơn bình thường
  - Mô phỏng điều kiện thực tế — đây là test case khó
""",
}

# ── Utilities ─────────────────────────────────────────────────────────────────

def trim_silence(audio: "np.ndarray", threshold: float = TRIM_SILENCE_THRESHOLD,
                 sr: int = SAMPLE_RATE) -> "np.ndarray":
    """Remove leading/trailing silence based on RMS energy in 10ms windows."""
    window = sr // 100  # 10ms
    rms = np.array([
        np.sqrt(np.mean(audio[i:i+window]**2))
        for i in range(0, len(audio)-window, window)
    ])
    nonsilent = np.where(rms > threshold)[0]
    if len(nonsilent) == 0:
        return audio
    start = max(0, nonsilent[0] * window - window)
    end   = min(len(audio), (nonsilent[-1]+2) * window)
    return audio[start:end]

def save_wav(audio: "np.ndarray", path: Path, sr: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sr, subtype="PCM_16")

def play_wav(path: Path) -> None:
    data, sr = sf.read(str(path), dtype="float32")
    sd.play(data, sr)
    sd.wait()

def record_utterance(duration: float = RECORD_SECS) -> "np.ndarray":
    """Record audio and return trimmed float32 array."""
    print(f"  🔴 Recording for up to {duration}s... (press Enter to stop early)", end="", flush=True)
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=CHANNELS, dtype="float32")
    # Allow early stop
    import threading
    done = threading.Event()
    def wait_enter():
        input()
        done.set()
    t = threading.Thread(target=wait_enter, daemon=True)
    t.start()
    while not done.is_set() and not audio.shape[0] <= 0:
        elapsed = 0
        start = time.perf_counter()
        while (time.perf_counter()-start) < duration and not done.is_set():
            time.sleep(0.05)
        break
    sd.stop()
    print(" ⏹  Stopped")
    if audio.ndim > 1: audio = audio[:,0]
    return trim_silence(audio.copy())

def colored(text: str, code: str) -> str:
    """ANSI color — degrades gracefully on Windows without color support."""
    try:
        return f"\033[{code}m{text}\033[0m"
    except Exception:
        return text

# ── Main recording loop ────────────────────────────────────────────────────────

def record_condition(condition: str, audio_dir: Path, n_variants: int,
                     resume: bool) -> dict[str, int]:
    """Record all phrases for one condition. Returns {intent: n_recorded}."""
    stats: dict[str, int] = {}
    print(CONDITION_INSTRUCTIONS.get(condition, f"\n  Condition: {condition}\n"))
    input("  Press Enter when ready to start recording...\n")

    for intent, phrases in INTENT_TEST_SET.items():
        phrases_to_record = phrases[:n_variants]
        print(f"\n  {'─'*50}")
        print(f"  Intent: {colored(intent, '1;33')}  ({len(phrases_to_record)} phrases)")
        print(f"  {'─'*50}")
        recorded_count = 0

        for idx, phrase in enumerate(phrases_to_record):
            wav_path = audio_dir / condition / intent / f"variant_{idx}.wav"

            if resume and wav_path.exists():
                print(f"  ⏩ Skipping (already recorded): variant_{idx}.wav — '{phrase}'")
                recorded_count += 1
                continue

            while True:
                print(f"\n  Phrase {idx+1}/{len(phrases_to_record)}: {colored(repr(phrase), '1;36')}")
                print(f"  Say this phrase clearly when recording starts.")
                input("  Press Enter to record...")

                audio = record_utterance()

                # Quality check
                duration = len(audio) / SAMPLE_RATE
                rms = float(np.sqrt(np.mean(audio**2))) if len(audio) > 0 else 0.0

                if duration < MIN_SPEECH_SECS or rms < 0.005:
                    print(f"  ⚠️  Too short or too quiet ({duration:.1f}s, RMS={rms:.4f})")
                    print("  Recording not saved. Please try again.")
                    continue

                print(f"  Duration: {duration:.1f}s | RMS: {rms:.4f}")

                # Playback + confirm
                print("  Playing back...")
                # Save temp to play
                tmp = wav_path.parent / f"_tmp_{idx}.wav"
                tmp.parent.mkdir(parents=True, exist_ok=True)
                save_wav(audio, tmp)
                play_wav(tmp)
                tmp.unlink(missing_ok=True)

                choice = input("  Accept? [y=yes / n=re-record / s=skip]: ").strip().lower()
                if choice == "y":
                    save_wav(audio, wav_path)
                    print(f"  ✓ Saved: {wav_path.relative_to(audio_dir.parent.parent)}")
                    recorded_count += 1
                    break
                elif choice == "s":
                    print("  Skipped.")
                    break
                else:
                    print("  Re-recording...")

        stats[intent] = recorded_count
    return stats

def main():
    ap = argparse.ArgumentParser(description="JARVIS STT test set recorder")
    ap.add_argument("--conditions", nargs="+", default=["clean","noisy"],
                    choices=["clean","noisy"])
    ap.add_argument("--audio-dir", default="tests/eval/audio")
    ap.add_argument("--variants", type=int, default=5,
                    help="Number of variants (phrases) to record per intent")
    ap.add_argument("--resume", action="store_true",
                    help="Skip already-recorded files")
    args = ap.parse_args()

    if not AUDIO_OK:
        print("ERROR: Required packages not found.")
        print("Install with: pip install sounddevice soundfile numpy")
        print()
        print("On Windows if sounddevice fails:")
        print("  pip install sounddevice --extra-index-url https://pypi.org/simple/")
        return 1

    audio_dir = ROOT / args.audio_dir

    print("=" * 60)
    print("JARVIS STT Test Set Recorder")
    print("=" * 60)
    print(f"  Sample rate : {SAMPLE_RATE} Hz (16kHz mono — matches Whisper)")
    print(f"  Conditions  : {args.conditions}")
    print(f"  Variants    : up to {args.variants} phrases per intent")
    print(f"  Intents     : {len(INTENT_TEST_SET)}")
    expected = len(INTENT_TEST_SET) * args.variants * len(args.conditions)
    print(f"  Expected files: ~{expected} WAV files")
    print(f"  Output dir  : {audio_dir}")
    if args.resume:
        print("  Mode        : RESUME (skipping existing files)")
    print()

    # Check microphone
    try:
        devices = sd.query_devices()
        default_input = sd.query_devices(kind="input")
        print(f"  Microphone  : {default_input['name']}")
        print(f"  Channels    : {default_input['max_input_channels']}")
    except Exception as e:
        print(f"  WARNING: Could not query microphone: {e}")

    print()
    input("Press Enter to begin...\n")

    total_recorded = 0
    for condition in args.conditions:
        print(f"\n{'='*60}")
        print(f"CONDITION: {condition.upper()}")
        print(f"{'='*60}")
        stats = record_condition(condition, audio_dir, args.variants, args.resume)
        n = sum(stats.values())
        total_recorded += n
        print(f"\n  Condition '{condition}' done: {n} files recorded")
        for intent, count in stats.items():
            print(f"    {intent}: {count} variants")

        if condition != args.conditions[-1]:
            print(f"\n{'─'*60}")
            print("Next condition coming up...")
            input("Press Enter when ready for next condition...")

    print(f"\n{'='*60}")
    print(f"RECORDING COMPLETE: {total_recorded} files total")
    print(f"{'='*60}")
    print(f"\nTo run evaluation:")
    print(f"  python tests/eval/stt_intent_eval.py --models small large-v3")
    print(f"\nResults -> docs/eval/stt_eval_results.json")
    return 0

if __name__ == "__main__": sys.exit(main())
