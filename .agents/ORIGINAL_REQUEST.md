# Original User Request

## 2026-08-24T02:31:19Z

JARVIS hiện tại đã có nền tảng vững chắc với 92 modules, 921+ tests passing bao gồm Wake Word, Persistent Memory, Screen Vision, Computer Control, Web Intelligence, Proactive Watchdog và Always-On HUD. Mục tiêu của lần nâng cấp này là **khai phá toàn bộ tiềm năng tự trị (Autonomous Agentic Superpower)**, biến JARVIS thành một AI có khả năng tự suy luận đa bước, tự viết code giải quyết bài toán mới trong sandbox, tự động hóa trình duyệt web chuyên sâu, điều khiển mọi ứng dụng Desktop qua thị giác máy tính và phân bổ đội ngũ sub-agents chạy ngầm để thực hiện bất kỳ yêu cầu phức tạp nào của người dùng.

Working directory: d:/Software GitCode/JARVIS
Integrity mode: development

---

## Requirements

### R1. Autonomous ReAct Planner & Multi-Step Task Engine (Lập Kế Hoạch & Tự Trị Đa Bước)
Xây dựng engine ReAct (Reasoning + Acting) chuyên sâu cho phép JARVIS tiếp nhận các mệnh lệnh phức tạp, trừu tượng từ người dùng:
- Tự động phân tách yêu cầu lớn thành Đồ thị Nhiệm vụ (Task Graph / DAG) gồm các bước hành động cụ thể.
- Vòng lặp Tự Đánh Giá (Self-Reflection) và Tự Khắc Phục Lỗi (Self-Healing): Khi một bước thất bại, JARVIS tự phân tích nguyên nhân lỗi, đổi chiến lược và thử lại cho đến khi hoàn thành.
- Chế độ kép: **Fully Autonomous** (tự chạy tự quyết định) kết hợp **Safety Gate** (xin ý kiến người dùng trước các hành động phá hủy hoặc giao dịch tài chính).

### R2. Dynamic Skill Synthesis & Sandboxed Self-Coding (Tự Viết Code & Tự Chế Tạo Công Cụ)
Trang bị cho JARVIS khả năng tự tạo công cụ theo thời gian thực:
- **Code Interpreter Sandbox**: Khi người dùng yêu cầu tác vụ chưa có module sẵn (ví dụ: "gộp 5 file Excel, tính tổng doanh thu và vẽ biểu đồ", "đổi tên 100 ảnh theo ngày chụp", "chuyển file PDF sang Word"), JARVIS tự động sinh mã nguồn Python/PowerShell an toàn, thực thi trong sandbox và trả về kết quả/file đầu ra.
- **Persistent Skill Library (`jarvis/skills/`)**: Khi một công cụ tự viết chạy thành công, JARVIS tự động lưu trữ, lập chỉ mục và đóng gói nó thành một Kỹ năng (Skill) tái sử dụng vĩnh viễn trong các phiên sau.

### R3. Full Browser Automation Agent (Tự Động Hóa Trình Duyệt Web Chuyên Sâu)
Tích hợp động cơ Browser Agent (Playwright / Chromium DevTools Protocol):
- Tự động mở trình duyệt, điều hướng, tìm kiếm thông tin chuyên sâu, trích xuất dữ liệu (Web Scraping) từ các trang web phức tạp (SPAs, JavaScript động).
- Tự động điền biểu mẫu, tải tệp tin, so sánh giá sản phẩm trên nhiều trang thương mại điện tử, tổng hợp tin tức và lưu thành tài liệu báo cáo.
- Quản lý phiên làm việc thông minh và hỗ trợ tương tác trang web không phụ thuộc vào layout tĩnh.

### R4. Computer-Use Vision & Desktop GUI Interaction (Thao Tác Mọi Ứng Dụng Desktop Qua Thị Giác)
Nâng cấp khả năng điều khiển máy tính lên cấp độ thị giác AI (Vision-driven Computer Use):
- Chụp ảnh màn hình, phân tích tọa độ bounding box của các nút bấm, ô văn bản, thanh menu trong bất kỳ phần mềm nào (Office, Photoshop, IDE, File Explorer, công cụ chuyên ngành).
- Thực hiện click chuột, kéo thả, gõ bàn phím chuẩn xác vào phần tử UI mục tiêu.
- Vòng lặp Visual Verification: Chụp lại màn hình sau mỗi thao tác để xác nhận trạng thái giao diện đã thay đổi đúng như kỳ vọng trước khi chuyển sang bước tiếp theo.

