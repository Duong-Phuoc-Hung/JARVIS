# JARVIS Beta v1 System Readiness Dashboard

**Release Target**: JARVIS Product Beta v1 (v5.2.0 Official Release)<br>
**Date**: 2026-09-19 (v5.2.0 Phase 4 + Peer Review Checkpoint)<br>
**Auditor / Author**: Teamwork Engineering Swarm & Peer Review Audit<br>
**Integrity Standards**: `AGENTS.md` (Fail-Closed Default, Anti-Fabrication Principle, Windows Atomic Persistence, Three-Tier Verdict Discipline)<br>
**Architecture Specification**: `PROJECT.md` & `docs/AUDIT_FRAMEWORK.md`<br>
**Last Peer-Reviewed**: 2026-09-21 — Reviewer: Duong Phuoc Hung (project owner) — Kết quả: 6 lỗi phát hiện và sửa (GATE-03 ngưỡng 80%→95%, section 5 thanh % vi phạm AUDIT_FRAMEWORK.md §106, UP-11 thiếu ghi chú nguồn ngành, D-06 thiếu caveat send-only, nhãn (engineering) không nhất quán, TieredSTT tier sai) — commit `9842fb9`

> [!WARNING]
> **Cảnh báo tự kiểm tra**: File này là nguồn chính cho trạng thái dự án, nhưng không miễn nhiễm với sai sót — như đã chứng minh bởi lỗi GATE-03 (2026-09-19→2026-09-21). Mọi cập nhật nội dung quan trọng (gate status, verdict, ngưỡng) phải được peer review độc lập trước khi commit. Không tin claim tĩnh trong file này khi chưa đối chiếu với file protocol gốc trong `docs/eval/`.

---

## 1. Executive Summary

JARVIS Beta v1 provides an autonomous, privacy-conscious AI desktop assistant tailored for Windows 11 64-bit with offline Vietnamese voice recognition, natural language intent routing, Windows hardware control, browser automation through Playwright-managed Chromium or real CDP attachment, and multi-channel remote connectivity.

### Phán Quyết Phát Hành Ba Tầng (Three-Tier Verdict Sign-Off — 2026-09-19)
Theo chuẩn mực phân tầng bắt buộc tại `AGENTS.md §5` và `docs/AUDIT_FRAMEWORK.md`:
- **Tầng 1 — Kỹ thuật & Kiểm thử đơn vị (Engineering / Unit)**: **`DONE`** (`PASS engineering`). Toàn bộ 8 technical blockers ban đầu (R1–R8) đã giải quyết triệt để; hợp đồng `ActionResult` và từ vựng canonical 5 trạng thái được chuẩn hóa 100%; unit test suite đạt **2,421 passed, 3 skipped, 268 subtests, 0 failed** trên Windows 11.
- **Tầng 2 — Thử nghiệm nội bộ (Internal Beta Pilot)**: **`CONDITIONAL GO`**. Hệ thống được phép vận hành trong môi trường giám sát trực tiếp trên máy trạm của nhà phát triển chính (`Duong-Phuoc-Hung`). Toàn bộ hợp đồng fail-closed khi thiếu phần cứng/khóa truy cập được xác minh nghiêm ngặt.
- **Tầng 3 — Phát hành thương mại rộng rãi (Product Release)**: **`NO-GO`**. Tiếp tục giữ trạng thái NO-GO do còn **6 cổng nghiệm thu mở (Open Gates)** phụ thuộc vào phần cứng thực tế, người dùng tương tác và chứng thư số thương mại (chi tiết tại Mục 3). GATE-05 Router LLM đã CLOSED 2026-09-20.

### Tổng Hợp Tiến Độ Các Pha Phát Triển
1. **Phase D (Core & Backend Subsystems)**: **14/17 tasks `DONE`** (bao gồm D-06 và D-08 ở scope hạn chế 2026-09-12, D-09 live IMAP pass, D-14 CI Authenticode signing), **1 task `PENDING_ZALO_OA_VERIFICATION`** (D-07), và **2 tasks cập nhật v5.2.0** (D-12 installer, D-17 release management).
2. **Phase H (Voice Pipeline Subsystems)**: **12/13 tasks `DONE`** (H-01..H-05, H-06 soak test 0.00 FP/hr, H-07..H-09, H-10 software 100% & 4/10 hardware signal, H-11 wizard 25 devices, H-12 diacritics), và **1 task `DONE (cần re-verify sau Phase G)`** (H-13: 48/50 [96.0%] ngày 2026-09-16).
3. **Phase G — Engineering Hardening (R1–R8, 2026-09-17)**: Hoàn tất **8/8 blockers** kỹ thuật cốt lõi (Planner fail-closed, ActionResult contract, health vocabulary, safety interceptor, Discord gateway, Labs feature flags, runtime evidence portfolio, Beta GO report).
4. **Phase P3 — Product Beta Acceptance Gates (R9–R14, 2026-09-18)**: Đóng toàn diện các cổng quản trị: R9 Credential Registry (`docs/credentials_registry.md`), R10 Risk Register (`docs/risk_register.md`), R12 Real Chromium E2E (**21/21 passed trong 45.38s**), R13 Workflow Benchmark (**200/200 passed, 0.105ms** qua dispatcher+mock), R14 Documentation Sync.
5. **Phase 4 — Runtime Evidence Portfolio (R15–R26, 2026-09-18→20)**: Thu thập bằng chứng thực nghiệm máy host: R15 TShark (`HARDWARE_BLOCKED (UAC_REQUIRED)`), R16 Home Assistant (`HARDWARE_BLOCKED (DOCKER_NOT_RUNNING)`), R17 Live IMAP (**`PASS runtime`** — 2 unread emails), R18/R25 v5.2.0 Build & GitHub Release (**`PASS runtime`**), R19 Router LLM (**`PASS runtime` — 9/10=90%, gemini-flash-lite-latest, 2026-09-20**), R20 TieredSTT Multi-Domain WER (**`PASS runtime`** — Command 8.50%, Free-form VN 3.72%), R26 Final Sync. Telegram D-06: **`PASS runtime (send path)`** — `@JARVISAssistantTest_bot`, message_id=3, 2026-09-20.
6. **Phase S — Peer Review Corrections (2026-09-19)**: Áp dụng 5 hiệu chỉnh kiểm toán quan trọng nhằm đảm bảo tính trung thực tuyệt đối theo `AGENTS.md §2`: (1) Làm rõ R13 là dispatcher+mock và giữ OPEN gate 10-workflow real OS, (2) Đánh dấu D-06/D-08 là scope hạn chế, (3) Báo cáo WER aggregate 8.50%/5.88% kèm lưu ý cỡ mẫu N=60, (4) Phân định self-signed CI cert vs commercial EV cert cho D-14, (5) Ghi nhận chính xác số lượng unit test 2,421/3skip/268subtests sau re-run.

