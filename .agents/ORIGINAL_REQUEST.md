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

## 2026-09-06T14:21:04Z

Kiểm toán độc lập và đánh giá toàn diện tính đúng đắn, độ tin cậy và khả năng hoạt động thực tế của từng chức năng/phân hệ trong dự án JARVIS theo chuẩn AUDIT_FRAMEWORK (4 trục: Evidence Tier, Truthfulness, Boundary Type, Blocked-by), kèm theo kiểm thử runtime probe và sinh test case biên cho các điểm nghẽn.

Working directory: d:\Software GitCode\JARVIS
Integrity mode: development

## Verification Resources
- `docs/AUDIT_FRAMEWORK.md`: Bộ tiêu chí đánh giá 4 trục và 19 cạm bẫy kiểm toán.
- `docs/ROADMAP.md`: Trạng thái các tính năng, phân loại Tier 1/Tier 2 hiện tại và danh mục cần audit.
- `AGENTS.md`: Tiêu chuẩn kỹ thuật cốt lõi (Fail-Closed, Atomic Persistence, Seam-First TDD, Synchronized Docs).
- Toàn bộ test suite hiện có trong thư mục `tests/` (`tests/unit/`, `tests/e2e/`, `tests/eval/`).

## Requirements

### R1. Phân rã và kiểm tra toàn diện các phân hệ chức năng
Đội ngũ agent phải rà soát và kiểm thử độc lập tất cả các phân hệ chức năng chính của JARVIS:
1. **Voice Pipeline**: TieredSTTEngine, Whisper local, Cloud STT fallback, VAD gating, Diacritic normalizer, Intent Router.
2. **Memory System**: SemanticVectorStore, SQLiteMemoryStore, MemoryManager, 30-thread concurrency, Atomic persistence.
3. **Security & InfoSec**: NetworkScanner, PacketCapture, SecretsManager (Windows Credential Manager), CodeInterpreterSandbox (Job Object & Low Integrity), ASTCodeValidator.
4. **Communications Hub**: TelegramBotController, DiscordBotController, Zalo OA adapter, Email IMAP reader, Mobile Bridge, TokenBucketRateLimiter.
5. **Browser & OS Control**: CDPDriver (Playwright CDP), Desktop automation, App launch/close, Media control, Audio endpoint switch.
6. **Terminal Control Center**: 9 module adapters (Biometrics, Comms, Data, Gesture, Hardware, Healing, Infosec, Smart Home, Workflow), Console engine, Session report.
7. **Self-Coding Engine**: SkillSynthesizer, SkillSandboxRunner, Dynamic skill registration.

### R2. Đánh giá độc lập theo 4 trục kỹ thuật (AUDIT_FRAMEWORK)
Mỗi chức năng phải được phân loại và lập hồ sơ minh bạch:
- **Trục 1 — Evidence Tier**: Gán nhãn 🟢 T1 (kiểm chứng thật trên OS/API thật), 🟡 T2 (mock thành phần cốt lõi), hoặc 🔴 T3 (chưa có test / mock toàn diện).
- **Trục 2 — Truthfulness**: Kiểm tra và xác nhận Fail-Closed vs Silent Fallback (`{"ok": True}` ảo) vs Active Fabrication (bịa số liệu) vs Ghost Process (tiến trình rỗng).
- **Trục 3 — Boundary Type**: Xác định Hard Boundary (Kernel-enforced) vs Risk-Reduction (Heuristic/Phòng thủ theo chiều sâu).
- **Trục 4 — Blocked-by**: Xác định trạng thái Không bị chặn vs Cần token/hạ tầng thật vs Cần quyết định thiết kế.

### R3. Thực thi kiểm thử runtime & Thử nghiệm đối kháng (Adversarial Probing)
- Chạy kiểm thử tự động trên mã nguồn production thực tế.
- Viết và chạy các runtime probe script kiểm tra điều kiện biên: input rỗng, tham số không hợp lệ, thiếu token cấu hình, ngắt kết nối mạng hoặc áp lực tải đồng thời.
- Viết bổ sung các ca kiểm thử mới cho các hàm đang có nghi vấn silent fallback hoặc chưa có bài test trực tiếp.

### R4. Lập báo cáo kiểm toán tổng thể (Master Audit Matrix)
- Tổng hợp toàn bộ kết quả vào tài liệu báo cáo `docs/FULL_FEATURE_AUDIT_REPORT.md`.
- Cung cấp bảng ma trận 4 trục cho 100% các chức năng được kiểm tra.
- Nêu rõ các phát hiện lỗi mới (nếu có), nguyên nhân gốc rễ và đề xuất khắc phục cụ thể theo quy trình TDD.

## Acceptance Criteria

### Tính toàn diện & Minh bạch
- [ ] Tất cả 7 phân hệ chính (R1) đều được kiểm tra độc lập và có mục đánh giá chi tiết trong báo cáo.
- [ ] 100% các chức năng được đánh giá đều có phân loại rõ ràng theo 4 trục (R2) kèm file test/runtime probe chứng minh.
- [ ] Không có phân hệ nào được tự chứng nhận 🟢 T1 nếu chỉ dựa trên test mock thành phần cốt lõi.

### Xác thực Runtime & Chống Fabrication
- [ ] Mọi tuyên bố về "hoạt động tốt" hoặc "fail-closed" đều phải dựa trên kết quả chạy lệnh pytest hoặc runtime script thực tế trên môi trường Windows hiện tại.
- [ ] Mọi trường hợp trả về kết quả giả định hoặc silent fallback được phát hiện đều phải có snippet mã nguồn và script tái hiện lỗi.

### Báo cáo & Tài liệu
- [ ] Báo cáo `docs/FULL_FEATURE_AUDIT_REPORT.md` được tạo đầy đủ với bảng ma trận tổng hợp, số liệu thống kê test pass/fail và danh mục khuyến nghị.
- [ ] Báo cáo tuân thủ nguyên tắc trung thực tuyệt đối theo `AGENTS.md` và `docs/AUDIT_FRAMEWORK.md`.


## 2026-09-13T10:25:05Z

