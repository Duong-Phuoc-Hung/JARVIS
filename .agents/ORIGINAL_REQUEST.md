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

## 2026-09-17T20:37:06Z

JARVIS v5.2.0 is a Windows desktop AI assistant at `CONDITIONAL GO — Internal Beta Pilot Only` (`HEAD` `7d15f97`, `origin/main`). Phase 3 acceptance gates (R9–R14) are complete. This session executes the remaining sprint items from `docs/ROADMAP.md` §BACKLOG (Sprint 2 + 3) to advance toward Product Beta GO.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: benchmark

**Anti-Fabrication Constraint (AGENTS.md §2, mandatory):**
- Every evidence item must come from a real process on this host machine
- `PENDING_CREDENTIALS` / `TOOL_NOT_FOUND` / `UNAVAILABLE` are valid truthful states — never overstate
- Hardware-blocked items: document the exact error, do NOT fabricate success
- Run actual commands and capture real stdout/stderr/exit codes

**Current HEAD**: `7d15f97` — all 2,424 unit tests pass, 0 failures

---

## Requirements

### R15. Npcap Install → Close TShark Gate (R-11)
Attempt to install the Npcap kernel driver (`winget install Npcap.Npcap` or from Npcap's direct winget package). If install succeeds (exit code 0): run a real live capture test through `jarvis/security/scanner.py` and capture the output. Update `docs/eval/tshark_live_evidence_v2.md` with the real result — either `PASS runtime` (packets captured) or `HARDWARE_BLOCKED (UAC_REQUIRED)` if Npcap install requires interactive elevation. No fabricated packets.

### R16. Home Assistant via Docker → Close HA Gate
Check if Docker Desktop is installed and running (`docker info`). If yes: run `docker pull homeassistant/home-assistant:stable` and start a local HA instance (`docker run -d --name ha-test -p 8123:8123 homeassistant/home-assistant:stable`). Wait for readiness (poll `http://localhost:8123` until HTTP 200 or 200s timeout). If ready: run the HA write-path test in `jarvis/integrations/home_assistant.py` via ActionDispatcher, capture real output. Save evidence as `docs/eval/ha_docker_evidence.md`. If Docker not available: document `DOCKER_NOT_FOUND` truthfully.

### R17. IMAP Live Test → Close IMAP Gate
Check if IMAP credentials exist in Windows Credential Manager via `jarvis/core/secrets.py` or via config. Run `pytest tests/ -k "imap" --collect-only` to find existing IMAP tests. Set `JARVIS_RUN_LIVE_IMAP_TESTS=1` and run with the SMTP_USER/SMTP_PASSWORD known from D-09 (Gmail IMAP/SMTP). Capture real output. If credentials resolve: save real pytest output as `docs/eval/imap_live_evidence_v2.md` (`PASS runtime` or failure). If missing: document `PENDING_CREDENTIALS` with exact env var needed.

### R18. v5.2.0 Release Build
Build the `JARVIS_Setup_v5.2.0.exe` installer using the existing Inno Setup script (or PowerShell build script already in the repo). Sign it using the CI Authenticode pipeline (`signtool` or PowerShell `Set-AuthenticodeSignature`). Generate SHA-256 hash. Update `jarvis/__init__.py` version to `5.2.0` if not already. Commit with version bump. Create a git tag `v5.2.0`. Do NOT push the tag or create GitHub Release without verifying the build artifact exists and has a valid SHA-256 hash.

### R19. Router LLM Live Test (P1-04)
Run N=10 live intent routing tests using the real Gemini API (check if `GEMINI_API_KEY` or `GOOGLE_API_KEY` is configured via Windows Credential Manager or environment). Test 10 diverse Vietnamese intent utterances through `LLMIntentRouter`. Record actual LLM response, classified intent, and routing decision for each. Save as `docs/eval/router_llm_live_evidence.md`. If no API key: document `PENDING_CREDENTIALS`.

### R20. TieredSTT WER Domain Measurement (P2-06)
Using the existing STT infrastructure (TieredSTTEngine with Whisper Small/Large-v3), run WER (Word Error Rate) measurement across 3 domains: wake-word phrases (N≥30), command utterances (N≥30), free-form Vietnamese (N≥30). Use the existing audio evaluation framework in `tests/eval/` or `docs/eval/stt_eval_independent_summary.md` as a starting reference. Report WER per domain. Save as `docs/eval/tiered_stt_wer_domain.md`. If no audio hardware: use existing pre-recorded WAV files from prior eval runs (N=420 in `tests/eval/`).

### R21. Documentation Sync + Tag + Commit
After R15–R20:
1. Update `docs/ROADMAP.md` Phase S status table with actual gate results
2. Update `CHANGELOG.md` with `[5.2.0-sprint2]` entry
3. Update `docs/BETA_GO_REPORT.md` §5 pending gates table with new statuses
4. Run full unit suite: `pytest tests/unit/ -q --tb=short` — record exact count
5. Commit: `git add -A && git commit -m "feat(release): Sprint 2+3 — R15 TShark, R16 HA Docker, R17 IMAP, R18 v5.2.0 build, R19 Router LLM live, R20 TieredSTT WER"`
6. Push to `origin/main`
7. If R18 build succeeded: `git tag v5.2.0 && git push origin v5.2.0`

---

## Acceptance Criteria

### R15 — TShark/Npcap
- [ ] `winget install Npcap.Npcap` attempted, exit code and output documented
- [ ] `docs/eval/tshark_live_evidence_v2.md` updated with real result
- [ ] If Npcap installed: real packet capture with `packet_count > 0` documented
- [ ] If UAC-blocked: exact error and remediation steps documented
- [ ] Zero fabricated packet counts

### R16 — HA Docker
- [ ] `docker info` output documented (available/not available)
- [ ] If Docker available: HA container started, HTTP probe result documented
- [ ] If HA ready: real write-path test result captured via ActionDispatcher
- [ ] `docs/eval/ha_docker_evidence.md` created with real output
- [ ] If Docker unavailable: `DOCKER_NOT_FOUND` documented with remediation

### R17 — IMAP Live
- [ ] Credential resolution attempt documented (Credential Manager + env)
- [ ] `JARVIS_RUN_LIVE_IMAP_TESTS=1 pytest` attempted with real result
- [ ] `docs/eval/imap_live_evidence_v2.md` created
- [ ] If PASS: real email fetched, `em.sender` and `em.subject` logged (no body content)
- [ ] If PENDING_CREDENTIALS: exact missing env vars documented

### R18 — Release Build
- [ ] `jarvis/__version__` is `5.2.0`
- [ ] Installer build attempted (Inno Setup or equivalent)
- [ ] SHA-256 hash of installer documented
- [ ] Git tag `v5.2.0` created (if build succeeded)
- [ ] If build fails: exact error documented, no fake artifact

### R19 — Router LLM Live
- [ ] API key resolution attempt documented
- [ ] If key available: 10 real LLM routing results with intent + confidence
- [ ] `docs/eval/router_llm_live_evidence.md` created
- [ ] If no key: `PENDING_CREDENTIALS` documented

### R20 — TieredSTT WER
- [ ] WER measured for ≥3 domains using real audio files or recorded corpus
- [ ] WER per domain reported (not estimated)
- [ ] `docs/eval/tiered_stt_wer_domain.md` created with real numbers
- [ ] Methodology documented (which model, which audio files, N count)

### R21 — Docs + Release
- [ ] `CHANGELOG.md` updated with Sprint 2+3 entry
- [ ] `docs/ROADMAP.md` updated with real gate statuses
- [ ] Full unit suite exit code 0, exact count documented
- [ ] Git commit pushed to `origin/main`
- [ ] If R18 build succeeded: `v5.2.0` tag pushed

---

## Verification Resources

- Current `HEAD`: `7d15f97` on `main`
- ROADMAP Sprint plan: `docs/ROADMAP.md` §BACKLOG P0–P3 + Sprint plan
- Existing STT eval corpus: `tests/eval/` (WAV files from N=420 evaluation)
- Existing HA client: `jarvis/integrations/home_assistant.py`
- Existing IMAP client: `jarvis/comms/email_imap.py` (`fetch_unread()` → `list[EmailMessage]`)
- Existing Router: check `jarvis/` for LLMIntentRouter implementation
- AGENTS.md §2 Anti-Fabrication is the governing standard for all evidence
- Hardware-blocked items (document honestly, do NOT fake): HA without Docker, IMAP without credentials, Npcap requiring UAC

---
*Full multi-part project with 7 requirements. Some may be hardware-blocked — document truthfully. Priority order: R21 docs sync must run last; R15–R20 can run in parallel.*

## 2026-09-18T09:40:57Z

<USER_REQUEST>
JARVIS v5.2.0 is a Windows desktop AI assistant. The previous Phase 4 teamwork session was killed by a server restart before completing R21 (commit + docs sync). All Phase 4 evidence files exist on disk but are uncommitted. This session must:
1. Complete R21 (commit all Phase 4 evidence + docs sync)
2. Attempt to start Docker Desktop daemon and re-run HA test
3. Check Windows Credential Manager for Gemini API key
4. Create GitHub Release v5.2.0 with installer
5. Update all docs with accurate final status

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: benchmark

**Anti-Fabrication Constraint (AGENTS.md §2 + §5, mandatory):**
- Every gate result must be from a real process on this host machine
- PENDING_CREDENTIALS / HARDWARE_BLOCKED / DOCKER_NOT_RUNNING are valid truthful states
- Never overstate or fabricate success
- Run actual commands, capture real stdout/stderr/exit codes

**Current HEAD**: `7d15f97` — Phase 4 work is uncommitted (git status shows ~10 untracked/modified files)

---

## Phase 4 Context (what was done before restart)

The following files exist on disk but are NOT yet committed:
- `docs/eval/ha_docker_evidence.md` — Docker CLI 29.5.3 present, daemon was NOT running: `HARDWARE_BLOCKED (DOCKER_NOT_RUNNING)`
- `docs/eval/imap_live_evidence_v2.md` — **PASS runtime**: live Gmail IMAP auth succeeded, 2 real emails retrieved
- `docs/eval/router_llm_live_evidence.md` — `PENDING_CREDENTIALS`: Gemini API key not found in env
- `docs/eval/tiered_stt_wer_domain.md` — Real WER: Command 8.37%, Free-form Vietnamese 3.72%, Combined 5.84%
- `docs/eval/tshark_live_evidence_v2.md` — modified: `HARDWARE_BLOCKED (UAC_REQUIRED)` for Npcap
- `scripts/build_installer.py` — modified
- `scripts/sign_installer_v520.py` — new signing script
- `tests/eval/run_eval_worker3.py`, `tests/eval/test_wer_domain_challenge.py` — WER test helpers
- `tests/test_live_infra_evidence.py` — live infra test
- `docs/superpowers/` — new directory (unknown content from Phase 4)
- `dist/installer/JARVIS_Setup_v5.2.0.exe` — real Inno Setup build (check if exists with `Test-Path`)

## Requirements

### R22. Complete R21 — Commit Phase 4 Evidence
Commit all Phase 4 uncommitted work. Before committing:
1. Run `pytest tests/unit/ -q --tb=short` — record exact pass/fail count. If any failures, fix them first.
2. Run `git add -A` then commit: `git add -A && git commit -m "feat(sprint2+3): Phase 4 evidence — R15 TShark UAC, R16 HA Docker blocked, R17 IMAP PASS runtime, R18 v5.2.0 build, R19 LLM PENDING, R20 TieredSTT WER 8.37%/3.72%"`
3. Push to `origin/main`

### R23. Docker Desktop Daemon — Retry HA Gate
Attempt to start the Docker Desktop service: `Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe' -WindowStyle Hidden`. Wait 60 seconds, then retry `docker info`. If daemon starts successfully: pull `homeassistant/home-assistant:stable`, start container on port 8123, probe `http://localhost:8123`, run the HA write-path test via ActionDispatcher. Update `docs/eval/ha_docker_evidence.md` with real result. If daemon still fails to start: document the exact error and keep `HARDWARE_BLOCKED`.

### R24. Gemini API Key via Windows Credential Manager
Check Windows Credential Manager for stored Gemini/Google API keys: run `cmdkey /list | Select-String -Pattern 'gemini|google|GOOGLE|GEMINI|API'`. Also check `jarvis/core/secrets.py` for how the app loads API keys. If found: run N=10 Router LLM live test with real Gemini API. Update `docs/eval/router_llm_live_evidence.md` with real routing results. If not found: document `PENDING_CREDENTIALS` with exact key name needed.

### R25. GitHub Release v5.2.0
If `dist/installer/JARVIS_Setup_v5.2.0.exe` exists (verify with `Test-Path`):
1. Compute SHA-256: `(Get-FileHash 'dist\installer\JARVIS_Setup_v5.2.0.exe' -Algorithm SHA256).Hash`
2. Create git tag: `git tag v5.2.0` (if not already exists: check with `git tag -l v5.2.0`)
3. Push tag: `git push origin v5.2.0`
4. Create GitHub Release using `gh release create v5.2.0 dist/installer/JARVIS_Setup_v5.2.0.exe --title "JARVIS v5.2.0 — Internal Beta" --notes "$(Get-Content docs/BETA_GO_REPORT.md | Select-Object -First 30 | Out-String)"`
5. Document release URL and SHA-256 in `docs/eval/release_v520_evidence.md`
If installer not found: document `BUILD_ARTIFACT_MISSING`.

### R26. Final Documentation Sync
After R22–R25:
1. Update `docs/BETA_GO_REPORT.md` §5 Pending Acceptance Gates table with Phase 4 real results:
   - R-11 TShark: `HARDWARE_BLOCKED (UAC_REQUIRED)` — Npcap driver requires interactive UAC elevation
   - R-16 HA Docker: result from R23 (PASS runtime if Docker started, otherwise HARDWARE_BLOCKED)
   - R-17 IMAP: `PASS runtime` — Gmail IMAP live, 2 emails retrieved
   - R-18 v5.2.0 Build: `PASS` — Inno Setup + Authenticode + SHA-256 documented
   - R-19 Router LLM: result from R24
   - R-20 TieredSTT WER: `PASS runtime` — Command 8.37%, Free-form VN 3.72%
2. Add `[5.2.0-phase4]` entry to `CHANGELOG.md`
3. Update `docs/ROADMAP.md` Phase S status table
4. Run full unit suite again after all changes: `pytest tests/unit/ -q --tb=short` — record exact count
5. Commit final docs: `git add -A && git commit -m "docs(phase4): final sync — Phase 4 gate status, ROADMAP update, CHANGELOG 5.2.0-phase4"`
6. Push to `origin/main`

## Acceptance Criteria

### R22 — Phase 4 Commit
- [ ] `pytest tests/unit/ -q` exits 0 before commit
- [ ] All Phase 4 evidence files committed (`git log --name-only HEAD` lists them)
- [ ] Commit pushed to `origin/main`
- [ ] Exact test count documented

### R23 — HA Docker Retry
- [ ] `Start-Process Docker Desktop` attempted, result documented
- [ ] `docker info` output after 60s documented (running/not running)
- [ ] `docs/eval/ha_docker_evidence.md` updated with real retry result
- [ ] If HA ready: real ActionDispatcher write-path test result
- [ ] Zero fabricated HA responses

### R24 — Router LLM Credential Manager
- [ ] `cmdkey /list` output documented
- [ ] Credential Manager search result documented
- [ ] `docs/eval/router_llm_live_evidence.md` updated with real result
- [ ] If PASS: 10 real routing results with intent labels
- [ ] If PENDING: exact credential name documented

### R25 — GitHub Release
- [ ] `dist/installer/JARVIS_Setup_v5.2.0.exe` existence verified with real `Test-Path`
- [ ] SHA-256 computed with real `Get-FileHash`
- [ ] Git tag `v5.2.0` created and pushed (or already exists — document)
- [ ] `gh release create` attempted, URL documented
- [ ] `docs/eval/release_v520_evidence.md` created

### R26 — Final Docs
- [ ] `docs/BETA_GO_REPORT.md` §5 updated with Phase 4 gate statuses
- [ ] `CHANGELOG.md` updated with `[5.2.0-phase4]`
- [ ] `docs/ROADMAP.md` updated
- [ ] Full unit suite passes with exact count documented
- [ ] Final commit pushed to `origin/main`
</USER_REQUEST>

## 2026-09-19T07:05:40Z

<USER_REQUEST>
Cập nhật và tạo mới 4 tài liệu trong repo JARVIS v5.2.0 để phản ánh đúng trạng thái hiện tại sau Phase G, Phase P3, Phase 4, và vòng peer-review. Tất cả tài liệu phải tuân thủ nghiêm ngặt Anti-Fabrication Principle trong `AGENTS.md §2` và Three-Tier Verdict Discipline trong `AGENTS.md §5`.

Working directory: d:\Software GitCode\JARVIS
Integrity mode: development

## Tổng quan trạng thái hiện tại (phải đọc trước khi làm)

**HEAD**: `3a7014f` | **Tag**: `v5.2.0` | **Branch**: `main`
**Phán quyết**: `CONDITIONAL GO — Internal Beta Pilot Only` (NOT Product Release GO)

### Số liệu thực tế đã xác nhận (không được thay đổi)
- Unit suite: **2,421 passed, 3 skipped, 268 subtests, 0 failed** (re-run 2026-09-19)
- 3 skipped = `test_data_analysis_service.py` lines 196/209/253 — `matplotlib` không cài, `pytest.importorskip`
- Browser E2E: **21/21 PASS, 45.38s**, real Chromium
- Workflow benchmark (R13): **200/200** — dispatcher+mock ONLY (`zero hardware dependencies`); **gate "10-workflow real OS execution" vẫn OPEN**
- TieredSTT WER R20: Command aggregate **8.50%** (mean utterance 8.37%), Free-form VN **3.72%**, Combined aggregate **5.88%** (N=60, D2+D3; D1 chưa đo)
- IMAP live: PASS runtime (imap.gmail.com:993, 2 emails)
- TShark: HARDWARE_BLOCKED (UAC_REQUIRED, npcap.sys thiếu)
- HA Docker: HARDWARE_BLOCKED (DOCKER_NOT_RUNNING)
- Router LLM: PENDING_CREDENTIALS (key sai định dạng)
- v5.2.0 installer: 74,950,832 bytes, SHA-256 `6b52e20f3c4cf08be76a55c4e7dc87d55c83112725425a579b46c9aff3510d3b`, Authenticode self-signed (commercial EV chưa có → SmartScreen warning)
- D-06 Telegram: 1 live send/receive cycle (2026-09-12), không có bằng chứng mới
- D-08 Discord: REST API auth confirmed (2026-09-12), không có round-trip command test mới
- H-13: 48/50 PASS (96.0%) từ 2026-09-16 — cần re-verify sau Phase G code changes

---

## Requirements

### R1. Cập nhật `docs/READINESS_DASHBOARD.md`

File hiện tại (2026-09-17) không có Phase G (R1-R8), Phase P3 (R9-R14), Phase 4 (R15-R26), và phản ánh sai trạng thái D-06/D-08/D-14/H-06/H-10/H-11/H-13. Cần:

1. **Cập nhật Section 1 (Executive Summary)**:
   - Thêm Phase G completion (R1-R8, 2026-09-17)
   - Thêm Phase P3 (R9-R14, 2026-09-18)
   - Thêm Phase 4 (R15-R26, 2026-09-18)
   - Thêm Phase S — Peer Review corrections (2026-09-19)
   - Cập nhật unit test count: 2,421 passed, 3 skipped, 268 subtests (2026-09-19)
   - Ghi rõ phán quyết 3 tầng: Engineering DONE / Internal Beta Pilot CONDITIONAL GO / Product Release NO-GO
   - Thêm v5.2.0 installer: 74,950,832 bytes, SHA-256 `6b52e20f3c4cf08be76a55c4e7dc87d55c83112725425a579b46c9aff3510d3b`

2. **Cập nhật bảng Phase D (Section 2.1)**:
   - D-06: Đổi từ `PENDING_CREDENTIALS` → `DONE (scope hạn chế)` với note: "1 live send/receive cycle 2026-09-12, không có bằng chứng mới"
   - D-07: Giữ `PENDING_ZALO_OA_VERIFICATION`
   - D-08: Đổi từ `PENDING_CREDENTIALS` → `DONE (scope hạn chế)` với note: "REST API auth 2026-09-12, không có round-trip command test mới"
   - D-09: Đổi từ `PENDING_CREDENTIALS` → `DONE` với note: "SMTP login PASS + IMAP PASS runtime 2026-09-18"
   - D-14: Thêm note rõ "self-signed CI ($0, ephemeral); commercial OV/EV cert chưa có → installer hiển thị SmartScreen warning trên máy sạch"
   - D-12: Cập nhật lên v5.2.0 (74,950,832 bytes, SHA-256 `6b52e20f...`)

3. **Cập nhật bảng Phase H (Section 2.2)**:
   - H-06: Đổi từ `PENDING_IDLE_SOAK` → `DONE` với evidence `docs/eval/wake_word_idle_results.json` (3600.1s, 0.00 FP/hr)
   - H-10: Đổi từ `BLOCKED_ON_HARDWARE` → `DONE (software 100%; 4/10 hardware configs có tín hiệu thật)`
   - H-11: Đổi từ `PENDING_FIRST_RUN` → `DONE` với note "25 devices listed, step 1/5 confirmed"
   - H-13: Đổi từ `PENDING_HUMAN_EXECUTION` → `DONE (48/50, 96.0%, 2026-09-16) — cần re-verify sau Phase G`

4. **Thêm Section mới sau Phase H**:
   - Section 2.3: Phase G — Engineering Hardening (R1-R8): bảng 8 items, tất cả DONE
   - Section 2.4: Phase P3 — Product Beta Acceptance Gates (R9-R14): R9/R10 PASS engineering, R11 HARDWARE_BLOCKED, R12 PASS runtime, R13 PASS runtime (dispatcher+mock — gate real OS OPEN), R14 DONE
   - Section 2.5: Phase 4 — Runtime Evidence Portfolio (R15-R26): R15 HARDWARE_BLOCKED, R16 HARDWARE_BLOCKED, R17 PASS runtime, R18/R25 PASS runtime, R19 PENDING_CREDENTIALS, R20 PASS runtime (D2+D3), R26 DONE
   - Section 2.6: Phase S — Peer Review (2026-09-19): 5 corrections applied

5. **Thêm Section 3: Open Gates**:
   - Gate "10-workflow real OS execution": OPEN — 200/200 dispatcher+mock không đóng gate này
   - Gate "TieredSTT Domain 1 Wake-Word WER": PENDING_INTERACTIVE_TERMINAL
   - Gate "H-13 re-verify sau Phase G": PENDING_HUMAN_EXECUTION
   - Gate "D-07 Zalo OA": PENDING_ZALO_OA_VERIFICATION
   - Gate "Router LLM live": PENDING_CREDENTIALS
   - Gate "HA Docker": HARDWARE_BLOCKED
   - Gate "TShark Npcap": HARDWARE_BLOCKED

---

### R2. Cập nhật `docs/PROJECT_STATE.md`

File hiện tại là snapshot T-01 (2026-09-16). Cần thêm checkpoint mới ở **đầu file** (sau dòng header, TRƯỚC phần content cũ, không xóa lịch sử):

Thêm block `## 0A. Current checkpoint — v5.2.0 Phase 4 + Peer Review (2026-09-19) — READ THIS FIRST` với:
- HEAD: `3a7014f`, Tag: `v5.2.0`, Branch: `main`
- Phán quyết 3 tầng: Engineering DONE / Internal Beta Pilot CONDITIONAL GO / Product Release NO-GO
- Summary phases: G (R1-R8 DONE) / P3 (R9-R14, R11 hardware-blocked) / Phase 4 (R17 IMAP PASS runtime, R18 installer, R19 PENDING_CREDENTIALS, R20 WER D2+D3, R25 release)
- Số liệu: unit 2,421/3skip/268subtests, E2E 21/21, WER 8.50%/3.72%/5.88%
- Pending: R11 Npcap UAC, R16 Docker daemon, R19 Gemini key, gate 10-workflow real OS
- Note: checkpoint này không xóa lịch sử T-01 bên dưới

---

### R3. Thêm addendum vào `docs/TECHNICAL_AUDIT_REPORT.md`

File hiện tại là tổng hợp 13 vòng audit lịch sử + POST-AUDIT OVERRIDE T-01. Cần thêm section mới ở **đầu file** sau POST-AUDIT OVERRIDE T-01 hiện có:

Thêm `## POST-AUDIT OVERRIDE — Phase 4 + Peer Review (2026-09-19)` với:
- 5 corrections từ peer review:
  * R13: 200/200 là dispatcher+mock (STT mocked, HA mocked, IMAP mocked — `zero hardware dependencies`). Gate "10-workflow real OS execution" OPEN. Verdict: `PASS runtime (dispatcher+mock)`, không phải `PASS runtime` cho OS execution.
  * D-06/D-08: Nhãn DONE copy từ Phase D 2026-09-12, không có bằng chứng mới. Verdict: `DONE (scope hạn chế)`.
  * WER: Aggregate 8.50%/5.88%, không phải mean utterance 8.37%/5.84%. Domain 1 chưa đo. N=60 nhỏ (khuyến nghị ≥200/domain). Ngưỡng tier-switching hardcoded (không data-driven).
  * D-14: Self-signed CI cert (DONE, $0). Commercial OV/EV cert chưa có → SmartScreen warning. P3-09 dài hạn.
  * Unit suite re-run 2026-09-19: 2,421/3skip/268subtests (3 skips = matplotlib không cài).
- Phán quyết 3 tầng hiện tại

---

### R4. Tạo `docs/eval/workflow_10_real_os_execution_protocol.md`

Tạo file protocol mới cho gate "10-workflow real OS execution". Tham khảo cấu trúc của `docs/eval/beta_voice_50_live_acceptance_protocol.md` (H-13 protocol). File cần có:

1. **Tiêu đề và mục đích**: Protocol đo 10 workflow với real voice → real STT → real OS action. Gate GO/NO-GO cho Internal Beta Pilot → Product Beta.

2. **Gate definition**:
   - Pass threshold: ≥95% per workflow
   - Fail condition: BẤT KỲ workflow nào <90% → gate FAIL dù trung bình ≥95%
   - N tối thiểu: 20 trials/workflow (200 total)

3. **Điều kiện hợp lệ** (anti-bias, bắt buộc):
   - STT: FasterWhisper `large-v3` CUDA — KHÔNG mock
   - Action: OS call thật có bằng chứng (log, return code, screenshot)
   - Log riêng từng workflow — không gộp chung
   - Ghi điều kiện âm học mỗi trial: `QUIET` (phòng yên tĩnh) hoặc `AMBIENT` (có tiếng ồn thực tế)
   - Ít nhất 20% trials trong điều kiện `AMBIENT`
   - Người nói: nếu có thể, không dùng chính người đã derive router rules
   - Chạy `AUDIT_FRAMEWORK.md` checklist trước khi submit kết quả

4. **10 workflow** với: ID | Trigger phrase mẫu | Action target | Evidence format | Pass condition:
   1. `WF-01` Mở ứng dụng: "mở Chrome" → `subprocess`/OS launch → process PID log
   2. `WF-02` Settings: "mở cài đặt" → Settings app launch → window title confirmed
   3. `WF-03` Tìm kiếm web: "tìm kiếm [topic]" → browser URL log
   4. `WF-04` Media control: "bật nhạc" → Spotify/media API → playback state log
   5. `WF-05` Âm lượng: "tăng âm lượng" → pycaw volume set → volume level before/after
   6. `WF-06` Thời tiết: "thời tiết hôm nay" → API call → response JSON snippet
   7. `WF-07` Hẹn giờ: "đặt hẹn giờ 5 phút" → timer registered → timer ID log
   8. `WF-08` Nhắc nhở: "nhắc tôi lúc 3 giờ" → reminder registered → confirmation log
   9. `WF-09` Ghi chú: "ghi chú [text]" → note saved → file/DB entry log
   10. `WF-10` Chụp màn hình: "chụp màn hình" → screenshot saved → file path + size log

5. **Template bảng kết quả** per-workflow:
   ```
   | Trial | Trigger | STT output | Action | Evidence | PASS/FAIL | Acoustic |
   ```

6. **Summary table** sau khi đo:
   ```
   | Workflow | N | Pass | Fail | Pass% | Gate |
   ```

7. **Checklist trước khi submit** (reference AUDIT_FRAMEWORK.md):
   - N ghi rõ
   - Log riêng từng workflow
   - Acoustic condition ghi rõ mỗi trial
   - Phát hiện nghiêm trọng ở đầu báo cáo
   - Không module nào bị dán ✅ chưa audit

---

## Acceptance Criteria

### Tính trung thực và nhất quán
- [ ] Không có số liệu nào khác với danh sách "Số liệu thực tế đã xác nhận"
- [ ] Không bất kỳ file nào tuyên bố "Product Release GO" hoặc "BETA GO" không có điều kiện
- [ ] R13 trong READINESS_DASHBOARD.md ghi rõ "dispatcher+mock" và "gate real OS OPEN"
- [ ] D-14 trong READINESS_DASHBOARD.md phân biệt self-signed vs commercial EV
- [ ] D-06/D-08 ghi rõ "scope hạn chế" và ngày test cuối 2026-09-12

### Đầy đủ nội dung
- [ ] READINESS_DASHBOARD.md có Section cho Phase G, P3, Phase 4, Phase S
- [ ] READINESS_DASHBOARD.md có Section "Open Gates" với ít nhất 7 gates
- [ ] PROJECT_STATE.md có block checkpoint v5.2.0 ở đầu file
- [ ] TECHNICAL_AUDIT_REPORT.md có addendum Phase 4 + Peer Review
- [ ] `docs/eval/workflow_10_real_os_execution_protocol.md` tồn tại với 10 workflow + evidence format

### Git và đồng bộ
- [ ] Tất cả 4 file được `git add`, commit với message: `docs(v520): update readiness dashboard, project state, audit report, add 10-workflow real OS protocol`
- [ ] `git push origin main` thành công
- [ ] `git status` clean sau push

### Kiểm tra không hồi quy
- [ ] `pytest tests/unit/ -q --tb=no` vẫn pass (không test nào break)
- [ ] `git diff --check` pass

---

## Tài liệu tham khảo (phải đọc để hiểu ngữ cảnh)

- `AGENTS.md` — Anti-Fabrication Principle (§2), Three-Tier Verdict Discipline (§5)
- `docs/BETA_GO_REPORT.md` — Phán quyết và gate matrix hiện tại (updated 2026-09-19)
- `CHANGELOG.md` — Entry [5.2.0-phase4] với số liệu thực tế (fixed 2026-09-19)
- `docs/eval/tiered_stt_wer_domain.md` — WER evidence (8.50%/3.72%/5.88%)
- `docs/eval/beta_voice_50_live_acceptance_protocol.md` — Template cho R4
- `tests/benchmarks/test_workflow_acceptance_benchmark.py` — Source xác nhận R13 là dispatcher+mock
- `docs/READINESS_DASHBOARD.md` — File cần update (đọc toàn bộ trước)
- `docs/PROJECT_STATE.md` — File cần update (đọc toàn bộ trước)
- `docs/TECHNICAL_AUDIT_REPORT.md` — File cần update (đọc toàn bộ trước)
</USER_REQUEST>



