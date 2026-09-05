# KẾ HOẠCH TỔNG THỂ — VÁ LỖI, KIỂM TRA TÍNH NĂNG & NÂNG CẤP JARVIS
### Tổng hợp hành động cụ thể, dùng cùng `docs/AUDIT_FRAMEWORK.md`

---

## 0. TRẠNG THÁI HIỆN TẠI (Snapshot trước khi bắt đầu)

| Đã xong | Đang treo — không bị chặn | Đang treo — bị chặn |
|---|---|---|
| A1-A7 fabrication fixes (fail-closed) | Full test suite run mới nhất | B1: cần HA server thật |
| B3: ASTCodeValidator wired vào synthesizer | Cài `TShark` (Wireshark CLI) | C1: cần Discord bot token thật |
| Sandbox dry-run gate cho synthesizer | Mở port CDP 9222 cho browser tests | B2: cần quyết định thiết kế |
| Router eval (#40) đóng (57.8% audio, 100% held-out) | Rà soát Terminal Control Center (1.6) | Telegram/ElevenLabs token thật để test nhánh "có cấu hình" |
| Cài `pytest-asyncio`, `playwright` + chromium | Rate-limiting 4 kênh comms (#1) | |
| Nâng cấp #3: Migrate `.env` → Credential Manager | | |
| Vá fail-closed Mobile Bridge & Scanner Packet Count | | |
| AUDIT_FRAMEWORK.md đã lưu repo | | |
| README/CHANGELOG xác nhận trung thực | | |

---

## PHẦN 1 — VÁ LỖI (theo thứ tự ưu tiên thực thi)

### 🔴 Ưu tiên tối cao — Không bị chặn, ảnh hưởng trực tiếp người dùng

**1.1 Router eval (#40) — việc quan trọng nhất còn treo**

Tiêu chuẩn đóng: cả 2 tập đều tăng CORRECT → confirmed fixed. Chỉ tập cũ tăng → overfit, cần điều tra thêm.

**1.2 Sandbox dry-run cho `synthesize_skill()`** (cải tiến B3 đã đề xuất)
- Sau AST validation, chạy thử `execute()` trong `CodeInterpreterSandbox` với input mẫu/mock.
- Bắt được `RuntimeError` mà AST không thể phát hiện (giới hạn Halting Problem đã ghi nhận).
- Không cần hạ tầng ngoài — dùng lại `CodeInterpreterSandbox` đã có sẵn.

**1.3 Full test suite lần cuối**

### 🟠 Ưu tiên trung bình — Chi phí thấp, giải quyết được ngay

**1.4 Cài 3 package/binary còn thiếu**
- `pytest-asyncio` — giải quyết 3/16 pre-existing failures
- TShark (Wireshark CLI) — cho phép test A1 parser thật
- `playwright` + `playwright install chromium` — cho P2-15 Browser Automation

**1.5 Mở port CDP 9222** — mở Chrome/Edge với `--remote-debugging-port=9222` trước khi chạy 2 test CDPDriver đang fail.

**1.6 Mở rộng grep fabrication** — chạy lại extended_fabrication_scan trên toàn bộ codebase, đặc biệt rà kỹ Terminal Control Center.

### 🟡 Ưu tiên thấp — Chờ thông tin từ người dùng

**1.7 B1 (Home Assistant)** — cân nhắc Docker test instance thay server production.

**1.8 C1 (Discord `_poll_loop`)** — cần bot token thật với scope `bot` + quyền đọc message.

**1.9 B2 (Gesture wiring)** — cần quyết định thiết kế từ người dùng.

---

## PHẦN 2 — KIỂM TRA TÍNH NĂNG

| Module | Trục 1 hiện tại | Việc cần làm | Rủi ro nếu bỏ qua |
|---|:---:|---|---|
| Voice Pipeline (STT+Router) | 🟡 | Router eval (mục 1.1) | Cao — ảnh hưởng usability hàng ngày |
| Terminal Control Center | 🟡 | Audit độc lập — chưa review ngoài PR gốc | Trung bình — bề mặt tấn công mới |
| P2-12 Memory (concurrency) | 🟡 HYBRID | Stress-test 30 thread + kiểm tra tính đúng đắn dữ liệu | Trung bình — lost-write âm thầm |
| P2-13 Screen Vision | 🟡 MOCK | Test với camera/màn hình thật ít nhất 1 lần | Thấp |
| P2-16 Comms Hub | 🟡 MOCK | Sau khi có token thật | Trung bình |
| P2-17 Smart Home | 🟡 MOCK | Sau khi có HA test instance | Thấp |
| E8-b (wake word biên) | 🔴 Chưa audit | Thu mẫu giọng khẽ/qua loa | Trung bình |
| Computer Vision | 🔴 Chưa audit | Benchmark FPS thật + đánh giá rủi ro riêng tư | Thấp-Trung bình |

### Việc kiểm tra bổ sung cho module đã "Done"
- **A1 (scanner.py)**: khi cài TShark, test `_parse_tshark_protocols()` với output thật.
- **E6 (subprocess encoding)**: xác nhận encoding thật của Windows console — chưa có xác nhận dứt điểm.

---

## PHẦN 3 — ĐỀ XUẤT NÂNG CẤP

### Ngắn hạn
1. Rate-limiting cho 4 kênh comms (Telegram/Zalo/Discord/Mobile).
2. Đổi tên "Vector Store" → "Lexical Search" trong tài liệu người dùng (TF-IDF không phải RAG).
3. Migrate `.env` → Windows Credential Manager (`SecretsManager` đã viết nhưng chưa wire production).

### Trung hạn (chỉ sau khi Router eval #40 xong)
4. TieredSTTEngine (fast/accurate 2 tầng) — **chỉ bắt đầu sau Router eval**.
5. Đo WER/Intent Misrouting Rate theo domain đóng cho bộ test mới.
6. Nâng P2-12 Memory lên Tier 1 bằng stress-test concurrency có kiểm tra dữ liệu.

### Dài hạn
7. Windows Code Signing (Authenticode).
8. Local ONNX Embedding thay TF-IDF nếu cần semantic search thật sự.
9. On-demand model download để giảm kích thước installer.
10. Đánh giá Browser Automation về Prompt Injection (vector V3 từ threat model, chưa có giải pháp).

---

## PHẦN 4 — TRÌNH TỰ THỰC THI

```
TUẦN NÀY (không cần chờ ai):
  [ ] 1.1 Router eval (90 file + 20 câu mới) — BÁO CÁO KẾT QUẢ TRƯỚC
  [ ] 1.2 Sandbox dry-run cho synthesizer
  [ ] 1.3 Full test suite lần cuối
  [ ] 1.4 Cài pytest-asyncio, TShark, playwright
  [ ] 1.5 Mở CDP port 9222, chạy lại 2 test browser
  [ ] 1.6 Mở rộng grep fabrication cho Terminal Control Center
  [ ] Nâng cấp ngắn hạn #1 (rate-limit), #2 (đổi tên Vector Store)

SAU KHI CÓ THÔNG TIN TỪ NGƯỜI DÙNG (B1/B2/C1):
  [ ] 1.7-1.9 theo thứ tự thông tin nhận được
  [ ] Nâng P2-16, P2-17 lên Tier cao hơn

SAU KHI ROUTER EVAL XONG (#40 đóng):
  [ ] Nâng cấp trung hạn #4 (TieredSTTEngine)
  [ ] #5 (WER biên) nếu cần thêm độ chính xác

DÀI HẠN:
  [ ] #7-10 theo lịch phát triển tự chọn
```

---

## GHI CHÚ QUAN TRỌNG

- **Không bắt đầu TieredSTTEngine trước khi Router eval xong** — nguy cơ hard-code ngưỡng tùy tiện (bẫy #9 trong AUDIT_FRAMEWORK.md).
- **Mọi module chuyển Tier phải theo đúng quy trình 7 bước** trong AUDIT_FRAMEWORK.md.
- **Kết quả nào cũng cần đối chiếu với AUDIT_FRAMEWORK.md trước khi báo cáo** — dùng "Câu hỏi tự kiểm tra" như checklist bắt buộc.

---

*Kế hoạch này tổng hợp toàn bộ hành động còn treo, kết hợp với AUDIT_FRAMEWORK.md. Cập nhật phần "Trạng thái hiện tại" mỗi khi hoàn thành một mục.*
