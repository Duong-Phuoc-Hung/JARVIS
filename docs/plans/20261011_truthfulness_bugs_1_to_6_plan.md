# KẾ HOẠCH TRIỂN KHAI: KHẮC PHỤC 6 LỖ HỔNG TRUTHFULNESS & SAFETY (BUGS 1-6)

## Phiên bản: 1.0 — Ngày: 2026-10-11

## Nhánh: fix/truthfulness-bugs-1-to-6

---

## 1. Danh Sách Nhiệm Vụ (Todos)

- [x] **Branch & File Inspection**: Tạo nhánh mới `fix/truthfulness-bugs-1-to-6`, đọc và thẩm tra toàn bộ các file liên quan.
- [x] **BUG-1**: Sửa `WebhookPlugin.send_payload false-success`:
  - Trả về `BackendResult.failure` khi mạng lỗi, URL không hợp lệ hoặc HTTP non-200.
  - Sửa `tests/test_empirical_challenger_m2.py` (loại bỏ assertion cũ `assert res.success is True` khi mạng lỗi).
- [x] **BUG-2**: Sửa truncation thẻ quarantine trong `email_imap.py`:
  - Đảm bảo việc cắt tỉa nội dung luôn thực hiện trên `clean_text` trước khi bọc thẻ XML quarantine.
  - Thêm test case xác minh email 10.000 ký tự luôn kết thúc với thẻ đóng `</email_quarantine>`.
- [x] **BUG-3**: Sửa `_inspect_dict_failure` trong `jarvis/agent/tool_runtime.py`:
  - Tôn trọng trường `success` hoặc `ok` tường minh khi có giá trị `True`, không để lỗi suy diễn sai từ status/nested data; bổ sung `'timeout'` vào danh sách failure statuses.
- [x] **BUG-4**: Sửa race enqueue-vs-drain trong `TTSManager`:
  - Khóa đồng bộ `self._lock` xuyên suốt kiểm tra và đưa vào hàng đợi `_queue.put()` trong `speak()`.
  - Hút sạch hàng đợi (drain queue) an toàn dưới khóa trong `stop()`, triệt tiêu khả năng enqueue sau khi drain; phân định rõ `stop()` và `shutdown()`.
- [x] **BUG-5**: Vô hiệu hóa legacy auto-apply updater trong `jarvis/workers/auto_updater.py`:
  - Khóa cờ `self.auto_apply = False`, ghi log cảnh báo bảo mật khi có yêu cầu auto-apply legacy git pull.
  - Loại bỏ hoàn toàn khả năng tự động chạy updater không có xác thực SHA-256 trong background loop.
- [x] **BUG-6**: Sửa status `'unverified'` -> `'timeout'` trong `WindowsApplicationLauncher.open()`:
  - Trả về `"status": "timeout"` khi hết thời gian chờ `self.timeout`.
  - Cập nhật các bài test liên quan trong `test_app_catalog.py` và `test_app_launcher.py`.
- [x] **Kiểm thử**: Viết test mới và cập nhật test cho cả 6 bug fixes.
- [x] **Xác minh toàn diện**:
  - Chạy per-task tests cho 6 bug fixes.
  - Chạy `python -m ruff check`: 0 errors.
  - Chạy `python tools/security_scanner.py`: 0 findings.
  - Chạy full unit suite regression: 2,978 passed, 3 skipped trong 462.27s (100% green).
- [x] **Đồng bộ tài liệu & Commit**:
  - Cập nhật `CHANGELOG.md`.
  - Cập nhật `CLAUDE.md`.
  - Cập nhật `README.md`, `docs/PROJECT_STATE.md`, `docs/ROADMAP.md`.
  - Thực hiện git commit trên nhánh `fix/truthfulness-bugs-1-to-6`.