# Teamwork Project Prompt — JARVIS Beta v1 Voice Pipeline & Core Integration

Working directory: d:\Software GitCode\JARVIS
Integrity mode: development

## Objective
Deliver a production-ready, verified Product Beta v1 of JARVIS on Windows with genuine evidence across all 17 Core/Backend/Release tasks (D-01 to D-17) and 13 Voice Pipeline tasks (H-01 to H-13). Prevent all fabrication, enforce fail-closed status codes, eliminate silent fallbacks, and validate voice recognition across multi-condition datasets.

---

## Requirements

### R1. Audio Capture & Hardware Synchronization (H-01, H-02, H-03)
- **16 kHz Direct Capture**: The audio recording subsystem must capture directly at 16000 Hz for Whisper STT models, eliminating 44.1kHz/48kHz linear interpolation distortions and transcription latency.
- **Microphone Device Synchronization**: Synchronize `record_audio()` with the active device index probed and selected by `AudioEngine`, ensuring wake-word detection and speech recording operate on the exact same physical input endpoint.
- **Acoustic Echo & Self-Contamination Suppression**: Enforce a post-TTS settling guard (~150ms) and active playback lockout to prevent the microphone from capturing synthesized Tony Stark/JARVIS voice responses.

### R2. Core Controls & Hardware Fail-Closed Semantics (H-04, H-08)
- **Zero-Crash Hotkeys**: Ensure global shortcut handlers (`Ctrl+Shift+L` PTT) dispatch directly to valid voice interaction routines without `AttributeError`.
- **Honest Hardware Status**: Master volume and display brightness controls must return explicit `status: failed`, `success: False`, and specific error codes (`VOLUME_SET_FAILED`, `BRIGHTNESS_SET_FAILED`) when endpoints return `None`, never converting hardware failures into ghost successes.

### R3. Multi-Condition Independent STT & Router Evaluation (H-05 / A1–A4)
- **Dataset Independence (A1)**: Prepare an independent test evaluation set of ≥200 audio utterances completely distinct from the historical 90-file evaluation set in `tests/eval/audio/`.
- **Dual Acoustic Conditions (A2)**: Execute evaluations across both `clean` and `noisy` acoustic environments.
- **Multi-Model Comparison (A3)**: Benchmark both `small` and `large-v3` models under direct execution to determine operational tradeoffs.
- **4-Way Outcome Reporting (A4)**: Provide transparent breakdown of `CORRECT`, `MISROUTED`, `STT_EMPTY`, and `ROUTER_ABSTAIN`.

### R4. Comms & Third-Party Integration Reality (D-06, D-07, D-08, D-09, D-14)
- Enforce explicit `NOT_CONFIGURED` status codes for Telegram, Zalo, Discord, and IMAP when credentials are missing.
- Document credentials requirement (`PENDING_CREDENTIALS`) and code signing certificate blocker (`BLOCKED_ON_CERT`) in release notes and readiness dashboard.

---

## Acceptance Criteria

### Audio & Pipeline Verification
- [ ] `pytest tests/unit/test_voice_pipeline_fixes.py -v` passes 100% (6/6).
- [ ] `record_audio()` requests 16000 Hz and passes `device=target_device` to sounddevice.
- [ ] `_handle_system_volume()` and `_handle_system_brightness()` return `success=False` when controller returns `None`.
- [ ] `Ctrl+Shift+L` hotkey initiates `_start_voice_interaction` with `"HOTKEY_PTT"`.

### Evaluation & Audit Truthfulness
- [ ] No claim of "100% achieved" without concrete sample size (N), passing test names, and raw execution logs.
- [ ] H-05 evaluation script executed on both clean and noisy sets with at least 2 models.
- [ ] All test results and evidence committed to git repository and synchronized in `CHANGELOG.md` and `task.md`.

## 2026-09-13T15:18:38Z

Hoàn thành phần còn thiếu của JARVIS Beta v1 trên repository tại `d:\Software GitCode\JARVIS` (commit cơ sở `a349520`). Cụ thể: chạy benchmark STT `large-v3` điều kiện `noisy` (N=210 âm thanh thật) để đóng H-05, cập nhật toàn bộ tài liệu phản ánh kết quả thực tế, xác nhận test suite vẫn 81/81 PASS, rồi commit và push lên `origin/main`.

Working directory: d:\Software GitCode\JARVIS
Integrity mode: development

## Context

Đây là dự án AI assistant JARVIS. Phiên làm việc trước đã hoàn thành:
- 81/81 automated tests PASS
- large-v3 clean benchmark: N=210, CORRECT=183 (87.1%), MISROUTED=3, ROUTER_ABSTAIN=24, latency p50=2785.2ms
- small model: N=420 (clean+noisy), CORRECT_total=241/420 (57.4%)

Còn thiếu: large-v3 **noisy** benchmark (N=210 âm thanh nhiễu) — đây là phần duy nhất có thể hoàn thành bằng phần mềm mà không cần phần cứng/người thật/credentials ngoài.

## Requirements

### R1. Chạy large-v3 noisy benchmark đến hoàn thành

Thực thi lệnh sau và chờ đến khi hoàn thành (ước tính ~2 giờ GPU):

```
.venv\Scripts\python.exe tests/eval/stt_intent_eval.py --audio-dir tests/eval/audio_independent --manifest tests/eval/independent_test_manifest.py --models large-v3 --conditions noisy --backend direct --out-dir docs/eval/independent_benchmark_large_noisy
```

Kết quả phải tạo ra ít nhất hai file:
- `docs/eval/independent_benchmark_large_noisy/stt_eval_summaries_direct.json`
- `docs/eval/independent_benchmark_large_noisy/stt_eval_results_direct.json`

Kết quả phải có `n_trials = 210`. Kiểm tra số học bắt buộc: `n_correct + n_misrouted + n_stt_empty + n_router_abstain = 210`.

### R2. Cập nhật 5 file tài liệu phản ánh kết quả thực tế

Sau khi có số liệu từ R1, cập nhật toàn bộ các file sau với số liệu đọc trực tiếp từ JSON output (không fabricate, không ước tính):

