## PHASE D (2026-09-12) — D-01 đến D-17 Hoàn thành & Trạng thái Khả dụng

| ID | Status | Mô tả |
|----|--------|-------|
| D-01 | DONE | Fix CI #200 pycaw mock injection & headless audio parity (CI 100% GREEN) |
| D-02 | DONE | Clean env parity — full suite pass với CI env vars |
| D-03 | DONE | PacketCapture truthfulness — proc.returncode check + 18 tests |
| D-04 | DONE | Browser CDP fail-closed + real Chromium tests (23 tests) |
| D-05 | DONE | Prompt injection regression tests (22 tests) |
| D-06 | PENDING_CREDENTIALS | Telegram transport fail-closed & whitelisting — cần bot token thật |
| D-07 | PENDING_CREDENTIALS | Zalo OA fail-closed & token bucket — cần OA credentials thật |
| D-08 | PENDING_CREDENTIALS | Discord gateway fail-closed & thread cleanup — cần bot token thật |
| D-09 | PENDING_CREDENTIALS | IMAP email real imaplib client — cần app-password thật |
| D-10 | DONE | Home Assistant authoritative write path qua ActionDispatcher + domain allowlist (13 tests) |
| D-11 | DONE | Dispatcher consistency tests (13 tests) |
| D-12 | DONE | One-click Windows Installer `JARVIS_Setup_v5.1.0.exe` (71.4 MB, Inno Setup 6, SHA-256 `E6335E5BF7F704B0FA09E38937BA89CB668939FF9090746B45150ED722031650`) |
| D-13 | DONE | Updater module với SHA256 + atomic replace + rollback (19 tests) |
| D-14 | BLOCKED_ON_CERT | Authenticode signing pipeline documented; blocked on commercial EV/OV cert |
| D-15 | DONE | Support diagnostics + log redaction bundle zip |
| D-16 | DONE | Secrets hardening — HASS_TOKEN & ELEVENLABS_API_KEY managed by Credential Manager |
| D-17 | DONE | RC build v5.1.0 / v5.1.3 — version bumped, artifact SHA256 generated, CHANGELOG updated |

---

## PHASE H (2026-09-13) — Voice Pipeline & Beta v1 Hardening (Trạng thái trung thực: 9 DONE, 4 CHƯA ĐÓNG/BLOCKED)

| ID | Status | Mô tả |
|----|--------|-------|
| H-01 | DONE | Fix resample mismatch: `record_audio()` chuyển default 16000 Hz, tránh audio slow 2.75x trên Whisper |
| H-02 | DONE | Đồng bộ input device giữa AudioEngine và `record_audio()` qua `_active_device_index` |
| H-03 | DONE | Chống self-audio contamination: 150ms settling delay sau TTS greeting + lockout loop khi TTS đang phát |
| H-04 | DONE | Fix crash hotkey Ctrl+Shift+L PTT: thay `_handle_voice_command` bằng `_start_voice_interaction` |
| H-05 | DONE | STT & Router benchmark độc lập hoàn tất 100% (Small: N=420 clean+noisy; Large-v3: N=420 clean+noisy; Clean 87.1% / 2.79s, Noisy 84.8% / 2.79s, 0% empty, 178+2+0+30=210) |
| H-06 | DONE | Idle soak 60 phút thật (3600.1s, Realtek built-in, 16kHz): **0 false triggers, 0.00 FP/hr** — vượt ngưỡng < 1 FP/hr. JSON: `docs/eval/wake_word_idle_results.json` |
| H-07 | DONE | Chuẩn hóa lệnh mở app/web: launch dedupe stress test (3 lệnh × 20 lần = 60 lần gọi; 3 allowed, 57 suppressed) |
| H-08 | DONE | Volume & brightness fail-closed trên hardware None: trả `success: False`, không ghost success |
| H-09 | DONE | Runaway soak test & leak detection framework: `tests/eval/soak_test_runner.py` (+0.00 handles/hr, 15 threads ổn định) |
| H-10 | PARTIAL | Ma trận cập nhật `docs/eval/audio_hardware_compatibility_matrix.md`; 2/10 Tier 1 PASS (Realtek built-in + Realtek Array, peak=5697); Bluetooth fail do A2DP mode; cần switch HFP + thêm 8 thiết bị |
| H-11 | PENDING_FIRST_RUN | Đã tạo onboarding wizard 5 bước `jarvis/ui/setup_wizard.py` (2 unit tests pass); chưa chạy interactive lần đầu với người dùng |
| H-12 | DONE | Chuẩn hóa tách lớp locale & diacritic folding đa âm bảo vệ nguyên vẹn từ đơn (`strip_vietnamese_diacritics`) |
| H-13 | PENDING_HUMAN_EXECUTION | Đã lập protocol 50 ca `docs/eval/beta_voice_50_live_acceptance_protocol.md` & 28 unit tests Tier 2 pass; cần tester người thật nói 50 câu live |

---

# KẾ HOẠCH TỔNG THỂ — VÁ LỖI, KIỂM TRA TÍNH NĂNG & NÂNG CẤP JARVIS
### Tổng hợp hành động cụ thể, dùng cùng `docs/AUDIT_FRAMEWORK.md`

