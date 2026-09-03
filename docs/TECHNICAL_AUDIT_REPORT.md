# BÁO CÁO KIỂM TOÁN KỸ THUẬT TỔNG HỢP — DỰ ÁN JARVIS ASSISTANT
### Tổng hợp toàn bộ quá trình audit qua 13 vòng phản biện kỹ thuật độc lập

---

## 0. TÓM TẮT ĐIỀU HÀNH (EXECUTIVE SUMMARY)

Dự án JARVIS đã trải qua một quá trình audit đối kháng (adversarial audit) hiếm thấy về độ sâu: 13 vòng trao đổi, mỗi vòng phát hiện một lỗ hổng cụ thể trong mã nguồn hoặc trong chính lập luận bảo mật, và mỗi vòng đều được đội ngũ phát triển xử lý bằng bằng chứng thực nghiệm thay vì chỉ khẳng định suông. Đây là điểm khác biệt lớn nhất so với báo cáo tự đánh giá ban đầu.

**Kết quả cốt lõi:**
- ✅ **Ranh giới bảo mật cấp Kernel đã đạt được thật sự** cho 2 trong 3 vector đe dọa chính: chặn spawn tiến trình con (Job Object) và chống ghi/phá hoại file (Mandatory Integrity Control).
- 🟡 **Ranh giới network vẫn ở tầng ứng dụng** — đã thu hẹp đáng kể qua nhiều lớp phòng thủ, nhưng chưa có ranh giới kernel được xác nhận end-to-end (AppContainer mới dừng ở bước tạo profile, chưa xác nhận tiến trình con chạy được và bị chặn mạng thật).
- ⚠️ **Một số phân hệ (Computer Vision, Browser Automation) chưa hề qua audit** — mọi đánh giá về chúng hiện tại là suy đoán, không có bằng chứng.
- ⚠️ **Benchmark hiệu năng đã tách bạch đúng** số liệu đo thật (AST, Sandbox overhead, SAPI5 TTS) khỏi số liệu mock (STT, một phần TTS Cloud) — đây là điểm mạnh cần giữ.

---

## 1. PHƯƠNG PHÁP LUẬN ĐÃ ÁP DỤNG (VÀ NÊN TIẾP TỤC DUY TRÌ)

Xuyên suốt quá trình, các nguyên tắc sau đã được chứng minh là hiệu quả và nên trở thành **quy chuẩn cố định** cho mọi audit tương lai của dự án:

| Nguyên tắc | Vì sao quan trọng |
|---|---|
| **Phân tầng 3 mức (Tier 1/2/3) thay vì điểm % hoặc /10** | % và điểm số tạo cảm giác chính xác giả; phân tầng buộc phải nêu rõ *loại* giới hạn (mock vs thật, kernel vs ứng dụng) |
| **Mọi tuyên bố bảo mật phải có test đối kháng (red-team) thật, không mock** | Đã phát hiện ít nhất 6 lỗ hổng mà unit test thông thường không thể phát hiện (`__closure__`, `io.open` bypass, `win32api.LoadLibrary`, precached module...) |
| **Blocklist luôn thua kém Allowlist trong hệ thống mở** | Áp dụng đúng cho `mobile_bridge.py` (đuôi file) — nên áp dụng lại cho việc đọc file trong sandbox và cho danh sách module |
| **"Đã chặn" phải phân biệt Kernel-Enforced vs Application-Layer** | Đây là phân biệt quan trọng nhất rút ra được: chỉ ranh giới kernel (MIC, Job Object) mới miễn nhiễm với reflection của Python |
| **Benchmark phải ghi rõ điều kiện đo (mock/thật)** | Tránh lặp lại lỗi ban đầu của báo cáo gốc — số liệu đẹp không có bằng chứng |

---

