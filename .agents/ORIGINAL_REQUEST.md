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

## 2026-09-02T14:50:58Z

JARVIS là AI Voice Assistant tiếng Việt chạy Windows 11, hiện ở v4.7.0.
Nhiệm vụ Sprint 3: implement các hạng mục P2 (Multimodal Feature Completion) theo ROADMAP v4.8.0.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: benchmark

---

## Bối cảnh Sprint 1-2 đã xong

| Sprint | Version | Kết quả |
|--------|---------|----------|
| Sprint 1 | v4.6.0 | ProactiveEngine, Wake word Vosk+Whisper, Router +80 rules, ROADMAP 748 lines |
| Sprint 2 | v4.7.0 | VAD energy gate, SAPI5 COM safety, Whisper preload, HUD non-blocking, Tray Status, +37 tests |

**Baseline v4.7.0:**
- Router: CORRECT 100%, SILENT 0%, MISROUTED 0% (N=148)
- Test suite: 0 failures
- Deps installed: `elevenlabs`, `sounddevice`, `faster_whisper`, `keyring`, `psutil`
- Deps MISSING: `vosk` (model not downloaded), `cv2`, `mediapipe`, `playwright`
- Env vars SET: `OPENAI_API_KEY`, `GOOGLE_API_KEY`
- Env vars NOT SET: `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `WEATHER_API_KEY`, `TELEGRAM_BOT_TOKEN`
- `jarvis/__init__.py`: `__version__ = "4.7.0"`

---

## Requirements Sprint 3 (v4.8.0)

### R1. P2-12: Two-Layer Stateful Memory System

**Files:** `jarvis/memory/manager.py`, `jarvis/memory/session.py`, `jarvis/memory/schema.sql`

Triển khai bộ nhớ ngữ cảnh 2 tầng:
- **Session sliding window** (10 lượt gần nhất) cho đối thoại liên tục
- **SQLite persistent store** (`logs/memory.db`, WAL mode) cho thông tin dài hạn: facts, episodes, user habits
- CRUD an toàn đa luồng: `save_fact`, `get_fact`, `record_episode`, `summarize_day`
- Tiêm context vào LLM prompt (session history + relevant facts)
- Đăng ký actions: `memory_save_fact`, `memory_query_fact`, `memory_summarize_daily`
- **Verify**: stress-test 30 threads concurrent read/write không `database is locked`

### R2. P2-13: Screen Vision & Dialog Detector

**Files:** `jarvis/vision/screen.py`, `jarvis/vision/vision_client.py`, `jarvis/vision/dialog_detector.py`

- `ScreenCaptureManager`: chụp màn hình bằng `mss`, nén JPEG 80%, <100ms
- `VisionLLMClient`: gửi ảnh Base64 tới Gemini hoặc OpenAI Vision API
- Win32 `EnumWindows` phát hiện dialog lỗi `#32770`, trích xuất nội dung
- Đăng ký actions: `screen_capture`, `screen_analyze`, `screen_explain_error`, `screen_summarize`
- **Verify**: payload ảnh tuân thủ schema provider LLM

### R3. P2-14: Real-Time Web Intelligence Hub

**Files:** `jarvis/web/search.py`, `jarvis/web/weather.py`, `jarvis/web/news.py`, `jarvis/web/finance.py`, `jarvis/web/cache.py`

- `TTLCache` thread-safe (TTL=600s, `threading.RLock`, SHA-256 key)
- DuckDuckGo search client (miễn phí, không cần API key)
- Thời tiết: OpenWeatherMap / wttr.in fallback
- RSS tin tức tiếng Việt: VnExpress, Tuổi Trẻ (dùng `xml.etree.ElementTree`)
- Tỷ giá crypto/forex: BTC, ETH, USD/VND
- Đăng ký actions: `web_search`, `weather_query`, `news_headlines`, `crypto_rates`, `morning_briefing`
- **Verify**: cache hit trong 10 phút, timeout graceful khi mất mạng (≤2s)

### R4. P2-15: Browser Automation

**Files:** `jarvis/browser/controller.py`, `jarvis/browser/actions.py`

- `BrowserController` quản lý Playwright Chromium headless session
- Actions: `navigate`, `click`, `type_text`, extract HTML
- Domain allowlist sandbox (ngăn truy cập trang độc hại)
- Graceful fallback khi `playwright` chưa cài (log warning, return stub)
- Đăng ký actions: `browser_navigate`, `browser_scrape`, `browser_fill_form`
- **Verify**: mock test navigate + extract HTML pass

### R5. P2-16: Telegram Bot Integration

**Files:** `jarvis/comms/telegram_bot.py`, `jarvis/comms/notifier.py`

- `TelegramNotifier`: gửi Markdown text + file qua REST API
- Long-polling nhận lệnh từ xa với `allowed_user_ids` whitelist
- Kết nối ProactiveEngine → auto-push alerts đến điện thoại
- Graceful fallback khi `TELEGRAM_BOT_TOKEN` chưa set (log warning)
- **Verify**: mock HTTP endpoint test pass, injection test rejected

