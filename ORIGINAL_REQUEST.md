# Original User Request

> **Original feature concept attribution:** The pre-existing JARVIS concepts
> for voice-first interaction, wake-word activation, STT/TTS, Local/Cloud AI
> routing, hardware diagnostics and window management, internal-network
> InfoSec auditing, workflow automation, data analysis, IoT/Home Assistant,
> biometric face authentication, gesture control, multi-channel
> communications, self-healing, and destructive-action safety guardrails were
> originally designed by **Huynh Minh Hoa
> ([@hoahuynh19a-crypto](https://github.com/hoahuynh19a-crypto))**.
>
> This credit is limited to those original concepts. Later extensions and the
> implementation, testing, security-hardening, benchmarking, and maintenance
> work in this repository are attributed separately through Git history and
> pull requests.
## 2026-08-24T01:02:20Z

JARVIS là một Windows desktop AI assistant với 67 modules, 537+ tests đang pass. Hệ thống hiện có gesture detection, voice pipeline (STT→LLM→TTS), overlay UI, và smart keyword router. Tuy nhiên JARVIS vẫn còn rất hạn chế — không có memory, không nhìn được màn hình, không tự động hóa được máy tính, không thể làm việc liên tục như một trợ lý thực sự. Mục tiêu: khai phá toàn bộ tiềm năng, biến JARVIS thành Personal AI không thua gì các sản phẩm thương mại.

Working directory: d:/Software GitCode/JARVIS
Integrity mode: development

---

## Hạn chế hiện tại cần vượt qua

1. **Chỉ nghe khi vỗ tay** — không có wake word, phải luôn dùng tay
2. **Không có memory** — mỗi lần hỏi là fresh start, không nhớ ngữ cảnh
3. **Không nhìn được màn hình** — không biết user đang làm gì
4. **Không điều khiển được máy tính** — chỉ mở app, không tương tác được
5. **Không tìm kiếm web** — không có thông tin realtime
6. **Không chủ động** — chỉ phản ứng, không tự nhắc nhở hay cảnh báo
7. **Không nhớ preferences** — không biết user thích gì
8. **Overlay đơn giản** — chỉ show/hide, không phải giao diện thực sự

---

## Requirements

### R1. Wake Word Detection — "Hey JARVIS"

Thay thế/bổ sung cho double clap: JARVIS lắng nghe liên tục wake word "Hey JARVIS" (hoặc "JARVIS" đơn giản) bằng lightweight local model (Vosk hoặc Porcupine hoặc custom energy + keyword detection). Khi nghe thấy wake word:
- Overlay xuất hiện ngay lập tức
- JARVIS nói "Vâng thưa Ngài" và bắt đầu ghi âm command
- Double clap vẫn hoạt động song song như backup
- Wake word có thể tắt/bật qua tray icon (để không làm phiền khi họp)

### R2. Memory & Context System — JARVIS Nhớ Mọi Thứ

Xây dựng persistent memory layer:
- **Short-term**: Conversation context trong session (10 turns gần nhất)
- **Long-term**: SQLite database lưu facts về user: tên, sở thích, thói quen, projects đang làm
- **Episodic**: Lịch sử tất cả interactions với timestamp và outcome
- JARVIS tự học preferences: "Ngài hay hỏi về thời tiết lúc sáng", "Ngài thích nhạc lo-fi khi làm việc"
- Khi LLM nhận command, tự động inject relevant memories vào system prompt
- Lệnh "JARVIS, nhớ rằng..." → lưu vào long-term memory ngay lập tức
- Lệnh "JARVIS, hôm nay tôi đã làm gì?" → tóm tắt episodic log

### R3. Screen Vision — JARVIS Nhìn Thấy Màn Hình

Tích hợp khả năng nhìn và hiểu màn hình:
- Chụp screenshot khi được kích hoạt (hoặc theo yêu cầu)
- Gửi screenshot lên Vision LLM (Gemini Vision hoặc GPT-4o Vision) để phân tích
- JARVIS trả lời các câu hỏi về màn hình: "Lỗi này là gì?", "File này nói về cái gì?", "Tab nào đang mở?"
- OCR text extraction từ screenshot (pytesseract hoặc Gemini Vision)
- Tự động detect khi có error dialog/warning popup và chủ động thông báo
- Lệnh "JARVIS, tóm tắt tài liệu này" → screenshot + vision analysis + TTS summary

### R4. Computer Control — JARVIS Điều Khiển Máy Tính

Cho JARVIS khả năng thực thi thao tác trên máy tính:
- **Window management**: "JARVIS, đóng tab này", "JARVIS, minimize tất cả", "JARVIS, chụp màn hình"
- **Mouse/Keyboard**: pyautogui để click, type, hotkey (chỉ sau voice confirmation với high-risk actions)
- **Volume/Display**: Điều chỉnh âm lượng, độ sáng, chuyển màn hình bằng giọng nói
- **Clipboard**: "JARVIS, copy cái này", "JARVIS, dán vào đây"
- **App switching**: Alt+Tab, focus window theo tên app
- **File operations**: "JARVIS, tìm file X", "JARVIS, mở thư mục Downloads"
- Safety: Mọi destructive action (xóa file, format) yêu cầu xác nhận bằng giọng nói

### R5. Web Intelligence — JARVIS Biết Chuyện Thế Giới

Tích hợp real-time web access:
- **Web search**: DuckDuckGo hoặc SerpAPI để search và tóm tắt kết quả
- **Thời tiết**: OpenWeatherMap API → đọc thời tiết Hà Nội/HCM theo location config
- **Tin tức**: RSS feed reader → tóm tắt tin tức công nghệ/crypto/thế giới buổi sáng
- **Currency/Crypto**: Rate exchange realtime (BTC, ETH, USD/VND)
- **Stock**: Giá cổ phiếu theo mã (VNIndex, AAPL, etc.)
- Lệnh "JARVIS, briefing sáng nay" → tổng hợp thời tiết + tin tức + crypto + lịch hôm nay
- Kết quả đọc to + hiển thị trên overlay dạng bullet points

### R6. Proactive Intelligence — JARVIS Chủ Động

JARVIS không chỉ phản ứng mà còn chủ động:
- **Smart reminders**: "JARVIS, nhắc tôi lúc 3 giờ chiều họp với team" → overlay + TTS alert đúng giờ
- **System health monitor**: Chủ động cảnh báo khi CPU > 90%, RAM > 85%, disk < 10GB, nhiệt độ > 85°C
- **Focus mode**: "JARVIS, tôi cần tập trung 2 tiếng" → block notifications, set timer, nhắc nghỉ 5 phút sau 25 phút
- **Daily briefing auto**: Mỗi sáng 8h (cấu hình được), tự động đọc briefing
- **Battery alert**: Nhắc sạc khi pin < 20%
- **Inactivity greeting**: Nếu không tương tác > 2 tiếng, JARVIS hỏi "Thưa Ngài, Ngài có cần hỗ trợ gì không?"
- Tất cả proactive behaviors có thể tắt/bật riêng lẻ qua config

### R7. Natural Language Shell — JARVIS Thực Thi Lệnh

JARVIS hiểu lệnh tự nhiên và chuyển thành hành động:
- "JARVIS, chạy server" → tự tìm `npm start` hoặc `python manage.py runserver` trong project folder
- "JARVIS, git status project JARVIS" → chạy git command và đọc tóm tắt
- "JARVIS, cài đặt package X" → `pip install X` hoặc `npm install X` tùy context
- "JARVIS, restart Docker" → chạy lệnh tương ứng
- "JARVIS, kiểm tra port 8080" → netstat + trả lời
- Safety gate: Lệnh có `rm`, `format`, `delete`, `drop` yêu cầu confirm bằng giọng nói trước khi chạy
- Kết quả command được tóm tắt và đọc to (không đọc toàn bộ stdout dài)

### R8. Always-On Intelligent Overlay

Nâng cấp overlay từ popup đơn giản thành giao diện thực sự:
- **Sidebar mode**: Option để overlay luôn hiển thị bên phải màn hình (collapsible)
- **Conversation history**: Hiển thị 5 turns gần nhất của cuộc hội thoại
- **Quick actions**: Buttons cho các action hay dùng (briefing, system status, focus mode)
- **Memory preview**: Hiển thị ngắn gọn 3 facts JARVIS nhớ về user
- **Status bar**: CPU/RAM/Battery realtime (cập nhật mỗi 5s)
- **Voice waveform**: Animation thực tế khi đang nghe/nói
- Có thể minimize về icon nhỏ ở góc màn hình

### R9. Regression & Integration Tests

Sau tất cả thay đổi:
- Tất cả 537+ tests cũ phải tiếp tục pass
- Thêm ≥ 20 tests mới cho R1-R8
- `python -m jarvis health-check` phải report tất cả new systems
- `python -m jarvis run` phải khởi động không lỗi với tất cả hệ thống mới

---

## Acceptance Criteria

### Wake Word (R1)
- [ ] "Hey JARVIS" được detect trong < 1s (offline, không cần internet)
- [ ] False positive rate < 1 lần/giờ trong môi trường bình thường
- [ ] Wake word + double clap cùng hoạt động song song
- [ ] Tắt/bật wake word qua tray menu không cần restart

### Memory (R2)
- [ ] "JARVIS, nhớ rằng tôi tên Hưng" → lần sau nhớ và dùng tên
- [ ] Session context: câu hỏi follow-up hiểu được ngữ cảnh câu trước
- [ ] `logs/memory.db` SQLite file tồn tại sau restart
- [ ] "JARVIS, hôm nay tôi đã làm gì?" → tóm tắt đúng interactions trong ngày

### Screen Vision (R3)
- [ ] "JARVIS, màn hình tôi đang hiện gì?" → mô tả chính xác qua Vision LLM
- [ ] "JARVIS, lỗi này nghĩa là gì?" (với error dialog trên màn hình) → giải thích
- [ ] Screenshot được capture và analyze < 3s
- [ ] Hoạt động khi không có Vision LLM key (fallback: "Tôi chưa thể nhìn thấy màn hình")

### Computer Control (R4)
- [ ] "JARVIS, tăng âm lượng" → volume tăng 10%
- [ ] "JARVIS, chụp màn hình" → screenshot lưu vào Desktop
- [ ] "JARVIS, minimize tất cả" → ShowDesktop
- [ ] High-risk actions yêu cầu confirm voice trước khi thực thi

### Web Intelligence (R5)
- [ ] "JARVIS, thời tiết Hà Nội hôm nay?" → trả lời chính xác (cần internet)
- [ ] "JARVIS, briefing sáng nay" → đọc to weather + top 3 news + BTC price
- [ ] Graceful degradation khi offline: "Xin lỗi Ngài, tôi không có kết nối mạng"
- [ ] Tất cả web results được cache 10 phút (không spam API)

### Proactive (R6)
- [ ] "JARVIS, nhắc tôi sau 5 phút" → TTS + overlay alert đúng 5 phút sau
- [ ] CPU > 90% → JARVIS tự cảnh báo bằng giọng nói trong < 30s
- [ ] Focus mode timer: nhắc nghỉ sau 25 phút (Pomodoro)
- [ ] Proactive behaviors tắt/bật được từng cái trong config

### Natural Language Shell (R7)
- [ ] "JARVIS, kiểm tra port đang chạy" → đọc kết quả netstat tóm tắt
- [ ] "JARVIS, git status" → tóm tắt bằng tiếng Việt ("Có 3 files chưa commit")
- [ ] Lệnh nguy hiểm (rm, delete) yêu cầu confirm
- [ ] Command output > 10 dòng được tóm tắt, không đọc hết

### Overlay (R8)
- [ ] Sidebar mode luôn hiển thị, có thể collapse về 40px
- [ ] Conversation history 5 turns hiển thị đúng
- [ ] CPU/RAM cập nhật realtime trên status bar
- [ ] Có thể kéo thả sidebar đến vị trí bất kỳ

### Tests & Regression (R9)
- [ ] Tổng tests ≥ 557 (537 + 20 mới)
- [ ] `pytest tests/ -x -q` pass 100%
- [ ] `python -m jarvis health-check` xanh tất cả subsystems mới

---

## Verification Protocol

1. **Explorers**: Map toàn bộ gaps, design architecture cho R1-R8
2. **Workers** (8 streams song song nếu có thể): Implement từng R
3. **Integration Worker**: Wire tất cả R vào `app.py` và config
4. **Reviewers + Challengers**: Test adversarially từng feature
5. **Victory Auditor**: Independent pytest full suite + health-check

Victory condition: 557+ tests pass, health-check all green, tất cả acceptance criteria verified.

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
- Tómタップ trạng thái tất cả 8 blocker (R1–R8): DONE / PARTIAL / BLOCKED
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

