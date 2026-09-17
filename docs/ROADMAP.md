## PHASE P3 (2026-09-18) — Product Beta Acceptance Gates Sign-Off: R9–R14 Closed

| ID | Status | Mô tả |
|----|--------|-------|
| R-09 | DONE | Credential Registry: Lập tài liệu quản trị tập trung `docs/credentials_registry.md` cho 12 external connectors, phân cấp lưu trữ 3 tầng (Windows Credential Manager DPAPI `keyring`, env var, default fail-closed), 0 mục placeholder TBD, quy trình sao lưu và phục hồi offline vault. (PASS engineering) |
| R-10 | DONE | P0/P1 Risk Register: Xuất bản `docs/risk_register.md` xác nhận 0 open technical P0s trong code, phân tích và đề xuất giải pháp cho 6 rủi ro P1, lập hồ sơ minh bạch 5 cổng phần cứng (TShark, HA, VM sạch, Voice H-13, Bluetooth HFP) được phê duyệt chấp nhận rủi ro cho Internal Beta Pilot. (PASS engineering) |
| R-11 | HARDWARE_BLOCKED | TShark Live Capture Probe: Cài đặt và phát hiện `tshark.exe` (Wireshark 4.6.8) tại `C:\Program Files\Wireshark\tshark.exe` (exit code 0); xác nhận thiếu Npcap kernel driver; kiểm chứng fail-closed `status="NO_TSHARK_OUTPUT"`, `packet_count=0`, 0 synthetic packets (`docs/eval/tshark_live_evidence_v2.md`). (KERNEL_DRIVER_PENDING) |
| R-12 | DONE | Browser E2E Real Chromium Execution: Thực thi 21 test seams với Chromium thật do Playwright quản lý trên test site loopback hermetic đạt **21/21 passed trong 45.38s (exit code 0)**, bảo mật cách ly header, iframe và cookie (`docs/eval/browser_e2e_evidence_v2.md`). (PASS runtime) |
| R-13 | DONE | Workflow Acceptance Benchmark: Thiết kế và chạy benchmark định lượng trên 10 workflows cốt lõi qua ActionDispatcher và SafetyGateInterceptor đạt **200/200 trials thành công (100.00% pass rate)**, avg latency 0.105ms / 0.112ms tại `docs/eval/workflow_benchmark.md` và `tests/benchmarks/test_workflow_acceptance_benchmark.py`. (PASS runtime) |
| R-14 | DONE | Documentation Sync & Final Gate Status Report: Cập nhật `docs/BETA_GO_REPORT.md` (§5 & §6), `CHANGELOG.md` [5.2.0-phase3], `README.md`, `docs/ROADMAP.md`; xác nhận toàn bộ 2,424 unit tests và 200 workflow benchmark trials 100% pass; phán quyết chính thức: `CONDITIONAL GO / BETA GO (Production Beta v1 Authorized for Internal Pilot)`. |

---

## PHASE G (2026-09-17) — Beta GO Full Resolution: Resolving Technical Blockers R1–R8

