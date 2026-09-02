# Original User Request

> **Original feature concept attribution:** The pre-existing JARVIS concepts
> for voice-first interaction, wake-word activation, STT/TTS, Local/Cloud AI
> routing, hardware diagnostics and window management, internal-network
> InfoSec auditing, workflow automation, data analysis, IoT/Home Assistant,
> biometric face authentication, gesture control, multi-channel
> communications, self-healing, and destructive-action safety guardrails were
> originally designed by **Huynh Minh Hoa
> ([@hoahuynh19a-crypto](https://github.com/hoahuynh19a-crypto))**.
>
> This credit is limited to those original concepts. Later extensions and the
> implementation, testing, security-hardening, benchmarking, and maintenance
> work in this repository are attributed separately through Git history and
> pull requests.
## 2026-08-24T01:02:20Z

JARVIS là một Windows desktop AI assistant với 67 modules, 537+ tests đang pass. Hệ thống hiện có gesture detection, voice pipeline (STT→LLM→TTS), overlay UI, và smart keyword router. Tuy nhiên JARVIS vẫn còn rất hạn chế — không có memory, không nhìn được màn hình, không tự động hóa được máy tính, không thể làm việc liên tục như một trợ lý thực sự. Mục tiêu: khai phá toàn bộ tiềm năng, biến JARVIS thành Personal AI không thua gì các sản phẩm thương mại.

Working directory: d:/Software GitCode/JARVIS
Integrity mode: development

---

## Hạn chế hiện tại cần vượt qua

1. **Chỉ nghe khi vỗ tay** — không có wake word, phải luôn dùng tay
2. **Không có memory** — mỗi lần hỏi là fresh start, không nhớ ngữ cảnh
3. **Không nhìn được màn hình** — không biết user đang làm gì
4. **Không điều khiển được máy tính** — chỉ mở app, không tương tác được
5. **Không tìm kiếm web** — không có thông tin realtime
6. **Không chủ động** — chỉ phản ứng, không tự nhắc nhở hay cảnh báo
7. **Không nhớ preferences** — không biết user thích gì
8. **Overlay đơn giản** — chỉ show/hide, không phải giao diện thực sự

---

## Requirements

### R1. Wake Word Detection — "Hey JARVIS"

Thay thế/bổ sung cho double clap: JARVIS lắng nghe liên tục wake word "Hey JARVIS" (hoặc "JARVIS" đơn giản) bằng lightweight local model (Vosk hoặc Porcupine hoặc custom energy + keyword detection). Khi nghe thấy wake word:
- Overlay xuất hiện ngay lập tức
- JARVIS nói "Vâng thưa Ngài" và bắt đầu ghi âm command
- Double clap vẫn hoạt động song song như backup
- Wake word có thể tắt/bật qua tray icon (để không làm phiền khi họp)

### R2. Memory & Context System — JARVIS Nhớ Mọi Thứ

Xây dựng persistent memory layer:
- **Short-term**: Conversation context trong session (10 turns gần nhất)
- **Long-term**: SQLite database lưu facts về user: tên, sở thích, thói quen, projects đang làm
- **Episodic**: Lịch sử tất cả interactions với timestamp và outcome
- JARVIS tự học preferences: "Ngài hay hỏi về thời tiết lúc sáng", "Ngài thích nhạc lo-fi khi làm việc"
- Khi LLM nhận command, tự động inject relevant memories vào system prompt
- Lệnh "JARVIS, nhớ rằng..." → lưu vào long-term memory ngay lập tức
- Lệnh "JARVIS, hôm nay tôi đã làm gì?" → tóm tắt episodic log

### R3. Screen Vision — JARVIS Nhìn Thấy Màn Hình

Tích hợp khả năng nhìn và hiểu màn hình:
- Chụp screenshot khi được kích hoạt (hoặc theo yêu cầu)
- Gửi screenshot lên Vision LLM (Gemini Vision hoặc GPT-4o Vision) để phân tích
- JARVIS trả lời các câu hỏi về màn hình: "Lỗi này là gì?", "File này nói về cái gì?", "Tab nào đang mở?"
- OCR text extraction từ screenshot (pytesseract hoặc Gemini Vision)
- Tự động detect khi có error dialog/warning popup và chủ động thông báo
- Lệnh "JARVIS, tóm tắt tài liệu này" → screenshot + vision analysis + TTS summary

### R4. Computer Control — JARVIS Điều Khiển Máy Tính

Cho JARVIS khả năng thực thi thao tác trên máy tính:
- **Window management**: "JARVIS, đóng tab này", "JARVIS, minimize tất cả", "JARVIS, chụp màn hình"
- **Mouse/Keyboard**: pyautogui để click, type, hotkey (chỉ sau voice confirmation với high-risk actions)
- **Volume/Display**: Điều chỉnh âm lượng, độ sáng, chuyển màn hình bằng giọng nói
- **Clipboard**: "JARVIS, copy cái này", "JARVIS, dán vào đây"
- **App switching**: Alt+Tab, focus window theo tên app
- **File operations**: "JARVIS, tìm file X", "JARVIS, mở thư mục Downloads"
- Safety: Mọi destructive action (xóa file, format) yêu cầu xác nhận bằng giọng nói

### R5. Web Intelligence — JARVIS Biết Chuyện Thế Giới

Tích hợp real-time web access:
- **Web search**: DuckDuckGo hoặc SerpAPI để search và tóm tắt kết quả
- **Thời tiết**: OpenWeatherMap API → đọc thời tiết Hà Nội/HCM theo location config
- **Tin tức**: RSS feed reader → tóm tắt tin tức công nghệ/crypto/thế giới buổi sáng
- **Currency/Crypto**: Rate exchange realtime (BTC, ETH, USD/VND)
- **Stock**: Giá cổ phiếu theo mã (VNIndex, AAPL, etc.)
- Lệnh "JARVIS, briefing sáng nay" → tổng hợp thời tiết + tin tức + crypto + lịch hôm nay
- Kết quả đọc to + hiển thị trên overlay dạng bullet points

### R6. Proactive Intelligence — JARVIS Chủ Động

JARVIS không chỉ phản ứng mà còn chủ động:
- **Smart reminders**: "JARVIS, nhắc tôi lúc 3 giờ chiều họp với team" → overlay + TTS alert đúng giờ
- **System health monitor**: Chủ động cảnh báo khi CPU > 90%, RAM > 85%, disk < 10GB, nhiệt độ > 85°C
- **Focus mode**: "JARVIS, tôi cần tập trung 2 tiếng" → block notifications, set timer, nhắc nghỉ 5 phút sau 25 phút
- **Daily briefing auto**: Mỗi sáng 8h (cấu hình được), tự động đọc briefing
- **Battery alert**: Nhắc sạc khi pin < 20%
- **Inactivity greeting**: Nếu không tương tác > 2 tiếng, JARVIS hỏi "Thưa Ngài, Ngài có cần hỗ trợ gì không?"
- Tất cả proactive behaviors có thể tắt/bật riêng lẻ qua config

### R7. Natural Language Shell — JARVIS Thực Thi Lệnh

JARVIS hiểu lệnh tự nhiên và chuyển thành hành động:
- "JARVIS, chạy server" → tự tìm `npm start` hoặc `python manage.py runserver` trong project folder
- "JARVIS, git status project JARVIS" → chạy git command và đọc tóm tắt
- "JARVIS, cài đặt package X" → `pip install X` hoặc `npm install X` tùy context
- "JARVIS, restart Docker" → chạy lệnh tương ứng
- "JARVIS, kiểm tra port 8080" → netstat + trả lời
- Safety gate: Lệnh có `rm`, `format`, `delete`, `drop` yêu cầu confirm bằng giọng nói trước khi chạy
- Kết quả command được tóm tắt và đọc to (không đọc toàn bộ stdout dài)

### R8. Always-On Intelligent Overlay

Nâng cấp overlay từ popup đơn giản thành giao diện thực sự:
- **Sidebar mode**: Option để overlay luôn hiển thị bên phải màn hình (collapsible)
- **Conversation history**: Hiển thị 5 turns gần nhất của cuộc hội thoại
- **Quick actions**: Buttons cho các action hay dùng (briefing, system status, focus mode)
- **Memory preview**: Hiển thị ngắn gọn 3 facts JARVIS nhớ về user
- **Status bar**: CPU/RAM/Battery realtime (cập nhật mỗi 5s)
- **Voice waveform**: Animation thực tế khi đang nghe/nói
- Có thể minimize về icon nhỏ ở góc màn hình

### R9. Regression & Integration Tests

Sau tất cả thay đổi:
- Tất cả 537+ tests cũ phải tiếp tục pass
- Thêm ≥ 20 tests mới cho R1-R8
- `python -m jarvis health-check` phải report tất cả new systems
- `python -m jarvis run` phải khởi động không lỗi với tất cả hệ thống mới

---

## Acceptance Criteria

### Wake Word (R1)
- [ ] "Hey JARVIS" được detect trong < 1s (offline, không cần internet)
- [ ] False positive rate < 1 lần/giờ trong môi trường bình thường
- [ ] Wake word + double clap cùng hoạt động song song
- [ ] Tắt/bật wake word qua tray menu không cần restart

### Memory (R2)
- [ ] "JARVIS, nhớ rằng tôi tên Hưng" → lần sau nhớ và dùng tên
- [ ] Session context: câu hỏi follow-up hiểu được ngữ cảnh câu trước
- [ ] `logs/memory.db` SQLite file tồn tại sau restart
- [ ] "JARVIS, hôm nay tôi đã làm gì?" → tóm tắt đúng interactions trong ngày

### Screen Vision (R3)
- [ ] "JARVIS, màn hình tôi đang hiện gì?" → mô tả chính xác qua Vision LLM
- [ ] "JARVIS, lỗi này nghĩa là gì?" (với error dialog trên màn hình) → giải thích
- [ ] Screenshot được capture và analyze < 3s
- [ ] Hoạt động khi không có Vision LLM key (fallback: "Tôi chưa thể nhìn thấy màn hình")

### Computer Control (R4)
- [ ] "JARVIS, tăng âm lượng" → volume tăng 10%
- [ ] "JARVIS, chụp màn hình" → screenshot lưu vào Desktop
- [ ] "JARVIS, minimize tất cả" → ShowDesktop
- [ ] High-risk actions yêu cầu confirm voice trước khi thực thi

### Web Intelligence (R5)
- [ ] "JARVIS, thời tiết Hà Nội hôm nay?" → trả lời chính xác (cần internet)
- [ ] "JARVIS, briefing sáng nay" → đọc to weather + top 3 news + BTC price
- [ ] Graceful degradation khi offline: "Xin lỗi Ngài, tôi không có kết nối mạng"
- [ ] Tất cả web results được cache 10 phút (không spam API)

### Proactive (R6)
- [ ] "JARVIS, nhắc tôi sau 5 phút" → TTS + overlay alert đúng 5 phút sau
- [ ] CPU > 90% → JARVIS tự cảnh báo bằng giọng nói trong < 30s
- [ ] Focus mode timer: nhắc nghỉ sau 25 phút (Pomodoro)
- [ ] Proactive behaviors tắt/bật được từng cái trong config

### Natural Language Shell (R7)
- [ ] "JARVIS, kiểm tra port đang chạy" → đọc kết quả netstat tóm tắt
- [ ] "JARVIS, git status" → tóm tắt bằng tiếng Việt ("Có 3 files chưa commit")
- [ ] Lệnh nguy hiểm (rm, delete) yêu cầu confirm
- [ ] Command output > 10 dòng được tóm tắt, không đọc hết

### Overlay (R8)
- [ ] Sidebar mode luôn hiển thị, có thể collapse về 40px
- [ ] Conversation history 5 turns hiển thị đúng
- [ ] CPU/RAM cập nhật realtime trên status bar
- [ ] Có thể kéo thả sidebar đến vị trí bất kỳ

### Tests & Regression (R9)
- [ ] Tổng tests ≥ 557 (537 + 20 mới)
- [ ] `pytest tests/ -x -q` pass 100%
- [ ] `python -m jarvis health-check` xanh tất cả subsystems mới

---

## Verification Protocol

1. **Explorers**: Map toàn bộ gaps, design architecture cho R1-R8
2. **Workers** (8 streams song song nếu có thể): Implement từng R
3. **Integration Worker**: Wire tất cả R vào `app.py` và config
4. **Reviewers + Challengers**: Test adversarially từng feature
5. **Victory Auditor**: Independent pytest full suite + health-check

Victory condition: 557+ tests pass, health-check all green, tất cả acceptance criteria verified.
