import os

changelog_entry = """## [5.1.10] T-03 Telegram real transport (2026-09-19)

> **Mục tiêu**: Thay thế Telegram mock transport bằng real transport sử dụng `requests`, đảm bảo chuẩn Fail-Closed và cấu hình theo config, không phụ thuộc vào `fake http_client`.

### 1. Root Cause & Bối cảnh
- Telegram transport đang phụ thuộc vào mock object (`mock_http` / `http_client`) và chưa có logic fetch update (`getUpdates`) hay gửi messages thật (`sendMessage`) qua API Telegram.
- `NotificationHub` chưa kiểm tra trạng thái trả về từ `telegram_controller.send_message` khiến các thông báo có thể bị bỏ lỡ âm thầm.
- Thiếu cơ chế init webhook/polling an toàn bên trong `JarvisApp`.

### 2. Chi tiết thay đổi kỹ thuật

#### `jarvis/comms/telegram.py`
- Bổ sung `requests.Session` để gọi trực tiếp các HTTP Endpoint `sendMessage`, `sendPhoto`, và `getUpdates`.
- Xử lý các mã lỗi: `401` -> `AUTH_FAILED`, `429` -> `RATE_LIMITED`, timeout/network -> `TIMEOUT`/`ERROR`.
- Hiện thực hoá vòng lặp long polling `_loop` trong `TelegramPollThread` khởi động bằng `start()` và dừng qua `stop()`.
- Theo dõi `update_id` (`last_update_id`) đảm bảo idempotency không xử lý trùng update.

#### `jarvis/core/app.py`
- Khởi tạo trực tiếp `TelegramBotController` trong constructor `JarvisApp` với bot_token thực tế qua `get_secret` và truyền sang `WorkerNotificationDispatcher`.
- Bổ sung gọi `.stop()` cho Telegram controller tại hàm `shutdown`.

#### `jarvis/workers/notification_hub.py`
- Bổ sung logic kiểm tra kết quả `tg.send_message`. Trả về `False` nếu telegram báo lỗi hoặc không truyền được tin.

#### `tests/test_telegram.py`
- Bổ sung các unit tests kiểm tra: `test_telegram_send_message_missing_token`, `test_telegram_send_photo_missing_token`, `test_telegram_poll_missing_token`, `test_telegram_unauthorized_user`, `test_telegram_authorized_user`.

### 3. Kết quả kiểm thử
- `test_telegram.py` unit tests 100% pass, xử lý đúng hành vi block unauthorized ID và gracefully handling missing token.
- Negative tests: Passed.
- Live roundtrip E2E: Tạm thời BLOCKED_FOR_LIVE_CERTIFICATION do thiếu credential thật tại môi trường test, tuy nhiên code logic đã hoàn thiện và đáp ứng đúng acceptance criteria.

"""

with open("CHANGELOG.md", "r", encoding="utf-8") as f:
    content = f.read()

with open("CHANGELOG.md", "w", encoding="utf-8") as f:
    f.write(changelog_entry + content)
