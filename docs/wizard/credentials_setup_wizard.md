# 🔐 JARVIS Credentials Setup Wizard

> **Wizard Version**: 1.0.0 — Updated 2026-09-16  
> **Applies to**: D-06 Telegram, D-07 Zalo OA, D-08 Discord, D-09 Gmail SMTP  
> **Repo**: `Duong-Phuoc-Hung/JARVIS`

Hướng dẫn này cung cấp các bước **copy-paste chính xác** để thiết lập từng credential cần thiết cho JARVIS. Hoàn thành theo thứ tự từ D-06 → D-09.

---

## Mục lục

- [D-06 — Telegram Bot Token](#d-06--telegram-bot-token)
- [D-07 — Zalo Official Account](#d-07--zalo-official-account)
- [D-08 — Discord Bot Token](#d-08--discord-bot-token)
- [D-09 — Gmail App Password (SMTP)](#d-09--gmail-app-password-smtp)
- [Xác minh tất cả credentials](#xác-minh-tất-cả-credentials)

---

## D-06 — Telegram Bot Token

### URL cần truy cập

```
https://t.me/BotFather
```

*(Mở trong ứng dụng Telegram Desktop hoặc web: https://web.telegram.org)*

### Các bước thực hiện

1. Mở Telegram và tìm kiếm **@BotFather**, hoặc truy cập trực tiếp https://t.me/BotFather.
2. Nhấn **Start** (hoặc gửi `/start`) nếu đây là lần đầu dùng BotFather.
3. Gửi lệnh `/newbot` vào chat với BotFather.
4. Nhập **tên hiển thị** cho bot khi được hỏi — ví dụ: `JARVIS Assistant`.
5. Nhập **username** cho bot khi được hỏi — phải kết thúc bằng `bot`, ví dụ: `JARVISAssistant_bot`.
6. BotFather sẽ trả về một đoạn tin nhắn chứa token — **sao chép toàn bộ chuỗi token**.

### Định dạng token

```
123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-abcdef01234
```

*(Phần trước dấu `:` là Bot ID; phần sau là secret. Không chia sẻ phần secret.)*

### Thiết lập GitHub Secret

```bash
gh secret set TELEGRAM_BOT_TOKEN --body "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-abcdef01234" --repo Duong-Phuoc-Hung/JARVIS
```

> Thay `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-abcdef01234` bằng token thực của bạn.

### Thiết lập local `.env`

Thêm dòng sau vào file `.env` tại thư mục gốc dự án:

```dotenv
# ── Telegram Bot Controller (D-06) ──────────────────────────
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-abcdef01234
```

### Lấy Telegram User ID (để whitelist)

1. Tìm **@userinfobot** trên Telegram: https://t.me/userinfobot
2. Gửi bất kỳ tin nhắn nào — bot sẽ trả về `Id: 987654321`.
3. Thêm User ID đó vào `.env`:

```dotenv
TELEGRAM_WHITELIST_USER_IDS=987654321
```

### Kiểm tra nhanh (sau khi thiết lập)

```bash
curl "https://api.telegram.org/bot<TOKEN>/getMe"
# Kết quả mong đợi: {"ok":true,"result":{"username":"JARVISAssistant_bot",...}}
```

---

## D-07 — Zalo Official Account

### URL cần truy cập

```
https://developers.zalo.me
```

*(Cần tài khoản Zalo cá nhân đã xác minh số điện thoại)*

### Các bước thực hiện

1. Truy cập https://developers.zalo.me và đăng nhập bằng tài khoản Zalo.
2. Nhấn **"Tạo ứng dụng mới"** (hoặc **"Create App"**) ở góc trên bên phải.
3. Chọn loại ứng dụng **"Official Account"** và điền tên ứng dụng, ví dụ: `JARVIS-OA`.
4. Hoàn tất tạo app — ghi lại **App ID** và **App Secret** hiển thị trong trang Dashboard.
5. Trong menu trái, chọn **"Official Account"** → **"Liên kết OA"**.
6. Liên kết với Zalo Official Account của bạn (tạo tại https://oa.zalo.me nếu chưa có).
7. Vào tab **"Access Token"** → nhấn **"Tạo Access Token"** → sao chép **OA Access Token**.

### Định dạng credentials

| Credential | Ví dụ định dạng |
|---|---|
| App ID | `1234567890123456789` (chuỗi số 19 chữ số) |
| App Secret | `abcdef1234567890abcdef1234567890` (chuỗi hex 32 ký tự) |
| OA Access Token | `v4_xxxxxxx.yyyyyyy.zzzzzzz...` (JWT token dài) |

### Thiết lập GitHub Secrets

```bash
gh secret set ZALO_OA_ACCESS_TOKEN --body "v4_xxxxxxx.yyyyyyy.zzzzzzz" --repo Duong-Phuoc-Hung/JARVIS
gh secret set ZALO_APP_ID --body "1234567890123456789" --repo Duong-Phuoc-Hung/JARVIS
gh secret set ZALO_APP_SECRET --body "abcdef1234567890abcdef1234567890" --repo Duong-Phuoc-Hung/JARVIS
```

### Thiết lập local `.env`

```dotenv
# ── Zalo Official Account (D-07) ────────────────────────────
ZALO_OA_ACCESS_TOKEN=v4_xxxxxxx.yyyyyyy.zzzzzzz
ZALO_APP_ID=1234567890123456789
ZALO_APP_SECRET=abcdef1234567890abcdef1234567890
```

> **Lưu ý**: OA Access Token hết hạn sau 3 tháng — cần refresh định kỳ tại Developers Portal.

### Cấu hình Webhook (tùy chọn cho production)

Trong trang Zalo Developers → App của bạn → **"Webhook"**:

```
Webhook URL: https://your-server.com:8765/zalo/webhook
```

Với môi trường local, dùng ngrok:

```bash
ngrok http 8765
# Paste ngrok HTTPS URL vào Webhook URL trên portal
```

---

## D-08 — Discord Bot Token

### URL cần truy cập

```
https://discord.com/developers/applications
```

*(Cần tài khoản Discord đã xác minh email)*

### Các bước thực hiện

1. Truy cập https://discord.com/developers/applications và đăng nhập.
2. Nhấn **"New Application"** ở góc trên bên phải.
3. Đặt tên application — ví dụ: `JARVIS` — rồi nhấn **"Create"**.
4. Trong menu trái, chọn **"Bot"**.
5. Nhấn **"Reset Token"** → xác nhận → **sao chép token hiển thị** (chỉ hiện một lần!).
6. Cuộn xuống phần **"Privileged Gateway Intents"** và bật **cả hai** intents sau:
   - ✅ **MESSAGE CONTENT INTENT**
   - ✅ **SERVER MEMBERS INTENT**
7. Nhấn **"Save Changes"**.

### Định dạng token

```
YOUR_DISCORD_BOT_TOKEN_HERE
```

*(Base64-encoded; 3 phần ngăn cách bởi dấu `.`)*

### Thiết lập GitHub Secret

```bash
gh secret set DISCORD_BOT_TOKEN --body "YOUR_DISCORD_BOT_TOKEN_HERE" --repo Duong-Phuoc-Hung/JARVIS
```

### Thiết lập local `.env`

```dotenv
# ── Discord Bot Controller (D-08) ───────────────────────────
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
DISCORD_GUILD_ID=123456789012345678
DISCORD_CHANNEL_ID=123456789012345678
```

### Mời Bot vào Server Discord của bạn

1. Trong trang Application → menu trái chọn **"OAuth2"** → **"URL Generator"**.
2. Tích **Scopes**: `bot`
3. Tích **Bot Permissions**: `Administrator` (hoặc chọn permissions cụ thể)
4. Sao chép URL được tạo và mở trong trình duyệt để mời bot vào server.

**URL mời nhanh** (thay `CLIENT_ID` bằng Application ID của bạn):

```
https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=8&scope=bot
```

> Application ID (khác với Bot Token) tìm tại trang **"General Information"** của Application.

### Lấy Discord User ID (để whitelist)

1. Trong Discord, vào **Settings → Advanced → bật Developer Mode**.
2. Chuột phải vào tên của bạn → **"Copy User ID"**.
3. Thêm vào `.env`:

```dotenv
DISCORD_WHITELIST_USER_IDS=987654321012345678
```

---

## D-09 — Gmail App Password (SMTP)

> **Lý do cần App Password**: Google không cho phép dùng mật khẩu chính để đăng nhập qua SMTP/IMAP.
> App Password là mật khẩu 16 ký tự dùng riêng cho ứng dụng bên thứ ba.

### URL cần truy cập

```
https://myaccount.google.com/security
```

Hoặc trực tiếp vào trang App Passwords:

```
https://myaccount.google.com/apppasswords
```

### Các bước thực hiện

1. Truy cập https://myaccount.google.com/security và đăng nhập Gmail cần dùng.
2. Tìm mục **"2-Step Verification"** — nếu chưa bật, nhấn vào và làm theo hướng dẫn để bật.
3. Sau khi bật 2FA, truy cập https://myaccount.google.com/apppasswords.
4. Trong phần **"Select app"**, chọn **"Mail"**.
5. Trong phần **"Select device"**, chọn **"Windows Computer"**.
6. Nhấn **"Generate"**.
7. Google hiển thị mật khẩu **16 ký tự có khoảng trắng** — sao chép và **bỏ toàn bộ khoảng trắng** khi dán vào config.

### Định dạng App Password

```
# Google hiển thị (có khoảng trắng — để dễ đọc):
abcd efgh ijkl mnop

# Dùng trong config (KHÔNG có khoảng trắng — 16 ký tự liền):
abcdefghijklmnop
```

### Thiết lập GitHub Secrets

```bash
gh secret set SMTP_PASSWORD --body "abcdefghijklmnop" --repo Duong-Phuoc-Hung/JARVIS
gh secret set SMTP_USER --body "your-email@gmail.com" --repo Duong-Phuoc-Hung/JARVIS
```

### Thiết lập local `.env`

```dotenv
# ── Gmail SMTP / IMAP (D-09) ────────────────────────────────
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

### Kiểm tra nhanh IMAP (Python)

```python
import imaplib
conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
conn.login("your-email@gmail.com", "abcdefghijklmnop")
print(conn.list())  # Liệt kê mailboxes — nếu thành công là OK
conn.logout()
```

---

## Xác minh tất cả credentials

Sau khi thiết lập, chạy script kiểm tra:

```bash
cd "d:\Software GitCode\JARVIS"
python scripts/verify_credentials.py
```

Kết quả mong đợi khi tất cả credentials đã được cấu hình đầy đủ:

```
[D-06 Telegram]    ✅ CONFIGURED  — TelegramBotController: bot_token=set
[D-07 Zalo OA]     ✅ CONFIGURED  — ZaloBotController: access_token=set
[D-08 Discord]     ✅ CONFIGURED  — DiscordBotController: bot_token=set
[D-09 Gmail IMAP]  ✅ CONFIGURED  — IMAPEmailReader: credentials=set
```

---

## Tham chiếu nhanh — Tất cả GitHub Secrets

| Secret Name | Module | Bắt buộc |
|---|---|:---:|
| `TELEGRAM_BOT_TOKEN` | `jarvis.comms.telegram` | ✅ |
| `ZALO_OA_ACCESS_TOKEN` | `jarvis.comms.zalo` | ✅ |
| `ZALO_APP_ID` | `jarvis.comms.zalo` | ✅ |
| `ZALO_APP_SECRET` | `jarvis.comms.zalo` | ✅ |
| `DISCORD_BOT_TOKEN` | `jarvis.comms.discord` | ✅ |
| `SMTP_USER` | `jarvis.comms.email_imap` | ✅ |
| `SMTP_PASSWORD` | `jarvis.comms.email_imap` | ✅ |

---

*Tài liệu này được tạo tự động bởi JARVIS Credentials Setup Wizard — `docs/wizard/credentials_setup_wizard.md`*