## 2. PHÂN LOẠI 3 TẦNG TRƯỞNG THÀNH — CẬP NHẬT SAU TOÀN BỘ AUDIT

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 🟢 TIER 1 — ĐÃ KIỂM CHỨNG BẰNG TEST ĐỐI KHÁNG THẬT (KERNEL-ENFORCED)      │
├──────────────────────────────────────────────────────────────────────────┤
│ • Chặn spawn tiến trình con      → Windows Job Object (ActiveProcessLimit=1)│
│ • Chống ghi/phá hoại file         → Windows MIC (TokenIntegrityLevel=LOW)  │
│ • Environment secret scrubbing    → Xác nhận 0 API key trong process con  │
│ • Zalo webhook signature          → HMAC constant-time, hex/base64 đúng   │
│ • Mobile Bridge file upload       → Explicit allowlist + double-ext check │
│ • AST Validator                   → Static analysis, latency <0.21ms      │
│ • TaskDAG / ReAct Planner         → Logic thuần bộ nhớ, test bao phủ tốt  │
│ • SQLite Store                    → Transaction, schema migration ổn định │
│ • CI/CD Pipeline & Packaging      → PyInstaller build thành công 4 jobs   │
├──────────────────────────────────────────────────────────────────────────┤
│ 🟡 TIER 2 — CHỨC NĂNG ĐÚNG NHƯNG PHỤ THUỘC MOCK / CHƯA CHỨNG MINH ĐẦY ĐỦ  │
├──────────────────────────────────────────────────────────────────────────┤
│ • Network isolation cho Sandbox   → Application-layer, AppContainer mới  │
│                                      ở mức "API khả thi", chưa end-to-end │
│ • STT (Faster-Whisper)            → Số liệu hiện tại là mock adapter,    │
│                                      chưa đo với model thật              │
│ • Audio VAD/Full-duplex           → Test bằng sóng sin toán học, chưa    │
│                                      test micro/loa thật, tiếng ồn thật  │
│ • HUD Overlay (Tkinter)           → Test headless, chưa test DPI scaling │
│ • Chrome CDP Controller           → Mock trong CI, chưa test session     │
│                                      thật kế thừa cookies                │
│ • TTS ElevenLabs                  → Phụ thuộc mạng/API bên ngoài         │
├──────────────────────────────────────────────────────────────────────────┤
│ 🔴 TIER 3 — CHƯA QUA AUDIT / RỦI RO KIẾN TRÚC CHƯA XỬ LÝ                 │
├──────────────────────────────────────────────────────────────────────────┤
│ • Computer Vision (Face/Emotion/YOLO/OCR) → 0 bằng chứng, 0 test nhắc tới│
│   trong toàn bộ 13 vòng audit — mọi số liệu FPS là suy đoán              │
│ • Browser Automation (Playwright)  → Chỉ có mô tả định tính, không có    │
│   test case hay số liệu cụ thể nào được trình bày                       │
│ • Vector Store "RAG"               → Xác nhận là TF-IDF lexical search,  │
│   không phải semantic embedding — cần định danh lại, không gọi là RAG   │
│ • Windows Code Signing              → Chưa có, SmartScreen sẽ cảnh báo   │
│ • Skill Synthesizer (AI tự viết code) → Đã cô lập process/file, NHƯNG    │
│   network vẫn có thể exfiltrate qua vector chưa đóng hoàn toàn           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. CHI TIẾT RANH GIỚI BẢO MẬT — TRẠNG THÁI THẬT SAU 13 VÒNG

### 3.1. Đã đóng hoàn toàn (Kernel-level, độc lập với code Python chạy trong sandbox)

| Vector đe dọa | Cơ chế chặn | Bằng chứng |
|---|---|---|
| Spawn tiến trình con (`cmd.exe`, `powershell.exe`) | Job Object `ActiveProcessLimit=1` | Test thật: `WinError 1816` khi thử spawn |
| Ghi/xóa file ngoài sandbox, kể cả bằng `io.open`/`os.open`/hàm gốc lấy qua `__closure__` | MIC `TokenIntegrityLevel=LOW` + SACL `S:(ML;OICI;NW;;;LW)` | Test thật: `[Errno 13]` từ kernel SRM, không phụ thuộc Python |
| Đọc `.env`/secrets qua biến môi trường | Scrubbed Environment | Test thật: quét `os.environ`, xác nhận 0 leaked keys |
| Reflection/dynamic import né AST (`getattr`, `__subclasses__`, `ctypes`, `win32api.LoadLibrary`) | Two-tier `sys.modules` poisoning + `sys.meta_path[0]` prefix wildcard matcher | Test đối kháng: 15/15 kịch bản né tránh đã biết đều bị chặn |
| Import ngược package `jarvis` để lấy hàm gốc | Blocklist tên `jarvis` + `sys.path` stripping | Test thật xác nhận |
| Giấu hàm gốc khỏi introspection (`__closure__`, `__globals__` qua instance) | Callable class + `__getattribute__` override | Test thật xác nhận (nhưng xem 3.2 — còn đường vòng qua class-level) |

