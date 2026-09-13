# Giao Thức Nghiệm Thu Giọng Nói Thực Tế (50 Live Voice Acceptance Cases)
**Dự Án**: JARVIS Voice Assistant — Beta v1  
**Mục Tiêu**: Kiểm thử trực tiếp bằng con người thật, giọng nói thật, micro thật (Tier 1 Evidence)  
**Tài Liệu Tham Chiếu Gốc**: Backlog H-13 (`ORIGINAL_REQUEST.md` & `ROADMAP.md`)  
**Tiêu Chuẩn Đạt**: >= 95% (tối thiểu 48/50 ca) task-level success trên 10 core workflow trong điều kiện phòng yên  
**Trạng Thái Nghiệm Thu Hiện Tại**: ⏳ **CHƯA ĐÓNG (PENDING_HUMAN_EXECUTION)**  

---

> [!WARNING]
> **CẢNH BÁO KIỂM TOÁN CHỐNG TRÁO ĐỔI BẰNG CHỨNG (ANTI-EVIDENCE SUBSTITUTION)**:
> Bộ kiểm thử tự động E2E (`tests/e2e/test_beta_v1_acceptance.py`: 28/28 tests, runtime 1.65s) **CHỈ LÀ TIÊU CHUẨN TIER 2 (AUTOMATED MOCK INTEGRATION)** để bảo vệ tính toàn vẹn của mã nguồn.
> Bộ kiểm thử tự động đó **TUYỆT ĐỐI KHÔNG THỂ THAY THẾ CHO H-13**. H-13 đòi hỏi con người thật ngồi trước máy tính, nói qua micro thật và quan sát hành vi thực tế của hệ thống. Không được phép đóng dấu DONE cho H-13 khi chưa có biên bản thực nghiệm của 50 ca này.

---

## 1. Quy Trình & Điều Kiện Môi Trường Kiểm Thử
1. **Người thử nghiệm (Human Tester)**: 1 người nói tiếng Việt tự nhiên, phát âm rõ ràng, không cố tình nói ngắt quãng hoặc giả giọng AI.
2. **Thiết bị thu âm**: Microphone vật lý thật của máy tính (Built-in mic hoặc USB mic cắm ngoài).
3. **Môi trường âm học**: Phòng yên tĩnh tiêu chuẩn văn phòng/gia đình (<45 dBA, không bật TV/nhạc to gần mic).
4. **Khoảng cách**: Người nói ngồi thẳng trước màn hình, cách micro từ 50 cm đến 80 cm.
5. **Cách thức kích hoạt**: Sử dụng wake word ("JARVIS ơi" / "Trợ lý ơi") hoặc phím tắt PTT `Ctrl+Shift+L`. Chờ chuông phản hồi hoặc đèn overlay xanh sáng lên mới bắt đầu đọc câu lệnh.
6. **Tiêu chí Đạt (Pass)**:
   - Whisper STT nhận diện đúng nội dung (không sai lệch từ khóa chính).
   - Intent Router định tuyến đúng action mục tiêu.
   - Hành động trên hệ điều hành Windows được thực thi chính xác.
   - JARVIS phản hồi âm thanh hoặc giọng nói TTS xác nhận.

---

## 2. Danh Mục 50 Ca Thử Nghiệm (10 Core Workflows × 5 Ca)

