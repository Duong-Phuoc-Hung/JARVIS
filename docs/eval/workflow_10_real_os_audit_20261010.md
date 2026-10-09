# Audit runner 10-workflow Real OS — 2026-10-10

Verdict: **artifact cũ INVALID / runner PASS engineering / release gate PENDING**.

## Vì sao báo cáo 8/10 cũ không hợp lệ

`10_workflow_real_os_report.json` ngày 2026-10-09 không chạy đúng 10 workflow
Beta trong protocol. Nó thay bằng system status, active window, clipboard, file
search, memory, sandbox và routine inspection. Runner còn:

- gắn `PASS runtime` chỉ từ `success=True`, không yêu cầu side-effect evidence;
- chấp nhận active window `hwnd=0`, title rỗng;
- ghi nội dung clipboard và kết quả có `.env` vào report;
- lệnh volume `query` trả thông điệp đã điều chỉnh volume;
- lệnh routine `list` lại tạo một routine mới;
- coi fail-closed là đủ để `overall_status=PASS`.

Vì vậy con số **8/10 runtime** bị vô hiệu hóa. JSON gốc được giữ nguyên làm audit
trail, không được dùng để đóng release gate.

## Refactor bằng Antigravity và kết quả review

Task `JARVIS-WORKFLOW-AUDIT-01` dùng `Gemini 3.6 Flash (High)`, một lượt triển
khai và hai vòng refactor. Candidate hiện có:

- đúng 10 domain Beta;
- validator objective evidence theo từng workflow;
- mặc định không dispatch workflow; `--execute` mới cho phép side effect;
- report redaction, collision-safe và release gate luôn `PENDING`;
- Result status chuẩn và exit code khác 0 nếu smoke chưa đủ 10/10;
- **37 unit tests pass** sau review bổ sung.

Review ban đầu phát hiện preflight gọi `JarvisApp.initialize()` và khởi chạy
Playwright browser, Telegram polling, global hotkeys cùng voice/wake subsystem.
Follow-up `JARVIS-WORKFLOW-PREFLIGHT-FIX1` đã thay bằng seam in-memory: chỉ tạo
`JarvisApp` chưa initialize, đăng ký core action definitions và Spotify action
definition, không dispatch hoặc start/stop runtime. Candidate đạt 41 unit tests
và preflight thật không có log subsystem cấm.

## Bằng chứng hiện tại

| Kiểm tra | Kết quả | Verdict |
|---|---:|---|
| Runner preflight FIX1 | 41 passed / 5.52s | PASS engineering scoped |
| Clock/runaway focused | 92 passed + 25 subtests / 34.20s | PASS engineering scoped |
| Empirical clock regression | 8 passed / 20.30s | PASS engineering scoped |
| Security scanner | 210 files, 69.684 lines, 0 findings / 1.44s | PASS static audit |
| Real preflight | 10/10 seams, exit 0, 0 forbidden subsystem log | PASS engineering only |
| Non-mutating preflight | không initialize/stop/dispatch runtime | PASS requirement |
| Full unit | 2.903 passed, 3 skipped, 0 failed (2.906 collected) | PASS engineering |
| E2E | 269 passed, 21 skipped, 0 failed (290 collected) | PASS engineering |
| Full repository | 4.415 passed, 47 skipped, 268 subtests, 0 failed / 15:32 | PASS engineering |
| 200 real-voice trials | chưa chạy | PENDING |

## Hướng sửa tiếp theo

Phần runner và regression đã đóng ở tầng engineering. Clock guard hiện được
inject theo instance, không còn phụ thuộc iterator global hoặc thứ tự gọi clock
của dispatcher/telemetry. Gate runtime vẫn yêu cầu 200 trial real voice với
resource thật; full-green bằng mock/fixture không thay thế gate này.
