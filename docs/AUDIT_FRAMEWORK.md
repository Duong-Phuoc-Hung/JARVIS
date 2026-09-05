# BỘ TIÊU CHÍ ĐÁNH GIÁ TOÀN DIỆN HỆ THỐNG
### Đúc kết từ 50 vòng audit đối kháng — Dùng để đánh giá bất kỳ module, tính năng, hoặc toàn bộ dự án

---

## NGUYÊN TẮC NỀN TẢNG

Đánh giá một hệ thống không phải là gán một nhãn duy nhất ("xong"/"chưa xong"). Qua toàn bộ quá trình audit, mọi module cần được chấm theo **4 trục độc lập** — một module có thể đạt điểm cao ở trục này nhưng thấp ở trục khác, và đó là thông tin quan trọng, không nên gộp thành một con số duy nhất.

```
┌─────────────────────────────────────────────────────────────────┐
│  TRỤC 1: BẰNG CHỨNG (Evidence)     — Đã kiểm chứng đến đâu?     │
│  TRỤC 2: TRUNG THỰC (Truthfulness) — Kết quả trả về có bịa không?│
│  TRỤC 3: RANH GIỚI (Boundary Type) — Nếu là bảo mật, loại gì?    │
│  TRỤC 4: CHẶN BỞI GÌ (Blocked-by)  — Có thể tiến triển ngay không?│
└─────────────────────────────────────────────────────────────────┘
```

---

## TRỤC 1 — BẰNG CHỨNG (Evidence Tier)

| Mức | Định nghĩa | Điều kiện xác nhận |
|---|---|---|
| 🟢 **T1 — Đã kiểm chứng thật** | Test chạy trên OS/hardware/API thật, không mock phần cốt lõi | File test cụ thể, `grep import` xác nhận test gọi đúng class production (không phải class tự định nghĩa trong file test) |
| 🟡 **T2 — Thiếu bằng chứng thật** | Logic đúng nhưng test mock phần quan trọng, hoặc N mẫu quá nhỏ | Ghi rõ phần nào bị mock (API, hardware, network...) |
| 🔴 **T3 — Chưa audit / vấn đề kiến trúc** | Không có test, hoặc có vấn đề đã biết chưa giải quyết được | Không có file test nào import class này, hoặc tên gọi sai bản chất kỹ thuật |

**Câu hỏi kiểm tra nhanh:** *"Nếu tôi xóa hết mock trong test này, nó còn chạy được không?"* — Nếu không, đây là T2, không phải T1.

---

## TRỤC 2 — TRUNG THỰC (Truthfulness) — Bổ sung mới, quan trọng ngang Trục 1

Đây là trục phát hiện được qua audit A1-A7: **một hàm có thể có Tier bằng chứng cao nhưng vẫn fabrication** nếu nó trả `success=True`/`ok=True` mà không có bằng chứng thật đứng sau.

| Mức | Định nghĩa | Ví dụ đã gặp |
|---|---|---|
| ✅ **Truthful (Fail-closed)** | Chỉ trả `True`/`success` sau khi có bằng chứng cụ thể (response 2xx, file tồn tại, process spawn thành công) | `open_app('notepad')` → `True` chỉ sau khi `shutil.which()` xác nhận path tồn tại |
| ⚠️ **Silent Fallback** | Trả `True` như giá trị mặc định khi thiếu cấu hình/client, không phải vì đã xác nhận | Telegram `send_message()` trả `ok=True` khi không có bot token (đã sửa) |
| 🔴 **Active Fabrication** | Bịa dữ liệu trông như thật (số liệu tính sẵn, chuỗi hardcode) thay vì thu thập/tính toán thật | `PacketCapture` bịa tỷ lệ TCP/UDP/ICMP theo công thức 70/20/10% cố định |
| 👻 **Ghost Process** | Thread/tiến trình chạy thật (không lỗi, không crash) nhưng không thực hiện chức năng đã khai báo | Discord `_poll_loop()` chỉ `sleep(2.0)`, không gọi API |

**Quy tắc bắt buộc:** Mọi hàm trả `success`/`ok`/`status` phải **fail-closed theo mặc định** — chỉ `True` sau khi có bằng chứng cụ thể. Đây là quy tắc code review nên áp dụng cho *mọi* PR mới, không chỉ khi audit.

