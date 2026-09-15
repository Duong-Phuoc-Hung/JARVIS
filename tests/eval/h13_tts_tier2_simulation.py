"""
H-13 TTS Tier-2 Simulation — Fixed Version
Uses existing TTS audio in docs/eval/h13_tts_tier2/
STT: faster_whisper small CPU (reliable, no CUDA deps)
Router: keyword matching (same approach as stt_intent_eval.py)
WARNING: TIER 2 ONLY. Does NOT close H-13.
"""
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Expected keyword patterns for each action
ACTION_KEYWORDS = {
    "open_app": ["notepad", "may tinh", "calculator", "file explorer", "spotify", "task manager",
                 "mo", "open", "bat", "khoi dong", "launch"],
    "web_open": ["google", "youtube", "github", "dan tri", "chatgpt", "mo trang", "truy cap",
                 "web", "trang", "kenh"],
    "volume_control": ["am luong", "volume", "loa", "tieng", "mute", "tat tieng", "tang", "giam",
                       "dat am"],
    "brightness_control": ["do sang", "man hinh", "sang", "brightness"],
    "music_play": ["nhac", "bai nhac", "phat nhac", "music", "bat nhac"],
    "music_pause": ["tam dung", "pause", "dung phat"],
    "music_resume": ["tiep tuc", "resume", "chay tiep"],
    "music_next": ["tiep theo", "next", "chuyen sang"],
    "music_prev": ["truoc", "prev", "quay lai bai"],
    "timer_set": ["hen gio", "dem nguoc", "timer", "phut", "giay", "gio"],
    "alarm_set": ["bao thuc", "alarm", "goi toi day"],
    "timer_cancel": ["huy hen gio", "huy timer", "xoa dong ho"],
    "timer_status": ["con bao nhieu", "het gio", "timer con"],
    "note_create": ["ghi chu", "luu", "nho"],
    "reminder_set": ["nhac toi", "nhac nho", "reminder"],
    "note_list": ["doc lai", "xem ghi chu", "danh sach"],
    "note_delete": ["xoa ghi chu", "bo ghi chu"],
    "todo_add": ["them vao", "viec can lam", "todo"],
    "weather_query": ["thoi tiet", "mua", "nhiet do", "do am", "nang", "troi"],
    "home_assistant": ["den", "dieu hoa", "rem", "nhiet do phong", "may lanh", "bat den", "tat den"],
    "morning_briefing": ["tom tat", "diem tin", "tin tuc", "ban tin"],
    "telegram_check": ["telegram", "tin nhan"],
    "email_check": ["email", "hom thu", "thu"],
    "system_status": ["trang thai", "he thong", "status", "bao cao"],
    "network_check": ["mang", "internet", "wifi", "ket noi"],
    "system_lock": ["khoa man hinh", "lock", "khoa may"],
    "system_sleep": ["che do ngu", "sleep", "ngu"],
    "shutdown_abort": ["huy lenh tat", "dung tat", "abort"],
    "system_restart": ["khoi dong lai", "restart", "reboot"],
    "battery_status": ["pin", "battery", "sac"],
}

TEST_CASES = [
    ("WF01-1", "open_app"), ("WF01-2", "open_app"), ("WF01-3", "open_app"),
    ("WF01-4", "open_app"), ("WF01-5", "open_app"),
    ("WF02-1", "web_open"), ("WF02-2", "web_open"), ("WF02-3", "web_open"),
    ("WF02-4", "web_open"), ("WF02-5", "web_open"),
    ("WF03-1", "volume_control"), ("WF03-2", "volume_control"), ("WF03-3", "volume_control"),
    ("WF03-4", "volume_control"), ("WF03-5", "brightness_control"),
    ("WF04-1", "music_play"), ("WF04-2", "music_pause"), ("WF04-3", "music_resume"),
    ("WF04-4", "music_next"), ("WF04-5", "music_prev"),
    ("WF05-1", "timer_set"), ("WF05-2", "alarm_set"), ("WF05-3", "timer_cancel"),
    ("WF05-4", "timer_status"), ("WF05-5", "timer_set"),
    ("WF06-1", "note_create"), ("WF06-2", "reminder_set"), ("WF06-3", "note_list"),
    ("WF06-4", "note_delete"), ("WF06-5", "todo_add"),
    ("WF07-1", "weather_query"), ("WF07-2", "weather_query"), ("WF07-3", "weather_query"),
    ("WF07-4", "weather_query"), ("WF07-5", "weather_query"),
    ("WF08-1", "home_assistant"), ("WF08-2", "home_assistant"), ("WF08-3", "home_assistant"),
    ("WF08-4", "home_assistant"), ("WF08-5", "home_assistant"),
    ("WF09-1", "morning_briefing"), ("WF09-2", "telegram_check"), ("WF09-3", "email_check"),
    ("WF09-4", "system_status"), ("WF09-5", "network_check"),
    ("WF10-1", "system_lock"), ("WF10-2", "system_sleep"), ("WF10-3", "shutdown_abort"),
    ("WF10-4", "system_restart"), ("WF10-5", "battery_status"),
]