1. **`docs/eval/stt_eval_independent_summary.md`** — Thêm bảng large-v3 noisy (4-way breakdown, latency p50, kiểm tra số học)
2. **`docs/READINESS_DASHBOARD.md`** — Cập nhật H-05 từ `PARTIAL` sang `DONE` nếu kết quả hợp lệ; thêm dòng large-v3 noisy vào bảng benchmark
3. **`docs/ROADMAP.md`** — Cập nhật trạng thái H-05
4. **`CHANGELOG.md`** — Thêm entry ghi lại kết quả large-v3 noisy với số liệu cụ thể
5. **`README.md`** — Cập nhật dòng mô tả phiên bản nếu H-05 được đóng

**Quy tắc bắt buộc (từ AGENTS.md):**
- Mọi số liệu phải đọc từ JSON thực tế trên đĩa (không sinh ngầm định)
- Không được tuyên bố "H-05 DONE" nếu `n_trials ≠ 210` hoặc số học không khớp
- Nếu benchmark thất bại hoặc output không hợp lệ, ghi trạng thái `FAILED` và lý do cụ thể

### R3. Xác nhận test suite và git push

Chạy:
```
python -m pytest tests/e2e/test_beta_v1_acceptance.py tests/unit/test_voice_pipeline_fixes.py tests/unit/test_zalo_bot.py tests/test_adversarial_beta_m1_comms_failclosed.py tests/unit/test_setup_wizard.py -v --tb=short
```

Phải đạt **81/81 PASS** (hoặc cao hơn). Nếu có test fail, dừng và báo cáo lỗi — không push nếu test fail.

Sau khi test pass:
```
git add docs/eval/stt_eval_independent_summary.md docs/eval/independent_benchmark_large_noisy/ docs/READINESS_DASHBOARD.md docs/ROADMAP.md CHANGELOG.md README.md
git commit -m "feat(eval): complete H-05 large-v3 noisy benchmark N=210, update all docs"
git push origin main
```

## Acceptance Criteria

### Benchmark output
- [ ] `stt_eval_summaries_direct.json` tồn tại trong `docs/eval/independent_benchmark_large_noisy/`
- [ ] `n_trials = 210` trong JSON output
- [ ] Số học khớp: `n_correct + n_misrouted + n_stt_empty + n_router_abstain = 210`
- [ ] `median_latency_ms` có giá trị thực (không phải 0 hoặc None)

### Documentation
- [ ] `stt_eval_independent_summary.md` có bảng large-v3 noisy với số liệu từ JSON thực tế
- [ ] `READINESS_DASHBOARD.md` phản ánh trạng thái H-05 chính xác (DONE hoặc FAILED với lý do)
- [ ] Không có số liệu nào trong tài liệu mâu thuẫn với JSON output

### Test và Git
- [ ] Test suite: ≥ 81 passed, 0 failed
- [ ] Commit tồn tại trên `origin/main` sau push
- [ ] `git status` sạch sau push

## 2026-09-16T06:10:43Z

Complete the D-14 code signing milestone for the JARVIS Windows desktop assistant. The goal is to get GitHub Actions producing a properly Authenticode-signed `JARVIS.exe` without requiring a paid certificate authority, and document a clear upgrade path for production signing.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: development

## Context

JARVIS is a Windows desktop AI assistant built with Python/PyInstaller. The project uses:
- GitHub Actions for CI/CD (`.github/workflows/release.yml`)
- SignPath Foundation (free tier) — **confirmed**: Foundation tier blocks ALL CI-based signing (both direct REST API and GitHub Actions connector). CI signing requires paid plan.
- Currently using Option C (unsigned pass-through) as interim solution — exe ships without Authenticode, SmartScreen warns on first run.

## Requirements

### R1. Free CI-based Authenticode signing

Implement a working solution that signs `JARVIS.exe` with an Authenticode signature in the GitHub Actions CI pipeline at zero cost. Acceptable approaches (pick best one):

- **Self-signed certificate via signtool** (using a repo-stored PFX or generated in-workflow via PowerShell `New-SelfSignedCertificate`) — signature valid but not CA-trusted; eliminates "unsigned" status, SmartScreen still warns but differently
- **Azure Code Signing** free tier (if it exists and supports GitHub Actions) — may provide a trusted signature
- **Windows SDK signtool** with a test certificate
- Any other legitimate zero-cost Authenticode approach

The chosen approach must work reliably in `windows-latest` GitHub Actions runners. The signed exe must pass `Get-AuthenticodeSignature` with `Status = Valid` (self-signed is acceptable; `NotTrusted` is acceptable; `NotSigned` is NOT acceptable).

### R2. Manual signing documentation (Option A)

Document the step-by-step process for a human operator to manually sign `JARVIS.exe` using the existing SignPath account (interactive user submission via web UI at `app.signpath.io`). Store as `docs/signing/manual_signing_guide.md`. Include:
- How to download the unsigned artifact from a GitHub Actions run
- How to submit it via SignPath web UI
- How to attach the signed exe to a GitHub Release
- Estimated time: ≤15 minutes per release

### R3. Upgrade path documentation (Option B)

Document the cost and steps to upgrade SignPath to a paid tier (or switch to an alternative like DigiCert, Sectigo, or Azure Code Signing paid) for production CI signing. Store as `docs/signing/production_signing_upgrade.md`. Include:
- Current blocker: SignPath Foundation blocks `githubactions.connectors.signpath.io` CI connector
- Minimum paid tier needed and estimated cost
- Alternative: Microsoft Azure Code Signing (ACS) — pricing and GitHub Actions integration steps
- What changes in `release.yml` would be needed

### R4. Update CI workflow

Update `.github/workflows/release.yml` sign job to use the R1 solution instead of the current unsigned pass-through. The release body should clearly indicate whether the exe is self-signed or CA-trusted.

## Verification Resources

