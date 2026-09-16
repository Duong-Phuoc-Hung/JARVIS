"""
H-13 Voice Acceptance Test — Step 2: Playback through VB-Audio + auto Pass/Fail
Usage: python scripts/h13_run_test.py
Requires: VB-Audio Virtual Cable installed, JARVIS running
"""
import sys
import json
import wave
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime

CASES_META = [
    (1,  "WF01-1", "Mở Notepad lên cho tôi",             "open_app(notepad)"),
    (2,  "WF01-2", "Mở máy tính tính tiền",              "open_app(calculator)"),
    (3,  "WF01-3", "Mở File Explorer ra",                "open_app(explorer)"),
    (4,  "WF01-4", "Khởi động ứng dụng Spotify",         "open_app(spotify)"),
    (5,  "WF01-5", "Mở Task Manager xem hiệu năng",      "open_app(taskmgr)"),
    (6,  "WF02-1", "Mở trang Google",                    "web_open(google.com)"),
    (7,  "WF02-2", "Mở kênh YouTube lên",                "web_open(youtube.com)"),
    (8,  "WF02-3", "Truy cập vào trang GitHub",          "web_open(github.com)"),
    (9,  "WF02-4", "Mở báo Dân Trí đọc tin tức",         "web_open(dantri.com.vn)"),
    (10, "WF02-5", "Mở trang ChatGPT",                   "web_open(chatgpt.com)"),
    (11, "WF03-1", "Tăng âm lượng lên mười phần trăm",  "volume_control(delta=+10)"),
    (12, "WF03-2", "Giảm âm lượng xuống",                "volume_control(delta=-10)"),
    (13, "WF03-3", "Tắt tiếng loa đi",                   "volume_control(level=0)"),
    (14, "WF03-4", "Đặt âm lượng ở mức năm mươi phần trăm", "volume_control(level=50)"),
    (15, "WF03-5", "Tăng độ sáng màn hình lên",          "brightness_control(delta=+15)"),
    (16, "WF04-1", "Bật một bài nhạc nhẹ không lời",     "music_play()"),
    (17, "WF04-2", "Tạm dừng phát nhạc",                 "music_pause()"),
    (18, "WF04-3", "Tiếp tục phát bài hát",              "music_resume()"),
    (19, "WF04-4", "Chuyển sang bài tiếp theo",          "music_next()"),
    (20, "WF04-5", "Quay lại bài vừa phát",              "music_prev()"),
    (21, "WF05-1", "Hẹn giờ cho tôi năm phút nữa",       "timer_set(300)"),
    (22, "WF05-2", "Đặt báo thức lúc bảy giờ sáng mai",  "alarm_set(07:00)"),
    (23, "WF05-3", "Hủy hẹn giờ đang chạy",              "timer_cancel()"),
    (24, "WF05-4", "Còn bao nhiêu thời gian nữa hết giờ","timer_status()"),
    (25, "WF05-5", "Đặt đồng hồ đếm ngược hai mươi phút","timer_set(1200)"),
    (26, "WF06-1", "Ghi chú nhớ nộp báo cáo lúc mười bốn giờ", "note_create()"),
    (27, "WF06-2", "Nhắc tôi uống nước sau một tiếng nữa","reminder_set()"),
    (28, "WF06-3", "Đọc lại các ghi chú hôm nay của tôi", "note_list()"),
    (29, "WF06-4", "Xóa ghi chú mua hàng hôm qua đi",   "note_delete()"),
    (30, "WF06-5", "Thêm vào việc cần làm gọi điện cho đối tác", "todo_add()"),
    (31, "WF07-1", "Thời tiết hôm nay thế nào",          "weather_query(today)"),
    (32, "WF07-2", "Ngày mai có mưa không",               "weather_query(tomorrow)"),
    (33, "WF07-3", "Nhiệt độ hiện tại ở Hà Nội là bao nhiêu", "weather_query(hanoi)"),
    (34, "WF07-4", "Thời tiết Thành phố Hồ Chí Minh cuối tuần", "weather_query(hcm)"),
    (35, "WF07-5", "Độ ẩm không khí bây giờ ra sao",     "weather_query(humidity)"),
    (36, "WF08-1", "Bật đèn phòng khách lên",            "home_assistant(light.on)"),
    (37, "WF08-2", "Tắt đèn phòng ngủ",                  "home_assistant(light.off)"),
    (38, "WF08-3", "Nhiệt độ phòng ngủ hiện tại là bao nhiêu", "home_assistant(sensor.temp)"),
    (39, "WF08-4", "Kéo rèm cửa sổ ra",                  "home_assistant(cover.open)"),
    (40, "WF08-5", "Bật điều hòa hai mươi lăm độ",       "home_assistant(climate.set)"),
    (41, "WF09-1", "Tóm tắt điểm tin buổi sáng cho tôi", "morning_briefing()"),
    (42, "WF09-2", "Kiểm tra xem có tin nhắn Telegram mới không", "telegram_check()"),
    (43, "WF09-3", "Kiểm tra hòm thư email chưa đọc",    "email_check()"),
    (44, "WF09-4", "Báo cáo trạng thái hệ thống hiện tại", "system_status()"),
    (45, "WF09-5", "Kiểm tra kết nối mạng Internet",     "network_check()"),
    (46, "WF10-1", "Khóa màn hình máy tính lại",         "system_lock()"),
    (47, "WF10-2", "Cho máy tính vào chế độ ngủ",        "system_sleep()"),
    (48, "WF10-3", "Hủy lệnh tắt máy tính",              "shutdown_abort()"),
    (49, "WF10-4", "Khởi động lại máy tính",             "system_restart()"),
    (50, "WF10-5", "Kiểm tra tình trạng pin của máy",    "battery_status()"),
]