**Kỹ thuật phát hiện:** Không tin đọc code tĩnh — gọi hàm thật với input rỗng/giả (`token=""`, `mock_http=None`, tên app không tồn tại) và quan sát giá trị trả về thực tế.

---

## TRỤC 3 — LOẠI RANH GIỚI (chỉ áp dụng cho cơ chế bảo mật/phòng thủ)

| Loại | Đặc điểm | Ví dụ |
|---|---|---|
| 🔒 **Hard Boundary** | Kernel-enforced, quyết định luận (deterministic), không có ngoại lệ kỹ thuật | Windows Job Object (`ActiveProcessLimit=1`), MIC (`TokenIntegrityLevel=LOW`) |
| 🛡️ **Risk-Reduction** | Heuristic/xác suất, có thể bị né bằng input đủ tinh vi | PromptGuard sanitization, Rate Limiter, AST Validator (chỉ bắt cú pháp tĩnh) |

**Quy tắc:** Không bao giờ xếp 2 loại này chung một cột "đã chặn". Risk-Reduction là lớp phòng thủ bổ trợ (defense-in-depth), không phải điểm dừng cuối cùng — luôn còn khả năng bị vượt qua bằng kỹ thuật chưa biết.

**Giới hạn cố hữu cần ghi nhận, không phải "thiếu sót":** một số công cụ về bản chất không thể vượt qua giới hạn lý thuyết của nó (ví dụ AST Validator không thể chứng minh chương trình không crash lúc chạy — Halting Problem). Ghi nhận đúng giới hạn này là trung thực, không phải yếu kém.

---

## TRỤC 4 — CHẶN BỞI GÌ (Blocked-by) — Xác định được làm ngay hay phải chờ

| Trạng thái | Nghĩa là gì | Hành động |
|---|---|---|
| ❌ **Không bị chặn** | Mọi tài nguyên cần thiết đã có sẵn (code, dữ liệu, script) | Ưu tiên làm ngay — không có lý do trì hoãn |
| ⏳ **Bị chặn bởi hạ tầng** | Cần token/server/thiết bị thật chưa có | Hỏi người dùng xác nhận, không tự đoán |
| ⏳ **Bị chặn bởi quyết định thiết kế** | Cần con người quyết định hướng đi (feature mới vs giữ nguyên giới hạn) | Đặt câu hỏi rõ ràng, không tự ý chọn |

**Bài học quan trọng:** đừng để việc "chưa thể tiến triển vì thiếu X" làm trì hoãn những việc *không* bị chặn bởi X. Luôn ưu tiên việc không bị chặn trước, kể cả khi nó có vẻ ít "quan trọng" hơn về mặt kiến trúc.

---

## BẢNG TỔNG HỢP MẪU — DÙNG CHO MỌI MODULE

| Module | T. Bằng chứng | T. Trung thực | T. Ranh giới (nếu có) | T. Bị chặn bởi | Ghi chú |
|---|:---:|:---:|:---:|:---:|---|
| *(tên module)* | 🟢/🟡/🔴 | ✅/⚠️/🔴/👻 | 🔒/🛡️/— | ❌/⏳ | *(bằng chứng cụ thể)* |

---

## QUY TRÌNH ÁP DỤNG 4 TRỤC CHO MỘT MODULE MỚI

```
BƯỚC 1: Đọc code — không tin mô tả, đọc trực tiếp implementation
BƯỚC 2: Grep xác nhận test có import class production không
         (không phải test tự định nghĩa mock class trùng tên)
BƯỚC 3: Runtime-verify: gọi hàm thật với input rỗng/giả/biên
         → xem giá trị success/ok/status trả về là gì thật sự
BƯỚC 4: Với mọi cơ chế "chặn"/"bảo vệ": thử ít nhất 1 cách né
         (API thay thế, truy cập tầng khác, điều kiện biên)
BƯỚC 5: Với số liệu: kiểm tra N mẫu, điều kiện đo, pattern có
         "quá đẹp" không (quá tuyến tính, quá đồng đều)
BƯỚC 6: Xếp module vào đúng 4 trục — không gộp thành 1 nhãn duy nhất
BƯỚC 7: Nếu phát hiện rủi ro nghiêm trọng, đặt lên đầu báo cáo,
         không chôn trong mục "cần cải thiện"
```