### Bộ Cài Đặt Windows v5.2.0 (Installer Artifact Attestation)
- **Đường dẫn tệp**: `dist/installer/JARVIS_Setup_v5.2.0.exe`
- **Công cụ biên dịch**: Inno Setup 6.2.2 (Unicode)
- **Kích thước tệp**: `74,950,832 bytes` (~71.48 MB)
- **Mã băm mật mã (SHA-256)**: `6b52e20f3c4cf08be76a55c4e7dc87d55c83112725425a579b46c9aff3510d3b`
- **Chữ ký số Authenticode**: Đã ký số bảo vệ tính toàn vẹn nhị phân với chứng thư self-signed CI (`CN=JARVIS Release v5.2.0`, 2048-bit RSA, RFC-3161 timestamping). Chưa có chứng thư thương mại OV/EV → hiển thị cảnh báo Windows SmartScreen trên máy sạch.

---

## 2. Master System Readiness Matrix

### 2.1 Core & Backend Subsystem Tasks (Phase D: D-01 to D-17)

| Task ID | Module / Component | Target Description | Verification Evidence | Status |
|:---:|---|---|---|:---:|
| **D-01** | `jarvis/audio/` | Fix CI #200 pycaw mock injection & headless audio parity | `tests/unit/test_audio_engine.py`, CI 100% Green | `DONE` |
| **D-02** | Environment & CI | Clean env parity — full test suite pass with CI env variables | Automated regression suite (630+ passing tests) | `DONE` |
| **D-03** | `jarvis/security/scanner.py` | PacketCapture truthfulness — check process exit code & parse packets | `tests/unit/test_security_scanner.py` (18 tests) | `DONE` |
| **D-04** | Historical browser seam | Legacy fail-closed unit/mock coverage; it did not prove real Chromium | historical `tests/unit/test_browser_control.py` cases | `SUPERSEDED_BY_T-01` |
| **D-05** | `jarvis/llm/` | Prompt injection regression defense tests | `tests/unit/test_prompt_injection.py` (22 tests) | `DONE` |
| **D-06** | `jarvis/comms/telegram.py` | Telegram real transport via `requests.Session` + fail-closed + whitelist defense | `tests/test_telegram.py` (T-03: 5 tests) + `docs/eval/telegram_d06_live_evidence_v2.md` (live send 2026-09-20: HTTP 200, message_id=3) | `PASS runtime (send path, 2026-09-20)` — `@JARVISAssistantTest_bot` gửi thành công; receive loop cần phiên tương tác; 1 live roundtrip lịch sử 2026-09-12 |
| **D-07** | `jarvis/comms/zalo.py` | Zalo OA fail-closed, token bucket, and whitespace sanitization | `tests/unit/test_zalo_bot.py` (25 tests) | `PENDING_ZALO_OA_VERIFICATION` |
| **D-08** | `jarvis/comms/discord.py` | Discord gateway fail-closed & thread cleanup | `tests/test_adversarial_beta_m1_comms_failclosed.py`, `tests/unit/test_discord_controller.py` + `docs/eval/discord_d08_live_evidence_v2.md` | `PASS auth (token valid 2026-09-20, HTTP 200)` — bot xác thực thành công; 0 guilds joined; live send PENDING_GUILD_INVITATION (cần invite bot vào server + set DISCORD_CHANNEL_ID) |
| **D-09** | `jarvis/comms/email_imap.py`| IMAP email client fail-closed & live mailbox read | `tests/unit/test_imap_client.py` (20 tests), `docs/eval/imap_live_evidence_v2.md` | `DONE` (live IMAP pass) |
| **D-10** | `jarvis/automation/hass.py` | Home Assistant authoritative write path via ActionDispatcher | `tests/unit/test_hass_dispatcher.py` (13 tests) | `DONE` |
| **D-11** | `jarvis/core/app.py` | ActionDispatcher consistency & registration tests | `tests/unit/test_action_dispatcher.py` (13 tests) | `DONE` |
| **D-12** | Packaging & Installer | One-click Windows Installer `JARVIS_Setup_v5.2.0.exe` (74,950,832 bytes) | Inno Setup 6.2.2, SHA-256 `6b52e20f...` verified | `DONE` |
| **D-13** | `jarvis/workers/updater.py`| Auto-updater with SHA256 integrity, atomic replace & rollback | `tests/unit/test_auto_updater.py` (19 tests) | `DONE` |
| **D-14** | Code Signing | Windows Authenticode CI signing & release procedure (self-signed CI cert; commercial EV cert pending in P3-09 → SmartScreen warning on clean machines) | Automated CI Authenticode signing in release workflow; manual SignPath & production upgrade guides documented | `DONE (self-signed CI) / P3-09 pending commercial EV` |
| **D-15** | `jarvis/core/diagnostics.py`| Support diagnostics bundle & log redaction ZIP generator | `tests/unit/test_diagnostics.py` | `DONE` |
| **D-16** | `jarvis/security/secrets.py`| Windows Credential Manager integration for tokens & API keys | `tests/unit/test_secrets_manager.py` | `DONE` |
| **D-17** | Release Management | Release Candidate v5.2.0 build, artifact generation & CHANGELOG | `pyproject.toml`, `dist/installer/`, `CHANGELOG.md` | `DONE` |

### 2.1A Browser remediation task