| STT | Workflow Mục Tiêu | Khẩu Lệnh Đọc Thực Tế (Nói Miệng) | Biến Thể Khẩu Ngữ Tự Nhiên | Expected Action | Expected System Response | Kết Quả Thực Tế (Pass/Fail) | STT Transcribed Text | Ghi Chú / Lỗi |
|:---:|:---|:---|:---|:---|:---|:---:|:---|:---|
| **WF-01: Khởi Chạy Ứng Dụng (App Launch)** |
| 1 | WF01-1 | "Mở Notepad lên cho tôi" | "Bật trình ghi chú Notepad đi" | `open_app(notepad)` | Mở cửa sổ Notepad trên màn hình | [ ] P / [ ] F | | |
| 2 | WF01-2 | "Mở máy tính tính tiền" | "Bật Calculator lên nhé" | `open_app(calculator)` | Mở Windows Calculator | [ ] P / [ ] F | | |
| 3 | WF01-3 | "Mở File Explorer ra" | "Vào ổ đĩa tệp tin" | `open_app(explorer)` | Mở cửa sổ File Explorer | [ ] P / [ ] F | | |
| 4 | WF01-4 | "Khởi động ứng dụng Spotify" | "Bật phần mềm nghe nhạc Spotify" | `open_app(spotify)` | Khởi chạy tiến trình Spotify | [ ] P / [ ] F | | |
| 5 | WF01-5 | "Mở Task Manager xem hiệu năng" | "Bật trình quản lý tác vụ lên" | `open_app(taskmgr)` | Mở cửa sổ Task Manager | [ ] P / [ ] F | | |
| **WF-02: Điều Hướng Trình Duyệt Web (Web Open)** |
| 6 | WF02-1 | "Mở trang Google" | "Vào Google tìm kiếm" | `web_open(google.com)` | Mở tab Google trên trình duyệt | [ ] P / [ ] F | | |
| 7 | WF02-2 | "Mở kênh YouTube lên" | "Vào xem YouTube đi" | `web_open(youtube.com)` | Mở trang YouTube | [ ] P / [ ] F | | |
| 8 | WF02-3 | "Truy cập vào trang GitHub" | "Mở kho mã nguồn GitHub" | `web_open(github.com)` | Mở trang GitHub | [ ] P / [ ] F | | |
| 9 | WF02-4 | "Mở báo Dân Trí đọc tin tức" | "Vào xem trang báo dantri.com.vn" | `web_open(dantri.com.vn)` | Mở trang báo điện tử Dân Trí | [ ] P / [ ] F | | |
| 10 | WF02-5 | "Mở trang ChatGPT" | "Vào chat.openai.com" | `web_open(chatgpt.com)` | Mở tab ChatGPT | [ ] P / [ ] F | | |
| **WF-03: Điều Khiển Âm Lượng & Màn Hình (Hardware Volume & Display)** |
| 11 | WF03-1 | "Tăng âm lượng lên mười phần trăm" | "Cho loa to lên một chút" | `volume_control(delta=+10)` | Master volume tăng +10 | [ ] P / [ ] F | | |
| 12 | WF03-2 | "Giảm âm lượng xuống" | "Vặn nhỏ loa lại" | `volume_control(delta=-10)` | Master volume giảm -10 | [ ] P / [ ] F | | |
| 13 | WF03-3 | "Tắt tiếng loa đi" | "Mute âm thanh máy tính" | `volume_control(level=0)` | Master volume về 0 (Mute) | [ ] P / [ ] F | | |
| 14 | WF03-4 | "Đặt âm lượng ở mức năm mươi phần trăm" | "Chỉnh loa về mức 50" | `volume_control(level=50)` | Master volume đặt chính xác 50% | [ ] P / [ ] F | | |
| 15 | WF03-5 | "Tăng độ sáng màn hình lên" | "Cho màn hình sáng thêm chút" | `brightness_control(delta=+15)` | Độ sáng màn hình tăng +15 | [ ] P / [ ] F | | |
| **WF-04: Phát & Dừng Phương Tiện Truyền Thông (Media Control)** |
| 16 | WF04-1 | "Bật một bài nhạc nhẹ không lời" | "Phát nhạc piano thư giãn" | `music_play(piano thư giãn)` | Phát nhạc qua Spotify/Media | [ ] P / [ ] F | | |
| 17 | WF04-2 | "Tạm dừng phát nhạc" | "Dừng bài hát đang phát lại" | `music_pause()` | Tạm dừng media hiện tại | [ ] P / [ ] F | | |
| 18 | WF04-3 | "Tiếp tục phát bài hát" | "Bật nhạc chạy tiếp đi" | `music_resume()` | Tiếp tục phát nhạc | [ ] P / [ ] F | | |
| 19 | WF04-4 | "Chuyển sang bài tiếp theo" | "Next qua bài hát khác" | `music_next()` | Chuyển bài kế tiếp | [ ] P / [ ] F | | |
| 20 | WF04-5 | "Quay lại bài vừa phát" | "Phát lại bài hát trước" | `music_prev()` | Quay lại bài trước đó | [ ] P / [ ] F | | |
| **WF-05: Đặt Giờ Hẹn & Đếm Ngược (Timer & Alarms)** |
| 21 | WF05-1 | "Hẹn giờ cho tôi năm phút nữa" | "Bấm giờ đếm ngược 5 phút" | `timer_set(duration=300)` | Đặt timer 5 phút | [ ] P / [ ] F | | |
| 22 | WF05-2 | "Đặt báo thức lúc bảy giờ sáng mai" | "Sáng mai gọi tôi dậy lúc 7 giờ" | `alarm_set(time="07:00")` | Tạo lịch báo thức 07:00 | [ ] P / [ ] F | | |
| 23 | WF05-3 | "Hủy hẹn giờ đang chạy" | "Xóa đồng hồ đếm ngược đi" | `timer_cancel()` | Hủy bộ đếm thời gian | [ ] P / [ ] F | | |
| 24 | WF05-4 | "Còn bao nhiêu thời gian nữa hết giờ" | "Kiểm tra xem đồng hồ còn mấy phút" | `timer_status()` | Thông báo thời gian còn lại | [ ] P / [ ] F | | |
| 25 | WF05-5 | "Đặt đồng hồ đếm ngược hai mươi phút" | "Bấm giờ 20 phút nướng bánh" | `timer_set(duration=1200)` | Đặt timer 20 phút | [ ] P / [ ] F | | |
| **WF-06: Ghi Chú & Nhắc Nhở Công Việc (Notes & Reminders)** |
| 26 | WF06-1 | "Ghi chú nhớ nộp báo cáo lúc mười bốn giờ" | "Lưu ghi chú kiểm tra tiến độ dự án" | `note_create(nộp báo cáo...)` | Lưu vào bộ nhớ SQLite/Vector | [ ] P / [ ] F | | |
| 27 | WF06-2 | "Nhắc tôi uống nước sau một tiếng nữa" | "Đặt nhắc nhở nghỉ giải lao" | `reminder_set(uống nước...)` | Tạo reminder tương ứng | [ ] P / [ ] F | | |
| 28 | WF06-3 | "Đọc lại các ghi chú hôm nay của tôi" | "Xem danh sách việc cần làm" | `note_list()` | TTS đọc danh sách ghi chú | [ ] P / [ ] F | | |
| 29 | WF06-4 | "Xóa ghi chú mua hàng hôm qua đi" | "Bỏ ghi chú cũ nhất" | `note_delete()` | Xóa bản ghi được chỉ định | [ ] P / [ ] F | | |
| 30 | WF06-5 | "Thêm vào việc cần làm gọi điện cho đối tác"| "Ghi lại công việc cần xử lý" | `todo_add(gọi điện...)` | Thêm vào todo list | [ ] P / [ ] F | | |
| **WF-07: Tra Cứu Thời Tiết & Môi Trường (Weather Query)** |
| 31 | WF07-1 | "Thời tiết hôm nay thế nào" | "Hôm nay trời có đẹp không" | `weather_query(today)` | Báo cáo nhiệt độ, mây, mưa | [ ] P / [ ] F | | |
| 32 | WF07-2 | "Ngày mai có mưa không" | "Xem dự báo thời tiết ngày mai" | `weather_query(tomorrow)` | Trả lời khả năng mưa ngày mai | [ ] P / [ ] F | | |
| 33 | WF07-3 | "Nhiệt độ hiện tại ở Hà Nội là bao nhiêu" | "Hà Nội bây giờ mấy độ" | `weather_query(hanoi)` | Báo nhiệt độ thực tế Hà Nội | [ ] P / [ ] F | | |
| 34 | WF07-4 | "Thời tiết Thành phố Hồ Chí Minh cuối tuần" | "Sài Gòn chủ nhật có nắng không" | `weather_query(hcm)` | Báo dự báo cuối tuần TP.HCM | [ ] P / [ ] F | | |
| 35 | WF07-5 | "Độ ẩm không khí bây giờ ra sao" | "Hôm nay trời có nồm ẩm không" | `weather_query(humidity)` | Báo độ ẩm không khí % | [ ] P / [ ] F | | |
| **WF-08: Điều Khiển Nhà Thông Minh (Smart Home)** |
| 36 | WF08-1 | "Bật đèn phòng khách lên" | "Cho sáng đèn khu vực tiếp khách" | `home_assistant(light.on)` | Gửi lệnh bật entity qua HA | [ ] P / [ ] F | | |
| 37 | WF08-2 | "Tắt đèn phòng ngủ" | "Tắt hết đèn trong phòng ngủ đi" | `home_assistant(light.off)` | Gửi lệnh tắt entity qua HA | [ ] P / [ ] F | | |
| 38 | WF08-3 | "Nhiệt độ phòng ngủ hiện tại là bao nhiêu" | "Xem cảm biến nhiệt độ phòng" | `home_assistant(sensor.temp)` | Đọc trạng thái sensor | [ ] P / [ ] F | | |
| 39 | WF08-4 | "Kéo rèm cửa sổ ra" | "Mở rèm ban công" | `home_assistant(cover.open)` | Điều khiển mở rèm cửa | [ ] P / [ ] F | | |
| 40 | WF08-5 | "Bật điều hòa hai mươi lăm độ" | "Chỉnh máy lạnh về 25 độ C" | `home_assistant(climate.set)`| Đặt nhiệt độ điều hòa | [ ] P / [ ] F | | |
| **WF-09: Thông Điệp & Điểm Tin Hệ Thống (Comms & Briefing)** |
| 41 | WF09-1 | "Tóm tắt điểm tin buổi sáng cho tôi" | "Có tin tức gì mới nổi bật không" | `morning_briefing()` | TTS đọc bản tin tổng hợp | [ ] P / [ ] F | | |
| 42 | WF09-2 | "Kiểm tra xem có tin nhắn Telegram mới không" | "Đọc thông báo từ Telegram" | `telegram_check()` | Báo tin nhắn hoặc NOT_CONFIGURED | [ ] P / [ ] F | | |
| 43 | WF09-3 | "Kiểm tra hòm thư email chưa đọc" | "Có email nào mới gửi đến không" | `email_check()` | Báo số email hoặc NOT_CONFIGURED | [ ] P / [ ] F | | |
| 44 | WF09-4 | "Báo cáo trạng thái hệ thống hiện tại" | "Hệ thống đang hoạt động ra sao" | `system_status()` | Báo CPU, RAM, pin, kết nối | [ ] P / [ ] F | | |
| 45 | WF09-5 | "Kiểm tra kết nối mạng Internet" | "Mạng wifi có ổn định không" | `network_check()` | Báo ping, tốc độ hoặc trạng thái | [ ] P / [ ] F | | |
| **WF-10: An Toàn Nguồn & Quản Trị Hệ Thống (System Power & Security)** |
| 46 | WF10-1 | "Khóa màn hình máy tính lại" | "Khóa máy đi làm việc khác" | `system_lock()` | Windows + L khóa màn hình | [ ] P / [ ] F | | |
| 47 | WF10-2 | "Cho máy tính vào chế độ ngủ" | "Sleep máy tính đi" | `system_sleep()` | Đưa máy tính vào Sleep | [ ] P / [ ] F | | |
| 48 | WF10-3 | "Hủy lệnh tắt máy tính" | "Đừng tắt máy nữa dừng lại" | `shutdown_abort()` | Hủy lệnh hẹn giờ tắt máy | [ ] P / [ ] F | | |
| 49 | WF10-4 | "Khởi động lại máy tính" | "Restart lại hệ thống" | `system_restart()` | Hỏi xác nhận an toàn (Confirmation)| [ ] P / [ ] F | | |
| 50 | WF10-5 | "Kiểm tra tình trạng pin của máy" | "Pin laptop còn bao nhiêu phần trăm"| `battery_status()` | Báo % pin và trạng thái sạc | [ ] P / [ ] F | | |

---

## 3. Biên Bản Ký Duyệt Nghiệm Thu
- **Tổng số ca thử nghiệm**: 50
- **Số ca thành công (Pass)**: `___ / 50`
- **Tỷ lệ thành công thực tế**: `___ %` (Ngưỡng đạt: >= 95%)
- **Người thực hiện kiểm thử (Tester)**: ___________________
- **Thiết bị microphone sử dụng**: ___________________
- **Ngày thực hiện**: _____ / _____ / 2026
- **Kết luận**: [ ] ĐẠT CHUẨN NGHIỆM THU LIVE / [ ] CHƯA ĐẠT (Cần tiếp tục tinh chỉnh)