---

## DANH SÁCH BẪY ĐÃ XÁC NHẬN QUA THỰC TẾ (checklist phòng tránh)

| # | Bẫy | Cách phát hiện đã dùng |
|---|---|---|
| 1 | Điểm số %/10 không có phương pháp | Thay bằng 4 trục ở trên |
| 2 | Kết luận tổng mâu thuẫn với bảng chi tiết cùng báo cáo | Kết luận phải suy trực tiếp từ bảng |
| 3 | Blocklist trong hệ mở (luôn sót) | Chuyển sang allowlist/prefix-wildcard |
| 4 | B1 (chuẩn bị) tưởng là B2 (end-to-end) | Tách rõ 2 bước, yêu cầu bằng chứng riêng |
| 5 | Cố giấu bí mật trong ngôn ngữ reflective | Chấp nhận giới hạn; chuyển ranh giới xuống OS |
| 6 | Benchmark mock lẫn với thật trong cùng bảng | Tách bảng, ghi rõ điều kiện đo ngay trong bảng |
| 7 | N mẫu quá nhỏ báo percentile | N<10 chỉ báo giá trị đơn/trung bình |
| 8 | Pattern số liệu "quá đẹp" (tuyến tính tuyệt đối) | Nghi ngờ; số thật luôn có nhiễu |
| 9 | Chọn ngưỡng tùy tiện không có đường cong dữ liệu | Luôn quét nhiều giá trị trước khi chốt |
| 10 | Domain-mismatch metric (WER cho hệ đóng) | Dùng metric đúng bản chất hệ thống |
| 11 | Quy kết nguyên nhân chưa kiểm chứng | Traceback/breakdown trước khi kết luận |
| 12 | Tăng trưởng "Hoàn thiện" đột biến (module mới = 🟢 ngay) | Mặc định 🔴/🟡 cho tới khi qua audit riêng |
| 13 | Risk-reduction đội lốt hard-boundary | Tách cột riêng bắt buộc |
| 14 | Rủi ro nghiêm trọng chôn trong mục phụ | Đưa lên đầu báo cáo |
| 15 | **Fabrication: success=True làm fallback mặc định** | Runtime-verify với input rỗng/giả |
| 16 | **Ghost process: thread chạy nhưng không làm gì** | Kiểm tra nội dung vòng lặp, không chỉ "thread alive" |
| 17 | **Overfit vào chính dữ liệu dùng để sửa lỗi** | Luôn cần bộ test độc lập mới để xác nhận tổng quát |
| 18 | **Test dùng class/mock tự định nghĩa thay vì import production** | `grep "^from jarvis\|^import jarvis"` trong mọi file test |
| 19 | **Việc bị chặn bởi X làm trì hoãn việc không liên quan tới X** | Luôn tách rõ Trục 4, ưu tiên việc không bị chặn trước |

---

## CÂU HỎI TỰ KIỂM TRA TRƯỚC KHI CÔNG BỐ ĐÁNH GIÁ HỆ THỐNG

- [ ] Mọi module đều được chấm đủ 4 trục, không gộp thành 1 nhãn?
- [ ] Mọi hàm trả `success/ok/status` đã được runtime-verify với input rỗng/giả chưa?
- [ ] Có module nào mới thêm vào mà chưa qua audit riêng nhưng đã dán 🟢 không?
- [ ] Số liệu benchmark có ghi rõ N và điều kiện đo ngay trong bảng không?
- [ ] Nếu có cải thiện sau khi sửa lỗi, đã có bộ test độc lập xác nhận không overfit chưa?
- [ ] Phát hiện nghiêm trọng nhất có nằm ở đầu báo cáo không?
- [ ] Danh sách việc tiếp theo có phân biệt rõ "không bị chặn — làm ngay" và "bị chặn — chờ thông tin" không?

---

*Bộ tiêu chí này là bản tổng hợp cuối cùng sau 50 vòng audit đối kháng cho dự án JARVIS, mở rộng khung phương pháp luận ban đầu bằng Trục 2 (Trung thực) — phát hiện quan trọng nhất rút ra từ đợt audit fabrication A1–A7.*
