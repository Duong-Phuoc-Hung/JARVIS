"""
H-13 TTS Tier-2 Simulation
===========================
Generates 50 Vietnamese audio clips using edge-tts (vi-VN-HoaiMyNeural)
and runs them through JARVIS STT + Intent Router.

WARNING: TIER 2 ONLY. Does NOT close H-13.
Per docs/eval/beta_voice_50_live_acceptance_protocol.md line 12-13:
"H-13 doi hoi con nguoi that ngoi truoc may tinh, noi qua micro that"
This simulation CANNOT substitute for H-13. H-13 remains PENDING_HUMAN_EXECUTION.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEST_CASES = [
    ("WF01-1", "Mo Notepad len cho toi", "open_app"),
    ("WF01-2", "Mo may tinh tinh tien", "open_app"),
    ("WF01-3", "Mo File Explorer ra", "open_app"),
    ("WF01-4", "Khoi dong ung dung Spotify", "open_app"),
    ("WF01-5", "Mo Task Manager xem hieu nang", "open_app"),
    ("WF02-1", "Mo trang Google", "web_open"),
    ("WF02-2", "Mo kenh YouTube len", "web_open"),
    ("WF02-3", "Truy cap vao trang GitHub", "web_open"),
    ("WF02-4", "Mo bao Dan Tri doc tin tuc", "web_open"),
    ("WF02-5", "Mo trang ChatGPT", "web_open"),
    ("WF03-1", "Tang am luong len muoi phan tram", "volume_control"),
    ("WF03-2", "Giam am luong xuong", "volume_control"),
    ("WF03-3", "Tat tieng loa di", "volume_control"),
    ("WF03-4", "Dat am luong o muc nam muoi phan tram", "volume_control"),
    ("WF03-5", "Tang do sang man hinh len", "brightness_control"),
    ("WF04-1", "Bat mot bai nhac nhe khong loi", "music_play"),
    ("WF04-2", "Tam dung phat nhac", "music_pause"),
    ("WF04-3", "Tiep tuc phat bai hat", "music_resume"),
    ("WF04-4", "Chuyen sang bai tiep theo", "music_next"),
    ("WF04-5", "Quay lai bai vua phat", "music_prev"),
    ("WF05-1", "Hen gio cho toi nam phut nua", "timer_set"),
    ("WF05-2", "Dat bao thuc luc bay gio sang mai", "alarm_set"),
    ("WF05-3", "Huy hen gio dang chay", "timer_cancel"),
    ("WF05-4", "Con bao nhieu thoi gian nua het gio", "timer_status"),
    ("WF05-5", "Dat dong ho dem nguoc hai muoi phut", "timer_set"),
    ("WF06-1", "Ghi chu nho nop bao cao luc muoi bon gio", "note_create"),
    ("WF06-2", "Nhac toi uong nuoc sau mot tieng nua", "reminder_set"),
    ("WF06-3", "Doc lai cac ghi chu hom nay cua toi", "note_list"),
    ("WF06-4", "Xoa ghi chu mua hang hom qua di", "note_delete"),
    ("WF06-5", "Them vao viec can lam goi dien cho doi tac", "todo_add"),
    ("WF07-1", "Thoi tiet hom nay the nao", "weather_query"),
    ("WF07-2", "Ngay mai co mua khong", "weather_query"),
    ("WF07-3", "Nhiet do hien tai o Ha Noi la bao nhieu", "weather_query"),
    ("WF07-4", "Thoi tiet Thanh pho Ho Chi Minh cuoi tuan", "weather_query"),
    ("WF07-5", "Do am khong khi bay gio ra sao", "weather_query"),
    ("WF08-1", "Bat den phong khach len", "home_assistant"),
    ("WF08-2", "Tat den phong ngu", "home_assistant"),
    ("WF08-3", "Nhiet do phong ngu hien tai la bao nhieu", "home_assistant"),
    ("WF08-4", "Keo rem cua so ra", "home_assistant"),
    ("WF08-5", "Bat dieu hoa hai muoi lam do", "home_assistant"),
    ("WF09-1", "Tom tat diem tin buoi sang cho toi", "morning_briefing"),
    ("WF09-2", "Kiem tra xem co tin nhan Telegram moi khong", "telegram_check"),
    ("WF09-3", "Kiem tra hom thu email chua doc", "email_check"),
    ("WF09-4", "Bao cao trang thai he thong hien tai", "system_status"),
    ("WF09-5", "Kiem tra ket noi mang Internet", "network_check"),
    ("WF10-1", "Khoa man hinh may tinh lai", "system_lock"),
    ("WF10-2", "Cho may tinh vao che do ngu", "system_sleep"),
    ("WF10-3", "Huy lenh tat may tinh", "shutdown_abort"),
    ("WF10-4", "Khoi dong lai may tinh", "system_restart"),
    ("WF10-5", "Kiem tra tinh trang pin cua may", "battery_status"),
]

VOICE = "vi-VN-HoaiMyNeural"
OUT_DIR = Path("docs/eval/h13_tts_tier2")


async def gen_audio(case_id: str, text: str) -> Path:
    import edge_tts
    p = OUT_DIR / f"{case_id}.mp3"
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(str(p))
    return p


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating {len(TEST_CASES)} TTS clips (voice={VOICE})...")
    paths = await asyncio.gather(*[gen_audio(c, t) for c, t, _ in TEST_CASES])
    print(f"Generated {len(paths)} files in {OUT_DIR}\n")

    print("Running STT + Intent Router...")
    try:
        from faster_whisper import WhisperModel
        try:
            model = WhisperModel("large-v3", device="cuda", compute_type="int8_float16")
            model_name = "large-v3 CUDA"
        except Exception:
            model = WhisperModel("small", device="cpu", compute_type="int8")
            model_name = "small CPU"
        print(f"STT model: {model_name}")
    except ImportError:
        print("SKIP: faster-whisper not available")
        return

    try:
        from jarvis.router.intent_router import IntentRouter
        router = IntentRouter()
        router_ok = True
    except Exception as e:
        print(f"Router unavailable: {e}")
        router_ok = False

    results = []
    counts = {"CORRECT": 0, "MISROUTED": 0, "STT_EMPTY": 0, "ROUTER_ABSTAIN": 0}

    for (case_id, text, expected), audio_path in zip(TEST_CASES, paths):
        t0 = time.time()
        segs, _ = model.transcribe(str(audio_path), language="vi", beam_size=3)
        transcribed = " ".join(s.text.strip() for s in segs).strip()
        lat = round((time.time() - t0) * 1000, 1)

        if not transcribed:
            status, action = "STT_EMPTY", None
        elif not router_ok:
            status, action = "ROUTER_ABSTAIN", "router_unavailable"
        else:
            try:
                r = router.route(transcribed)
                action = str(getattr(r, "action", None) or getattr(r, "intent", r))
                status = "CORRECT" if expected.lower() in action.lower() else "MISROUTED"
            except Exception as e:
                status, action = "ROUTER_ABSTAIN", str(e)[:60]

        counts[status] = counts.get(status, 0) + 1
        print(f"  {case_id}: {status} | {transcribed[:35]} | {lat}ms")
        results.append({"case_id": case_id, "status": status, "transcribed": transcribed,
                        "expected": expected, "actual": action, "latency_ms": lat})

    total = len(results)
    acc = counts["CORRECT"] / total * 100
    arith = f"{counts['CORRECT']}+{counts['MISROUTED']}+{counts['STT_EMPTY']}+{counts['ROUTER_ABSTAIN']}={total}"
    print(f"\n=== H-13 TTS TIER-2 RESULTS ===")
    print(f"Arithmetic: {arith}")
    print(f"Accuracy: {acc:.1f}%")
    print("WARNING: H-13 still PENDING_HUMAN_EXECUTION")

    output = {
        "tier": "TIER_2_SYNTHETIC_TTS",
        "warning": "Does NOT close H-13. Real human voice (Tier 1) required.",
        "voice_model": VOICE,
        "stt_model": model_name,
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": total,
        "counts": counts,
        "accuracy_pct": round(acc, 1),
        "arithmetic_check": arith,
        "results": results,
    }
    op = OUT_DIR / "h13_tts_simulation_results.json"
    op.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {op}")


if __name__ == "__main__":
    asyncio.run(main())