# Safe cases that won't lock/sleep/restart machine
SAFE_CASES = set(range(1, 46))  # Skip 46-49 (lock/sleep/shutdown/restart) for auto-run
RISKY_CASES = {46, 47, 48, 49}  # Require manual confirmation

REC_DIR = Path(__file__).parent.parent / "docs" / "eval" / "h13_recordings"
RESULTS_DIR = Path(__file__).parent.parent / "docs" / "eval"
LOG_FILE = RESULTS_DIR / "h13_results.json"


def play_wav_to_vbaudio(wav_path: Path, vb_device_name: str = "CABLE Input") -> bool:
    """Play WAV file to VB-Audio Virtual Cable output device."""
    try:
        import sounddevice as sd
        import soundfile as sf

        # Find VB-Audio device
        devices = sd.query_devices()
        vb_idx = None
        for i, dev in enumerate(devices):
            if vb_device_name.lower() in dev["name"].lower() and dev["max_output_channels"] > 0:
                vb_idx = i
                break

        if vb_idx is None:
            print(f"  WARNING: '{vb_device_name}' not found. Using default output.")
            vb_idx = None

        data, sr = sf.read(str(wav_path))
        sd.play(data, sr, device=vb_idx)
        sd.wait()
        return True
    except ImportError:
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.run(
                ["powershell", "-Command",
                 f" = New-Object System.Media.SoundPlayer '{wav_path}'; .PlaySync()"],
                timeout=10, capture_output=True, creationflags=creationflags,
            )
            return True
        except Exception:
            return False
    except Exception as e:
        print(f"  Playback error: {e}")
        return False


def wait_for_jarvis_response(timeout: float = 8.0) -> str:
    """
    Attempt to capture JARVIS STT output from its log.
    Returns transcribed text or empty string.
    """
    # Look for JARVIS log directory
    log_candidates = [
        Path.home() / "AppData" / "Local" / "JARVIS" / "logs" / "jarvis.log",
        Path(__file__).parent.parent / "logs" / "jarvis.log",
        Path(__file__).parent.parent / "jarvis.log",
    ]
    log_path = next((p for p in log_candidates if p.exists()), None)

    if log_path is None:
        return ""  # Can't read log

    # Record current position
    try:
        initial_size = log_path.stat().st_size
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.3)
            new_size = log_path.stat().st_size
            if new_size > initial_size:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(initial_size)
                    new_content = f.read()
                # Look for STT output pattern
                for line in new_content.splitlines():
                    if "STT:" in line or "transcribed:" in line or "whisper" in line.lower():
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            return parts[-1].strip()
    except Exception:
        pass
    return ""


