# Original User Request

## 2026-09-02T07:28:59Z

JARVIS là AI Voice Assistant tiếng Việt chạy Windows 11, hiện ở v4.6.0.
Nhiệm vụ Sprint 2: implement các hạng mục P1 (Accuracy, Acoustic & UX Hardening) theo ROADMAP v4.7.0.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: benchmark

---

## Bối cảnh Sprint 1 đã xong (v4.6.0)

| Hạng mục | Kết quả |
|----------|---------|
| ProactiveEngine (`workers/proactive.py`) | ✅ Tạo mới hoàn chỉnh |
| Wake word: Vosk + faster-whisper fallback | ✅ Wired, multi-tier cascade |
| Tier-2 LLM routing (force_llm=False) | ✅ Verified via OpenAI Tool Calling |
| Router Tier-1 +80 rules | ✅ SILENT 0%, MISROUTED 0% (N=143) |
| Test suite | ✅ 0 failures |
| `docs/ROADMAP.md` | ✅ 748 lines, Sprint 1–4 plan |

**Baseline v4.6.0:**
- STT text-routing: CORRECT 100%, SILENT 0%, MISROUTED 0% (N=143)
- STT acoustic: ~22% (small model), latency 853ms
- Deps MISSING: `vosk` (model not downloaded), `cv2`, `mediapipe`, `playwright`
- Env vars SET: `OPENAI_API_KEY`, `GOOGLE_API_KEY`
- Env vars NOT SET: `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `TELEGRAM_BOT_TOKEN`

---

## Requirements Sprint 2 (v4.7.0)

### R1. P1-8: DSP Acoustic Hardening — Chống Echo & False Positive

**File:** `jarvis/audio/wake_word.py`, `jarvis/core/app.py`

Sprint 1 đã tăng cooldown 1s→2.5s. Sprint 2 cần hardening sâu hơn:
- **Implement Voice Activity Detection (VAD)** bằng energy-based hoặc WebRTC VAD để chỉ xử lý frame có giọng nói thực, loại bỏ silence/noise frames trước khi đưa vào wake word detector
- **Acoustic Echo Cancellation tốt hơn**: sau khi TTS phát xong, disable microphone input 2.5s (không chỉ ignore trigger — thực sự không xử lý audio frames trong window này)
- **SFM/ZCR thresholds review**: verify các threshold hiện tại (flatness 0.03, ZCR) không quá aggressive với giọng nói thật
- **Verify**: false positive rate từ speaker output ≤ 1 trigger mỗi 30 phút trong điều kiện TTS bình thường

### R2. P1-9: SAPI5 TTS Thread Safety — COM Initialization

**File:** `jarvis/tts/manager.py`

`SAPI5` (Windows built-in TTS) yêu cầu `pythoncom.CoInitialize()` trên mỗi thread riêng biệt. Hiện tại `_worker_thread` daemon trong TTSManager có thể crash với `CoInitialize has not been called` trên Windows.
- **Fix**: thêm `pythoncom.CoInitialize()` vào `_worker_thread` target function trước khi khởi tạo `win32com.client.Dispatch("SAPI.SpVoice")`
- **Add `pythoncom.CoUninitialize()`** trong finally block
- **Verify**: TTS speaks 10 consecutive phrases in daemon thread without COM error

### R3. P1-10: Faster-Whisper Pre-loading & VAD Trim

**File:** `jarvis/stt/engine.py`

Hiện tại `FasterWhisperSTT` load model on first call → latency spike 2-5s trên lần đầu.
- **Pre-load model** khi khởi tạo class (lazy load → eager load với background thread)
- **Implement VAD-based silence trimming**: dùng `faster_whisper` built-in `vad_filter=True` và `vad_parameters={"min_silence_duration_ms": 500}` để cắt silence trước khi transcribe
- **Target**: cold-start latency ≤ 200ms sau preload (model đã trong memory)
- **Verify**: `time.time()` difference từ lúc gọi `transcribe()` đến khi nhận kết quả ≤ 1.5s trên file audio 3 giây

### R4. P1-6 & P1-7: HUD Overlay Non-Blocking & System Tray

**Files:** `jarvis/ui/overlay.py`, `jarvis/ui/tray.py`, `jarvis/core/app.py`

**P1-6: HUD Overlay thread isolation**
- Kiểm tra `AlwaysOnOverlay` có chạy trên thread riêng (không block main audio loop) hay không
- Nếu dùng Tkinter: đảm bảo `mainloop()` chạy trên dedicated thread, mọi update từ thread khác qua `after()` callback
- **Verify**: voice recording latency không tăng khi overlay đang hiển thị animation

**P1-7: System Tray Controls**
- Verify tray có các menu items: Bật/Tắt Wake Word, Bật/Tắt Mic, Thoát
- Thêm menu item: **"Status"** hiển thị: phiên bản, trạng thái TTS, trạng thái STT model, RAM usage
- **Verify**: tray icon hoạt động, menu items callable và không crash

### R5. P1-11: Hardware Voice Reporting

**File:** `jarvis/hardware/reporter.py`, `jarvis/llm/router.py`

- Verify `HardwareReporter.format_voice_summary()` trả về chuỗi tiếng Việt có thông số CPU%, RAM%, nhiệt độ GPU
- Thêm router rules cho: `"cpu mấy phần trăm"`, `"ram còn bao nhiêu"`, `"nhiệt độ máy"`, `"pin còn bao nhiêu"`, `"tốc độ cpu"` → action `system_status`
- **Verify**: 5 utterances trên map đúng intent `system_status`, MISROUTED = 0

### R6. Test Suite Integrity

- Chạy `pytest tests/unit/ tests/test_adversarial_*.py -q` → 0 failures
- Chạy `python tests/eval/routing_eval_n150.py` → SILENT ≤ 5%, MISROUTED = 0
- Cập nhật `CHANGELOG.md` v4.7.0 với đầy đủ thay đổi
- Commit và push lên `origin main` với message format: `feat: v4.7.0 - Sprint 2 Acoustic & UX Hardening`

---

## Acceptance Criteria

### DSP & Echo (R1)
- [ ] VAD filter active: silent frames không đưa vào wake word detector
- [ ] Microphone muted/ignored for exactly 2.5s after TTS completes (implementation-level, not just flag)
- [ ] `tests/unit/test_acoustic_hardening.py`: ≥ 5 tests pass về VAD filtering và echo suppression

### SAPI5 COM Safety (R2)
- [ ] `pythoncom.CoInitialize()` được gọi trong TTS worker thread
- [ ] 10 consecutive TTS calls in daemon thread → 0 COM errors
- [ ] `tests/unit/test_tts_com_safety.py`: ≥ 3 tests pass

### Faster-Whisper Pre-load (R3)
- [ ] `FasterWhisperSTT.__init__()` starts model loading in background thread
- [ ] Second call to `transcribe()` (model warm) takes ≤ 1.5s for 3-second audio
- [ ] `vad_filter=True` in transcribe call (verify in source)
- [ ] `tests/unit/test_stt_preload.py`: ≥ 3 tests pass

### HUD & Tray (R4)
- [ ] Overlay update calls go through `after()` or equivalent (no direct Tkinter from non-main thread)
- [ ] Tray menu has ≥ 4 items including new "Status"
- [ ] `tests/unit/test_tray_menu.py` hoặc similar: ≥ 3 tests pass

### Hardware Voice (R5)
- [ ] 5 hardware query utterances route to `system_status` (MISROUTED = 0)
- [ ] `format_voice_summary()` returns non-empty string with CPU%, RAM% values

### Overall (R6)
- [ ] `pytest tests/unit/ -q` → 0 failures
- [ ] `pytest tests/test_adversarial_*.py -q` → 0 failures
- [ ] `routing_eval_n150.py` → SILENT ≤ 5%, MISROUTED = 0
- [ ] `CHANGELOG.md` has v4.7.0 entry
- [ ] `jarvis/__init__.py` has `__version__ = "4.7.0"`
- [ ] Pushed to `origin main`

---

## Verification Resources

- `tests/eval/routing_eval_n150.py` — router coverage eval
- `docs/ROADMAP.md` — Sprint 2 detail at lines 652–672
- `AUDIT_METHODOLOGY.md` — evaluation rules (Tier 1/2/3, Wilson CI)
- `CHANGELOG.md` — v4.6.0 entry for format reference
- `jarvis/audio/wake_word.py` — current wake word implementation (multi-tier)
- `jarvis/tts/manager.py` — TTS manager with SAPI5 fallback
- `jarvis/stt/engine.py` — FasterWhisperSTT implementation
