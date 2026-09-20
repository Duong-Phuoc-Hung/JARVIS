# Giao Thức Nghiệm Thu Thực Thi Hệ Điều Hành Thực Tế Qua Giọng Nói (10-Workflow Real Voice -> Real STT -> Real OS Execution Acceptance Protocol)

**Dự Án**: JARVIS Voice Assistant — v5.2.0<br>
**Tài Liệu Cấp**: Cổng Nghiệm Thu Chuyển Tầng (Phase Transition Acceptance Gate Protocol)<br>
**Mục Tiêu**: Đánh giá toàn diện chuỗi khép kín: Giọng nói thật (Real Voice) $\rightarrow$ Nhận dạng âm thanh thật (Real STT FasterWhisper `large-v3` CUDA) $\rightarrow$ Định tuyến ý định thật (Real Intent Router) $\rightarrow$ Tác động hệ điều hành thực tế (Real OS Execution).<br>
**Vị Trí Cổng**: Gate GO/NO-GO bắt buộc để thăng cấp hệ thống từ **Internal Beta Pilot (CONDITIONAL GO)** lên **Product Beta (Product Release GO)**.<br>
**Trạng Thái Cổng Hiện Tại**: ⏳ **ĐANG MỞ (OPEN — PENDING_REAL_EXECUTION)**<br>

---

> [!WARNING]
> ### CẢNH BÁO KIỂM TOÁN CHỐNG TRÁO ĐỔI BẰNG CHỨNG (ANTI-EVIDENCE SUBSTITUTION)
> 1. **R13 Dispatcher Benchmark KHÔNG Phải Là Bằng Chứng Thực Thi OS**:
>    Bộ benchmark 200/200 trials trong `tests/benchmarks/test_workflow_acceptance_benchmark.py` (Phase P3 / R13) chạy trên tầng `ActionDispatcher` với **100% phần cứng bị mock** (`stt_mock`, `app_open_mock`, `imap_mock`, `ha_client_mock`). Kết quả đó chỉ đạt **Tier 2 (PASS runtime dispatcher+mock)** nhằm xác nhận kiến trúc router và safety interceptor không crash.
> 2. **Tuyệt Đối Không Gộp Mock Vào Bảng Này**:
>    Bất kỳ dữ liệu nào thu thập từ file âm thanh tổng hợp giả lập, STT mock, hoặc process stub đều bị coi là **Active Fabrication** theo `docs/AUDIT_FRAMEWORK.md §Trục 2` và `AGENTS.md §2`.
> 3. **Cổng Real OS Chỉ Đóng Khi Có Bằng Chứng Tier 1**:
>    Cổng này đòi hỏi micro vật lý thu âm người nói thật, mô hình FasterWhisper `large-v3` GPU giải mã thật, và hệ điều hành Windows 11 thực thi sinh ra side-effect thực sự (Process PID sống, Window Handle, thay đổi âm lượng phần cứng, ghi đĩa dữ liệu, API network response).

---

## 1. Định Nghĩa Cổng Nghiệm Thu (Gate Definition) & Tiêu Chuẩn Phán Quyết

1. **Quy mô mẫu thử nghiệm ($N$)**:
   - Tối thiểu **20 trials** cho mỗi workflow đơn lẻ.
   - Tổng quy mô: **200 trials** trên 10 workflows cốt lõi.
2. **Ngưỡng Đạt (Pass Threshold)**:
   - Tỷ lệ thành công mỗi workflow: $\ge 95.0\%$ (tối thiểu **19/20 trials** đạt chuẩn).
   - Tỷ lệ thành công tổng thể 10 workflows: $\ge 95.0\%$ (tối thiểu **190/200 trials** đạt chuẩn).