- Current workflow: `.github/workflows/release.yml` — sign job at line ~91
- SignPath API confirmed: `POST /api/v1/{orgId}/signing-requests` → 404 on Foundation tier
- Self-signed test: `$cert = New-SelfSignedCertificate -Type CodeSigning -Subject "CN=JARVIS Test" -CertStoreLocation Cert:\CurrentUser\My`; `$pfxPass = ConvertTo-SecureString "password" -AsPlainText -Force`; `Export-PfxCertificate -Cert $cert -FilePath jarvis_test.pfx -Password $pfxPass`; `signtool sign /f jarvis_test.pfx /p password /fd SHA256 JARVIS.exe`
- Verify: `Get-AuthenticodeSignature JARVIS.exe | Select-Object Status, SignerCertificate`

## Acceptance Criteria

### Signing (R1)
- [ ] `JARVIS.exe` produced by the CI pipeline passes `Get-AuthenticodeSignature` with `Status` = `Valid` or `UnknownError` (self-signed, not `NotSigned`)
- [ ] The signing step completes in ≤ 5 minutes in the GitHub Actions workflow
- [ ] No secrets cost money to set up (free certificate generation or free-tier service)
- [ ] The approach works reliably on `windows-latest` runners

### Documentation (R2 + R3)
- [ ] `docs/signing/manual_signing_guide.md` exists with ≥ 5 numbered steps, each ≤ 3 sentences
- [ ] `docs/signing/production_signing_upgrade.md` lists ≥ 2 alternative signing solutions with pricing

### Workflow (R4)
- [ ] `.github/workflows/release.yml` sign job uses the R1 approach (not the unsigned pass-through)
- [ ] Release body text accurately states the signing type (self-signed vs trusted)
- [ ] All existing GitHub Actions tests in JARVIS CI still pass (`pytest tests/unit/ -q` exits 0)

## 2026-09-16T12:02:27Z

Implement WASAPI exclusive mode capture fallback in the JARVIS audio engine so that Bluetooth HFP devices (LY-Z5202, AirPods) that currently fail with PaError -9999 can be captured successfully.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: development

## Context

JARVIS is a Windows AI assistant that uses `sounddevice` (PortAudio backend) for microphone capture in `jarvis/audio/engine.py`. Bluetooth HFP devices fail with `PaError -9999` (paDeviceUnavailable) because Windows holds an exclusive audio session for HFP devices that PortAudio cannot bypass.

**Confirmed hardware matrix** (from CHANGELOG [5.1.7]):
- TIER1_PASS (real signal): USB Audio [1] 16kHz, Realtek Array [3], USB Audio [27] 48kHz
- TIER1_FAIL: BT LY-Z5202 [32], AirPods Pro [48], AirPods PH [54] — all PaError -9999

**Root cause**: Windows OS session manager holds exclusive HFP session. PortAudio (sounddevice default) cannot bypass it. WASAPI exclusive mode opens the device directly at the kernel level, bypassing the session manager.

**Key codebase facts**:
- `jarvis/audio/engine.py` — 652 lines; stream opened at line 625 via `sd.InputStream(...)`
- `AudioEngineMode`: LIVE | MOCK | HEADLESS
- `_stream_worker()` at line 613: opens stream, retries 3x on exception, then degrades to MOCK
- AGENTS.md rule: Fail-Closed — must NOT silently return mock if a real BT device is explicitly selected and WASAPI also fails; surface the error truthfully

## Requirements

### R1. WASAPI Exclusive Capture Fallback

Modify `jarvis/audio/engine.py` `_stream_worker()` to attempt WASAPI exclusive mode when PortAudio fails with any exception (including PaError -9999). The retry sequence must be:

1. Try standard `sd.InputStream(device=idx, ...)` — existing behavior
2. If exception -> try `sd.InputStream(device=idx, extra_settings=sd.WasapiSettings(exclusive=True), samplerate=16000, channels=1, ...)` — WASAPI exclusive at 16kHz (HFP native rate)
3. If both fail -> log truthful error, set `self.mode = AudioEngineMode.MOCK` (existing fallback)

Add a config field `use_wasapi_exclusive: bool = True` to `AudioEngineConfig` (or equivalent config dataclass in the file). When False, skip step 2.

The WASAPI attempt must only be made on Windows (guard with `sys.platform == "win32"`). On non-Windows, maintain existing behavior.

### R2. Fail-Closed Semantics Preserved

If the user explicitly configured a specific BT device (via `input_device` config or `JARVIS_INPUT_DEVICE` env var) and BOTH PortAudio AND WASAPI fail:
- Do NOT silently substitute a different physical device
- Log: `"BT HFP device {idx} failed on both PortAudio and WASAPI exclusive. Entering MOCK mode. Error: {e}"`
- Publish `audio.device_unavailable` event on the event bus with `reason="wasapi_exclusive_failed"`
- This matches the existing `MicrophoneDeviceUnavailableError` fail-closed contract

### R3. Tests (TDD — Red first, then Green)

Add/update tests in `tests/unit/test_audio_engine.py`:

1. **test_wasapi_fallback_triggered_on_pa_error**: Mock `sd.InputStream` to raise `Exception("PaError -9999")` on first call, then succeed on second call (simulating WASAPI success). Assert `_stream_worker` called InputStream twice and the second call included `extra_settings` with `exclusive=True`.

2. **test_wasapi_fallback_both_fail_enters_mock**: Mock `sd.InputStream` to always raise `Exception("PaError -9999")`. Assert engine enters `AudioEngineMode.MOCK` after exhausting retries. Assert no True/success return is fabricated.

3. **test_wasapi_skipped_on_non_windows**: With `sys.platform` patched to `"linux"`, assert that -9999 failure does NOT trigger WASAPI retry — goes straight to reconnect/mock logic.

4. **test_wasapi_exclusive_disabled_config**: Set `use_wasapi_exclusive=False` in config. Assert WASAPI retry is never attempted even when PortAudio fails.

All 4 new tests must pass alongside ALL existing tests in `tests/unit/test_audio_engine.py`.

### R4. Documentation (MANDATORY per AGENTS.md)