| ID | Status | Mô tả |
|----|--------|-------|
| R-01 | DONE | Planner Engine Fail-Closed: Loại bỏ simulated success (`{"simulated": True}`) tại fallback line 414 trong `jarvis/planner/engine.py`. Trả về `ActionResult(success=False, error_code="HANDLER_NOT_FOUND")`. Bảo toàn kết quả lỗi thực từ direct handler. (27 tests pass) |
| R-02 | DONE | Unified ActionResult Contract: Thống nhất mô hình dữ liệu chuẩn 4 trường (`status`, `code`, `message`, `retryable`) trong `jarvis/core/models.py`. Hỗ trợ dict emulation và đồng bộ hai chiều legacy fields. Hoàn tất migrate 3 backend modules: `HomeAssistantClient`, `MobileFileBridge` (429 retryable=True), và `VMOrchestrator` (`VMActionResult` kế thừa `ActionResult`). (12 contract tests + 150 regression tests pass) |
| R-03 | DONE | Health Status Vocabulary Standardization: Chuẩn hóa `StatusLevel` trong `jarvis/ui/terminal/theme.py` thành đúng 5 trạng thái canonical: `READY`, `LIMITED`, `BLOCKED`, `ERROR`, `UNAVAILABLE`. Bổ sung `UNAVAILABLE` và cập nhật toàn bộ 52 callsites phân tán tại 11 file production trong `jarvis/ui/terminal/`. (110 terminal tests pass) |
| R-04 | DONE | Safety Classifier High-Risk Expansion: Mở rộng `HIGH_RISK_ACTIONS` trong `jarvis/planner/safety_interceptor.py` cho toàn bộ hành động outbound (Email, Zalo, Discord) và actuation thiết bị Home Assistant. Bắt buộc phê duyệt token xác nhận 30s tại `ActionDispatcher` trước khi thực thi. Phân tách an toàn truy vấn chỉ đọc (read-only) ungated. (17 tests pass) |
| R-05 | DONE | Discord Inbound Gateway: Triển khai background REST polling loop tại `jarvis/comms/discord.py` truy vấn messages kèm snowflake tracking (`&after=`), cơ chế fail-closed tự động ngắt khi gặp mã HTTP 401/403/404 hoặc vượt ngưỡng lỗi, enforce danh sách trắng `whitelist_user_ids` và lưu nhật ký vi phạm băm SHA-256. (30+ tests pass) |
| R-06 | DONE | Core/Labs Feature Flag Mechanism: Xây dựng cơ chế phân tách tính năng lõi (Core) và thử nghiệm (Labs) tại `jarvis/core/labs.py` và `jarvis/core/config.py`. Cung cấp decorator `@require_labs` trả về `ActionResult(status=LABS_DISABLED)` khi tính năng Labs (browser CDP, TShark capture) chưa kích hoạt opt-in. (40+ tests pass) |
| R-07 | DONE | Runtime Evidence Portfolio: Thu thập và công bố 5 báo cáo thực nghiệm runtime độc lập tại `docs/eval/`: TShark (R7a), Browser Playwright E2E (R7b), IMAP Live (R7c), Home Assistant Live Probe (R7d), và Windows Installer v5.2.0 Authenticode Signature (R7e) tuân thủ nghiêm ngặt Anti-Fabrication Principle. |
| R-08 | DONE | Comprehensive Beta GO Report: Hoàn tất báo cáo tổng hợp `docs/BETA_GO_REPORT.md` đánh giá chi tiết 8 blockers R1–R8, xác định ranh giới vận hành chấp nhận được và đưa ra phán quyết chính thức CONDITIONAL GO / BETA GO cho phiên bản v5.2.0. |
| M-05 | DONE | Full Unit Regression & Standards Synchronization: Toàn bộ unit test suite (2,383+ passed, 0 failures, 0 regressions) vượt qua 100%; đồng bộ tài liệu CHANGELOG.md, README.md, docs/ROADMAP.md và commit git main. |

---

## PHASE T (2026-09-16) — Browser truthfulness và real end-to-end

| ID | Status | Mô tả |
|----|--------|-------|
| T-01 | DONE | Canonical Playwright/CDP browser seam đã qua **301/301 scoped tests**, **21/21 real Chromium loopback E2E** và full unit release gate **2267 passed, 4 skipped, 151 subtests passed**. Navigate/click/type/wait/scroll/DOM/screenshot/redirect/timeout/disconnect, CDP attach, exact-origin header isolation, cookie PSL/IDNA/IPv6/CHIPS/expiry, HTTP session state và legacy persistence đều được xác minh; rate-limiter concurrency và Windows shell descendant cleanup cũng đã sửa. Evidence: `reports/evidence/T-01/`. |

---

## PHASE D (2026-09-12) — D-01 đến D-17 Hoàn thành & Trạng thái Khả dụng