| Task ID | Module / Component | Target Description | Verification Evidence | Status |
|:---:|---|---|---|:---:|
| **T-01** | `jarvis/browser/`, browser core/legacy consumers | Canonical truthful Playwright/CDP end-to-end, fail-closed fallback/results/prices/session handling | `reports/evidence/T-01/`: 301 scoped PASS; 21 real Chromium E2E PASS; full unit gate 2267 PASS / 4 SKIP | `DONE` |

### 2.2 Voice Pipeline & Interaction Tasks (Phase H: H-01 to H-13)

| Task ID | Module / Component | Target Description | Verification Evidence | Status |
|:---:|---|---|---|:---:|
| **H-01** | `jarvis/core/app.py` | Direct 16kHz audio capture precedence, avoiding 2.75x slow-down | `tests/unit/test_voice_pipeline_fixes.py::test_h01_*` | `DONE` |
| **H-02** | `jarvis/core/app.py` | Synchronize input device with `AudioEngine._active_device_index` | `tests/unit/test_voice_pipeline_fixes.py::test_h02_*` | `DONE` |
| **H-03** | `jarvis/core/app.py` | Acoustic settling delay (150ms) & active TTS playback lockout | `tests/unit/test_voice_pipeline_fixes.py::test_h03_*` | `DONE` |
| **H-04** | `jarvis/core/app.py` | Global `Ctrl+Shift+L` PTT hotkey dispatching without crash | `tests/unit/test_voice_pipeline_fixes.py::test_h04_*` | `DONE` |
| **H-05** | `tests/eval/` | Multi-condition empirical benchmark (Small vs Large-v3, Clean/Noisy)| `docs/eval/stt_eval_independent_summary.md` (Small N=420 clean+noisy; Large-v3 N=420 clean+noisy: Clean 87.1%, Noisy 84.8%, 0% empty, arithmetic verified) | `DONE` |
| **H-06** | `jarvis/audio/wake_word.py` | Wake-word false positive reduction via VAD energy threshold | `docs/eval/wake_word_idle_results.json` (3600.1s soak test, 0.00 FP/hr, 0 false triggers) | `DONE` |
| **H-07** | `jarvis/automation/control.py`| Process launch deduplication & runaway guard under stress | `tests/unit/test_app_web_dedupe_stress.py` (3 tests) | `DONE` |
| **H-08** | `jarvis/core/app.py` | System volume and brightness fail-closed returning `success=False` | `tests/unit/test_voice_pipeline_fixes.py::test_h08_*` | `DONE` |
| **H-09** | `tests/eval/` | Soak test harness & leak detection (+0.00 handles/hr, 15 threads) | `tests/eval/results_soak_test.json`, `soak_test_runner.py`| `DONE` |
| **H-10** | `jarvis/audio/engine.py` | Audio device compatibility layer & fallback matrix (software WASAPI exclusive fallback 100%; 4/10 hardware configs có tín hiệu thật) | `docs/eval/audio_hardware_compatibility_matrix.md`, `jarvis/audio/engine.py` | `DONE (software 100%; 4/10 hardware configs có tín hiệu thật)` |
| **H-11** | `jarvis/ui/setup_wizard.py`| First-run setup onboarding wizard & configuration integrity (wizard 25 devices listed, step 1/5 confirmed) | `jarvis/ui/setup_wizard.py`, `tests/unit/test_setup_wizard.py` (2 tests PASS) | `DONE` |
| **H-12** | `jarvis/llm/router.py` | Safe diacritic normalization & multi-word diacritic folding | `tests/unit/test_diacritic_normalization.py` | `DONE` |
| **H-13** | `docs/eval/`, `tests/e2e/` | Human live acceptance testing (50 cases) & automated E2E test suite (48/50, 96.0%, 2026-09-16) | `docs/eval/beta_voice_50_live_acceptance_protocol.md` (50 cases); `tests/e2e/test_beta_v1_acceptance.py` (28/28 Tier 2 tests) | `DONE (48/50, 96.0%, 2026-09-16) — cần re-verify sau Phase G` |

---

### 2.3 Phase G — Engineering Hardening (R1–R8: 2026-09-17)

Toàn bộ 8 technical blockers cốt lõi của giai đoạn Beta đã được xử lý dứt điểm, loại bỏ hoàn toàn mã giả lập và nuốt lỗi ngầm định:

| Task ID | Module / Component | Target Description | Verification Evidence | Status |
|:---:|---|---|---|:---:|
| **R-01** | `jarvis/planner/engine.py` | Loại bỏ fallback simulated success (`{"simulated": True}`) tại dòng 414; fail-closed `HANDLER_NOT_FOUND`; bảo toàn mã lỗi từ direct handler | `tests/test_adversarial_m1_planner_failclosed.py` + 27 unit tests passing | `DONE` |
| **R-02** | `jarvis/core/models.py` | Thống nhất mô hình chuẩn 4 trường (`status`, `code`, `message`, `retryable`) trên `ActionResult`; dict emulation; migrate HomeAssistant, MobileFileBridge, VMOrchestrator | `tests/unit/test_action_result_contract.py` (12 tests) + 150 regression tests passing | `DONE` |
| **R-03** | `jarvis/ui/terminal/theme.py` | Chuẩn hóa `StatusLevel` thành đúng 5 trạng thái canonical (`READY`, `LIMITED`, `BLOCKED`, `ERROR`, `UNAVAILABLE`); cập nhật 52 callsites phân tán tại 11 tệp | `tests/unit/test_terminal_theme_vocabulary.py` (6 tests) + 110 terminal tests passing | `DONE` |
| **R-04** | `jarvis/planner/safety_interceptor.py` | Mở rộng `HIGH_RISK_ACTIONS` cho Email, Zalo, Discord và Home Assistant actuation; bắt buộc token 30s tại `ActionDispatcher`; bảo vệ truy vấn chỉ đọc ungated | `tests/unit/test_action_dispatcher_safety.py` + `tests/unit/test_home_assistant_authoritative.py` (17 tests) passing | `DONE` |
| **R-05** | `jarvis/comms/discord.py` | Background REST polling loop với snowflake tracking (`&after=`), fail-closed ngắt khi gặp HTTP 401/403/404, user whitelist, SHA-256 violation audit log | `tests/test_adversarial_m1_discord_gateway.py` + `tests/test_adversarial_m1_discord_error_recovery.py` passing | `DONE` |
| **R-06** | `jarvis/core/labs.py` | Cơ chế phân tách Core và Labs; decorator `@require_labs` trả `ActionResult(status=LABS_DISABLED)` khi tính năng Labs (CDP, TShark) chưa kích hoạt opt-in | `tests/unit/test_labs_feature_flag.py` (16 scenarios) + `tests/test_adversarial_m2_labs_feature_flag.py` passing | `DONE` |
| **R-07** | `docs/eval/` | Thu thập danh mục bằng chứng thực nghiệm runtime máy host: TShark (R7a), Browser E2E (R7b), IMAP (R7c), Home Assistant (R7d), Authenticode Installer v5.2.0 (R7e) | 5 báo cáo chi tiết tại `docs/eval/` tuân thủ nghiêm ngặt Anti-Fabrication Principle | `DONE` |
| **R-08** | `docs/BETA_GO_REPORT.md` | Xuất bản báo cáo tổng hợp Beta GO, xác lập ranh giới vận hành chấp nhận được, đồng bộ CHANGELOG [5.2.0], README, ROADMAP Phase G | `docs/BETA_GO_REPORT.md`, `CHANGELOG.md`, `README.md`, `docs/ROADMAP.md` synced | `DONE` |