### 3.2. Còn lỗ hổng đã biết nhưng CHƯA vá (cần xử lý ngay)

| # | Lỗ hổng | Mức độ | Cách khai thác |
|---|---|---|---|
| 1 | `type(open).__call__.__globals__` lộ hàm gốc qua truy cập ở tầng **class**, không qua instance | 🔴 Cao | `type(builtins.open).__call__.__globals__['_orig_builtin_open']` — bỏ qua toàn bộ `__getattribute__` override vì đây là class-level access, không phải instance-level |
| 2 | Đây là giới hạn **vật lý của CPython** (đã được đội ngũ xác nhận đúng): không thể vừa giữ hàm hoạt động vừa xóa biến khỏi `__globals__` vì Python tra cứu tên tại thời điểm gọi | — | Không có cách vá thuần Python; cần chuyển guard sang C-extension biên dịch sẵn, hoặc chấp nhận đây là giới hạn của lớp phòng thủ ứng dụng (đã ghi nhận đúng trong tài liệu) |

### 3.3. Network — trạng thái thật, chưa nên coi là "đã giải quyết"

- Đã xác nhận **B1**: `CreateAppContainerProfile` chạy được dưới quyền user thường (HRESULT 0x0).
- **CHƯA xác nhận B2**: một tiến trình `python.exe` thực sự khởi động dưới token AppContainer đó, và khi gọi `socket.connect()` từ bên trong, có thực sự bị chặn hay không.
- Rào cản thực tế đã biết: cần cấp ACE `ALL APPLICATION PACKAGES` cho toàn bộ cây nhị phân CPython + `.pyd` — nếu chưa làm, tiến trình con AppContainer nhiều khả năng **crash khi khởi động** (lỗi truy cập, không liên quan gì tới code AI viết gì).
- **Kết luận trung thực hiện tại**: Network vẫn đang được bảo vệ chủ yếu bằng prefix wildcard matcher ở tầng ứng dụng (Python) — đây là phòng thủ tốt, thu hẹp bề mặt tấn công đáng kể, nhưng **không phải ranh giới kernel** như file/process đã đạt được.

---

## 4. TÌNH TRẠNG BENCHMARK HIỆU NĂNG — PHÂN BIỆT RÕ THẬT/MOCK

### 4.1. Số liệu đo thật, đáng tin cậy

| Hạng mục | p50 | Ghi chú |
|---|---|---|
| AST Validator (code phức tạp) | 0.21 ms | Static analysis, không phụ thuộc phần cứng ngoài CPU |
| Khởi tạo Sandbox (Job Object + MIC Token) | ~170–195 ms | Chi phí cố định mỗi lần gọi skill AI-synthesized; dao động do system jitter, **cần đo lại ở trạng thái máy idle để xác nhận baseline ổn định** |
| SAPI5 TTS (đồng bộ, PCM thật) | 22.79 ms (33 ký tự) → 141.79 ms (239 ký tự) | Đo bằng `SpMemoryStream`, có kiểm tra dung lượng PCM sinh ra — đáng tin |

### 4.2. Số liệu hiện là mock/pipeline-adapter — KHÔNG được dùng để công bố hiệu năng thật

| Hạng mục | Trạng thái | Việc cần làm |
|---|---|---|
| STT Faster-Whisper | Đo qua adapter pass-through, chưa nạp model CTranslate2 thật | Chạy lại **không** set `JARVIS_MOCK_AUDIO=1`, dùng model `base int8` thật, đo trên audio buffer thật |
| TTS ElevenLabs | Chưa có số liệu độ trễ mạng thật | Đo round-trip thật, bao gồm cả trường hợp cache miss |
| Computer Vision (YOLO, Face) | Không có script benchmark nào được trình bày | Cần xây benchmark riêng trước khi công bố FPS |