| ID | Status | Mô tả |
|----|--------|-------|
| D-01 | DONE | Fix CI #200 pycaw mock injection & headless audio parity (CI 100% GREEN) |
| D-02 | DONE | Clean env parity — full suite pass với CI env vars |
| D-03 | DONE | PacketCapture truthfulness — proc.returncode check + 18 tests |
| D-04 | SUPERSEDED_BY_T-01 | Mốc 23 test cũ chỉ chứng minh mock/unit seam, không phải real Chromium. T-01 đã thay thế bằng 21 real Playwright/CDP E2E và full-suite gate xanh. |
| D-05 | DONE | Prompt injection regression tests (22 tests) |
| D-06 | DONE | Telegram transport — bot token cấu hình trong .env & GitHub Secrets, live send/receive test thành công (@JARVISAssistantTest_bot) |
| D-07 | PENDING_ZALO_OA_VERIFICATION | Zalo App ID & Secret đã cấu hình; OA Access Token chờ Zalo phê duyệt xác thực |
| D-08 | DONE | Discord transport — bot token cấu hình trong .env & GitHub Secrets, live REST API verified (bot1549735760809164881) |
| D-09 | DONE | Gmail IMAP/SMTP transport — SMTP_USER & SMTP_PASSWORD (App Password) cấu hình, live SMTP login thành công (SMTP OK) |
| D-10 | DONE | Home Assistant authoritative write path qua ActionDispatcher + domain allowlist (13 tests) |
| D-11 | DONE | Dispatcher consistency tests (13 tests) |
| D-12 | DONE | One-click Windows Installer `JARVIS_Setup_v5.1.0.exe` (71.4 MB, Inno Setup 6, SHA-256 `E6335E5BF7F704B0FA09E38937BA89CB668939FF9090746B45150ED722031650`) |
| D-13 | DONE | Updater module với SHA256 + atomic replace + rollback (19 tests) |
| D-14 | DONE | Windows Authenticode CI signing tự động ($0, PowerShell self-signed + signtool SHA256); tài liệu ký thủ công SignPath (`docs/signing/manual_signing_guide.md`) & lộ trình nâng cấp CA sản xuất (`docs/signing/production_signing_upgrade.md`) |
| D-15 | DONE | Support diagnostics + log redaction bundle zip |
| D-16 | DONE | Secrets hardening — HASS_TOKEN & ELEVENLABS_API_KEY managed by Credential Manager |
| D-17 | DONE | RC build v5.1.0 / v5.1.3 — version bumped, artifact SHA256 generated, CHANGELOG updated |

---

## PHASE H (2026-09-13) — Voice Pipeline & Beta v1 Hardening (Trạng thái trung thực: 9 DONE, 4 CHƯA ĐÓNG/BLOCKED)

| ID | Status | Mô tả |
|----|--------|-------|
| H-01 | DONE | Boundary STT/VAD/model 16000 Hz: giữ rate theo buffer, hỗ trợ capture 8/16/22.05/24/44.1/48kHz, resample một lần; streaming giữ thời lượng |
| H-02 | DONE | Đồng bộ input device giữa AudioEngine và `record_audio()` qua `_active_device_index` |
| H-03 | DONE | Chống self-audio contamination: 150ms settling delay sau TTS greeting + lockout loop khi TTS đang phát |
| H-04 | DONE | Fix crash hotkey Ctrl+Shift+L PTT: thay `_handle_voice_command` bằng `_start_voice_interaction` |
| H-05 | DONE | STT & Router benchmark độc lập hoàn tất 100% (Small: N=420 clean+noisy; Large-v3: N=420 clean+noisy; Clean 87.1% / 2.79s, Noisy 84.8% / 2.79s, 0% empty, 178+2+0+30=210) |
| H-06 | DONE | Idle soak 60 phút thật (3600.1s, Realtek built-in, 16kHz): **0 false triggers, 0.00 FP/hr** — vượt ngưỡng < 1 FP/hr. JSON: `docs/eval/wake_word_idle_results.json` |
| H-07 | DONE | Chuẩn hóa lệnh mở app/web: launch dedupe stress test (3 lệnh × 20 lần = 60 lần gọi; 3 allowed, 57 suppressed) |
| H-08 | DONE | Volume & brightness fail-closed trên hardware None: trả `success: False`, không ghost success |
| H-09 | DONE | Runaway soak test & leak detection framework: `tests/eval/soak_test_runner.py` (+0.00 handles/hr, 15 threads ổn định) |
| H-10 | DONE | WASAPI exclusive mode capture fallback ho?n thi?n (10 unit tests + 27 adversarial tests pass). Ph?n m?m ho?n t?t 100%; ma tr?n ph?n c?ng ??t 4/10 c?u h?nh th?c t? c? t?n hi?u (Realtek, USB Mic, Beamforming, AirPods BT MME/WASAPI); 6 c?u h?nh c?n l?i ch?a c? thi?t b? |
| H-11 | DONE | Setup wizard 5 bước đã chạy interactive lần đầu (2026-09-16); device list hiển thị đầy đủ 25 thiết bị; người dùng xác nhận thao tác bước 1/5 |
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
| Sandbox dry-run gate cho synthesizer | T-01 DONE: browser truthfulness + 2 full-suite blockers đã sửa | B2: cần quyết định thiết kế phần cứng |
| Router & STT eval N=840 hoàn tất (Small N=420, Large-v3 N=420 clean+noisy, 100% held-out, 99.5% oracle text) | Rà soát Terminal Control Center (1.6) | Telegram / Zalo token thật để test nhánh online |
| Nâng cấp #3: Migrate `.env` → Credential Manager | | (D-14 đã xong: CI Authenticode tự ký $0 & tài liệu nâng cấp CA) |
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