Update per AGENTS.md mandatory rules:
1. `CHANGELOG.md` — Add entry for H-10 WASAPI fix: objective, root cause, files changed, test counts
2. `docs/ROADMAP.md` — Update H-10 status from BLOCKED_ON_HARDWARE to reflect WASAPI implementation done (physical BT verification still pending physical device)
3. `README.md` — Add note in audio/hardware section that WASAPI exclusive mode is auto-enabled for BT HFP devices on Windows
4. Commit all changes: `git add CHANGELOG.md docs/ROADMAP.md README.md jarvis/audio/engine.py tests/unit/test_audio_engine.py && git commit -m "feat(h10): WASAPI exclusive capture fallback for BT HFP devices (PaError -9999)" && git push origin main`

## Verification Resources

**Existing tests**: `tests/unit/test_audio_engine.py` — run with:
```
.venv\Scripts\python.exe -m pytest tests/unit/test_audio_engine.py -v
```

**Full suite** (must not regress):
```
.venv\Scripts\python.exe -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

**WASAPI API** (sounddevice built-in, no new deps needed):
```python
import sounddevice as sd
# Check if WasapiSettings exists:
hasattr(sd, 'WasapiSettings')  # True on Windows sounddevice build
# Usage:
extra = sd.WasapiSettings(exclusive=True)
stream = sd.InputStream(device=idx, extra_settings=extra, samplerate=16000, channels=1, dtype='float32', blocksize=512)
```

**AGENTS.md rules** (mandatory, read at `d:\Software GitCode\JARVIS\AGENTS.md` before implementing):
- Fail-Closed: Never return False/MOCK without logging the real error
- Anti-Fabrication: Do not simulate "BT device working" in tests using fake peak values
- TDD: Write failing test first, then implement to pass it
- Atomic writes: Use threading.Lock for any file writes
- Git: Must commit CHANGELOG.md + ROADMAP.md + README.md together with source changes

## Acceptance Criteria

### R1 — WASAPI Implementation
- [ ] `sd.WasapiSettings(exclusive=True)` retry logic present in `_stream_worker()` or a private helper it calls
- [ ] Guarded by `sys.platform == "win32"` check
- [ ] `use_wasapi_exclusive` config field exists and controls the retry
- [ ] Samplerate for WASAPI attempt is 16000 Hz (HFP native rate)

### R2 — Fail-Closed
- [ ] When WASAPI attempt also fails: `self.mode == AudioEngineMode.MOCK` (not silently succeeds)
- [ ] Error log contains device index and exception message (not fabricated success)
- [ ] `audio.device_unavailable` event published with truthful reason

### R3 — Tests
- [ ] 4 new tests added and named exactly as specified
- [ ] All 4 pass: `pytest tests/unit/test_audio_engine.py -v -k "wasapi"` exits 0
- [ ] Full suite still passes: `pytest tests/ -q` exits 0 with >= 1882 tests passing

### R4 — Documentation
- [ ] `CHANGELOG.md` has new entry for H-10 WASAPI with root cause + file list + test counts
- [ ] `docs/ROADMAP.md` H-10 reflects WASAPI implementation done
- [ ] All changes committed and pushed to `origin/main`

## 2026-09-17T09:17:05Z

JARVIS v5.2.0 tại `HEAD 57a40a5` đang ở trạng thái **Beta NO-GO**. Mục tiêu là giải quyết 4 blocker kỹ thuật ưu tiên cao nhất để đưa hệ thống đạt trạng thái Beta GO. Các blocker còn lại (Discord inbound, Core/Labs, runtime evidence) được xử lý trong giai đoạn tiếp theo.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: benchmark

---

## Requirements

### R1. Bỏ simulated success trong planner (fail-closed)

`jarvis/planner/engine.py` tại khoảng line 414 hiện trả kết quả thành công giả khi không tìm thấy handler cho một action. Hành vi này vi phạm fail-closed contract của toàn hệ thống. Planner phải trả một kết quả lỗi rõ ràng — với error code cụ thể như `UNHANDLED_ACTION`, `HANDLER_NOT_FOUND`, hoặc tương đương — thay vì giả vờ thành công. Không được dùng silent fallback hay exception bị nuốt.

### R2. Thống nhất Result model (`ActionResult`)

`jarvis/core/models.py` — `ActionResult` hiện thiếu các fields tiêu chuẩn. Model phải có đủ 4 fields: `status` (enum hoặc string chuẩn hóa), `code` (error/success code cụ thể), `message` (human-readable), `retryable` (bool — caller có nên retry không). Ít nhất 3 backend module đang trả `dict` hoặc `dataclass` khác nhau phải được migrate để dùng chung `ActionResult`. Toàn bộ callsite hiện tại phải tương thích ngược hoặc được cập nhật.

### R3. Thống nhất Health status vocabulary

`jarvis/ui/terminal/theme.py` và các module liên quan hiện dùng nhiều trạng thái health không nhất quán. Vocabulary chuẩn phải gồm đúng 5 trạng thái: `READY`, `LIMITED`, `BLOCKED`, `ERROR`, `UNAVAILABLE`. Trạng thái `UNAVAILABLE` hiện không tồn tại và phải được thêm vào. Các trạng thái ngoài 5 trạng thái này phải được xóa hoặc alias về chuẩn. Tất cả module báo cáo health phải dùng vocabulary này.

### R4. Mở rộng Safety classifier lên high-risk actions mới

`jarvis/planner/safety_interceptor.py` — classifier hiện không liệt kê email outbound, Zalo outbound, Discord outbound, và Home Assistant actions trong nhóm high-risk cần xác nhận của người dùng trước khi thực thi. Các action này phải được thêm vào nhóm high-risk. Khi dispatcher nhận action thuộc nhóm này, phải trigger confirm flow trước khi execute — không được execute ngầm.

---

## Verification Resources

- Test suite hiện tại: `pytest tests/unit/` → 153 passed tại HEAD `57a40a5`
- Các file liên quan trực tiếp:
  - `jarvis/planner/engine.py` ~line 414 (simulated success)
  - `jarvis/core/models.py` ~line 73 (ActionResult)
  - `jarvis/ui/terminal/theme.py` ~line 37 (health status enum)
  - `jarvis/planner/safety_interceptor.py` ~line 31 (high-risk classifier)
- Quy tắc fail-closed bắt buộc: `AGENTS.md` Section 2 (Anti-Fabrication Principle)
- Quy tắc atomic persistence: `AGENTS.md` Section 3

---

## Acceptance Criteria

### R1 — Planner fail-closed
- [ ] Thêm unit test trước khi sửa chứng minh hành vi sai hiện tại (Red phase)
- [ ] Sau khi sửa: test đó pass; planner trả error rõ ràng với error code cụ thể khi không có handler
- [ ] `pytest tests/unit/` không có regression (>= 153 passed)
- [ ] Không còn bất kỳ đường code nào trả `{"ok": True}` hay `{"success": True}` ngầm định khi action chưa thực sự chạy

### R2 — ActionResult contract
- [ ] `ActionResult` có đủ 4 fields với type hints: `status`, `code`, `message`, `retryable`
- [ ] Ít nhất 3 backend module đã migrate — xác minh bằng grep không còn trả raw `dict` từ các callsite đó
- [ ] `pytest tests/unit/` không có regression

### R3 — Health vocabulary
- [ ] `UNAVAILABLE` tồn tại trong enum/constant
- [ ] Grep toàn repo không còn health status nằm ngoài 5 trạng thái chuẩn trong production code
- [ ] `pytest tests/unit/` không có regression

### R4 — Safety high-risk
- [ ] Email outbound, Zalo outbound, Discord outbound, HA actions xuất hiện trong danh sách high-risk của `safety_interceptor.py`
- [ ] Có ít nhất 1 test case cho mỗi nhóm action mới xác nhận confirm flow được trigger
- [ ] `pytest tests/unit/` không có regression

### Tổng thể
- [ ] `pytest tests/unit/` sau tất cả thay đổi: >= 153 passed, 0 regression
- [ ] Commit tất cả thay đổi vào `main` với message rõ ràng theo từng R
- [ ] Cập nhật `CHANGELOG.md` ghi lại từng blocker đã sửa

## 2026-09-17T11:47:29Z

JARVIS v5.2.0 đã giải quyết xong các blocker kỹ thuật R1–R4 (commit `c532805`). Giai đoạn này hoàn thiện 3 hạng mục còn lại để đưa hệ thống vào trạng thái Beta GO hoàn chỉnh: implement Discord inbound gateway, thiết lập cơ chế Core/Labs feature flag, thu thập runtime evidence thật cho các module chưa được kiểm thử live. Cuối cùng xuất báo cáo tổng hợp chi tiết.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: benchmark

---

## Context

- Codebase hiện tại tại HEAD `c532805` trên `origin/main`
- Test baseline: `pytest tests/unit/` → 2,367 passed tại HEAD mới nhất
- `jarvis/comms/discord.py`: `start_polling()` log warning "not supported" và return ngưay; `_poll_loop` không có implementation
- `jarvis/core/config.py`: ConfigManager có sẵn dot-notation (`config.get("labs.xxx")`), nhưng chưa có bất kỳ Labs flag nào
- `jarvis/security/scanner.py`: TSharkCaptureWrapper code hoàn chỉnh nhưng comment ghi "UNTESTED: no TShark available in dev environment"; tests bị `@pytest.mark.skip(reason="requires tshark binary")`
- `tests/`: 21 browser E2E tests đang skip do thiếu opt-in flag
- IMAP live test: chưa được commit; credentials phải lấy từ env vars `JARVIS_RUN_LIVE_IMAP_TESTS`, `JARVIS_TEST_IMAP_HOST`, `JARVIS_TEST_IMAP_USER`, `JARVIS_TEST_IMAP_PASSWORD` (không được hardcode trong code)

---

## Requirements

### R5. Discord Inbound Gateway

`jarvis/comms/discord.py` — implement thực sự cho `start_polling()` và `_poll_loop()`. Gateway phải nhận được tin nhắn từ Discord và chuyển chúng vào handler callback đã đăng ký. Phải dùng Discord REST API (GET `/channels/{channel_id}/messages` với `after` tracking) trong thread riêng biệt — không cần WebSocket nếu REST polling đủ để nhận lệnh. Fail-closed: nếu `bot_token` trống hoặc request lỗi liên tục, phải log và dừng polling hoàn toàn, không retry vô tận. Whitelist `whitelist_user_ids` phải được enforce cho mọi message đến.

### R6. Core/Labs Feature Flag Mechanism

Thêm cơ chế tách biệt tính năng ổn định (Core) và tính năng thử nghiệm (Labs) trong hệ thống. Cần có: (1) config key `labs.enabled` (bool, mặc định `False`) và `labs.features` (list[str], các tính năng Labs được phép); (2) một hàm/decorator hoặc guard check tại dispatch layer để block tính năng Labs khi flag tắt; (3) ít nhất 2 tính năng hiện có được đánh dấu là Labs (ví dụ: browser CDP capture, TShark live capture — hoặc tương đương phù hợp). Khi Labs bị tắt và code cố chạy tính năng Labs, phải trả về `ActionResult` với `status="LABS_DISABLED"`, không phải silent success.

### R7. Runtime Evidence — Thu Thập Bằng Chứng Thật

Thu thập runtime evidence thật cho các module chưa có bằng chứng live. Thực hiện theo thứ tự:

**R7a — TShark:** Kiểm tra TShark có trong PATH hoặc `C:\Program Files\Wireshark\tshark.exe`. Nếu có: bỏ skip marker trên test TShark, chạy `pytest tests/ -m tshark -v` và ghi kết quả. Nếu không có: cài Wireshark/TShark qua `winget install wireshark` hoặc `choco install wireshark`, sau đó chạy test. Ghi output thật (không mock) vào `docs/eval/tshark_live_evidence.md`.

**R7b — Browser E2E (Chromium/Playwright):** Kiểm tra Playwright và Chromium có sẵn. Nếu thiếu: chạy `python -m playwright install chromium`. Bật opt-in flag phù hợp để chạy 21 test đang skip, rồi chạy `pytest tests/ -m browser_e2e -v`. Ghi kết quả thật vào `docs/eval/browser_e2e_evidence.md`.

**R7c — IMAP Live:** Kiểm tra biến `JARVIS_RUN_LIVE_IMAP_TESTS` có bằng `"1"` không. Nếu có và đủ 3 biến credential: chạy integration test live. Nếu không: ghi rõ "credentials not configured in environment — test skipped per opt-in protocol" vào `docs/eval/imap_live_evidence.md`. Không được tự tạo credentials giả.

**R7d — Home Assistant:** Kiểm tra xem có HA instance local tại `http://homeassistant.local:8123` hoặc `http://localhost:8123` bằng HTTP request. Ghi kết quả thật (AVAILABLE/UNAVAILABLE) vào `docs/eval/ha_evidence.md`. Không cần cài mới nếu chưa có.