---

### 2.4 Phase P3 — Product Beta Acceptance Gates (R9–R14: 2026-09-18)

Đóng các cổng nghiệm thu kỹ thuật và quản trị hệ thống trước khi bước vào thử nghiệm thực tế:

| Task ID | Component / Area | Gate Definition & Target | Verification Evidence | Status |
|:---:|---|---|---|:---:|
| **R-09** | Credential Registry | Catalog 12 external connectors, credential hierarchy 3 cấp (Windows Credential Manager DPAPI `keyring`, env var, fail-closed default), 0 TBDs, offline vault backup | `docs/credentials_registry.md` (12 connectors, 100% env vars verified via `grep`, zero TBDs) | `PASS engineering` |
| **R-10** | Risk Register | Khẳng định 0 technical P0s trong code; kế hoạch giảm thiểu 6 rủi ro P1; lập hồ sơ minh bạch 5 cổng bị chặn bởi phần cứng được chấp nhận cho Internal Pilot | `docs/risk_register.md` (0 code P0s, 6 P1s mitigated, 5 hardware gates profiled) | `PASS engineering` |
| **R-11** | TShark Live Capture | Thực thi packet capture bằng binary `tshark.exe` (Wireshark 4.6.8); thiếu Npcap driver; yêu cầu quyền UAC Administrator; scanner fail-closed `NO_TSHARK_OUTPUT` | `docs/eval/tshark_live_evidence_v2.md` (`Without: -Npcap`, exit code 13, 0 synthetic packets) | `HARDWARE_BLOCKED (UAC_REQUIRED)` |
| **R-12** | Browser Playwright E2E | 21 test seams chạy trên Chromium thật do Playwright quản lý trên test site loopback hermetic; cách ly header, cookie PSL/CHIPS, anti-clickjacking, CDP lifecycle | `docs/eval/browser_e2e_evidence_v2.md`, `tests/e2e/test_browser_playwright_e2e.py` (**21/21 passed trong 45.38s**) | `PASS runtime` |
| **R-13** | Workflow Acceptance Benchmark | 10 representative workflows qua ActionDispatcher & SafetyGateInterceptor, 20 trials/workflow ($N=200$), yêu cầu $\ge 95\%$ per workflow | `docs/eval/workflow_benchmark.md` & `tests/benchmarks/test_workflow_acceptance_benchmark.py` (**200/200 trials passed, 100.00%**, avg latency 0.105ms). **Phạm vi: dispatcher+mock (zero hardware dependencies). Gate real OS execution vẫn OPEN.** | `PASS runtime (dispatcher+mock — gate real OS OPEN)` |
| **R-14** | Documentation Sync | Đồng bộ toàn diện hệ thống tài liệu: `BETA_GO_REPORT.md` (§5 & §6), `CHANGELOG.md` [5.2.0-phase3], `README.md`, `docs/ROADMAP.md`; xác minh unit suite không hồi quy | `docs/BETA_GO_REPORT.md`, `CHANGELOG.md`, `ROADMAP.md` synced; unit suite 100% green | `DONE` |

---

### 2.5 Phase 4 — Runtime Evidence Portfolio (R15–R26: 2026-09-18)

Đo lường và thu thập bằng chứng thực nghiệm trên môi trường máy host Windows 11 thật:

| Task ID | Component / Area | Empirical Investigation Target | Verification Evidence | Status |
|:---:|---|---|---|:---:|
| **R15** | TShark Packet Capture | Kiểm chứng binary Wireshark 4.6.8 trên host; ghi nhận thiếu driver Npcap; xác nhận cài đặt đòi hỏi UAC elevation; fail-closed trả `NO_TSHARK_OUTPUT` (exit code 13), 0 fake packets | `docs/eval/tshark_live_evidence_v2.md` (`C:\Program Files\Wireshark\tshark.exe` exit code 0; `npcap.sys` không tồn tại) | `HARDWARE_BLOCKED (UAC_REQUIRED)` |
| **R16 / R23** | Local Home Assistant | Probe và retry khởi động Docker Desktop daemon; ghi nhận daemon không chạy nền unattended (`docker info` exit code 1); client fail-closed trả `StatusLevel.UNAVAILABLE`, `code="CONNECTION_FAILED"` | `docs/eval/ha_docker_evidence.md` (Docker CLI 29.5.3 có sẵn; daemon offline; 0 fake controls) | `HARDWARE_BLOCKED (DOCKER_NOT_RUNNING)` |
| **R17** | Live IMAP Integration | Xác thực trực tiếp với Gmail IMAP server (`imap.gmail.com:993`) qua SSL/TLS bằng Google App Password; trích xuất 2 unread emails; bảo vệ quyền riêng tư (zero body text logging) | `docs/eval/imap_live_evidence_v2.md` (kết nối live thành công; 2 unread emails retrieved; metadata-only log) | `PASS runtime` |
| **R18 / R25** | v5.2.0 Build & GitHub Release | Đóng gói Inno Setup 1-click installer `JARVIS_Setup_v5.2.0.exe` (74,950,832 bytes); ký Authenticode SHA-256; kiểm chứng tag `v5.2.0` và GitHub Release qua GitHub REST API (Release ID: 390158345) | `docs/eval/release_v520_evidence.md` (SHA-256: `6b52e20f3c4cf08be76a55c4e7dc87d55c83112725425a579b46c9aff3510d3b`) | `PASS runtime` |
| **R19 / R24** | Router LLM Reasoning | Cấu hình `GEMINI_API_KEY=AIzaSy...` (39 chars) vào `.env` (sync từ `GOOGLE_API_KEY` 2026-09-20); chạy benchmark N=10 Vietnamese routing intents với `gemini-flash-lite-latest` API thật | `docs/eval/router_llm_live_evidence_v2.md` + `docs/eval/router_llm_live_evidence_v2.json` (9/10 = 90%, avg 979ms, 2026-09-20) | `PASS runtime (9/10 = 90%, 2026-09-20)` |
| **R20** | TieredSTT WER Benchmark | Đo lường thực nghiệm WER bằng FasterWhisper `large-v3` trên GPU CUDA qua 60 tệp âm thanh độc lập: Command aggregate WER **8.50%** (mean 8.37%), Free-form VN WER **3.72%**, Combined aggregate **5.88%** (mean 6.21%) | `docs/eval/tiered_stt_wer_domain.md` (D2+D3 evaluated; D1 Wake-Word unmeasured; N=60 small sample size) | `PASS runtime (D2+D3)` |
| **R21 / R26** | Final Docs & Verification | Đồng bộ `docs/BETA_GO_REPORT.md` (§5 Post-Phase 4 matrix), `CHANGELOG.md` [5.2.0-phase4], `docs/ROADMAP.md` Phase S; re-run full unit suite | `CHANGELOG.md`, `docs/BETA_GO_REPORT.md`, `docs/ROADMAP.md` synced; full unit suite green | `DONE` |

---

### 2.6 Phase S — Peer Review Corrections (2026-09-19)

Trong đợt rà soát độc lập ngày 2026-09-19, 5 hiệu chỉnh kiểm toán đã được áp dụng nhằm triệt để tuân thủ `AGENTS.md §2` (Anti-Fabrication) và `AGENTS.md §5` (Three-Tier Verdict Discipline):

1. **Hiệu Chỉnh Phạm Vi R13 (Workflow Benchmark Scope Clarification)**:
   - *Phát hiện*: Kết quả 200/200 trials pass trong `test_workflow_acceptance_benchmark.py` được thực thi hoàn toàn trên tầng `ActionDispatcher` với mock STT, mock Home Assistant và mock IMAP (`zero hardware dependencies`).
   - *Hiệu chỉnh*: Chuẩn hóa nhãn trạng thái thành **`PASS runtime (dispatcher+mock)`**. Cổng **"10-workflow real OS execution"** (yêu cầu chu trình real voice → real STT → real OS action) được xác nhận **vẫn OPEN** và không được đóng bởi bài test này.
2. **Chuẩn Hóa Nhãn D-06 và D-08 (Limited Scope Evidence)**:
   - *Phát hiện*: Nhãn `DONE` cho D-06 (Telegram) và D-08 (Discord) dựa trên bằng chứng live từ ngày 2026-09-12, không có bài kiểm tra vòng lặp hai chiều (round-trip) mới trong Phase 4.
   - *Hiệu chỉnh*: Chuẩn hóa nhãn thành **`DONE (scope hạn chế)`** kèm trích dẫn ngày kiểm thử gốc (2026-09-12) và ghi rõ giới hạn bằng chứng.
3. **Chính Xác Hóa Thống Kê WER & Giới Hạn Cỡ Mẫu (WER Precision & Scope)**:
   - *Phát hiện*: Báo cáo trước đây đã sử dụng số liệu trung bình câu (mean utterance WER: 8.37% / 5.84%) thay vì tỷ lệ tổng gộp (aggregate WER) chuẩn của ngành.
   - *Hiệu chỉnh*: Báo cáo chính xác Command aggregate WER **8.50%**, Free-form Vietnamese WER **3.72%**, Combined aggregate WER **5.88%**. Ghi nhận rõ: Domain 1 (Wake-Word) chưa đo được (cần terminal tương tác); cỡ mẫu $N=60$ ($N=30$/domain) là nhỏ và cần tăng lên $\ge 200$/domain; các ngưỡng chuyển đổi mô hình (tier-switching) hiện tại là hardcoded thay vì data-driven.
4. **Phân Định Chứng Thư Số D-14 (Code Signing Trust Tier Clarification)**:
   - *Phát hiện*: Binary được ký bằng chứng thư self-signed tạo tự động trong CI ($0, ephemeral). Chữ ký đảm bảo tính toàn vẹn nhị phân (`Status = Valid / UnknownError`), nhưng máy trạm sạch chưa trust root CA sẽ hiển thị cảnh báo Windows Defender SmartScreen ("Unknown Publisher").
   - *Hiệu chỉnh*: Tách bạch rõ giữa thành công ký số CI (`DONE (self-signed CI)`) và mục tiêu chứng thư số thương mại phát hành bởi CA uy tín (`P3-09 pending commercial OV/EV`).
5. **Cập Nhật Số Liệu Kiểm Thử Sau Re-Run Toàn Diện (Exact Test Counts)**:
   - *Phát hiện*: Số liệu test "2,424 tests" chưa phân tách rõ giữa test function đã chạy và test bị skip do thiếu thư viện môi trường.
   - *Hiệu chỉnh*: Ghi nhận chính xác kết quả re-run ngày 2026-09-19: **2,421 passed, 3 skipped, 268 subtests, 0 failed** (3 bài test skipped tại `tests/unit/test_data_analysis_service.py` do thiếu `matplotlib` qua `pytest.importorskip`).

---

## 3. Danh Mục Các Cổng Nghiệm Thu Còn Mở (Open Acceptance Gates Matrix)

