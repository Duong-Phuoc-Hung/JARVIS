# 🤖 JARVIS — Trợ Lý AI Cá Nhân Tự Trị Cho Windows

<div align="center">

[![CI Status](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/workflows/ci.yml/badge.svg)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)
[![Tests](https://img.shields.io/badge/tests-633%20passed-00ff88?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)
[![Version](https://img.shields.io/badge/version-4.0.0-purple?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/releases)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4?style=flat-square)](README.md)

**JARVIS** là hệ thống trợ lý AI cá nhân tự trị chạy ngầm trên Windows, lấy cảm hứng từ trợ lý JARVIS của Tony Stark trong Iron Man. Không cần mở VS Code hay bất kỳ IDE nào — JARVIS cài đặt như một ứng dụng thật, tự khởi động cùng máy tính, và luôn sẵn sàng phục vụ bằng giọng nói tiếng Việt hoặc qua Telegram/Zalo/Discord.

</div>

---

## 📋 Mục Lục

- [Tính Năng Nổi Bật](#-tính-năng-nổi-bật)
- [Hướng Dẫn Cài Đặt](#-hướng-dẫn-cài-đặt-chi-tiết)
- [Cấu Hình `.env`](#-cấu-hình-env)
- [Danh Sách Kỹ Năng Chi Tiết](#-danh-sách-kỹ-năng-chi-tiết)
- [Điều Khiển Qua Điện Thoại](#-điều-khiển-qua-điện-thoại)
- [Phím Tắt Toàn Hệ Thống](#%EF%B8%8F-phím-tắt-toàn-hệ-thống)
- [Autonomous ReAct Agent](#-autonomous-react-agent)
- [Kiến Trúc Hệ Thống](#-kiến-trúc-hệ-thống)
- [Developer Guide](#-developer-guide)
- [FAQ](#-câu-hỏi-thường-gặp)

---

## ✨ Tính Năng Nổi Bật

### 🎙️ Nhận Diện Giọng Nói Offline & Barge-in
- **Wake word:** Nói *"Hey JARVIS"* từ bất kỳ khoảng cách nào, JARVIS lập tức lắng nghe
- **Barge-in (ngắt lời):** Trong khi JARVIS đang nói, bạn có thể nói chèn vào ngay — JARVIS tự tắt tiếng và nghe lệnh mới
- **VAD (Voice Activity Detection):** Thuật toán phát hiện giọng nói qua năng lượng RMS — không cần internet, độ trễ <10ms
- **STT:** Faster-Whisper chạy hoàn toàn offline, nhận dạng tiếng Việt + tiếng Anh trong <200ms
- **TTS:** Piper TTS offline, giọng nói tự nhiên, phản hồi bằng âm thanh trong <80ms

### 🧠 Intent Router Thông Minh
- **15+ mẫu tiếng Việt** được nhận diện tức thì không qua LLM (zero-latency fast path)
- Ví dụ nhận diện: *"mở"* → app_launcher, *"ghi chú"* → note_taker, *"tính"* → calculator
- **Fallback LLM:** Khi không khớp mẫu, gửi lên Gemini để phân tích ý định
- Độ chính xác: **>95%** trên tập lệnh tiếng Việt thông dụng

### 🧬 Tự Sinh Kỹ Năng Mới (Self-Coding)
- Nói *"JARVIS, tạo kỹ năng theo dõi giá vàng"* → JARVIS viết code Python, kiểm tra syntax, chạy test, đăng ký vào hệ thống — tất cả trong <15 giây
- Kỹ năng tự tổng hợp được lưu tại `~/.jarvis/skills/` và tải lại tự động khi khởi động
- Hỗ trợ mô tả bằng ngôn ngữ tự nhiên: *"kỹ năng gửi email hàng ngày lúc 8h sáng"*

### 🔍 Bộ Nhớ Ngữ Nghĩa (Semantic RAG)
- Lưu trữ ghi chú, hội thoại, và tài liệu vào vector store nội bộ (TF-IDF BM25)
- Tìm kiếm theo nghĩa — không cần nhớ từ khóa chính xác: *"hôm qua tôi nói gì về dự án Alpha?"*
- Hoạt động hoàn toàn offline, không gửi dữ liệu ra ngoài
- Dung lượng: hỗ trợ tới 10.000 entries, truy vấn trong <50ms

### 🌙 Night Shift Worker
- Nhận nhiệm vụ tối: *"tối nay phân tích 50 file code trong src/ cho tôi"*
- JARVIS tự chạy trong khi bạn ngủ, thực hiện các tác vụ nặng (phân tích, tổng hợp, xử lý file)
- 7h sáng: JARVIS chủ động gọi dậy bạn và đọc báo cáo kết quả Markdown

### 🌐 Browser CDP Controller
- Điều khiển Chrome thực bằng giọng nói qua Playwright CDP (Chrome DevTools Protocol)
- Lệnh: *"mở YouTube"*, *"tìm kiếm Python tutorial"*, *"click vào nút Subscribe"*
- *"chụp màn hình trang này"* → ảnh PNG tự động lưu Desktop
- *"trích xuất văn bản trang"* → đọc nội dung trang cho bạn nghe
- Hỗ trợ: scroll, fill form, nhấn phím tắt, đóng tab

### 🔄 Auto-Update Daemon
- Kiểm tra GitHub Releases mỗi 6 giờ tự động
- So sánh phiên bản theo Semantic Versioning (vX.Y.Z)
- Tải về bản mới → backup bản cũ → cài đặt trong nền → thông báo qua toast
- Rollback về phiên bản trước nếu có lỗi: *"JARVIS, khôi phục bản cũ"*

### 🧩 Plugin SDK
- Lập trình viên có thể tạo plugin riêng và phân phối qua pip: `pip install jarvis-plugin-ten`
- JARVIS tự quét `~/.jarvis/plugins/` và `importlib.metadata` khi khởi động
- Mỗi plugin chỉ cần: `metadata.json` + `__init__.py` với hàm `execute(params) → result`

---

## 📥 Hướng Dẫn Cài Đặt Chi Tiết

> Chọn **một trong 3 cách** bên dưới. Khuyên dùng **Cách 3** nếu muốn cài hẳn vào máy.

---

### 🔷 Cách 1 — Chạy Từ Source Code

Dành cho lập trình viên muốn tùy chỉnh hoặc phát triển thêm.

**Bước 1 — Cài Python 3.11**

Tải tại: https://python.org/downloads/release/python-3119/

> ⚠️ **Bắt buộc:** Trong màn hình cài đặt, tích ✅ **"Add Python to PATH"** trước khi nhấn Install.

Kiểm tra sau khi cài xong:
```powershell
python --version
# Kết quả mong đợi: Python 3.11.x
```

**Bước 2 — Tải JARVIS**

```powershell
git clone https://github.com/Duong-Phuoc-Hung/JARVIS.git
cd JARVIS
```

Nếu chưa có Git: tải ZIP tại https://github.com/Duong-Phuoc-Hung/JARVIS → **Code → Download ZIP** → giải nén → mở terminal trong folder.

**Bước 3 — Cài thư viện**

```powershell
pip install -r requirements.txt
```

> ⏳ Mất 2–5 phút. Tải ~200MB.

**Bước 4 — Tạo file cấu hình**

Tạo file tên `.env` trong folder JARVIS (xem [mục cấu hình](#-cấu-hình-env) bên dưới).

**Bước 5 — Khởi chạy**

```powershell
# Chạy ngầm (khuyên dùng) — xuất hiện icon ở system tray
python main.py --tray

# Chạy có console để xem log
python main.py
```

**Bước 6 — Tự khởi động cùng Windows (tuỳ chọn)**

```powershell
python -m jarvis install-autostart
# Để tắt:
python -m jarvis uninstall-autostart
```

---

### 🔷 Cách 2 — Build File .EXE Standalone

Sau khi build, bạn có 1 file `JARVIS.exe` chạy được ngay, không cần Python.

**Bước 1 — Cài PyInstaller**
```powershell
pip install pyinstaller
```

**Bước 2 — Build**
```powershell
python scripts/build_installer.py --exe-only
```
> ⏳ Mất 5–10 phút lần đầu.

**Bước 3 — Chạy**
```powershell
# Double-click JARVIS.exe hoặc:
.\dist\JARVIS.exe --tray
```

**Bước 4 — Tạo shortcut Desktop**
Nhấp phải `JARVIS.exe` → **Send to** → **Desktop (create shortcut)**

---

### 🔷 Cách 3 — Windows Installer (Cài Như App Thật ⭐ Khuyên Dùng)

Sau khi cài, JARVIS có trong Start Menu, tự khởi động cùng Windows, gỡ cài sạch từ Control Panel.

**Bước 1 — Cài Inno Setup 6**

Tải miễn phí: https://jrsoftware.org/isdl.php → chọn `innosetup-6.x.x.exe` → cài đặt bình thường.

**Bước 2 — Cài PyInstaller + Dependencies**
```powershell
pip install pyinstaller
pip install -r requirements.txt
```

**Bước 3 — Build .exe trước**
```powershell
python scripts/build_installer.py --exe-only
# → dist/JARVIS.exe
```

**Bước 4 — Build file installer**
```powershell
python scripts/build_installer.py
# → dist/installer/JARVIS_Setup_v4.0.0.exe
```

**Bước 5 — Chạy installer**

Double-click `JARVIS_Setup_v4.0.0.exe` → làm theo từng bước:

| Màn hình | Hành động |
|----------|-----------|
| Welcome | → Next |
| License Agreement | Chọn "I accept" → Next |
| Select Destination | Mặc định `C:\Program Files\JARVIS` → Next |
| Select Components | ✅ Core Files ✅ Desktop Icon ✅ Start Menu ✅ Auto-start |
| Ready to Install | → Install |
| Installation Complete | ✅ Launch JARVIS → Finish |

**Sau khi cài xong, JARVIS có ở:**

| Vị trí | Dùng để |
|--------|---------|
| `C:\Program Files\JARVIS\JARVIS.exe` | File thực thi chính |
| Desktop → **JARVIS AI Assistant** | Chạy bằng double-click |
| Start Menu → tìm **"JARVIS"** | Mở từ Start |
| Startup folder | Tự chạy khi bật máy |
| Control Panel → Programs | Gỡ cài đặt sạch |

---

## ⚙️ Cấu Hình `.env`

Tạo file `.env` tại thư mục gốc của JARVIS. Chỉ cần `GOOGLE_API_KEY` là đủ để chạy cơ bản.

```env
# ╔══════════════════════════════════════════╗
# ║   JARVIS v4.0.0 — Configuration File    ║
# ╚══════════════════════════════════════════╝

# ── Bắt buộc ─────────────────────────────────────────────────
# Lấy miễn phí tại: https://aistudio.google.com/apikey
GOOGLE_API_KEY=AIzaSy...

# ── Telegram Bot (tuỳ chọn) ──────────────────────────────────
# 1. Mở Telegram → tìm @BotFather → gửi /newbot → đặt tên
# 2. Sao chép token nhận được vào đây
TELEGRAM_BOT_TOKEN=123456789:ABC...
# 3. Lấy chat_id: gửi tin nhắn cho bot → vào
#    https://api.telegram.org/bot<token>/getUpdates
TELEGRAM_CHAT_ID=987654321

# ── Discord Bot (tuỳ chọn) ───────────────────────────────────
# Tạo tại: https://discord.com/developers/applications
# → New Application → Bot → Reset Token
DISCORD_BOT_TOKEN=MTI...
# Server ID (nhấp phải server → Copy Server ID)
DISCORD_GUILD_ID=1234567890

# ── Zalo Official Account (tuỳ chọn) ─────────────────────────
# Đăng ký OA: https://oa.zalo.me/home
# Vào Developer → API → lấy Access Token
ZALO_ACCESS_TOKEN=v4.0...
ZALO_OA_ID=123456789
# Tạo secret bất kỳ để verify webhook
ZALO_WEBHOOK_SECRET=my_secret_key_123

# ── Cài đặt giọng nói ─────────────────────────────────────────
# Ngôn ngữ: vi (tiếng Việt) hoặc en (tiếng Anh)
JARVIS_LANGUAGE=vi
# Tên model Whisper: tiny / base / small / medium / large-v3
JARVIS_WHISPER_MODEL=base
# Giọng đọc Piper (tên model trong ~/.jarvis/voices/)
JARVIS_VOICE=vi_VN-vivos-medium

# ── Cài đặt hệ thống ──────────────────────────────────────────
# 0 = chế độ bình thường | 1 = không mở cửa sổ (server/CI)
JARVIS_HEADLESS=0
# Cổng webhook Zalo (mặc định 8765)
JARVIS_ZALO_PORT=8765
# Cổng Mobile Bridge (mặc định 8766)
JARVIS_MOBILE_PORT=8766

# ── Thông báo (tuỳ chọn) ──────────────────────────────────────
# Discord Webhook URL để gửi thông báo vào channel
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## 🧰 Danh Sách Kỹ Năng Chi Tiết

### 1. 📰 Briefing Sáng (`briefing`)

Tổng hợp thông tin buổi sáng và đọc to cho bạn nghe.

**Kích hoạt:**
```
"JARVIS, báo cáo sáng nay"
"Hey JARVIS, briefing đi"
"Tóm tắt tin tức hôm nay"
```

**Nội dung bao gồm:**
| Mục | Nguồn | Ví dụ output |
|-----|-------|-------------|
| 🌤️ Thời tiết | OpenWeatherMap | "Hà Nội 28°C, mây rải rác, độ ẩm 75%" |
| 📰 Tin tức | RSS feeds | Top 3 tiêu đề từ VnExpress, Tuổi Trẻ |
| 💰 Crypto | CoinGecko API | "Bitcoin $67,500 (+2.3% hôm nay)" |
| 📅 Lịch hôm nay | File notes | Các ghi chú có tag "today" |

**Tham số:**
```
"Báo cáo sáng ở Đà Nẵng"           → city=DaNang
"Báo cáo không cần tin tức"         → include_news=false
"Briefing không có crypto"          → include_crypto=false
```

---

### 2. 📝 Ghi Chú (`note_taker`)

Lưu, tìm kiếm và quản lý ghi chú cá nhân với tag phân loại.

**Kích hoạt:**
```
"Ghi chú: họp với khách lúc 3h chiều"
"Nhớ hộ tôi: deadline dự án X là thứ 6"
"Tìm ghi chú về dự án Alpha"
"Xem tất cả ghi chú hôm nay"
```

**Các hành động:**
| Hành động | Lệnh mẫu | Kết quả |
|-----------|----------|---------|
| `add` | "Ghi chú: mua sữa" | Lưu với timestamp + tag |
| `list` | "Xem ghi chú hôm nay" | Hiện danh sách 10 ghi chú mới nhất |
| `search` | "Tìm ghi chú về họp" | Tìm kiếm full-text |
| `clear` | "Xóa tất cả ghi chú" | Xóa toàn bộ (có xác nhận) |

**Tag phân loại:**
```
"Ghi chú urgent: fix bug trước 5h"    → tag=urgent
"Ghi chú work: báo cáo Q3"           → tag=work
"Ghi chú personal: sinh nhật vợ 20/9" → tag=personal
```

**Lưu trữ:** `~/.jarvis/notes.sqlite` — mã hóa, tìm kiếm full-text qua FTS5

---

### 3. ⏱️ Pomodoro (`pomodoro`)

Bộ đếm thời gian Pomodoro giúp tập trung làm việc theo phiên.

**Kích hoạt:**
```
"Bắt đầu tập trung 25 phút"
"Pomodoro 45 phút"
"Dừng đếm giờ"
"Còn bao nhiêu phút?"
```

**Cách hoạt động:**
1. JARVIS bắt đầu đếm ngược (mặc định 25 phút)
2. Cứ 5 phút: thông báo toast "Còn 20 phút..."
3. Hết giờ: âm thanh chuông + thông báo giọng nói "Hết phiên tập trung!"
4. Đề xuất nghỉ ngắn 5 phút

**Tham số thời gian:**
```
"Tập trung 45 phút"    → duration=45
"Pomodoro 1 tiếng"     → duration=60
"Nghỉ 10 phút"         → break_mode=true, duration=10
```

---

### 4. 💻 Điều Khiển Hệ Thống (`system_control`)

Điều khiển các chức năng hệ thống Windows bằng giọng nói.

**Âm lượng:**
```
"Tăng âm lượng"                → +10%
"Giảm âm lượng"                → -10%
"Tắt tiếng"                    → mute toggle
"Đặt âm lượng 50 phần trăm"   → set_volume=50
```

**Màn hình & Hiển thị:**
```
"Chụp màn hình"                → lưu PNG vào Desktop với tên JARVIS_YYYYMMDD_HHMMSS.png
"Hiện desktop"                  → thu nhỏ tất cả cửa sổ (Win+D)
"Khóa máy tính"                → LockWorkStation() ngay lập tức
```

**Thông số `screenshot`:**
- Định dạng: PNG, chất lượng lossless
- Lưu tại: `~/Desktop/JARVIS_screenshot_<timestamp>.png`
- Độ trễ: ~150ms từ lệnh đến khi file xuất hiện

---

### 5. 🗂️ Quản Lý File (`file_manager`)

Tìm kiếm và mở file/thư mục bằng mô tả tự nhiên.

**Kích hoạt:**
```
"Tìm file báo cáo tháng trước"
"Mở thư mục Downloads"
"Tìm file Excel về doanh thu"
"Tìm file Python nào tôi chỉnh hôm qua"
```

**Khả năng tìm kiếm:**
| Tiêu chí | Ví dụ |
|---------|-------|
| Tên file | "tìm file tên báo cáo" |
| Loại file | "tìm file Excel", "tìm file PDF" |
| Thời gian | "file chỉnh hôm qua", "file tạo tuần này" |
| Nội dung | "file có chứa từ 'hợp đồng'" |
| Thư mục | "trong Documents", "trong Downloads" |

---

### 6. 🧮 Máy Tính (`calculator`)

Tính toán biểu thức và chuyển đổi đơn vị bằng giọng nói.

**Tính toán:**
```
"Tính 15% của 2 triệu rưỡi"     → 375,000
"Bao nhiêu là 1500 USD sang VND" → 37,500,000 VNĐ (tỷ giá thực)
"Căn bậc hai của 144"            → 12
"2 mũ 10"                        → 1024
```

**Chuyển đổi đơn vị:**
```
"5 kilogram bằng bao nhiêu pound"
"30 độ C bằng bao nhiêu Fahrenheit"
"100 km/h bằng bao nhiêu m/s"
```

---

### 7. 📋 Clipboard (`clipboard`)

Đọc, lưu và quản lý nội dung clipboard.

**Kích hoạt:**
```
"Đọc clipboard"          → JARVIS đọc to nội dung hiện tại
"Sao chép: xin chào"    → copy "xin chào" vào clipboard
"Dán vào đây"           → Ctrl+V
"Lịch sử clipboard"     → xem 5 lần copy gần nhất
```

---

### 8. 🚀 Mở Ứng Dụng (`app_launcher`)

Tìm và mở ứng dụng, website, thư mục bằng tên tự nhiên.

**Kích hoạt:**
```
"Mở Chrome"             → mở Google Chrome
"Mở VS Code"            → mở Visual Studio Code
"Mở Spotify"            → mở Spotify
"Mở YouTube"            → mở youtube.com trong browser mặc định
"Mở thư mục Downloads"  → mở Explorer tại Downloads
```

**Tìm kiếm thông minh:** So sánh fuzzy matching với danh sách app đã cài — gõ sai tên vẫn tìm được.

---

### 9. 👁️ Phân Tích Màn Hình (`screen_context`)

Chụp màn hình và phân tích nội dung bằng Gemini Vision AI.

**Kích hoạt:** `Ctrl+Shift+Space` hoặc:
```
"Giải thích lỗi trên màn hình"
"Dịch đoạn văn bản này"
"Tóm tắt trang web đang mở"
"Code này làm gì vậy?"
```

**Khả năng phân tích:**
- **Lỗi code:** Đọc stack trace → giải thích nguyên nhân → gợi ý fix
- **Văn bản nước ngoài:** Dịch sang tiếng Việt ngay trên màn hình
- **Tài liệu/PDF:** Tóm tắt nội dung chính
- **UI/Design:** Mô tả layout, đề xuất cải thiện

---

### 10. ⏺️ Ghi Macro (`macro_recorder`)

Ghi lại chuỗi thao tác chuột/bàn phím và phát lại tự động.

**Ghi macro:**
```
"Ghi lại macro tên gửi email"
# → thực hiện các thao tác: mở Gmail, nhập địa chỉ, soạn nội dung...
"Dừng ghi"
```

**Phát lại:**
```
"Phát lại macro gửi email"
"Chạy macro gửi email 5 lần"
```

**Lưu tại:** `~/.jarvis/macros/<name>.json` — có thể chỉnh sửa thủ công

---

### 11. 🔊 Sound Board (`sound_board`)

Phát các âm thanh phản hồi và hiệu ứng âm thanh theo ngữ cảnh.

**Kích hoạt:**
```
"Phát âm thanh Iron Man"
"Phát âm hoàn thành"
"Bật nhạc nền làm việc"
```

**Thư viện âm thanh có sẵn:**
| Âm thanh | Khi nào phát |
|---------|-------------|
| `startup.wav` | JARVIS khởi động |
| `ready.wav` | Sẵn sàng nghe lệnh |
| `done.wav` | Hoàn thành tác vụ |
| `error.wav` | Gặp lỗi |
| `iron_man.wav` | Theo yêu cầu |

---

### 12. 🔍 Tìm Kiếm Ký Ức (`rag_search`)

Tìm kiếm trong toàn bộ ký ức của JARVIS theo ngữ nghĩa.

**Kích hoạt:**
```
"Tuần trước tôi ghi gì về dự án Alpha?"
"JARVIS đã làm gì lúc 2h sáng?"
"Tìm tất cả ghi chú về buổi họp"
"Tôi đã note deadline nào chưa?"
```

**Nguồn dữ liệu tìm kiếm:**
- Tất cả ghi chú (`note_taker`)
- Lịch sử hội thoại với JARVIS
- Báo cáo Night Shift
- Kết quả tác vụ đã thực hiện

**Thuật toán:** TF-IDF BM25 cosine similarity — tìm theo nghĩa, không cần từ khóa chính xác

---

### 13. 🧬 Tự Tạo Kỹ Năng (`skill_synthesizer`)

Yêu cầu JARVIS viết code và tạo kỹ năng mới hoàn toàn tự động.

**Kích hoạt:**
```
"Tạo kỹ năng theo dõi giá vàng"
"Tạo kỹ năng gửi email hàng ngày lúc 8h"
"Tạo kỹ năng kiểm tra thời tiết Đà Nẵng"
```

**Quy trình tự động (< 15 giây):**
```
1. JARVIS hiểu yêu cầu → thiết kế interface
2. Gemini viết code Python
3. py_compile() kiểm tra syntax
4. Chạy smoke test với input mẫu
5. Đăng ký vào SkillRegistry
6. "Xong! Kỹ năng 'gia_vang' đã sẵn sàng."
```

---

### 14. 🌙 Night Planner (`night_planner`)

Lên kế hoạch và thực hiện tác vụ dài trong đêm.

**Kích hoạt:**
```
"Tối nay phân tích tất cả file log trong /logs"
"Đêm nay tổng hợp dữ liệu doanh thu tháng 8"
"JARVIS làm báo cáo project status trong khi tôi ngủ"
```

**Luồng hoạt động:**
```
22:00 → Bạn giao nhiệm vụ → JARVIS xác nhận
22:01 → Night Shift bắt đầu làm việc ngầm
07:00 → JARVIS gọi "Chào buổi sáng! Tôi đã hoàn thành..."
→ Báo cáo Markdown tại ~/.jarvis/reports/night_YYYYMMDD.md
```

---

### 15. 🏠 Nhà Thông Minh (`smart_home_discovery`)

Tự động quét và điều khiển thiết bị nhà thông minh trên mạng LAN.

**Kích hoạt:**
```
"Quét thiết bị nhà thông minh"
"Bật đèn phòng khách"
"Tắt máy lạnh"
"Đặt nhiệt độ 24 độ"
```

**Thiết bị hỗ trợ phát hiện:**
| Giao thức | Thiết bị |
|-----------|---------|
| Home Assistant | Toàn bộ ecosystem HA |
| Tasmota | Ổ cắm thông minh Sonoff |
| Tuya | Đèn, ổ cắm Tuya/SmartLife |
| mDNS/Zeroconf | Thiết bị tự quảng bá |

---

### 16. 🌐 Điều Khiển Trình Duyệt (`browser_control`)

Điều khiển Chrome bằng giọng nói qua Playwright CDP.

**Kích hoạt:**
```
"Mở YouTube"
"Tìm kiếm Python tutorial"
"Click vào nút đăng nhập"
"Nhập email vào ô đầu tiên: test@example.com"
"Cuộn xuống"
"Chụp màn hình trang này"
"Đóng tab"
```

> ⚠️ Yêu cầu cài Playwright: `playwright install chromium`

---

### 17. 🔄 Tự Cập Nhật (`auto_updater`)

Kiểm tra và cài đặt bản cập nhật JARVIS tự động.

**Kích hoạt:**
```
"Kiểm tra cập nhật JARVIS"
"JARVIS tự cập nhật đi"
"Lịch sử cập nhật"
"Khôi phục phiên bản cũ"
```

**Tự động:** Kiểm tra mỗi 6 giờ → nếu có bản mới → thông báo toast → hỏi bạn có muốn cập nhật không.

---

### 18. 🧠 Chế Độ Agent Tự Trị (`agent_mode`)

JARVIS tự lên kế hoạch và thực thi mục tiêu phức tạp không cần can thiệp.

**Kích hoạt:**
```
"JARVIS, phân tích toàn bộ code trong thư mục src/"
"Tìm tất cả file log có lỗi ERROR và tổng hợp thành báo cáo"
"Nghiên cứu về LangChain và viết tóm tắt 500 từ"
```

**Vòng lặp ReAct:**
```
[THINK]   → "Cần đọc từng file trong src/ trước"
[ACT]     → Gọi tool: list_dir(path="src/")
[OBSERVE] → "Thấy 23 file .py"
[THINK]   → "Sẽ đọc từng file"
[ACT]     → Gọi tool: read_file(path="src/main.py")
  ...
[REFLECT] → Tổng hợp kết quả
[DONE]    → Báo cáo đầy đủ
```

**12 Tools tích hợp:**
`web_search` · `read_file` · `write_file` · `run_python` · `browser_open` · `screenshot` · `calculator` · `memory_search` · `send_telegram` · `list_dir` · `git_status` · `take_note`

---

## 📱 Điều Khiển Qua Điện Thoại

### Telegram Bot

**Thiết lập (5 phút):**
1. Mở Telegram → tìm **@BotFather** → gửi `/newbot`
2. Đặt tên (ví dụ: `My JARVIS Bot`) → lấy token
3. Thêm vào `.env`: `TELEGRAM_BOT_TOKEN=<token>`
4. Lấy Chat ID: gửi tin nhắn bất kỳ cho bot → vào `https://api.telegram.org/bot<token>/getUpdates` → lấy `chat.id`
5. Thêm: `TELEGRAM_CHAT_ID=<chat_id>`
6. Khởi động lại JARVIS

**Lệnh Telegram:**
| Lệnh | Chức năng | Ví dụ phản hồi |
|------|-----------|---------------|
| `/start` | Xin chào & liệt kê lệnh | "JARVIS sẵn sàng! Tôi có thể giúp gì?" |
| `/status` | Trạng thái hệ thống | CPU 15%, RAM 8GB/32GB, Uptime 4h |
| `/briefing` | Báo cáo sáng | Thời tiết + tin tức + crypto |
| `/note <nội dung>` | Ghi chú nhanh | "Đã ghi: họp lúc 3h" |
| `/calc <biểu thức>` | Tính toán | `/calc 15% of 2500000` → 375,000 |
| `/screenshot` | Chụp màn hình → gửi ảnh | Gửi ảnh PNG ~2MB |
| `/skills` | Danh sách kỹ năng | 18 kỹ năng đang hoạt động |
| Tin nhắn tự do | Ngôn ngữ tự nhiên | JARVIS xử lý như lệnh giọng nói |

---

### Zalo Official Account

**Thiết lập:**
1. Đăng ký OA tại https://oa.zalo.me → xác minh
2. Vào **Developer Console** → **API** → lấy `Access Token`
3. Cấu hình Webhook URL: `http://<your-ip>:8765/webhook`
4. Thêm vào `.env`: `ZALO_ACCESS_TOKEN`, `ZALO_OA_ID`, `ZALO_WEBHOOK_SECRET`

**Lệnh Zalo:**
| Lệnh | Chức năng |
|------|-----------|
| `/status` | Trạng thái JARVIS |
| `/briefing` | Báo cáo sáng |
| `/note <nội dung>` | Ghi chú nhanh |
| `/calc <biểu thức>` | Tính toán |
| `/screenshot` | Chụp màn hình |
| Tin nhắn tự do | Xử lý bằng IntentRouter |

---

### Discord Bot

**Lệnh Discord:**
```
!status       — Trạng thái JARVIS
!briefing     — Báo cáo sáng
!note <text>  — Ghi chú
!screenshot   — Chụp màn hình
!calc <expr>  — Tính toán
```

---

## ⌨️ Phím Tắt Toàn Hệ Thống

Hoạt động từ **bất kỳ ứng dụng nào** — kể cả khi JARVIS đang chạy ngầm.

| Phím tắt | Chức năng | Chi tiết |
|----------|-----------|---------|
| `Ctrl+Shift+J` | Bật/Tắt JARVIS listening | Toggle chế độ lắng nghe giọng nói |
| `Ctrl+Shift+L` | Khóa màn hình | Gọi Win32 `LockWorkStation()` ngay lập tức |
| `Ctrl+Shift+M` | Tắt/Bật mic | Toggle mute microphone trong JARVIS |
| `Ctrl+Shift+B` | Mở Briefing sáng | Phát báo cáo sáng qua TTS |
| `Ctrl+Shift+S` | Chụp màn hình | Lưu PNG vào Desktop, thông báo toast |
| `Ctrl+Shift+Space` | Phân tích màn hình | Chụp + gửi Gemini Vision + đọc kết quả |

---

## 🔔 Notification Hub

Gửi thông báo đồng thời qua nhiều kênh.

**Kích hoạt:**
```python
# Trong code:
hub.notify("Họp bắt đầu!", channels=["all"])
hub.schedule("Nhắc uống nước", at="every_2h")
hub.add_rule("CPU > 90%", check_fn=lambda: psutil.cpu_percent() > 90)
```

**6 Kênh thông báo:**
| Kênh | Điều kiện cần |
|------|-------------|
| 🪟 Windows Toast | Mặc định — luôn hoạt động |
| 🔊 Sound | File âm thanh trong `~/.jarvis/sounds/` |
| 🗣️ TTS | Piper TTS đang chạy |
| 📱 Telegram | `TELEGRAM_BOT_TOKEN` đã cấu hình |
| 💬 Discord | `DISCORD_WEBHOOK_URL` đã cấu hình |
| 📞 Zalo | `ZALO_ACCESS_TOKEN` đã cấu hình |

---

## 🏗️ Kiến Trúc Hệ Thống

```
┌─────────────────────────────────────────────────────┐
│                   INPUT LAYER                        │
│  🎙️ Voice (VAD+Whisper)  📱 Telegram  📞 Zalo       │
│  💬 Discord              ⌨️  Hotkeys  📲 Mobile      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                INTELLIGENCE LAYER                    │
│                                                      │
│  Intent Router (15+ VN patterns, fast-path)         │
│         │                                            │
│         ├── Match → Direct Skill Invocation          │
│         └── No match → LLM (Gemini) Classification  │
│                                                      │
│  ReAct Agent (Think→Act→Observe→Reflect)            │
│  Semantic Memory (TF-IDF BM25, offline)             │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                   SKILLS (18+)                       │
│  briefing · note_taker · pomodoro · system_control  │
│  file_manager · calculator · clipboard · launcher   │
│  screen_context · macro_recorder · sound_board      │
│  rag_search · skill_synthesizer · night_planner     │
│  smart_home · browser_control · auto_updater        │
│  [pip plugins: jarvis-plugin-*]                     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  OUTPUT LAYER                        │
│  🗣️ TTS (Piper, <80ms)   🔔 Notification Hub       │
│  🪟 System Tray          📊 Health Reports          │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│               DAEMON LAYER (Background)              │
│  🌙 Night Shift Worker    🔄 Auto-Update (6h)        │
│  🏠 Smart Home Discovery  🧩 Plugin Hot-Loader       │
└─────────────────────────────────────────────────────┘
```

---

## 🧪 Developer Guide

### Cài môi trường phát triển

```powershell
git clone https://github.com/Duong-Phuoc-Hung/JARVIS.git
cd JARVIS
pip install -e ".[dev]"    # Cài với dev dependencies (pytest, ruff, mypy)
pre-commit install          # Cài hooks kiểm tra code trước mỗi commit
```

### Chạy tests

```powershell
make test           # Tất cả 633 tests
make test-cov       # Tests + coverage report
make test-fast      # Bỏ qua slow tests

# Chạy 1 file cụ thể:
make test-file f=tests/unit/test_react_agent.py
```

### Code quality

```powershell
make lint           # Kiểm tra với Ruff
make format         # Auto-format
make typecheck      # Type check với mypy
make check          # Tất cả cùng lúc
```

### Tạo kỹ năng mới

```python
# jarvis/skills/my_skill/__init__.py
def execute(params: dict, context=None) -> dict:
    """
    Kỹ năng mẫu.
    
    Args:
        params: {"action": "do_something", "value": "..."}
    
    Returns:
        {"data": {...}, "output": "Kết quả dạng text"}
    """
    action = params.get("action", "")
    return {
        "data": {"result": "ok"},
        "output": f"Đã thực hiện: {action}"
    }
```

```json
// jarvis/skills/my_skill/metadata.json
{
  "name": "my_skill",
  "version": "1.0.0",
  "description": "Mô tả kỹ năng",
  "parameters_schema": {
    "type": "object",
    "properties": {
      "action": {"type": "string", "default": "default"}
    }
  }
}
```

---

## ❓ Câu Hỏi Thường Gặp

<details>
<summary><b>❌ Lỗi "Python not found" khi chạy lệnh</b></summary>

**Nguyên nhân:** Python chưa được thêm vào PATH.

**Cách fix:**
1. Gõ vào thanh tìm kiếm Windows: *"Edit the system environment variables"*
2. Nhấn **Environment Variables**
3. Trong **System Variables** → tìm **Path** → **Edit**
4. Thêm 2 dòng mới:
   - `C:\Users\<TênBạn>\AppData\Local\Programs\Python\Python311\`
   - `C:\Users\<TênBạn>\AppData\Local\Programs\Python\Python311\Scripts\`
5. OK → Mở lại terminal

</details>

<details>
<summary><b>❌ pip install thất bại / lỗi mạng</b></summary>

```powershell
# Thử 1: Dùng mirror trong nước
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# Thử 2: Tăng timeout
pip install -r requirements.txt --timeout=120

# Thử 3: Cài từng gói quan trọng
pip install google-generativeai python-dotenv numpy Pillow requests pytest
```

</details>

<details>
<summary><b>🎙️ JARVIS không nghe giọng nói / độ nhạy kém</b></summary>

1. Kiểm tra micro: **Settings → System → Sound → Input** → đảm bảo micro được chọn
2. Test micro bằng cách nói và xem thanh mức âm thanh có dao động không
3. Nói to hơn hoặc gần mic hơn (khoảng cách tối ưu: 30–50cm)
4. Trong `.env`, giảm ngưỡng VAD: `JARVIS_VAD_THRESHOLD=0.005` (mặc định 0.01)
5. Kiểm tra `GOOGLE_API_KEY` có hợp lệ không

</details>

<details>
<summary><b>🏗️ Build .exe thất bại</b></summary>

```powershell
# Xóa cache và thử lại
Remove-Item -Recurse -Force build, dist, __pycache__
pip install --upgrade pyinstaller
python scripts/build_installer.py --exe-only --no-clean

# Nếu lỗi "missing module":
pip install <tên-module-bị-thiếu>
python scripts/build_installer.py --exe-only
```

</details>

<details>
<summary><b>📱 Telegram bot không phản hồi</b></summary>

1. Kiểm tra token trong `.env` đúng chưa (không có dấu cách, đầy đủ ký tự)
2. Đảm bảo bot chưa bị block: vào @BotFather → `/mybots` → xem bot còn active không
3. Xác nhận `TELEGRAM_CHAT_ID` là ID của bạn (không phải ID bot)
4. Thử gửi `/start` cho bot để kích hoạt

</details>

<details>
<summary><b>🔒 Antivirus chặn JARVIS.exe</b></summary>

PyInstaller tạo file `.exe` từ Python thường bị một số antivirus flag nhầm (false positive). Cách xử lý:

1. **Windows Defender:** Settings → Virus & threat protection → Manage settings → Add exclusion → Folder → chọn thư mục JARVIS
2. **Cách an toàn hơn:** Chạy từ source code (Cách 1) thay vì .exe

</details>

---

## 📋 Nhật Ký Phiên Bản

| Phiên bản | Ngày | Điểm nổi bật |
|-----------|------|-------------|
| **v4.0.0** | 2026-08-28 | ReAct Autonomous Agent · Notification Hub · Windows Installer · pyproject.toml |
| v3.2.0 | 2026-08-28 | Zalo Bot 2-Way Control |
| v3.1.0 | 2026-08-28 | Browser CDP · Auto-Update · Plugin SDK · GitHub Release CI |
| v3.0.0 | 2026-08-28 | Self-Coding Skills · Semantic RAG · Night Shift · Discord |
| v2.0.0 | 2026-08-24 | 9 Built-in Skills · Memory · Global Hotkeys · System Tray |

Chi tiết: [CHANGELOG.md](CHANGELOG.md)

---

<div align="center">

Tạo bởi **Duong Phuoc Hung** với ❤️

[⭐ Star](https://github.com/Duong-Phuoc-Hung/JARVIS) · [🐛 Báo lỗi](https://github.com/Duong-Phuoc-Hung/JARVIS/issues) · [📖 Changelog](CHANGELOG.md) · [📦 Releases](https://github.com/Duong-Phuoc-Hung/JARVIS/releases)

</div>
