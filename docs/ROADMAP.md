# JARVIS Technical Roadmap & Codebase Audit (v4.6.0 – v5.0.0)

> **Tài liệu**: Lộ trình Phát triển Kỹ thuật & Báo cáo Kiểm toán Mã nguồn Toàn diện  
> **Dự án**: JARVIS — Vietnamese Voice AI Assistant for Windows 11  
> **Phiên bản tài liệu**: v4.6.0-CANONICAL  
> **Ngày phát hành**: 2026-09-02  
> **Trạng thái**: Đã phê duyệt (Approved Baseline)

---

## Mục lục (Table of Contents)
1. [Tổng quan Kiến trúc & Bối cảnh (Executive Architecture & Context)](#tổng-quan-kiến-trúc--bối-cảnh)
2. [Phần A — Phân loại trạng thái hiện tại (Part A: Current State Classification)](#phần-a--phân-loại-trạng-thái-hiện-tại-part-a-current-state-classification)
   - [A.1. Bảng phân loại module toàn diện (Comprehensive Module Inventory)](#a1-bảng-phân-loại-module-toàn-diện)
   - [A.2. Kiểm kê Stubs, Placeholders & NotImplementedError (Stubs Inventory)](#a2-kiểm-kê-stubs-placeholders--notimplementederror)
   - [A.3. Kiểm kê Dependencies còn thiếu & Đánh giá tác động (Missing Dependencies & Impact)](#a3-kiểm-kê-dependencies-còn-thiếu--đánh-giá-tác-động)
3. [Phần B — Backlog ưu tiên kỹ thuật P0–P3 (Part B: Prioritized Technical Backlog)](#phần-b--backlog-ưu-tiên-kỹ-thuật-p0p3-part-b-prioritized-technical-backlog)
   - [🔴 Nhóm P0: Critical Subsystems & Blocking Fixes](#-nhóm-p0-critical-subsystems--blocking-fixes)
   - [🟠 Nhóm P1: High UX, Acoustic & Performance Hardening](#-nhóm-p1-high-ux-acoustic--performance-hardening)
   - [🟡 Nhóm P2: Medium Multimodal Intelligence & Integrations](#-nhóm-p2-medium-multimodal-intelligence--integrations)
   - [🟢 Nhóm P3: Low Polish, Packaging & Enterprise Tooling](#-nhóm-p3-low-polish-packaging--enterprise-tooling)
4. [Phần C — Kế hoạch theo giai đoạn Sprints 1–4 (Part C: Phased Sprint Plan)](#phần-c--kế-hoạch-theo-giai-đoạn-sprints-14-part-c-phased-sprint-plan)
   - [Sprint 1 (Tuần 1–2 / v4.6.0): P0 Criticals & Zero-Crash Baseline](#sprint-1-tuần-12--v460-p0-criticals--zero-crash-baseline)
   - [Sprint 2 (Tuần 3–6 / v4.7.0): Accuracy, Acoustic & UX Hardening](#sprint-2-tuần-36--v470-accuracy-acoustic--ux-hardening)
   - [Sprint 3 (Tháng 2–3 / v4.8.0): Multimodal Feature Completion](#sprint-3-tháng-23--v480-multimodal-feature-completion)
   - [Sprint 4 (Tháng 4+ / v5.0.0): Enterprise Polish, Benchmarks & Distribution](#sprint-4-tháng-4--v500-enterprise-polish-benchmarks--distribution)
5. [Ma trận Truy xuất Nguồn gốc & Kiểm thử (Traceability & Verification Matrix)](#ma-trận-truy-xuất-nguồn-gốc--kiểm-thử)

---

## Tổng quan Kiến trúc & Bối cảnh

JARVIS là Trợ lý Ảo bằng giọng nói tiếng Việt chuyên biệt dành cho hệ điều hành Windows 11, vận hành theo mô hình **Zero-Cloud Dependency** (ưu tiên xử lý cục bộ 100% offline với khả năng tăng cường linh hoạt qua đám mây khi có kết nối).

### Bối cảnh Phát triển (v4.2.0 – v4.5.0)
Trong các bản phát hành trước, JARVIS đã hoàn thành nhiều cột mốc quan trọng về bảo mật và độ ổn định hệ thống:
- **v4.5.0**: Khắc phục hiện tượng Echo feedback loop (E9) với cooldown tăng từ 1.0s lên 2.5s; tích hợp `SecretsManager` qua Windows Credential Manager cho 6 module chính; đưa test suite về 0 failures.
- **v4.4.0**: Xử lý encoding subprocess trên 23 vị trí kèm wrapper `run_safe()` và cờ `CREATE_NO_WINDOW`; khắc phục lỗi crash khi `parse_intent(None)`; bổ sung bộ lọc Spectral Flatness Measure (SFM < 0.03) loại bỏ kích hoạt giả wake word bởi âm thuần.
- **v4.3.0 & v4.2.0**: Cách ly tiến trình Windows AppContainer B2 và Low Integrity MIC; bảo mật email IMAP 5 lớp; phòng chống injection và sandbox escape.

### Mục tiêu Cốt lõi v4.6.0
Bản phát hành v4.6.0 tập trung giải quyết dứt điểm các điểm nghẽn kỹ thuật nghiêm trọng (P0 Critical) phát hiện qua kiểm toán thực nghiệm:
1. **Audio & Wake Word Subsystem**: Tích hợp mô hình offline Vosk tiếng Việt (`vosk-model-small-vn-0.4`) kết hợp sliding-window Faster-Whisper fallback.
2. **Proactive Intelligence Subsystem**: Hoàn thiện cầu nối worker `jarvis/workers/proactive.py` với `ProactiveEngine`, lịch nhắc nhở, cảnh báo ngưỡng phần cứng (CPU/RAM/Nhiệt độ) và đồng hồ Pomodoro.
3. **LLM Routing Subsystem**: Mở rộng tập quy tắc Tier-1 Fast-Path regex giảm tỷ lệ `SILENT_FAILURE` từ 64.8% xuống $\le 40\%$, đồng thời kiểm chứng đường ống fallback Tier-2 LLM Tool Calling qua OpenAI API.
4. **Testing & Release**: Duy trì 100% tỷ lệ pass trên toàn bộ test suite (0 failures).

---

## Phần A — Phân loại trạng thái hiện tại (Part A: Current State Classification)

### A.1. Bảng phân loại module toàn diện

Toàn bộ 28 gói module (subpackages) và hơn 170 tệp mã nguồn Python trong cây thư mục `jarvis/` được kiểm toán chi tiết và phân loại theo 3 trạng thái:
- `✅ Done` (Hoàn thành): Module đã hoàn chỉnh logic nghiệp vụ, có kiểm thử tự động, hoạt động ổn định trong môi trường production.
- `🟡 Partial` (Một phần): Module cơ bản hoàn chỉnh nhưng thiếu thư viện C/ML tùy chọn (optional dependencies) hoặc cần mở rộng quy tắc ngữ pháp / dữ liệu huấn luyện.
- `❌ Missing/Stub` (Thiếu / Stub): Module chưa có tệp triển khai thực tế hoặc chứa các thành phần facade cần thay thế.

| Sub-Package / Module | Trạng thái (Status) | Số tệp / LOC (ước tính) | Chức năng Kỹ thuật Cốt lõi | Ghi chú Ràng buộc & Suy giảm tính năng |
|---|:---:|---|---|---|
| **Root Entrypoints** (`cli.py`, `__main__.py`, `__init__.py`) | `✅ Done` | 3 files / ~600 LOC | CLI argument parsing, entrypoint execution, version metadata (`v4.6.0`) | Không có |
| **`jarvis/agent/`** | `✅ Done` | 3 files / ~800 LOC | Vòng lặp tự trị ReAct (`Think→Act→Observe→Reflect`), `ToolExecutionResult`, cách ly Sandbox | Hỗ trợ fallback ReAct độc lập không bắt buộc `langgraph` |
| **`jarvis/audio/`** | `🟡 Partial` | 7 files / ~2,800 LOC | Luồng âm thanh full-duplex, AEC, RMS/spectral DSP, VAD segmenter, Wake Word đa tầng | Thiếu `vosk` trong venv (chạy Tier 2 Acoustic Fallback); cần xử lý trong P0-A |
| **`jarvis/automation/`** | `✅ Done` | 7 files / ~2,200 LOC | Giả lập đầu vào OS, GUI actor, cổng duyệt an toàn SafetyGate, Shell assistant, Windows AppContainer | Bắt buộc thực thi với cờ `CREATE_NO_WINDOW` |
| **`jarvis/browser/`** | `🟡 Partial` | 8 files / ~2,400 LOC | Trình điều khiển đa tầng (CDP driver, Playwright driver, Mock driver), quản lý phiên web | `playwright` chưa cài; fallback sang CDP WebSocket driver và Scraper |
| **`jarvis/comms/`** | `✅ Done` | 7 files / ~1,800 LOC | Bot Telegram, Email IMAP bảo mật 5 lớp, Discord bot, Zalo webhook controller, rate limiter | Yêu cầu cấu hình API Token qua SecretsManager khi kích hoạt |
| **`jarvis/core/`** | `✅ Done` | 8 files / ~3,800 LOC | `JarvisApp` trung tâm điều phối, vòng lặp thoại voice loop, `ActionDispatcher`, logging đa luồng | Đã fix E9 Echo Loop & SecretsManager; tích hợp `HardwareReporter` |
| **`jarvis/data/`** | `✅ Done` | 4 files / ~900 LOC | Trích xuất và phân tích tài liệu (PDF, DOCX, TXT, Markdown), phân tích thống kê bảng biểu | Không có |
| **`jarvis/gesture/`** | `🟡 Partial` | 7 files / ~1,600 LOC | Nhận diện tiếng vỗ tay âm học (Acoustic clap), theo dõi cử chỉ bàn tay qua camera | Nhận diện vỗ tay `✅ Done`; camera cử chỉ thiếu `cv2`/`mediapipe` |
| **`jarvis/hardware/`** | `✅ Done` | 3 files / ~1,100 LOC | Thu thập vi cơ CPU, RAM, GPU, Nhiệt độ, Disk S.M.A.R.T. qua ctypes Win32 & CIM | Đầy đủ fallback cho môi trường không có cảm biến GPU |
| **`jarvis/healing/`** | `✅ Done` | 2 files / ~800 LOC | Bộ tự phục hồi (Self-Healing), khởi động lại tiến trình lỗi, dọn dẹp RAM rò rỉ | Không có |
| **`jarvis/llm/`** | `🟡 Partial` | 3 files / ~3,200 LOC | Bộ định tuyến ý định 2 tầng (`LLMIntentRouter`), regex engine, tạo dynamic tool schema | Tier-1 thiếu rule (28.8% baseline); cần mở rộng quy tắc trong P0-D |
| **`jarvis/memory/`** | `✅ Done` | 2 files / ~1,400 LOC | Bộ nhớ dài hạn SQLite WAL (`logs/memory.db`), tổng kết ngày, truy hồi sự kiện TF-IDF | Đảm bảo tính an toàn đa luồng |
| **`jarvis/planner/`** | `✅ Done` | 6 files / ~1,900 LOC | Lập kế hoạch đồ thị phụ thuộc DAG, engine thực thi sóng song song, tự suy ngẫm lỗi | Hỗ trợ nội suy biến động `{{steps.node.output}}` |
| **`jarvis/platform/`** | `✅ Done` | 4 files / ~1,200 LOC | Win32 API native helpers, DPI awareness, đăng ký Windows Autostart Registry | Không có |
| **`jarvis/plugins/`** | `✅ Done` | 7 files / ~900 LOC | Trình nạp plugin động (Spotify, Cursor, Chrome, Shell, System, Webhooks) | Đạt chuẩn kiến trúc mở rộng |
| **`jarvis/proactive/`** | `✅ Done` | 7 files / ~2,100 LOC | Lập lịch nhắc nhở, Pomodoro focus timer, giám sát phần cứng chủ động, daily briefing | Đầy đủ unit tests (100% pass) |
| **`jarvis/sandbox/`** | `✅ Done` | 5 files / ~2,800 LOC | Cách ly Windows Job Objects, AppContainer SID, Low Integrity token, AST sanitizer | Có platform guard chuẩn cho Windows |
| **`jarvis/security/`** | `✅ Done` | 5 files / ~1,700 LOC | Phát hiện prompt injection, quét bảo mật, quản lý bí mật `SecretsManager` | Tích hợp sâu Windows Credential Manager |
| **`jarvis/skills/`** | `✅ Done` | 25 files / ~4,500 LOC | 19 kỹ năng tích hợp sẵn + Bộ tự tổng hợp mã nguồn (Self-Coding Skill Synthesizer) | Không có |
| **`jarvis/smart_home/`** | `✅ Done` | 4 files / ~800 LOC | Khách hàng Home Assistant REST/WS API, MQTT client, khám phá thiết bị mDNS | Không có |
| **`jarvis/stt/`** | `✅ Done` | 3 files / ~1,500 LOC | Faster-Whisper CT2 cục bộ (CUDA/CPU), OpenAI Whisper API, Windows SAPI, VAD buffer | `faster-whisper` (1.2.1) đã cài sẵn và hoạt động |
| **`jarvis/tts/`** | `✅ Done` | 8 files / ~1,400 LOC | ElevenLabs cloud TTS, SAPI5 offline fallback, bộ đệm đĩa SHA-256, voice manager | `elevenlabs` (2.64.0) đã cài sẵn; SAPI5 offline an toàn |
| **`jarvis/ui/`** | `✅ Done` | 4 files / ~2,400 LOC | Giao diện Web Dashboard (FastAPI/WS), Floating HUD Overlay (Tkinter/Win32), Tray | Hỗ trợ headless mode cho CI test suite |
| **`jarvis/utils/`** | `✅ Done` | 2 files / ~200 LOC | Trình bao bọc an toàn `run_safe()` với cờ ngăn cửa sổ cmd bật lên | Chuẩn hóa UTF-8 subprocess |
| **`jarvis/vision/`** | `🟡 Partial` | 8 files / ~2,500 LOC | Chụp ảnh màn hình `mss`, Vision LLM (Gemini/GPT-4o), OCR, thanh tra cửa sổ Win32 | `cv2`/`face_recognition` thiếu; fallback mss/Vision LLM |
| **`jarvis/web/`** | `✅ Done` | 7 files / ~1,900 LOC | Tìm kiếm web đa nguồn (DuckDuckGo), tỷ giá tài chính/crypto, thời tiết, RSS tin tức | Có bộ đệm đĩa TTL 10 phút |
| **`jarvis/workers/`** | `✅ Done` | 8 files / ~2,100 LOC | Quản lý luồng tiến trình nền, SubAgentManager, Night Shift worker, NotificationHub | Cần bổ sung shim `proactive.py` (P0-B) |

---

### A.2. Kiểm kê Stubs, Placeholders & NotImplementedError

Kiểm toán cú pháp tĩnh AST (Abstract Syntax Tree) và regex trên toàn bộ kho lưu trữ khẳng định mã nguồn JARVIS **không chứa các hàm rỗng giả mạo hay facade lừa đảo**. Các đánh dấu vị trí kỹ thuật đều phục vụ mục đích cấu trúc rõ ràng:

| # | Phân loại | Vị trí Tệp & Dòng | Định danh / Hàm | Hành vi Hiện tại trong Codebase | Hướng Khắc phục & Chuẩn hóa Production |
|---|---|---|---|---|---|
| 1 | `# TODO` | `jarvis/skills/skill_synthesizer/__init__.py:100` | `SkillSynthesizer._generate_skill_code` | Comment vị trí mẫu trong chuỗi template Python khi sinh mã kỹ năng động. | Thay thế bằng khối xử lý mặc định ghi log cấu trúc JSON và kích hoạt fallback dispatcher. |
| 2 | `raise NotImplementedError` | `jarvis/sandbox/security.py:513` | `run_in_restricted_token_with_job` | Bảo vệ nền tảng: Báo lỗi nếu chạy ngoài Windows (`sys.platform != "win32"`). | Đây là thiết kế bảo mật Windows native chuẩn. Giữ nguyên guard và ghi chú tài liệu. |
| 3 | `raise NotImplementedError` | `jarvis/sandbox/security.py:948` | `run_in_appcontainer_with_job` | Bảo vệ nền tảng: Báo lỗi nếu chạy ngoài Windows đối với AppContainer isolation. | Giữ nguyên guard Windows NT AppContainer; hỗ trợ môi trường Windows 11. |
| 4 | Dummy `pass` Hook | `jarvis/comms/zalo.py:407` | `ZaloWebhookHandler.log_message` | Dùng `pass` để ngăn `BaseHTTPRequestHandler` in rác log stderr mặc định ra màn hình. | Chuyển hướng bản ghi sang `logger.debug(...)` để hỗ trợ quan sát khi cần chẩn đoán. |
| 5 | Dummy `pass` Hook | `jarvis/core/logger.py:301` | `LogContext.__exit__` | Dùng `pass` trong hàm thoát ngữ cảnh Context Manager chuẩn. | Giữ nguyên theo chuẩn cấu trúc Python Context Manager. |
| 6 | Dummy `pass` Hook | `jarvis/memory/sqlite_store.py:779` | `SQLiteMemoryStore.close` | Dùng `pass` với giải thích kiến trúc kết nối theo từng lệnh gọi độc lập. | Giữ nguyên; nếu áp dụng connection pooling trong tương lai sẽ dọn dẹp tại đây. |
| 7 | Missing Module Bridge | `jarvis/workers/proactive.py` | `ProactiveEngine` | Tệp chưa tồn tại trong `jarvis/workers/` (module thực tế nằm tại `jarvis/proactive/engine.py`). | Tạo `jarvis/workers/proactive.py` làm cầu nối tương thích re-export `ProactiveEngine` (P0-B). |
| 8 | Missing Dep Fallback | `jarvis/audio/wake_word.py:37` | `import vosk` fallback | Rơi vào `AcousticSpectralDetector` (dễ bị nhiễu phòng kích hoạt sai). | Cài đặt `vosk` và cấu hình mô hình tiếng Việt `vosk-model-small-vn-0.4` (P0-A). |
| 9 | Missing Dep Fallback | `jarvis/gesture/hand_tracker.py:41` | `import cv2, mediapipe` | Bắt `ImportError`, gán cờ `AVAILABLE=False` và tắt chức năng camera. | Giữ cơ chế suy giảm mềm (graceful degradation) cho gói tùy chọn `[gestures]`. |
| 10 | Missing Dep Fallback | `jarvis/vision/biometrics.py:39` | `import face_recognition` | Bắt `ImportError`, gán cờ `AVAILABLE=False` và vô hiệu hóa mở khóa khuôn mặt. | Giữ cơ chế suy giảm mềm cho gói tùy chọn xác thực sinh trắc học. |
| 11 | In-Code Test Double | `jarvis/browser/driver.py:855` | `MockBrowserDriver` | Trình duyệt giả lập trong bộ nhớ phục vụ chạy kiểm thử CI/CD độc lập không cần mạng. | Giữ nguyên phục vụ test isolation; production sử dụng `CDPBrowserDriver` hoặc `PlaywrightDriver`. |
| 12 | In-Code Test Double | `jarvis/stt/engine.py:726` | `MockSTTEngine` | Động cơ STT giả lập phục vụ kiểm thử đơn vị hồi quy không cần microphone vật lý. | Giữ nguyên phục vụ test suite; production sử dụng `FasterWhisperSTT` hoặc `WhisperAPISTT`. |

---

### A.3. Kiểm kê Dependencies còn thiếu & Đánh giá tác động

| Tên Thư viện (Dependency) | Nhóm Chức năng | Trạng thái trong `.venv` | Khai báo `pyproject.toml` | Module bị ảnh hưởng trong `jarvis/` | Cơ chế Fallback khi Thiếu & Tác động Thực tế | Mức độ Ưu tiên |
|---|---|:---:|:---:|---|---|:---:|
| **`vosk`** | Audio / Wake Word | ❌ Chưa cài | ❌ Chưa có | `jarvis/audio/wake_word.py` | Rơi về `AcousticSpectralDetector`. **Tác động**: Nhận diện wake word kém chính xác trong môi trường có tiếng ồn. | 🔴 **P0** |
| **`pvporcupine`** | Audio / Wake Word | ❌ Chưa cài | ✅ `[wakeword]` | `jarvis/audio/wake_word.py` | Bỏ qua Porcupine, chuyển sang Vosk hoặc Acoustic fallback. Không gây gián đoạn nếu có Vosk. | 🟡 **P2** |
| **`playwright`** | Browser Automation | ❌ Chưa cài | ✅ `[browser]` | `jarvis/browser/driver.py` | Fallback sang `CDPBrowserDriver` (Chrome DevTools Protocol) và HTTP WebScraper. | 🟠 **P1** |
| **`opencv-python` (`cv2`)** | Vision / Gestures | ❌ Chưa cài | ✅ `[gestures]` | `jarvis/gesture/hand_tracker.py`<br>`jarvis/vision/biometrics.py` | Bắt ngoại lệ và gán cờ `AVAILABLE=False`. Chức năng cử chỉ âm thanh (vỗ tay) vẫn hoạt động 100%. | 🟡 **P2** |
| **`mediapipe`** | Vision / Gestures | ❌ Chưa cài | ✅ `[gestures]` | `jarvis/gesture/hand_tracker.py` | Tắt nhận diện tọa độ khớp ngón tay camera. Không ảnh hưởng đến các luồng âm thanh và giọng nói. | 🟡 **P2** |
| **`face_recognition`** | Vision / Biometrics | ❌ Chưa cài | ❌ Chưa có | `jarvis/vision/biometrics.py` | Tắt tính năng nhận diện khuôn mặt tự động đăng nhập. Đăng nhập hệ thống dùng Windows PIN/Pass. | 🟡 **P2** |
| **`winotify`** | Notifications | ❌ Chưa cài | ✅ `[notifications]` | `jarvis/workers/notification_hub.py` | Fallback sang thông báo khay hệ thống Pystray và cửa sổ nổi HUD Tkinter. | 🟠 **P1** |
| **`matplotlib`** | Data / Charts | ❌ Chưa cài | ✅ `[charts]` | `jarvis/data/analysis_service.py` | Trả về bảng tóm tắt văn bản số liệu ASCII thay vì vẽ biểu đồ hình ảnh. | 🟢 **P3** |
| **`paho-mqtt`** | Smart Home IoT | ❌ Chưa cài | ❌ Chưa có | `jarvis/smart_home/mqtt.py` | Tắt kênh MQTT; điều khiển nhà thông minh vẫn hoạt động qua Home Assistant REST/WS API. | 🟡 **P2** |
| **`onnxruntime`** | Offline TTS Piper | ❌ Chưa cài | ❌ Chưa có | `jarvis/tts/piper.py` | Piper TTS offline đánh dấu không khả dụng; hệ thống fallback ngay lập tức sang Windows SAPI5 TTS. | 🟠 **P1** |

---

## Phần B — Backlog ưu tiên kỹ thuật P0–P3 (Part B: Prioritized Technical Backlog)

Định nghĩa phân loại mức độ ưu tiên:
- 🔴 **P0 Critical**: Lỗi nghiêm trọng chặn việc sử dụng thực tế — JARVIS không khởi động được, thiếu module lõi, hoặc định tuyến ý định giọng nói chính bị mất dấu.
- 🟠 **P1 High**: Trải nghiệm người dùng và độ chính xác chưa cao — hệ thống chạy được nhưng độ trễ lớn, dễ kích hoạt sai hoặc gây block phần cứng.
- 🟡 **P2 Medium**: Tính năng giá trị cao còn thiếu — bộ nhớ ngữ cảnh đa lượt, thị giác máy tính màn hình, tìm kiếm web thời gian thực, cầu nối IoT.
- 🟢 **P3 Low**: Hoàn thiện đóng gói — bộ cài đặt tự động Windows, bảng điều khiển web, công cụ đo benchmark và hỗ trợ song ngữ.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           BẢNG TỔNG HỢP BACKLOG 22 HẠNG MỤC                      │
├───────┬───────────────────────────────────┬──────────┬───────────────────────────┤
│ ID    │ Tên Hạng mục Tính năng            │ Ưu tiên  │ Module Tác động Chính     │
├───────┼───────────────────────────────────┼──────────┼───────────────────────────┤
│ P0-1  │ Production-Ready Wake Word Engine │ 🔴 P0    │ jarvis/audio/wake_word.py │
│ P0-2  │ ProactiveEngine Worker Bridge     │ 🔴 P0    │ jarvis/workers/proactive  │
│ P0-3  │ Tier-2 LLM Routing Pipeline       │ 🔴 P0    │ jarvis/llm/router.py      │
│ P0-4  │ Router Tier-1 Coverage Expansion  │ 🔴 P0    │ jarvis/llm/router.py      │
│ P0-5  │ Test Suite Zero-Failure Integrity │ 🔴 P0    │ tests/conftest.py, tests/ │
│ P1-6  │ Floating HUD Overlay & Async Loop │ 🟠 P1    │ jarvis/ui/overlay.py      │
│ P1-7  │ System Tray Dynamic Controls      │ 🟠 P1    │ jarvis/ui/tray.py         │
│ P1-8  │ Acoustic Transient Filter & DSP   │ 🟠 P1    │ jarvis/audio/dsp.py       │
│ P1-9  │ SAPI5 Fallback TTS COM Safety     │ 🟠 P1    │ jarvis/tts/fallback.py    │
│ P1-10 │ Faster-Whisper Preload & VAD Opt  │ 🟠 P1    │ jarvis/stt/engine.py      │
│ P1-11 │ Hardware Telemetry Voice Summary  │ 🟠 P1    │ jarvis/hardware/reporter  │
│ P2-12 │ Two-Layer Memory System (SQLite)  │ 🟡 P2    │ jarvis/memory/manager.py  │
│ P2-13 │ Screen Vision & Dialog Inspection │ 🟡 P2    │ jarvis/vision/screen.py   │
│ P2-14 │ Real-Time Web Intelligence Hub    │ 🟡 P2    │ jarvis/web/search.py      │
│ P2-15 │ Browser Automation Worker         │ 🟡 P2    │ jarvis/browser/controller │
│ P2-16 │ Telegram Bot Remote Channel       │ 🟡 P2    │ jarvis/comms/telegram_bot │
│ P2-17 │ Smart Home (Home Assistant) Bridge│ 🟡 P2    │ jarvis/smart_home/        │
│ P3-18 │ Windows One-Click Installer Setup │ 🟢 P3    │ scripts/install.ps1       │
│ P3-19 │ Realtime Web Telemetry Dashboard  │ 🟢 P3    │ jarvis/web/dashboard.py   │
│ P3-20 │ Automated Benchmark Harness Suite │ 🟢 P3    │ tests/eval/               │
│ P3-21 │ CLI System Pre-Flight Diagnostics │ 🟢 P3    │ jarvis/cli.py             │
│ P3-22 │ Bilingual Code-Switching Engine   │ 🟢 P3    │ jarvis/utils/vietnamese.py│
└───────┴───────────────────────────────────┴──────────┴───────────────────────────┘
```

---

### 🔴 Nhóm P0: Critical Subsystems & Blocking Fixes

#### Item P0-1: Production-Ready Offline Wake Word Detection Subsystem
- **Priority:** 🔴 P0 Critical
- **Tên tính năng:** Hệ thống Nhận diện Từ khóa Đánh thức Ngoại tuyến ("Hey JARVIS" / "JARVIS")
- **Mô tả kỹ thuật:**  
  Môi trường hiện tại thiếu `vosk`, khiến `WakeWordDetector` phải rơi xuống `AcousticSpectralDetector` (phân tích SFM/ZCR), vốn rất nhạy cảm với tạp âm và tiếng gõ phím trong môi trường thực tế. Hạng mục này tích hợp thư viện `vosk`, nạp mô hình tiếng Việt nhỏ gọn (`vosk-model-small-vn-0.4`), xây dựng cơ chế sliding-window Faster-Whisper keyword search dự phòng, loại bỏ hoàn toàn nguy cơ `ImportError`, và đảm bảo tỷ lệ phát hiện từ khóa qua microphone $\ge 70\%$ với độ trễ phản hồi $< 1.0\text{s}$.
- **Tệp liên quan & Line spans:**
  - `jarvis/audio/wake_word.py` (L1–L758)
  - `jarvis/audio/engine.py` (L50–L210)
  - `config/default_config.yaml` (L30–L45)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Thêm `vosk` vào môi trường ảo; thiết lập logic tự động quét thư mục mô hình tại `models/vosk-model-small-vn-0.4` hoặc `%LOCALAPPDATA%/JARVIS/models/vosk`.
  2. Trong `jarvis/audio/wake_word.py`, hoàn thiện lớp `VoskKeywordDetector` với danh sách ngữ pháp giới hạn: `["hey jarvis", "jarvis", "chào jarvis", "[unk]"]`.
  3. Xây dựng bộ đệm xoay vòng (ring buffer) hỗ trợ `FasterWhisperSTT` phát hiện từ khóa "jarvis" trong cửa sổ trượt 1.5s làm fallback thứ cấp khi chưa tải mô hình Vosk.
  4. Duy trì `AcousticSpectralDetector` làm phương án dự phòng cấp 3 cho môi trường test CI không có microphone hoặc thiết bị âm thanh.
  5. Cung cấp phương thức bật/tắt an toàn luồng (`set_enabled(bool)`) hỗ trợ điều khiển tức thì từ Khay hệ thống Windows Tray.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - Unit Test: `pytest tests/unit/test_wake_word.py -v`
  - Integration Test: Nạp khối dữ liệu âm thanh tổng hợp 44.1kHz chứa tín hiệu formant "hey jarvis" và xác nhận callback kích hoạt với `confidence >= 0.40`.
  - Negative Test: Nạp 5 giây âm thanh nhiễu trắng và vỗ tay đôi; xác nhận số lần kích hoạt giả bằng 0.

---

#### Item P0-2: ProactiveEngine Background Worker Daemon Architecture
- **Priority:** 🔴 P0 Critical
- **Tên tính năng:** Trình điều phối Chủ động Nền (`ProactiveEngine`) và Quản lý Tác vụ Định kỳ
- **Mô tả kỹ thuật:**  
  Tệp `jarvis/workers/proactive.py` hiện chưa tồn tại (trong khi `jarvis/core/app.py` và các plugin mở rộng có nhu cầu import trực tiếp từ đường dẫn này). Cần tạo tệp cầu nối `jarvis/workers/proactive.py` kết nối đầy đủ với `jarvis/proactive/engine.py`, tích hợp bộ lập lịch nhắc nhở (ReminderScheduler), giám sát ngưỡng phần cứng (HardwareAlertWatchdog: RAM > 90%, CPU > 95%, Nhiệt độ > 85°C), đồng hồ Pomodoro tập trung và đăng ký action `proactive_reminder` với `ActionDispatcher`.
- **Tệp liên quan & Line spans:**
  - `jarvis/workers/proactive.py` (Tệp mới, ~350 LOC)
  - `jarvis/workers/__init__.py`
  - `jarvis/core/app.py` (L60–L150, L680–L760)
  - `config/default_config.yaml` (L80–L110)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Tạo `jarvis/workers/proactive.py` xuất khẩu `ProactiveEngine`, `ReminderScheduler`, `HardwareAlertWatchdog`, và `PomodoroTimer`.
  2. Triển khai vòng lặp daemon với chu kỳ quét 1.0 giây kiểm tra hàng đợi nhắc nhở (lưu trữ JSON bền vững tại `data/reminders.json`).
  3. Tích hợp watchdog kiểm tra chỉ số `HardwareMonitor` mỗi 10 giây với cơ chế chống lặp cảnh báo (cooldown 120 giây giữa các lần thông báo cùng loại).
  4. Đăng ký các hành vi `proactive_reminder`, `focus_mode_start`, `focus_mode_cancel` vào `ActionDispatcher`.
  5. Liên kết vòng đời `ProactiveEngine.start()` và `ProactiveEngine.stop()` vào phương thức khởi tạo và hủy của `JarvisApp`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - Kiểm tra import không crash: `python -c "import jarvis.workers.proactive; from jarvis.workers.proactive import ProactiveEngine"`
  - Unit Test: `pytest tests/unit/test_proactive_engine.py -v` (đảm bảo toàn bộ $\ge 3$ test cases đạt trạng thái PASSED).
  - Giả lập RAM 95% và kiểm tra sự kiện `hardware.alert` được phát lên EventBus và phát âm thanh cảnh báo.

---

#### Item P0-3: Tier-2 LLM Semantic Routing Pipeline Verification & Live Wiring
- **Priority:** 🔴 P0 Critical
- **Tên tính năng:** Đường ống Phân tích Ý định Ngữ nghĩa Tầng 2 (Tier-2 LLM Tool Calling)
- **Mô tả kỹ thuật:**  
  Đo lường thực tế cho thấy 64.8% câu lệnh tự nhiên của người dùng không khớp tập luật tĩnh Tier-1 và rơi vào `SILENT_FAILURE`. Pipeline định tuyến LLM Tier-2 đã được định hình trong mã nguồn nhưng cần hoàn thiện kiểm chứng luồng `force_llm=False`. Khi Tier-1 miss, hệ thống tự động sinh JSON Schema công cụ động từ `ActionDispatcher`, gọi `LLMClient` (OpenAI/Gemini) và giải mã phản hồi cấu trúc thành `IntentResult(action_name=..., params=...)` thay vì trả về `generic_llm_response` hay `unknown_intent`.
- **Tệp liên quan & Line spans:**
  - `jarvis/llm/router.py` (L50–L180, L980–L1200)
  - `jarvis/llm/client.py` (L40–L320)
  - `jarvis/core/app.py` (L420–L510)
  - `jarvis/core/dispatcher.py` (L80–L150)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Xác thực hàm sinh schema `generate_tool_schema_from_dispatcher(self.dispatcher)` tương thích định dạng OpenAI Function Calling và Google Gemini Tools.
  2. Kết nối `SecretsManager` để nạp `OPENAI_API_KEY` hoặc `GEMINI_API_KEY` từ Windows Credential Manager vào `LLMClient`.
  3. Cập nhật `LLMIntentRouter.parse_intent()`: Khi Tier-1 không tìm thấy kết quả và `force_llm=False`, chuyển tiếp truy vấn sang LLM kèm danh sách công cụ hiện hữu.
  4. Trích xuất Function Call từ phản hồi LLM và ánh xạ chính xác vào `IntentResult(action_name=tool_name, parameters=tool_args, source="llm")`.
  5. Bổ sung ghi log chẩn đoán: `logger.info("Tier-2 LLM resolved tool call: %s -> %s", text, intent.action_name)`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - Unit Test: `pytest tests/unit/test_llm_router.py -k "test_tier2_tool_calling" -v`
  - Integration Test: Thực thi `router.parse_intent("đặt hẹn họp lúc 3 giờ chiều", force_llm=False)` với khóa API mock/live; xác nhận trả về `intent.action_name == "proactive_reminder"` hoặc action tương ứng (không phải `unknown_intent`).

---

#### Item P0-4: Router Tier-1 Fast-Path Coverage Expansion ($\ge 40-60$ Rules)
- **Priority:** 🔴 P0 Critical
- **Tên tính năng:** Mở rộng Tập Luật Tĩnh Tier-1 và Hỗ trợ Tiếng Việt Không Dấu
- **Mô tả kỹ thuật:**  
  Đánh giá thực nghiệm qua `tests/eval/routing_eval_n150.py` ghi nhận tỷ lệ `SILENT_FAILURE` lên đến 64.8% (99/152 câu bị bỏ lỡ). Nguyên nhân chính: 52.5% do đầu ra STT Faster-Whisper trả về dạng không dấu (`mo chrome`, `tat may tinh`), 18.2% do câu lệnh tắt tiếng Anh (`volume up`, `shut down`), và 29.3% do thiếu mẫu câu phổ biến về ghi nhớ, thời tiết, âm nhạc và quản lý hệ thống. Bổ sung $\ge 40-60$ quy tắc regex mới trong `jarvis/llm/router.py` nhằm kéo giảm `SILENT_FAILURE` xuống $\le 40.0\%$ (mục tiêu $< 15\%$) trong khi giữ vững tỷ lệ `MISROUTED = 0`.
- **Tệp liên quan & Line spans:**
  - `jarvis/llm/router.py` (L827–L980, L1200–L1650)
  - `tests/eval/routing_eval_n150.py` (L38–L280)
  - `tests/unit/test_llm_router.py`
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Bổ sung regex mở ứng dụng không dấu (`mo`, `bat`, `chay`, `khoi dong`) cho Chrome, Notepad, Word, Excel, Paint, Calculator, PowerPoint, Settings.
  2. Bổ sung regex truy cập website không dấu (`mo youtube`, `vao facebook`, `mo trang web tin tuc`).
  3. Bổ sung regex điều khiển nguồn hệ thống (`tat may tinh`, `tat nguon`, `shut down`, `stop`, `thoi`, `huy`, `cancel`, `khoi dong lai`, `restart`).
  4. Bổ sung regex âm lượng và màn hình (`tang am luong`, `giam am luong`, `tat tieng`, `mute`, `volume up/down`, `tat man hinh`, `screen off`).
  5. Bổ sung regex điều khiển phát nhạc (`mo nhac`, `phat nhac`, `play music`, `bat nhac len`, `spotify`).
  6. Bổ sung regex truy vấn thời tiết (`thoi tiet hom nay`, `du bao thoi tiet`, `troi hom nay`, `weather today`, `bao nhieu do`).
  7. Bổ sung regex ghi nhớ ghi chú (`ghi nho`, `save this`, `tom tat hom nay`, `nho la`).
  8. Bảo vệ chống ReDoS bằng cách giới hạn độ dài chuỗi đầu vào $\le 512$ ký tự và dùng word-boundary `\b`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - Chạy đánh giá toàn diện: `python tests/eval/routing_eval_n150.py` -> Xác nhận SILENT_FAILURE $\le 40.0\%$ và MISROUTED $= 0$.
  - Unit Test: `pytest tests/unit/test_llm_router.py -v` -> 0 failures.

---

#### Item P0-5: Test Suite Integrity & Zero-Failure Baseline Maintenance
- **Priority:** 🔴 P0 Critical
- **Tên tính năng:** Bảo vệ Toàn vẹn Test Suite và Duy trì Chuẩn 0 Lỗi Hồi quy
- **Mô tả kỹ thuật:**  
  Duy trì tiêu chuẩn nghiêm ngặt 0 test failure trên toàn bộ suite kiểm thử đơn vị và đối kháng (`pytest tests/ -q --ignore=tests/e2e`), chuẩn hóa các trường hợp thiếu thư viện tùy chọn qua `pytest.importorskip`, loại bỏ cảnh báo deprecation và đảm bảo tính tương thích môi trường Windows 11.
- **Tệp liên quan & Line spans:**
  - `tests/conftest.py` (L1–L1022)
  - `tests/unit/test_*.py`
  - `tests/test_adversarial_*.py`
  - `pytest.ini`
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Rà soát 51+ file test, bọc các thư viện tùy chọn (`cv2`, `mediapipe`, `vosk`) bằng `pytest.importorskip`.
  2. Chuẩn hóa mock fixtures cho thiết bị âm thanh, Win32 platform và HTTP server.
  3. Cấu hình cờ `asyncio_mode = auto` và timeout bảo vệ chống treo luồng trong `pytest.ini`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/ -q` (0 failures).
  - `pytest tests/test_adversarial_*.py -q` (0 failures).
  - `pytest tests/ -q --ignore=tests/e2e` (0 failures).

---

### 🟠 Nhóm P1: High UX, Acoustic & Performance Hardening

#### Item P1-6: Floating HUD Overlay UI & Non-Blocking Async Voice Loop
- **Priority:** 🟠 P1 High
- **Tên tính năng:** Giao diện Cửa sổ Nổi HUD và Tách biệt Luồng Thu âm Bất đồng bộ
- **Mô tả kỹ thuật:**  
  Tách biệt hoàn toàn luồng giao diện Tkinter HUD Overlay khỏi luồng thu âm giọng nói. Cung cấp hiệu ứng trạng thái mượt mà (`IDLE` -> `LISTENING` -> `THINKING` -> `SPEAKING`), bộ đếm tự ẩn thông minh, và loại bỏ việc gọi hàm `sounddevice.rec()` chặn đồng bộ 5.0 giây trong `_ai_voice_loop`.
- **Tệp liên quan & Line spans:**
  - `jarvis/ui/overlay.py` (L1–L450)
  - `jarvis/core/app.py` (L330–L420)
  - `jarvis/audio/engine.py` (L100–L180)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Đảm bảo `JarvisOverlay` chạy trên luồng Tkinter riêng biệt với hàng đợi sự kiện an toàn luồng.
  2. Bổ sung phương thức `JarvisApp.record_audio(duration_s, sample_rate)` cho phép trả về bộ đệm giả lập trong chế độ `headless` hoặc kiểm thử tự động.
  3. Hợp nhất luồng xử lý câu lệnh văn bản qua `process_text_command(transcript, requester="voice")`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/test_m3_ux.py -v`
  - `pytest tests/test_adversarial_m3_ui_app.py -v`

---

#### Item P1-7: Windows System Tray Controller Dynamic Toggle & Telemetry Sync
- **Priority:** 🟠 P1 High
- **Tên tính năng:** Điều khiển Khay Hệ thống Động và Đồng bộ Trạng thái Thời gian thực
- **Mô tả kỹ thuật:**  
  Nâng cấp `SystemTrayController` với menu ngữ cảnh động (bật/tắt nhanh Wake Word, cử chỉ vỗ tay, chế độ không làm phiền DND) không cần khởi động lại ứng dụng, đồng thời cập nhật biểu tượng trạng thái trực quan (Rảnh rỗi, Đang nghe, Đang xử lý, Lỗi).
- **Tệp liên quan & Line spans:**
  - `jarvis/ui/tray.py` (L1–L380)
  - `jarvis/core/app.py` (L200–L260)
  - `jarvis/core/events.py`
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Triển khai các hàm callback menu `_on_toggle_wakeword` và `_on_toggle_gestures` trong `pystray.Menu`.
  2. Lắng nghe sự kiện từ `EventBus` (`voice.listening`, `voice.thinking`) để đổi icon khay hệ thống tương ứng.
  3. Cung cấp cơ chế fallback an toàn cho môi trường không có màn hình hoặc khay hệ thống.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_tray.py -v`
  - Kiểm tra gọi `tray_controller._on_toggle_wakeword()` cập nhật chính xác thuộc tính `wake_word_detector.is_enabled`.

---

#### Item P1-8: Acoustic Transient Filter & DSP Dynamic Noise Floor Hardening
- **Priority:** 🟠 P1 High
- **Tên tính năng:** Bộ Lọc Âm học DSP và Chống Kích hoạt Giả do Tiếng ồn
- **Mô tả kỹ thuật:**  
  Hoàn thiện thuật toán theo dõi ngưỡng ồn động Exponential Moving Average (EMA, `alpha = 0.992`) và tỷ số kích hoạt Schmitt Trigger trong `AudioDSPProcessor` nhằm triệt tiêu kích hoạt giả từ tiếng bàn phím cơ, tiếng click chuột và tiếng đóng cửa.
- **Tệp liên quan & Line spans:**
  - `jarvis/audio/dsp.py` (L1–L320)
  - `jarvis/gesture/detector.py` (L1–L410)
  - `config/default_config.yaml` (L50–L75)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Tích hợp bộ lọc Spectral Flatness Measure (SFM) và Zero Crossing Rate (ZCR) để loại bỏ âm đơn tần số và nhiễu trắng băng rộng.
  2. Ràng buộc mức năng lượng đỉnh tối thiểu so với đường cơ sở RMS rolling.
  3. Áp dụng thời gian trễ phục hồi (cooldown 2.5s) triệt tiêu hoàn toàn vòng lặp vọng âm (echo feedback loop).
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/test_audio_dsp.py -v`
  - `pytest tests/test_gesture_detector.py -v`

---

#### Item P1-9: SAPI5 Local TTS Fallback Thread Safety & COM Initialization
- **Priority:** 🟠 P1 High
- **Tên tính năng:** Động cơ TTS Cục bộ SAPI5 An toàn Luồng và Khởi tạo COM
- **Mô tả kỹ thuật:**  
  Đảm bảo khả năng tổng hợp giọng nói ngoại tuyến 100% ổn định khi ElevenLabs mất kết nối hoặc hết hạn mức API. Xử lý triệt để xung đột căn hộ luồng COM (`pythoncom.CoInitialize()`) khi gọi `SAPI.SpVoice` từ background worker, kèm fallback PowerShell Base64.
- **Tệp liên quan & Line spans:**
  - `jarvis/tts/fallback.py` (L1–L280)
  - `jarvis/tts/manager.py` (L1–L390)
  - `jarvis/tts/elevenlabs.py` (L1–L210)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Bao bọc khởi tạo SAPI5 trong khối `try ... pythoncom.CoInitialize()` và giải phóng `pythoncom.CoUninitialize()` khi hủy luồng.
  2. Bổ sung phương thức chạy script PowerShell ẩn định dạng Base64 khi không có `win32com`.
  3. Xây dựng kho câu chào hỏi luân phiên không lặp lại trong `TTSManager`.
  4. Duy trì bộ đệm tệp âm thanh SHA-256 (`.cache/jarvis_welcome/`) tránh tổng hợp lại các câu cố định.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/test_tts_engine.py -v`
  - `pytest tests/unit/test_tts_cache.py -v`

---

#### Item P1-10: Faster-Whisper Local STT Model Preloading & VAD Optimization
- **Priority:** 🟠 P1 High
- **Tên tính năng:** Tối ưu hóa Nạp trước Mô hình Faster-Whisper và Phân đoạn VAD
- **Mô tả kỹ thuật:**  
  Tối ưu hóa pipeline nhận diện giọng nói Faster-Whisper CT2 cục bộ để đạt thời gian chuyển đổi văn bản dưới 1 giây. Thực hiện nạp trước mô hình `small` / `base` trong luồng nền lúc khởi động, tích hợp bộ phân đoạn Silero/WebRTC VAD để cắt ngắn khoảng lặng đầu/cuối và tự động cấu hình GPU FP16 hoặc CPU INT8.
- **Tệp liên quan & Line spans:**
  - `jarvis/stt/engine.py` (L1–L450)
  - `jarvis/audio/vad.py` (L1–L250)
  - `config/default_config.yaml` (L20–L35)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Bổ sung routine làm ấm mô hình (model warming) trong background daemon thread khi khởi động ứng dụng.
  2. Cắt khung âm thanh ngay khi phát hiện khoảng lặng 0.8s thay vì chờ hết timeout 5.0s.
  3. Tự động phát hiện CUDA (`torch.cuda.is_available()`) để chọn `device="cuda"`, `compute_type="float16"` hoặc fallback `device="cpu"`, `compute_type="int8"`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_stt_engine.py -v`
  - Đo độ trễ xử lý mẫu âm thanh 3 giây ($\le 800\text{ms}$ trên GPU, $\le 1.8\text{s}$ trên CPU).

---

#### Item P1-11: Persistent Hardware Telemetry Watchdog & Voice Summary
- **Priority:** 🟠 P1 High
- **Tên tính năng:** Giám sát Phần cứng Liên tục và Đọc Báo cáo Bằng Giọng nói
- **Mô tả kỹ thuật:**  
  Mở rộng `HardwareMonitor` và `HardwareReporter` để thu thập dữ liệu tải CPU, RAM, GPU, trạng thái sạc pin và sức khỏe ổ cứng S.M.A.R.T. bằng thư viện Win32 ctypes thuần túy kết hợp CIM/WMI, hỗ trợ đọc báo cáo thông số trực tiếp khi người dùng gõ 3 tiếng vỗ tay hoặc ra lệnh giọng nói.
- **Tệp liên quan & Line spans:**
  - `jarvis/hardware/monitor.py` (L1–L380)
  - `jarvis/hardware/reporter.py` (L1–L220)
  - `jarvis/core/app.py` (L230–L245)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Triển khai các hàm Win32 API ctypes: `GlobalMemoryStatusEx` và `GetSystemTimes` lấy chỉ số CPU/RAM.
  2. Triển khai `GetSystemPowerStatus` lấy tỷ lệ pin và trạng thái cắm nguồn AC.
  3. Hoàn thiện hàm `format_voice_summary(lang="vi")` trả về chuỗi báo cáo ngắn gọn, tự nhiên.
  4. Nối `HardwareReporter` vào hàm xử lý `JarvisApp._handle_system_status()`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/test_hardware_monitor.py -v`
  - Gọi action `system_status` và xác nhận kết quả trả về chứa chỉ số CPU % và RAM % thực tế thay vì chuỗi mẫu cố định.

---

### 🟡 Nhóm P2: Medium Multimodal Intelligence & Integrations

#### Item P2-12: Two-Layer Stateful Memory System (Session Sliding Window & SQLite Store)
- **Priority:** 🟡 P2 Medium
- **Tên tính năng:** Hệ thống Bộ nhớ Ngữ cảnh Hai Tầng (Phiên làm việc & SQLite Dài hạn)
- **Mô tả kỹ thuật:**  
  Triển khai bộ nhớ ngữ cảnh 2 tầng: Bộ nhớ phiên làm việc trượt 10 lượt (`SessionContextManager`) phục vụ đối thoại liên tục, và cơ sở dữ liệu SQLite bền vững (`logs/memory.db` chế độ WAL) lưu trữ thông tin cá nhân, thói quen, nhật ký sự kiện và tổng kết hoạt động hàng ngày.
- **Tệp liên quan & Line spans:**
  - `jarvis/memory/manager.py` (Tệp mới, ~400 LOC)
  - `jarvis/memory/session.py` (Tệp mới, ~200 LOC)
  - `jarvis/memory/schema.sql` (Tệp mới, ~60 LOC)
  - `jarvis/llm/router.py` (L600–L750)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Tạo cấu trúc bảng SQLite: `facts`, `episodes`, `user_habits` với khóa chính và chỉ mục thời gian.
  2. Cung cấp các hàm CRUD an toàn đa luồng: `save_fact`, `get_fact`, `record_episode`, `summarize_day`.
  3. Tiêm các sự thật liên quan và lịch sử đối thoại gần nhất vào prompt hệ thống LLM.
  4. Đăng ký các action `memory_save_fact`, `memory_query_fact`, `memory_summarize_daily`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_memory_system.py -v`
  - Chạy stress-test 30 luồng đồng thời ghi/đọc dữ liệu không xảy ra lỗi `database is locked`.

---

#### Item P2-13: Screen Vision & Win32 Modal Dialog Visual Inspection
- **Priority:** 🟡 P2 Medium
- **Tên tính năng:** Thị giác Màn hình Mutilmodal và Thanh tra Hộp thoại Lỗi Win32
- **Mô tả kỹ thuật:**  
  Cung cấp khả năng hiểu nội dung màn hình máy tính (<100ms chụp ảnh, <3.0s suy luận) sử dụng `mss`, mô hình Vision LLM (Gemini 1.5 Flash / GPT-4o Vision), và bộ quét cửa sổ Win32 phát hiện hộp thoại lỗi modal `#32770` để hỗ trợ giải thích lỗi cho người dùng.
- **Tệp liên quan & Line spans:**
  - `jarvis/vision/screen.py` (Tệp mới, ~300 LOC)
  - `jarvis/vision/vision_client.py` (Tệp mới, ~250 LOC)
  - `jarvis/vision/dialog_detector.py` (Tệp mới, ~200 LOC)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Triển khai `ScreenCaptureManager` chụp màn hình chính hoặc cửa sổ kích hoạt, nén JPEG chất lượng 80.
  2. Triển khai `VisionLLMClient` hỗ trợ chuẩn Gemini `inlineData` Base64 và OpenAI `image_url`.
  3. Dùng Win32 `EnumWindows` phát hiện các dialog lỗi `#32770` và trích xuất nội dung thông báo.
  4. Đăng ký các action `screen_inspect`, `screen_explain_error`, `screen_summarize_doc`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_screen_vision.py -v`
  - Xác thực payload ảnh chụp gửi đi tuân thủ đúng schema của nhà cung cấp LLM.

---

#### Item P2-14: Real-Time Web Intelligence, Search & Financial Rates Hub
- **Priority:** 🟡 P2 Medium
- **Tên tính năng:** Trung tâm Thông tin Web Thời gian thực (Tìm kiếm, Thời tiết, Tin tức, Tỷ giá)
- **Mô tả kỹ thuật:**  
  Xây dựng hub tra cứu thông tin trực tuyến gồm DuckDuckGo search miễn phí, thời tiết OpenWeatherMap / wttr.in, RSS tin tức tiếng Việt (VnExpress, Tuổi Trẻ), tỷ giá ngoại tệ / crypto (USD/VND, BTC, ETH) với bộ nhớ đệm an toàn luồng TTL 10 phút.
- **Tệp liên quan & Line spans:**
  - `jarvis/web/search.py` (Tệp mới, ~220 LOC)
  - `jarvis/web/weather.py` (Tệp mới, ~200 LOC)
  - `jarvis/web/news.py` (Tệp mới, ~180 LOC)
  - `jarvis/web/finance.py` (Tệp mới, ~220 LOC)
  - `jarvis/web/cache.py` (Tệp mới, ~150 LOC)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Xây dựng `TTLCache` (TTL = 600s, `threading.RLock`, mã hóa SHA-256 truy vấn).
  2. Triển khai client tìm kiếm DuckDuckGo và tóm tắt kết quả qua LLM.
  3. Phân tích RSS feed tin tức bằng thư viện chuẩn `xml.etree.ElementTree`.
  4. Đăng ký các action `web_search`, `web_weather`, `web_news_briefing`, `web_crypto_rate`, `web_morning_briefing`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_web_intelligence.py -v`
  - Kiểm tra dữ liệu được lấy từ cache trong vòng 10 phút và xử lý timeout êm ái khi mất mạng.

---

#### Item P2-15: Browser Automation & Web Action Dispatching
- **Priority:** 🟡 P2 Medium
- **Tên tính năng:** Tự động hóa Trình duyệt Web (Playwright / CDP Controller)
- **Mô tả kỹ thuật:**  
  Tích hợp worker điều khiển trình duyệt Playwright Chromium headless/headful cho phép JARVIS thực thi các luồng công việc phức tạp trên web (tìm kiếm Google, tra cứu giá sản phẩm trên sàn TMĐT, trích xuất dữ liệu bảng biểu, chụp ảnh website).
- **Tệp liên quan & Line spans:**
  - `jarvis/browser/controller.py` (Tệp mới, ~320 LOC)
  - `jarvis/browser/actions.py` (Tệp mới, ~200 LOC)
  - `config/default_config.yaml`
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Xây dựng `BrowserController` quản lý phiên Chromium độc lập.
  2. Triển khai các thao tác điều hướng `navigate`, bấm nút `click`, điền biểu mẫu `type_text`, và trích xuất HTML.
  3. Áp dụng cơ chế sandbox giới hạn domain hợp lệ ngăn truy cập trang độc hại.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_browser_automation.py -v`

---

#### Item P2-16: Telegram & External Communication Bot Integration
- **Priority:** 🟡 P2 Medium
- **Tên tính năng:** Kênh Thông báo và Điều khiển Từ xa qua Telegram Bot
- **Mô tả kỹ thuật:**  
  Kết nối JARVIS với Telegram Bot API cho phép gửi thông báo chủ động từ xa (cảnh báo quá nhiệt phần cứng, hoàn thành tác vụ nền, nhắc nhở lịch hẹn) và tiếp nhận câu lệnh điều khiển từ xa có xác thực ID người dùng bảo mật.
- **Tệp liên quan & Line spans:**
  - `jarvis/comms/telegram_bot.py` (Tệp mới, ~280 LOC)
  - `jarvis/comms/notifier.py` (Tệp mới, ~150 LOC)
  - `config/default_config.yaml`
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Xây dựng `TelegramNotifier` gửi tin nhắn văn bản Markdown và file âm thanh qua REST API.
  2. Thiết lập cơ chế Long-Polling nhận lệnh từ xa với danh sách trắng `allowed_user_ids`.
  3. Kết nối cảnh báo từ `ProactiveEngine` để tự động đẩy thông báo về điện thoại người dùng.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_telegram_bot.py -v` (với mock HTTP endpoint).

---

#### Item P2-17: Smart Home & IoT Automation Bridge (Home Assistant Connector)
- **Priority:** 🟡 P2 Medium
- **Tên tính năng:** Cầu nối Điều khiển Nhà Thông minh IoT (Home Assistant Bridge)
- **Mô tả kỹ thuật:**  
  Cung cấp tích hợp 2 chiều với nền tảng Home Assistant qua REST API và WebSocket, cho phép bật/tắt đèn phòng, điều chỉnh nhiệt độ điều hòa, kích hoạt ngữ cảnh nhà thông minh bằng câu lệnh tiếng Việt tự nhiên.
- **Tệp liên quan & Line spans:**
  - `jarvis/smart_home/home_assistant.py` (Tệp mới, ~300 LOC)
  - `jarvis/llm/router.py`
  - `config/default_config.yaml`
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Triển khai `HomeAssistantClient` truy vấn trạng thái thực thể và gọi dịch vụ (`light.turn_on`, `climate.set_temperature`).
  2. Ánh xạ tên gọi tiếng Việt thân thiện ("đèn bàn làm việc" -> `light.desk_light`).
  3. Đăng ký các action `iot_light_control`, `iot_climate_control`, `iot_switch_control`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_home_assistant.py -v`

---

### 🟢 Nhóm P3: Low Polish, Packaging & Enterprise Tooling

#### Item P3-18: Windows One-Click Installer & Autostart Setup
- **Priority:** 🟢 P3 Low
- **Tên tính năng:** Bộ Cài đặt Tự động Một Chạm và Đăng ký Khởi động Cùng Windows
- **Mô tả kỹ thuật:**  
  Xây dựng kịch bản cài đặt tự động PowerShell (`scripts/install.ps1`) và công thức đóng gói EXE/MSI độc lập (qua PyInstaller / InnoSetup) tự động thiết lập môi trường ảo, tải mô hình offline và quản lý Registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- **Tệp liên quan & Line spans:**
  - `scripts/install.ps1`
  - `scripts/build_standalone.ps1`
  - `jarvis/cli.py` (L140–L190)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Viết `scripts/install.ps1` kiểm tra Python 3.10+, Visual C++ Redistributable, PortAudio và tự động tải mô hình Vosk/Whisper.
  2. Thêm các lệnh CLI `install-autostart`, `uninstall-autostart`, `autostart-status`.
  3. Tạo shortcut màn hình Desktop và Start Menu với biểu tượng JARVIS.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/test_cli.py -k "autostart" -v`
  - Kiểm tra cú pháp script PowerShell: `powershell -Command "Test-Path scripts/install.ps1"`

---

#### Item P3-19: Interactive Web Dashboard & Realtime Telemetry WebSocket
- **Priority:** 🟢 P3 Low
- **Tên tính năng:** Bảng điều khiển Web Tương tác và Luồng Telemetry WebSocket
- **Mô tả kỹ thuật:**  
  Nâng cấp server FastAPI / WebSocket (`jarvis/web/dashboard.py`) để truyền phát luồng dữ liệu thời gian thực gồm dạng sóng âm thanh microphone (waveform), đồ thị CPU/RAM, nhật ký định tuyến ý định và trạng thái các plugin lên giao diện HTML5/Vue.js chủ đề Iron Man HUD.
- **Tệp liên quan & Line spans:**
  - `jarvis/web/dashboard.py` (L1–L250)
  - `jarvis/web/static/index.html`
  - `jarvis/web/static/app.js`
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Triển khai endpoint WebSocket `/ws/telemetry` phát dữ liệu nhịp 10Hz.
  2. Cung cấp các REST API `/api/status`, `/api/logs`, `/api/command`.
  3. Thiết kế giao diện Dark Mode tương tác trực tiếp với trợ lý qua web browser.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_dashboard_server.py -v`

---

#### Item P3-20: Automated Benchmark & Acoustic Evaluation Suite
- **Priority:** 🟢 P3 Low
- **Tên tính năng:** Bộ Công cụ Đánh giá Benchmark Tự động và Kiểm thử Âm học
- **Mô tả kỹ thuật:**  
  Xây dựng bộ công cụ benchmark tự động đo đạc liên tục độ chính xác nhận dạng STT (tỷ lệ lỗi từ WER / lỗi ký tự CER trên tập âm thanh phòng ồn), khoảng tin cậy Wilson 95% cho định tuyến ý định và độ trễ toàn trình.
- **Tệp liên quan & Line spans:**
  - `tests/eval/routing_eval_n150.py` (L1–L318)
  - `tests/eval/stt_intent_eval.py`
  - `docs/benchmark_results.md`
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Tự động hóa việc chạy `routing_eval_n150.py` tính toán tỷ lệ CORRECT, SILENT, MISROUTED kèm Wilson CI.
  2. Xây dựng runner kiểm tra âm học trên tập file `.wav` mẫu trong `tests/eval/audio/`.
  3. Xuất kết quả tự động ra định dạng Markdown trong `docs/benchmark_results.md`.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `python tests/eval/routing_eval_n150.py --dry-run`

---

#### Item P3-21: CLI System Pre-Flight Diagnostics & Health Probes
- **Priority:** 🟢 P3 Low
- **Tên tính năng:** Công cụ Chẩn đoán Tiền kiểm Hệ thống Toàn diện qua CLI
- **Mô tả kỹ thuật:**  
  Nâng cấp lệnh `jarvis health` (`run_health_check` trong `jarvis/cli.py`) để kiểm tra toàn diện thiết bị âm thanh vào/ra, tính toàn vẹn của mô hình Vosk/Whisper, quyền ghi CSDL SQLite, khả năng chụp ảnh màn hình và kết nối API với giao diện màu ANSI sinh động.
- **Tệp liên quan & Line spans:**
  - `jarvis/cli.py` (L88–L137)
  - `scripts/system_diagnostic.ps1`
  - `tests/test_cli.py`
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Bổ sung các đầu dò kiểm tra mô hình AI, kết nối LLM, quyền truy cập thư mục dữ liệu.
  2. Hỗ trợ cờ `--json` xuất báo cáo có cấu trúc cho các công cụ giám sát ngoài.
  3. Trả về mã thoát khác 0 nếu phát hiện lỗi phần cứng hoặc cấu hình nghiêm trọng.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/test_cli.py -k "test_run_health_check" -v`
  - Chạy thử nghiệm: `python -m jarvis health --json`

---

#### Item P3-22: Multi-Language & Code-Switching Vietnamese-English Engine
- **Priority:** 🟢 P3 Low
- **Tên tính năng:** Xử lý Song ngữ Việt - Anh và Chuẩn hóa Văn bản Tiếng Việt
- **Mô tả kỹ thuật:**  
  Nâng cấp bộ định tuyến và tiền xử lý văn bản để nhận diện tự nhiên các câu lệnh chèn tiếng Anh (code-switching) phổ biến trong giới công nghệ (ví dụ: "open Chrome", "search Google bài hát mới", "restart máy tính", "git push origin main") và xử lý đồng nhất giữa văn bản có dấu và không dấu.
- **Tệp liên quan & Line spans:**
  - `jarvis/stt/engine.py`
  - `jarvis/llm/router.py`
  - `jarvis/utils/vietnamese.py` (Tệp mới, ~150 LOC)
- **Các bước triển khai cụ thể (Implementation Steps):**
  1. Viết module chuẩn hóa xóa dấu tiếng Việt linh hoạt `remove_vietnamese_accents`.
  2. Bổ sung hỗ trợ biểu thức chính quy song ngữ cho các thuật ngữ công nghệ.
  3. Đánh giá độ chính xác phân loại trên tập dữ liệu câu lệnh song ngữ.
- **Phương pháp kiểm chứng kiểm thử (Test Verification):**
  - `pytest tests/unit/test_vietnamese_utils.py -v`
  - `pytest tests/unit/test_llm_router.py -k "code_switching" -v`

---

## Phần C — Kế hoạch theo giai đoạn Sprints 1–4 (Part C: Phased Sprint Plan)

```
Lộ trình Tổng thể:
Sprint 1 (Tuần 1–2 / v4.6.0) ──> Khắc phục dứt điểm P0, Mở rộng Tier-1 & 0 Test Failures
Sprint 2 (Tuần 3–6 / v4.7.0) ──> Ổn định Âm học, HUD Overlay, Khay Hệ thống & Giảm độ trễ
Sprint 3 (Tháng 2–3 / v4.8.0) ──> Hoàn thiện Tính năng Đa phương thức (Bộ nhớ, Thị giác, Web, IoT)
Sprint 4 (Tháng 4+ / v5.0.0)  ──> Đóng gói Bộ cài đặt Windows, Bảng điều khiển Web & CI/CD
```

---

### Sprint 1 (Tuần 1–2 / v4.6.0): P0 Criticals & Zero-Crash Baseline
- **Chủ đề (Theme):** Xóa bỏ Toàn bộ Điểm nghẽn Nghiêm trọng (Zero-Crash Baseline & P0 Fixes)
- **Thời lượng:** 1–2 Tuần
- **Phiên bản Mục tiêu:** `v4.6.0`
- **Danh sách Backlog Items thực thi:**
  - **P0-1:** Wake Word ngoại tuyến sẵn sàng production (Vosk + Faster-Whisper sliding window fallback).
  - **P0-2:** Cầu nối `jarvis/workers/proactive.py` hoàn chỉnh (`ProactiveEngine`, nhắc nhở, cảnh báo phần cứng, Pomodoro).
  - **P0-3:** Đường ống định tuyến LLM Tier-2 kiểm chứng luồng `force_llm=False` với OpenAI API key.
  - **P0-4:** Mở rộng $\ge 40-60$ quy tắc Tier-1 Fast-Path, hạ `SILENT_FAILURE` $\le 40\%$, giữ `MISROUTED = 0`.
  - **P0-5:** Bảo vệ toàn diện bộ test suite, đạt chuẩn 0 failures trên mọi unit và adversarial test suite.
- **Sản phẩm Bàn giao (Deliverables):**
  1. `docs/ROADMAP.md` phiên bản chuẩn hóa toàn diện (Parts A, B, C).
  2. Tệp `jarvis/workers/proactive.py` hoạt động đồng bộ cùng `app.py`.
  3. `jarvis/audio/wake_word.py` hỗ trợ nạp Vosk và fallback không bị crash.
  4. `jarvis/llm/router.py` bổ sung hơn 60 quy tắc regex mới.
  5. Cập nhật `CHANGELOG.md` cho v4.6.0 và phiên bản `__version__ = "4.6.0"` trong `jarvis/__init__.py`.
- **Tiêu chí Nghiệm thu Sprint (Acceptance Gate):**
  - `pytest tests/ -q --ignore=tests/e2e` vượt qua 100% với 0 lỗi (0 failures).
  - Chạy `python tests/eval/routing_eval_n150.py` đạt `SILENT_FAILURE <= 40.0%` và `MISROUTED == 0`.
  - Lệnh kiểm tra import `python -c "import jarvis.core.app; import jarvis.workers.proactive"` thực thi thành công.

---

### Sprint 2 (Tuần 3–6 / v4.7.0): Accuracy, Acoustic & UX Hardening
- **Chủ đề (Theme):** Tối ưu hóa Âm học, Giao diện Trực quan & Giảm độ trễ Phản hồi
- **Thời lượng:** 2–4 Tuần
- **Phiên bản Mục tiêu:** `v4.7.0`
- **Danh sách Backlog Items thực thi:**
  - **P1-6:** Tách biệt luồng HUD Overlay Tkinter và cơ chế thu âm không chặn trong `JarvisApp`.
  - **P1-7:** Menu Khay hệ thống Windows Tray điều khiển bật/tắt nhanh Wake Word và cử chỉ.
  - **P1-8:** Tinh chỉnh bộ lọc âm học DSP (EMA tracking, SFM/ZCR) và thời gian trễ 2.5s chống dội âm.
  - **P1-9:** Bảo đảm an toàn luồng COM cho SAPI5 local TTS với `pythoncom.CoInitialize()`.
  - **P1-10:** Nạp trước mô hình Faster-Whisper và phân đoạn VAD cắt khoảng lặng tức thì.
  - **P1-11:** Tích hợp bộ đọc thông số phần cứng CPU/RAM trực tiếp bằng giọng nói.
  - Mở rộng độ phủ Tier-1 Fast-Path đạt $\ge 60-70\%$ trên tập câu lệnh mở rộng.
- **Sản phẩm Bàn giao (Deliverables):**
  1. Độ trễ toàn trình từ lúc dứt câu nói đến khi phát âm thanh phản hồi $< 1.5\text{s}$.
  2. Hiệu ứng đồ họa HUD overlay hiển thị mượt mà đồng bộ theo trạng thái thoại.
  3. Hoàn toàn không còn hiện tượng xung đột tài nguyên microphone giữa các luồng.
- **Tiêu chí Nghiệm thu Sprint (Acceptance Gate):**
  - Nhận diện từ khóa thực tế qua microphone đạt $\ge 70\%$ trên 30 lần thử nghiệm âm thanh phòng.
  - Tỷ lệ kích hoạt vỗ tay giả $< 1$ lần trong 2 giờ làm việc văn phòng bình thường.
  - Vượt qua 100% các bài test UX/UI (`test_m3_ux.py`, `test_adversarial_m3_ui_app.py`).

---

### Post-Sprint 2 Maintenance (2026-09-02): Healing Truthfulness & Wake-Word CI Determinism

> Hai hạng mục bảo trì này nằm **ngoài** danh sách backlog P0–P3 gốc của roadmap này — chúng
> là các phát hiện/lỗi được xử lý sau khi Sprint 2 (`v4.7.0`) đã đóng, trên `main`, không bump
> phiên bản runtime. Ghi nhận tại đây để giữ roadmap đồng bộ với trạng thái thật của `main`.

- **✅ HOÀN THÀNH — Healing truthfulness** (`jarvis/healing/terminator.py`, PR #31, merge
  commit `10d470237b0fe4bc295f02215b4606590d79d17e`): tự phục hồi hệ thống (thuộc module
  `jarvis/healing/` đã đánh dấu `✅ Done` ở bảng A.1 phía trên) giờ chỉ báo thành công sau khi
  việc chấm dứt tiến trình được xác nhận thực sự xảy ra, và RAM đã giải phóng chỉ được báo cáo
  từ phép đo trước/sau thực tế — không còn bịa đặt số liệu hay tự nhận thành công khi chưa xác
  nhận. Xem `CLAUDE.md` §0/§1A "Healing truthfulness" và `docs/PROJECT_STATE.md` checkpoint
  2026-09-02 để biết chi tiết đầy đủ.
- **✅ HOÀN THÀNH — Wake-word Whisper CI determinism** (`tests/unit/test_wake_word_p0.py`, PR
  #32, merge commit `aaeeb53f834134bb4490147c238e82e863558caa`): test-only fix, đóng góp cho
  tiêu chí nghiệm thu "0 test failures" của Sprint 1/2 — không thay đổi hành vi wake-word
  production, không phải một sửa lỗi kiến trúc mới cho Item P0-1.
- **✅ ĐÃ TRIỂN KHAI VÀ KIỂM CHỨNG (chưa commit/merge) — Central dispatch truthfulness**
  (nhánh `fix/dispatch-truthfulness`, 2026-09-03): `jarvis/core/dispatcher.py`
  (`dispatch_action()`/`dispatch_action_async()`, hàm chuẩn hóa dùng chung
  `_normalize_handler_outcome()`) và `jarvis/core/app.py` (`process_text_command()`,
  `_on_gesture_event()`) giờ lan truyền trung thực một thất bại tường minh của handler
  xuyên suốt: handler → dispatcher → phản hồi ứng dụng → bộ nhớ → nhật ký tương tác → sự
  kiện `action.post_dispatch`. Không còn tự động biến thất bại tường minh thành `success=True`.
  57 test tất định (`tests/unit/test_dispatch_truthfulness.py`) cộng với
  `test_action_dispatcher_safety.py`/`test_app_integration.py` không đổi hành vi. **Chưa
  được commit/merge vào `main`** — cho tới khi đó, `main` vẫn còn lỗi gốc. Xem `CLAUDE.md`
  §0/§1A "Dispatch truthfulness" và `docs/PROJECT_STATE.md` checkpoint 2026-09-03 để biết
  chi tiết đầy đủ.
  - **✅ HOÀN THÀNH (chỉ định trực tiếp từ chủ sở hữu kho mã, cùng nhánh) — `hardware_status_query`
    compatibility alias**: router (`jarvis/llm/router.py`) cố ý định tuyến "Báo cáo tình
    trạng hệ thống" và các câu hỏi phần cứng/trạng thái khác tới action `hardware_status_query`
    từ nhiều nơi, nhưng `app.py` trước đây chỉ đăng ký `system_status` — gây `ACTION_NOT_FOUND`
    thật, trước đây bị chính lỗi dispatch-truthfulness che giấu. Theo quyết định của chủ sở
    hữu, **không** sửa `jarvis/llm/router.py` (hợp đồng router có chủ đích, đa điểm gọi); sửa
    hẹp trong `jarvis/core/app.py::_register_core_actions()` — đăng ký thêm
    `hardware_status_query` dùng lại đúng handler `self._handle_system_status` hiện có (không
    trùng lặp logic, `system_status` giữ nguyên). 5 test mới xác nhận
    (`TestHardwareStatusQueryAlias`); `tests/unit/test_integration_e2e.py::test_memory_recording_in_process_text_command`
    pass lại **không sửa file test đó**. Toàn bộ `tests/unit/`: **1413 passed, 1 skipped, 50
    subtests passed, 0 failed.**
  Các phát hiện khác chưa liên quan (TShark/network/v.v., nếu có trong các tài liệu audit khác)
  không bị ảnh hưởng và không được đóng theo mục này.

---

### Sprint 3 (Tháng 2–3 / v4.8.0): Multimodal Feature Completion
- **Chủ đề (Theme):** Hoàn thiện Trí tuệ Đa phương thức (Bộ nhớ, Thị giác, Web, IoT)
- **Thời lượng:** 1–2 Tháng
- **Phiên bản Mục tiêu:** `v4.8.0`
- **Danh sách Backlog Items thực thi:**
  - **P2-12:** Hệ thống bộ nhớ 2 tầng (`SessionContextManager` và SQLite `logs/memory.db`).
  - **P2-13:** Công cụ Thị giác Màn hình (`mss`, Gemini 1.5 Flash / GPT-4o Vision, thanh tra dialog lỗi `#32770`).
  - **P2-14:** Hub tra cứu Web thời gian thực (DuckDuckGo, thời tiết, RSS tin tức, tỷ giá crypto/forex, cache 10m).
  - **P2-15:** Trình điều khiển tự động hóa trình duyệt web Playwright Chromium.
  - **P2-16:** Kênh thông báo và điều khiển từ xa qua Telegram Bot.
  - **P2-17:** Cầu nối điều khiển thiết bị nhà thông minh Home Assistant.
- **Sản phẩm Bàn giao (Deliverables):**
  1. Gói `jarvis/memory/` lưu trữ thông tin bền vững với chế độ WAL.
  2. Gói `jarvis/vision/` hỗ trợ đọc hiểu màn hình độ trễ thấp.
  3. Gói `jarvis/web/` cung cấp dữ liệu trực tuyến có bộ đệm.
  4. Các cổng kết nối `jarvis/comms/` và `jarvis/smart_home/`.
- **Tiêu chí Nghiệm thu Sprint (Acceptance Gate):**
  - Đăng ký và thực thi thành công 12 action mới qua `ActionDispatcher`.
  - Kiểm thử đa luồng SQLite vượt qua 30 luồng đồng thời không phát sinh lỗi khóa bảng.
  - Mọi tác vụ mạng bên ngoài xử lý timeout và mất kết nối êm ái trong vòng $\le 2.0\text{s}$.

---

### Sprint 4 (Tháng 4+ / v5.0.0): Enterprise Polish, Benchmarks & Distribution
- **Chủ đề (Theme):** Đóng gói Phân phối Tự động, Đo lường Toàn diện & CI/CD Chuẩn Enterprise
- **Thời lượng:** Liên tục (Ongoing)
- **Phiên bản Mục tiêu:** `v5.0.0`
- **Danh sách Backlog Items thực thi:**
  - **P3-18:** Bộ cài đặt tự động một chạm `scripts/install.ps1` và bản đóng gói EXE/MSI độc lập.
  - **P3-19:** Bảng điều khiển web tương tác hiển thị dạng sóng âm thanh và telemetry WebSocket.
  - **P3-20:** Hệ thống tự động đo lường benchmark liên tục báo cáo vào `docs/benchmark_results.md`.
  - **P3-21:** Công cụ chẩn đoán sức khỏe hệ thống qua dòng lệnh `jarvis health --json`.
  - **P3-22:** Động cơ hỗ trợ câu lệnh song ngữ Việt - Anh và chuẩn hóa văn bản.
- **Sản phẩm Bàn giao (Deliverables):**
  1. Script cài đặt tự động `scripts/install.ps1` trên Windows 11 sạch.
  2. Bản dựng ứng dụng độc lập không đòi hỏi cài sẵn Python.
  3. Bảng điều khiển Web trực quan thời gian thực.
  4. Quy trình CI/CD tự động kiểm thử và xuất bản phiên bản.
- **Tiêu chí Nghiệm thu Sprint (Acceptance Gate):**
  - Cài đặt thành công trên máy Windows 11 mới chỉ với 1 dòng lệnh PowerShell.
  - Duy trì khởi động cùng hệ thống qua Registry sau các lần khởi động lại máy.
  - Không có bất kỳ lỗi hồi quy nào trên toàn bộ suite $> 600$ test cases.

---

## Ma trận Truy xuất Nguồn gốc & Kiểm thử

Bảng đối chiếu nguồn gốc yêu cầu (Traceability Matrix) và câu lệnh kiểm thử tự động tương ứng cho từng hạng mục kỹ thuật:

| Mã Backlog | Nguồn Yêu cầu (Source Requirement) | Sprint Mục tiêu | Module Tác động Chính | Lệnh Kiểm thử Xác minh Tự động (Pytest Command) |
|---|---|:---:|---|---|
| **P0-1** | `ORIGINAL_REQUEST.md` §R2 (P0-A) | Sprint 1 | `jarvis/audio/wake_word.py` | `pytest tests/unit/test_wake_word.py -v` |
| **P0-2** | `ORIGINAL_REQUEST.md` §R2 (P0-B) | Sprint 1 | `jarvis/workers/proactive.py` | `pytest tests/unit/test_proactive_engine.py -v` |
| **P0-3** | `ORIGINAL_REQUEST.md` §R2 (P0-C) | Sprint 1 | `jarvis/llm/router.py` | `pytest tests/unit/test_llm_router.py -v` |
| **P0-4** | `ORIGINAL_REQUEST.md` §R2 (P0-D) | Sprint 1 | `jarvis/llm/router.py` | `python tests/eval/routing_eval_n150.py` |
| **P0-5** | `ORIGINAL_REQUEST.md` §R3 | Sprint 1 | `tests/` | `pytest tests/ -q --ignore=tests/e2e` |
| **P1-6** | `PROJECT.md` Giao diện Cửa sổ Nổi | Sprint 2 | `jarvis/ui/overlay.py` | `pytest tests/test_m3_ux.py -v` |
| **P1-7** | `PROJECT.md` Khay Hệ thống Tray | Sprint 2 | `jarvis/ui/tray.py` | `pytest tests/unit/test_tray.py -v` |
| **P1-8** | `AUDIT_METHODOLOGY.md` Âm học | Sprint 2 | `jarvis/audio/dsp.py` | `pytest tests/test_audio_dsp.py -v` |
| **P1-9** | `AUDIT_METHODOLOGY.md` Local TTS | Sprint 2 | `jarvis/tts/fallback.py` | `pytest tests/test_tts_engine.py -v` |
| **P1-10**| `AUDIT_METHODOLOGY.md` STT CT2 | Sprint 2 | `jarvis/stt/engine.py` | `pytest tests/unit/test_stt_engine.py -v` |
| **P1-11**| `PROJECT.md` Hardware Subsystem | Sprint 2 | `jarvis/hardware/monitor.py` | `pytest tests/test_hardware_monitor.py -v` |
| **P2-12**| `ORIGINAL_REQUEST.md` Memory Store | Sprint 3 | `jarvis/memory/manager.py` | `pytest tests/unit/test_memory_system.py -v` |
| **P2-13**| `PROJECT.md` Vision Screen | Sprint 3 | `jarvis/vision/screen.py` | `pytest tests/unit/test_screen_vision.py -v` |
| **P2-14**| `PROJECT.md` Web Intelligence | Sprint 3 | `jarvis/web/search.py` | `pytest tests/unit/test_web_intelligence.py -v` |
| **P2-15**| `PROJECT.md` Trình duyệt Web | Sprint 3 | `jarvis/browser/controller.py` | `pytest tests/unit/test_browser_automation.py -v` |
| **P2-16**| `PROJECT.md` Kênh Giao tiếp | Sprint 3 | `jarvis/comms/telegram_bot.py` | `pytest tests/unit/test_telegram_bot.py -v` |
| **P2-17**| `PROJECT.md` Nhà thông minh | Sprint 3 | `jarvis/smart_home/` | `pytest tests/unit/test_home_assistant.py -v` |
| **P3-18**| `ORIGINAL_REQUEST.md` Installer | Sprint 4 | `scripts/install.ps1` | `pytest tests/test_cli.py -k "autostart" -v` |
| **P3-19**| `PROJECT.md` Web Dashboard | Sprint 4 | `jarvis/web/dashboard.py` | `pytest tests/unit/test_dashboard_server.py -v` |
| **P3-20**| `ORIGINAL_REQUEST.md` Benchmark | Sprint 4 | `tests/eval/` | `python tests/eval/routing_eval_n150.py --dry-run` |
| **P3-21**| `ORIGINAL_REQUEST.md` Diagnostics | Sprint 4 | `jarvis/cli.py` | `pytest tests/test_cli.py -k "test_run_health_check" -v` |
| **P3-22**| `PROJECT.md` Tiếng Việt Song ngữ | Sprint 4 | `jarvis/utils/vietnamese.py` | `pytest tests/unit/test_vietnamese_utils.py -v` |
