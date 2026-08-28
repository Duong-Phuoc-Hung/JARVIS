# 🤖 JARVIS - Trợ Lý AI Cá Nhân Tự Trị Cho Windows

<div align="center">

![JARVIS Banner](https://img.shields.io/badge/JARVIS-Autonomous%20AI%20Assistant-00f0ff?style=for-the-badge&logo=windows)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-633%20Passed%20(100%25)-00ff88?style=for-the-badge)
![CI](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/workflows/ci.yml/badge.svg)
![Version](https://img.shields.io/badge/Version-4.0.0-purple?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

**JARVIS** là trợ lý AI cá nhân tự trị toàn năng dành riêng cho Windows — lấy cảm hứng từ JARVIS của Tony Stark.
Hệ thống vận hành độc lập **không cần VS Code**, chạy ngầm dưới system tray, nhận lệnh bằng giọng nói tiếng Việt,
tự lập kế hoạch và thực thi mục tiêu phức tạp qua vòng lặp ReAct tự trị.

**v4.0.0:** JARVIS tự lên kế hoạch → tự chọn tool → tự thực thi → tự tổng hợp kết quả. **Không cần can thiệp.**

</div>

---

## ✨ Tính Năng Nổi Bật (v4.0.0)

| Icon | Tính Năng | Mô Tả |
|------|-----------|-------|
| 🧠 | **ReAct Autonomous Agent** | Think→Act→Observe→Reflect, 12 tools tích hợp |
| 🎙️ | **Giọng Nói Offline** | VAD + Barge-in + Piper TTS <80ms + Faster-Whisper <200ms |
| 🧬 | **Self-Coding Skills** | *"Tạo skill theo dõi giá vàng"* → tự code & đăng ký ngay |
| 🔍 | **Semantic RAG Memory** | Tìm ký ức theo nghĩa TF-IDF BM25, không cần GPU |
| 🌙 | **Night Shift Worker** | Giao việc 22h → JARVIS làm xuyên đêm → báo cáo 7h sáng |
| 👁️ | **Vision AI Screen** | `Ctrl+Shift+Space` → Gemini phân tích màn hình |
| 🌐 | **Browser CDP** | Điều khiển Chrome bằng giọng nói (Playwright) |
| 📡 | **5 Kênh Điều Khiển** | Voice + Telegram + Discord + **Zalo** + Mobile |
| 🔔 | **Notification Hub** | Toast + Sound + TTS + tất cả kênh đồng thời |
| 🏠 | **Smart Home** | Tự quét LAN tìm HA/Tasmota/Tuya |
| 🔄 | **Auto-Update** | Kiểm tra GitHub Releases mỗi 6h, tự cập nhật |
| 🧩 | **Plugin SDK** | Cài thêm kỹ năng qua `pip install jarvis-plugin-*` |
| 📦 | **Standalone .EXE** | Không cần Python — chạy thẳng, cài như app thực |

---

## 📦 Cài Đặt — 3 Cách Chạy (Không Cần VS Code)

### ⚡ Cách 1: Chạy Trực Tiếp (Development)
```bash
git clone https://github.com/Duong-Phuoc-Hung/JARVIS.git
cd JARVIS
pip install -r requirements.txt
python main.py --tray          # Chạy ngầm dưới system tray
```

### 🏗️ Cách 2: Build .EXE Standalone
```bash
pip install pyinstaller
python scripts/build_installer.py --exe-only

# Kết quả: dist/JARVIS.exe (chạy trực tiếp, không cần Python)
dist\JARVIS.exe --tray
```

### 🪟 Cách 3: Windows Installer (Khuyên Dùng)
```bash
# 1. Cài Inno Setup: https://jrsoftware.org/isdl.php
# 2. Build installer:
python scripts/build_installer.py
# 3. Chạy: dist/installer/JARVIS_Setup_v4.0.0.exe
```
Sau khi cài:
- ✅ Xuất hiện trong **Start Menu** → tìm "JARVIS"
- ✅ Icon **Desktop** (tuỳ chọn)
- ✅ **Tự khởi động** cùng Windows (tuỳ chọn)
- ✅ Gỡ cài sạch từ **Control Panel → Programs**

---

## 🧰 Danh Sách 20+ Built-in Skills

| # | Skill | Lệnh Thoại Ví Dụ | Ver |
|---|-------|-----------------|-----|
| 1 | **briefing** | "Báo cáo sáng nay" | v2 |
| 2 | **file_manager** | "Tìm file Python trong Downloads" | v2 |
| 3 | **note_taker** | "Ghi chú: họp lúc 3h" | v2 |
| 4 | **pomodoro** | "Tập trung 25 phút" | v2 |
| 5 | **system_control** | "Chụp màn hình", "Khóa máy" | v2 |
| 6 | **git_assistant** | "Trạng thái git hiện tại" | v2 |
| 7 | **calculator** | "Tính 1500 USD sang VND" | v2 |
| 8 | **clipboard** | "Đọc clipboard" | v2 |
| 9 | **app_launcher** | "Mở VS Code", "Mở Chrome" | v2 |
| 10 | **screen_context** | "Giải thích lỗi trên màn hình" | v2.2 |
| 11 | **macro_recorder** | "Lưu macro gửi email" | v2.2 |
| 12 | **sound_board** | "Phát âm hoàn thành" | v2.2 |
| 13 | **rag_search** | "Tháng trước tôi note gì?" | v3 |
| 14 | **skill_synthesizer** | "Tạo skill theo dõi giá vàng" | v3 |
| 15 | **night_planner** | "Tối nay phân tích dữ liệu" | v3 |
| 16 | **smart_home_discovery** | "Quét thiết bị nhà thông minh" | v2.3 |
| 17 | **browser_control** | "Mở YouTube", "Tìm kiếm..." | v3.1 |
| 18 | **auto_updater** | "Kiểm tra cập nhật JARVIS" | v3.1 |
| 19 | **[ReAct Agent Mode]** | "Phân tích toàn bộ code src/" | v4 |
| 20+ | **[pip Plugins]** | `pip install jarvis-plugin-*` | v3.1 |

---

## 📡 Kênh Điều Khiển (5 Kênh)

| Kênh | Cài Đặt | Lệnh Mẫu |
|------|---------|----------|
| 🎙️ **Voice** | Mặc định | *"Hey JARVIS, báo cáo sáng"* |
| 📱 **Telegram** | Set `TELEGRAM_BOT_TOKEN` trong `.env` | `/briefing`, `/note họp 3h` |
| 💬 **Discord** | Set `DISCORD_BOT_TOKEN` | `!status`, `!screenshot`, `!briefing` |
| 📞 **Zalo** | Set `ZALO_ACCESS_TOKEN` + webhook | `/status`, `/note`, `/calc 100*1.1` |
| 📲 **Mobile Bridge** | Chạy cùng LAN | Gửi file phone↔PC |

---

## ⌨️ Phím Tắt Toàn Hệ Thống

| Phím Tắt | Chức Năng |
|----------|----------|
| `Ctrl+Shift+J` | Bật/Tắt JARVIS listening |
| `Ctrl+Shift+L` | Lock PC ngay lập tức |
| `Ctrl+Shift+M` | Tắt tiếng mic |
| `Ctrl+Shift+B` | Mở Briefing sáng |
| `Ctrl+Shift+S` | Chụp ảnh màn hình ra Desktop |
| `Ctrl+Shift+Space` | **Phân tích màn hình (Vision AI)** |

---

## ⚙️ Cấu Hình `.env`

```env
# LLM
GOOGLE_API_KEY=your_gemini_key

# Telegram Bot
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=your_chat_id

# Discord Bot
DISCORD_BOT_TOKEN=your_discord_token

# Zalo Official Account
ZALO_ACCESS_TOKEN=your_zalo_oa_token
ZALO_OA_ID=your_oa_id
ZALO_WEBHOOK_SECRET=your_secret

# TTS
ELEVENLABS_API_KEY=optional_key

# Chế độ môi trường
JARVIS_HEADLESS=0        # 1 = không mở cửa sổ (CI/server)
JARVIS_MOCK_AUDIO=0      # 1 = dùng mock audio (test)
```

---

## 🧪 Chạy Tests

```bash
# Tất cả 633 tests
python -m pytest tests/unit/ -v

# Chỉ test 1 module
python -m pytest tests/unit/test_react_agent.py -v

# Kiểm tra sức khỏe hệ thống
python scripts/health_check_report.py
```

---

## 🏗️ CI/CD Pipeline

```
Push → main
  ├── 🔍 Lint Job     (syntax check 30+ modules)
  ├── 🧪 Test Job     (633 tests, JUnit XML report)
  └── 📦 Import Check (validate all new modules)
        ↓
Tag v*.*.*
  └── 🚀 Release Job  (PyInstaller .exe → GitHub Release)
```

[![CI Status](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/workflows/ci.yml/badge.svg)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)

---

## 📋 Nhật Ký Cập Nhật

Xem chi tiết tại [CHANGELOG.md](CHANGELOG.md).

| Version | Nổi Bật |
|---------|---------|
| **v4.0.0** | ReAct Agent, Notification Hub, Windows Installer |
| v3.2.0 | Zalo Bot 2-Way Control |
| v3.1.0 | Browser CDP, Auto-Update, Plugin SDK, Release CI |
| v3.0.0 | Self-Code, Semantic RAG, Night Shift, Discord |
| v2.0.0 | 9 Skills, Memory, Hotkeys, Tray Daemon |