**R7e — Installer v5.2.0:** Kiểm tra GitHub Release artifact cho v5.2.0: `jarvis-signed-exe` tồn tại và version string bên trong là `5.2.0` (không phải `5.1.0`). Ghi bằng chứng vào `docs/eval/installer_evidence.md`.

### R8. Báo Cáo Tổng Hợp Beta GO

Sau khi hoàn thành R5–R7, tạo file `docs/BETA_GO_REPORT.md` với nội dung:
- Tóm tắt trạng thái tất cả 8 blocker (R1–R8): DONE / PARTIAL / BLOCKED
- Cho mỗi item: root cause ban đầu, giải pháp áp dụng, bằng chứng xác minh (số test pass, runtime output)
- Danh sách known limitations còn lại (nếu có) với lý do chấp nhận được
- Verdict cuối cùng: GO / CONDITIONAL GO / NO-GO với lý do

---

## Verification Resources

- Test suite: `pytest tests/unit/` → 2,367 passed baseline (tại HEAD `c532805`)
- Marker đã đăng ký trong `pyproject.toml`: `integration`, `browser_e2e`, `requires_audio`, `slow`
- `AGENTS.md` Section 2: Anti-Fabrication — runtime evidence phải từ process thật, không mock
- `AGENTS.md` Section 1: commit CHANGELOG.md, README.md, ROADMAP.md cùng với code