### R5. Autonomous Background Workers & Task Delegation (Đội Ngũ Sub-Agent Chạy Ngầm)
Xây dựng cơ chế phân luồng Sub-Agent cho các nhiệm vụ dài hạn:
- Khởi tạo các Background Worker độc lập cho các tác vụ tốn thời gian (ví dụ: giám sát biến động giá, quét an ninh mạng, xử lý batch dữ liệu nặng) mà không làm nghẽn giao diện chính.
- Báo cáo tiến độ thời gian thực về HUD Overlay và gửi thông báo tổng kết (kèm file xuất bản) qua giọng nói hoặc Telegram khi hoàn thành.

### R6. Unified Multi-Modal Integration & HUD Telemetry (Đồng Bộ Đa Phương Thức)
Tích hợp toàn diện các năng lực mới vào hệ thống cốt lõi:
- **Voice & Wake Word**: Ra lệnh tự nhiên bằng tiếng Việt thông qua "Hey JARVIS".
- **HUD Sidebar Overlay**: Hiển thị cây nhiệm vụ (Task DAG), thanh tiến trình từng bước, log code đang chạy và kết quả trực quan.
- **Memory Layer**: Tự động lưu vết tất cả các tác vụ đã thực hiện vào SQLite memory để tra cứu và học hỏi thói quen.

### R7. Comprehensive Regression & Integration Test Suite
- Đảm bảo toàn bộ 921+ bài kiểm thử hiện có tiếp tục vượt qua 100% (zero regressions).
- Bổ sung tối thiểu 30 bài kiểm thử mới bao phủ toàn diện: ReAct Planner, Code Interpreter, Skill Synthesis, Browser Automation, Computer-Use coordinate mapping và Sub-agent worker lifecycle.
- Kiểm tra chẩn đoán hệ thống (`python -m jarvis health-check`) báo cáo tất cả các phân hệ mới đều đạt trạng thái READY/OK.

---

## Acceptance Criteria

### Autonomous Planner & Self-Healing (R1)
- [ ] Mệnh lệnh phức tạp 3+ bước được phân tách thành Task Graph hợp lệ và thực thi tuần tự/song song thành công.
- [ ] Khi gặp lỗi thực thi ở một bước, engine tự động retry/đổi phương án và hoàn thành mục tiêu.
- [ ] Safety Gate chặn lại và yêu cầu xác nhận đối với các thao tác rủi ro cao.

### Self-Coding & Skill Library (R2)
- [ ] Tác vụ xử lý dữ liệu (CSV/Excel/File) được giải quyết thành công qua Code Interpreter tự sinh mã.
- [ ] Công cụ mới được tự động đóng gói và lưu vào `jarvis/skills/`, có thể gọi lại thành công ở lần kế tiếp.

### Browser Automation (R3)
- [ ] Browser Agent tự động mở web, tìm kiếm, trích xuất dữ liệu từ trang web động và tổng hợp thành kết quả.
- [ ] Hỗ trợ tải file và xử lý form tự động không bị treo.

### Computer-Use Vision (R4)
- [ ] Nhận diện đúng tọa độ phần tử UI trên màn hình từ hình ảnh chụp và thực hiện click/gõ phím chính xác.
- [ ] Visual verification kiểm tra thành công trạng thái thay đổi sau hành động.

### Background Sub-Agents & HUD (R5, R6)
- [ ] Sub-agent chạy ngầm hoàn thành tác vụ độc lập và báo cáo kết quả về HUD Overlay/Voice.
- [ ] HUD Overlay hiển thị trực quan Task DAG và tiến độ thời gian thực.

### Regression & Verification (R7)
- [ ] Tổng số tests đạt ≥ 951 tests (921 baseline + ≥ 30 tests mới), tỷ lệ đạt 100%.
- [ ] `python -m jarvis health-check` thoát với mã 0, tất cả các phân hệ mới đều OK.
