# 🤖 JARVIS - Trợ Lý AI Cá Nhân Tự Trị Cho Windows

<div align="center">

![JARVIS Banner](https://img.shields.io/badge/JARVIS-Autonomous%20AI%20Assistant-00f0ff?style=for-the-badge&logo=windows)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-500%2B%20Passed%20(100%25)-00ff88?style=for-the-badge)
![CI](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)
![Version](https://img.shields.io/badge/Version-3.0.0-purple?style=for-the-badge)

**JARVIS** là một trợ lý AI cá nhân tự trị toàn năng (Autonomous AI Desktop Assistant) dành riêng cho Windows, lấy cảm hứng từ JARVIS của Tony Stark. Hệ thống có khả năng vận hành độc lập như một ứng dụng chạy ngầm, nhận diện giọng nói tiếng Việt / tiếng Anh ("Hey JARVIS"), lập kế hoạch tác vụ tự động (ReAct Planner), điều khiển màn hình (Computer-Use), tự động hóa trình duyệt và thực thi mã an toàn.

**Mới trong v3.0.0:** JARVIS có thể TỰ TIẾN HÓA — tự sinh kỹ năng mới bằng AI, tìm kiếm ký ức thông minh (Semantic RAG), làm việc xuyên đêm tự trị, điều khiển qua Discord, cầu nối file mobile, và tự khám phá thiết bị nhà thông minh.

</div>

---

## ✨ Điểm Nổi Bật & Tính Năng Chính (v3.0.0)

* 🎙️ **Giọng Nói Thời Gian Thực + Barge-in**: VAD energy-based, full-duplex ngắt lời bất kỳ lúc, Piper TTS offline < 80ms, Faster-Whisper STT < 200ms
* 🧬 **Tự Sinh Kỹ Năng Mới (Self-Coding)**: *"JARVIS, tạo kỹ năng theo dõi giá vàng"* → tự viết code, test và đăng ký vào hệ thống ngay lập tức
* 🔍 **Ký Ức Thông Minh (Semantic RAG)**: Tìm kiếm toàn bộ ký ức theo ngữ nghĩa TF-IDF cosine — không cần GPU
* 🌙 **Night Shift Worker**: Giao nhiệm vụ lúc 22h → JARVIS tự làm xuyên đêm → báo cáo Markdown lúc 7h sáng
* 👁️ **Phân Tích Màn Hình (Vision AI)**: `Ctrl+Shift+Space` → chụp màn hình → Gemini Vision giải thích/tóm tắt/dịch
* 📱 **Điều Khiển Đa Kênh**: Telegram, Discord (`!status`, `!briefing`, `!screenshot`...), Mobile File Bridge
* 🏠 **Smart Home Auto-Discovery**: Tự quét LAN tìm Home Assistant, Tasmota, Tuya
* ⌨️ **Phím Tắt Toàn Hệ Thống**: 6 hotkeys Win32 từ mọi ứng dụng
* 🖥️ **Chạy Ngầm System Tray**: Khởi động Windows, tắt theo lịch, biểu tượng Arc Reactor
* 📦 **CI/CD Tự Động**: GitHub Actions chạy 500+ tests mỗi lần push

---

## 🧰 Danh Sách 18 Built-in Skills (v3.0.0)

| # | Skill | Lệnh Thoại Ví Dụ | Phiên Bản |
|---|-------|-----------------|----------|
| 1 | **briefing** | "Báo cáo sáng nay" | v2.0.0 |
| 2 | **file_manager** | "Tìm file Python trong Downloads" | v2.0.0 |
| 3 | **note_taker** | "Ghi chú: họp lúc 3h" | v2.0.0 |
| 4 | **pomodoro** | "Bắt đầu tập trung 25 phút" | v2.0.0 |
| 5 | **system_control** | "Chụp màn hình", "Khóa máy" | v2.0.0 |
| 6 | **git_assistant** | "Trạng thái git hiện tại" | v2.0.0 |
| 7 | **calculator** | "Tính 1500 USD sang VND" | v2.0.0 |
| 8 | **clipboard** | "Đọc clipboard", "Copy văn bản" | v2.0.0 |
| 9 | **app_launcher** | "Mở VS Code", "Mở Chrome" | v2.0.0 |
| 10 | **screen_context** | "Giải thích lỗi trên màn hình" | v2.2.0 |
| 11 | **macro_recorder** | "Lưu macro gửi email", "Phát lại" | v2.2.0 |
| 12 | **sound_board** | "Phát âm thanh hoàn thành" | v2.2.0 |
| 13 | **rag_search** | "Tôi đã note gì về dự án X?" | v3.0.0 |
| 14 | **skill_synthesizer** | "Tạo kỹ năng theo dõi giá vàng" | v3.0.0 |
| 15 | **night_planner** | "Tối nay phân tích dữ liệu cho tôi" | v3.0.0 |
| 16 | **smart_home_discovery** | "Quét thiết bị nhà thông minh" | v2.3.0 |
| 17 | **[Synthesized Skills]** | Tạo tự động từ mô tả | v3.0.0 |
| 18 | **[External Plugins]** | Cài qua pip (v3.3 roadmap) | — |

---

## ⌨️ Phím Tắt Toàn Hệ Thống (Global Hotkeys)

| Phím Tắt | Chức Năng |
|----------|----------|
| `Ctrl+Shift+J` | Bật/Tắt JARVIS listening |
| `Ctrl+Shift+L` | Lock PC ngay lập tức |
| `Ctrl+Shift+M` | Tắt tiếng mic |
| `Ctrl+Shift+B` | Mở Briefing sáng |
| `Ctrl+Shift+S` | Chụp ảnh màn hình ra Desktop |
| `Ctrl+Shift+Space` | Phân tích màn hình hiện tại (Vision AI) |

---



---

## 🛠️ Hướng Dẫn Cài Đặt & Khởi Chạy

### 1. Cài Đặt Môi Trường
```bash
# Clone repository
git clone https://github.com/Duong-Phuoc-Hung/JARVIS.git
cd JARVIS

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### 2. Đóng Gói Ứng Dụng .EXE Độc Lập (PyInstaller)
```bash
# Tạo file dist/JARVIS.exe độc lập
python build.py
```

### 3. Tạo Phím Tắt Khởi Động 1-Click (Desktop & Start Menu)
Chạy script tự động tạo shortcut:
```bash
python scripts/create_shortcuts.py
```
Sau khi chạy xong, bạn có thể:
1. Nhấp đúp vào biểu tượng **JARVIS AI Assistant** trên Màn hình chính (Desktop).
2. Tìm kiếm **"JARVIS Assistant"** trong Windows Start Menu.
3. Hoặc nhấp đúp vào tệp `run_jarvis.bat`.

---

## ⌨️ Phím Tắt Toàn Cầu (Global Shortcuts)

| Phím Tắt | Chức Năng |
| :--- | :--- |
| `Ctrl + Shift + J` | Bật / Tắt giao diện Holographic Overlay HUD |
| `Ctrl + Shift + L` | Kích hoạt ghi âm giọng nói tức thì (Push-To-Talk) |
| `Ctrl + Shift + M` | Bật / Tắt nhận diện từ khóa Hey JARVIS |
| `Ctrl + Shift + B` | Phát báo cáo tổng hợp buổi sáng (Briefing) |
| `Ctrl + Shift + S` | Kiểm tra nhanh tình trạng phần cứng hệ thống |

---

## 🧩 Thư Viện Kỹ Năng Sẵn Có (Built-in Skills)

| Kỹ Năng | Tên Gọi | Mô Tả & Câu Lệnh Mẫu |
| :--- | :--- | :--- |
| **Briefing Sáng** | `briefing` | *"JARVIS, briefing sáng nay"* — Tổng hợp thời tiết, tin tức, crypto, lịch trình |
| **Quản Lý File** | `file_manager` | *"JARVIS, tìm file report"* hoặc *"mở thư mục Downloads"* |
| **Ghi Chú Nhanh** | `note_taker` | *"JARVIS, ghi chú: gọi cho khách hàng lúc 3 giờ"* |
| **Pomodoro** | `pomodoro` | *"JARVIS, bắt đầu Pomodoro 25 phút"* |
| **Điều Khiển Hệ Thống** | `system_control` | *"JARVIS, tăng âm lượng"*, *"chụp màn hình"*, *"thu nhỏ tất cả"* |
| **Trợ Lý Git** | `git_assistant` | *"JARVIS, git status"* — Báo cáo thay đổi repository bằng tiếng Việt |
| **Máy Tính & Tỷ Giá** | `calculator` | *"JARVIS, 15% của 2 triệu"* hoặc *"đổi 100 USD sang VND"* |
| **Clipboard** | `clipboard` | *"JARVIS, đọc clipboard"* hoặc *"sao chép vào clipboard"* |
| **Mở Ứng Dụng** | `app_launcher` | *"JARVIS, mở Chrome"*, *"mở Spotify"*, *"mở VS Code"* |

---

## 💻 Quản Lý Khởi Động Cùng Windows (Autostart)

Bạn có thể quản lý tự khởi động qua dòng lệnh hoặc qua menu khay hệ thống:

```bash
# Bật tự khởi động cùng Windows
python -m jarvis install-autostart

# Tắt tự khởi động cùng Windows
python -m jarvis uninstall-autostart

# Kiểm tra trạng thái hiện tại
python -m jarvis autostart-status
```

---

## 🔍 Kiểm Tra Sức Khỏe Toàn Bộ Hệ Thống (Health Check)

Kiểm tra trạng thái sẵn sàng của toàn bộ 17 phân hệ:
```bash
python -m jarvis health-check
```

---

## 🧪 Chạy Kiểm Thử (Unit Tests)

Kiểm tra toàn bộ test suite kiểm định chất lượng:
```bash
python -m pytest tests/unit/ -v
```

---

## 📋 Nhật Ký Cập Nhật (Changelog)
Chi tiết các bản cập nhật và tối ưu hóa xem tại [CHANGELOG.md](CHANGELOG.md).