---

## Acceptance Criteria

### R5 — Discord inbound gateway
- [ ] `start_polling()` không còn log "not supported" — có thread thật chạy polling loop
- [ ] `_poll_loop()` có implementation gọi Discord REST API thật (hoặc mock integration test chứng minh contract)
- [ ] Whitelist enforcement: message từ user ngoài whitelist bị drop với log rõ ràng
- [ ] Fail-closed: nếu token trống → return ngưay, không start thread
- [ ] Unit test cho: polling với valid token, polling với empty token (fail-closed), whitelist block, message dispatch đến callback
- [ ] `pytest tests/unit/` không có regression

### R6 — Core/Labs flag
- [ ] `config.get("labs.enabled")` trả `False` khi không set
- [ ] Khi `labs.enabled = False`: gọi tính năng Labs → `ActionResult(status="LABS_DISABLED")`, không execute
- [ ] Khi `labs.enabled = True`: tính năng Labs chạy bình thường
- [ ] Ít nhất 2 tính năng được đánh dấu Labs trong code
- [ ] Unit test cho cả 3 scenario trên
- [ ] `pytest tests/unit/` không có regression

### R7 — Runtime evidence
- [ ] `docs/eval/tshark_live_evidence.md` tồn tại với output thật từ tshark hoặc ghi rõ "binary not found"
- [ ] `docs/eval/browser_e2e_evidence.md` tồn tại với kết quả 21 tests (pass/skip/fail) từ lần chạy thật
- [ ] `docs/eval/imap_live_evidence.md` tồn tại với bằng chứng live hoặc ghi rõ "opt-in env var not set"
- [ ] `docs/eval/ha_evidence.md` tồn tại với kết quả HTTP probe thật (AVAILABLE/UNAVAILABLE)
- [ ] `docs/eval/installer_evidence.md` tồn tại xác minh version artifact
- [ ] Không có file nào chứa kết quả fabricated/hardcoded

### R8 — Beta GO Report
- [ ] `docs/BETA_GO_REPORT.md` tồn tại với đủ 8 blocker
- [ ] Mỗi blocker có: root cause, solution, evidence (test count hoặc runtime proof)
- [ ] Verdict rõ ràng: GO / CONDITIONAL GO / NO-GO

### Tổng thể
- [ ] Commit tất cả thay đổi và docs vào `main`
- [ ] `pytest tests/unit/` sau toàn bộ thay đổi: >= 2,367 passed, 0 regression
## 2026-09-17T19:21:38Z

JARVIS v5.2.0 is a Windows desktop AI assistant. Phase 2 (R1–R8) engineering remediation is DONE and committed at `HEAD` (`88eca25` on `origin/main`). The current verdict is **CONDITIONAL GO — Internal Beta Pilot Only**. Product Beta release requires 9 additional acceptance gates to be closed with real runtime evidence. This session closes the **completable** gates and documents the hardware-blocked ones precisely.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: benchmark

**Anti-Fabrication Constraint (MANDATORY):** This project enforces `AGENTS.md §2` strictly. Do NOT report any gate as PASS or DONE unless the evidence is from a real process execution on this host machine. Specifically:
- `PENDING_CREDENTIALS` is **not** a live IMAP test pass
- `TOOL_NOT_FOUND` is **not** a TShark capture pass
- `UNAVAILABLE` is **not** an HA write-path pass
- A CI artifact URL is **not** a clean-machine install pass

Every evidence file must contain actual command output (stdout/stderr verbatim), timestamps, exit codes, and host context. No fabricated data.

---

## Requirements

### R9. Credential Registry
Create `docs/credentials_registry.md` cataloguing every external connector in the JARVIS codebase with: connector name, credential type(s), environment variable(s), current owner (documented as "primary user"), backup/recovery procedure, and rotation policy. Cover: Gmail IMAP/SMTP, Telegram bot, Discord bot, Zalo (pending), ElevenLabs TTS, Home Assistant token, OpenAI/Gemini API keys, GitHub Actions secrets. Each row must have a concrete backup procedure (not "TBD").

