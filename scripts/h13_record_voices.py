"""
H-13 Voice Acceptance Test — Step 1: Record 50 phrases
Usage: python scripts/h13_record_voices.py
Records each phrase to: docs/eval/h13_recordings/case_{N:02d}.wav
"""
import sys
import time
import wave
from pathlib import Path

CASES = [
    (1,  "WF01-1", "Mo Notepad len cho toi",                "open_app(notepad)"),
    (2,  "WF01-2", "Mo may tinh tinh tien",                 "open_app(calculator)"),
    (3,  "WF01-3", "Mo File Explorer ra",                   "open_app(explorer)"),
    (4,  "WF01-4", "Khoi dong ung dung Spotify",            "open_app(spotify)"),
    (5,  "WF01-5", "Mo Task Manager xem hieu nang",         "open_app(taskmgr)"),
    (6,  "WF02-1", "Mo trang Google",                       "web_open(google.com)"),
    (7,  "WF02-2", "Mo kenh YouTube len",                   "web_open(youtube.com)"),
    (8,  "WF02-3", "Truy cap vao trang GitHub",             "web_open(github.com)"),
    (9,  "WF02-4", "Mo bao Dan Tri doc tin tuc",            "web_open(dantri.com.vn)"),
    (10, "WF02-5", "Mo trang ChatGPT",                      "web_open(chatgpt.com)"),
    (11, "WF03-1", "Tang am luong len muoi phan tram",      "volume_control(delta=+10)"),
    (12, "WF03-2", "Giam am luong xuong",                   "volume_control(delta=-10)"),
    (13, "WF03-3", "Tat tieng loa di",                      "volume_control(level=0)"),
    (14, "WF03-4", "Dat am luong o muc nam muoi phan tram", "volume_control(level=50)"),
    (15, "WF03-5", "Tang do sang man hinh len",             "brightness_control(delta=+15)"),
    (16, "WF04-1", "Bat mot bai nhac nhe khong loi",        "music_play()"),
    (17, "WF04-2", "Tam dung phat nhac",                    "music_pause()"),
    (18, "WF04-3", "Tiep tuc phat bai hat",                 "music_resume()"),
    (19, "WF04-4", "Chuyen sang bai tiep theo",             "music_next()"),
    (20, "WF04-5", "Quay lai bai vua phat",                 "music_prev()"),
    (21, "WF05-1", "Hen gio cho toi nam phut nua",          "timer_set(300)"),
    (22, "WF05-2", "Dat bao thuc luc bay gio sang mai",     "alarm_set(07:00)"),
    (23, "WF05-3", "Huy hen gio dang chay",                 "timer_cancel()"),
    (24, "WF05-4", "Con bao nhieu thoi gian nua het gio",   "timer_status()"),
    (25, "WF05-5", "Dat dong ho dem nguoc hai muoi phut",   "timer_set(1200)"),
    (26, "WF06-1", "Ghi chu nho nop bao cao luc muoi bon gio", "note_create()"),
    (27, "WF06-2", "Nhac toi uong nuoc sau mot tieng nua",  "reminder_set()"),
    (28, "WF06-3", "Doc lai cac ghi chu hom nay cua toi",   "note_list()"),
    (29, "WF06-4", "Xoa ghi chu mua hang hom qua di",       "note_delete()"),
    (30, "WF06-5", "Them vao viec can lam goi dien cho doi tac", "todo_add()"),
    (31, "WF07-1", "Thoi tiet hom nay the nao",             "weather_query(today)"),
    (32, "WF07-2", "Ngay mai co mua khong",                  "weather_query(tomorrow)"),
    (33, "WF07-3", "Nhiet do hien tai o Ha Noi la bao nhieu", "weather_query(hanoi)"),
    (34, "WF07-4", "Thoi tiet Thanh pho Ho Chi Minh cuoi tuan", "weather_query(hcm)"),
    (35, "WF07-5", "Do am khong khi bay gio ra sao",        "weather_query(humidity)"),
    (36, "WF08-1", "Bat den phong khach len",               "home_assistant(light.on)"),
    (37, "WF08-2", "Tat den phong ngu",                     "home_assistant(light.off)"),
    (38, "WF08-3", "Nhiet do phong ngu hien tai la bao nhieu", "home_assistant(sensor.temp)"),
    (39, "WF08-4", "Keo rem cua so ra",                     "home_assistant(cover.open)"),
    (40, "WF08-5", "Bat dieu hoa hai muoi lam do",          "home_assistant(climate.set)"),
    (41, "WF09-1", "Tom tat diem tin buoi sang cho toi",    "morning_briefing()"),
    (42, "WF09-2", "Kiem tra xem co tin nhan Telegram moi khong", "telegram_check()"),
    (43, "WF09-3", "Kiem tra hom thu email chua doc",       "email_check()"),
    (44, "WF09-4", "Bao cao trang thai he thong hien tai",  "system_status()"),
    (45, "WF09-5", "Kiem tra ket noi mang Internet",        "network_check()"),
    (46, "WF10-1", "Khoa man hinh may tinh lai",            "system_lock()"),
    (47, "WF10-2", "Cho may tinh vao che do ngu",           "system_sleep()"),
    (48, "WF10-3", "Huy lenh tat may tinh",                 "shutdown_abort()"),
    (49, "WF10-4", "Khoi dong lai may tinh",                "system_restart()"),
    (50, "WF10-5", "Kiem tra tinh trang pin cua may",       "battery_status()"),
]