def run_test(skip_risky: bool = True, dry_run: bool = False):
    results = []
    pass_count = 0
    fail_count = 0
    skip_count = 0

    print("=" * 60)
    print("H-13 Automated Voice Test Runner")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Risky cases (lock/sleep/restart): {'SKIPPED' if skip_risky else 'INCLUDED'}")
    print("=" * 60)

    jarvis_ready = input("\nJARVIS running and listening? (y/n): ").strip().lower()
    if jarvis_ready != "y":
        print("Start JARVIS first: python -m jarvis --headless or via tray")
        return

    for num, wf_id, phrase, expected in CASES_META:
        wav_path = REC_DIR / f"case_{num:02d}.wav"

        if not wav_path.exists():
            print(f"[{num:02d}/50] SKIP — no recording: {phrase[:45]}")
            results.append({"case": num, "wf_id": wf_id, "phrase": phrase,
                           "expected": expected, "result": "SKIP_NO_AUDIO",
                           "stt": "", "pass": None})
            skip_count += 1
            continue

        if skip_risky and num in RISKY_CASES:
            print(f"[{num:02d}/50] SKIP (risky: {wf_id}): {phrase[:45]}")
            results.append({"case": num, "wf_id": wf_id, "phrase": phrase,
                           "expected": expected, "result": "SKIP_RISKY",
                           "stt": "", "pass": None})
            skip_count += 1
            continue

        if dry_run:
            print(f"[{num:02d}/50] DRY: would play {wav_path.name} → {expected}")
            results.append({"case": num, "wf_id": wf_id, "phrase": phrase,
                           "expected": expected, "result": "DRY_RUN",
                           "stt": "", "pass": None})
            continue

        print(f"\n[{num:02d}/50] {wf_id} | Playing: {phrase[:50]}")
        time.sleep(1.0)  # Give JARVIS time to be in listening state

        play_ok = play_wav_to_vbaudio(wav_path)
        if not play_ok:
            print(f"  FAIL — playback error")
            results.append({"case": num, "wf_id": wf_id, "phrase": phrase,
                           "expected": expected, "result": "FAIL_PLAYBACK",
                           "stt": "", "pass": False})
            fail_count += 1
            continue

        # Wait for response and manual evaluation
        time.sleep(2.0)  # Buffer after playback

        print(f"  Expected: {expected}")
        result = input(f"  Result (p=Pass / f=Fail / s=Skip): ").strip().lower()
        stt_text = input(f"  STT text seen (or Enter to skip): ").strip()

        passed = result == "p"
        status = "PASS" if passed else ("FAIL" if result == "f" else "SKIP")
        results.append({
            "case": num, "wf_id": wf_id, "phrase": phrase,
            "expected": expected, "result": status,
            "stt": stt_text, "pass": passed if result != "s" else None
        })

        if result == "p":
            pass_count += 1
            print(f"  ✅ PASS")
        elif result == "f":
            fail_count += 1
            print(f"  ❌ FAIL")
        else:
            skip_count += 1

        time.sleep(0.5)

    # Summary
    total_evaluated = pass_count + fail_count
    pct = (pass_count / total_evaluated * 100) if total_evaluated > 0 else 0

    print("\n" + "=" * 60)
    print(f"H-13 Results Summary")
    print(f"  Pass: {pass_count}")
    print(f"  Fail: {fail_count}")
    print(f"  Skip: {skip_count}")
    print(f"  Pass Rate: {pct:.1f}% (threshold: >=95%)")
    verdict = "✅ ĐẠT" if pct >= 95 and total_evaluated >= 48 else "❌ CHƯA ĐẠT"
    print(f"  Verdict: {verdict}")
    print("=" * 60)

    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "total_cases": 50,
        "evaluated": total_evaluated,
        "pass": pass_count,
        "fail": fail_count,
        "skip": skip_count,
        "pass_rate_pct": round(pct, 1),
        "verdict": verdict,
        "cases": results
    }
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {LOG_FILE}")

    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-risky", action="store_true",
                        help="Include risky cases (lock/sleep/restart)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Dry run (list cases, don't play)")
    args = parser.parse_args()
    run_test(skip_risky=not args.include_risky, dry_run=args.dry_run)