---

## 5. LỘ TRÌNH NÂNG CẤP — ƯU TIÊN THEO MỨC ĐỘ RỦI RO VÀ CHI PHÍ

### 🔴 Ưu tiên 1 — Bảo mật cốt lõi còn hở (nên làm ngay, trước khi release)

1. **Xác nhận end-to-end AppContainer (B2)**
   - Cấp ACE `ALL APPLICATION PACKAGES` cho thư mục cài Python + `jarvis/`.
   - Dùng `UpdateProcThreadAttribute` với `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` để gán AppContainer token khi `CreateProcessAsUserW`.
   - Viết test đối kháng thật: khởi động tiến trình con dưới AppContainer, gọi `socket.create_connection(('8.8.8.8', 53))`, xác nhận bị chặn — không chỉ xác nhận `CreateAppContainerProfile` trả `0x0`.
   - **Cho tới khi có test này pass, tài liệu phải ghi rõ Network = Application-Layer, không phải Kernel-Enforced.**

2. **Vá lỗ hổng `type(open).__call__.__globals__`**
   - Ngắn hạn: chuyển các biến `_orig_*` sang một closure không thể truy cập qua class attribute (ví dụ đóng gói trong một factory function trả về instance đã "đông cứng").
   - Dài hạn: viết guard bằng C-extension nhỏ, biên dịch sẵn (`.pyd`), không tồn tại dưới dạng Python function nên không có `__globals__` để introspect.

3. **Bổ sung firewall/WFP rule làm lớp bổ trợ cho AppContainer**
   - Ngay cả sau khi có AppContainer, nên thêm một lớp fallback: rule tường lửa scope theo path thực thi của tiến trình sandbox con, phòng trường hợp cấu hình AppContainer bị lỗi ở máy người dùng cuối.

### 🟠 Ưu tiên 2 — Đóng khoảng trống benchmark và mở rộng test đối kháng

4. Chạy lại STT/TTS benchmark với model thật (không mock), công bố số liệu RTF thật trên các cấu hình máy tiêu chuẩn (CPU-only, GPU rời).
5. Đo lại Sandbox overhead 3-5 lần ở trạng thái máy idle để xác nhận baseline ổn định (150ms hay 195ms là con số đúng?).
6. Mở rộng bộ test đối kháng `mobile_bridge.py`/`discord.py`/`telegram.py` theo đúng mẫu đã áp dụng cho `zalo.py` (fail-close, timing-safe compare).

### 🟡 Ưu tiên 3 — Audit các phân hệ chưa từng được kiểm tra

7. **Computer Vision** (Face Recognition, Emotion, YOLO, OCR): hiện tại 0% được audit trong toàn bộ quá trình. Cần:
   - Đo FPS thật trên phần cứng cụ thể (không suy đoán).
   - Kiểm tra rủi ro riêng tư: dữ liệu khuôn mặt có được lưu trữ không, có mã hóa không, có gửi ra ngoài không.
8. **Browser Automation** (Playwright/CDP): cần audit riêng vì đây là vector prompt-injection tiềm tàng (đã nêu ở V3 trong threat model ban đầu nhưng chưa có giải pháp cụ thể) — nội dung trang web độc hại có thể chứa chỉ dẫn ẩn đánh lừa AI thực thi hành động ngoài ý muốn người dùng.
9. Định danh lại "Vector Store" thành "Lexical/TF-IDF Search" trong toàn bộ tài liệu người dùng, tránh gây hiểu nhầm là semantic RAG.

### 🟢 Ưu tiên 4 — Cải thiện trải nghiệm & vận hành (không khẩn cấp về bảo mật)

10. Windows Code Signing (Authenticode) để loại bỏ cảnh báo SmartScreen.
11. Local ONNX Embedding (ví dụ `all-MiniLM-L6-v2`) thay thế TF-IDF nếu muốn RAG ngữ nghĩa thật.
12. Tích hợp Windows Credential Manager thay vì lưu API key dạng plaintext trong `.env`.
13. Cơ chế On-demand download cho model AI nặng (Whisper weights, Piper voices) để giảm kích thước installer.

---

## 6. NGUYÊN TẮC TRÌNH BÀY CHO CÁC BÁO CÁO TƯƠNG LAI

