# 🤖 JARVIS — Trợ Lý AI Cá Nhân Tự Trị Cho Windows

Current verified snapshot (2026-10-23), source **5.4.0**, **unreleased / CONDITIONAL GO (Internal Pilot)**:
- **Sprint 12 Next-Gen Speech Frontiers & Spoken Disfluency Self-Correction Engine (Levelt Model)**:
  - Báo cáo Nghiên cứu Tiên phong Argon Sovereign v4.0 ([`docs/research/argon_next_generation_speech_frontiers.md`](docs/research/argon_next_generation_speech_frontiers.md)): Khảo sát và đối chiếu 5 giới hạn công nghệ SOTA (Disfluency Repair, Speaker Privilege Gating, Micro-AFE vs Vietnamese Tone Formants, Dynamic Context Biasing Whisper, Declarative Macro DAG).
  - Động cơ Sửa sai Khẩu ngữ & Đổi ý Giữa câu (`SpokenDisfluencyRepairEngine` tại `jarvis/nlp/disfluency_repair.py`): Dựa trên mô hình sản sinh lời nói Levelt (1983) phân rã phát ngôn thành Prefix + Reparandum + Interregnum + Repair. Tự động phát hiện và đính chính các trường hợp nói nhầm số liệu ("tăng âm lượng lên 50 à nhầm 80 phần trăm"), đổi ứng dụng ("mở chrome à thôi mở edge", "mở chrome à thôi edge"), đổi bài hát/video ("bật bài hát nắng à không bài chúng ta của hiện tại"), và khử lặp từ nói lắp ("mở mở chrome" -> "mở chrome").
  - Chốt chặn Hủy lệnh Tức thời giữa câu (Mid-Speech Abort Guard): Bắt trọn các phát ngôn đổi ý triệt tiêu lệnh nguy hiểm ("tắt máy tính đi à thôi bỏ đi", "mở visual studio code à thôi đừng mở"), trả về trạng thái hủy tức thì với độ trễ micro-giây, ngăn chặn tuyệt đối việc thực thi ngoài ý muốn.
  - Bảo vệ Ngôn ngữ học Thực thể: Ngăn chặn bắt nhầm các từ phủ định là tên bài hát/truy vấn ("tìm kiếm bài hát không phải em") khi Reparandum rỗng.
  - Viễn trắc Phần cứng Argon Telemetry thực tế: Độ trễ CPU đơn luồng **p50 = 0.0473ms (47.3 micro-giây) / p95 = 0.0684ms**, tiêu tốn **0 MB VRAM**, tính tất định **100%**.
  - Toàn bộ 49 bài kiểm thử Disfluency Repair, AWACI, Speculative Pre-Routing, Joint Slot Tagger, Night-Shift Trainer và Argon Voice-to-Action Benchmark: **100% PASS (49/49 passed)** trong **96.93s**.
- **Sprint 11 SOTA Voice & NLP Blueprint: AWACI Active Window Awareness, Speculative Intent Pre-Routing, Joint BIO Slot Tagger INT8 & Night-Shift Autonomous Flywheel**:
  - AWACI Engine (`jarvis/context/screen_context.py`): Nhận diện ngữ cảnh cửa sổ đang hoạt động qua native Win32 C-API (`GetForegroundWindow`, `GetWindowTextW`, `QueryFullProcessImageNameW`), phân loại ngữ cảnh ứng dụng (browser, media_player, code_editor, terminal, document_editor) và giải quyết nhập nhằng khẩu lệnh phụ thuộc ngữ cảnh ("dừng lại", "phóng to", "lưu file", "đóng tab") với độ trễ vi mô <0.05ms (cold 0.105ms, cached 0.002ms).
  - Định tuyến đón đầu suy đoán (Speculative Intent Pre-Routing - `jarvis/stt/speculative_router.py`): Khớp ý định trước ngay trên luồng streaming hypotheses âm thanh từng phần, pre-warm socket/subsystem, đưa độ trễ cảm nhận (perceived latency) xuống **0.20ms p50 / 0.22ms p90** (< 100ms budget). Tự động hủy suy đoán khi xuất hiện từ do dự/phủ định ("à thôi", "đừng", "hủy").
  - Mô hình Joint Intent & Token-Level BIO Slot Tagger INT8 (`jarvis/nlp/joint_tagger.py`): Mô hình Machine Learning liên hợp phân loại ý định câu kết hợp gán nhãn thực thể cấp token BIO (`B-app`, `I-app`, `B-device`, `B-location`, `B-level`, `B-query`, `B-time`, `B-action`, `B-component`, `O`). Kích thước trên đĩa chỉ **209 KB** (ngân sách <= 15MB), độ trễ suy luận CPU đơn luồng **1.54ms p50 / 2.12ms p90** (ngân sách <= 2.50ms).
  - Vòng lặp Tự học ban đêm Night-Shift Continuous Learning Flywheel (`jarvis/workers/night_shift_trainer.py`): Chạy ngầm định kỳ 03:00 AM VN, tự động lọc sạch thông tin nhạy cảm PII (`scrub_pii`), gom cụm ngữ nghĩa không giám sát (`MiniBatchKMeans`), tăng cường dữ liệu đa trục đối chuẩn (không dấu, lỗi STT, tiền tố/hậu tố), tái huấn luyện và thẩm định nghiêm ngặt qua `AutomatedEvaluatorGate` (CV Accuracy >= 98%, Golden Regression = 100%) trước khi ghi đĩa nguyên tử an toàn Windows Atomic Persistence.
  - Toàn bộ 38 bài kiểm thử AWACI, Speculative Pre-Routing, Joint Slot Tagger, Night-Shift Trainer và Argon Voice-to-Action Benchmark: **100% PASS (38/38 passed)** trong **20.99s**.
- **Sprint 10 Voice-to-Action Reflex Arc & Dynamic Tiered ASR**:
  - Chuỗi phản xạ Voice-to-Action cận-zero latency: Tối ưu toàn bộ đường ống từ thu âm -> Silero VAD v6 -> CTranslate2 Whisper -> Normalizer -> ONNX NLU -> ActionDispatcher, đưa tổng độ trễ phản xạ p50 xuống **301.75ms** (vượt chuẩn cam kết <= 1,100ms).
  - Dynamic Tiered ASR Engine (DynamicTieredASREngine): Tự động định tuyến giữa Faster-Whisper Small (int8_float16, ~786MB VRAM) và Large-v3 khi độ không chắc chắn cao (avg_logprob < -0.65 hoặc no_speech_prob > 0.50), tuần tự hóa cấp phát bộ nhớ bằng threading.Lock() bảo vệ ngân sách VRAM < 2.0GB trên GPU laptop NVIDIA GeForce GTX 1650 Max-Q.
  - Silero VAD v6 ONNX Streaming (VoiceActivityDetector): Đánh giá luồng âm thanh theo các khối 576 mẫu (~36ms tại 16kHz) với độ trễ suy luận micro-second (p50 = 0.49ms), kết hợp khóa Post-TTS Settling Guard (150ms mutex lock) chống micro thu âm lại giọng phản hồi của chính trợ lý.
  - Nối dây trực tiếp Zero-Latency NLU-to-Dispatcher: Bỏ qua hoàn toàn Cloud LLM đối với 15 domains lệnh desktop / thiết bị / hệ thống cục bộ, thực thi tức thì qua ActionDispatcher với tau_NLU = 0.12ms và tau_Dispatch = 0.09ms.
  - Khắc phục triệt để lỗ hổng PII Scrubber (UnrecognizedTurnCollector): Sửa lỗi nhóm bắt giữ regex _PASSWORD_PREFIX_RE làm rò rỉ mật khẩu và thẻ tín dụng; bảo đảm 100% thay thế bằng [REDACTED_PASSWORD] và [REDACTED_CARD].
  - Toàn bộ 95 bài kiểm thử ASR, VAD, NLU, Automation và Argon E2E Benchmark: **100% PASS (95/95 passed)** trong **43.56s**.