AUDIO_DIR = Path("docs/eval/h13_tts_tier2")
OUT = AUDIO_DIR / "h13_tts_simulation_results.json"


def keyword_match(text: str, expected_action: str) -> bool:
    text_lower = text.lower()
    keywords = ACTION_KEYWORDS.get(expected_action, [])
    return any(k in text_lower for k in keywords)


def main():
    print("H-13 TTS Tier-2 Simulation — STT Only (small CPU, keyword match)")
    print("WARNING: TIER 2 ONLY. Does NOT close H-13.\n")

    # Check audio files exist
    existing = list(AUDIO_DIR.glob("*.mp3"))
    print(f"Audio files found: {len(existing)} in {AUDIO_DIR}")
    if len(existing) < 50:
        print(f"ERROR: Expected 50 audio files, found {len(existing)}")
        return

    # Load STT model
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        model_name = "small CPU int8"
        print(f"STT model: {model_name}\n")
    except Exception as e:
        print(f"FATAL: Cannot load STT model: {e}")
        return

    results = []
    counts = {"CORRECT": 0, "MISROUTED": 0, "STT_EMPTY": 0, "ROUTER_ABSTAIN": 0}

    for case_id, expected_action in TEST_CASES:
        audio_path = AUDIO_DIR / f"{case_id}.mp3"
        if not audio_path.exists():
            print(f"  {case_id}: SKIP (file not found)")
            counts["ROUTER_ABSTAIN"] += 1
            results.append({"case_id": case_id, "status": "ROUTER_ABSTAIN",
                           "error": "audio file not found", "expected": expected_action})
            continue

        t0 = time.time()
        segs, _ = model.transcribe(str(audio_path), language="vi", beam_size=3)
        transcribed = " ".join(s.text.strip() for s in segs).strip()
        lat = round((time.time() - t0) * 1000, 1)

        if not transcribed:
            status = "STT_EMPTY"
        elif keyword_match(transcribed, expected_action):
            status = "CORRECT"
        else:
            status = "MISROUTED"

        counts[status] = counts.get(status, 0) + 1
        print(f"  {case_id}: {status} ({lat}ms) | '{transcribed[:40]}'")
        results.append({
            "case_id": case_id,
            "status": status,
            "transcribed": transcribed,
            "expected_action": expected_action,
            "latency_ms": lat,
        })

    total = len(results)
    acc = counts["CORRECT"] / total * 100 if total > 0 else 0
    arith = f"{counts['CORRECT']}+{counts['MISROUTED']}+{counts['STT_EMPTY']}+{counts['ROUTER_ABSTAIN']}={sum(counts.values())}"

    print(f"\n{'='*60}")
    print(f"TIER-2 TTS SIMULATION RESULTS (NOT Tier 1 — H-13 still PENDING_HUMAN_EXECUTION)")
    print(f"Arithmetic: {arith}")
    print(f"CORRECT: {counts['CORRECT']}/{total} = {acc:.1f}%")
    print(f"{'='*60}")

    output = {
        "tier": "TIER_2_SYNTHETIC_TTS",
        "warning": "Does NOT close H-13. Tier 1 requires real human voice and microphone.",
        "voice_model": "vi-VN-HoaiMyNeural (Microsoft edge-tts)",
        "stt_model": model_name,
        "router_method": "keyword_match (no LLM API required)",
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": total,
        "counts": counts,
        "accuracy_pct": round(acc, 1),
        "arithmetic_check": arith,
        "results": results,
    }
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {OUT}")


if __name__ == "__main__":
    main()