3. **Điều Kiện Trượt Tuyệt Đối (Fail-Closed Veto Condition)**:
   - Nếu **BẤT KỲ** workflow nào có tỷ lệ thành công $< 90.0\%$ (tức $\le 17/20$ trials đạt), toàn bộ Gate bị tuyên bố **FAIL ngay lập tức**, kể cả khi điểm trung bình của 10 workflow cộng lại đạt $\ge 95\%$.
   - *Nguyên tắc*: Không cho phép việc thực thi hoàn hảo ở các tác vụ đơn giản (như lấy thời tiết hay chụp màn hình) bù trừ cho sự thất bại ở tác vụ điều khiển hệ thống cốt lõi (như mở ứng dụng hay chỉnh âm lượng).
4. **Quy Tắc Phán Quyết 3 Tầng**:
   - `GO (Product Beta Release Authorized)`: 10/10 workflows $\ge 95\%$, không workflow nào $< 90\%$, tổng $\ge 95\%$, 100% bằng chứng OS thật xác thực, audit checklist thông qua.
   - `CONDITIONAL GO (Internal Pilot Only)`: Trung bình $\ge 95\%$, có workflow đạt từ $90\%$ đến $94\%$, không có workflow nào $< 90\%$, cần lập ticket khắc phục trong sprint kế tiếp.
   - `NO-GO / GATE FAIL`: Bất kỳ workflow nào $< 90\%$, hoặc phát hiện bất kỳ dấu hiệu mock nào trong quá trình kiểm thử.

---

## 2. Điều Kiện Hợp Lệ Bắt Buộc & Kiểm Soát Thiên Vị (Anti-Bias Provisions)

Mọi phiên kiểm thử phải tuân thủ nghiêm ngặt 7 điều kiện kỹ thuật dưới đây:

1. **STT Engine Thật (Zero-Mock CUDA Inference)**:
   - Bắt buộc kích hoạt `FasterWhisperSTT` với model `large-v3`, thiết bị `cuda`, kiểu tính toán `float16`.
   - Nghiêm cấm sử dụng model `small`, model `base`, cloud fallback giả lập, hoặc tiêm chuỗi văn bản (text injection) vào pipeline.
2. **Thực Thi OS Thật & Bằng Chứng Khách Quan (Real OS Side-Effects)**:
   - Mọi hành vi phải được xác nhận bằng chứng khách quan trên hệ thống: Process ID (`PID`), Window Title Win32, mức âm lượng trước/sau qua `pycaw`, HTTP response JSON thực tế, File lưu trữ tồn tại trên đĩa.
   - Cấm chấp nhận các hàm trả về dictionary `{"success": True}` nếu không tạo ra thay đổi trạng thái tương ứng trên Windows.
3. **Phân Tách Dữ Liệu & Log Riêng Biệt (Isolated Workflow Logs)**:
   - Dữ liệu thô và log thực thi của mỗi workflow phải được ghi thành file/bảng riêng biệt trong thư mục `docs/eval/workflow_10_real_os_logs/`.
   - Tuyệt đối không gộp log của nhiều workflow thành một file duy nhất để tránh hiện tượng xóa nhòa lỗi biên.
4. **Kiểm Soát Điều Kiện Âm Học (Acoustic Noise Conditions)**:
   - Mỗi trial bắt buộc phải được gán nhãn điều kiện âm học tại thời điểm phát lệnh:
     * `QUIET`: Môi trường phòng yên tĩnh tiêu chuẩn (<45 dBA SPL, không có tạp âm phụ).
     * `AMBIENT`: Môi trường có tiếng ồn thực tế (55–65 dBA SPL: tiếng gõ phím cơ, tiếng quạt tản nhiệt, tiếng nói chuyện hoặc âm thanh phương tiện từ cửa sổ).
   - **Tỷ lệ AMBIENT bắt buộc**: Ít nhất **20% số trials** (tối thiểu **4/20 trials** mỗi workflow, và tối thiểu **40/200 trials** tổng thể) phải được thực hiện trong điều kiện `AMBIENT`.