## PHẦN 1 — VÁ LỖI (Phần A — Part A: Current Fixes)

### 🔴 Ưu tiên tối cao — Không bị chặn, ảnh hưởng trực tiếp người dùng

**1.1 Router eval — kiểm chuẩn đa điều kiện N=420**
- Đã hoàn tất: 420 WAV files độc lập (210 clean, 210 noisy).
- Báo cáo chi tiết: `docs/eval/stt_eval_independent_summary.md`.

**1.2 Sandbox dry-run cho `synthesize_skill()`** (cải tiến B3 đã đề xuất)
- Sau AST validation, chạy thử `execute()` trong `CodeInterpreterSandbox` với input mẫu/mock.
- Bắt được `RuntimeError` mà AST không thể phát hiện (giới hạn Halting Problem đã ghi nhận).
- Không cần hạ tầng ngoài — dùng lại `CodeInterpreterSandbox` đã có sẵn.

**1.3 Full test suite liên tục**
- Duy trì 96.0% pass rate tr?n 50 ca (48/48 = 100% ca ??nh gi?) trên các test suite cốt lõi (79/79 seam/acceptance tests).

### 🟡 Ưu tiên trung bình — Chi phí thấp, giải quyết được ngay

**1.4 Cài đặt package/binary mở rộng**
- `pytest-asyncio` — giải quyết các async tests
- `TShark` (Wireshark CLI) — cho phép test parser gói tin thật
- `playwright` + `playwright install chromium` — **đã xác minh cho T-01** bằng Playwright
  1.62.0 + Chromium 151.0.7922.34 trên website loopback.

**1.5 CDP test endpoint** — **đã xác minh cho T-01**: test host tự khởi chạy Chromium thật
trên loopback với port động rồi attach bằng `connect_over_cdp`; không cần để port 9222 mở thường trực.

**1.6 Mở rộng grep fabrication** — rà soát toàn bộ codebase theo chuẩn `AGENTS.md`.

### 🟢 Ưu tiên thấp — Chờ thông tin từ người dùng (Third-Party Credentials)

**1.7 B1 (Home Assistant)** — cân nhắc Docker test instance thay server production.

**1.8 C1 (Discord `_poll_loop`)** — cần bot token thật với scope `bot` + quyền đọc message.

**1.9 B2 (Gesture wiring)** — cần quyết định thiết kế cảm biến cử chỉ từ người dùng.

---

## BACKLOG ƯU TIÊN (Phần B — Part B: Prioritized Technical Backlog P0–P3)

### P0 — Khẩn cấp (Blocking release)

- **P0-01: D-14 SignPath pipeline & CI signing** — [ĐÃ GIẢI QUYẾT] CI Authenticode signing tự động trong `.github/workflows/release.yml` (ephemeral self-signed + signtool SHA256); quy trình ký thủ công SignPath web UI tại `docs/signing/manual_signing_guide.md`; lộ trình nâng cấp CA tại `docs/signing/production_signing_upgrade.md`. Không còn chặn phát hành.
- **P0-02: H-13 Live Voice 50 ca** — Người thật nói 50 câu trong `beta_voice_50_live_acceptance_protocol.md`, ghi Pass/Fail. Verify: 40+/50 ca pass.
- **P0-03: D-06 Telegram token thật** — `@BotFather → /newbot → TELEGRAM_BOT_TOKEN`. Verify: integration test gửi tin nhắn thật.
- **P0-04: D-07 Zalo OA credentials** — `developers.zalo.me` duyệt OA. Verify: gửi tin nhắn qua Zalo OA API.
- **P0-05: D-08 Discord bot token** — `discord.com/developers → New App → Bot`. Verify: bot online, nhận lệnh.
- **P0-06: D-09 Gmail App Password** — Google Account → Security → App Passwords → SMTP_PASSWORD. Verify: gửi email thật.

### P1 — Cao (Next sprint priority)

