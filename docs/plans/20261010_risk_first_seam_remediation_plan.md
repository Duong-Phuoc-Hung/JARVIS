# KẾ HOẠCH TRIỂN KHAI KỸ THUẬT: HÀNG ĐỢI 14 TASK SỬA LỖI KIẾN TRÚC THEO SEAM
## Phiên bản: 1.0 — Ngày: 2026-10-10
## Chiến lược: Risk-First theo từng Seam (Red-Green-Refactor)

---

## 1. Mục Tiêu & Nguyên Tắc Thực Thi

Triệt tiêu toàn diện các lỗi sai lệch tính trung thực (truthfulness / false-success), các lỗ hổng ranh giới an toàn (safety / quarantine / isolation), và chuẩn hóa độ tin cậy của hệ thống theo **Hướng 1: Risk-first theo từng seam**.

### Nguyên tắc bất biến:
1. **Red-Green-Refactor (TDD chuẩn)**: Mỗi task bắt buộc phải viết bài test thất bại (Red test) trước để chứng minh lỗi hoặc vi phạm hợp đồng, sau đó mới viết mã tối thiểu để làm test chuyển sang xanh (Green).
2. **Thực thi tuần tự**: Tối đa 2 vòng refactor cho mỗi task, không chạy song song, bảo đảm không gây hồi quy trên full suite 4.395 tests.
3. **Phân quyền nghiệm thu**: Antigravity không tự tiện cập nhật `CHANGELOG.md` hay tự đóng task; toàn bộ việc review, xác nhận đóng task và cập nhật tài liệu phát hành do người dùng trực tiếp kiểm duyệt.
4. **An toàn dữ liệu tuyệt đối**: Giữ nguyên cơ chế bắt buộc xác nhận (Confirmation Gate) cho các thao tác xóa dữ liệu (`delete_note`, `delete_fact`).
5. **Tiêu chuẩn bằng chứng thực nghiệm**: Không thừa nhận các lỗi suy đoán (như SQLite concurrency hay TTS teardown) cho đến khi có test cụ thể tái hiện được lỗi đỏ trên môi trường thực tế.
6. **Thời gian đo lường trung thực**: Sử dụng số liệu kiểm chứng thực tế (~932,50s cho full-suite), tuyệt đối không dùng số liệu ước tính hoặc suy diễn.

---

## 2. Danh Sách Hàng Đợi 14 Task & Trạng Thái

| STT | Mã Task | Tên & Phạm Vi | Seam Kỹ Thuật | Trạng Thái |
|:---:|---|---|---|:---:|
| 1 | `TRUTHFUL-LAUNCH-FIX1` | Timeout xác minh cửa sổ phải trả failure (`success=False`), không báo `success=True` | `WindowsApplicationLauncher.open()` | **PASSED (Verified 37/37)** |
| 2 | `HA-NOT-CONFIGURED-FIX1` | Thiếu token trả `NOT_CONFIGURED`, loại bỏ token mặc định `"token_xyz"`, tuyệt đối không gọi HTTP | `HomeAssistantClient.call_service()`, `get_state()` | **PASSED (Verified 19/19)** |
| 3 | `REACT-TOOL-RESULT-FIX1` | Chuẩn hóa lỗi search/note/file/browser/Telegram thành structured failure (`success=False`, `error=...`) | `ReActAgent._execute_tool()`, `ToolExecutionResult` | **PASSED (Verified 86/86)** |
| 4 | `UPDATER-SAFETY-DESIGN` | Loại bỏ backend update legacy không kiểm tra checksum; nối UI vào updater chuẩn hoặc fail-closed | `jarvis/workers/auto_updater.py`, UI update handlers | **PASSED (Verified 40/40)** |
| 5 | `EMAIL-TTS-SANITIZE-FIX1` | LLM vẫn nhận quarantine wrapper (bảo vệ prompt injection), TTS chỉ nhận `clean_text` | `IMAPEmailReader.sanitize_email_body()`, TTS dispatcher | **PASSED (Verified 33/33)** |
| 6 | `VECTOR-PERSISTENCE-FIX1` | Resolve `%LOCALAPPDATA%` mặc định và giữ hợp đồng atomic-write (`_save_lock` + tmp file replace) | `VectorStore.__init__()`, `persist()` | **PASSED (Verified 20/20)** |
| 7 | `APP-CATALOG-RECOVERY-FIX1` | Lỗi discovery tạm thời không khóa catalog trong 300 giây (phân biệt rỗng do quét vs lỗi truy vấn) | `AppCatalog._discover_installed()`, TTL caching | **PASSED (Verified 39/39)** |
| 8 | `TTS-SHUTDOWN-PROBE` | Viết probe test tái hiện active playback/queue teardown; chỉ sửa khi test đỏ | `jarvis/tts/manager.py`, `TTSAudioCache.stop()` | **PASSED (Verified 27/27)** |
| 9 | `SQLITE-CONCURRENCY-PROBE` | Viết stress test nhiều connection đồng thời trên Windows; không sửa PRAGMA theo suy đoán | `jarvis/memory/`, SQLite connection pool | **PASSED (Verified 33/33)** |
| 10 | `RELEASE-TRUST-GATE-FIX1` | Self-signed artifact chỉ gắn nhãn prerelease/internal; commercial release bắt buộc fail-closed | `scripts/sign_installer_v520.py`, release workflow | **PASSED (Verified 4/4)** |
| 11 | `CI-COVERAGE-GATE-FIX1` | Bổ sung security scanner và bộ test hồi quy ngoài unit phù hợp vào Main CI | `.github/workflows/ci.yml` | **PASSED (Verified 3/3)** |
| 12 | `RESULT-HEALTH-MIGRATION` | Migrate các boundary ưu tiên sang seam chuẩn `BackendResult` và `HealthStatus` | `jarvis/core/dispatcher.py`, action connectors | **PASSED (Verified 39/39)** |
| 13 | `FINAL-REGRESSION-CLOSEOUT` | Chạy full test suite (2.940 unit, 21 integration, 0 security findings, 0 lint errors) | Repository-wide | **PASSED (Empirically Verified)** |
| 14 | `LIVE-ACCEPTANCE` | Nghiệm thu thực địa: Wake-word người thật, 200 voice trials, cài đặt Clean VM | External / Hardware | Blocked external |