5. **Chống Thiên Vị Người Nói (Speaker Independence & Anti-Overfitting)**:
   - Khuyến nghị sử dụng người thử nghiệm độc lập, **không phải** là kỹ sư đã trực tiếp thiết kế các biểu thức chính quy (regex rules) hoặc từ khóa định tuyến của `LLMIntentRouter`.
   - Trong trường hợp bất khả kháng chỉ có 1 người thử nghiệm, người nói bắt buộc phải sử dụng các biến thể khẩu ngữ tự nhiên mới (Held-out paraphrasing) chưa từng có trong bộ unit test hoặc file huấn luyện trước đây.
6. **Khoảng Cách & Thiết Bị Thu Âm Chuẩn**:
   - Sử dụng microphone vật lý thực tế của hệ thống (Microphone Array tích hợp trên laptop hoặc USB Mic cắm ngoài).
   - Khoảng cách người nói đến micro: duy trì ổn định từ 50 cm đến 75 cm.
7. **Tiền Kiểm Tra AUDIT_FRAMEWORK Trước Khi Nộp Báo Cáo**:
   - Trước khi nộp và ký duyệt kết quả, người kiểm thử phải rà soát qua 19 cạm bẫy kiểm toán tại `docs/AUDIT_FRAMEWORK.md`.

---

## 3. Đặc Tả Chi Tiết 10 Workflows Cốt Lõi (Specification Matrix)

