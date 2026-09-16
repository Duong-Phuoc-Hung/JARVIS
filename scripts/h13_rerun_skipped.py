"""Re-run specific skipped H-13 cases"""
import json, sys, time
from pathlib import Path

REC_DIR = Path("docs/eval/h13_recordings")
LOG_FILE = Path("docs/eval/h13_results.json")

RERUN_CASES = [
    (5,  "WF01-5", "Mở Task Manager xem hiệu năng",        "open_app(taskmgr)"),
    (6,  "WF02-1", "Mở trang Google",                       "web_open(google.com)"),
    (29, "WF06-4", "Xóa ghi chú mua hàng hôm qua đi",      "note_delete()"),
    (30, "WF06-5", "Thêm vào việc cần làm gọi điện cho đối tác", "todo_add()"),
    (31, "WF07-1", "Thời tiết hôm nay thế nào",             "weather_query(today)"),
    (46, "WF10-1", "Khóa màn hình máy tính lại [SAFE-lock then unlock]", "system_lock()"),
    (48, "WF10-3", "Hủy lệnh tắt máy tính [SAFE-no-op]",   "shutdown_abort()"),
    (50, "WF10-5", "Kiểm tra tình trạng pin của máy",       "battery_status()"),
]

def play_wav(wav_path):
    try:
        import sounddevice as sd, soundfile as sf
        devices = sd.query_devices()
        vb_idx = next((i for i, d in enumerate(devices)
                       if "cable input" in d["name"].lower() and d["max_output_channels"] > 0), None)
        data, sr = sf.read(str(wav_path))
        sd.play(data, sr, device=vb_idx)
        sd.wait()
        return True
    except Exception as e:
        print(f"  Playback error: {e}")
        return False

# Load existing results
with open(LOG_FILE, encoding="utf-8") as f:
    results = json.load(f)

case_map = {c["case"]: c for c in results["cases"]}

print("=" * 60)
print("H-13 Re-run: 8 skipped cases")
print("JARVIS must be running and listening via VB-Audio!")
print("=" * 60)
jarvis_ok = input("JARVIS running? (y/n): ").strip().lower()
if jarvis_ok != "y":
    print("Start JARVIS first!")
    sys.exit(1)

new_pass = 0
new_fail = 0

for num, wf_id, phrase, expected in RERUN_CASES:
    wav = REC_DIR / f"case_{num:02d}.wav"
    print(f"\n[{num:02d}] {wf_id} | {expected}")
    print(f"  SAY: {phrase}")
    if not wav.exists():
        print("  WAV missing — SKIP")
        continue
    input("  Press Enter to play...")
    play_wav(wav)
    time.sleep(2.0)
    r = input("  (p=Pass / f=Fail): ").strip().lower()
    stt = input("  STT text (Enter to skip): ").strip()
    passed = r == "p"
    case_map[num]["result"] = "PASS" if passed else "FAIL"
    case_map[num]["pass"] = passed
    case_map[num]["stt"] = stt
    if passed:
        new_pass += 1
        print("  ✅ PASS")
    else:
        new_fail += 1
        print("  ❌ FAIL")

# Recalculate
all_cases = list(case_map.values())
total_pass = sum(1 for c in all_cases if c.get("pass") is True)
total_fail = sum(1 for c in all_cases if c.get("pass") is False)
total_skip = sum(1 for c in all_cases if c.get("pass") is None)
evaluated = total_pass + total_fail
pct = (total_pass / evaluated * 100) if evaluated > 0 else 0
verdict = "✅ ĐẠT CHUẨN NGHIỆM THU LIVE" if pct >= 95 and evaluated >= 48 else "❌ CHƯA ĐẠT"

results.update({
    "evaluated": evaluated, "pass": total_pass, "fail": total_fail,
    "skip": total_skip, "pass_rate_pct": round(pct, 1),
    "verdict": verdict, "cases": all_cases
})
with open(LOG_FILE, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"Updated Results: Pass={total_pass} Fail={total_fail} Skip={total_skip}")
print(f"Pass Rate: {pct:.1f}% | Evaluated: {evaluated}/50")
print(f"Verdict: {verdict}")