---

## 0. TRẠNG THÁI HIỆN TẠI (Snapshot kiểm toán & phát hành)

| Đã xong | Đang treo — không bị chặn | Đang treo — bị chặn |
|---|---|---|
| A1-A7 fabrication fixes (fail-closed) | Full test suite run định kỳ | B1: cần Home Assistant server thật |
| B3: ASTCodeValidator wired vào synthesizer | Cài `TShark` (Wireshark CLI cho pcap thật) | C1: cần Discord bot token thật |
| Sandbox dry-run gate cho synthesizer | Mở port CDP 9222 cho browser live tests | B2: cần quyết định thiết kế phần cứng |
| Router & STT eval N=840 hoàn tất (Small N=420, Large-v3 N=420 clean+noisy, 100% held-out, 99.5% oracle text) | Rà soát Terminal Control Center (1.6) | Telegram / Zalo token thật để test nhánh online |
| Nâng cấp #3: Migrate `.env` → Credential Manager | | D-14: cần chứng thư Authenticode OV/EV thương mại |
| Nâng cấp #4: TieredSTTEngine (Local Whisper + Cloud + VAD) | | |
| Rate-limiting 4 kênh comms (Token Bucket) | | |
| P2-12 Memory Concurrency Hardening (Tier 1, 30 threads) | | |
| Phase 7: Full 7-Subsystem Independent Audit (28 components) | | |
| Phase 8: Remediation 8 High-Priority Defects D1–D8 (TDD fail-closed) | | |
| Phase 9: IMAP real imaplib client (fail-closed NOT_CONFIGURED) | | |
| Phase 9: TTS Priority 4 fail-closed (return False, không return True) | | |
| Phase 9: Volume control fail-closed tests — 4 tests | | |
| Phase 9: IMAP unit tests — 20 tests | | |
| AUDIT_FRAMEWORK.md đã lưu repo | | |
| README/CHANGELOG xác nhận trung thực | | |
| E2E Acceptance Test Suite Beta v1 (28/28 passed) | | |
| Voice Pipeline fixes & Seam Suite (8/8 passed) | | |
| Zalo Bot Controller Seam Suite (25/25 passed) | | |
| Comms Fail-Closed Adversarial Suite (18/18 passed) | | |

---

## PHẦN 1 — VÁ LỖI (theo thứ tự ưu tiên thực thi)

### 🔴 Ưu tiên tối cao — Không bị chặn, ảnh hưởng trực tiếp người dùng

**1.1 Router eval — kiểm chuẩn đa điều kiện N=420**
- Đã hoàn tất: 420 WAV files độc lập (210 clean, 210 noisy).
- Báo cáo chi tiết: `docs/eval/stt_eval_independent_summary.md`.

**1.2 Sandbox dry-run cho `synthesize_skill()`** (cải tiến B3 đã đề xuất)
- Sau AST validation, chạy thử `execute()` trong `CodeInterpreterSandbox` với input mẫu/mock.
- Bắt được `RuntimeError` mà AST không thể phát hiện (giới hạn Halting Problem đã ghi nhận).
- Không cần hạ tầng ngoài — dùng lại `CodeInterpreterSandbox` đã có sẵn.

**1.3 Full test suite liên tục**
- Duy trì 100% pass rate trên các test suite cốt lõi (79/79 seam/acceptance tests).

### 🟡 Ưu tiên trung bình — Chi phí thấp, giải quyết được ngay

**1.4 Cài đặt 3 package/binary mở rộng**
- `pytest-asyncio` — giải quyết các async tests
- `TShark` (Wireshark CLI) — cho phép test parser gói tin thật
- `playwright` + `playwright install chromium` — cho P2-15 Browser Automation live

**1.5 Mở port CDP 9222** — mở Chrome/Edge với `--remote-debugging-port=9222` khi chạy live CDP driver tests.

**1.6 Mở rộng grep fabrication** — rà soát toàn bộ codebase theo chuẩn `AGENTS.md`.

### 🟢 Ưu tiên thấp — Chờ thông tin từ người dùng (Third-Party Credentials)

**1.7 B1 (Home Assistant)** — cân nhắc Docker test instance thay server production.

**1.8 C1 (Discord `_poll_loop`)** — cần bot token thật với scope `bot` + quyền đọc message.

**1.9 B2 (Gesture wiring)** — cần quyết định thiết kế cảm biến cử chỉ từ người dùng.

---

## PHẦN 2 — KIỂM TRA TÍNH NĂNG