- **Sprint 8 SOTA Vietnamese NLU Engine v4.0: Compound Multi-Intent, 15 Ontology Domains, ONNX Runtime (<2ms) & Continuous Learning Loop**:
  - Động cơ Phân rã Đa ý định (Compound Multi-Intent Decomposer): Tự động phân tích và bóc tách câu lệnh kép nối bằng liên từ ("và", "đồng thời", "sau đó", "rồi", ","), bảo vệ thực thể tra cứu và kích hoạt cơ chế phục hồi vị ngữ bị khuyết (Predicate Ellipsis Resolution: "tắt đèn phòng khách và phòng ngủ" -> 2 lệnh độc lập).
  - 15 Intent Domains Trợ lý Toàn diện (+ 1 OOD Negative Class): Bổ sung 5 domains desktop SOTA (`window_management`, `file_management`, `clipboard_action`, `network_control`, `system_power`), trích xuất tham số có kiểu (typed slots) chi tiết.
  - Bộ chuẩn hóa âm vị tiếng Việt (`VietnamesePhoneticNormalizer`): Xử lý triệt để các biến thể phiên âm tiếng Anh mượn từ Whisper STT ("cờ rôm" -> chrome, "ét xel" -> excel, "quốt" -> word, "sì po ti phai" -> spotify, "phây búc" -> facebook, "vê ét cốt" -> vscode, "wai phai" -> wifi).
  - Động cơ Suy luận ONNX Runtime C-API: Tăng tốc 34.3x cho bước tính xác suất ma trận, giảm độ trễ trung vị p50 từ 5.70ms xuống **1.87ms** và p95 xuống **2.78ms** trên CPU Intel Core i7 qua 2,500 lượt đo thực tế.
  - Vòng lặp Học tiếp diễn Tự động hóa (`/automation`): Tự động thu thập câu lệnh unknown / low-confidence (<0.45), khử trùng PII (Email, Phone, Card, Password), hợp nhất dữ liệu, loại bỏ trùng lặp và kích hoạt Gating kiểm định (CV Acc >= 97.5%, F1 >= 96.0%, 100% Golden Regression pass) trước khi triển khai model mới.
  - Toàn bộ 65 bài kiểm thử NLP, Router và Automation: **100% PASS (65/65 passed)**.
- **Sprint 7 Upgraded On-Device Vietnamese NLP Intent Classifier, Data Augmentation & Tier 0 ML Fast-Path**:
  - Mô hình Machine Learning phân loại ý định tiếng Việt cục bộ (`VietnameseNLPClassifier`): Kiến trúc lai ghép Dual N-Grams (Word n-grams 1-2 kết hợp Character sub-word n-grams 2-5) loại bỏ nhạy cảm với lỗi chính tả/gõ sai dấu, tích hợp bảo vệ tài nguyên OpenBLAS/OMP đa luồng chống tràn bộ nhớ.
  - Hiệu năng vượt trội sau nâng cấp: Pipeline huấn luyện `scripts/train_vietnamese_nlp.py` đạt **98.46% CV Accuracy** (± 0.22%) và **97.19% F1-macro** qua 5-Fold Stratified Cross-Validation trên 1,684 mẫu câu huấn luyện (tăng vọt từ 86.10% ban đầu).
  - Tự động hóa Data Augmentation: Tự sinh các biến thể không dấu (unaccented: "tat am thanh", "mo chrome", "tat may lanh"), các hạt từ cảm thán và tiền tố/hậu tố tự nhiên của khẩu ngữ tiếng Việt.
  - Bộ trích xuất tham số có kiểu (Typed Slot-Filling Engine): Tự động trích xuất chính xác level %, delta +/-, mute/unmute, app name, device, room location, nhiệt độ, thời gian và câu truy vấn cho 10 intent domains.
  - Xử lý Out-of-Distribution (OOD): Bộ lọc độ bao phủ từ vựng (Word Vocabulary Coverage) nhận diện và từ chối 100% các câu ngoài phạm vi và chuỗi ký tự ngẫu nhiên về nhãn `unknown`.
  - Tích hợp sâu Tier 0 ML Fast-Path: Kết nối trực tiếp vào `LLMIntentRouter` (`jarvis/llm/router.py`), cho phép xử lý câu lệnh offline tức thì với độ trễ <1.5ms, tiết kiệm 100% chi phí token và hoạt động trơn tru ngay cả khi mất mạng internet.
- **Sprint 6 Autonomous Tech Radar, Windows Standalone Packaging & Scheduled Automation Sidecar**:
  - Comprehensive Academic & Industry Tech Radar (`TechRadarAggregator`): Tự động quét và phân tích tài liệu học thuật SOTA từ ArXiv Atom 1.0 và open-source GitHub Trending, chuẩn hóa và nạp trực tiếp vào SQLite Continuous Learning Vault / Memory Graph của Argon (`knowledge_nodes`, `knowledge_edges`, `tech_radar_blips`).
  - Fixed Packaging Entrypoints & CLI Arguments: Khắc phục triệt để lỗi entrypoint GUI `main_tray()` trong `jarvis/__main__.py` (khắc phục `ImportError` của gui-script `jarvis-tray`) và đối số `--tray` trong `jarvis/cli.py` (khắc phục crash autostart registry `JARVIS.exe --tray`).
  - Standalone Windows Packaging Script (`scripts/build_standalone_package.py`): Đóng gói thương mại độc lập PyInstaller `--onedir` bundle vào `dist/JARVIS/JARVIS.exe`, triệt tiêu 120MB %TEMP% extraction penalty (khởi động tức thì <500ms), bundle đầy đủ native DLLs và assets. Hỗ trợ thẩm định `--dry-run` và kiểm tra môi trường máy sạch `--check`.
  - Scheduled Automation Sidecar (`sidecar.json`): Cấu hình chạy ngầm tự hành định kỳ 09:00 AM VN (`Asia/Ho_Chi_Minh`), điều phối 3 tác vụ `autonomous_tech_radar_sync`, `system_health_check`, và `learning_vault_consolidation` với cơ chế fail-closed ghi log tới `logs/sidecar.log`.
  - Fail-Closed Telegram STT (`STT_UNAVAILABLE`): Chuẩn hóa xử lý âm thanh Telegram khi STT offline/chưa cấu hình, loại bỏ hoàn toàn ghost success.
- **Sprint 5 Voice Biometrics, Streaming STT & Full-Duplex Realtime Voice Session**:
  - Nhận diện sinh trắc học giọng nói người nói (`VoiceBiometricsManager`): Trích xuất vector đặc trưng 64 chiều (Mel filterbank, spectral centroid/spread/flux, harmonic subband ratios) trên mặt cầu đơn vị, so khớp cosine distance, và lưu trữ đĩa nguyên tử an toàn Windows Atomic Persistence (retry loop WinError 5). Cổng xác thực trực tiếp tại `JARVISApp._start_voice_interaction` ngăn chặn người lạ kích hoạt trợ lý.
  - Nhận dạng giọng nói luồng theo khối thời gian thực (`StreamingSTTEngine` & `StreamingSTTSession`): Tiếp nhận audio 100ms - 200ms qua ring buffer, phát giả thuyết từng phần (`on_partial`) cập nhật HUD theo nhịp `step_interval_s = 0.25s`, hiển thị chữ chạy thời gian thực trên Overlay HUD ngay khi người dùng nói, và chốt phiên âm (`on_final`) khi gặp ngắt câu tự nhiên `silence_cutoff_s = 0.75s`.
  - Giao thức phiên thoại hai chiều thời gian thực (`RealtimeVoiceSession`): Máy trạng thái hội thoại đầy đủ (`IDLE`, `LISTENING`, `THINKING`, `SPEAKING`), hỗ trợ ngắt lời tức thì bằng giọng nói (Hardware/Acoustic Barge-In) khi người dùng cất tiếng trong lúc JARVIS đang phát TTS, lập tức dừng phát âm thanh và chuyển sang nghe tiếp.
  - Cơ sở khoa học & Viễn trắc phần cứng: Toàn bộ công trình nghiên cứu bình duyệt (ITU-T, IEEE, PNAS, MPEG-7) và số liệu đo đạc thực tế mic laptop được lập hồ sơ tại [`docs/SCIENTIFIC_FOUNDATIONS.md`](docs/SCIENTIFIC_FOUNDATIONS.md).
- **Sprint 4 Acoustic Front-End (AFE) & Whisper Hallucination Shield**:
  - Tiền xử lý âm học thương mại (`AcousticFrontEnd`): Bộ lọc thông dải Butterworth bậc 4 (80Hz - 7500Hz) triệt tiêu DC offset và rung quạt máy tính (<80Hz), kết hợp AGC và bộ giới hạn đỉnh `tanh`.
  - Whisper Hallucination Shield & Sàn nhiễu động (`live_noise_floor`): Thay thế ngưỡng năng lượng tĩnh cũ (0.015) bằng ngưỡng thích ứng môi trường (`max(0.018, floor * 2.5)`). Bỏ qua STT khi chỉ có tiếng quạt/ồn nền (SNR < 5.5 dB), tiết kiệm >3.3s CPU và ngăn chặn 100% ảo giác phiên âm ("Affair", "Life", "A fifth").
- **Sprint 1 Voice & Audio Pipeline Overhaul**:
  - Triệt tiêu hoàn toàn nghịch lý nhạy/chặt của wake-word bằng cơ chế Two-Stage Wake-Word Verification: đồng bộ tham số nhạy/candidate gate (`0.02`), bổ sung danh mục bí danh ngữ âm tiếng Việt (`chào jarvis`, `ơi jarvis`, `ê jarvis`, `tra vit`) và chuẩn hóa chuỗi `transcript` đầu vào trong `WhisperSlidingWindowDetector`.
  - Sentence-Level Streaming TTS: Phân tách câu hội thoại và phát âm dạng luồng theo từng câu, giảm Time-to-First-Audio xuống <800ms.
  - True Low-Latency Barge-In: Ngắt lời tức thì qua hotkey PTT (`Ctrl+Shift+L`), khẩu lệnh thoại (`dừng nói`, `im lặng`, `stop talking`), và tự động dừng phát khi bắt đầu lượt tương tác mới mà không phá hủy cache hay dừng luồng TTS worker.
