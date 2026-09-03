# 🤖 JARVIS — Trợ Lý AI Cá Nhân Tự Trị Cho Windows

<div align="center">

[![CI Status](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/workflows/ci.yml/badge.svg)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)
[![Tests](https://img.shields.io/badge/tests-passing-00ff88?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)
[![Source Version](https://img.shields.io/badge/source%20version-5.0.0-purple?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/blob/main/pyproject.toml)
[![Releases](https://img.shields.io/badge/releases-GitHub-blue?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/releases)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue?style=flat-square)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11%2064--bit-0078D4?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)

**JARVIS** là hệ thống trợ lý AI cá nhân tự trị (Autonomous AI Desktop Assistant) chạy nền trên Windows 11/10 64-bit, lấy cảm hứng từ trợ lý JARVIS của Tony Stark trong Iron Man. 
JARVIS có khả năng nhận diện giọng nói offline tiếng Việt & tiếng Anh, tự động phân luồng ý định thông minh, tự động viết mã mở rộng kỹ năng (Self-Coding), ghi nhớ ngữ nghĩa theo thời gian thực (Semantic RAG Memory), điều khiển toàn diện hệ thống Windows, tự động hóa trình duyệt qua Playwright CDP và kết nối điều khiển từ xa qua Telegram, Zalo OA và Discord.

<sub>**Phiên bản mã nguồn / phát triển (source/runtime, `jarvis.__version__`): 5.0.0** trên `main` — đánh dấu mốc phát triển J.A.R.V.I.S. Terminal Control Center (đã merge vào `main` qua PR #37), mở rộng bề mặt sản phẩm lớn, không có thay đổi phá vỡ tương thích nào với lệnh/cấu hình/API hiện có. **`v5.0.0` đã được gắn tag chính thức và GitHub Release "JARVIS v5.0.0" đã publish vào 2026-09-03** (release workflow chạy thành công, đính kèm file `JARVIS_v5.0.0_windows_x64.zip`) — đây hiện là bản phát hành chính thức mới nhất, kế tiếp `v4.5.1`. **Bản phát hành chính thức (GitHub Release):** luôn xem [trang Releases](https://github.com/Duong-Phuoc-Hung/JARVIS/releases) để biết bản mới nhất thực tế tại thời điểm bạn đọc — tài liệu này ghi lại một mốc kiểm tra tại một thời điểm cụ thể, không phải một con số cập nhật tự động. Lịch sử phát triển trong CHANGELOG đã đến mốc **v5.0.0 — J.A.R.V.I.S. Terminal Control Center** trên `main` (kế thừa mốc v4.7.0 — Sprint 2 Acoustic & UX Hardening, cộng thêm mốc bảo trì sau v4.7.0 sửa lỗi báo cáo thiếu trung thực của self-healing và làm tất định test wake-word Whisper trên CI). Với bản phát hành này, phiên bản mã nguồn/phát triển và bản phát hành chính thức trùng khớp (`5.0.0` = `v5.0.0`) — đây là một sự hội tụ có chủ đích của chủ sở hữu dự án, không phải quy tắc chung; hai khái niệm này vẫn có thể lệch nhau trở lại ở các mốc phát triển tiếp theo.</sub>

</div>

---

## 📋 Mục Lục

1. [✨ Tính Năng Nổi Bật](#-tính-năng-nổi-bật)
2. [💻 Yêu Cầu Hệ Thống (Prerequisites)](#-yêu-cầu-hệ-thống-prerequisites)
3. [🚀 Hướng Dẫn Cài Đặt Từng Bước (Step-by-Step Installation)](#-hướng-dẫn-cài-đặt-từng-bước-step-by-step-installation)
4. [⚡ Dành Cho Người Dùng Cuối — Quick Start (Standalone ZIP)](#-dành-cho-người-dùng-cuối--quick-start-standalone-zip)
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

### 🎙️ Nhận Diện Giọng Nói Offline & Voice Pipeline (v4.8.1)
- **Wake Word:** Nhận diện từ khóa *"Hey JARVIS"* tức thì với độ trễ cực thấp.
- **Barge-in (Ngắt lời tức thời):** Khi JARVIS đang nói, bạn có thể nói chèn vào — hệ thống lập tức tắt âm thanh TTS và chuyển sang nghe lệnh mới.
- **VAD (Voice Activity Detection):** Thuật toán phát hiện giọng nói thông minh bằng năng lượng RMS hoặc WebRTC VAD — xử lý offline, độ trễ <10ms.
- **STT (Speech-to-Text) & Safe Diacritic Normalization (v4.8.1):** Faster-Whisper (CTranslate2) chạy offline với bộ chuẩn hóa bỏ dấu đa âm an toàn (`strip_vietnamese_diacritics`) bảo vệ nguyên vẹn từ đơn, triệt tiêu 100% va chạm homophone (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`, `tắt` vs `tắc`).
- **Kháng Lệch Ngữ Âm (Phonetic Drift Robustness):** Tích hợp 15 alias ngữ âm chọn lọc cho các lỗi nghe nhầm đặc thù của Faster-Whisper (`tắc máy`, `tập máy tính`, `cái đặt`, `đặt time`, `tắc tính`, `tắt tính`, `ghi chú`), nâng độ chính xác thực tế trên 90 audio test lên 63.3% và đạt 100% trên tập held-out mới.
- **TTS (Text-to-Speech):** Piper TTS offline mượt mà tự nhiên (<80ms) cùng tùy chọn kết nối ElevenLabs chất lượng studio.

### 🧠 Router Ý Định 3 Lớp Thông Minh (3-Tier Intent Router)
- **Regex & Rule Fast-Path:** Nhận diện ngay lập tức hơn 150+ mẫu câu lệnh tiếng Việt không cần gọi LLM (zero-latency, 0 token), tự động hỗ trợ cả có dấu, không dấu và biến thể ngữ âm.
- **Project & Workspace Assistant:** Quản lý dự án, chuẩn bị workspace, tạo project, liệt kê thư mục và theo dõi Git thông minh.
- **Fallback Gemini LLM:** Phân tích ý định phức tạp qua Google Gemini 1.5 Flash / Pro khi không khớp rule.
- **Autonomous ReAct Agent:** Tự động lập kế hoạch (Plan), thực thi công cụ (Act), quan sát (Observe) và phản hồi (Reflect).

### 🧬 Tự Sinh Kỹ Năng Mới (Self-Coding Skills)
- Nói *"JARVIS, tạo kỹ năng theo dõi giá vàng"* → JARVIS tự thiết kế interface, viết code Python, kiểm tra cú pháp (`py_compile`), chạy smoke test và đăng ký trực tiếp vào hệ thống trong <15 giây.

### 🔍 Bộ Nhớ Ngữ Nghĩa (Semantic Memory & RAG)
- Tự động lưu trữ nhật ký hội thoại, ghi chú và tài liệu vào SQLite vector store (TF-IDF BM25 & Cosine Similarity) hoàn toàn offline.
- Tìm kiếm ký ức theo ngữ nghĩa: *"Hôm qua tôi nói gì về kế hoạch dự án?"*

### 🌐 Tự Động Hóa Trình Duyệt & Hệ Thống
- Điều khiển Chrome trực tiếp qua giao thức Playwright CDP (Chrome DevTools Protocol).
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

## ⚡ Dành Cho Người Dùng Cuối — Quick Start (Standalone ZIP)

Nếu bạn không muốn cài đặt Python hoặc cấu hình dòng lệnh, bạn có thể sử dụng bản đóng gói độc lập (standalone `.exe` trong file ZIP — đây là artifact thật mà GitHub Actions release workflow phát hành; không có bộ cài đặt Setup Wizard đi kèm release chính thức):

1. **Tải Bản Đóng Gói:**
   - Truy cập [Releases Page](https://github.com/Duong-Phuoc-Hung/JARVIS/releases) và tải file ZIP của bản phát hành mới nhất — tên file luôn theo định dạng `JARVIS_v<phiên bản>_windows_x64.zip` (ví dụ `JARVIS_v5.0.0_windows_x64.zip`, bản phát hành chính thức mới nhất tính đến thời điểm viết tài liệu này — luôn kiểm tra trang Releases để biết bản mới nhất thực tế).
2. **Giải Nén & Chạy:**
   - Giải nén file ZIP vào thư mục bạn muốn (ví dụ: `C:\Program Files\JARVIS` hoặc bất kỳ thư mục nào).
   - Double-click `JARVIS.exe`, hoặc chạy `JARVIS.exe --tray` để khởi động thẳng vào khay hệ thống.
   - (Tùy chọn) Tự tạo shortcut ngoài Desktop hoặc thêm vào Startup folder của Windows nếu muốn tự động khởi động cùng máy — bản ZIP không tự làm việc này thay bạn.
3. **Cấu Hình API Key:**
   - Điền Gemini API Key trong cửa sổ Settings ban đầu hoặc lưu vào `%LOCALAPPDATA%\JARVIS\.env`.
4. **Sử Dụng Ngay:**
   - Mở `JARVIS.exe` từ thư mục đã giải nén, hoặc từ shortcut bạn tự tạo.
   - JARVIS sẽ chạy ngầm dưới khay hệ thống, không hiển thị cửa sổ console gây phiền toái.

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
```

### Chạy bộ kiểm thử (Running Test Suites)

JARVIS bao gồm hơn 630+ bài kiểm thử tự động toàn diện:

```powershell
# Chạy toàn bộ test suites:
pytest tests/

# Chạy kiểm thử kèm báo cáo độ bao phủ mã nguồn (Coverage Report):
pytest tests/ --cov=jarvis --cov-report=term-missing

# Chạy kiểm thử riêng cho bộ nhận diện Intent Router:
pytest tests/test_router_project_intents.py -v
```

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

# 2. Đóng gói thành file cài đặt Windows Installer dist/installer/JARVIS_Setup_v5.0.0.exe
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
| 12| 🔍 **Tìm Ký Ức RAG** | `rag_search` | *"Tuần trước tôi nói gì về dự án X?"* | Tìm kiếm thông tin trong bộ nhớ ngữ nghĩa dài hạn |
| 13| 🧬 **Tự Viết Kỹ Năng** | `skill_synthesizer`| *"Tạo kỹ năng theo dõi giá vàng"* | Tự động viết code Python và nạp kỹ năng mới trong <15s |
| 14| 🌙 **Night Planner** | `night_planner` | *"Tối nay phân tích các file log"* | Thực hiện tác vụ nặng ban đêm và báo cáo lúc sáng |
| 15| 🏠 **Nhà Thông Minh** | `smart_home_discovery`| *"Quét thiết bị nhà thông minh"* | Quét mDNS và điều khiển Home Assistant / Tasmota |
| 16| 🌐 **Điều Khiển Browser**| `browser_control`| *"Mở YouTube tìm bài hát Iron Man"* | Điều khiển trình duyệt Chrome qua Playwright CDP |
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
│  🌐 Playwright CDP Automation          📊 Health Diagnostics           │
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