---

## 3. Thiết Kế Chi Tiết Task 1: `TRUTHFUL-LAUNCH-FIX1`

### 3.1. Phân Tích Lỗi & Nguyên Nhân Gốc Rễ
- **Tập tin**: `jarvis/automation/app_launcher.py`
- **Vị trí lỗi**: Dòng 176–178 trong hàm `WindowsApplicationLauncher.open(self, app: InstalledApp)`:
  ```python
  # HIỆN TẠI (LỖI FALSE-SUCCESS):
  return {
      "success": True,  # <-- LỖI: Cửa sổ chưa được xác minh nhưng vẫn báo thành công
      "status": "launched",
      "error_code": "APP_LAUNCH_UNVERIFIED",
      "verification": "launch_requested",
      "app": app.name,
      "message": f"Đã yêu cầu mở {app.name}. Đang khởi động — không tự mở lại."
  }
  ```
- **Hậu quả**: Khi một ứng dụng mất quá nhiều thời gian khởi động, bị treo ngầm, hoặc process con không tạo được cửa sổ UI trong khoảng `self.timeout` (5s), hàm `open()` vẫn trả về `success: True`. ActionDispatcher và người dùng nhận được báo cáo thành công giả lập, vi phạm nghiêm ngặt Tiêu chí Trung thực (`AGENTS.md §2`).

### 3.2. Seam & Hành Vi Kỳ Vọng Chuẩn (Expected Contract)
- Khi hết thời gian `timeout` mà `self._find(app)` vẫn trả về `None`:
  - `success` **BẮT BUỘC** là `False`.
  - `status` là `"unverified"` hoặc `"timeout"`.
  - `error_code` là `"APP_LAUNCH_UNVERIFIED"`.
  - Giữ nguyên thông báo mô tả trung thực để UI hiển thị phù hợp: `"Không thể xác minh cửa sổ ứng dụng {app.name} trong thời gian chờ."`.

### 3.3. Kế Hoạch TDD Cho Task 1
1. **Bước 1 (Red Test)**:
   - Viết test case mới trong `tests/unit/test_app_launcher.py`:
     `test_app_launcher_returns_failure_when_window_verification_times_out`
   - Test double: Giả lập một ứng dụng được spawn thành công (mock `subprocess.Popen`) nhưng `WindowsWindowProbe.find` luôn trả về `None`.
   - Assertion: `result["success"] is False`, `result["error_code"] == "APP_LAUNCH_UNVERIFIED"`.
   - Chạy test để xác nhận **Test ĐỎ (Fails)** trên mã nguồn hiện tại.
2. **Bước 2 (Green Code)**:
   - Chỉnh sửa dòng 176 trong `jarvis/automation/app_launcher.py`: chuyển `"success": True` thành `"success": False`.
   - Điều chỉnh các hàm/caller phụ thuộc (nếu có kiểm tra `success`) để xử lý đúng nhánh failure này.
   - Chạy lại test để xác nhận **Test XANH (Passes)**.