Để tránh lặp lại các vấn đề đã gặp ở vòng cuối (điểm số /10 tái xuất hiện, phân hệ chưa audit bị trộn lẫn với phân hệ đã audit kỹ):

- **Không dùng điểm số %/10 cho bất kỳ hạng mục nào** — chỉ dùng Tier 1/2/3 kèm mô tả cụ thể vì sao.
- **Mọi phân hệ chưa có test đối kháng hoặc benchmark thật phải được đánh dấu rõ "CHƯA AUDIT"**, không đặt chung bảng với phân hệ đã kiểm chứng.
- **Không dùng từ "tuyệt đối an toàn"** — thay bằng "đã kiểm chứng qua test đối kháng thực nghiệm, chưa phát hiện đường vòng tại thời điểm audit".
- **Mọi số liệu benchmark phải ghi rõ điều kiện đo** (mock hay thật, có/không có model trọng số, máy nào) ngay trong bảng, không chỉ ở chú thích cuối.

---

## 7. Cập Nhật Trạng Thái Kiểm Toán Bổ Sung (2026-09-02)

> Phần này bổ sung — không thay thế — 13 vòng audit gốc ở trên. Các phát hiện TShark/network/khác
> đã liệt kê ở Mục 3.2–3.3 và Mục 5 **không** bị đóng lại ở đây; 7 hạng mục sau được cập nhật hoặc
> ghi nhận mới, dựa trên bằng chứng nguồn/commit thực tế được đối chiếu trực tiếp trong các phiên
> làm việc liên quan (hạng mục #6/#7 được phát hiện khi xây dựng J.A.R.V.I.S. Terminal Control
> Center trên nhánh `feat/terminal-control-center`, chưa merge).