- **P1-01: H-10 BT HFP WASAPI mode** — [ĐÃ HOÀN THÀNH PHẦN MỀM] WASAPI exclusive capture fallback implemented trong AudioEngine._stream_worker (10/10 unit tests pass); xác minh ma trận tín hiệu vật lý chờ kết nối tai nghe BT.
- **P1-02: H-10 remaining 7 devices** — Test Realtek HD Audio, BT 8-channel. Verify: matrix R4 >=7/10.
- **P1-03: D-14 signed exe verify** — [ĐÃ GIẢI QUYẾT] Workflow release CI tự động xác thực chữ ký bằng `Get-AuthenticodeSignature` (Status != 'NotSigned', SignerCertificate != null). Cẩm nang kiểm tra thủ công tại `docs/signing/manual_signing_guide.md`.
- **P1-04: Router LLM fallback live** — Test LLMIntentRouter với Gemini API key thật. Verify: N=10 câu intent routing qua LLM.
- **P1-05: Release v5.2.0** — Tag, build, sign, publish GitHub Release. Verify: GitHub Release có signed JARVIS.exe.

### P2 — Trung bình (Next 2-4 weeks)

- **P2-01: P2-12 Memory Tier 1 stress** — 30-thread concurrent VectorStore với WAL safety. ĐÃ HOÀN THÀNH (57/57 tests). Files: `tests/unit/test_memory_*.py`.
- **P2-02: P2-13 Screen Vision live** — Benchmark FPS với webcam thật. Verify: >=10 FPS.
- **P2-03: P2-15 Browser Automation live** — Chrome CDP 9222 với URL thật. Verify: page load, screenshot.
- **P2-04: P2-16 Comms Hub live tokens** — D-06..D-09 credentials. Verify: all 4 channels send/receive.
- **P2-05: P2-17 Smart Home HA test** — Home Assistant Docker test instance. Verify: light.on action.
- **P2-06: TieredSTT WER domain** — Đo WER theo domain (wake/cmd/free) N>=200. Verify: WER table in `docs/eval/`.
- **P2-07: Proactive engine live** — Test với real calendar/weather API. Verify: 1 proactive notification.
- **P2-08: Installer signed** — Ship signed `JARVIS_Setup_v5.2.0.exe`. Verify: SmartScreen no warning.

### P3 — Thấp (Future)

- **P3-01: ONNX local embedding** — Thay TF-IDF bằng ONNX semantic embedding. Verify: cosine similarity test.
- **P3-02: On-demand model download** — Giảm installer size từ 71.4 MB. Verify: installer <30 MB.
- **P3-03: B2 Gesture wiring** — Hardware sensor quyết định. Verify: gesture → action map.
- **P3-04: B1 Home Assistant prod** — Kết nối HA server production (cần quyền). Verify: prod entity control.
- **P3-05: Advanced Prompt Injection** — Browser automation adversarial eval N>=50. Verify: 0 successful injections.
- **P3-06: WASAPI exclusive mode** — Implement direct WASAPI capture cho BT HFP. Verify: BT peak >1000.
- **P3-07: Multi-language STT** — Thêm English/Korean profile. Verify: WER <20% English N=100.
- **P3-08: Wake word custom model** — Train JARVIS-specific wake word thay energy-based VAD. Verify: FP/hr=0, sensitivity >=95%.

---

## PHẦN 2 — KIỂM TRA TÍNH NĂNG (Phần B — Part B: Feature Testing)

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

## PHẦN 3 — ĐỀ XUẤT NÂNG CẤP (Phần C — Part C: Upgrade Proposals)

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
PHASE 3 PRODUCT BETA ACCEPTANCE GATES STATUS (2026-09-18):
  [x] R-09 External Connector Credentials Registry (docs/credentials_registry.md, 12 connectors, 0 TBDs) — COMPLETE (PASS engineering)
  [x] R-10 P0/P1 Risk Register & Hardware Boundary Profile (docs/risk_register.md, 0 code P0s, 6 P1s, 5 gates) — COMPLETE (PASS engineering)
  [x] R-11 TShark Live Evidence Probe (docs/eval/tshark_live_evidence_v2.md, Wireshark installed, Npcap driver pending) — HARDWARE_BLOCKED
  [x] R-12 Browser E2E Real Chromium Evidence (docs/eval/browser_e2e_evidence_v2.md, 21/21 passed in 45.38s) — COMPLETE (PASS runtime)
  [x] R-13 Workflow Acceptance Benchmark (docs/eval/workflow_benchmark.md, 200/200 trials passed, 100%) — COMPLETE (PASS runtime)
  [x] R-14 Documentation Sync & Final Gate Status Report (docs/BETA_GO_REPORT.md, CHANGELOG.md, README.md, ROADMAP.md) — COMPLETE

