# 🤖 JARVIS - Trợ Lý AI Cá Nhân Tự Trị Cho Windows

<div align="center">

![JARVIS Banner](https://img.shields.io/badge/JARVIS-Autonomous%20AI%20Assistant-00f0ff?style=for-the-badge&logo=windows)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-405%2F405%20Passed%20(100%25)-00ff88?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

**JARVIS** là một trợ lý AI cá nhân tự trị toàn năng (Autonomous AI Desktop Assistant) dành riêng cho Windows, lấy cảm hứng từ JARVIS của Tony Stark. Hệ thống có khả năng vận hành độc lập như một ứng dụng chạy ngầm, nhận diện giọng nói tiếng Việt / tiếng Anh ("Hey JARVIS"), lập kế hoạch tác vụ tự động (ReAct Planner), điều khiển màn hình (Computer-Use), tự động hóa trình duyệt và thực thi mã an toàn.

</div>

---

## ✨ Điểm Nổi Bật & Tính Năng Chính

* 🎙️ **Điều Khiển Bằng Giọng Nói & Đánh Thức Tự Động**: Đánh thức bằng từ khóa *"Hey JARVIS"*, chuyển đổi giọng nói (STT Whisper) và phản hồi tự nhiên (TTS ElevenLabs / SAPI5).
* 🖥️ **Ứng Dụng Độc Lập Chạy Ngầm (System Tray Daemon)**: Chạy dưới khay hệ thống cạnh đồng hồ với biểu tượng Arc Reactor phát sáng, không cần mở VS Code.
* 🚀 **Khởi Động Nhanh 1-Click & Tự Khởi Động Cùng Windows**: Hỗ trợ phím tắt Desktop, Start Menu và cấu hình tự bật cùng máy qua Windows Registry.
* 🧠 **Bộ Nhớ Dài Hạn (Persistent Memory)**: Tự động ghi nhớ thói quen, sở thích, thông tin cá nhân và tóm tắt hoạt động hàng ngày qua SQLite WAL.
* 🎯 **Lập Kế Hoạch Tự Trị (ReAct Planner & DAG Engine)**: Phân rã mục tiêu phức tạp thành đồ thị phụ thuộc DAG, tự động phản tư và sửa lỗi khi gặp sự cố.
* 👁️ **Thị Giác Máy Tính & Thao Tác Chuột/Phím (Computer-Use Vision & GUI Actor)**: Nhận diện tọa độ phần tử giao diện 1000x1000, tự động click, gõ chữ, kéo thả và kiểm chứng hình ảnh trước/sau thao tác.
* 🌐 **Tự Động Hóa Web & So Sánh Giá (Browser Automation)**: Trích xuất nội dung web sang Markdown, lưu giữ phiên đăng nhập/cookie Netscape và so sánh giá sàn TMĐT.
* ⚡ **Zero-Idle Sleep Mode**: Tối ưu hóa tài nguyên, mức sử dụng CPU ở trạng thái chờ cực thấp (**< 0.05% CPU**).

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

### 2. Tạo Phím Tắt Khởi Động 1-Click (Desktop & Start Menu)
Chạy script tự động tạo shortcut:
```bash
python scripts/create_shortcuts.py
```
Sau khi chạy xong, bạn có thể:
1. Nhấp đúp vào biểu tượng **JARVIS AI Assistant** trên Màn hình chính (Desktop).
2. Tìm kiếm **"JARVIS Assistant"** trong Windows Start Menu.
3. Hoặc nhấp đúp vào tệp `run_jarvis.bat`.

---

## ⌨️ Phím Tắt & Thao Tác Nhanh

| Thao Tác | Phím Tắt / Hành Động | Chức Năng |
| :--- | :--- | :--- |
| **Bật/Tắt HUD** | `Ctrl + Shift + J` | Mở/đóng giao diện Holographic Overlay HUD |
| **Đánh Thức** | Nói *"Hey JARVIS"* | Kích hoạt trợ lý lắng nghe lệnh giọng nói |
| **Khay Hệ Thống** | Click chuột phải icon Tray | Mở menu tùy chọn, tắt mic, quản lý autostart |
| **Thoát Ứng Dụng** | Menu Tray -> **Exit** | Dừng hoàn toàn và giải phóng 100% tài nguyên máy |

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

Kiểm tra toàn bộ 405 bài test kiểm định chất lượng:
```bash
python -m pytest tests/unit/ -v
```

---

## 📋 Nhật Ký Cập Nhật (Changelog)
Chi tiết các bản cập nhật và tối ưu hóa xem tại [CHANGELOG.md](CHANGELOG.md).
