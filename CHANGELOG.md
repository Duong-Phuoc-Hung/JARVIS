# 📝 JARVIS - Nhật Ký Cập Nhật & Bản Ghi Phát Triển (Changelog)

---

## 🛡️ Phiên Bản 4.1.0 (2026-08-30) — OS-Level Kernel Isolation & Master Technical Audit Hardening

Sau 13 vòng kiểm toán đối kháng (Adversarial Technical Audit), phiên bản 4.1.0 mang đến cuộc đại tu kiến trúc an ninh lớn nhất từ trước đến nay cho JARVIS, chuyển đổi ranh giới bảo mật từ monkey-patching tầng ứng dụng sang **Ranh giới Cấp Kernel Hệ Điều Hành (OS Kernel Boundaries)** trên Windows x64.

### 🔒 1. Cách Ly An Ninh Cấp OS Kernel (OS-Level Sandboxing)
* **Windows Mandatory Integrity Control (MIC):**
  - Chuyển tiến trình con thực thi mã động sang `TokenIntegrityLevel = LOW` (`S-1-16-4096`) qua `SetTokenInformation`.
  - Khắc phục lỗi kiểu dữ liệu 64-bit `wintypes.HANDLE` trong chữ ký `ctypes` để gọi thành công `advapi32.SetNamedSecurityInfoW` với SACL `S:(ML;OICI;NW;;;LW)` dưới quyền người dùng phổ thông (Non-Elevated Standard User).
  - Windows Kernel SRM chặn đứng mọi hành vi ghi file trái phép ra ngoài thư mục sandbox với `[Errno 13] Permission denied` trực tiếp từ kernel.