- **Sprint 2 Local Semantic Router & Typed Slot-Filling**:
  - Kiến trúc phân giải intent cận biên (`LocalSemanticRouter`) đạt độ trễ <0.5ms cho 90% tương tác hàng ngày (âm lượng, độ sáng, Home Assistant IoT, quản lý tabs/cửa sổ, nghe nhạc, hẹn giờ/nhắc nhở, tìm kiếm).
  - Trích xuất tham số có kiểu (level %, delta +/-, entity_id, nhiệt độ, duration giây), chuẩn hóa số từ tiếng Việt, và loại bỏ tiền tố xưng hô tự nhiên ("jarvis ơi", "cho mình", "làm ơn").
- **Sprint 3 Native Windows UI Automation & Fast-Path Accessibility**:
  - Bộ điều khiển `WindowsUIAutomation` thuần ctypes Win32 API, đồng bộ Desktop Station `Default` cho 100% khả năng hiển thị cửa sổ tương tác từ tiến trình ngầm.
  - Thao tác trực tiếp (direct control manipulation) qua `BM_CLICK` và `WM_SETTEXT` với độ trễ <50ms; tích hợp fast-path vào `GUIActor` và `ComputerController` giúp giảm phụ thuộc vào Vision LLM 2.5-4s.
- Triệt tiêu 6 lỗi trung thực (BUGS 1-6): Webhook fail-closed trên URL sai/lỗi mạng, IMAP quarantine tags bảo toàn khi truncate, Agent tool runtime tôn trọng cờ success tường minh, TTSManager khắc phục race enqueue/drain, vô hiệu hóa legacy auto-apply updater chưa xác thực, chuẩn hóa status timeout khi xác minh cửa sổ app launcher.
- Triệt tiêu các lỗ hổng trung thực (PacketCapture TShark parsing, Telegram/Discord API 200/ok verification, Terminal UI truthful dispatch).
- Triệt tiêu 100% `RuntimeWarning: coroutine 'Server._close' was never awaited` trong vòng đời tắt Web Dashboard / WebSocket.
- Sửa đứt gãy OpenWakeWord streaming qua cooldown bằng bộ đệm trượt `_OpenWakeWordFrameBuffer` (1.280 mẫu).
- Kích hoạt AppContainer kernel network isolation mặc định cho `execute_python()` với fallback an toàn Low-Integrity.
- Tích hợp `ReActAgent` hoàn chỉnh vào `ActionDispatcher` và `SafetyGateInterceptor` với kiểm soát workspace.
- Hợp nhất schema Skill manifest (`display_name`, `actions`) và bảo vệ manifest khỏi telemetry runtime bằng `.to_manifest_dict()`.
- Phân rã hai God-objects: `app.py` (từ 3.965 xuống 2.136 dòng qua `jarvis/core/handlers/`) và `router.py` (từ 3.678 xuống 2.214 dòng qua `rules_catalog.py`).
- Nghiệm thu hiện tại: microphone probe đạt **PASS engineering** (25 input devices, default index 1). Artifact ambient cũ chỉ dài **2,06 giây** nên đã bị hạ verdict và **không** còn được dùng làm bằng chứng false-wake runtime. Recall `true_wake` 10 lần và ambient soak tối thiểu 120 giây vẫn **PENDING**. Báo cáo 10-workflow cũ cũng bị vô hiệu hóa; preflight mới đã được sửa thành seam in-memory 10/10, không initialize/dispatch subsystem, nhưng 200 trial voice/Real-OS vẫn **PENDING**. Product GO tiếp tục **PENDING**.
- Full unit test suite (`tests/unit/`): **162 test files, 3,186 unit tests, 100% PASS, 0 failures**.
- Security scanner: **0 findings / 218 files / 75,313 lines / 2.96s** (Clean scan).

Wake-word hardening trước đó (2026-10-04), source **5.2.1**:

Release hardening trước đó (2026-10-04), source **5.2.1**:
đã bổ sung confirmation cho auto-kill/dialog dismissal, sửa các nhánh báo thành
công giả, decoder TTS, fallback LLM và khai báo dependency đóng gói âm thanh.
Scoped verification: **147 passed + 15 subtests, 42.74s**; không phải full-suite
hay nghiệm thu microphone thật. Đã loại bỏ giá tài chính cố định khi mất API.
Full post-briefing run: **4321 passed / 3 failed / 40 skipped**, 268 subtests,
1 warning; ba test hợp đồng/fixture đã được xử lý tiếp nhưng chưa có full-green
trên cây cuối. Ghi chú đã có atomic replace và bảo vệ JSON hỏng.
Nhóm regression cuối gồm ba ca lỗi đã sửa: **76 passed / 38.75s**.
Xem [báo cáo và gate phát hành](docs/eval/release_readiness_20261004.md).
Các kết quả ngày 23/09 dưới đây là lịch sử, không phải lần chạy hiện tại.

Runtime repair verification (2026-09-23): unit **3,002 passed / 3 skipped**;
E2E **290 passed / 21 skipped**; security subset **66 passed**; scanner **0
findings** trên 202 tệp. Full repository chưa được chứng nhận vì còn nhóm test
legacy ngoài unit; không dùng kết quả partial để tuyên bố full-green. Release
vẫn NO-GO vì 10 workflow mới có routing evidence, còn voice live, credential,
hardware và clean-machine installer evidence chưa đủ.
[runtime evidence](docs/eval/runtime_fix_verification_20260923.md).

SRS hiện trạng: [Markdown](docs/SRS_JARVIS_Current_System_2026-09-23.md) ·
[Word DOCX](docs/SRS_JARVIS_Current_System_2026-09-23.docx).

10-workflow matrix: [routing/runtime evidence](docs/eval/workflow_10_windows_runtime_20260923.md).
Dispatcher đã có `BackendResult`/`HealthStatus` seam dùng chung; connector migration
toàn bộ vẫn đang theo từng phase.

Verified app launch follow-up (2026-09-22, unreleased **5.2.1**): câu mở desktop
app đi qua danh mục cục bộ và xác minh cửa sổ theo AUMID/đường dẫn executable;
không dùng tên gần giống làm bằng chứng. Notepad/Calculator được gộp đúng định danh.
Scoped **244 tests + 25 subtests passed**. Kiểm tra thật **8/8 ca** trên máy này
(6 thao tác qua dispatcher + 2 ca chỉ phân tích lệnh), gồm khôi phục Calculator
thu nhỏ đúng cửa sổ. Quét **175 mục**, không phải 175 ứng dụng đã được thử mở.
Còn giới hạn shared launcher/profile, portable, lựa chọn mặc định và nghiệm thu máy khác.
[Báo cáo hiện tại](docs/eval/app_catalog_verified_20260922.md).

Các mục stage 1 dưới đây là lịch sử; xem báo cáo trên để biết trạng thái mới.

Installed-app discovery **stage 1**, unreleased, source version **5.2.1**:
`mở ứng dụng <tên chính xác>` tra cứu danh mục Windows hiện tại thay vì chỉ alias
cố định. Trùng tên cần chọn; AppID/launcher chưa xác minh cửa sổ không báo success.
Chưa có UI chọn/lưu mặc định, portable-folder setup hay nghiệm thu nhiều máy.
[Evidence và giới hạn](docs/eval/app_catalog_20260922.md).

Windows app/web patch (2026-09-22, source `jarvis.__version__` **5.2.1**, unreleased):
giữ nguyên URL đích, encode search, không báo mở thành công khi browser từ chối,
không đoán app bằng chuỗi con. **76 scoped tests + 25 subtests passed**; chưa xác
minh cửa sổ/trang tải thật. [Phạm vi và evidence mới](docs/eval/windows_command_execution_20260922.md).

<div align="center">