| # | Phát hiện | Trạng thái | Bằng chứng |
|---|---|:---:|---|
| 1 | **Healing false-success / fabricated recovery** (`jarvis/healing/terminator.py`) — báo cáo thành công chấm dứt tiến trình dù chưa xác nhận thực sự xảy ra, và bịa đặt số liệu RAM đã giải phóng bằng công thức giả lập | ✅ **RESOLVED** — PR #31 | Merge commit `10d470237b0fe4bc295f02215b4606590d79d17e` (feature commit `e24a366d98a38a53f3467e2b8ee17e1d4e44c63e`). Xem `docs/SECURITY_ARCHITECTURE.md` §4 và `CLAUDE.md` §0 cho hợp đồng trung thực (truthfulness contract) đầy đủ. |
| 2 | **Wake-word optional-dependency CI nondeterminism** (`tests/unit/test_wake_word_p0.py`) — test Whisper fallback không tất định giữa môi trường có/không cài `faster-whisper` | ✅ **RESOLVED** — PR #32 — **chỉ là vấn đề test, không phải sửa lỗi hành vi wake-word production** | Merge commit `aaeeb53f834134bb4490147c238e82e863558caa` (feature commit `c70c79384744e1756bc893125cd967c69f2276d8`). Không thay đổi `jarvis/audio/wake_word.py` hay bất kỳ hành vi runtime nào. |
| 3 | **Central dispatch truthfulness** (`ActionDispatcher` / `process_text_command`, `jarvis/core/dispatcher.py` + `jarvis/core/app.py`) — báo cáo sai một kết quả hành động thất bại tường minh thành công | ✅ **RESOLVED — ĐÃ MERGE VÀO `main`** — PR #34 | Merge commit `ae6d5d8ffd98f4629af951e19820bf047f9c05d7` (feature commit `e99c522be808d9160a5b9c57bf9bd8ec11d3dd69`), post-merge CI **#160 SUCCESS** (Syntax Check/Import Validation/Unit Tests/Pipeline Summary đều xanh). Root cause xác nhận: dispatcher bọc mọi kết quả handler trả về bình thường (không exception) thành `success=True` vô điều kiện, bất kể `ActionResult(success=False)`/`{"success": False}`/`{"status": "failed"/"error"}` handler báo hiệu gì; `process_text_command()` không bao giờ đọc lại `action_result.success`. Sửa qua hàm chuẩn hóa dùng chung `_normalize_handler_outcome()` (chỉ nhận diện các quy ước thành công/thất bại đã xác lập qua kiểm toán mã nguồn thực tế — không dùng falsiness chung chung), áp dụng đồng nhất cho cả `dispatch_action()`/`dispatch_action_async()`; `process_text_command()` và `_on_gesture_event()` (`triple_clap`/`clap_pause_clap`/pattern chung) lan truyền `action_result.success` trung thực xuống phản hồi/log/bộ nhớ/sự kiện. An toàn (`SafetyGateInterceptor`, RBAC, `CONFIRMATION_*`) không bị đụng tới. Kiểm chứng: 57 test (`tests/unit/test_dispatch_truthfulness.py`) + `test_action_dispatcher_safety.py` (15) + `test_app_integration.py` (1) đều pass; toàn bộ `tests/unit/` trên `main`: **1413 passed, 1 skipped, 0 failed**. Xem `docs/SECURITY_ARCHITECTURE.md` §5, `CLAUDE.md` §0/§1A, và `docs/PROJECT_STATE.md` checkpoint hiện tại. |
| 4 | **(Phát hiện mới, phát sinh khi kiểm chứng hạng mục #3)** Router/dispatcher action-name mismatch cho truy vấn phần cứng — `jarvis/llm/router.py` định tuyến "Báo cáo tình trạng hệ thống" tới `hardware_status_query`, nhưng `jarvis/core/app.py` chỉ đăng ký `system_status` | ✅ **RESOLVED — ĐÃ MERGE VÀO `main`** — cùng PR #34 (chỉ định trực tiếp từ chủ sở hữu kho mã) | Lỗi có thật, tồn tại từ trước, trước đây bị chính lỗi #3 che giấu (dispatcher cũ luôn báo `success=True`). Theo quyết định của chủ sở hữu: **không** sửa `jarvis/llm/router.py` (hợp đồng router có chủ đích, đa điểm gọi — xem `docs/PROJECT_STATE.md` checkpoint hiện tại để biết đầy đủ các điểm gọi); sửa hẹp bằng cách đăng ký `hardware_status_query` như một alias tương thích trong `jarvis/core/app.py::_register_core_actions()`, dùng lại chính `self._handle_system_status` (không trùng lặp logic, `system_status` giữ nguyên). Kiểm chứng: 5 test mới (`TestHardwareStatusQueryAlias`); `tests/unit/test_integration_e2e.py::test_memory_recording_in_process_text_command` **pass lại mà không sửa file test đó**. Merge commit giống hạng mục #3: `ae6d5d8ffd98f4629af951e19820bf047f9c05d7`. |
| 5 | **Đồng bộ tài liệu sau khi merge hạng mục #3/#4** — các file tài liệu (bao gồm chính báo cáo này) từng mô tả PR #34 là "chưa commit/merge" | ✅ **RESOLVED — tài liệu (docs-only)** — PR #35 | Merge commit `399a70cc471bf35d98e1b976f8c895054d4f7524` (feature commit `a344af1f7b408306d92f781f01a2fc2e5253043d`), post-merge CI **#162 SUCCESS**. Chỉ cập nhật tài liệu — không đổi hành vi hệ thống, không phải một phát hiện bảo mật/kỹ thuật mới, không mở lại hạng mục #3/#4. |
| 6 | **Packet-capture fabrication** (`jarvis/security/scanner.py::PacketCapture.capture_packets()`) — hàm `_build_capture_result()` nội bộ luôn tổng hợp một tỷ lệ phân bổ giao thức TCP/UDP/ICMP cố định (70%/20%/10%) từ tham số `count` yêu cầu, bất kể `tshark` có thực sự chạy thành công hay không, và luôn báo `status="SUCCESS"` — kể cả trên nhánh `except Exception` khi lệnh `tshark` thất bại/timeout | 🔴 **OPEN — CHƯA SỬA** (phát hiện khi xây dựng Terminal UI, cố ý không sửa trong phạm vi công việc đó) | Đường dẫn "thành công" (`scanner.py:633`, không hề parse `proc.stdout` thật) và đường dẫn exception (`scanner.py:638`) đều gọi `_build_capture_result()`, hàm này tính `tcp_count = int(count * 0.70)` v.v. (`scanner.py:648-650`) và trả `status="SUCCESS"` vô điều kiện (`scanner.py:652-661`). Terminal UI (`jarvis/ui/terminal/modules/infosec.py`) không bao giờ gọi hàm này — chỉ báo cáo trạng thái tồn tại của binary `tshark` qua `resolve_tshark_binary()` (đường thật, không fabricate) và luôn hiển thị `LIMITED` kèm giải thích trung thực. Xem `CLAUDE.md`'s "Durable Terminal Control Center invariant" và `docs/PROJECT_STATE.md` checkpoint hiện tại. Sửa `PacketCapture` bản thân nó là công việc riêng, chưa bắt đầu. |
| 7 | **Comms send-truthfulness gap** (`jarvis/comms/telegram.py::send_message()`/`send_photo()`, `jarvis/comms/discord.py::send_message()`/`send_embed()`/`send_file()`) — trả về payload thành công tổng hợp dù không có xác nhận gửi thật | 🔴 **OPEN — CHƯA SỬA** (phát hiện khi xây dựng Terminal UI, cố ý không sửa trong phạm vi công việc đó) | Telegram: khi không có `http_client` thật được gán (luôn đúng với `TelegramBotController()` khởi tạo trần), `send_message()`/`send_photo()` trả `{"ok": True, ...}` tổng hợp (`telegram.py:244-245`, `257-258`) mà không gọi mạng thật. Discord: `send_message()`/`send_embed()` vẫn trả `{"success": True, ...}` ngay cả khi lệnh POST HTTP thật ném exception (`discord.py:318-320`); `send_file()` không hề gọi mạng và vẫn báo thành công. Terminal UI (`jarvis/ui/terminal/modules/comms.py`) không bao giờ gọi các hàm gửi này — các mục "Send Message"/"Send Photo"/"Send Embed" luôn báo `LIMITED` kèm giải thích trung thực, không bao giờ hiển thị "SENT" giả. Sửa các backend gửi tin nhắn bản thân chúng là công việc riêng, chưa bắt đầu. |

Mọi phát hiện khác trong Mục 3–6 phía trên (TShark, network isolation ứng dụng tầng, Computer
Vision chưa audit, Browser Automation chưa audit, v.v.) **giữ nguyên trạng thái như đã ghi** —
không có bằng chứng nguồn mới nào trong phiên làm việc này chứng minh chúng đã được xử lý,
ngoại trừ hạng mục #6/#7 mới được ghi nhận (không phải "đã xử lý" — chỉ là phát hiện mới,
chưa sửa) ở trên.