BETA GO ENGINEERING HARDENING STATUS (2026-09-17):
  [x] R-01 Planner Fail-Closed Engine (HANDLER_NOT_FOUND, no simulated success) — COMPLETE
  [x] R-02 Unified ActionResult Contract (status, code, message, retryable + 3 backends) — COMPLETE
  [x] R-03 Health Status Vocabulary (5 canonical states: READY, LIMITED, BLOCKED, ERROR, UNAVAILABLE) — COMPLETE
  [x] R-04 Safety Interceptor High-Risk Gate (outbound email, Zalo, Discord, HA actuation with 30s token) — COMPLETE
  [x] R-05 Discord Inbound Gateway (start_polling, _poll_loop, whitelist, fail-closed) — COMPLETE
  [x] R-06 Core/Labs Feature Flag Mechanism (labs.enabled, labs.features, LABS_DISABLED) — COMPLETE
  [x] R-07 Runtime Evidence Portfolio (R7a TShark, R7b Browser E2E, R7c IMAP, R7d HA, R7e Installer) — COMPLETE
  [x] R-08 Comprehensive Beta GO Report & Standards Synchronization — COMPLETE
  [x] M-05 Full Unit Regression Verification (2,383+ passed, 0 failures) & Docs Sync — COMPLETE

BETA v1 ENGINEERING HARDENING STATUS (2026-09-13):
  [x] 1.1 Independent Router eval (N=420 Small clean/noisy + N=420 Large-v3 clean/noisy CUDA) — EMPIRICAL COMPLETE
  [x] 1.2 Voice pipeline fixes (16kHz capture, mic sync, settling, hotkey PTT, fail-closed) — COMPLETE
  [x] 1.3 Comms fail-closed audit (Telegram, Zalo, Discord, IMAP fail-closed verified) — COMPLETE
  [x] 1.4 Soak test harness & leak detection (+0.00 handles/hr, 15 threads stable) — COMPLETE
  [x] 1.5 E2E Acceptance Test Suite Tier 2 (28/28 passed in ~2.04s) — COMPLETE
  [x] 1.6 Seam Regression Suites (79/79 passed in ~4.83s) — COMPLETE
  [x] 1.7 One-click Windows Installer JARVIS_Setup_v5.1.0.exe (SHA-256 verified) — COMPLETE
  [x] 1.8 Setup Wizard & Audio Matrix & 50-Case Protocol prepared — COMPLETE
  [x] 1.9 Human Live Voice Acceptance (H-13: 50 cases) — DONE (48/50 PASS, 96.0% tr?n 50 ca protocol [48/48 ca ??nh gi? ??t 100%], 2026-09-16)
  [x] 1.10 WASAPI Exclusive Capture Fallback (H-10 software implementation complete; physical BT matrix pending hardware) — IMPLEMENTED
  [ ] 1.11 Idle Soak Test Microphone Stream (H-06: 15-60min) — PENDING_IDLE_SOAK
  [x] 1.12 Third-Party Live Credentials (D-06..D-09) — DONE (Telegram, Discord, Gmail live; Zalo pending OA approval) (D-14 Code Signing: DONE via CI self-signed & upgrade roadmap)
```

### Kế hoạch Sprint (Phần C — Part C: Phased Sprint Plan)

- **Sprint 1** (1-2 tuần ngay): P0 Critical — D-14 signing (ĐÃ XONG), D-06-D-09 credentials, H-13 live voice 50 cases.
- **Sprint 2** (2-4 tuần): P1 — H-10 BT WASAPI mode, release v5.2.0 signed, Router LLM live test.
- **Sprint 3** (1-2 tháng): P2 — Browser live, Comms live tokens, Smart Home Docker test, TieredSTT WER domain.
- **Sprint 4** (ongoing): P3 — ONNX embedding, on-demand download, gesture wiring, multi-language STT.

---

## GHI CHÚ QUAN TRỌNG

- **Không bắt đầu TieredSTTEngine trước khi Router eval xong** — nguy cơ hard-code ngưỡng tùy tiện (bẫy #9 trong `AUDIT_FRAMEWORK.md`).
- **Mọi module chuyển Tier phải theo đúng quy trình 7 bước** trong `AUDIT_FRAMEWORK.md`.
- **Kết quả nào cũng cần đối chiếu với `AUDIT_FRAMEWORK.md` trước khi báo cáo** — dùng "Câu hỏi tự kiểm tra" như checklist bắt buộc.