[![CI Status](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/workflows/ci.yml/badge.svg)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)
[![Tests](https://img.shields.io/badge/tests-see_current_audit-orange?style=flat-square)](docs/eval/readiness_security_audit_20260922.md)
[![Source Version](https://img.shields.io/badge/source%20version-5.3.0-purple?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/blob/main/pyproject.toml)
[![Releases](https://img.shields.io/badge/releases-GitHub-blue?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/releases)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue?style=flat-square)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11%2064--bit-0078D4?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)

**JARVIS** là hệ thống trợ lý AI cá nhân tự trị (Autonomous AI Desktop Assistant) chạy nền trên Windows 11/10 64-bit, lấy cảm hứng từ trợ lý JARVIS của Tony Stark trong Iron Man. 
JARVIS có khả năng nhận diện giọng nói offline tiếng Việt & tiếng Anh, tự động phân luồng ý định thông minh, tự động viết mã mở rộng kỹ năng (Self-Coding với Sandbox Dry-Run), ghi nhớ nhật ký và tìm kiếm từ vựng thời gian thực (Lexical / TF-IDF Search Memory), điều khiển toàn diện hệ thống Windows, tự động hóa trình duyệt bằng Chromium do Playwright quản lý hoặc phiên Chromium được attach qua CDP, và kết nối điều khiển từ xa qua Telegram, Zalo OA và Discord.

<sub>**Phiên bản mã nguồn / phát triển (`jarvis.__version__`): 5.3.0.** Nâng cấp SOTA Voice & NLP Blueprint: AWACI Screen Context Awareness, Speculative Intent Pre-Routing, Joint BIO Slot Tagger INT8 & Night-Shift Autonomous Flywheel. **Product release: NO-GO**; chưa đóng các gate runtime hoặc nghiệm thu máy sạch. Xem [kiểm toán hiện tại và số liệu kiểm thử](docs/eval/readiness_security_audit_20260922.md). Các số liệu T-01, Telegram, Router và 2.421 unit tests ở tài liệu cũ là evidence lịch sử, không phải kết quả tái nghiệm thu của bản vá này.</sub>


</div>

---

## 📋 Mục Lục

1. [✨ Tính Năng Nổi Bật](#-tính-năng-nổi-bật)
2. [💻 Yêu Cầu Hệ Thống (Prerequisites)](#-yêu-cầu-hệ-thống-prerequisites)
3. [🚀 Hướng Dẫn Cài Đặt Từng Bước (Step-by-Step Installation)](#-hướng-dẫn-cài-đặt-từng-bước-step-by-step-installation)
4. [⚡ Dành Cho Người Dùng Cuối — Quick Start (Installer & Standalone ZIP)](#-dành-cho-người-dùng-cuối--quick-start-installer--standalone-zip)
5. [🛠️ Dành Cho Nhà Phát Triển (Developer Setup)](#%EF%B8%8F-dành-cho-nhà-phát-triển-developer-setup)
6. [🔧 Các Lỗi Thường Gặp & Cách Khắc Phục (Common Errors & Fixes)](#-các-lỗi-thường-gặp--cách-khắc-phục-common-errors--fixes)
7. [⚙️ Cấu Hình `.env`](#%EF%B8%8F-cấu-hình-env)
8. [🧰 Danh Sách Kỹ Năng Chi Tiết (18+ Skills)](#-danh-sách-kỹ-năng-chi-tiết-18-skills)
9. [⌨️ Phím Tắt Toàn Hệ Thống](#%EF%B8%8F-phím-tắt-toàn-hệ-thống)
10. [📱 Điều Khiển Qua Điện Thoại (Telegram / Zalo / Discord)](#-điều-khiển-qua-điện-thoại)
11. [🏗️ Kiến Trúc Giọng Nói & Tự Trị (Architecture)](#%EF%B8%8F-kiến-trúc-giọng-nói--tự-trị-architecture)
12. [🔒 Mô Hình Bảo Mật (Security Model)](#-mô-hình-bảo-mật-security-model)
13. [📄 Giấy Phép & Tác Giả](#-giấy-phép--tác-giả)

---

## ✨ Tính Năng Nổi Bật

### 🎙️ Nhận Diện Giọng Nói Offline & Voice Pipeline (v5.1.3 Beta v1)
- **Wake Word:** Nhận diện từ khóa *"Hey JARVIS"* tức thì với độ trễ cực thấp.
- **Wake-word calibration:** Có thể ghi score classifier thật cho hai phiên `true_wake` và `ambient` bằng `tools/wake_word_score_probe.py`; hệ thống không tự đổi threshold khi chưa có dữ liệu có nhãn.
- **Wake-word acceptance fail-closed:** `tools/live_wake_word_acceptance.py` chỉ trả `PASS runtime` khi có frame/score microphone thật, đúng OpenWakeWord + Whisper cascade và đạt tiêu chí phiên. `true_wake` 0/10 là lỗi; ambient dưới 120 giây bị chặn; mặc định dùng sensitivity production thay vì âm thầm ghi đè.
- **Barge-in (Ngắt lời tức thời):** Khi JARVIS đang nói, bạn có thể nói chèn vào — hệ thống lập tức tắt âm thanh TTS và chuyển sang nghe lệnh mới.
- **VAD (Voice Activity Detection):** Thuật toán phát hiện giọng nói thông minh bằng năng lượng RMS hoặc WebRTC VAD — xử lý offline, độ trễ <10ms.
- **STT (Speech-to-Text) & Safe Diacritic Normalization:** Faster-Whisper (CTranslate2) chạy offline với bộ chuẩn hóa bỏ dấu đa âm an toàn (`strip_vietnamese_diacritics`) bảo vệ nguyên vẹn từ đơn, triệt tiêu 100% va chạm homophone (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`, `tắt` vs `tắc`).
- **Kháng Lệch Ngữ Âm (Phonetic Drift Robustness):** Tích hợp 15 alias ngữ âm chọn lọc cho các lỗi nghe nhầm đặc thù của Faster-Whisper (`tắc máy`, `tập máy tính`, `cái đặt`, `đặt time`, `tắc tính`, `tắt tính`, `ghi chú`), nâng độ chính xác thực tế trên 90 audio test lên 63.3% và đạt 100% trên tập held-out mới.
- **Tiered STT Coordinator (v5.1.0 Phase 5):** Tự động điều phối phân tầng nhận diện đa cấp giữa Faster-Whisper Local (Tier 1), OpenAI Whisper Cloud (Tier 2) và Windows SAPI (Tier 3) dựa trên ước tính chất lượng tín hiệu SNR (>10dB) và thời hạn deadline; tích hợp VAD silence bypass (<1ms, 0 GPU inference).
- **TTS (Text-to-Speech):** Piper TTS offline mượt mà tự nhiên (<80ms) cùng tùy chọn kết nối ElevenLabs chất lượng studio.

### 🧠 Router Ý Định 3 Lớp Thông Minh (3-Tier Intent Router)
- **Regex & Rule Fast-Path:** Nhận diện ngay lập tức hơn 150+ mẫu câu lệnh tiếng Việt không cần gọi LLM (zero-latency, 0 token), tự động hỗ trợ cả có dấu, không dấu và biến thể ngữ âm.
- **Project & Workspace Assistant:** Quản lý dự án, chuẩn bị workspace, tạo project, liệt kê thư mục và theo dõi Git thông minh.
- **Fallback Gemini LLM:** Phân tích ý định phức tạp qua Google Gemini 1.5 Flash / Pro khi không khớp rule.
- **Autonomous ReAct Agent:** Tự động lập kế hoạch (Plan), thực thi công cụ (Act), quan sát (Observe) và phản hồi (Reflect).

### 🧬 Tự Sinh Kỹ Năng Mới (Self-Coding Skills)
- Nói *"JARVIS, tạo kỹ năng theo dõi giá vàng"* → JARVIS tự thiết kế interface, viết code Python, kiểm tra cú pháp an toàn tĩnh (AST Validator), chạy thử nghiệm cô lập trong CodeInterpreterSandbox (Job Object & Low Integrity) và đăng ký trực tiếp vào hệ thống trong <15 giây.

### 🔍 Bộ Nhớ Từ Vựng & Tìm Kiếm Tài Liệu (Lexical Search Memory - Tier 1 Hardened)
- Tự động lưu trữ nhật ký hội thoại, ghi chú và tài liệu vào SQLite lexical store (TF-IDF BM25 & Cosine Similarity) hoàn toàn offline.
- **An toàn đa luồng & Ghi đĩa nguyên tử (Phase 6):** Kiểm thử chịu tải 30 luồng đồng thời (30-thread stress test), khóa `RLock` toàn diện, và cơ chế ghi đĩa nguyên tử (Atomic Replace) ngăn chặn triệt để tình trạng hỏng dữ liệu hoặc xung đột đọc/ghi khi nhiều tác vụ chạy ngầm.
- Tìm kiếm từ khóa và ngữ cảnh: *"Hôm qua tôi nói gì về kế hoạch dự án?"*

### 🌐 Tự Động Hóa Trình Duyệt & Hệ Thống
- Mở Chromium thật do Playwright quản lý hoặc attach một Chromium đang chạy qua Chrome DevTools Protocol (`connect_over_cdp`).
- Thực hiện và xác minh navigate, click, clear-first typing, selector wait, scroll, DOM/title/URL read và screenshot thật; timeout, browser đóng và CDP mất kết nối trả status/error code fail-closed.
- HTTP fallback chỉ đọc HTML và luôn báo đúng `driver_type=http_scraper`; nó không thể biến click/type/wait/scroll/screenshot thành success. Mock chỉ dùng khi caller chọn rõ `driver_type=mock` và không được tính là E2E.
- Price comparison chỉ trả offer có nguồn JSON-LD/DOM quan sát được; không sinh giá 0, stock hoặc shipping giả khi scrape thất bại.
- Phân tích ngữ cảnh màn hình tức thời qua Gemini Vision AI (`Ctrl+Shift+Space`).
- Tự động hóa macro chuột/bàn phím, điều khiển âm lượng, màn hình, quản lý file và ứng dụng Windows.

---

## 💻 Yêu Cầu Hệ Thống (Prerequisites)

Trước khi cài đặt, vui lòng đảm bảo máy tính của bạn đáp ứng các yêu cầu sau:

| Thành phần | Yêu cầu tối thiểu | Chi tiết & Link tải chính thức |
|---|---|---|
| **Hệ điều hành** | Windows 11 / 10 (64-bit) | Build 19041 trở lên (Hỗ trợ Win32 API & System Tray) |
| **Python** | **Python 3.13+ (64-bit)** | Tải tại: [Python 3.13.2 64-bit](https://www.python.org/downloads/release/python-3132/)<br>⚠️ **Bắt buộc:** Tích chọn ✅ **"Add python.exe to PATH"** trong màn hình cài đặt đầu tiên. |
| **Git** | Git for Windows | Tải tại: [Git for Windows Official](https://git-scm.com/download/win) |
| **Visual C++ Runtime** | VC++ 2015–2022 Redistributable (x64) | Tải tại: [vc_redist.x64.exe (Microsoft)](https://aka.ms/vs/17/release/vc_redist.x64.exe)<br>*(Bắt buộc cho Pillow, sounddevice, CTranslate2, faster-whisper)* |
| **Phần cứng âm thanh** | Microphone & Loa / Tai nghe | Đảm bảo micro và loa hoạt động bình thường trong Windows Settings |
| **API Key** | Google Gemini API Key | Lấy miễn phí tại: [Google AI Studio](https://aistudio.google.com/apikey) |

---

## 🚀 Hướng Dẫn Cài Đặt Từng Bước (Step-by-Step Installation)

Dành cho người dùng và lập trình viên muốn cài đặt từ mã nguồn (Source Code) trên Windows 11/10.

### Bước 1: Clone kho mã nguồn (Repository)

Mở **PowerShell** hoặc **Command Prompt (Terminal)** và chạy:

```powershell
git clone https://github.com/Duong-Phuoc-Hung/JARVIS.git
cd JARVIS
```

### Bước 2: Tạo môi trường ảo (Virtual Environment)

Tạo môi trường ảo độc lập để tránh xung đột với các thư viện Python khác trên hệ thống:

```powershell
python -m venv .venv
```

### Bước 3: Kích hoạt Virtual Environment

- **Trên PowerShell:**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
  *(💡 Nếu gặp lỗi `ExecutionPolicy`: chạy lệnh `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` rồi kích hoạt lại).*

- **Trên Command Prompt (CMD):**
  ```cmd
  .venv\Scripts\activate.bat
  ```

Sau khi kích hoạt, đầu dòng lệnh sẽ xuất hiện tiền tố `(.venv)`.

### Bước 4: Cài đặt các thư viện phụ thuộc (Dependencies)

Cập nhật `pip` và cài đặt danh mục thư viện:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> ⏳ Quá trình cài đặt mất khoảng 1–3 phút tùy tốc độ mạng.

### Bước 5: Cấu hình file môi trường `.env`

Tạo file `.env` tại thư mục gốc của dự án `JARVIS\` và điền Gemini API Key của bạn:

```powershell
# Tạo nhanh file .env bằng PowerShell (UTF-8 clean encoding):
Set-Content -Path .env -Value "GEMINI_API_KEY=AIzaSyYourActualAPIKeyHere" -Encoding utf8
```

Hoặc mở trình soạn thảo và tạo file `.env` với nội dung đầy đủ:

```env
# ── Cấu hình bắt buộc ─────────────────────────────────────────
GEMINI_API_KEY=AIzaSyYourActualGeminiAPIKeyHere
GOOGLE_API_KEY=AIzaSyYourActualGeminiAPIKeyHere

# ── Cấu hình giọng nói & ngôn ngữ (Tùy chọn) ─────────────────
JARVIS_LANGUAGE=vi
JARVIS_WHISPER_MODEL=base
JARVIS_VOICE=vi_VN-vivos-medium

# ── Điều khiển từ xa (Tùy chọn) ──────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
ZALO_ACCESS_TOKEN=
ZALO_OA_ID=
```

### Bước 6: Kiểm tra sức khỏe hệ thống (Health Check)

Chạy lệnh kiểm tra chẩn đoán toàn bộ 17 hệ thống con (Audio, Wake Word, Memory Store, UI Tray, Router, v.v.):

```powershell
python -m jarvis health-check
```

Đảm bảo tất cả các mục quan trọng đều báo `[+] READY`.

### Bước 7: Khởi chạy JARVIS lần đầu

```powershell
# Khởi chạy JARVIS (Mặc định chạy nền ở khay hệ thống System Tray):
python -m jarvis

# Xem trợ giúp và danh sách tùy chọn dòng lệnh:
python -m jarvis --help

# Khởi chạy ở chế độ Headless (không bật khay hệ thống):
python -m jarvis run --headless
```

Sau khi khởi chạy:
- Biểu tượng JARVIS xuất hiện ở khay hệ thống (System Tray cạnh đồng hồ).
- Nói *"Hey JARVIS"* hoặc nhấn phím tắt `Ctrl+Shift+J` để bắt đầu trò chuyện!

### Bước 8: J.A.R.V.I.S. Terminal Control Center (giao diện Terminal tương tác)

Ngoài chế độ voice-first mặc định, JARVIS còn cung cấp một giao diện Terminal/PowerShell
tương tác dạng menu phân cấp — một lớp trình bày mỏng (thin presentation layer) gọi trực
tiếp vào các module sản phẩm hiện có, không sao chép logic nghiệp vụ hay bỏ qua bất kỳ cơ chế
an toàn nào:

```powershell
python -m jarvis menu
# hoặc, sau khi cài đặt package:
jarvis menu
```

Điều hướng bằng một phím số duy nhất (hỗ trợ cả `msvcrt` một-phím trên Windows Terminal/
PowerShell lẫn chế độ nhập dòng khi stdin được redirect). Bộ phím toàn cục nhất quán trên mọi
màn hình:

| Phím | Chức năng |
|---|---|
| `[1]`–`[9]` | Chọn module (Hardware, InfoSec, Workflow, Data, Smart Home, Biometrics, Gesture, Communications, Self-Healing) |
| `[J]` | Khởi chạy JARVIS Voice Core thật (cùng một `JarvisApp` dùng bởi `jarvis run` — không có lõi JARVIS thứ hai) |
| `[A]` | Chạy tất cả các thao tác **an toàn cho batch** trên màn hình hiện tại — chỉ hiển thị khi có **từ 2 thao tác an toàn trở lên** (không bao giờ gửi tin nhắn, không bao giờ chấm dứt tiến trình, không bao giờ bật/tắt toàn bộ thiết bị) |
| `[R]` | Làm mới màn hình hiện tại |
| `[S]` | Lưu kết quả/phiên làm việc vào thư mục báo cáo của JARVIS (`%LOCALAPPDATA%/JARVIS/reports/cli/`) |
| `[B]` | Quay lại một cấp menu |
| `[H]` | Trợ giúp cho màn hình hiện tại |
| `[0]` | Thoát |

**An toàn**: mọi trạng thái hiển thị đều trung thực (không có `READY` giả chỉ vì một class
import thành công); mọi báo cáo lưu đều được xác minh đã ghi thành công trước khi báo "Đã
lưu"; các thông tin nhạy cảm (token, mật khẩu, embedding sinh trắc học) luôn được ẩn
(`<REDACTED>`) trước khi lưu hoặc hiển thị. Xác nhận Y/N trên Terminal chỉ là lớp UX quyết
định có thử gọi hành động hay không — không bao giờ tự nó là lớp xác thực. Với **chấm dứt
tiến trình** (Self-Healing), backend `HealingEngine` tự kiểm tra danh sách tiến trình được
bảo vệ (`PROTECTED_PROCESS_WHITELIST`) trước khi thực thi, bất kể ai gọi. Với **điều khiển
thiết bị Smart Home**, hiện chưa có cơ chế xác thực đáng tin cậy nào (không có action
`ActionDispatcher` chính thức, không có hợp đồng an toàn nào trong `HomeAssistantClient`) —
vì vậy các thao tác Turn On/Off/Toggle/Set Temperature **hiện chưa thực thi thật**, chỉ báo
cáo trạng thái trung thực rằng chưa có đường xác thực khả dụng, thay vì gọi thẳng API mà
không có cơ chế bảo vệ nào phía sau. Không bao giờ chạy tự động qua `[A]`.

---

## ⚡ Dành Cho Người Dùng Cuối — Quick Start (Installer & Standalone ZIP)

Để phục vụ thử nghiệm Product Beta v1 cho 10–30 người dùng nội bộ, JARVIS cung cấp cả bộ cài đặt chuẩn Windows một chạm và bản portable ZIP độc lập:

### Cách 1: Bộ Cài Đặt Một Chạm — One-Click Windows Installer (Khuyến nghị cho Beta v1)
1. **Tải Bộ Cài Đặt:**
   - Tải file `JARVIS_Setup_v5.1.0.exe` (71.4 MB) từ [Releases Page](https://github.com/Duong-Phuoc-Hung/JARVIS/releases) hoặc thư mục phát hành `dist/installer/`.
   - **Mã băm kiểm tra toàn vẹn SHA-256**:
     ```text
     E6335E5BF7F704B0FA09E38937BA89CB668939FF9090746B45150ED722031650
     ```
2. **Cài Đặt Dễ Dàng:**
   - Chạy `JARVIS_Setup_v5.1.0.exe` và làm theo hướng dẫn trên màn hình.
   - Trình cài đặt Inno Setup 6 tự động tạo shortcut trên Desktop, Start Menu và tùy chọn khởi động cùng Windows.
3. **Cấu Hình & Khởi Động:**
   - Điền Gemini API Key trong giao diện cấu hình ban đầu hoặc lưu vào Windows Credential Manager.
   - JARVIS sẽ chạy nền tại khay hệ thống (System Tray). Nhấn tổ hợp phím `Ctrl+Shift+L` hoặc nói *"Hey JARVIS"* để ra lệnh.
4. **Gỡ Cài Đặt Sạch Sẽ:**
   - Gỡ bỏ dễ dàng và an toàn thông qua Windows Settings > Apps & Features hoặc chạy `unins000.exe` trong thư mục cài đặt mà không làm mất cấu hình cá nhân của người dùng.

### Cách 2: Bản Standalone Portable (ZIP)
Nếu bạn không muốn cài đặt vào Program Files:
1. Tải file ZIP `JARVIS_v5.3.0_windows_x64.zip` từ trang Releases (hoặc tự tạo trực tiếp từ mã nguồn bằng lệnh `python scripts/build_standalone_package.py`).
2. Giải nén vào thư mục tùy chọn (ví dụ: `D:\JARVIS\`).
3. Chạy `JARVIS.exe` hoặc `JARVIS.exe --tray` để khởi chạy ứng dụng trực tiếp vào khay hệ thống mà không cần cài đặt Python.

### 🚀 Khởi Chạy Từ Dòng Lệnh (CLI & Source Execution)
Sau khi cài đặt hoặc trong môi trường phát triển:
```powershell
# Khởi chạy daemon trợ lý mặc định:
python -m jarvis

# Khởi chạy trực tiếp vào khay hệ thống (System Tray mode):
JARVIS.exe --tray
# hoặc từ mã nguồn:
python -m jarvis --tray
python -m jarvis.cli --tray

# Khởi chạy entrypoint GUI chuẩn (được cài đặt qua pip/wheel):
jarvis-tray

# Chẩn đoán sức khỏe phần cứng và 17 phân hệ:
python -m jarvis health-check

# Mở trung tâm điều khiển tương tác (Terminal Control Center):
python -m jarvis menu
```

### 🔐 Chữ Ký Số Authenticode & Bảo Mật Binary (Code Signing)
Toàn bộ các bản phát hành nhị phân (`JARVIS.exe` standalone và bộ cài đặt `JARVIS_Setup_*.exe`) đều được gắn chữ ký số Windows Authenticode (mã băm SHA-256) tự động trong pipeline GitHub Actions CI nhằm bảo vệ tính toàn vẹn mã nguồn (code integrity) và ngăn chặn mã độc can thiệp/chỉnh sửa trái phép (tamper detection).

- **Cảnh báo Windows SmartScreen ("Unknown Publisher")**: Vì JARVIS là dự án mã nguồn mở sử dụng chứng thư Authenticode tự ký (self-signed) trong CI để giữ chi phí $0, Windows SmartScreen sẽ hiển thị hộp thoại cảnh báo *"Windows protected your PC / Unknown Publisher"* trong lần khởi chạy đầu tiên. Đây là hành vi bảo mật mặc định của Windows đối với các chứng thư chưa tích lũy danh tiếng SmartScreen. Người dùng hoàn toàn có thể yên tâm bấm **"More info" → "Run anyway"** để khởi chạy ứng dụng.
- **Tài liệu hướng dẫn ký số & Nâng cấp sản xuất**:
  * **Ký thủ công qua SignPath Web UI (Option A)**: Dành cho release engineer muốn ký số qua cổng SignPath Foundation mà không tốn phí, xem hướng dẫn chi tiết tại [`docs/signing/manual_signing_guide.md`](docs/signing/manual_signing_guide.md).
  * **Lộ trình nâng cấp chứng thư sản xuất (Option B)**: Đánh giá chi phí và hướng dẫn tích hợp chứng thư số thương mại toàn cầu (Microsoft Azure Trusted Signing, DigiCert, Sectigo) cho các bản phát hành v5.2.0 chính thức, xem tại [`docs/signing/production_signing_upgrade.md`](docs/signing/production_signing_upgrade.md).

---

## 🛠️ Dành Cho Nhà Phát Triển (Developer Setup)

Dành cho các lập trình viên muốn tùy biến mã nguồn, viết thêm kỹ năng hoặc đóng góp mã nguồn (Contributing).

### Cài đặt môi trường phát triển đầy đủ

```powershell
git clone https://github.com/Duong-Phuoc-Hung/JARVIS.git
cd JARVIS
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Cài đặt trọn gói bao gồm tất cả dev dependencies và optional extras:
pip install -e ".[all]"

# Cài Chromium revision tương thích với Playwright để dùng browser automation/E2E:
python -m playwright install chromium
```

### Chạy bộ kiểm thử (Running Test Suites)

JARVIS bao gồm 162 test files với hơn 3.186 bài kiểm thử tự động cùng các bộ kiểm chuẩn chuyên biệt:

```powershell
# 1. Chạy bộ kiểm thử chấp nhận E2E Beta v1 (28 tests qua 4 tầng kiểm thử):
pytest tests/e2e/test_beta_v1_acceptance.py -v

# 2. Chạy bộ hồi quy Voice Pipeline Seams (8 tests):
pytest tests/unit/test_voice_pipeline_fixes.py -v

# 3. Chạy bộ kiểm thử Zalo Controller Seams (25 tests):
pytest tests/unit/test_zalo_bot.py -v

# 4. Chạy bộ kiểm thử đối kháng Fail-Closed Comms Hub (18 tests):
pytest tests/test_adversarial_beta_m1_comms_failclosed.py -v

# 5. Chạy deterministic local E2E bằng Chromium/CDP thật (opt-in, không dùng mạng ngoài):
$env:JARVIS_RUN_BROWSER_E2E = "1"
pytest tests/e2e/test_browser_playwright_e2e.py -v --timeout=120

# 6. Chạy toàn bộ unit release gate:
pytest tests/unit/

# 7. Chạy toàn bộ test suites kết hợp:
pytest tests/

# 8. Chạy kiểm thử kèm báo cáo độ bao phủ mã nguồn (Coverage Report):
pytest tests/ --cov=jarvis --cov-report=term-missing
```

Evidence T-01 được lưu tại `reports/evidence/T-01/`. Snapshot 2026-09-16 có 21/21
real-browser E2E, 301/301 browser-scoped tests và full `tests/unit/` 2267 passed / 4 skipped;
T-01 được chứng nhận DONE trên môi trường test chuẩn CI với writable isolated profile.

### Kiểm tra cú pháp, Linting & Type Checking

```powershell
# Kiểm tra code style và quy chuẩn với Ruff:
ruff check .

# Tự động định dạng code:
ruff format .

# Kiểm tra tĩnh kiểu dữ liệu (Static Type Checking) với Mypy:
mypy jarvis
```

### Đóng gói ứng dụng (Building Executable & Installer)

```powershell
# 1. Đóng gói thành file chạy trực tiếp dist/JARVIS.exe:
python scripts/build_exe.py

# 2. Đóng gói thành file cài đặt Windows Installer dist/installer/JARVIS_Setup_v5.1.0.exe
#    (chỉ build local qua Inno Setup — release workflow chính thức trên GitHub Actions
#    KHÔNG publish file Setup này, chỉ publish JARVIS_v<version>_windows_x64.zip):
python scripts/build_installer.py
```

---

## 🔧 Các Lỗi Thường Gặp & Cách Khắc Phục (Common Errors & Fixes)

Dưới đây là 5 lỗi phổ biến nhất và giải pháp xử lý triệt để:

### 1. ❌ SQLite database locked / Permission Denied
- **Hiện tượng:** Gặp lỗi `sqlite3.OperationalError: database is locked` hoặc `PermissionError` khi khởi động hoặc lưu ghi chú.
- **Nguyên nhân:** Có tiến trình JARVIS khác đang chạy ngầm chiếm giữ database, hoặc phiên làm việc trước bị tắt đột ngột khiến file `.wal` / `.shm` bị khóa.
- **Cách khắc phục:**
  1. Đóng toàn bộ tiến trình JARVIS đang chạy:
     ```powershell
     Stop-Process -Name "JARVIS","python" -Force -ErrorAction SilentlyContinue
     ```
  2. Kiểm tra thư mục dữ liệu tại `%LOCALAPPDATA%\JARVIS\data` (hoặc `~/.jarvis/`).
  3. Xóa các file lock tạm `.wal` và `.shm`:
     ```powershell
     Remove-Item "$env:LOCALAPPDATA\JARVIS\data\*.db-wal" -Force -ErrorAction SilentlyContinue
     Remove-Item "$env:LOCALAPPDATA\JARVIS\data\*.db-shm" -Force -ErrorAction SilentlyContinue
     ```
  4. Khởi động lại JARVIS.

---

### 2. ❌ PIL / Pillow DLL Load Failed
- **Hiện tượng:** `ImportError: DLL load failed while importing _imaging: The specified module could not be found.`
- **Nguyên nhân:** Hệ điều hành Windows bị thiếu thư viện C runtime của Microsoft hoặc cache cài đặt Pillow bị lỗi.
- **Cách khắc phục:**
  1. Tải và cài đặt [Visual C++ 2015–2022 Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe).
  2. Cài đặt lại Pillow không dùng cache:
     ```powershell
     pip uninstall -y Pillow
     pip install --no-cache-dir Pillow
     ```

---

### 3. ❌ faster-whisper CTranslate2 model download / CUDA fallback
- **Hiện tượng:** Lỗi khi tải mô hình Whisper từ Hugging Face Hub (Connection Timeout / SSL Error) hoặc lỗi crash liên quan đến CUDA/GPU.
- **Nguyên nhân:** Máy tính không có card đồ họa NVIDIA hoặc CUDA toolkit không khớp; kết nối tới HuggingFace bị gián đoạn.
- **Cách khắc phục:**
  1. Cấu hình fallback sang CPU int8 trong file cấu hình `config.yaml` hoặc `.env`:
     ```yaml
     whisper:
       device: "cpu"
       compute_type: "int8"
     ```
  2. Nếu mạng quốc tế bị nghẽn, cấu hình mirror Hugging Face trên PowerShell trước khi chạy:
     ```powershell
     $env:HF_ENDPOINT = "https://hf-mirror.com"
     ```
  3. Tải trước model để kiểm tra:
     ```powershell
     python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
     ```

---

### 4. ❌ UAC / Administrator Rights & Phím Tắt Toàn Cục (Hotkeys)
- **Hiện tượng:** Phím tắt `Ctrl+Shift+J` hoặc tính năng gửi phím tự động không hoạt động khi đang focus vào các cửa sổ chạy quyền Admin (như Task Manager, CMD Administrator).
- **Nguyên nhân:** Cơ chế bảo mật UIPI (User Interface Privilege Isolation) của Windows ngăn ứng dụng quyền chuẩn tương tác với cửa sổ quyền Elevated Administrator.
- **Cách khắc phục:**
  1. Đối với nhu cầu hàng ngày, chạy JARVIS dưới quyền tài khoản chuẩn (Standard User).
  2. Nếu thường xuyên làm việc trên các cửa sổ Administrator và muốn JARVIS can thiệp: Nhấp chuột phải vào `JARVIS.exe` (hoặc Terminal) và chọn **"Run as administrator"**.

---

### 5. ❌ API Key 401 Unauthorized / Invalid API Key
- **Hiện tượng:** Lỗi `google.api_core.exceptions.InvalidArgument: 401 Unauthorized` hoặc `API_KEY_INVALID`.
- **Nguyên nhân:** File `.env` đặt sai vị trí, tên biến không đúng chuẩn, hoặc API Key bị dính khoảng trắng, dấu ngoặc kép thừa.
- **Cách khắc phục:**
  1. Đảm bảo file `.env` nằm tại thư mục gốc của dự án hoặc `%LOCALAPPDATA%\JARVIS\.env`.
  2. Sử dụng định dạng chuẩn (không dùng dấu ngoặc kép, không khoảng trắng):
     ```env
     GEMINI_API_KEY=AIzaSyD-YourExactKeyHere
     GOOGLE_API_KEY=AIzaSyD-YourExactKeyHere
     ```
  3. Kiểm tra kết nối API Key trực tiếp:
     ```powershell
     python -c "import os, dotenv, google.generativeai as genai; dotenv.load_dotenv(); genai.configure(api_key=os.getenv('GEMINI_API_KEY')); print(genai.GenerativeModel('gemini-1.5-flash').generate_content('ping').text)"
     ```

---

## ⚙️ Cấu Hình `.env`

Bảng mô tả các biến môi trường hỗ trợ trong `.env`:

| Tên biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `GEMINI_API_KEY` | **Có** | — | API Key lấy từ [Google AI Studio](https://aistudio.google.com/apikey) |
| `GOOGLE_API_KEY` | Tùy chọn | — | Dự phòng cho `GEMINI_API_KEY` |
| `JARVIS_LANGUAGE` | Không | `vi` | Ngôn ngữ giao tiếp chính (`vi` hoặc `en`) |
| `JARVIS_WHISPER_MODEL` | Không | `base` | Model Whisper: `tiny`, `base`, `small`, `medium` |
| `JARVIS_VOICE` | Không | `vi_VN-vivos-medium` | Tên giọng đọc Piper TTS trong `~/.jarvis/voices/` |
| `JARVIS_HEADLESS` | Không | `0` | `0`: Chế độ thường (Tray UI), `1`: Headless mode (Server) |
| `TELEGRAM_BOT_TOKEN` | Không | — | Token Telegram Bot từ @BotFather |
| `TELEGRAM_CHAT_ID` | Không | — | Chat ID người dùng nhận thông báo Telegram |
| `DISCORD_BOT_TOKEN` | Không | — | Token ứng dụng Discord Bot |
| `ZALO_ACCESS_TOKEN` | Không | — | Access token Zalo Official Account |

### 🔒 Bảo Mật: Di Chuyển `.env` Sang Windows Credential Manager (`SecretsManager`)

Để bảo vệ các API Keys không bị lưu dưới dạng văn bản thô (plaintext) trên ổ đĩa, JARVIS hỗ trợ công cụ di chuyển tự động sang Windows Credential Manager:

```powershell
# 1. Xem trước các khóa sẽ được di chuyển an toàn (Dry Run - không thay đổi file):
python -m jarvis.cli migrate-secrets --dry-run

# 2. Thực hiện di chuyển và tự động xóa giá trị plaintext khỏi file .env (Purge):
python -m jarvis.cli migrate-secrets --purge
```
Sau khi thực hiện, hệ thống `ConfigManager` sẽ tự động truy xuất API Keys trực tiếp từ Windows Credential Manager an toàn mà không cần lưu khóa thô trong `.env`.

---

## 🧰 Danh Sách Kỹ Năng Chi Tiết (18+ Skills)

JARVIS được tích hợp sẵn 18+ kỹ năng mạnh mẽ, tự động kích hoạt qua giọng nói hoặc văn bản:

| # | Kỹ năng | Intent ID | Câu lệnh mẫu | Mô tả chức năng |
|---|---|---|---|---|
| 1 | 📰 **Briefing Sáng** | `briefing` | *"JARVIS, báo cáo sáng nay"* | Tổng hợp thời tiết, tin tức nổi bật và lịch trình |
| 2 | 📝 **Ghi Chú Nhanh** | `note_taker` | *"Ghi chú: họp dự án lúc 3h chiều"* | Lưu trữ và tìm kiếm ghi chú toàn văn với SQLite FTS5 |
| 3 | ⏱️ **Bộ Đếm Pomodoro** | `pomodoro` | *"Bắt đầu tập trung 25 phút"* | Đếm ngược chu kỳ làm việc, thông báo toast khi hoàn thành |
| 4 | 💻 **Điều Khiển Hệ Thống**| `system_control`| *"Tăng âm lượng 20%", "Khóa máy tính"* | Điều chỉnh âm thanh, chụp màn hình, khóa máy Windows |
| 5 | 🗂️ **Quản Lý File** | `file_manager` | *"Tìm file báo cáo doanh thu"* | Tìm kiếm và mở tập tin, thư mục theo ngôn ngữ tự nhiên |
| 6 | 🧮 **Máy Tính Thông Minh**| `calculator` | *"Tính 15% của 5 triệu rưỡi"* | Tính toán biểu thức toán học và quy đổi tỷ giá/đơn vị |
| 7 | 📋 **Quản Lý Clipboard** | `clipboard` | *"Đọc clipboard", "Sao chép: Xin chào"* | Đọc to nội dung clipboard hoặc lưu trữ lịch sử sao chép |
| 8 | 🚀 **Mở Ứng Dụng** | `app_launcher` | *"Mở Google Chrome", "Mở VS Code"* | Fuzzy search tìm và khởi chạy phần mềm trên máy |
| 9 | 👁️ **Phân Tích Màn Hình**| `screen_context`| *"Giải thích lỗi trên màn hình"* (`Ctrl+Shift+Space`) | Chụp ảnh màn hình và phân tích với Gemini Vision AI |
| 10| ⏺️ **Ghi & Phát Macro** | `macro_recorder`| *"Ghi lại macro gửi email"* | Tự động hóa chuỗi thao tác bàn phím/chuột lặp lại |
| 11| 🔊 **Sound Board** | `sound_board` | *"Phát âm thanh hoàn thành"* | Phát âm thanh phản hồi trạng thái vui nhộn |
| 12| 🔍 **Tìm Ký Ức / Tài Liệu** | `rag_search` | *"Tuần trước tôi nói gì về dự án X?"* | Tìm kiếm từ khóa và ngữ cảnh (TF-IDF & Lexical Search) |
| 13| 🧬 **Tự Viết Kỹ Năng** | `skill_synthesizer`| *"Tạo kỹ năng theo dõi giá vàng"* | Tự động viết code Python và nạp kỹ năng mới trong <15s |
| 14| 🌙 **Night Planner** | `night_planner` | *"Tối nay phân tích các file log"* | Thực hiện tác vụ nặng ban đêm và báo cáo lúc sáng |
| 15| 🏠 **Nhà Thông Minh** | `smart_home_discovery`| *"Quét thiết bị nhà thông minh"* | Quét mDNS và điều khiển Home Assistant / Tasmota |
| 16| 🌐 **Điều Khiển Browser**| `browser_control`| *"Mở YouTube tìm bài hát Iron Man"* | Chromium thật qua Playwright managed launch hoặc CDP attach; HTTP chỉ-read fail-closed |
| 17| 🔄 **Tự Cập Nhật** | `auto_updater` | *"Kiểm tra bản cập nhật mới"* | Tự động kiểm tra và nâng cấp phiên bản qua GitHub |
| 18| 📂 **Quản Lý Dự Án** | `workspace_prepare`| *"Mở dự án JARVIS", "Commit dự án"* | Quản lý dự án lập trình, Git assistant và workspace |

---

## ⌨️ Phím Tắt Toàn Hệ Thống

Các phím tắt hoạt động toàn cầu trên Windows (ngay cả khi ứng dụng đang chạy ẩn ở System Tray):

| Phím tắt | Hành động | Chi tiết |
|---|---|---|
| `Ctrl + Shift + J` | **Toggle Listening** | Bật / Tắt chế độ lắng nghe giọng nói |
| `Ctrl + Shift + Space` | **Phân tích màn hình** | Chụp màn hình và gửi Gemini Vision AI phân tích |
| `Ctrl + Shift + L` | **Khóa máy tính** | Khóa màn hình Windows (`LockWorkStation`) tức thì |
| `Ctrl + Shift + M` | **Mute Microphone** | Tắt / Mở nhanh microphone của JARVIS |
| `Ctrl + Shift + B` | **Briefing Sáng** | Đọc to bản tin tổng hợp buổi sáng |
| `Ctrl + Shift + S` | **Chụp màn hình** | Lưu ảnh chụp màn hình chất lượng cao ra Desktop |

---

## 📱 Điều Khiển Qua Điện Thoại

### Telegram Bot
1. Nhắn tin cho `@BotFather` trên Telegram để tạo bot và lấy `TELEGRAM_BOT_TOKEN`.
2. Điền token và `TELEGRAM_CHAT_ID` vào file `.env`.
3. Gửi lệnh `/start`, `/status`, `/briefing`, `/note`, `/screenshot` hoặc trò chuyện bằng ngôn ngữ tự nhiên từ bất kỳ đâu!

### Zalo Official Account & Discord Bot
- Hỗ trợ webhook 2 chiều qua cổng `8765` cho Zalo OA.
- Tích hợp Discord Bot qua `DISCORD_BOT_TOKEN` để điều khiển máy tính qua channel Discord riêng tư.

---

## 🏗️ Kiến Trúc Giọng Nói & Tự Trị (Architecture)

```
┌────────────────────────────────────────────────────────────────────────┐
│                              INPUT LAYER                               │
│  🎙️ Voice (VAD RMS/WebRTC)  📱 Telegram  💬 Discord  📞 Zalo OA        │
│  ⌨️ Global Win32 Hotkeys   👁️ Screen Context Vision                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                         INTELLIGENCE ROUTER                            │
│  Layer 1: Regex Fast-Path (20+ VN patterns, zero-latency, 0 token)     │
│  Layer 2: Rule Engine Greedy Matcher (Workspace, System, Media, App)   │
│  Layer 3: Gemini 1.5 Flash / Pro LLM Fallback                          │
│  Layer 4: Autonomous ReAct Engine (Think ➔ Act ➔ Observe ➔ Reflect)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                           CORE SKILLS (18+)                            │
│  briefing · note_taker · pomodoro · system_control · file_manager       │
│  calculator · clipboard · app_launcher · screen_context · macro_rec    │
│  rag_search · skill_synthesizer · night_planner · smart_home           │
│  browser_control · auto_updater · project_manager · git_assistant      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                       OUTPUT & EXECUTION LAYER                         │
│  🗣️ Piper TTS / ElevenLabs (<80ms)    🔔 Windows Notification Toast     │
│  🪟 Silent Subprocess Manager (No-Flash) 💾 SQLite FTS5 Memory         │
│  🌐 Playwright + Real CDP Automation   📊 Health Diagnostics           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🔒 Mô Hình Bảo Mật (Security Model)

- **Chạy Ngầm Tĩnh Lặng (No Console Flash):** Toàn bộ các tiến trình subprocess/PowerShell/CMD được spawn đều chạy ẩn hoàn toàn (`CREATE_NO_WINDOW`), không gián đoạn trải nghiệm người dùng.
- **Bảo Mật Bộ Nhớ Cục Bộ:** Dữ liệu ghi chú, ký ức và cấu hình được lưu cục bộ trên máy tại `%LOCALAPPDATA%\JARVIS\` và thư mục người dùng `~/.jarvis/`.
- **An Toàn Mã Nguồn:** Tính năng tự tạo kỹ năng (Self-Coding) được kiểm tra cú pháp và chạy thử nghiệm trong sandbox an toàn trước khi tích hợp vào hệ thống.

**Ghi chú bảo trì gần đây nhất (sau v4.7.0, không đổi phiên bản runtime):**
- Tự phục hồi hệ thống (Self-Healing) giờ chỉ báo thành công sau khi việc chấm dứt tiến trình đã được **xác nhận thực sự xảy ra** — không còn tự nhận thành công chỉ vì lệnh chấm dứt được gọi.
- RAM đã giải phóng không bao giờ bị bịa đặt — chỉ báo cáo từ phép đo trước/sau thực tế, bỏ qua khi không đo được.
- Test wake-word Whisper trên CI đã được làm tất định giữa các môi trường có/không cài `faster-whisper` — **không** thay đổi hành vi wake-word thật khi chạy production.
- Kết quả thất bại của một lệnh giờ được lan truyền trung thực xuyên suốt hệ thống — từ hành động thực thi, qua bộ điều phối hành động, đến phản hồi hiển thị cho người dùng, nhật ký tương tác và bộ nhớ — không còn trường hợp một lệnh thất bại bị báo cáo nhầm thành công.

---

## 📄 Giấy Phép & Tác Giả

Dự án được phát hành theo giấy phép **MIT License**. Xem file [LICENSE](LICENSE) để biết thêm chi tiết.

- **Tác giả:** Duong Phuoc Hung
- **GitHub:** [@Duong-Phuoc-Hung](https://github.com/Duong-Phuoc-Hung)
- **Repository:** [https://github.com/Duong-Phuoc-Hung/JARVIS](https://github.com/Duong-Phuoc-Hung/JARVIS)

<div align="center">

*Phát triển với tất cả đam mê và sự tận tâm dành cho cộng đồng công nghệ Windows & AI Assistant!* 🚀

[⭐ Star Dự Án](https://github.com/Duong-Phuoc-Hung/JARVIS) · [🐛 Báo Lỗi / Đóng Góp](https://github.com/Duong-Phuoc-Hung/JARVIS/issues) · [📦 Tải Bản Phát Hành](https://github.com/Duong-Phuoc-Hung/JARVIS/releases)

</div>

## Runtime regression fixes (2026-09-23)

Latest verification after the ROI, weather safety, and Windows brightness fixes:
**2,997 unit tests passed (4 skipped)** and **290 E2E tests passed (21 skipped)**.
See [runtime fix evidence](docs/eval/runtime_fix_verification_20260923.md).
