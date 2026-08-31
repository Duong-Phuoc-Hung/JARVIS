# Original User Request

## 2026-08-31T05:34:01Z

Sửa 3 lỗi còn tồn tại trong JARVIS v4.1.x — một AI voice assistant chạy trên Windows 11 64-bit Python 3.13, codebase tại `d:\Software GitCode\JARVIS`.

Working directory: `d:\Software GitCode\JARVIS`
Integrity mode: benchmark

---

## Requirements

### R1. Intent Recognition — Project & Workspace Commands

`jarvis/llm/router.py` phải nhận diện và route đúng các lệnh liên quan đến quản lý dự án / workspace. Hiện tại tất cả những lệnh này đang trả về `unknown_intent`.

Phạm vi cần nhận diện (tất cả):
- Mở / chuyển sang dự án: "mở dự án X", "switch sang project Y", "chuyển workspace"
- Tạo dự án/workspace mới: "tạo project mới", "tạo workspace tên ABC"
- Liệt kê dự án: "liệt kê dự án", "show projects", "các project đang có"
- Lệnh git liên quan: "git status dự án", "commit dự án", "push project"

Phải thêm intent rules vào `rule_engine` hoặc `_regex_rules` theo đúng kiến trúc hiện có, không tạo hệ thống routing mới.

### R2. Suppress Admin CMD / PowerShell Flash — Toàn bộ Codebase

Mọi subprocess/PowerShell/CMD được JARVIS spawn phải chạy ẩn hoàn toàn — không được để cửa sổ console hiện ra trước mặt người dùng trong bất kỳ tình huống nào:
- Khi JARVIS khởi động
- Liên tục khi chạy nền (CPU/temp polling, health check, proactive engine)
- Khi chạy installer (JARVIS_Setup_v4.1.1.exe)

Tất cả `subprocess.Popen`, `subprocess.run`, `subprocess.call`, `os.system` trong toàn bộ thư mục `jarvis/` và `scripts/` trên Windows phải dùng `creationflags=CREATE_NO_WINDOW` (hoặc `startupinfo` với `STARTF_USESHOWWINDOW` / `SW_HIDE`).

### R3. Rewrite README.md — Complete Installation Guide

Viết lại toàn bộ mục Installation trong `README.md` từ đầu, đủ chính xác để người dùng mới hoàn toàn có thể cài thành công trên Windows 11 mà không cần hỗ trợ thêm.

Nội dung bắt buộc:
- **Prerequisites rõ ràng**: Python 3.13 (link download), Git, Visual C++ Redistributable, Windows 11/10 64-bit
- **Các bước theo đúng thứ tự**: clone → venv → pip install → cấu hình API key → chạy lần đầu
- **Common Errors & Fix**: ít nhất 5 lỗi phổ biến (SQLite path, PIL/Pillow, faster-whisper model download, UAC/admin rights, API key 401)
- **Quick Start** cho người dùng cuối (chỉ dùng installer .exe, không cần Python)
- **Dev Setup** cho developer (clone + venv)

---

## Acceptance Criteria

### R1 — Intent Recognition

- [ ] `router.parse_intent("mở dự án jarvis", force_llm=False).action_name` ≠ `"unknown_intent"` và ≠ `"generic_llm_response"`
- [ ] `router.parse_intent("tạo workspace mới", force_llm=False).action_name` ≠ `"unknown_intent"`
- [ ] `router.parse_intent("liệt kê project", force_llm=False).action_name` ≠ `"unknown_intent"`
- [ ] `router.parse_intent("git status dự án", force_llm=False).action_name` ≠ `"unknown_intent"`
- [ ] Tất cả tests hiện có trong `tests/` vẫn pass (không gây regression)
- [ ] Thêm ít nhất 5 test cases mới cho project/workspace intents

### R2 — No Console Flash

- [ ] Chạy lệnh: `Select-String -Path "jarvis\**\*.py","scripts\**\*.py" -Pattern "subprocess\.(Popen|run|call|check_output)" -Recurse` → mọi match đều có `CREATE_NO_WINDOW` hoặc `startupinfo` trong cùng lời gọi đó (kiểm tra trong vòng 5 dòng xung quanh)
- [ ] `os.system(` không xuất hiện trong `jarvis/` (hoặc nếu có phải được wrap)
- [ ] Chạy JARVIS trong 60 giây: không có cửa sổ console nào pop lên

### R3 — README Installation

- [ ] Có section "Quick Start (End User)" với các bước dùng installer .exe
- [ ] Có section "Developer Setup" với đủ bước từ `git clone` đến `python -m jarvis`
- [ ] Có section "Prerequisites" nêu rõ Python 3.13+, Windows 11/10, Git
- [ ] Có section "Common Errors" với ít nhất 5 lỗi + cách fix
- [ ] Một người đọc README lần đầu có thể cài thành công mà không cần hỏi thêm
