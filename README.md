# 🤖 JARVIS — Trợ Lý AI Cá Nhân Tự Trị Cho Windows

<div align="center">

[![CI Status](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/workflows/ci.yml/badge.svg)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)
[![Tests](https://img.shields.io/badge/tests-passing-00ff88?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)
[![Source Version](https://img.shields.io/badge/source%20version-5.2.0-purple?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/blob/main/pyproject.toml)
[![Releases](https://img.shields.io/badge/releases-GitHub-blue?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/releases)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue?style=flat-square)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11%2064--bit-0078D4?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)

**JARVIS** là hệ thống trợ lý AI cá nhân tự trị (Autonomous AI Desktop Assistant) chạy nền trên Windows 11/10 64-bit, lấy cảm hứng từ trợ lý JARVIS của Tony Stark trong Iron Man. 
JARVIS có khả năng nhận diện giọng nói offline tiếng Việt & tiếng Anh, tự động phân luồng ý định thông minh, tự động viết mã mở rộng kỹ năng (Self-Coding với Sandbox Dry-Run), ghi nhớ nhật ký và tìm kiếm từ vựng thời gian thực (Lexical / TF-IDF Search Memory), điều khiển toàn diện hệ thống Windows, tự động hóa trình duyệt bằng Chromium do Playwright quản lý hoặc phiên Chromium được attach qua CDP, và kết nối điều khiển từ xa qua Telegram, Zalo OA và Discord.

<sub>**Phiên bản chính thức (Beta GO Release, `jarvis.__version__`): 5.2.0** trên `main` — hoàn thiện toàn diện phân hệ Core / Backend / Integrations / Release (D-01..D-17), Voice Pipeline Hardening (H-01..H-13), và giải quyết dứt điểm toàn bộ 8 technical blockers R1–R8: Planner Fail-Closed loại bỏ hoàn toàn simulated success, mô hình kết quả thống nhất `ActionResult` chuẩn 4 trường, từ vựng sức khỏe chuẩn hóa 5 trạng thái (`READY`, `LIMITED`, `BLOCKED`, `ERROR`, `UNAVAILABLE`), Safety Gate Interceptor bảo vệ hành vi outbound (Email, Zalo, Discord) và Home Assistant, Discord Inbound Gateway với snowflake tracking và whitelist, cơ chế Feature Flag Core/Labs cách ly tính năng thử nghiệm, danh mục bằng chứng thực nghiệm runtime (R7a–R7e), và báo cáo Beta GO toàn diện. Toàn bộ 2,383+ regression tests xanh 100%.</sub>


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
- **Barge-in (Ngắt lời tức thời):** Khi JARVIS đang nói, bạn có thể nói chèn vào — hệ thống lập tức tắt âm thanh TTS và chuyển sang nghe lệnh mới.
- **VAD (Voice Activity Detection):** Thuật toán phát hiện giọng nói thông minh bằng năng lượng RMS hoặc WebRTC VAD — xử lý offline, độ trễ <10ms.
- **WASAPI Exclusive Capture Fallback (Windows):** Tự động kích hoạt cơ chế WASAPI Exclusive mode khi thiết bị Bluetooth HFP (AirPods, tai nghe đàm thoại) gặp lỗi chiếm dụng phiên độc quyền Windows OS (`PaError -9999`), ghi âm trực tiếp tại tầng kernel ở tần số 16kHz native.
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

### 🛡️ Cơ Chế An Toàn & Chuẩn Hóa Hệ Thống (Beta GO Hardening)
- **Planner Fail-Closed (R1):** Loại bỏ hoàn toàn mô phỏng thành công (`simulated: True`). Mọi action không tìm thấy handler đều lập tức trả về lỗi chính thức `HANDLER_NOT_FOUND`, bảo toàn trạng thái lỗi thực từ các handler cấp dưới.
- **Chuẩn Hóa Kết Quả Thực Thi `ActionResult` (R2):** Thống nhất mô hình dữ liệu trả về trên toàn hệ thống gồm 4 trường chuẩn: `status` (`ActionStatus`), `code`, `message`, `retryable` cùng cơ chế mapping emulation (`__getitem__`, `get`, `__contains__`) và đồng bộ 2 chiều tương thích ngược cho Home Assistant, Mobile Bridge, VM Orchestrator.
- **Từ Vựng Trạng Thái Hệ Thống 5 Cấp Chuẩn Hóa (R3):** Chuẩn hóa `StatusLevel` trên Terminal Control Center và tất cả 9 module adapters về đúng 5 trạng thái: `READY`, `LIMITED`, `BLOCKED`, `ERROR`, `UNAVAILABLE`, triệt tiêu hoàn toàn sự phân mảnh trạng thái phi chuẩn.
- **Safety Interceptor & Xác Nhận Hành Động Rủi Ro Cao (R4):** Mở rộng nhóm `HIGH_RISK_ACTIONS` bao quát toàn bộ hành động gửi tin/email ra ngoài (Email, Zalo, Discord) và cơ cấu kích hoạt thiết bị Home Assistant (turn on/off, toggle, set temp). Bắt buộc người dùng phê duyệt qua token xác nhận 30s trước khi thực thi; các truy vấn chỉ đọc (read-only) được tự động phân tách an toàn và chạy không trễ.
- **Discord Inbound Gateway (R5):** Tiếp nhận lệnh từ xa qua cơ chế REST polling với channel snowflake tracking (`&after=`), tự động dừng an toàn khi gặp mã lỗi HTTP chí mạng (401, 403, 404) hoặc đạt ngưỡng lỗi liên tiếp, enforce danh sách trắng `whitelist_user_ids` và ghi nhật ký kiểm toán băm SHA-256.
- **Cơ Chế Feature Flag Core/Labs (R6):** Tách bạch chặt chẽ giữa tính năng lõi ổn định và tính năng thử nghiệm (browser CDP, TShark packet capture) qua cấu hình `labs.enabled` và `labs.features`. Mọi lệnh gọi tới tính năng Labs chưa kích hoạt bị từ chối fail-closed với `ActionResult(status=LABS_DISABLED)`.
- **Hồ Sơ Bằng Chứng Thực Nghiệm Runtime (R7):** Bộ tài liệu kiểm toán thực tế độc lập tại `docs/eval/` cho 5 phân hệ: TShark (`TOOL_NOT_FOUND`), Browser E2E (21 Chromium seams), IMAP (`PENDING_CREDENTIALS`), Home Assistant (`UNAVAILABLE`), và Authenticode Installer v5.2.0, tuân thủ 100% nguyên tắc trung thực (Anti-Fabrication).
- **Báo Cáo Beta GO Toàn Diện (R8):** Tổng hợp kiểm toán toàn diện 8 blockers tại `docs/BETA_GO_REPORT.md` với phán quyết chính thức `CONDITIONAL GO / BETA GO`.

---

## 💻 Yêu Cầu Hệ Thống (Prerequisites)

Trước khi cài đặt, vui lòng đảm bảo máy tính của bạn đáp ứng các yêu cầu sau:

| Thành phần | Yêu cầu tối thiểu | Chi tiết & Link tải chính thức |
|---|---|---|
| **Hệ điều hành** | Windows 11 / 10 (64-bit) | Build 19041 trở lên (Hỗ trợ Win32 API & System Tray) |
| **Python** | **Python 3.13+ (64-bit)** | Tải tại: [Python 3.13.2 64-bit](https://www.python.org/downloads/release/python-3132/)<br>⚠️ **Bắt buộc:** Tích chọn ✅ **"Add python.exe to PATH"** trong màn hình cài đặt đầu tiên. |
| **Git** | Git for Windows | Tải tại: [Git for Windows Official](https://git-scm.com/download/win) |
| **Visual C++ Runtime** | VC++ 2015–2022 Redistributable (x64) | Tải tại: [vc_redist.x64.exe (Microsoft)](https://aka.ms/vs/17/release/vc_redist.x64.exe)<br>*(Bắt buộc cho Pillow, sounddevice, CTranslate2, faster-whisper)* |
| **Phần cứng âm thanh** | Microphone & Loa / Tai nghe | Đảm bảo micro và loa hoạt động bình thường trong Windows Settings. Hỗ trợ tự động WASAPI Exclusive fallback cho tai nghe Bluetooth HFP (AirPods, v.v.). |
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
1. Tải file ZIP `JARVIS_v5.1.0_windows_x64.zip` từ trang Releases.
2. Giải nén vào thư mục tùy chọn (ví dụ: `D:\JARVIS\`).
3. Chạy `JARVIS.exe` hoặc `JARVIS.exe --tray`.

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

JARVIS bao gồm hơn 2.000 bài kiểm thử tự động cùng các bộ kiểm chuẩn chuyên biệt cho Product Beta v1 và browser automation:

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

Dưới đây là 6 lỗi phổ biến nhất và giải pháp xử lý triệt để:

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

### 6. ❌ Lỗi micro Bluetooth HFP / PaError -9999 (Windows Exclusive Session)
- **Hiện tượng:** Tai nghe Bluetooth đàm thoại (AirPods, tai nghe HFP) không thu được âm thanh hoặc báo lỗi `PaError -9999` (`paDeviceUnavailable`).
- **Nguyên nhân:** Windows OS Session Manager tự động chiếm giữ phiên đàm thoại Bluetooth HFP ở chế độ độc quyền, khiến PortAudio mặc định bị từ chối truy cập qua Shared mode.
- **Cách khắc phục:**
  1. JARVIS v5.1.10 đã tích hợp tự động cơ chế **WASAPI Exclusive Capture Fallback**: hệ thống tự động nhận biết lỗi PortAudio và mở luồng ghi âm kernel WASAPI Exclusive trực tiếp tại tần số 16kHz mono.
  2. Đảm bảo cấu hình `audio.use_wasapi_exclusive = True` trong config (mặc định đã bật).
  3. Nếu tai nghe vẫn không thu âm được, kiểm tra kết nối Bluetooth trong Windows Settings và đảm bảo tai nghe đang ở profile *Hands-free AG Audio*.

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