### R6. Test Suite & Release

- Mỗi R1-R5 phải có unit tests trong `tests/unit/`
- Chạy `pytest tests/unit/ -q` → 0 failures
- Chạy `pytest tests/test_adversarial_*.py -q` → 0 failures
- Đăng ký ≥ 12 actions mới qua ActionDispatcher
- Cập nhật `jarvis/__init__.py` → `__version__ = "4.8.0"`
- Cập nhật `CHANGELOG.md` với v4.8.0 entry
- Commit và push lên `origin main`

---

## Acceptance Criteria

### Memory System (R1)
- [ ] `jarvis/memory/manager.py` tồn tại và importable
- [ ] SQLite WAL mode enabled trên `logs/memory.db`
- [ ] `save_fact` + `get_fact` round-trip: data lưu và đọc đúng
- [ ] 30-thread stress test: 0 `database is locked` errors
- [ ] `tests/unit/test_memory_system.py`: ≥ 5 tests pass

### Screen Vision (R2)
- [ ] `ScreenCaptureManager.capture()` returns JPEG bytes <100ms
- [ ] `VisionLLMClient` builds valid API payload (Gemini + OpenAI)
- [ ] Dialog detector finds `#32770` windows on Win32
- [ ] `tests/unit/test_screen_vision.py`: ≥ 4 tests pass

### Web Intelligence (R3)
- [ ] `TTLCache` returns cached data within TTL window
- [ ] DuckDuckGo search returns ≥ 1 result (mock or real)
- [ ] Weather fallback (wttr.in) works when API key missing
- [ ] RSS parser extracts ≥ 1 headline from XML feed
- [ ] Network timeout handled gracefully (no crash, ≤ 2s)
- [ ] `tests/unit/test_web_intelligence.py`: ≥ 6 tests pass

### Browser Automation (R4)
- [ ] `BrowserController` initializes without crash (even without playwright)
- [ ] Domain allowlist blocks disallowed URLs
- [ ] `tests/unit/test_browser_automation.py`: ≥ 3 tests pass

### Telegram Bot (R5)
- [ ] `TelegramNotifier.send_message()` sends POST to Telegram API
- [ ] `allowed_user_ids` whitelist blocks unauthorized users
- [ ] Graceful when `TELEGRAM_BOT_TOKEN` not set
- [ ] `tests/unit/test_telegram_bot.py`: ≥ 3 tests pass

### Overall (R6)
- [ ] `pytest tests/unit/ -q` → 0 failures
- [ ] `pytest tests/test_adversarial_*.py -q` → 0 failures
- [ ] ≥ 12 new actions registered in ActionDispatcher
- [ ] `jarvis/__init__.py` has `__version__ = "4.8.0"`
- [ ] `CHANGELOG.md` has v4.8.0 entry
- [ ] All changes committed and pushed to `origin main`

---

## Verification Resources

- `docs/ROADMAP.md` — Sprint 3 detail at lines 675–694 (P2-12 through P2-17)
- `CHANGELOG.md` — v4.7.0 entry for format reference
- `jarvis/core/app.py` — ActionDispatcher registration pattern (L516-L800)
- `jarvis/memory/` — existing memory module (may have partial impl)
- `jarvis/vision/` — existing vision module (screen.py, dialog_detector.py)
- `jarvis/web/` — existing web module (weather.py, etc.)
- `jarvis/browser/` — existing browser module (partial impl)
- `jarvis/comms/` — existing comms module (telegram_bot.py, email_imap.py)
- `tests/eval/routing_eval_n150.py` — router eval script

## 2026-09-03T15:09:08Z

Nâng cấp độ chính xác và khả năng chống Overfitting cho Voice Pipeline của JARVIS: triển khai Preprocessing Diacritic Normalization an toàn, đánh giá tách bạch trên 90 file audio thật, mở rộng alias ngữ âm có kiểm soát, xây dựng Held-Out Test Set độc lập (25-30 câu mới), cập nhật CHANGELOG/README và đẩy lên Git main.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: benchmark

---

## Requirements

### R1. Safe Preprocessing Diacritic Normalization
- Triển khai hàm `strip_vietnamese_diacritics(text: str) -> str` trong `jarvis/llm/router.py`.
- Tích hợp chuẩn hóa không dấu an toàn vào `_match_rule_key`:
  - **Chỉ áp dụng diacritic folding cho cụm từ nhiều tiếng (`len(words) >= 2`)**: ví dụ `"điều chỉnh âm lượng"`, `"tìm kiếm google"`, `"trời hôm nay thế nào"`.
  - **Từ đơn (`len(words) == 1`)**: Bắt buộc so khớp nguyên vẹn cả từ (whole-word token match), KHÔNG bỏ dấu kiểu chuỗi con để triệt tiêu vĩnh viễn va chạm ngữ âm (e.g. `nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`).
- Đồng bộ hóa `tests/eval/stt_intent_eval.py` để `predict_intent` gọi qua router production với chuẩn hóa diacritic thay vì quét thô dictionary.

