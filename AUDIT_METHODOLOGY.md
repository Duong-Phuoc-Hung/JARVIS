# KHUNG PHƯƠNG PHÁP LUẬN: REVIEW DỰ ÁN & LẬP KẾ HOẠCH HOÀN THIỆN
### Đúc kết từ 22 vòng audit đối kháng — dùng làm quy trình chuẩn cho mọi lần review tiếp theo

---

## PHẦN A — 7 TIÊU CHÍ BẮT BUỘC CHO MỌI TUYÊN BỐ "ĐÃ HOÀN THIỆN"

Trước khi dán nhãn bất kỳ phân hệ nào là "xong", "hoàn thiện", "✅", trả lời đủ 7 câu hỏi sau bằng **bằng chứng cụ thể**, không phải suy luận hay mô tả định tính:

| # | Câu hỏi | Bằng chứng chấp nhận được | Bằng chứng KHÔNG chấp nhận |
|---|---|---|---|
| 1 | **Có test không, hay chỉ có mô tả?** | Tên file test cụ thể, số lượng case, log pass/fail | "Đã hoạt động tốt", "mượt mà" |
| 2 | **Test chạy trên môi trường thật hay mock?** | Ghi rõ: `TEST THẬT` / `TEST MOCK` | Không phân biệt, gộp chung "đã test" |
| 3 | **Nếu là số liệu hiệu năng, N mẫu là bao nhiêu?** | N≥30 cho percentile (p95/p99); N=5 chỉ đủ cho p50+StdDev | Đưa p95/p99 từ N<10 mẫu mà không cảnh báo |
| 4 | **Nếu là ranh giới bảo mật, Hard Boundary hay Risk-Reduction?** | Hard = kernel-enforced/deterministic; Risk-Reduction = heuristic/xác suất | Gọi mọi thứ là "đã chặn" như nhau |
| 5 | **Nếu chọn ngưỡng/tham số, có bằng chứng đường cong hay chỉ đoán?** | Bảng quét nhiều giá trị, chọn điểm tối ưu có lý do | Hard-code một số "nghe hợp lý" |
| 6 | **Module mới xuất hiện lần đầu, đã qua ít nhất 1 vòng audit riêng chưa?** | Có file test + kết quả cụ thể cho module đó | Dán nhãn "Hoàn thiện" ngay khi mới viết xong |
| 7 | **Con số tổng hợp có tự mâu thuẫn với chi tiết bên dưới không?** | Kết luận tổng được suy ra trực tiếp từ bảng chi tiết | Viết kết luận lạc quan độc lập với bảng dữ liệu |

**Quy tắc vàng:** Nếu không trả lời được ít nhất 5/7 câu bằng bằng chứng cụ thể → dán nhãn 🟡 (thiếu bằng chứng) hoặc 🔴 (chưa audit), không được dán 🟢.

---

## PHẦN B — HỆ THỐNG PHÂN TẦNG CHUẨN (THAY CHO % / ĐIỂM SỐ)

```
🟢 TIER 1 — Đã kiểm chứng thật
   Có test chạy trên môi trường thật (không mock) + kết quả cụ thể +
   (nếu là bảo mật) phân loại đúng Hard/Risk-Reduction

🟡 TIER 2 — Logic đúng, thiếu bằng chứng thật
   Có test nhưng chỉ mock, HOẶC N quá nhỏ, HOẶC chưa xác nhận end-to-end

🔴 TIER 3 — Chưa audit / có vấn đề kiến trúc chưa giải
   Không có test nào, HOẶC có vấn đề đã biết chưa giải, HOẶC mô tả sai bản chất kỹ thuật
```

**Không bao giờ dùng:** điểm số %/10, các cụm "tuyệt đối an toàn", "hoàn hảo", "sẵn sàng production" không kèm điều kiện.

---

## PHẦN C — QUY TRÌNH REVIEW MỘT PHÂN HỆ

```
BƯỚC 1: Đọc code trực tiếp (không đọc mô tả trước)
   → Trích dẫn số dòng cụ thể nếu phát hiện vấn đề ("zalo.py:90-109")

BƯỚC 2: Hỏi "Test nào xác nhận điều này?"
   → Nếu câu trả lời là "chưa có" → dừng lại, không dán nhãn Tier 1

BƯỚC 3: Với mọi cơ chế phòng thủ, tự hỏi "Làm sao để né được cái này?"
   → Thử ít nhất 3 hướng: (a) API thay thế cùng chức năng, (b) truy cập ở tầng
     khác (class vs instance), (c) điều kiện biên
   → Case thật: __closure__, __globals__ class-level, win32api thay ctypes,
     COM automation thay socket

BƯỚC 4: Với mọi số liệu benchmark, tự hỏi "Số này có pattern bất thường không?"
   → Case thật: RTF 1.10x tuyệt đối = dấu hiệu số bị tính công thức, không đo thật

BƯỚC 5: Viết kết luận CHỈ dựa trên những gì đã xác nhận ở bước 1-4
```

---

## PHẦN D — 14 BẪY PHƯƠNG PHÁP LUẬN ĐÃ PHÁT HIỆN

