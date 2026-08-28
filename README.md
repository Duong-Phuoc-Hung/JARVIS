# 🤖 JARVIS — Trợ Lý AI Cá Nhân Tự Trị Cho Windows

<div align="center">

![JARVIS Banner](https://img.shields.io/badge/JARVIS-Autonomous%20AI%20Assistant-00f0ff?style=for-the-badge&logo=windows)
![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-633%20Passed%20(100%25)-00ff88?style=for-the-badge)
![CI](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/workflows/ci.yml/badge.svg)
![Version](https://img.shields.io/badge/Version-4.0.0-purple?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?style=for-the-badge&logo=windows)

**JARVIS** là trợ lý AI cá nhân tự trị toàn năng — lấy cảm hứng từ JARVIS của Tony Stark trong Iron Man.

Chạy ngầm dưới Windows · Nhận lệnh bằng giọng nói tiếng Việt · Không cần mở VS Code

</div>

---

## 📺 JARVIS Làm Được Gì?

> 💬 Bạn nói: **"Hey JARVIS, báo cáo sáng nay"**
> → JARVIS đọc thời tiết, tin tức, lịch hôm nay cho bạn nghe

> 💬 Bạn nói: **"Tạo kỹ năng theo dõi giá vàng cho tôi"**
> → JARVIS tự viết code, kiểm tra, cài vào hệ thống — xong trong 10 giây

> 💬 Bạn nhắn Zalo: **"/briefing"**
> → JARVIS gửi báo cáo sáng về điện thoại bạn

> 💬 Bạn nói: **"Tối nay phân tích 50 file code cho tôi"**
> → JARVIS tự làm xuyên đêm, sáng dậy có báo cáo Markdown sẵn

---

## 🚀 Bắt Đầu Nhanh — Chọn Cách Phù Hợp Với Bạn

| | Cách 1: Chạy từ Code | Cách 2: File .EXE | Cách 3: Installer |
|--|---------------------|------------------|------------------|
| **Dành cho** | Lập trình viên | Người dùng thông thường | Cài hẳn vào máy |
| **Yêu cầu** | Python 3.10+ | Không cần gì | Inno Setup |
| **Kết quả** | Chạy từ terminal | 1 file .exe portable | Cài như app thật |
| **Autostart** | Thủ công | Thủ công | ✅ Tự động |
| **Thời gian** | ~5 phút | ~10 phút | ~15 phút |

---

## 📥 CÁCH 1 — Chạy Từ Source Code (Dành Cho Dev)

### Bước 1: Cài Python

Nếu chưa có Python, tải tại: https://python.org/downloads

Chọn **Python 3.11** (khuyên dùng) → tích ✅ **"Add Python to PATH"** → Install

Kiểm tra sau khi cài:
```bash
python --version
# Phải hiện: Python 3.11.x
```

---

### Bước 2: Tải JARVIS Về Máy

**Cách A — Dùng Git** (khuyên dùng):
```bash
git clone https://github.com/Duong-Phuoc-Hung/JARVIS.git
cd JARVIS
```

**Cách B — Tải thủ công**:
1. Vào https://github.com/Duong-Phuoc-Hung/JARVIS
2. Nhấn nút xanh **Code** → **Download ZIP**
3. Giải nén → Mở folder `JARVIS-main`
4. Nhấp vào thanh địa chỉ, gõ `cmd`, nhấn Enter

---

### Bước 3: Cài Các Thư Viện Cần Thiết

```bash
pip install -r requirements.txt
```

> ⏳ Quá trình này mất khoảng 2–5 phút, tùy tốc độ mạng.

Nếu gặp lỗi **"pip not found"**:
```bash
python -m pip install -r requirements.txt
```

---

### Bước 4: Tạo File Cấu Hình `.env`

Tạo file tên `.env` trong folder JARVIS (dùng Notepad):

```env
# ===== BẮT BUỘC =====
# Lấy tại: https://aistudio.google.com/apikey (miễn phí)
GOOGLE_API_KEY=AIzaSy...your_key_here

# ===== TÙY CHỌN — Telegram Bot =====
# Tạo bot: nhắn @BotFather trên Telegram → /newbot
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ===== TÙY CHỌN — Discord Bot =====
# Tạo tại: https://discord.com/developers/applications
DISCORD_BOT_TOKEN=

# ===== TÙY CHỌN — Zalo OA =====
# Đăng ký: https://oa.zalo.me/home
ZALO_ACCESS_TOKEN=
ZALO_OA_ID=
```

> 💡 Chỉ cần `GOOGLE_API_KEY` là đủ để chạy. Phần còn lại cài sau cũng được.

---

### Bước 5: Khởi Chạy JARVIS

```bash
# Chạy bình thường (có cửa sổ console)
python main.py

# Chạy ngầm dưới system tray (khuyên dùng)
python main.py --tray
```

Sau khi chạy:
- Biểu tượng **⚡ Arc Reactor** xuất hiện cạnh đồng hồ góc phải
- Nhấp chuột phải vào biểu tượng để xem menu
- Nói **"Hey JARVIS"** để thử

---

### Bước 6 (Tuỳ chọn): Tự Khởi Động Cùng Windows

```bash
python -m jarvis install-autostart
```

Từ giờ, mỗi lần bật máy JARVIS tự chạy ngầm — không cần làm gì thêm.

Để tắt autostart:
```bash
python -m jarvis uninstall-autostart
```

---

## 🏗️ CÁCH 2 — Build File .EXE (Không Cần Python)

Sau khi build xong, bạn có **1 file `JARVIS.exe`** — copy sang máy khác chạy được ngay, không cần cài Python.

### Bước 1: Cài PyInstaller
```bash
pip install pyinstaller
```

### Bước 2: Build .EXE
```bash
python scripts/build_installer.py --exe-only
```

> ⏳ Quá trình build mất 3–8 phút. Bình thường, đừng tắt đi.

### Bước 3: Chạy File .EXE
```
dist\
└── JARVIS.exe     ← Double-click để chạy!
```

```bash
# Hoặc chạy ngầm từ dòng lệnh:
dist\JARVIS.exe --tray
```

### Bước 4 (Tuỳ chọn): Tạo Shortcut Desktop
Nhấp phải vào `JARVIS.exe` → **Send to** → **Desktop (create shortcut)**

---

## 🪟 CÁCH 3 — Windows Installer (Cài Như App Thật — Khuyên Dùng)

Kết quả: JARVIS xuất hiện trong Start Menu, có thể gỡ cài từ Control Panel, tự khởi động cùng Windows.

### Bước 1: Cài Inno Setup

Tải miễn phí tại: **https://jrsoftware.org/isdl.php**

Chọn **"Inno Setup 6.x.x"** → chạy file tải về → cài đặt bình thường (Next → Next → Finish).

### Bước 2: Build File .EXE Trước
```bash
pip install pyinstaller
python scripts/build_installer.py --exe-only
```

### Bước 3: Build Installer
```bash
python scripts/build_installer.py
```

Kết quả sẽ có:
```
dist\
├── JARVIS.exe                          ← file exe thô
└── installer\
    └── JARVIS_Setup_v4.0.0.exe        ← FILE CÀI ĐẶT NÀY!
```

### Bước 4: Cài Đặt JARVIS

Double-click vào **`JARVIS_Setup_v4.0.0.exe`** → làm theo hướng dẫn:

| Màn Hình | Lựa Chọn Khuyên Dùng |
|----------|---------------------|
| Chào mừng | → Next |
| Thư mục cài | Mặc định `C:\Program Files\JARVIS` → Next |
| Tùy chọn thêm | ✅ Tạo icon Desktop · ✅ Thêm Start Menu · ✅ Khởi động cùng Windows |
| Sẵn sàng cài | → Install |
| Hoàn thành | ✅ Khởi động JARVIS ngay → Finish |

### Sau Khi Cài Xong

| Vị Trí | Mô Tả |
|--------|-------|
| 📂 `C:\Program Files\JARVIS\JARVIS.exe` | File chạy chính |
| 🖥️ Desktop → **JARVIS AI Assistant** | Shortcut double-click |
| 🪟 Start Menu → tìm **"JARVIS"** | Tìm kiếm từ Start |
| ⚙️ Control Panel → Programs | Gỡ cài đặt tại đây |
| 🔄 Task Manager → Startup | Quản lý autostart |

### Gỡ Cài Đặt Sạch
```
Control Panel → Programs → Programs & Features
→ Tìm "JARVIS AI Assistant" → Uninstall
```

---

## 🎙️ Hướng Dẫn Sử Dụng Cơ Bản

### Bật / Tắt Listening

| Cách | Mô Tả |
|------|-------|
| Nói **"Hey JARVIS"** | Kích hoạt bằng giọng nói |
| Nhấn `Ctrl+Shift+J` | Phím tắt bật/tắt |
| Nhấp chuột phải tray → **Listen** | Từ menu khay hệ thống |

### Phím Tắt Toàn Hệ Thống

| Phím | Chức Năng | Hoạt Động Ở |
|------|-----------|------------|
| `Ctrl+Shift+J` | Bật/Tắt JARVIS listening | Mọi nơi |
| `Ctrl+Shift+L` | Khóa màn hình ngay | Mọi nơi |
| `Ctrl+Shift+M` | Tắt/Bật mic | Mọi nơi |
| `Ctrl+Shift+B` | Phát báo cáo sáng | Mọi nơi |
| `Ctrl+Shift+S` | Chụp màn hình → Desktop | Mọi nơi |
| `Ctrl+Shift+Space` | Phân tích màn hình (Vision AI) | Mọi nơi |

### Ví Dụ Lệnh Hay Dùng

```
"Hey JARVIS, báo cáo sáng nay"
"Ghi chú: họp với khách lúc 3 giờ chiều"
"Tìm file báo cáo tháng trước"
"Mở YouTube"
"Tính 15% của 2 triệu rưỡi"
"Bắt đầu tập trung 25 phút"
"Chụp màn hình"
"Tháng trước tôi đã note gì về dự án X?"
"Tạo kỹ năng theo dõi giá Bitcoin"
"Có bản cập nhật JARVIS nào không?"
```

---

## 📱 Điều Khiển Qua Điện Thoại

### Telegram Bot (Dễ Cài Nhất)

1. Mở Telegram → tìm **@BotFather**
2. Gửi `/newbot` → đặt tên → lấy token
3. Thêm vào `.env`: `TELEGRAM_BOT_TOKEN=...`
4. Khởi động lại JARVIS
5. Nhắn bot của bạn bất kỳ lệnh nào

Lệnh Telegram:
```
/start      — Xin chào
/briefing   — Báo cáo sáng
/note họp 3h — Ghi chú nhanh
/calc 100*1.1 — Tính toán
/screenshot — Chụp màn hình gửi về
/status     — Trạng thái hệ thống
```

### Zalo (Điều Khiển Từ Zalo)

1. Đăng ký Zalo Official Account tại https://oa.zalo.me
2. Lấy **Access Token** từ Developer Console
3. Thêm vào `.env`: `ZALO_ACCESS_TOKEN=...`
4. Nhắn tin vào OA của bạn các lệnh:

```
/status     — Trạng thái JARVIS
/briefing   — Báo cáo sáng
/note <nội dung> — Ghi chú
/calc <biểu thức> — Tính toán
/screenshot — Chụp màn hình
Hoặc nhắn tiếng Việt tự nhiên bất kỳ
```

---

## 🧰 Danh Sách 20+ Kỹ Năng Built-in

| # | Kỹ Năng | Lệnh Thoại Ví Dụ | Từ Phiên Bản |
|---|---------|-----------------|-------------|
| 1 | **Briefing Sáng** | *"Báo cáo sáng nay"* | v2.0 |
| 2 | **Quản Lý File** | *"Tìm file Excel tháng trước"* | v2.0 |
| 3 | **Ghi Chú** | *"Ghi chú: họp lúc 3h chiều"* | v2.0 |
| 4 | **Pomodoro** | *"Tập trung 25 phút"* | v2.0 |
| 5 | **Điều Khiển Hệ Thống** | *"Chụp màn hình"*, *"Khóa máy"* | v2.0 |
| 6 | **Trợ Lý Git** | *"Trạng thái git dự án này"* | v2.0 |
| 7 | **Máy Tính** | *"Tính 15% của 2 triệu rưỡi"* | v2.0 |
| 8 | **Clipboard** | *"Đọc nội dung clipboard"* | v2.0 |
| 9 | **Mở Ứng Dụng** | *"Mở Chrome"*, *"Mở Spotify"* | v2.0 |
| 10 | **Phân Tích Màn Hình** | *"Giải thích lỗi đang hiện"* | v2.2 |
| 11 | **Ghi Macro** | *"Ghi lại thao tác này"*, *"Phát lại"* | v2.2 |
| 12 | **Âm Thanh** | *"Phát âm thanh Iron Man"* | v2.2 |
| 13 | **Tìm Kiếm Ký Ức** | *"Tuần trước tôi note gì về X?"* | v3.0 |
| 14 | **Tự Tạo Kỹ Năng** | *"Tạo kỹ năng theo dõi giá vàng"* | v3.0 |
| 15 | **Night Planner** | *"Tối nay phân tích data cho tôi"* | v3.0 |
| 16 | **Nhà Thông Minh** | *"Quét thiết bị trên mạng nhà"* | v2.3 |
| 17 | **Điều Khiển Chrome** | *"Mở YouTube"*, *"Tìm kiếm..."* | v3.1 |
| 18 | **Tự Cập Nhật** | *"Có bản JARVIS mới không?"* | v3.1 |
| 19 | **Agent Tự Trị** | *"Phân tích toàn bộ code src/"* | v4.0 |
| 20+ | **Plugin Bên Ngoài** | `pip install jarvis-plugin-ten` | v3.1 |

---

## ❓ Câu Hỏi Thường Gặp (FAQ)

<details>
<summary><b>🔴 Lỗi "Python not found" khi chạy lệnh</b></summary>

Nguyên nhân: Python chưa được thêm vào PATH.

Cách sửa:
1. Vào **Settings** → tìm **"Edit environment variables"**
2. Chọn **"Environment Variables"**
3. Trong **System Variables** → tìm **Path** → Edit
4. Thêm đường dẫn Python (VD: `C:\Python311\` và `C:\Python311\Scripts\`)
5. Restart terminal

</details>

<details>
<summary><b>🔴 Lỗi "pip install" thất bại</b></summary>

Thử lần lượt:
```bash
# Cách 1: Upgrade pip trước
python -m pip install --upgrade pip
pip install -r requirements.txt

# Cách 2: Cài từng gói
pip install google-generativeai
pip install pystray pillow

# Cách 3: Dùng --user nếu thiếu quyền
pip install -r requirements.txt --user
```

</details>

<details>
<summary><b>🟡 JARVIS không nghe giọng nói</b></summary>

Kiểm tra:
1. Micro đã cắm và được Windows nhận chưa? (Settings → Sound → Input)
2. Micro được chọn là Default Input Device?
3. Thử nói to hơn, hoặc ngồi gần micro hơn
4. Kiểm tra file `.env` có `GOOGLE_API_KEY` đúng không?

</details>

<details>
<summary><b>🟡 Build .EXE thất bại</b></summary>

```bash
# Cài lại PyInstaller phiên bản mới nhất
pip install --upgrade pyinstaller

# Xóa cache cũ
rmdir /s /q build dist __pycache__

# Build lại
python scripts/build_installer.py --exe-only --no-clean
```

</details>

<details>
<summary><b>🟡 Không có biểu tượng JARVIS trên system tray</b></summary>

Kiểm tra:
1. Nhấp vào mũi tên **"^"** cạnh đồng hồ → tìm biểu tượng ẩn
2. Kéo biểu tượng JARVIS ra vùng hiện
3. Nếu không thấy: mở **Task Manager** → tìm JARVIS process còn sống không

</details>

<details>
<summary><b>🟢 Muốn dùng giọng nói tiếng Anh</b></summary>

Trong file `.env` thêm:
```env
JARVIS_LANGUAGE=en
```

</details>

---

## 🧪 Kiểm Tra Hệ Thống

```bash
# Chạy tất cả 633 tests
python -m pytest tests/unit/ -v

# Tóm tắt nhanh
python -m pytest tests/unit/ -q

# Kiểm tra sức khỏe và xuất báo cáo
python scripts/health_check_report.py
# → Xuất ra: reports/health_YYYYMMDD_HHMMSS.md
```

---

## 🔄 Cập Nhật JARVIS

### Tự động (Khuyên Dùng)
```
Nói: "JARVIS, kiểm tra cập nhật"
Nói: "JARVIS, tự cập nhật đi"
```

### Thủ Công
```bash
git pull origin main
pip install -r requirements.txt
# Khởi động lại JARVIS
```

---

## 📋 Nhật Ký Phiên Bản

| Phiên Bản | Ngày | Tính Năng Nổi Bật |
|-----------|------|------------------|
| **v4.0.0** | 2026-08-28 | ReAct Autonomous Agent · Notification Hub · Windows Installer |
| v3.2.0 | 2026-08-28 | Zalo Bot 2-Way Control |
| v3.1.0 | 2026-08-28 | Browser CDP · Auto-Update · Plugin SDK · Release CI |
| v3.0.0 | 2026-08-28 | Self-Code · Semantic RAG · Night Shift · Discord Bot |
| v2.0.0 | 2026-08-24 | 9 Built-in Skills · Memory · Global Hotkeys · System Tray |

Chi tiết đầy đủ: [CHANGELOG.md](CHANGELOG.md)

---

## 🤝 Đóng Góp

Pull requests luôn được chào đón!

1. Fork repository
2. Tạo branch: `git checkout -b feature/ten-tinh-nang`
3. Commit: `git commit -m "feat: mô tả"`
4. Push: `git push origin feature/ten-tinh-nang`
5. Mở Pull Request

---

<div align="center">

Made with ❤️ by **Duong Phuoc Hung**

[⭐ Star trên GitHub](https://github.com/Duong-Phuoc-Hung/JARVIS) · [🐛 Báo Lỗi](https://github.com/Duong-Phuoc-Hung/JARVIS/issues) · [📋 Changelog](CHANGELOG.md)

</div>