### R2. Baseline Evaluation trên 90 File Audio Thật (Ablation Step 2)
- Chạy `tests/eval/stt_intent_eval.py --models large-v3 --backend direct` trên 90 file WAV thật (clean + noisy).
- Đo lường và đối chiếu độc lập hiệu quả của riêng bước Preprocessing Diacritic Normalization:
  - Tỷ lệ `CORRECT` tăng từ 37.8% lên ≥ 44.4%.
  - `ROUTER_ABSTAIN` giảm từ 58.9% xuống ≤ 50.0%.
  - `MISROUTED` giữ nguyên ≤ 3.3% (0 ca misrouting mới nào được tạo ra).

### R3. Selective & Safe Phonetic Drift Aliases (Step 3)
- Bổ sung có chọn lọc các biến thể ngữ âm thực tế mà Faster-Whisper nghe nhầm nhưng có độ đặc hiệu ngữ nghĩa cao, không có nguy cơ nhầm lẫn sang intent khác:
  - `system_power`: `"tắc máy"`, `"tập máy tính"`, `"sắt đau má"` (shutdown).
  - `app_open`: `"cái đặt"`, `"má kẻ đặt"`, `"open sentence"`, `"open sente"`.
  - `reminder`: `"đặt time"`, `"đặc nhắc"`.
  - `system_volume`: `"tắc tính"`, `"tắt tính"`.
  - `memory_save_fact`: `"ghi chú"`, `"ghi chu"`, `"tạo ghi chú mới"`, `"tao ghi chu moi"`.
- Đảm bảo các rule này không tạo ra misrouting mới trên test suite hiện có.

### R4. Held-Out Generalization Evaluation (Anti-Overfitting Verification — Step 4)
- Xây dựng file test held-out độc lập `tests/eval/test_voice_generalization_heldout.py` với ít nhất 25–30 câu lệnh mới hoàn toàn chưa từng xuất hiện trong 90 file WAV cũ.
- Bao phủ đầy đủ các intent: thời tiết, nhắc nhở, điều khiển hệ thống, tìm kiếm, âm lượng, ghi chú, ứng dụng.
- Đánh giá khả năng tổng quát hóa của Router:
  - `CORRECT >= 85%` trên tập held-out mới.
  - `MISROUTED == 0`.

### R5. Full Test Suite Integrity, CHANGELOG, README & Git Main Push
- Chạy toàn bộ test suite: `pytest tests/unit/ tests/test_adversarial_*.py -q` → 0 failures.
- Cập nhật `CHANGELOG.md` ghi nhận v4.8.1:
  - Safe Preprocessing Diacritic Normalization (Zero-Homophone-Collision).
  - Kết quả benchmark STT trên 90 audio file thật (CORRECT, ROUTER_ABSTAIN, MISROUTED).
  - Held-out Generalization Evaluation (N=30 unseen utterances).
- Cập nhật `README.md` phần voice recognition và các câu lệnh hỗ trợ.
- Commit và push sạch lên branch `origin main`.

---

## Acceptance Criteria

### Preprocessing Diacritic Normalization (R1)
- [ ] `strip_vietnamese_diacritics` hoạt động đúng cho toàn bộ bảng chữ cái tiếng Việt (kể cả `đ/Đ` và các ký tự tổ hợp).
- [ ] Không có va chạm homophone giữa `nhạc` và `nhắc nhở lúc...`, giữa `dừng` và `ứng dụng`, giữa `dán` và `hấp dẫn`.
- [ ] `parse_intent("Điều chỉnh âm lượng")` trả về `system_volume`.
- [ ] `parse_intent("Tìm kiếm Google.")` trả về `web_open`.
- [ ] `parse_intent("Trời hôm nay thế nào?")` trả về `shell_exec`.

### Real Audio Evaluation (R2 & R3)
- [ ] Chạy `stt_intent_eval.py` trên 90 file audio thật hoàn tất không crash.
- [ ] Tỷ lệ `CORRECT` trên 90 audio file thật tăng ≥ 10 pp so với baseline cũ (37.8% → ≥ 50%).
- [ ] Tỷ lệ `MISROUTED` không tăng quá ngưỡng cho phép (≤ 4.4%).
- [ ] File kết quả lưu tại `docs/eval/stt_eval_results_direct.json` và `docs/eval/stt_eval_summaries_direct.json`.

### Held-Out Test Set (R4)
- [ ] File `tests/eval/test_voice_generalization_heldout.py` tồn tại với ≥ 25 test cases mới độc lập.
- [ ] 100% test cases trong tập held-out pass (`pytest tests/eval/test_voice_generalization_heldout.py` → 0 failures).

### Test Suite & Git Push (R5)
- [ ] `pytest tests/unit/ tests/test_adversarial_*.py -q` → 0 failures.
- [ ] `CHANGELOG.md` có mục v4.8.1 chi tiết.
- [ ] `README.md` được cập nhật.
- [ ] `git status` clean, commit đẩy thành công lên `origin main`.