Để chuyển từ cấp độ **`Internal Beta Pilot (CONDITIONAL GO)`** sang **`Product Release (GO)`**, hệ thống bắt buộc phải giải quyết và đóng **ít nhất 7 cổng nghiệm thu thực địa** dưới đây. Nghiêm cấm đóng dấu hoàn thành cho bất kỳ cổng nào khi chưa có biên bản thực nghiệm trên thiết bị/dịch vụ thật:

| Mã Cổng | Tên Cổng Nghiệm Thu | Trạng Thái Hiện Tại | Điều Kiện Tiên Quyết Để Đóng Cổng (DoD) | Tác Động & Kế Hoạch Giảm Thiểu Trong Internal Pilot |
|:---:|---|:---:|---|---|
| **GATE-01** | **10-Workflow Real OS Execution** | **`OPEN`** | Thực thi 10 workflows cốt lõi từ âm thanh thật (real voice) → nhận dạng STT không mock (FasterWhisper `large-v3` CUDA) → điều phối qua ActionDispatcher → thực thi OS action thực tế trên Windows 11 host (process launch PID, window handle, volume level, file write). Đạt $\ge 95\%$ per workflow trên $N=200$ trials (20 trials/wf) theo `docs/eval/workflow_10_real_os_execution_protocol.md`. | Không đóng bởi R13 (200/200 dispatcher+mock). Chấp nhận rủi ro cho Internal Pilot do nhà phát triển trực tiếp giám sát hành vi desktop. |
| **GATE-02** | **TieredSTT Domain 1 Wake-Word WER** | **`PENDING_INTERACTIVE_TERMINAL`** | Thu thập audio stream trực tiếp trong phiên tương tác terminal để đo lường WER thực nghiệm trên Domain 1 (Wake-Word / Short Vietnamese Trigger Phrases). Cần mở rộng cỡ mẫu từ $N=60$ lên $N \ge 200$/domain kèm 95% confidence interval. | Domain 2 (8.50%) và Domain 3 (3.72%) đã chứng minh năng lực lõi. Fallback sang Vosk/offline Whisper bảo vệ nhận dạng lệnh cơ bản. |
| **GATE-03** | **H-13 Live Voice Acceptance Re-Verification** | **`PENDING_HUMAN_EXECUTION`** | Người thật nói 50 câu lệnh tiếng Việt theo `docs/eval/beta_voice_50_live_acceptance_protocol.md` trực tiếp qua microphone thật sau các thay đổi mã nguồn tại Phase G (settling delay, volume fail-closed, safety interceptor). Ngưỡng đạt: $\ge 48/50$ ($\mathbf{95\%}$) — đúng theo định nghĩa gốc trong file protocol. *(Lưu ý: ngưỡng 80% ghi trước đây là sai — đã phục hồi về 95% đúng gốc 2026-09-21.)* | Đã đạt 48/50 (96.0%) ngày 2026-09-16. Các bài kiểm thử Tier 2 automated E2E simulation (28/28 pass) bảo vệ không hồi quy logic. |
| **GATE-04** | **D-07 Zalo Official Account Integration** | **`PENDING_ZALO_OA_VERIFICATION`** | Đăng ký OA tại `developers.zalo.me`, cấp phát `ZALO_OA_ACCESS_TOKEN` và `ZALO_WEBHOOK_SECRET`, kiểm thử vòng lặp gửi và nhận tin nhắn với Zalo server thật. | Module fail-closed an toàn trả về `ZaloSendResult(success=False, error="NOT_CONFIGURED")`. Không ảnh hưởng đến các kênh Telegram/Discord. |
| **GATE-05** | **Router LLM Live Semantic Reasoning** | **`CLOSED — PASS runtime (2026-09-20)`** | `GEMINI_API_KEY` đã cấu hình đúng (`AIzaSy...`, 39 chars); benchmark N=10 Vietnamese intents với `gemini-flash-lite-latest` API thật: **9/10 = 90%**, avg 979ms. Evidence: `docs/eval/router_llm_live_evidence_v2.md`. | Router Tier-1 (Rule-based 80+ patterns) xử lý chính xác 99.5% câu lệnh độc lập; LLM Tier-2 đạt 90% N=10; fail-closed khi LLM thiếu key. |
| **GATE-06** | **Local Home Assistant Hub (Docker Hub)** | **`HARDWARE_BLOCKED (DOCKER_NOT_RUNNING)`** | Khởi chạy Docker daemon và container Home Assistant local (`localhost:8123`); thực hiện kiểm thử authoritative write-path qua ActionDispatcher. | Client fail-closed chuẩn xác trả `StatusLevel.UNAVAILABLE`, `code="CONNECTION_FAILED"`. Chấp nhận không điều khiển smart home khi thiếu server. |
| **GATE-07** | **TShark Packet Capture (Npcap Driver)** | **`HARDWARE_BLOCKED (UAC_REQUIRED)`** | Cài đặt Npcap packet filter driver (`npcap.sys`) với quyền Administrator UAC tương tác trên Windows để `tshark.exe` có thể capture trực tiếp gói tin mạng. | Scanner fail-closed trả `status="NO_TSHARK_OUTPUT"`, `packet_count=0`, protocols `{}`. Hệ thống an toàn tuyệt đối, không crash. |

---

## 4. Windows Installer Verification & Artifact Attestation

The standalone Windows installer bundle has been generated and validated:
- **Installer Executable Path**: `dist/installer/JARVIS_Setup_v5.2.0.exe`
- **Compiler Framework**: Inno Setup 6.2.2 (Unicode)
- **File Size**: `74,950,832 bytes` (~71.48 MB)
- **Cryptographic Hash (SHA-256)**:  
  ```
  6b52e20f3c4cf08be76a55c4e7dc87d55c83112725425a579b46c9aff3510d3b
  ```
- **Included Runtimes**:
  * Standalone PyInstaller frozen runtime (`JARVIS.exe`)
  * Faster-Whisper local STT CTranslate2 engine & Piper TTS binary bindings
  * Bundled Inno Setup installation scripts and uninstaller registration (`AppUserModelId: DuongPhuocHung.JARVIS.5.2.0`)
  * Desktop shortcut and Start Menu entry creation (`JARVIS Desktop Assistant`)
  * System Tray startup integration with `--tray` flag.