# Vietnamese phrases (for display)
VI_PHRASES = [
    "Mở Notepad lên cho tôi",
    "Mở máy tính tính tiền",
    "Mở File Explorer ra",
    "Khởi động ứng dụng Spotify",
    "Mở Task Manager xem hiệu năng",
    "Mở trang Google",
    "Mở kênh YouTube lên",
    "Truy cập vào trang GitHub",
    "Mở báo Dân Trí đọc tin tức",
    "Mở trang ChatGPT",
    "Tăng âm lượng lên mười phần trăm",
    "Giảm âm lượng xuống",
    "Tắt tiếng loa đi",
    "Đặt âm lượng ở mức năm mươi phần trăm",
    "Tăng độ sáng màn hình lên",
    "Bật một bài nhạc nhẹ không lời",
    "Tạm dừng phát nhạc",
    "Tiếp tục phát bài hát",
    "Chuyển sang bài tiếp theo",
    "Quay lại bài vừa phát",
    "Hẹn giờ cho tôi năm phút nữa",
    "Đặt báo thức lúc bảy giờ sáng mai",
    "Hủy hẹn giờ đang chạy",
    "Còn bao nhiêu thời gian nữa hết giờ",
    "Đặt đồng hồ đếm ngược hai mươi phút",
    "Ghi chú nhớ nộp báo cáo lúc mười bốn giờ",
    "Nhắc tôi uống nước sau một tiếng nữa",
    "Đọc lại các ghi chú hôm nay của tôi",
    "Xóa ghi chú mua hàng hôm qua đi",
    "Thêm vào việc cần làm gọi điện cho đối tác",
    "Thời tiết hôm nay thế nào",
    "Ngày mai có mưa không",
    "Nhiệt độ hiện tại ở Hà Nội là bao nhiêu",
    "Thời tiết Thành phố Hồ Chí Minh cuối tuần",
    "Độ ẩm không khí bây giờ ra sao",
    "Bật đèn phòng khách lên",
    "Tắt đèn phòng ngủ",
    "Nhiệt độ phòng ngủ hiện tại là bao nhiêu",
    "Kéo rèm cửa sổ ra",
    "Bật điều hòa hai mươi lăm độ",
    "Tóm tắt điểm tin buổi sáng cho tôi",
    "Kiểm tra xem có tin nhắn Telegram mới không",
    "Kiểm tra hòm thư email chưa đọc",
    "Báo cáo trạng thái hệ thống hiện tại",
    "Kiểm tra kết nối mạng Internet",
    "Khóa màn hình máy tính lại",
    "Cho máy tính vào chế độ ngủ",
    "Hủy lệnh tắt máy tính",
    "Khởi động lại máy tính",
    "Kiểm tra tình trạng pin của máy",
]

OUT_DIR = Path(__file__).parent.parent / "docs" / "eval" / "h13_recordings"
SAMPLE_RATE = 16000
RECORD_SECONDS = 5


def record_phrase(filename, duration=RECORD_SECONDS):
    try:
        import sounddevice as sd
        print(f"  Recording {duration}s... SPEAK NOW!", end="", flush=True)
        import numpy as np
        audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
        print(" Done!")
        filename.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(filename), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        return True
    except ImportError:
        print("\nERROR: pip install sounddevice numpy")
        return False


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("H-13 Voice Recording — JARVIS Beta v1")
    print(f"Recording {RECORD_SECONDS}s per phrase. Quiet room, 50-80cm from mic.")
    print("Press Enter before each phrase. Ctrl+C to pause.\n")

    done = 0
    for i, (num, wf_id, _, expected) in enumerate(CASES):
        wav_path = OUT_DIR / f"case_{num:02d}.wav"
        phrase_vi = VI_PHRASES[i]
        if wav_path.exists():
            print(f"[{num:02d}/50] SKIP (already recorded): {phrase_vi[:50]}")
            done += 1
            continue
        print(f"\n{'─'*60}")
        print(f"[{num:02d}/50] {wf_id} | Expected: {expected}")
        print(f"  SAY: \"{phrase_vi}\"")
        input("  Press Enter to start recording...")
        if record_phrase(wav_path):
            done += 1
        else:
            break

    print(f"\nDone! {done}/50 files in {OUT_DIR}")
    print("Next: python scripts/h13_run_test.py")


if __name__ == "__main__":
    main()