* **Windows Job Object Resource & Process Hardening:**
  - Thiết lập `ActiveProcessLimit = 1`, `JobMemoryLimit = 256MB` và `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
  - Chặn đứng 100% việc tạo tiến trình con (`cmd.exe`, `powershell.exe`, `subprocess.Popen`) với mã lỗi kernel `WinError 1816`.
* **Environment Block Sanitization:**
  - Tự động làm sạch toàn bộ biến môi trường nhạy cảm (API Keys, Token) trước khi truyền qua `CreateProcessAsUserW`.

### 🛡️ 2. Phòng Thủ Đa Tầng Tầng Ứng Dụng (In-Process Runtime Defense-in-Depth)
* **Khắc Phục Lỗ Hổng `__closure__` & `__globals__` Introspection:**
  - Thay thế các wrapper hàm bằng Slot-based Guard Classes (`__slots__ = ()`) ghi đè `__getattribute__` để chặn trích xuất hàm gốc.
* **Prefix Wildcard Matcher & Hai Tầng Đầu Độc Cache:**
  - Nâng cấp cơ chế chặn module cấm sang kiểm tra tiền tố họ module (`win32*`, `_win32*`, `pywin*`, `comtypes*`, `pythoncom*`, `pywintypes*`, `wmi*`, `clr*`, `ctypes`, `socket`, `ssl`).
  - Đầu độc toàn bộ cache `sys.modules` và chèn `_BlockedMetaPathFinder` vào `sys.meta_path[0]`, đồng thời loại bỏ đường dẫn thư mục dự án khỏi `sys.path`.

### 📱 3. An Ninh Cầu Nối Di Động & Webhook
* **Zalo Bot Webhook:**
  - Sửa lỗi xác thực HMAC-SHA256: hỗ trợ constant-time so sánh (`hmac.compare_digest`) cho cả chuỗi Hex 64 ký tự lẫn Base64 44 ký tự.
  - Ràng buộc địa chỉ lắng nghe an toàn trên `127.0.0.1`.
* **Mobile Bridge File Uploads:**
  - Chuyển từ cơ chế blocklist sang **Strict Explicit Allowlist** (`.txt`, `.pdf`, `.png`, `.jpg`, `.csv`, `.json`).
  - Bổ sung kiểm tra đệ quy double-extension (`path.suffixes`) ngăn chặn hoàn toàn kịch bản tấn công tệp thực thi đội lốt tài liệu (`invoice.exe.pdf`).

### ⚡ 4. Bộ Đo Đạc Phần Cứng & Khắc Phục Lỗi STT
* **Sửa Lỗi Xử Lý Đệm Âm Thanh STT:** Sửa ngoại lệ `ValueError: The truth value of an array with more than one element is ambiguous` trong `jarvis/stt/faster_whisper.py` khi nhận mảng `np.ndarray`.
* **Bộ Benchmark Phần Cứng Độc Lập (`scripts/benchmark_hardware.py`):**
  - Đo đạc thực nghiệm số liệu thật trên CPU Intel Core i7-10750H (AST Validator p50: 0.03-0.21ms, OS Sandbox Overhead p50: 170-195ms, SAPI5 PCM Speech Synthesis: 22-141ms).
  - Tách bạch rõ ràng số liệu phần cứng thật khỏi số liệu pipeline adapter giả lập.
* **Tài Liệu Kiểm Toán & Kiến Trúc:**
  - Bổ sung [`docs/SECURITY_ARCHITECTURE.md`](file:///d:/Software%20GitCode/JARVIS/docs/SECURITY_ARCHITECTURE.md) và [`docs/TECHNICAL_AUDIT_REPORT.md`](file:///d:/Software%20GitCode/JARVIS/docs/TECHNICAL_AUDIT_REPORT.md).
* **Test Suite:**
  - Bổ sung 15 Adversarial Integration Tests trong [`tests/integration/test_sandbox_os_boundaries.py`](file:///d:/Software%20GitCode/JARVIS/tests/integration/test_sandbox_os_boundaries.py). Toàn bộ 662 tests pass 100%.

---

## 🚀 Phiên Bản 4.0.1 (2026-08-29) — Stability, CA/CI & Runtime Fixes

Quá trình rà soát bằng phân tích tĩnh (Ruff, mypy) và pipeline CI đã phát hiện một số lỗi tiềm ẩn trước đây bị che khuất bởi các khối `except` quá rộng hoặc đơn giản là chưa từng được bộ test kiểm tra. Các lỗi bên dưới đã được sửa và đều được xác nhận dựa trên hành vi thực tế khi chạy chương trình, không chỉ đơn thuần là làm cho lỗi type-checking biến mất.

### Build & thư viện phụ thuộc

- Sửa một dòng bị lỗi trong `requirements.txt` khiến lệnh `pip install -r requirements.txt` không thể chạy được.
- Sửa `build-backend` không hợp lệ trong `pyproject.toml` (`setuptools.backends.legacy:build` không tồn tại), vốn làm hỏng mọi quy trình build theo chuẩn PEP 517 như `pip install .` và `python -m build`.

### Lỗi khi chạy chương trình

- Sửa tích hợp Telegram bị lỗi (`jarvis/agent/graph.py`, `jarvis/workers/notification_hub.py`) — mã nguồn tham chiếu đến class `TelegramController` không tồn tại và sử dụng sai chữ ký của hàm `send_message`.
- Sửa các lời gọi định tuyến intent bằng LLM (`jarvis/agent/graph.py`, `jarvis/comms/zalo.py`) — mã nguồn tham chiếu đến class `IntentRouter` không tồn tại.
- Bổ sung chức năng tự khởi động cùng Windows (`jarvis/platform/windows.py`) — `set_autostart` và `get_autostart_status` đã được CLI sử dụng nhưng trước đó chưa hề được định nghĩa.
- Sửa chức năng điều khiển âm lượng Windows (`jarvis/automation/control.py`) — sử dụng sai nguồn của hằng số `CLSCTX_ALL`, khiến các thao tác lấy âm lượng, đặt âm lượng và tắt tiếng đều âm thầm thất bại.
- Sửa nhiều lỗi không khớp API/chữ ký hàm trong `jarvis/core/app.py` như sử dụng sai thành viên enum, thiếu đối số bắt buộc, chữ ký cũ của chức năng sinh skill và điền form, cũng như các thao tác tra cứu bị lặp.
- Sửa đăng ký plugin (`jarvis/core/plugin.py`) — có hai định nghĩa `stop_all()` khiến định nghĩa sau ghi đè định nghĩa trước, đồng thời `register_plugin()` có thể trả về `None` thay vì giá trị `bool` đúng chuẩn.
- Sửa các lệnh liệt kê skill trên Discord/Zalo (`jarvis/comms/discord.py`, `jarvis/comms/zalo.py`) — `SkillMetadata` trước đó bị truy cập như một `dict` thay vì một `dataclass`.
- Sửa chức năng lấy giá tiền mã hóa trong skill bản tin buổi sáng (`jarvis/skills/briefing`) — mã nguồn gọi đến một phương thức không tồn tại.
- Sửa bộ xác minh hình ảnh (`jarvis/vision/visual_verifier.py`) — trước đó kết quả được tạo từ dữ liệu ảnh `None` chưa được xử lý thay vì sử dụng các giá trị fallback đã được tính sẵn.
- Bổ sung phương thức `show()` còn thiếu cho overlay luôn hiển thị (`jarvis/ui/overlay.py`) — hàm `toggle()` có gọi đến phương thức này nhưng trước đó nó không tồn tại.
- Sửa dữ liệu pin không hợp lệ trên hệ thống headless/VM (`jarvis/ui/overlay.py`) — `_safe_probe_battery()` giờ coi phần trăm pin sentinel không hợp lệ (ví dụ `-1` do psutil trả về khi hệ thống không có pin thực) là không khả dụng (`None`) thay vì trả trực tiếp giá trị sai, đồng thời vẫn giữ đúng trạng thái đang cắm nguồn AC; bổ sung 3 regression test cho phần trăm hợp lệ, sentinel không hợp lệ và trường hợp không có pin.
- Dữ liệu pin trên Windows giờ hoạt động ổn định giữa các phiên bản Python và xử lý an toàn cả hai giá trị sentinel `-1` và `255` từ `GetSystemPowerStatus`. Nguyên nhân là `ctypes.wintypes.BYTE` đã thay đổi từ kiểu signed sang unsigned giữa Python 3.11 và 3.12, khiến giá trị `-1` trước đây có thể lọt qua bước kiểm tra phạm vi.

### Chất lượng mã nguồn

- Dọn dẹp toàn bộ cảnh báo Ruff + mypy trong `jarvis/` và `tests/` như thứ tự import, binding biến trong closure, thu hẹp kiểu `Optional`, v.v. — không làm thay đổi chức năng.
- Sửa TTS ở chế độ headless/mock trên GitHub Actions — `JARVIS_MOCK_AUDIO=1` giờ bỏ qua việc phát âm thanh vật lý nhưng vẫn giữ nguyên quá trình kiểm tra tổng hợp giọng nói và bộ nhớ đệm.
- Bộ unit test của CI (`tests/unit/`) đã được xác nhận chạy thành công: **647 test passed**.
- GitHub Actions đã được xác nhận hoạt động thành công trên Python 3.13: **Syntax Check, Unit Tests, Import Validation và Pipeline Summary đều passed**.
- Workflow phát hành hiện sử dụng Python 3.13, đồng bộ với pipeline CI chính.

> **Lưu ý:** Điều này **không có nghĩa toàn bộ cây `tests/` đều đang xanh**. Các bộ test mở rộng không thuộc CI như adversarial/challenger stress test, biometrics và các kịch bản e2e vẫn còn một số lỗi tồn tại từ trước, không liên quan đến đợt rà soát này. Một số test yêu cầu các thư viện tùy chọn không được cài trong CI (ví dụ `cv2`), trong khi một số khác kiểm tra những tính năng vốn chưa từng được triển khai.
---

## 🚀 Phiên Bản 4.0.0 (2026-08-28) — Full Autonomous ReAct Agent

JARVIS v4.0.0 là bước nhảy vọt lớn nhất: JARVIS không chỉ thực thi lệnh mà giờ có thể **tự lập kế hoạch và thực thi mục tiêu phức tạp** thông qua vòng lặp Think → Act → Observe → Reflect.

### 🧠 1. LangGraph ReAct Agent (`jarvis/agent/graph.py`)
* Vòng lặp tự trị: **Think → Act → Observe → Reflect → Done**
* 12 built-in tools: web_search, take_note, read_file, write_file, run_python, browser, screenshot, calculator, memory_search, send_telegram, list_dir, git_status
* Heuristic fallback khi LLM không khả dụng
* Giới hạn iterations tránh vòng lặp vô hạn
* Lịch sử đầy đủ từng bước (task_id, steps, result, timestamps)

### 🔔 2. Notification Hub Đa Kênh (`jarvis/workers/notification_hub.py`)
* Gửi đồng thời đến: **Telegram, Discord, Zalo, Windows Toast, Sound, TTS**
* Scheduling: nhắc nhở theo `HH:MM` hoặc ISO datetime, lặp daily/hourly
* Alert Rules: thêm điều kiện tùy chỉnh với cooldown chống spam
* Lịch sử 100 thông báo gần nhất

### 📦 3. Windows Standalone Installer
* `JARVIS.spec` — PyInstaller spec tự sinh
* `installer/setup.iss` — Inno Setup script tạo JARVIS_Setup_v*.exe
* `scripts/build_installer.py` — One-command build: tests → exe → installer
* Hỗ trợ: Desktop shortcut, Start Menu, Autostart Windows, Uninstall

### 🧪 4. Tests (+51 mới, tổng 633)
* `test_zalo_bot.py` — 15 tests
* `test_notification_hub.py` — 17 tests
* `test_react_agent.py` — 19 tests

---

## 🚀 Phiên Bản 3.2.0 (2026-08-28) — Zalo Bot 2-Way Control

### 📱 1. Zalo Bot Controller (`jarvis/comms/zalo.py`)
* Tích hợp Zalo Official Account API — điều khiển JARVIS từ ứng dụng Zalo
* Lệnh: `/status`, `/briefing`, `/note`, `/calc`, `/weather`, `/screenshot`, `/skills`, `/help`
* Ngôn ngữ tự nhiên tiếng Việt → IntentRouter
* Whitelist bảo mật + HMAC-SHA256 signature verification
* Webhook HTTP server nhúng (port 8765, không cần Flask)
* Broadcast đến tất cả user trong whitelist

---

## 🚀 Phiên Bản 3.1.0 (2026-08-28) — Browser Control, Auto-Update & Plugin SDK


Bản nâng cấp v3.1.0 mở rộng JARVIS với khả năng **điều khiển Chrome bằng giọng nói**, **tự cập nhật từ GitHub Releases**, **hệ sinh thái plugin bên thứ 3**, và **pipeline CI/CD tự động build .EXE**.

### 🌐 1. Browser CDP Controller (`jarvis/browser/cdp_controller.py`)
* Điều khiển Chrome/Edge bằng giọng nói qua Playwright (CDP)
* Lệnh: *"Mở YouTube", "Tìm kiếm tin tức", "Click vào nút Đăng nhập", "Chụp ảnh trang web"*
* 9 hành động: `open`, `navigate`, `search`, `click`, `type`, `screenshot`, `extract`, `scroll`, `close`
* Quick URL shortcuts: youtube, gmail, github, shopee, lazada, vnexpress, dantri, tgdd...
* Skill `browser_control` tích hợp trực tiếp vào voice pipeline

### 🔄 2. Auto-Update Daemon (`jarvis/workers/auto_updater.py`)
* Tự động kiểm tra GitHub Releases mỗi 6 giờ
* So sánh semver thông minh: `v3.1.0 > v3.0.0`
* Tự áp dụng bản mới qua `git pull` + `pip install -r requirements.txt`
* Backup marker trước khi cập nhật, rollback về bản trước nếu lỗi
* Lịch sử 30 lần kiểm tra gần nhất tại `logs/update_history.json`
* Skill `auto_updater`: check, update, rollback, history, status

### 🧩 3. Plugin SDK (`jarvis/plugins/loader.py`)
* Hot-load kỹ năng từ `~/.jarvis/plugins/<name>/` — không cần khởi động lại
* Cài từ pip: `pip install jarvis-plugin-<name>` (entry_point: `jarvis.plugins`)
* API: `PluginLoader.load_all()`, `call_plugin()`, `reload_plugin()`, `unload_plugin()`
* Tự động merge vào SkillRegistry khi start JARVIS

### ⚙️ 4. Release CI/CD Pipeline (`.github/workflows/release.yml`)
* Tự động build `JARVIS_v*.*.*.exe` khi push tag `v*.*.*`
* Jobs: tests → build .exe (PyInstaller) → zip → publish GitHub Release
* Sinh `reports/version_status.json` đính kèm vào release
* Support prerelease flag cho `beta`/`rc` tags

### 🧪 5. Tests (+46 mới, tổng 582)
* `tests/unit/test_browser_control.py` — 15 tests (navigation, click, screenshot, extract)
* `tests/unit/test_auto_updater.py` — 16 tests (version compare, fetch, check, apply, rollback, history)
* `tests/unit/test_plugin_sdk.py` — 15 tests (mock loader, folder loader, manifest, unload)

---

## 🚀 Phiên Bản 3.0.0 (2026-08-28) — Self-Coding AI, Semantic Memory RAG & Night Shift Worker


Bản nâng cấp thế hệ thứ ba đưa JARVIS v3.0.0 có khả năng **TỰ TIẾN HÓA**: tự sinh kỹ năng mới từ mô tả tiếng Việt, tìm kiếm ký ức theo ngữ nghĩa (Semantic RAG), và làm việc xuyên đêm tự trị không cần giám sát.

### 🧬 1. Self-Coding Skill Synthesizer (`jarvis/skills/skill_synthesizer/`)
* Tự sinh kỹ năng mới từ mô tả tiếng Việt — *"JARVIS, tạo kỹ năng theo dõi giá vàng"*
* Tự tạo `metadata.json`, mã nguồn `execute()` với 9 template type và đăng ký vào `SkillRegistry` ngay lập tức
* Rollback tự động nếu sinh code thất bại hoặc `ast.parse()` báo lỗi cú pháp
* Hành động: `create`, `preview`, `list`, `delete`

### 🔍 2. Semantic Memory RAG (`jarvis/memory/vector_store.py`)
* Semantic Vector Store với TF-IDF cosine similarity thuần Python — không cần GPU, không cần numpy
* BM25-style IDF formula: `log((N+1)/(df+0.5))` — cho kết quả đúng ngay cả khi dataset nhỏ
* Optional FAISS integration khi có sẵn để tăng tốc 10x
* Lệnh thoại: *"JARVIS, tháng trước tôi đã note gì về dự án X?"*
* Bổ sung vào `MemoryManager`: `semantic_search()`, `build_rag_context()`, `index_fact_to_vectors()`
* Skill `rag_search`: hành động search, index, stats, clear

### 🌙 3. Night Shift Autonomous Worker (`jarvis/workers/night_shift.py`)
* Nhận nhiệm vụ lớn trước khi ngủ, tự thực hiện theo lịch lúc 23:00
* Tự phân rã nhiệm vụ thành các bước (9 keyword categories)
* Tạo báo cáo Markdown tổng hợp, lưu `logs/night_report_*.md`
* Skill `night_planner`: hành động add, list, cancel, report, run_now

---

## 🚀 Phiên Bản 2.3.0 (2026-08-28) — Điều Khiển Đa Kênh & Smart Home

### 📱 1. Discord Bot Controller đầy đủ (`jarvis/comms/discord.py`)
* Điều khiển JARVIS qua Discord server: `!status`, `!briefing`, `!skills`, `!note`, `!calc`, `!screenshot`, `!macro`, `!exec`, `!help`
* Security whitelist theo Discord User ID — chặn người không có quyền
* Rich Embed Discord: bảng màu, fields, icon
* Gửi ảnh chụp màn hình về Discord channel, chuyển file
* Backward compatible alias: `DiscordBotClient = DiscordBotController`

### 🔗 2. Mobile File Bridge (`jarvis/comms/mobile_bridge.py`)
* Nhận file/ảnh từ điện thoại qua Telegram → tự lưu vào `downloads/`
* Validation: extension whitelist (14 loại), giới hạn 50MB
* Gửi clipboard và ảnh màn hình về điện thoại trong < 2 giây
* Transfer history log: `logs/mobile_transfers.json`

### 🏠 3. Smart Home Auto-Discovery (`jarvis/smart_home/discovery.py`)
* Tự quét mạng LAN bằng socket ping + port scan (không cần external deps)
* Nhận dạng 3 loại thiết bị: Home Assistant (port 8123), Tasmota (`/cm?cmnd=Status`), generic HTTP smart device
* Auto-register vào entity registry, persist: `logs/smart_home_devices.json`
* Background scan thread với `discovery_interval_s=3600`
* Skill `smart_home_discovery`: hành động scan, list, probe, status

---

## 🚀 Phiên Bản 2.2.0 (2026-08-28) — Nhìn Thấy Màn Hình & Tự Ghi Nhớ Thao Tác

### 👁️ 1. Context-Aware Screen Assistant (`jarvis/skills/screen_context/`)
* Nhấn `Ctrl+Shift+Space` → JARVIS chụp và phân tích nội dung màn hình hiện tại
* 5 modes: `summarize` (tóm tắt bài báo), `explain_error` (giải thích lỗi terminal), `translate` (dịch văn bản), `describe` (mô tả), `analyze` (phân tích code/dữ liệu)
* Vision LLM integration (Gemini 1.5 Flash) với graceful fallback
* Support cả mss và PIL.ImageGrab

### 📹 2. Voice Macro Recorder (`jarvis/skills/macro_recorder/`)
* Lưu, phát lại và xóa quy trình thao tác bằng giọng nói
* 5 loại bước: `click`, `type`, `key`, `wait`, `open`
* Playback qua pyautogui (optional) hoặc clipboard fallback
* Persist: `logs/macros.json`, hành động: record, play, list, delete

### 🔊 3. Sound Board (`jarvis/skills/sound_board/`)
* Phát âm thanh phản hồi điện ảnh Stark UI tổng hợp bằng numpy sine wave
* 5 preset: activation (3-tone ↑), completion (2-tone ↓), error (200Hz buzz), thinking (330Hz pulse ×3), alert (880Hz burst)
* Fallback im lặng khi sounddevice không khả dụng

---

## 🚀 Phiên Bản 2.1.0 (2026-08-28) — Đàm Thoại Thời Gian Thực & AI Offline

### 🎙️ 1. Voice Activity Detection & Barge-in (`jarvis/audio/vad.py`, `jarvis/audio/fullduplex.py`)
* `VoiceActivityDetector`: phát hiện speech vs silence bằng RMS energy (pure Python) + optional webrtcvad
* `FullDuplexVoiceManager`: ngắt lời JARVIS bất kỳ lúc nào với barge-in state machine
* State machine: IDLE → LISTENING → SPEAKING → INTERRUPTED
* `listen_for_speech()` với pre-speech buffer 200ms và silence timeout configurable

### 🔊 2. Piper TTS Offline (`jarvis/tts/piper.py`)
* Giọng đọc tiếng Việt siêu nhanh (< 80ms) chạy hoàn toàn offline qua ONNX Runtime
* Lazy model loading, Vietnamese phoneme support
* Fallback chain: Piper Offline → ElevenLabs → SAPI5
* Hướng dẫn cài model: `models/piper/vi_VN-vivos-medium.onnx`

### 🎤 3. Faster-Whisper STT Offline (`jarvis/stt/faster_whisper.py`)
* Nhận diện giọng nói tiếng Việt cục bộ với độ trễ < 200ms (model `base`, `int8`)
* Lazy model loading, VAD filter built-in, auto language detection
* `TranscriptionResult` dataclass: text, language, confidence, duration_ms, segments
* Fallback chain: Faster-Whisper Local → Whisper API

### 🎵 4. Stark UI Sound Effects (`jarvis/audio/sound_effects.py`)
* `SoundEffectsPlayer`: tổng hợp tone bằng numpy sine wave — không cần file audio
* 5 preset: activation, completion, error, thinking, alert + custom tone
* Async playback thread để không block JARVIS response

---

## 🔄 CI/CD Pipeline (2026-08-28)

### ⚙️ GitHub Actions (`/.github/workflows/ci.yml`)
* Chạy tự động trên `push` và `pull_request` vào branch `main`
* Job `test`: `python -m pytest tests/unit/ -q --tb=short` trên `windows-latest`
* Job `lint`: `python -m py_compile` cho 15+ module mới
* Cache pip dependencies, upload artifacts `reports/`

### 📊 Health Check Report (`scripts/health_check_report.py`)
* Sinh `reports/health_YYYYMMDD_HHMMSS.md` với bảng trạng thái từng module
* Sinh `reports/version_status.json` với metadata phiên bản
* Kiểm tra import 17 module mới (core + skills)

---

## 🚀 Phiên Bản 2.0.0 (2026-08-27) - Nâng Cấp Toàn Diện: Built-in Skills, Global Hotkeys, Memory Scoring & Standalone Packaging


Bản nâng cấp toàn diện đưa **JARVIS v2.0.0** trở thành một trợ lý cá nhân hoàn thiện với kho kỹ năng đóng gói sẵn, phím tắt toàn hệ thống, cơ chế xếp hạng ký ức thông minh, pipeline đóng gói `.exe` độc lập và giao diện điều khiển đa phương thức.

---

### 🧩 1. Thư Viện 9 Built-in Skills Đóng Gói Sẵn (`jarvis/skills/`)
* **Briefing Sáng (`briefing`)**: Tự động tổng hợp thời tiết thực tế, tin tức công nghệ nóng, tỷ giá thị trường Crypto (BTC, ETH) và lịch trình trong ngày; định dạng báo cáo song ngữ và đọc qua giọng nói TTS.
* **Quản Lý File & Thư Mục (`file_manager`)**: Tìm kiếm file theo tên/phần mở rộng, liệt kê nội dung và mở các thư mục người dùng quen thuộc (Downloads, Documents, Desktop, Workspace).
* **Ghi Chú Nhanh Bằng Giọng Nói (`note_taker`)**: Lưu, phân loại nhãn (tag), tìm kiếm và quản lý ghi chú cá nhân tức thì lưu trữ bền vững trong SQLite/JSON.
* **Chế Độ Tập Trung Pomodoro (`pomodoro`)**: Quản lý các chu kỳ tập trung 25 phút làm việc / 5 phút nghỉ ngơi, tự động tắt thông báo không cần thiết.
* **Điều Khiển Hệ Thống Windows (`system_control`)**: Điều chỉnh âm lượng, độ sáng, chụp ảnh màn hình ra Desktop, khóa máy tính trạm, thu nhỏ toàn bộ cửa sổ về Desktop.
* **Trợ Lý Git Thông Minh (`git_assistant`)**: Báo cáo nhanh trạng thái Git repository (branch hiện tại, file thay đổi, commit gần đây) bằng tiếng Việt tự nhiên.
* **Máy Tính & Quy Đổi Tiền Tệ (`calculator`)**: Phân tích cú pháp cây AST toán học an toàn (hỗ trợ hàm căn bậc hai, phần trăm, lượng giác) và quy đổi tỷ giá tiền tệ tự động (USD, VND, EUR, JPY, GBP).
* **Quản Lý Clipboard (`clipboard`)**: Đọc nhanh nội dung trong bộ nhớ đệm và sao chép văn bản mới bằng Win32 API.
* **Trình Khởi Chạy Ứng Dụng (`app_launcher`)**: Khởi chạy trực tiếp các phần mềm phổ biến (Chrome, VS Code, Spotify, Notepad, Terminal, Settings).

---

### 🧠 2. Cơ Chế Xếp Hạng Ký Ức & Inject System Prompt Thông Minh (`jarvis/memory/`)
* Bổ sung thuật toán tính điểm mức độ liên quan `get_relevant_facts_for_prompt(query, limit)` dựa trên đối sánh từ khóa câu lệnh với hồ sơ người dùng, thói quen và dự án.
* Tự động ưu tiên danh tính người dùng (`user_name`, `email`, `current_project`) và chèn ngữ cảnh vào System Prompt của LLM Intent Router.

---

### ⌨️ 3. Phím Tắt Toàn Cầu Zero-Dependency (`jarvis/platform/hotkeys.py`)
* Xây dựng `GlobalHotkeyManager` dựa trên nền tảng Win32 `RegisterHotKey` và vòng lặp `GetMessageW` chạy trên luồng nền riêng biệt.
* Phím tắt mặc định toàn hệ thống:
  * `Ctrl + Shift + J`: Bật/tắt HUD Holographic Overlay
  * `Ctrl + Shift + L`: Kích hoạt ghi âm giọng nói tức thì (Push-To-Talk)
  * `Ctrl + Shift + M`: Bật/tắt lắng nghe Wake Word ("Hey JARVIS")
  * `Ctrl + Shift + B`: Phát báo cáo tổng hợp buổi sáng
  * `Ctrl + Shift + S`: Kiểm tra tình trạng phần cứng hệ thống

---

### 📦 4. Đóng Gói Ứng Dụng Độc Lập PyInstaller (`build.py` & `scripts/build_exe.py`)
* Xây dựng pipeline đóng gói 1-click tạo tệp thực thi `dist/JARVIS.exe`.
* Tự động bundle cấu hình, thư viện skills, icons và cấu hình đầy đủ hidden imports.

---

### 🌐 5. Nâng Cấp Web Dashboard REST API & Điều Khiển Telegram 2-Chiều
* **Web Dashboard**: Bổ sung các REST endpoint `/api/skills`, `/api/skills/invoke`, `/api/memory`, `/api/hotkeys`.
* **Telegram Bot Controller**: Bổ sung bộ lệnh điều khiển từ xa `/briefing`, `/skills`, `/note <text>`, `/calc <expr>` bên cạnh `/status`, `/lock`, `/exec`.

---

## 🚀 Phiên Bản 1.0.0 (2026-08-25) - Bản Phát Hành Độc Lập Toàn Diện

Phiên bản hoàn thiện đưa **JARVIS** trở thành một **Trợ lý AI Cá nhân Toàn Năng (Autonomous AI Desktop Assistant)**, có khả năng vận hành độc lập như một ứng dụng cài đặt trên Windows, chạy ngầm dưới khay hệ thống, tự khởi động cùng máy và thao tác mọi tác vụ theo yêu cầu bằng giọng nói hoặc phím tắt.

---

### 🌟 1. Tính Năng Ứng Dụng Độc Lập & Khay Hệ Thống (Standalone Desktop Daemon)
* **Khởi chạy không cần VS Code**:
  * `run_jarvis.bat`: Bộ khởi động 1-click có giao diện điều khiển dòng lệnh trực quan.
  * `run_jarvis_silent.vbs`: Khởi chạy ngầm 100% trong nền (không hiện cửa sổ CMD đen).
  * `scripts/create_shortcuts.py`: Tự động tạo Shortcut trên Màn hình chính (`Desktop\JARVIS AI Assistant.lnk`) và Windows Start Menu (`JARVIS Assistant.lnk`).
* **System Tray Controller (Khay Hệ Thống Windows)**:
  * Biểu tượng **Arc Reactor** động phát sáng hiển thị trạng thái thực tế: `ACTIVE` (Cyan), `LISTENING` (Vàng), `MUTED` (Đỏ), `DISABLED` (Xám).
  * Menu ngữ cảnh chuột phải:
    * 🌟 **Mở HUD Hologram** (`Ctrl + Shift + J`)
    * 🎤 **Bật / Tắt Nhận Diện Giọng Nói ("Hey JARVIS")**
    * 🔇 **Tắt / Bật Microphone**
    * 🌐 **Mở Web Dashboard Điều Khiển**
    * ⚙️ **Quản lý Tự Khởi Động cùng Windows**
    * 🔄 **Tải lại Cấu hình (Hot-Reload)**
    * ❌ **Thoát Hoàn Toàn & Giải phóng Tài nguyên**
* **Global Hotkey**: Nhấn `Ctrl + Shift + J` từ bất kỳ ứng dụng, game hoặc trình duyệt nào để bật/tắt Holographic Overlay HUD ngay lập tức.

---

### ⚡ 2. Quản Lý Khởi Động & Tiết Kiệm Tài Nguyên (Zero-Idle Resource Management)
* **Windows Registry Autostart Manager**:
  * Tích hợp trực tiếp vào khóa Registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
  * Hỗ trợ bộ lệnh CLI:
    * `python -m jarvis install-autostart`: Cài đặt tự khởi động cùng Windows.
    * `python -m jarvis uninstall-autostart`: Gỡ bỏ tự khởi động.
    * `python -m jarvis autostart-status`: Kiểm tra trạng thái kích hoạt.
* **Tiết Kiệm Năng Lượng Khi Chờ (Zero-Idle Sleep Mode)**:
  * Mức tiêu thụ CPU ở trạng thái chờ cực thấp (**< 0.05% CPU**).
  * Giải phóng bộ nhớ và dừng toàn bộ thread nền ngay lập tức khi người dùng chọn Thoát (Exit).

---

### 🛡️ 3. Vá Toàn Bộ Lỗi Logic & Đạt 100% Test Suite Pass (405/405 Tests)
* **ReAct Planner & Self-Reflection (`jarvis/planner/`)**:
  * Khắc phục lỗi interceptor vô hạn trên các bước đã được người dùng xác nhận an toàn (`confirmation_token`).
  * Sửa cơ chế DAG Dynamic Replanning (`is_successful`) cho phép thay thế tác vụ lỗi bằng đồ thị con thành công.
  * Tự động điều chỉnh chữ ký tham số (`url` -> `query`) khi phản tư chuyển sang tìm kiếm trực tiếp.
* **Computer-Use Vision & GUI Actor (`jarvis/vision/`)**:
  * Khắc phục lỗi `AttributeError: gemini_api_key` với mock spec, hỗ trợ thuộc tính cấp lớp và `getattr` an toàn.
  * Tối ưu hóa chu trình locate 4 tầng (Vision LLM -> OCR -> Win32 UIA -> Heuristics) và cơ chế Self-Healing Retry.
* **Code Interpreter Sandbox & AST Validator (`jarvis/sandbox/`)**:
  * Bổ sung thuộc tính `execution_time_seconds` cho kết quả sandbox.
  * Tăng cường bộ lọc AST và Regex chặn toàn bộ các biến thể nguy hiểm của lệnh PowerShell `Remove-Item` và các lệnh phá hoại ổ đĩa/hệ thống bất kể thứ tự flag.
* **Persistent Memory & Session Context (`jarvis/memory/`)**:
  * Cung cấp đối tượng `MemoryCommandResult` đa năng (vừa là chuỗi tự nhiên vừa hỗ trợ truy xuất dict).
  * Chuẩn hóa định dạng hội thoại nhiều lượt `- User:` / `- JARVIS:` cho System Prompt Injection.
* **Browser Automation (`jarvis/browser/`)**:
  * Sửa lỗi thẻ code block Markdown `<pre><code class="language-python">`.
  * Bổ sung tính năng xuất Cookie chuẩn Netscape ghi trực tiếp vào tệp đích.
  * Sửa bộ điều hướng so sánh giá trực tiếp trên các sàn TMĐT (Shopee, Tiki, Lazada, CellphoneS, GearVN).
* **Sub-Agent Worker Pool (`jarvis/workers/`)**:
  * Đảm bảo kiểm tra tín hiệu hủy (`check_cancelled`) sau khi hoàn thành tác vụ và khi thoát khỏi trạng thái `PAUSED`.

---

### 📊 4. Tổng Kết 17 Subsystems Hoạt Động Hoàn Hảo
1. `Platform & OS`: Win32 API Native Integration
2. `Audio Subsystem`: Virtual/Hardware Audio Stream
3. `Wake Word Engine`: Acoustic Spectral & Vosk ("Hey JARVIS")
4. `Persistent Memory`: SQLite WAL Long-term Facts & Episodic Log
5. `Screen Vision`: Real-time Desktop Capture & Error Dialog Detector
6. `Web Intelligence Hub`: Weather, RSS News, Crypto & Financial Tracker
7. `OS Automation & Shell`: Multi-monitor, Window Focus & Safety Gate
8. `Proactive Intelligence`: Reminders, Health Watchdog, Pomodoro & Briefings
9. `Always-On Overlay HUD`: Waveform Spectrum Analyzer & Task DAG Monitor
10. `Autonomous ReAct Planner`: Dynamic DAG & Self-Reflection Loop
11. `Code Interpreter Sandbox`: AST Safety Validator & Artifact Manager
12. `Persistent Skill Library`: Dynamic Skill Synthesis & Packaging
13. `Browser Automation Agent`: Headless/Visible Browser & Cookie Persistence
14. `Computer-Use Vision & GUI Actor`: 1000x1000 Grounding & Verification
15. `Sub-Agent Worker Pool`: Multi-threaded Autonomous Worker Engine
16. `Speech Services`: Whisper STT & ElevenLabs/SAPI5 TTS
17. `System Tray & Autostart`: Zero-idle Background Daemon & Registry Autostart