---

*Báo cáo này tổng hợp nội dung từ 13 vòng trao đổi kỹ thuật, bao gồm các commit: `ec32e4d`, `3039bb4`, `dfa2eaf`, `adab40d`, `40adeeb`, `48cef9b`, `296e49c`, `5c31c3f`, `2ee3669`, `dfffc0e`. Mục 7 (2026-09-02, cập nhật 2026-09-03) bổ sung thêm 7 phát hiện mới ngoài phạm vi 13 vòng gốc — hạng mục #3 (central dispatch truthfulness) và hạng mục #4 (`hardware_status_query` alias) đã được merge vào `main` qua **PR #34** (merge commit `ae6d5d8ffd98f4629af951e19820bf047f9c05d7`, post-merge CI #160 SUCCESS); hạng mục #5 ghi nhận việc đồng bộ tài liệu sau đó qua **PR #35** (merge commit `399a70cc471bf35d98e1b976f8c895054d4f7524`, post-merge CI #162 SUCCESS); hạng mục #6/#7 (2026-09-03, nhánh `feat/terminal-control-center`, chưa merge) ghi nhận hai lỗ hổng trung thực thật, tồn tại từ trước, được phát hiện khi xây dựng J.A.R.V.I.S. Terminal Control Center — cả hai vẫn **OPEN**, cố ý không sửa trong phạm vi công việc UI đó. Mọi merge commit ghi ở đây là bằng chứng lịch sử cho đúng PR đó — không phải tuyên bố "`main` hiện tại"; luôn xác minh `origin/main` thực tế trước khi dựa vào bất kỳ SHA nào trong tài liệu.*
