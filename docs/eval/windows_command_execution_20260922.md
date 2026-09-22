# Windows command correctness — 2026-09-22

Phạm vi người dùng chốt: chức năng trên Windows trước, thiết bị ngoài qua ứng dụng
sau, Home Assistant cuối cùng. Đây là bản vá giới hạn, không phải hoàn tất toàn bộ yêu cầu.
Source version 5.2.1; các thay đổi chưa commit. Không dùng số 2.458 tests của revision
trước để chứng nhận revision này.

## Thay đổi và bằng chứng

| Đường xử lý | Đã sửa | Giới hạn |
|---|---|---|
| Website controller | Giữ path/query case, bỏ command prefix, encode query, kiểm tra URL/port | Chỉ HTTP(S), từ chối URL chứa credentials |
| Browser execution | False/exception trả BROWSER_OPEN_FAILED, bỏ shell fallback | True chỉ là browser launch acknowledged, không chứng minh page load |
| App resolver | Alias chính xác, không khớp chuỗi con | App chưa nhận diện phải có alias hoặc executable tìm được |
| App/web handlers | Không dùng success message khi lỗi; giữ error_code | Chưa migration toàn hệ thống sang Result model chung |
| Router | Explicit URL và encode hai Google search rules | Chưa giải quyết mọi negation, ambiguity, input dài |

TDD: 11 tests đầu thất bại trước bản vá; thêm regression substring app, ba ca
router→handler và domain có port đều đã quan sát RED trước khi sửa. Test browser
exception bảo vệ không fallback shell. Tổng file mới: 17 cases.

Lệnh scoped:

```powershell
.venv\Scripts\python -m pytest tests/unit/test_windows_command_targets.py tests/unit/test_h07_voice_app_intents.py tests/unit/test_app_web_dedupe_stress.py tests/unit/test_computer_control.py -o addopts='' -q --tb=short --junitxml=reports/evidence/windows_command_scoped_20260922.xml
```

Kết quả: **76 passed, 25 subtests passed / 10,15s**, exit 0. JUnit có thể gộp subtests
vào count; không diễn giải count XML thành số test functions.
Evidence: `reports/evidence/windows_command_scoped_20260922.xml`.
Verdict: **PASS engineering / PASS fail-closed (scoped)**, **runtime PENDING**.
Không mở browser/app thật, không gọi thiết bị, không bật live credentials.

Full-suite diagnostic sau sửa code:

```powershell
.venv\Scripts\python -m pytest tests -o addopts='' -q --maxfail=1 --tb=short --junitxml=reports/evidence/windows_command_full_20260922.xml
```

**182 passed, 1 failed, 23 skipped / 32,21s**, exit 1. Dừng ở lỗi đầu tiên,
không phải chỉ còn một lỗi trong toàn dự án. Lỗi: `test_r2_r3_vision_zero_size_roi_or_corrupt_bytes`,
`jarvis/vision/screen.py:230` cố lưu JPEG từ ảnh rỗng (`cannot write empty image`).
Evidence: `reports/evidence/windows_command_full_20260922.xml`.
Review độc lập xác nhận hai lỗi tích hợp (router query/port domain) đã sửa;
reviewer chạy riêng 17 tests mới xanh. `git diff --check` exit 0 (có cảnh báo LF/CRLF).

## Còn phải làm

1. Sửa lỗi full-suite và chạy lại đầy đủ trước commit/push main.
2. Kiểm tra command→dispatcher→OS với ứng dụng/site người dùng chọn, quan sát đúng
   cửa sổ/page; không suy ra từ mock hay browser boolean.
3. Bổ sung regression cho câu phủ định, nhiều mục tiêu, input quá dài; không để
   cắt input làm đổi URL/hành động. Chưa tuyên bố mọi câu lệnh đều an toàn/chính xác.
4. Tiếp tục 10 workflow real OS, voice live, clean-machine install/update/rollback,
   code signing và các gate còn mở trong audit trước.

**Product release: NO-GO.** Chưa commit/push do full suite chưa đạt điều kiện.
