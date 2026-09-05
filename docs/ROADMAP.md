# KẾ HOẠCH TỔNG THỂ — VÁ LỖI, KIỂM TRA TÍNH NĂNG & NÂNG CẤP JARVIS
### Tổng hợp hành động cụ thể, dùng cùng `docs/AUDIT_FRAMEWORK.md`

---

## 0. TRẠNG THÁI HIỆN TẠI (Snapshot trước khi bắt đầu)

| Đã xong | Đang treo — không bị chặn | Đang treo — bị chặn |
|---|---|---|
| A1-A7 fabrication fixes (fail-closed) | **Router eval (#40)** — ưu tiên #1 | B1: cần HA server thật |
| B3: ASTCodeValidator wired vào synthesizer | Full test suite run mới nhất | C1: cần Discord bot token thật |
| AUDIT_FRAMEWORK.md đã lưu repo | Cài `pytest-asyncio`, `TShark`, `playwright` | B2: cần quyết định thiết kế |
| README/CHANGELOG xác nhận trung thực | Sandbox dry-run cho synthesizer | Telegram/ElevenLabs token thật để test nhánh "có cấu hình" |

---

## PHẦN 1 — VÁ LỖI (theo thứ tự ưu tiên thực thi)

### 🔴 Ưu tiên tối cao — Không bị chặn, ảnh hưởng trực tiếp người dùng

**1.1 Router eval (#40) — việc quan trọng nhất còn treo**
```bash
# Bước 1: chạy lại 90 file cũ, xác nhận CORRECT tăng sau khi sửa taxonomy
python tests/eval/stt_intent_eval.py --models large-v3 --conditions clean noisy

# Bước 2: tạo bộ test độc lập mới — 20 câu KHÔNG dùng để derive rule
#   Lấy từ 14 intent trong INTENT_TEST_SET, viết thêm 1-2 biến thể mới mỗi intent
#   chưa từng xuất hiện trong 90 file gốc hay trong danh sách rule đã sửa

# Bước 3: eval trên bộ mới, so sánh CORRECT rate với bộ cũ
```
**Tiêu chuẩn đóng:** cả 2 tập đều tăng CORRECT → confirmed fixed. Chỉ tập cũ tăng → overfit, cần điều tra thêm (có thể do rule quá cụ thể, không tổng quát).

**1.2 Sandbox dry-run cho `synthesize_skill()`** (cải tiến B3 đã đề xuất)
- Sau AST validation, chạy thử `execute()` trong `CodeInterpreterSandbox` với input mẫu/mock trước khi kích hoạt cho người dùng.
- Bắt được `RuntimeError` mà AST không thể phát hiện (giới hạn Halting Problem đã ghi nhận).
- Không cần hạ tầng ngoài — dùng lại `CodeInterpreterSandbox` đã có sẵn.

**1.3 Full test suite lần cuối**
```bash
pytest tests/ -q --timeout=60 2>&1 | tee test_results_final.txt
pytest tests/ --collect-only -q | tail -5   # đối chiếu tổng số test
```
Cần có con số này trước khi coi Phase 1 + B3 "đóng hoàn toàn" theo đúng chuẩn đã áp dụng cho các phase trước.

### 🟠 Ưu tiên trung bình — Chi phí thấp, giải quyết được ngay

**1.4 Cài 3 package/binary còn thiếu**
```bash
pip install pytest-asyncio          # giải quyết 3/16 pre-existing failures
# Cài TShark (Wireshark CLI) → cho phép test A1 parser thật
pip install playwright && playwright install chromium   # cho P2-15 Browser Automation
```

**1.5 Mở port CDP 9222** — mở Chrome/Edge với `--remote-debugging-port=9222` trước khi chạy 2 test CDPDriver đang fail.

**1.6 Mở rộng grep fabrication** — chạy lại `extended_fabrication_scan.py` (đã viết ở Phase 1) trên toàn bộ codebase một lần nữa, đặc biệt rà kỹ **Terminal Control Center** (module mới nhất, ít audit nhất, hiển thị trực tiếp cho người dùng).

### 🟡 Ưu tiên thấp — Chờ thông tin từ bạn (không tự làm được)

**1.7 B1 (Home Assistant)** — nếu có ý định dùng thật, cân nhắc dựng test instance qua Docker (`homeassistant/home-assistant` image) thay vì cần server production thật, để runtime-verify `call_service()` end-to-end mà không rủi ro tới thiết bị nhà thật.

**1.8 C1 (Discord `_poll_loop`)** — cần bot token thật với scope `bot` + quyền đọc message trước khi implement `GET /channels/{id}/messages` polling thật.

**1.9 B2 (Gesture wiring)** — cần bạn quyết định: đây có phải tính năng bạn thực sự muốn dùng (wave tay để điều khiển), hay giữ nguyên `LIMITED` là đủ cho nhu cầu hiện tại?

---

## PHẦN 2 — KIỂM TRA TÍNH NĂNG (áp dụng 4 trục từ AUDIT_FRAMEWORK.md)

### Danh sách module cần audit lại/lần đầu, sắp theo mức độ rủi ro nếu bỏ qua

| Module | Trục 1 hiện tại | Việc cần làm để tăng Tier | Rủi ro nếu bỏ qua |
|---|:---:|---|---|
| Voice Pipeline (STT+Router) | 🟡 | Xong Router eval (mục 1.1) | Cao — ảnh hưởng usability hàng ngày |
| Terminal Control Center | 🟡 | Audit độc lập — chưa có ai review ngoài chính PR gốc | Trung bình — bề mặt tấn công mới từ contributor ngoài |
| P2-12 Memory (concurrency) | 🟡 HYBRID | Stress-test 30 thread đồng thời + kiểm tra tính đúng đắn dữ liệu (không chỉ "không exception") | Trung bình — lost-write âm thầm |
| P2-13 Screen Vision | 🟡 MOCK | Test với camera/màn hình thật ít nhất 1 lần | Thấp — không phải core feature |
| P2-16 Comms Hub | 🟡 MOCK | Sau khi có token thật (C1, B3 mục 1.8/1.3 hạ tầng) | Trung bình |
| P2-17 Smart Home | 🟡 MOCK (rất ít) | Sau khi có HA test instance (mục 1.7) | Thấp — ít người dùng tính năng này hàng ngày |
| E8-b (wake word biên) | 🔴 Chưa audit | Thu mẫu giọng khẽ/qua loa | Trung bình — ảnh hưởng độ chính xác kích hoạt |
| Computer Vision (Face/Gesture nhận diện) | 🔴 Chưa audit | Benchmark FPS thật + đánh giá rủi ro riêng tư | Thấp-Trung bình tùy mức độ dùng |

### Việc kiểm tra bổ sung cần làm cho các module đã "Done"

- **A1 (scanner.py)**: khi cài TShark xong, chạy thử `capture_packets()` thật, xác nhận `_parse_tshark_protocols()` parse đúng định dạng — đừng giả định code đã viết là đúng chỉ vì logic "nhìn hợp lý".
- **E6 (subprocess encoding)**: xác nhận lại encoding thật của Windows console (`chcp`, `locale.getpreferredencoding()`) — đã treo từ lâu, chưa có xác nhận dứt điểm liệu UTF-8 hard-code có đúng 100% trường hợp hay không.

---

## PHẦN 3 — ĐỀ XUẤT NÂNG CẤP (phân theo thời hạn)

### Ngắn hạn (làm trong đợt tới)
1. Rate-limiting cho 4 kênh comms (Telegram/Zalo/Discord/Mobile) — chưa làm, đã đề xuất từ lâu, chi phí thấp.
2. Đổi tên "Vector Store" → "Lexical Search" trong toàn bộ tài liệu người dùng — TF-IDF không phải RAG, đây là sửa tài liệu, không cần code.
3. Windows Credential Manager — migrate `.env` sang `SecretsManager` đã viết nhưng chưa wire vào production.

### Trung hạn
4. TieredSTTEngine (fast/accurate 2 tầng) — **chỉ implement sau khi Router eval (#40) xác nhận xong**, vì ngưỡng confidence cần dữ liệu thật, không đoán.
5. Đo WER/Intent Misrouting Rate theo domain đóng cho bộ test mới (mục 1.1) trên điều kiện âm thanh biên (C3 trong file điều kiện tiên quyết).
6. Nâng P2-12 Memory lên Tier 1 bằng stress-test concurrency có kiểm tra tính đúng đắn dữ liệu.

### Dài hạn
7. Windows Code Signing (Authenticode).
8. Local ONNX Embedding thay TF-IDF nếu thực sự cần semantic search.
9. On-demand model download để giảm kích thước installer.
10. Đánh giá riêng cho Browser Automation về khả năng chống Prompt Injection (vector V3 đã biết từ threat model ban đầu, chưa có giải pháp cụ thể).

---

## PHẦN 4 — TRÌNH TỰ THỰC THI CỤ THỂ (Gantt đơn giản theo thứ tự)

```
TUẦN NÀY (không cần chờ ai):
  □ 1.1 Router eval (90 file + 20 câu mới) — BÁO CÁO KẾT QUẢ TRƯỚC
  □ 1.2 Sandbox dry-run cho synthesizer
  □ 1.3 Full test suite lần cuối
  □ 1.4 Cài 3 package (pytest-asyncio, TShark, playwright)
  □ 1.5 Mở CDP port 9222, chạy lại 2 test browser
  □ 1.6 Mở rộng grep fabrication cho Terminal Control Center
  □ Nâng cấp ngắn hạn #1, #2 (rate-limit, đổi tên Vector Store)

SAU KHI CÓ THÔNG TIN TỪ BẠN (B1/B2/C1/B3-token):
  □ 1.7-1.9 theo thứ tự bạn cung cấp thông tin
  □ Nâng P2-16, P2-17 lên Tier cao hơn tương ứng

SAU KHI ROUTER EVAL XONG (#40 đóng):
  □ Nâng cấp trung hạn #4 (TieredSTTEngine) — chỉ bắt đầu từ đây
  □ #5 (WER biên) nếu cần thêm độ chính xác

DÀI HẠN (không gấp):
  □ #7-10 theo lịch phát triển tự chọn
```

---

## GHI CHÚ QUAN TRỌNG

- **Không bắt đầu TieredSTTEngine trước khi Router eval xong** — đã 2 lần bị cảnh báo nguy cơ hard-code ngưỡng tùy tiện (bẫy #9 trong AUDIT_FRAMEWORK.md).
- **Mọi module chuyển Tier phải theo đúng quy trình 7 bước** trong AUDIT_FRAMEWORK.md — không tự nâng 🟢 chỉ vì thêm test mock.
- **Kết quả nào cũng cần đối chiếu với AUDIT_FRAMEWORK.md trước khi báo cáo** — dùng "Câu hỏi tự kiểm tra" ở cuối file đó như checklist bắt buộc trước khi gửi báo cáo.

---

*Kế hoạch này tổng hợp toàn bộ hành động còn treo từ audit trước, kết hợp với AUDIT_FRAMEWORK.md (đánh giá) và điều kiện tiên quyết (chuẩn bị). Nên cập nhật lại phần "Trạng thái hiện tại" mỗi khi hoàn thành một mục.*