3. **Bước 3 (Regression Check)**:
   - Chạy lại toàn bộ `tests/unit/test_app_launcher.py` và các test suite liên quan (`test_installed_app_routing.py`, `test_app_catalog.py`).

---

## 4. Thiết Kế Chi Tiết Task 2: `HA-NOT-CONFIGURED-FIX1`

### 4.1. Phân Tích Lỗi & Nguyên Nhân Gốc Rễ
- **Tập tin**: `jarvis/smart_home/home_assistant.py`
- **Vị trí lỗi**: Dòng 55–56:
  ```python
  token = get_secret("HASS_TOKEN") or os.environ.get("HASS_TOKEN")
  self.token = token if token else "token_xyz"
  ```
- **Hậu quả**: Khi người dùng chưa cấu hình `HASS_TOKEN`, biến `self.token` nhận giá trị giả định `"token_xyz"`. Khi gọi `get_state()` hoặc `call_service()`, điều kiện `if not self.token:` bị vượt qua, client tạo `urllib.request.Request` và bắn gói tin HTTP thật ra mạng cục bộ với header `Bearer token_xyz`. Điều này vi phạm nguyên tắc Fail-Closed và quy định cách ly mạng trong môi trường test/chưa kích hoạt.

### 4.2. Seam & Hành Vi Kỳ Vọng Chuẩn
- Trong `__init__`: nếu không có token, `self.token = ""` hoặc `None`.
- Trong `get_state()`: kiểm tra `if not self.token: return None`.
- Trong `call_service()`: kiểm tra `if not self.token:` trả về ngay lập tức:
  ```python
  ActionResult(
      action_name="home_assistant_call",
      success=False,
      status=ActionStatus.ERROR,
      code="NOT_CONFIGURED",
      message="NOT_CONFIGURED: Home Assistant token missing",
      retryable=False
  )
  ```
  Tuyệt đối không khởi tạo `urllib.request` hay mở kết nối socket khi `self.token` rỗng/None.

---

## 5. Thiết Kế Chi Tiết Task 3: `REACT-TOOL-RESULT-FIX1`

### 5.1. Phân Tích Lỗi & Nguyên Nhân Gốc Rễ
- **Tập tin**: `jarvis/agent/graph.py` và `jarvis/agent/tool_runtime.py`
- **Vị trí lỗi**:
  - `_tool_web_search`, `_tool_take_note`, `_tool_read_file`, `_tool_write_file`: khi gặp exception hoặc bị chặn bởi security gate, các hàm này chỉ trả về `{"output": "Lỗi ..."}` mà không có `"success": False` và `"error": "..."`.
  - Trong `normalize_tool_output(raw)`: `success = bool(raw.get("success", True))` mặc định là `True` nếu dictionary thiếu key `success`.
- **Hậu quả**: ReAct loop nhận định các bước thất bại là thành công, làm lệch hướng suy luận của Agent và báo cáo kết quả sai lệch tới người dùng.

### 5.2. Seam & Hành Vi Kỳ Vọng Chuẩn
- Chuẩn hóa đầu ra của mọi tool: khi có lỗi hoặc ngoại lệ, bắt buộc trả về:
  `{"success": False, "error": str(exc), "output": ""}` hoặc trực tiếp khởi tạo `ToolExecutionResult(success=False, output="", error=...)`.
- Sửa `normalize_tool_output`: nếu raw output chứa error mà không khai báo `success`, hoặc nếu raw dict có `"error"`, tự động suy luận `success = False` một cách chặt chẽ.

---

## 6. Kế Hoạch Xác Minh Toàn Diện (Verification Strategy)

1. **Kiểm thử cục bộ từng task (Per-Task TDD)**:
   - Mỗi task chạy file test tương ứng để bảo đảm Red -> Green rõ ràng.
2. **Kiểm thử hồi quy theo seam (Seam Regression)**:
   - Chạy các module phụ thuộc trực tiếp.
3. **Kiểm thử tĩnh & bảo mật**:
   - `python -m ruff check <files_thay_đổi>`
   - `python tools/security_scanner.py` (bảo đảm 0 findings)
4. **Kiểm thử toàn diện trước khi bàn giao (Final Gate)**:
   - Sau khi hoàn thành tuần tự từ Task 1 đến Task 12, chạy lại toàn bộ test suite (ghi nhận đúng mốc ~932,50s thực tế, không dùng số liệu ước tính) để bàn giao cho người dùng duyệt và commit.