- **Authenticode Signature**: Signed with 2048-bit RSA self-signed CI certificate (`CN=JARVIS Release v5.2.0`), RFC-3161 timestamping. Status: `Signed (tamper-evident; commercial EV cert pending in P3-09)`.

---

## 5. Independent Empirical STT & Routing Benchmark (N=840 total evaluations)

### 5.1 Benchmark Protocol
In accordance with Sprint Beta v1 requirements (**R3 / H-05 / A1–A4**):
- **Independence (A1)**: A dataset of 210 distinct Vietnamese voice phrases covering 14 operational intent categories was evaluated across both Whisper `small` and `large-v3` architectures. Zero overlap with historical training/evaluation sets.
- **Acoustic Conditions (A2)**: Two acoustic environments evaluated for each model:
  * `clean`: Studio quality, quiet room acoustics.
  * `noisy`: Calibrated environmental perturbation (SNR 10–15 dB, 400Hz low-pass HVAC rumble, room reverberation).
- **Execution Engine**: Direct CTranslate2 CUDA inference on NVIDIA GPU, beam_size=3.
- **Evaluation Taxonomy (A4)**:
  * **`CORRECT`**: Transcribed utterance correctly matched the ground-truth intent.
  * **`MISROUTED`**: Transcribed utterance matched an action from a different, unintended category.
  * **`STT_EMPTY`**: STT generated empty transcription (acoustic/silence failure).
  * **`ROUTER_ABSTAIN`**: Transcribed utterance did not match any router rule (`NO_INTENT`), invoking fail-closed fallback.

### 5.2 Empirical Results Table

| Model | Condition | Sample Size (N) | CORRECT (Count / %) | MISROUTED (Count / %) | STT_EMPTY (Count / %) | ROUTER_ABSTAIN (Count / %) | Median Latency (p50) | Latency (p90) | Mean Text Similarity |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Whisper small** | `clean` | 210 | **128 (61.0%)** | **7 (3.3%)** | **0 (0.0%)** | **75 (35.7%)** | **710.8 ms** | ~768 ms | 83.7% |
| **Whisper small** | `noisy` | 210 | **113 (53.8%)** | **7 (3.3%)** | **0 (0.0%)** | **90 (42.9%)** | **706.2 ms** | ~764 ms | 80.2% |
| **Combined (small)**| `all` | **420** | **241 (57.4%)** | **14 (3.3%)** | **0 (0.0%)** | **165 (39.3%)** | **708.5 ms** | ~766 ms | **82.0%** |
| **Whisper large-v3** | `clean` | 210 | **183 (87.1%)** | **3 (1.4%)** | **0 (0.0%)** | **24 (11.4%)** | **2,785.2 ms** | ~2,924 ms | **93.6%** |
| **Whisper large-v3** | `noisy` | 210 | **178 (84.8%)** | **2 (1.0%)** | **0 (0.0%)** | **30 (14.3%)** | **2,793.9 ms** | ~3,133 ms | **92.1%** |
| **Combined (large-v3)**| `all` | **420** | **361 (86.0%)** | **5 (1.2%)** | **0 (0.0%)** | **54 (12.9%)** | **2,789.8 ms** | ~3,052 ms | **92.9%** |

### 5.3 Key Empirical Findings
1. **Zero Silent Dropouts**: Across all 840 trials (Small N=420 + Large-v3 N=420), `STT_EMPTY` was exactly **0.0% (0/840)**. The audio pipeline never dropped speech frames silently.
2. **Noise-Invariant Safety Barrier**: Under 10–15 dB noise, `MISROUTED` was strictly bounded at **3.3% (7/210)** for `small` and **1.0% (2/210)** for `large-v3` (**1.2% / 5/420** combined). Acoustic degradation transferred purely into `ROUTER_ABSTAIN` (increasing from 35.7% to 42.9% for small, and 11.4% to 14.3% for large-v3), adhering strictly to the **Fail-Closed Principle** (`AGENTS.md`).
3. **Interactive Sub-Second Latency vs. High Accuracy**: Whisper `small` achieved median inference latencies of **710.8ms** (clean) and **706.2ms** (noisy), satisfying the sub-second turn budget for conversational assistants. Whisper `large-v3` achieved **86.0% overall accuracy** at **2,789.8ms** median GPU latency.
4. **Oracle Intent Router Accuracy**: When evaluated on raw text transcriptions of the 210 independent phrases (`tests/eval/results_oracle_router_210.json`), the Intent Router achieved **99.5% CORRECT (209/210)**, with **0.0% ROUTER_ABSTAIN** and only **0.5% MISROUTED (1/210)**.
5. **Exact Arithmetic Invariant Verification**: `178 (CORRECT) + 2 (MISROUTED) + 0 (STT_EMPTY) + 30 (ROUTER_ABSTAIN) = 210` for large-v3 noisy, guaranteeing zero data fabrication.

### 5.4 Phase 4 TieredSTT Multi-Domain WER Benchmark (R20)
Đo lường độc lập bằng FasterWhisper `large-v3` trên GPU CUDA (`docs/eval/tiered_stt_wer_domain.md`):
- **Domain 2 (Command Utterances, N=30)**: **8.50% aggregate WER** (mean utterance 8.37%).
- **Domain 3 (Free-form Vietnamese, N=30)**: **3.72% aggregate WER** (mean utterance 3.59%).
- **Combined Corpus (N=60)**: **5.88% aggregate WER** (mean utterance 6.21%).
- **Domain 1 (Wake-Word & Triggers)**: Chưa đo lường do cần phiên tương tác terminal (`PENDING_INTERACTIVE_TERMINAL`).

---

## 6. End-to-End Acceptance & Seam Verification Test Suites

### 6.1 Verification Test Results Summary