| ID | Tên Workflow | Trigger Phrase Mẫu (Nói Miệng Tiếng Việt) | Action Target & Seam Phụ Trách | Định Dạng Bằng Chứng Bắt Buộc (Evidence Format) | Tiêu Chuẩn Đạt (Pass Condition) |
|:---:|:---|:---|:---|:---|:---|
| **WF-01** | Mở ứng dụng (App Launch) | "Mở Chrome lên", "Khởi động Notepad", "Bật Spotify" | `open_app` / `app_open` $\rightarrow$ `ComputerController.open_app()` via `subprocess.Popen` | Log Process PID thật, tên tiến trình đang chạy xác nhận qua `psutil.Process(pid).is_running()` | Tiến trình được tạo với PID hợp lệ (>0), tiến trình tồn tại trong danh sách tác vụ Windows trong vòng 2.0s, không bị chặn bởi rate-limit. |
| **WF-02** | Cài đặt hệ thống (Windows Settings) | "Mở cài đặt", "Vào settings hệ thống", "Mở cửa sổ cài đặt" | `open_app("cài đặt")` $\rightarrow$ `ms-settings:` URI via `os.startfile` | Log xác nhận Window Title "Settings" hoặc "Cài đặt" qua Win32 `GetWindowText` hoặc PID của `SystemSettings.exe` | Cửa sổ Windows Settings hiển thị trên màn hình trong vòng 3.0s, tiêu đề cửa sổ được định danh chính xác. |
| **WF-03** | Tìm kiếm web (Web Search) | "Tìm kiếm thời tiết Hà Nội", "Tìm kiếm thông tin Python 3.13", "Tra cứu giá vàng" | `web_open` / `web_search` $\rightarrow$ `ComputerController.open_website()` | Log chuỗi URL điều hướng đầy đủ có chứa query mã hóa URL (ví dụ: `https://www.google.com/search?q=...`) | Trình duyệt mặc định được gọi với đúng tham số tìm kiếm, URL hợp lệ, trả về `success=True`. |
| **WF-04** | Điều khiển media (Media Control) | "Bật nhạc", "Tiếp tục phát bài hát", "Tạm dừng phát nhạc" | `spotify_play` / `music_play` / Media keys $\rightarrow$ `SpotifyPlugin` & Windows Media API | Log trạng thái phát nhạc (`playback_state: PLAYING/PAUSED`) từ Spotify API hoặc log gửi phím ảo `VK_MEDIA_PLAY_PAUSE` | Trạng thái media của máy tính chuyển đổi đúng theo yêu cầu (từ dừng sang phát hoặc ngược lại). |
| **WF-05** | Điều chỉnh âm lượng (Volume Control) | "Tăng âm lượng", "Giảm âm lượng xuống", "Đặt âm lượng năm mươi phần trăm" | `system_volume` $\rightarrow$ `ComputerController.change_volume()` / `set_volume()` via `pycaw` | Log giá trị âm lượng thực tế của Endpoint trước và sau khi gọi: `level_before`, `delta`, `level_after` | Mức âm lượng Master thay đổi đúng với độ biến thiên yêu cầu (dung sai $\le \pm 2\%$), không gặp lỗi `VOLUME_SET_FAILED`. |
| **WF-06** | Tra cứu thời tiết (Weather API) | "Thời tiết hôm nay thế nào", "Thời tiết tại Đà Nẵng", "Hôm nay trời có mưa không" | `weather_query` $\rightarrow$ `WeatherClient.get_weather()` via REST API | Đoạn trích JSON response thô (HTTP 200, `temp_c`, `humidity`, `condition_text`), cache status (`hit/miss`) | Nhận được dữ liệu thời tiết hợp lệ từ OpenWeatherMap hoặc wttr.in fallback trong $\le 2.5s$, TTS phát ra câu trả lời có số đo nhiệt độ thực tế. |
| **WF-07** | Hẹn giờ đếm ngược (Timer Registration) | "Đặt hẹn giờ năm phút", "Hẹn giờ ba phút nấu mì", "Bấm giờ mười phút" | `timer_set` / `proactive_reminder` $\rightarrow$ `ProactiveEngine.register_timer()` | Log UUID định danh bộ hẹn giờ (`timer_id`), thời lượng đếm ngược (`duration_seconds=300`), thời điểm kích hoạt dự kiến (`target_timestamp`) | Bộ hẹn giờ được đưa vào hàng đợi đang hoạt động, trả về mã xác nhận hợp lệ, chuông báo thức kích hoạt đúng khi hết giờ. |
| **WF-08** | Đặt nhắc nhở (Reminder Schedule) | "Nhắc tôi lúc ba giờ chiều", "Nhắc tôi uống nước sau một tiếng", "Nhắc tôi nộp báo cáo lúc 17 giờ" | `reminder_set` / `proactive_reminder` $\rightarrow$ `ProactiveEngine.add_reminder()` | Log bản ghi nhắc nhở trong SQLite database/queue với `reminder_id`, nội dung thông điệp, thời gian báo hẹn chuẩn ISO-8601 | Bản ghi được ghi thành công vào bộ nhớ lưu trữ, hệ thống phát thông điệp xác nhận đã lên lịch nhắc. |
| **WF-09** | Lưu ghi chú (Note Taking) | "Ghi chú nhớ mua sách mới", "Lưu ghi chú kiểm tra server", "Tạo ghi chú gọi cho khách hàng" | `note_create` / `note_taking` $\rightarrow$ `jarvis.skills.note_taker.execute(action='add')` | Log ghi nhận file đĩa (`notes.json` hoặc SQLite DB), bao gồm `note_id`, timestamp, độ dài chuỗi ký tự đã lưu | Dữ liệu ghi chú được đọc ngược lại từ file đĩa (round-trip read verification) khớp 100% với nội dung khẩu lệnh. |
| **WF-10** | Chụp màn hình (Screen Capture) | "Chụp màn hình", "Chụp ảnh màn hình máy tính", "Lưu ảnh màn hình hiện tại" | `screen_capture` $\rightarrow$ `ScreenCaptureManager.capture()` via `mss` / Win32 GDI | Đường dẫn tuyệt đối tới file ảnh chụp trên đĩa, kích thước file tính bằng byte (`file_size > 10,000 bytes`), định dạng file (`.jpg` hoặc `.png`) | File ảnh được tạo thành công trên ổ cứng, định dạng ảnh hợp lệ (header JPEG/PNG đúng chuẩn), thời gian chụp $< 150ms$. |