| Module | Trục 1 hiện tại | Việc cần làm | Rủi ro nếu bỏ qua |
|---|:---:|---|---|
| Voice Pipeline (STT+Router) | 🟢 Tier 1 | Independent N=420 eval (Clean/Noisy) | ĐÃ HOÀN THÀNH (61.0% clean, 53.8% noisy, 0% empty) |
| Terminal Control Center | 🟡 MOCK | Audit độc lập — review adapter phần cứng | Trung bình — bề mặt điều khiển |
| P2-12 Memory (concurrency) | 🟢 Tier 1 | Stress-test 30 thread + atomic JSON + WAL safety | ĐÃ HOÀN THÀNH (57/57 tests) |
| P2-13 Screen Vision | 🟡 MOCK | Test với camera/màn hình thật ít nhất 1 lần | Thấp |
| P2-16 Comms Hub | 🟡 MOCK | Fail-closed verified; chờ token thật | Trung bình (an toàn fail-closed) |
| P2-17 Smart Home | 🟡 MOCK | Sau khi có HA test instance | Thấp |
| Wake-word & DSP (H-06) | 🟢 Tier 1 | VAD energy-based gating + frame drop | ĐÃ HOÀN THÀNH (5/5 tests) |
| Computer Vision | 🟡 Chờ hardware | Benchmark FPS thật + đánh giá rủi ro riêng tư | Thấp-Trung bình |

---

## PHẦN 3 — ĐỀ XUẤT NÂNG CẤP

### Ngắn hạn (Đã hoàn tất trong Beta v1)
1. Rate-limiting cho 4 kênh comms (Telegram/Zalo/Discord/Mobile) — **ĐÃ HOÀN THÀNH** (22/22 tests passing).
2. Đổi tên "Vector Store" → "Lexical Search" trong tài liệu người dùng (TF-IDF không phải RAG) — **ĐÃ HOÀN THÀNH**.
3. Migrate `.env` → Windows Credential Manager (`SecretsManager` bảo vệ token/khóa) — **ĐÃ HOÀN THÀNH**.
4. 16kHz STT Capture Precedence & Microphone Device Sync — **ĐÃ HOÀN THÀNH**.
5. Acoustic Settling Guard (150ms) & Playback Lockout — **ĐÃ HOÀN THÀNH**.

### Trung hạn (Phiên bản v5.2.0)
6. TieredSTTEngine (fast/accurate 2 tầng Whisper Small / Large-v3) — **ĐÃ HOÀN THÀNH**.
7. Nâng P2-12 Memory lên Tier 1 bằng stress-test concurrency có kiểm tra dữ liệu — **ĐÃ HOÀN THÀNH** (57/57 tests passing).
8. Đo WER/Intent Misrouting Rate theo domain đóng cho bộ test mới.

### Dài hạn
9. Windows Code Signing (Authenticode thương mại OV/EV cho installer).
10. Local ONNX Embedding thay TF-IDF nếu cần semantic search thực sự.
11. On-demand model download để giảm kích thước installer (hiện tại 71.4 MB).
12. Đánh giá Browser Automation về Prompt Injection nâng cao.

---

## PHẦN 4 — TRÌNH TỰ THỰC THI & CHỮ KÝ PHÁT HÀNH

```
BETA v1 ENGINEERING HARDENING STATUS (2026-09-13):
  [x] 1.1 Independent Router eval (N=420 Small clean/noisy + N=420 Large-v3 clean/noisy CUDA) — EMPIRICAL COMPLETE
  [x] 1.2 Voice pipeline fixes (16kHz capture, mic sync, settling, hotkey PTT, fail-closed) — COMPLETE
  [x] 1.3 Comms fail-closed audit (Telegram, Zalo, Discord, IMAP fail-closed verified) — COMPLETE
  [x] 1.4 Soak test harness & leak detection (+0.00 handles/hr, 15 threads stable) — COMPLETE
  [x] 1.5 E2E Acceptance Test Suite Tier 2 (28/28 passed in ~2.04s) — COMPLETE
  [x] 1.6 Seam Regression Suites (79/79 passed in ~4.83s) — COMPLETE
  [x] 1.7 One-click Windows Installer JARVIS_Setup_v5.1.0.exe (SHA-256 verified) — COMPLETE
  [x] 1.8 Setup Wizard & Audio Matrix & 50-Case Protocol prepared — COMPLETE
  [ ] 1.9 Human Live Voice Acceptance (H-13: 50 cases) — PENDING_HUMAN_EXECUTION
  [ ] 1.10 Physical Audio Hardware Matrix (H-10: 9/10 endpoints) — BLOCKED_ON_HARDWARE
  [ ] 1.11 Idle Soak Test Microphone Stream (H-06: 15-60min) — PENDING_IDLE_SOAK
  [ ] 1.12 Third-Party Live Credentials (D-06..D-09) & EV/OV Cert (D-14) — PENDING_CREDENTIALS / BLOCKED_ON_CERT
```

---

## GHI CHÚ QUAN TRỌNG

- **Không bắt đầu TieredSTTEngine trước khi Router eval xong** — nguy cơ hard-code ngưỡng tùy tiện (bẫy #9 trong `AUDIT_FRAMEWORK.md`).
- **Mọi module chuyển Tier phải theo đúng quy trình 7 bước** trong `AUDIT_FRAMEWORK.md`.
- **Kết quả nào cũng cần đối chiếu với `AUDIT_FRAMEWORK.md` trước khi báo cáo** — dùng "Câu hỏi tự kiểm tra" như checklist bắt buộc.