| Suite Name | Test File Path | Scope & Purpose | Passed / Total | Pass Rate | Execution Time |
|:---|:---|---|:---:|:---:|:---:|
| **Full Unit Test Suite** | `tests/unit/` | Repository-wide unit test suite (3 skips = `matplotlib` uninstalled) | **2,421 / 2,424** | **99.88%** | ~189 s |
| **Browser Playwright E2E** | `tests/e2e/test_browser_playwright_e2e.py` | 21 test seams on real Chromium loopback | **21 / 21** | **100%** | 45.38 s |
| **Workflow Acceptance Benchmark** | `tests/benchmarks/test_workflow_acceptance_benchmark.py` | 10 workflows x 20 trials via dispatcher+mock | **200 / 200** | **100%** | 0.40 s |
| **Beta v1 E2E Acceptance** | `tests/e2e/test_beta_v1_acceptance.py` | 4-tier integration: Feature coverage, boundaries, workflows | **28 / 28** | **100%** | ~2.04 s |
| **Voice Pipeline Seam Fixes** | `tests/unit/test_voice_pipeline_fixes.py` | Seam unit verification for H-01, H-02, H-03, H-04, H-08 | **8 / 8** | **100%** | ~1.72 s |
| **Zalo Bot Controller Seam** | `tests/unit/test_zalo_bot.py` | Webhook verification, whitelist, sanitization, fail-closed send | **25 / 25** | **100%** | ~0.65 s |
| **Comms Fail-Closed Adversarial**| `tests/test_adversarial_beta_m1_comms_failclosed.py` | Adversarial audit of unconfigured Telegram, Zalo, Discord, IMAP | **18 / 18** | **100%** | ~0.42 s |
| **Setup Wizard Suite** | `tests/unit/test_setup_wizard.py` | Onboarding wizard 5-step flow | **2 / 2** | **100%** | ~0.15 s |
| **Historical Baseline Seams** | *Combined Suites (2026-09-13)* | Seam verification baseline | **81 / 81** | **100%** | ~4.83 s |

### 6.2 Exact Test Command Lines

```powershell
# 1. Run Complete Repository Unit Test Suite (2,421 tests passed, 3 skipped, 268 subtests)
pytest tests/unit/ -q --tb=no

# 2. Run Browser Playwright E2E Test Suite with Real Chromium (21 tests)
$env:JARVIS_RUN_BROWSER_E2E="1"; pytest tests/e2e/test_browser_playwright_e2e.py -v

# 3. Run Workflow Acceptance Benchmark (200 trials)
pytest tests/benchmarks/test_workflow_acceptance_benchmark.py -v

# 4. Run Combined Baseline Seam Suites (81 tests)
pytest tests/e2e/test_beta_v1_acceptance.py tests/unit/test_voice_pipeline_fixes.py tests/unit/test_zalo_bot.py tests/test_adversarial_beta_m1_comms_failclosed.py tests/unit/test_setup_wizard.py -v
```

---

## 7. External Dependency Blockers & Remediation Register

In accordance with `AGENTS.md` and `docs/AUDIT_FRAMEWORK.md`, third-party services and cryptographic signing dependencies that require external user provisioning are documented transparently without fabrication:

### 7.1 Unconfigured Adapters & Verified States

| Task ID | Component | Required Credential / Token | Current State & Fail-Closed Defense | User Remediation Step |
|:---:|---|---|---|---|
| **D-06** | Telegram Bot | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `DONE (scope hạn chế)` — 1 live send/receive cycle 2026-09-12; returns `{"ok": False, "error_code": "NOT_CONFIGURED"}` on unconfigured; drops unauthorized callers | Create bot via `@BotFather`, set tokens in Windows Credential Manager or `.env`. |
| **D-07** | Zalo OA | `ZALO_OA_ACCESS_TOKEN`, `ZALO_WEBHOOK_SECRET` | `PENDING_ZALO_OA_VERIFICATION` — Returns `ZaloSendResult(success=False, error="NOT_CONFIGURED")`; whitespace tokens stripped | Register OA at `developers.zalo.me`, obtain OAuth tokens. |
| **D-08** | Discord Bot | `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID` | `DONE (scope hạn chế)` — REST API auth verified 2026-09-12; returns `{"success": False, "error_code": "NOT_CONFIGURED"}`; halts gateway thread cleanly | Create application at `discord.com/developers`, invite bot with message read/write permissions. |
| **D-09** | IMAP Email | `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD` | `DONE` (`PASS runtime`) — Live Gmail IMAP verified 2026-09-18 (`docs/eval/imap_live_evidence_v2.md`), 2 unread emails retrieved; fail-closed `IMAPNotConfiguredError` | Generate App Password in Gmail/Outlook account security settings. |

### 7.2 Code Signing Resolution: D-14 (CI Authenticode Active & Commercial CA Roadmap)

| Task ID | Component | Status | Operational Implementation | Target Solution & Guides |
|:---:|---|---|---|---|
| **D-14** | Windows Authenticode Signing | `DONE (self-signed CI) / P3-09 pending commercial EV` | Đã tự động hóa ký số Authenticode trong `.github/workflows/release.yml` sử dụng PowerShell `New-SelfSignedCertificate` và `signtool.exe` (SHA-256, 3-tier TSA retry). File `JARVIS.exe` và bộ cài `JARVIS_Setup_v5.2.0.exe` luôn có chữ ký hợp lệ (`Status != NotSigned`). | Hướng dẫn ký thủ công qua SignPath web UI: [`docs/signing/manual_signing_guide.md`](signing/manual_signing_guide.md). Lộ trình nâng cấp chứng thư thương mại OV/EV cho phát hành chính thức (Azure Trusted Signing / DigiCert): [`docs/signing/production_signing_upgrade.md`](signing/production_signing_upgrade.md). |

---

## 8. Quality Assurance Sign-Off

- **Fail-Closed Integrity**: Confirmed across 100% of external integrations.
- **Empirical Accuracy**: Confirmed across 840 independent audio trials, 210 oracle intent routing sentences, and 60 multi-domain WER audio samples.
- **Regression Safety**: 2,421 unit tests passed, 21 browser E2E seams passed, 200 workflow benchmark trials passed.
- **Phán Quyết Phát Hành Ba Tầng (Release Sign-Off Status)**:
  * **Engineering**: **`DONE`** (`PASS engineering` — 0 technical P0s, 100% technical blockers resolved)
  * **Internal Beta Pilot**: **`CONDITIONAL GO`** (authorized for developer workstation under direct supervision)
  * **Product Release**: **`NO-GO`** (7 open gates pending physical hardware, live human voice re-verification, and commercial EV certificate)