---

## 4. Biểu Mẫu Ghi Nhận Kết Quả Từng Workflow (Per-Workflow Trial Table Template)

Người thử nghiệm phải sử dụng biểu mẫu chuẩn dưới đây cho từng workflow (tạo đủ 10 bảng riêng biệt tương ứng với WF-01 đến WF-10):

### Bảng Kết Quả Chi Tiết: WF-[XX] — [Tên Workflow]
*Mô hình STT: FasterWhisper `large-v3` CUDA | Thiết bị thu âm: [Tên Micro] | Người nói: [Họ Tên]*

| Trial # | Trigger Khẩu Lệnh Nói Thực Tế | STT Transcribed Output | Action Đã Gọi | Bằng Chứng OS Thực Tế (Evidence Log) | Kết Quả (PASS / FAIL) | Điều Kiện Âm Học (QUIET / AMBIENT) | Độ Trễ E2E (ms) | Ghi Chú / Mã Lỗi |
|:---:|:---|:---|:---|:---|:---:|:---:|:---:|:---|
| 01 | | | | | [ ] P / [ ] F | QUIET | | |
| 02 | | | | | [ ] P / [ ] F | QUIET | | |
| 03 | | | | | [ ] P / [ ] F | QUIET | | |
| 04 | | | | | [ ] P / [ ] F | QUIET | | |
| 05 | | | | | [ ] P / [ ] F | QUIET | | |
| 06 | | | | | [ ] P / [ ] F | QUIET | | |
| 07 | | | | | [ ] P / [ ] F | QUIET | | |
| 08 | | | | | [ ] P / [ ] F | QUIET | | |
| 09 | | | | | [ ] P / [ ] F | QUIET | | |
| 10 | | | | | [ ] P / [ ] F | QUIET | | |
| 11 | | | | | [ ] P / [ ] F | QUIET | | |
| 12 | | | | | [ ] P / [ ] F | QUIET | | |
| 13 | | | | | [ ] P / [ ] F | QUIET | | |
| 14 | | | | | [ ] P / [ ] F | QUIET | | |
| 15 | | | | | [ ] P / [ ] F | QUIET | | |
| 16 | | | | | [ ] P / [ ] F | QUIET | | |
| 17 | | | | | [ ] P / [ ] F | AMBIENT | | |
| 18 | | | | | [ ] P / [ ] F | AMBIENT | | |
| 19 | | | | | [ ] P / [ ] F | AMBIENT | | |
| 20 | | | | | [ ] P / [ ] F | AMBIENT | | |

*Quy định số lượng âm học tối thiểu: Ít nhất 4 trials (từ Trial 17 đến 20) bắt buộc thực hiện trong môi trường AMBIENT.*

---

## 5. Bảng Tổng Hợp Kết Quả Toàn Diện (Acceptance Summary Table)

Bảng này được lập sau khi hoàn thành đo đạc toàn bộ 200 trials trên 10 workflows:

| Mã WF | Tên Workflow Cốt Lõi | Tổng Số Trials ($N$) | Số Lượng PASS | Số Lượng FAIL | Tỷ Lệ Đạt Tổng (%) | Tỷ Lệ Đạt AMBIENT (%) | Độ Trễ P50 (ms) | Độ Trễ P95 (ms) | Trạng Thái Cổng (PASS $\ge 95\%$ / FAIL $< 90\%$) |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **WF-01** | Mở ứng dụng (App Launch) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **WF-02** | Cài đặt hệ thống (Settings App) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **WF-03** | Tìm kiếm web (Web Search URL) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **WF-04** | Điều khiển media (Media Playback) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **WF-05** | Âm lượng (pycaw Volume Control) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **WF-06** | Thời tiết (Live Weather API) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **WF-07** | Hẹn giờ (Timer Registration) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **WF-08** | Nhắc nhở (Reminder Schedule) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **WF-09** | Ghi chú (Note Persistence) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **WF-10** | Chụp màn hình (Screen Capture) | 20 | | | % | % | ms | ms | [ ] PASS / [ ] FAIL |
| **TỔNG** | **Toàn Bộ 10 Workflows** | **200** | | | **%** | **%** | **ms** | **ms** | **[ ] ĐẠT CỔNG / [ ] TRƯỢT** |