### R10. P0/P1 Risk Register
Create `docs/risk_register.md` containing:
- **P0 issues** (blocker — must resolve before any production use): list with accepted-risk rationale or resolution path
- **P1 issues** (high-severity — must resolve before General Availability): list with owner, ETA, accepted-risk statement
- **Known hardware-blocked gates**: TShark binary not in PATH, HA instance not available locally, clean-machine VM not provisioned, voice acceptance H-13 requires human tester — each documented with: what would constitute PASS, what hardware/environment is needed, and who is responsible

### R11. TShark Live Evidence (attempt + document)
Attempt to install Wireshark/TShark via `winget install Wireshark.Wireshark` (or verify if already available). If install succeeds OR binary is already in PATH: run a real live packet capture test using `jarvis/security/scanner.py` with the actual binary and capture the real output as `docs/eval/tshark_live_evidence_v2.md`. If install requires UAC or fails: document the exact error, exit code, and what steps would be needed, and update the existing `docs/eval/tshark_live_evidence.md` to reflect the current status accurately (do NOT overstate).

### R12. Browser E2E Real Chromium Evidence
Run the browser E2E test suite with `JARVIS_RUN_BROWSER_E2E=1` environment variable set. Capture the actual pytest output (pass/fail counts, timing) and save as `docs/eval/browser_e2e_evidence_v2.md`. If tests fail: record the actual failure messages verbatim — do NOT hide failures. Gate passes only if exit code 0.

### R13. Workflow Acceptance Benchmark (design + run)
Design and implement a benchmark for 10 representative JARVIS workflows. Each workflow must be end-to-end testable via the dispatcher/planner layer without real hardware (stub external APIs). Target: ≥95% pass rate per workflow, no workflow below 90%. Save benchmark results as `docs/eval/workflow_benchmark.md`. The 10 workflows should cover: text command dispatch, voice→text→action pipeline (mocked STT), web search, email read (mocked IMAP), file management, app launch, HA query (mocked), system status check, note taking, reminder setting. Run the benchmark and report actual results.

### R14. Documentation Sync + Final Gate Status Report
After R9–R13 are complete:
1. Update `docs/BETA_GO_REPORT.md` §5 (Pending Acceptance Gates table) with actual status of each gate — PASS/PARTIAL/BLOCKED with evidence citations
2. Update `CHANGELOG.md` with a `[5.2.0-phase3]` entry
3. Update `docs/ROADMAP.md` to reflect new gate statuses
4. Run full unit suite (`pytest tests/unit/ -q --tb=short`) and record exact pass/fail count
5. Commit all changes: `git add -A && git commit -m "feat(beta-go): Phase 3 — close R9/R10/R13 gates, attempt R11/R12, final gate status report"`
6. Push to `origin/main`

---

## Acceptance Criteria

### R9 — Credential Registry
- [ ] File `docs/credentials_registry.md` exists and is committed
- [ ] Every connector listed in the codebase (`grep -r "os.getenv\|os.environ" jarvis/comms/ jarvis/core/config.py`) has a corresponding row
- [ ] Each row has: connector, env var(s), owner, backup procedure (specific, not "TBD"), rotation policy
- [ ] No row uses placeholder text for backup procedure

### R10 — Risk Register
- [ ] File `docs/risk_register.md` exists and is committed
- [ ] P0 section: either empty (no P0s) with justification, or each P0 has accepted-risk rationale
- [ ] P1 section: each known hardware-blocked gate documented with exact PASS criteria and hardware requirements
- [ ] H-13 voice acceptance explicitly documented as `PENDING_HUMAN_EXECUTION` with testing protocol reference

### R11 — TShark Evidence
- [ ] `docs/eval/tshark_live_evidence.md` (or `_v2.md`) reflects current host state accurately
- [ ] If binary available: real capture output with actual packet count > 0
- [ ] If binary not available: exact winget/install output, exit code, and remediation steps
- [ ] No fabricated capture output

### R12 — Browser E2E Evidence
- [ ] `docs/eval/browser_e2e_evidence_v2.md` contains real pytest output with timestamp
- [ ] Reports actual pass/skip/fail counts from this host machine
- [ ] If tests fail: failure messages included verbatim, gate marked BLOCKED not PASS

### R13 — Workflow Benchmark
- [ ] `docs/eval/workflow_benchmark.md` exists with 10 workflows measured
- [ ] Each workflow: name, pass/fail/skip count, pass rate %
- [ ] Overall: if ≥9/10 workflows achieve ≥95% pass, mark as PASS; otherwise PARTIAL with specifics
- [ ] Benchmark code committed to `tests/eval/` or `tests/benchmarks/`

### R14 — Documentation Sync
- [ ] `docs/BETA_GO_REPORT.md` §5 table updated with post-Phase-3 gate statuses
- [ ] `CHANGELOG.md` updated with Phase 3 entry
- [ ] `docs/ROADMAP.md` updated
- [ ] `pytest tests/unit/ -q --tb=short` exits with code 0, exact count documented
- [ ] Git commit pushed to `origin/main`

---

## Verification Resources

- Current `HEAD`: `88eca25` on `main` (Phase 2 complete)
- Existing evidence files: `docs/eval/` (5 files from Phase 2)
- Existing `docs/BETA_GO_REPORT.md` §5 has the pending gates table to update
- Full unit suite baseline: **2,424 collected, 0 failed** (as of Phase 2 fix commit)
- AGENTS.md §2 Anti-Fabrication Principle is the governing standard for all evidence
- H-13 voice protocol: `docs/eval/beta_voice_50_live_acceptance_protocol.md`
- Hardware-blocked items (DO NOT fake evidence for these):
  - HA write path: no local HA instance
  - IMAP live: `JARVIS_RUN_LIVE_IMAP_TESTS=1` requires real credentials from user
  - Clean-machine install: requires fresh VM
  - Voice H-13: requires human tester speaking 50 utterances

---
*This is a full multi-part project (R9–R14 are distinct workstreams, some parallelizable). Voice H-13, HA live, and clean-machine are explicitly out of scope — document them precisely, do not attempt to fake them.*