| Bẫy | Mô tả | Cách phòng tránh |
|---|---|---|
| **Bẫy điểm số giả** | Chấm 88%, 92%, 9.5/10 không có phương pháp đo | Cấm dùng %/10; chỉ dùng Tier 1/2/3 |
| **Bẫy overclaim tổng-chi tiết mâu thuẫn** | "100% hoàn thành" trong khi bảng chi tiết cùng báo cáo liệt kê nhiều mục chưa xong | Kết luận phải suy trực tiếp từ bảng |
| **Bẫy blocklist trong hệ mở** | Liệt kê từng module/đuôi file nguy hiểm — luôn sót | Chuyển sang allowlist hoặc prefix-wildcard |
| **Bẫy "B1 mà tưởng là B2"** | Xác nhận bước chuẩn bị rồi coi như xác nhận toàn bộ chuỗi | Tách rõ "API khả thi" (B1) và "hành vi end-to-end đã quan sát" (B2) |
| **Bẫy giấu bí mật trong ngôn ngữ reflective** | Cố giấu hàm/biến trong Python khi code không tin cậy chạy chung interpreter | Ranh giới thật phải ở tầng OS/kernel |
| **Bẫy benchmark mock lẫn với thật** | Đưa số liệu mock/adapter vào cùng bảng với số liệu đo phần cứng thật | Tách bảng riêng, ghi rõ điều kiện đo trong bảng |
| **Bẫy cỡ mẫu quá nhỏ** | Báo cáo p95/p99 từ N=5 | N≥30 mới nên báo percentile; N<10 chỉ báo p50+StdDev |
| **Bẫy pattern-quá-đẹp** | RTF tuyến tính tuyệt đối, số liệu đồng đều bất thường | Nghi ngờ mọi số liệu "quá sạch" |
| **Bẫy chọn ngưỡng tùy tiện** | Hard-code threshold không dựa trên đường cong dữ liệu | Luôn quét nhiều giá trị, chọn dựa trên trade-off cụ thể |
| **Bẫy domain-mismatch metric** | Dùng WER tự do cho hệ thống domain đóng | Dùng metric đúng bản chất (Intent Misrouting Rate) |
| **Bẫy quy kết nhân quả không kiểm chứng** | "Tỷ lệ đúng thấp là do X" mà không tách được nguyên nhân thật | Luôn có breakdown từng thành phần trước khi kết luận nguyên nhân |
| **Bẫy tăng trưởng "Hoàn thiện" đột biến** | Hàng loạt module mới dán ✅ trong 1 ngày không có audit riêng | Module mới mặc định 🔴/🟡 cho tới khi qua test thật |
| **Bẫy risk-reduction đội lốt hard-boundary** | Xếp PromptGuard, rate-limit ngang với kernel-enforced | Luôn tách cột: Hard Boundary vs Risk-Reduction |
| **Bẫy rủi ro an toàn ẩn trong mục "cần cải thiện"** | Chôn phát hiện nghiêm trọng vào mục phụ thay vì headline | Bất kỳ con số nào ngụ ý phần lớn use-case thất bại phải lên đầu |

---

## PHẦN E — KHUNG LẬP KẾ HOẠCH NÂNG CẤP

### Thứ tự ưu tiên chuẩn

```
1. 🔴 Lỗ hổng bảo mật Hard Boundary còn hở (RCE, exfiltration, privilege escalation)
2. 🔴 Rủi ro an toàn ảnh hưởng hành vi hệ thống (hallucination → hành động sai)
3. 🟠 Khoảng trống bằng chứng cho tuyên bố đã công bố
4. 🟠 Module chưa qua audit nhưng đang dùng trong production
5. 🟡 Cải thiện UX/hiệu năng đã có bằng chứng rõ vấn đề
6. 🟢 Nợ kỹ thuật dài hạn (code signing, đổi tên gọi sai...)
```

### Mẫu bảng theo dõi tiến độ

| # | Việc | Tier hiện tại | Tier mục tiêu | Bằng chứng cần có để chuyển Tier | Trạng thái |
|---|---|:---:|:---:|---|---|
| 1 | ... | 🟡 | 🟢 | Tên test cụ thể sẽ viết | ⏳/✅ |

---

## PHẦN F — TỰ KIỂM TRA TRƯỚC KHI CÔNG BỐ BÁO CÁO

- [ ] Mọi con số hiệu năng đều ghi rõ N mẫu và điều kiện đo (thật/mock)?
- [ ] Mọi tuyên bố "đã chặn"/"đã đóng" đều có tên test case cụ thể đi kèm?
- [ ] Không có điểm số %/10 nào xuất hiện trong toàn bộ báo cáo?
- [ ] Câu kết luận tổng có thể được người đọc tự suy ra từ bảng chi tiết, không mâu thuẫn?
- [ ] Module mới thêm vào có được audit riêng, hay chỉ "thừa hưởng" nhãn tốt?
- [ ] Nếu có phát hiện rủi ro nghiêm trọng, nó nằm ở phần đầu/nổi bật, không bị chôn trong mục phụ?

---

*Đúc kết từ 22 vòng audit đối kháng — JARVIS project 2026-08-30 đến 2026-09-01.*