---

## 6. Danh Mục Kiểm Tra Bắt Buộc Trước Khi Ký Duyệt & Submit (Pre-Submission Audit Checklist)

Tuân thủ nghiêm ngặt chuẩn mực `docs/AUDIT_FRAMEWORK.md` và `AGENTS.md §2`:

- [ ] **Quy mô mẫu thử $N$**: Đã ghi nhận chính xác 20 trials cho mỗi workflow, không thiếu trial nào, tổng cộng 200 trials.
- [ ] **Log độc lập**: Mỗi workflow có bảng ghi dữ liệu chi tiết riêng biệt, không gộp chung dữ liệu giữa các workflow.
- [ ] **Điều kiện âm học rõ ràng**: Từng trial đều có đánh dấu `QUIET` hoặc `AMBIENT`; tổng số trial trong điều kiện `AMBIENT` đạt tối thiểu $\ge 20\%$ (ít nhất 4 trials/workflow và $\ge 40$ trials toàn bộ).
- [ ] **FasterWhisper thật**: Khẳng định 100% nhận dạng giọng nói chạy qua FasterWhisper `large-v3` trên GPU CUDA, không có bất kỳ mock transcript hoặc text injection nào.
- [ ] **Bằng chứng OS xác thực**: Mọi kết quả PASS đều có bằng chứng vật lý đi kèm (PID, Window Title, URL, Before/After Scalar, HTTP Response JSON, Disk File Path).
- [ ] **Trung thực Fail-closed**: Không có hành động nào tự động gán nhãn `PASS` khi hệ điều hành trả về mã lỗi hoặc khi ứng dụng không khởi chạy.
- [ ] **Công bố lỗi minh bạch**: Bất kỳ ca thất bại (FAIL) hoặc lỗi biên nào phát hiện được đều phải được ghi nhận chi tiết ở phần đầu của biên bản tổng hợp, không được giấu trong chú thích phụ.
- [ ] **Người thử nghiệm khách quan**: Ghi rõ họ tên người phát ngôn và xác nhận người nói không sử dụng lại bộ từ khóa trùng khít 100% với regex nội bộ mà đã áp dụng cách nói tự nhiên.

---

## 7. Biên Bản Ký Duyệt Nghiệm Thu (Gate Authorization Sign-off)

- **Tổng số trials thực hiện**: `200 / 200`
- **Số trials thành công (PASS)**: `___ / 200`
- **Tỷ lệ thành công chung**: `___ %` (Ngưỡng đạt tối thiểu: $\ge 95.0\%$)
- **Workflow có tỷ lệ thấp nhất**: `WF-___` đạt `___ %` (Yêu cầu bắt buộc: $\ge 90.0\%$)
- **Tỷ lệ trials trong điều kiện AMBIENT**: `___ %` (Yêu cầu bắt buộc: $\ge 20.0\%$)
- **Người thực hiện kiểm thử (Tester)**: _________________________________________
- **Thiết bị Microphone sử dụng**: _________________________________________
- **Phần cứng GPU thử nghiệm**: _________________________________________
- **Ngày hoàn thành kiểm thử**: _____ / _____ / 2026
- **KẾT LUẬN CUỐI CÙNG**:
  - [ ] **GO — Đạt Cổng Nghiệm Thu Product Beta**: Đủ điều kiện thăng hạng JARVIS từ Internal Beta Pilot lên Product Beta v1.
  - [ ] **NO-GO / CHƯA ĐẠT**: Cổng tiếp tục mở, yêu cầu kỹ thuật khắc phục các điểm nghẽn và tiến hành đo đạc lại.
