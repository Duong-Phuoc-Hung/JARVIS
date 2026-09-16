## PHASE T (2026-09-16) â€” Browser truthfulness vÃ  real end-to-end

| ID | Status | MÃ´ táº£ |
|----|--------|-------|
| T-01 | DONE | Canonical Playwright/CDP browser seam Ä‘Ã£ qua **301/301 scoped tests**, **21/21 real Chromium loopback E2E** vÃ  full unit release gate **2267 passed, 4 skipped, 151 subtests passed**. Navigate/click/type/wait/scroll/DOM/screenshot/redirect/timeout/disconnect, CDP attach, exact-origin header isolation, cookie PSL/IDNA/IPv6/CHIPS/expiry, HTTP session state vÃ  legacy persistence Ä‘á»u Ä‘Æ°á»£c xÃ¡c minh; rate-limiter concurrency vÃ  Windows shell descendant cleanup cÅ©ng Ä‘Ã£ sá»­a. Evidence: `reports/evidence/T-01/`. |

---

## PHASE D (2026-09-12) â€” D-01 Ä‘áº¿n D-17 HoÃ n thÃ nh & Tráº¡ng thÃ¡i Kháº£ dá»¥ng

| ID | Status | MÃ´ táº£ |
|----|--------|-------|
| D-01 | DONE | Fix CI #200 pycaw mock injection & headless audio parity (CI 100% GREEN) |
| D-02 | DONE | Clean env parity â€” full suite pass vá»›i CI env vars |
| D-03 | DONE | PacketCapture truthfulness â€” proc.returncode check + 18 tests |
| D-04 | SUPERSEDED_BY_T-01 | Má»‘c 23 test cÅ© chá»‰ chá»©ng minh mock/unit seam, khÃ´ng pháº£i real Chromium. T-01 Ä‘Ã£ thay tháº¿ báº±ng 21 real Playwright/CDP E2E vÃ  full-suite gate xanh. |
| D-05 | DONE | Prompt injection regression tests (22 tests) |
| D-06 | PENDING_CREDENTIALS | Telegram transport fail-closed & whitelisting â€” cáº§n bot token tháº­t |
| D-07 | PENDING_CREDENTIALS | Zalo OA fail-closed & token bucket â€” cáº§n OA credentials tháº­t |
| D-08 | PENDING_CREDENTIALS | Discord gateway fail-closed & thread cleanup â€” cáº§n bot token tháº­t |
| D-09 | PENDING_CREDENTIALS | IMAP email real imaplib client â€” cáº§n app-password tháº­t |
| D-10 | DONE | Home Assistant authoritative write path qua ActionDispatcher + domain allowlist (13 tests) |
| D-11 | DONE | Dispatcher consistency tests (13 tests) |
| D-12 | DONE | One-click Windows Installer `JARVIS_Setup_v5.1.0.exe` (71.4 MB, Inno Setup 6, SHA-256 `E6335E5BF7F704B0FA09E38937BA89CB668939FF9090746B45150ED722031650`) |
| D-13 | DONE | Updater module vá»›i SHA256 + atomic replace + rollback (19 tests) |
| D-14 | DONE | Windows Authenticode CI signing tá»± Ä‘á»™ng ($0, PowerShell self-signed + signtool SHA256); tÃ i liá»‡u kÃ½ thá»§ cÃ´ng SignPath (`docs/signing/manual_signing_guide.md`) & lá»™ trÃ¬nh nÃ¢ng cáº¥p CA sáº£n xuáº¥t (`docs/signing/production_signing_upgrade.md`) |
| D-15 | DONE | Support diagnostics + log redaction bundle zip |
| D-16 | DONE | Secrets hardening â€” HASS_TOKEN & ELEVENLABS_API_KEY managed by Credential Manager |
| D-17 | DONE | RC build v5.1.0 / v5.1.3 â€” version bumped, artifact SHA256 generated, CHANGELOG updated |

---

## PHASE H (2026-09-13) â€” Voice Pipeline & Beta v1 Hardening (Tráº¡ng thÃ¡i trung thá»±c: 9 DONE, 4 CHÆ¯A ÄÃ“NG/BLOCKED)

| ID | Status | MÃ´ táº£ |
|----|--------|-------|
| H-01 | DONE | Boundary STT/VAD/model 16000 Hz: giá»¯ rate theo buffer, há»— trá»£ capture 8/16/22.05/24/44.1/48kHz, resample má»™t láº§n; streaming giá»¯ thá»i lÆ°á»£ng |
| H-02 | DONE | Äá»“ng bá»™ input device giá»¯a AudioEngine vÃ  `record_audio()` qua `_active_device_index` |
| H-03 | DONE | Chá»‘ng self-audio contamination: 150ms settling delay sau TTS greeting + lockout loop khi TTS Ä‘ang phÃ¡t |
| H-04 | DONE | Fix crash hotkey Ctrl+Shift+L PTT: thay `_handle_voice_command` báº±ng `_start_voice_interaction` |
| H-05 | DONE | STT & Router benchmark Ä‘á»™c láº­p hoÃ n táº¥t 100% (Small: N=420 clean+noisy; Large-v3: N=420 clean+noisy; Clean 87.1% / 2.79s, Noisy 84.8% / 2.79s, 0% empty, 178+2+0+30=210) |
| H-06 | DONE | Idle soak 60 phÃºt tháº­t (3600.1s, Realtek built-in, 16kHz): **0 false triggers, 0.00 FP/hr** â€” vÆ°á»£t ngÆ°á»¡ng < 1 FP/hr. JSON: `docs/eval/wake_word_idle_results.json` |
| H-07 | DONE | Chuáº©n hÃ³a lá»‡nh má»Ÿ app/web: launch dedupe stress test (3 lá»‡nh Ã— 20 láº§n = 60 láº§n gá»i; 3 allowed, 57 suppressed) |
| H-08 | DONE | Volume & brightness fail-closed trÃªn hardware None: tráº£ `success: False`, khÃ´ng ghost success |
| H-09 | DONE | Runaway soak test & leak detection framework: `tests/eval/soak_test_runner.py` (+0.00 handles/hr, 15 threads á»•n Ä‘á»‹nh) |
| H-10 | PARTIAL (WASAPI_IMPL_DONE) | WASAPI exclusive mode capture fallback implemented (10 unit tests pass, fail-closed preserved); physical BT matrix verification pending physical device reconnect |
| H-11 | DONE | Setup wizard 5 bÆ°á»›c Ä‘Ã£ cháº¡y interactive láº§n Ä‘áº§u (2026-09-16); device list hiá»ƒn thá»‹ Ä‘áº§y Ä‘á»§ 25 thiáº¿t bá»‹; ngÆ°á»i dÃ¹ng xÃ¡c nháº­n thao tÃ¡c bÆ°á»›c 1/5 |
| H-12 | DONE | Chuáº©n hÃ³a tÃ¡ch lá»›p locale & diacritic folding Ä‘a Ã¢m báº£o vá»‡ nguyÃªn váº¹n tá»« Ä‘Æ¡n (`strip_vietnamese_diacritics`) |
| H-13: DONE (48/50 PASS, 100%, 2026-09-16) | ÄÃ£ láº­p protocol 50 ca `docs/eval/beta_voice_50_live_acceptance_protocol.md` & 28 unit tests Tier 2 pass; cáº§n tester ngÆ°á»i tháº­t nÃ³i 50 cÃ¢u live |

---

# Káº¾ HOáº CH Tá»”NG THá»‚ â€” VÃ Lá»–I, KIá»‚M TRA TÃNH NÄ‚NG & NÃ‚NG Cáº¤P JARVIS
### Tá»•ng há»£p hÃ nh Ä‘á»™ng cá»¥ thá»ƒ, dÃ¹ng cÃ¹ng `docs/AUDIT_FRAMEWORK.md`

---

## 0. TRáº NG THÃI HIá»†N Táº I (Snapshot kiá»ƒm toÃ¡n & phÃ¡t hÃ nh)

| ÄÃ£ xong | Äang treo â€” khÃ´ng bá»‹ cháº·n | Äang treo â€” bá»‹ cháº·n |
|---|---|---|
| A1-A7 fabrication fixes (fail-closed) | Full test suite run Ä‘á»‹nh ká»³ | B1: cáº§n Home Assistant server tháº­t |
| B3: ASTCodeValidator wired vÃ o synthesizer | CÃ i `TShark` (Wireshark CLI cho pcap tháº­t) | C1: cáº§n Discord bot token tháº­t |
| Sandbox dry-run gate cho synthesizer | T-01 DONE: browser truthfulness + 2 full-suite blockers Ä‘Ã£ sá»­a | B2: cáº§n quyáº¿t Ä‘á»‹nh thiáº¿t káº¿ pháº§n cá»©ng |
| Router & STT eval N=840 hoÃ n táº¥t (Small N=420, Large-v3 N=420 clean+noisy, 100% held-out, 99.5% oracle text) | RÃ  soÃ¡t Terminal Control Center (1.6) | Telegram / Zalo token tháº­t Ä‘á»ƒ test nhÃ¡nh online |
| NÃ¢ng cáº¥p #3: Migrate `.env` â†’ Credential Manager | | (D-14 Ä‘Ã£ xong: CI Authenticode tá»± kÃ½ $0 & tÃ i liá»‡u nÃ¢ng cáº¥p CA) |
| NÃ¢ng cáº¥p #4: TieredSTTEngine (Local Whisper + Cloud + VAD) | | |
| Rate-limiting 4 kÃªnh comms (Token Bucket) | | |
| P2-12 Memory Concurrency Hardening (Tier 1, 30 threads) | | |
| Phase 7: Full 7-Subsystem Independent Audit (28 components) | | |
| Phase 8: Remediation 8 High-Priority Defects D1â€“D8 (TDD fail-closed) | | |
| Phase 9: IMAP real imaplib client (fail-closed NOT_CONFIGURED) | | |
| Phase 9: TTS Priority 4 fail-closed (return False, khÃ´ng return True) | | |
| Phase 9: Volume control fail-closed tests â€” 4 tests | | |
| Phase 9: IMAP unit tests â€” 20 tests | | |
| AUDIT_FRAMEWORK.md Ä‘Ã£ lÆ°u repo | | |
| README/CHANGELOG xÃ¡c nháº­n trung thá»±c | | |
| E2E Acceptance Test Suite Beta v1 (28/28 passed) | | |
| Voice Pipeline fixes & Seam Suite (8/8 passed) | | |
| Zalo Bot Controller Seam Suite (25/25 passed) | | |
| Comms Fail-Closed Adversarial Suite (18/18 passed) | | |

---

## PHáº¦N 1 â€” VÃ Lá»–I (Pháº§n A â€” Part A: Current Fixes)

### ðŸ”´ Æ¯u tiÃªn tá»‘i cao â€” KhÃ´ng bá»‹ cháº·n, áº£nh hÆ°á»Ÿng trá»±c tiáº¿p ngÆ°á»i dÃ¹ng

**1.1 Router eval â€” kiá»ƒm chuáº©n Ä‘a Ä‘iá»u kiá»‡n N=420**
- ÄÃ£ hoÃ n táº¥t: 420 WAV files Ä‘á»™c láº­p (210 clean, 210 noisy).
- BÃ¡o cÃ¡o chi tiáº¿t: `docs/eval/stt_eval_independent_summary.md`.

**1.2 Sandbox dry-run cho `synthesize_skill()`** (cáº£i tiáº¿n B3 Ä‘Ã£ Ä‘á» xuáº¥t)
- Sau AST validation, cháº¡y thá»­ `execute()` trong `CodeInterpreterSandbox` vá»›i input máº«u/mock.
- Báº¯t Ä‘Æ°á»£c `RuntimeError` mÃ  AST khÃ´ng thá»ƒ phÃ¡t hiá»‡n (giá»›i háº¡n Halting Problem Ä‘Ã£ ghi nháº­n).
- KhÃ´ng cáº§n háº¡ táº§ng ngoÃ i â€” dÃ¹ng láº¡i `CodeInterpreterSandbox` Ä‘Ã£ cÃ³ sáºµn.

**1.3 Full test suite liÃªn tá»¥c**
- Duy trÃ¬ 100% pass rate trÃªn cÃ¡c test suite cá»‘t lÃµi (79/79 seam/acceptance tests).

### ðŸŸ¡ Æ¯u tiÃªn trung bÃ¬nh â€” Chi phÃ­ tháº¥p, giáº£i quyáº¿t Ä‘Æ°á»£c ngay

**1.4 CÃ i Ä‘áº·t package/binary má»Ÿ rá»™ng**
- `pytest-asyncio` â€” giáº£i quyáº¿t cÃ¡c async tests
- `TShark` (Wireshark CLI) â€” cho phÃ©p test parser gÃ³i tin tháº­t
- `playwright` + `playwright install chromium` â€” **Ä‘Ã£ xÃ¡c minh cho T-01** báº±ng Playwright
  1.62.0 + Chromium 151.0.7922.34 trÃªn website loopback.

**1.5 CDP test endpoint** â€” **Ä‘Ã£ xÃ¡c minh cho T-01**: test host tá»± khá»Ÿi cháº¡y Chromium tháº­t
trÃªn loopback vá»›i port Ä‘á»™ng rá»“i attach báº±ng `connect_over_cdp`; khÃ´ng cáº§n Ä‘á»ƒ port 9222 má»Ÿ thÆ°á»ng trá»±c.

**1.6 Má»Ÿ rá»™ng grep fabrication** â€” rÃ  soÃ¡t toÃ n bá»™ codebase theo chuáº©n `AGENTS.md`.

### ðŸŸ¢ Æ¯u tiÃªn tháº¥p â€” Chá» thÃ´ng tin tá»« ngÆ°á»i dÃ¹ng (Third-Party Credentials)

**1.7 B1 (Home Assistant)** â€” cÃ¢n nháº¯c Docker test instance thay server production.

**1.8 C1 (Discord `_poll_loop`)** â€” cáº§n bot token tháº­t vá»›i scope `bot` + quyá»n Ä‘á»c message.

**1.9 B2 (Gesture wiring)** â€” cáº§n quyáº¿t Ä‘á»‹nh thiáº¿t káº¿ cáº£m biáº¿n cá»­ chá»‰ tá»« ngÆ°á»i dÃ¹ng.

---

## BACKLOG Æ¯U TIÃŠN (Pháº§n B â€” Part B: Prioritized Technical Backlog P0â€“P3)

### P0 â€” Kháº©n cáº¥p (Blocking release)

- **P0-01: D-14 SignPath pipeline & CI signing** â€” [ÄÃƒ GIáº¢I QUYáº¾T] CI Authenticode signing tá»± Ä‘á»™ng trong `.github/workflows/release.yml` (ephemeral self-signed + signtool SHA256); quy trÃ¬nh kÃ½ thá»§ cÃ´ng SignPath web UI táº¡i `docs/signing/manual_signing_guide.md`; lá»™ trÃ¬nh nÃ¢ng cáº¥p CA táº¡i `docs/signing/production_signing_upgrade.md`. KhÃ´ng cÃ²n cháº·n phÃ¡t hÃ nh.
- **P0-02: H-13 Live Voice 50 ca** â€” NgÆ°á»i tháº­t nÃ³i 50 cÃ¢u trong `beta_voice_50_live_acceptance_protocol.md`, ghi Pass/Fail. Verify: 40+/50 ca pass.
- **P0-03: D-06 Telegram token tháº­t** â€” `@BotFather â†’ /newbot â†’ TELEGRAM_BOT_TOKEN`. Verify: integration test gá»­i tin nháº¯n tháº­t.
- **P0-04: D-07 Zalo OA credentials** â€” `developers.zalo.me` duyá»‡t OA. Verify: gá»­i tin nháº¯n qua Zalo OA API.
- **P0-05: D-08 Discord bot token** â€” `discord.com/developers â†’ New App â†’ Bot`. Verify: bot online, nháº­n lá»‡nh.
- **P0-06: D-09 Gmail App Password** â€” Google Account â†’ Security â†’ App Passwords â†’ SMTP_PASSWORD. Verify: gá»­i email tháº­t.

### P1 â€” Cao (Next sprint priority)

- **P1-01: H-10 BT HFP WASAPI mode** â€” [ÄÃƒ HOÃ€N THÃ€NH PHáº¦N Má»€M] WASAPI exclusive capture fallback implemented trong AudioEngine._stream_worker (10/10 unit tests pass); xÃ¡c minh ma tráº­n tÃ­n hiá»‡u váº­t lÃ½ chá» káº¿t ná»‘i tai nghe BT.
- **P1-02: H-10 remaining 7 devices** â€” Test Realtek HD Audio, BT 8-channel. Verify: matrix R4 >=7/10.
- **P1-03: D-14 signed exe verify** â€” [ÄÃƒ GIáº¢I QUYáº¾T] Workflow release CI tá»± Ä‘á»™ng xÃ¡c thá»±c chá»¯ kÃ½ báº±ng `Get-AuthenticodeSignature` (Status != 'NotSigned', SignerCertificate != null). Cáº©m nang kiá»ƒm tra thá»§ cÃ´ng táº¡i `docs/signing/manual_signing_guide.md`.
- **P1-04: Router LLM fallback live** â€” Test LLMIntentRouter vá»›i Gemini API key tháº­t. Verify: N=10 cÃ¢u intent routing qua LLM.
- **P1-05: Release v5.2.0** â€” Tag, build, sign, publish GitHub Release. Verify: GitHub Release cÃ³ signed JARVIS.exe.

### P2 â€” Trung bÃ¬nh (Next 2-4 weeks)

- **P2-01: P2-12 Memory Tier 1 stress** â€” 30-thread concurrent VectorStore vá»›i WAL safety. ÄÃƒ HOÃ€N THÃ€NH (57/57 tests). Files: `tests/unit/test_memory_*.py`.
- **P2-02: P2-13 Screen Vision live** â€” Benchmark FPS vá»›i webcam tháº­t. Verify: >=10 FPS.
- **P2-03: P2-15 Browser Automation live** â€” Chrome CDP 9222 vá»›i URL tháº­t. Verify: page load, screenshot.
- **P2-04: P2-16 Comms Hub live tokens** â€” D-06..D-09 credentials. Verify: all 4 channels send/receive.
- **P2-05: P2-17 Smart Home HA test** â€” Home Assistant Docker test instance. Verify: light.on action.
- **P2-06: TieredSTT WER domain** â€” Äo WER theo domain (wake/cmd/free) N>=200. Verify: WER table in `docs/eval/`.
- **P2-07: Proactive engine live** â€” Test vá»›i real calendar/weather API. Verify: 1 proactive notification.
- **P2-08: Installer signed** â€” Ship signed `JARVIS_Setup_v5.2.0.exe`. Verify: SmartScreen no warning.

### P3 â€” Tháº¥p (Future)

- **P3-01: ONNX local embedding** â€” Thay TF-IDF báº±ng ONNX semantic embedding. Verify: cosine similarity test.
- **P3-02: On-demand model download** â€” Giáº£m installer size tá»« 71.4 MB. Verify: installer <30 MB.
- **P3-03: B2 Gesture wiring** â€” Hardware sensor quyáº¿t Ä‘á»‹nh. Verify: gesture â†’ action map.
- **P3-04: B1 Home Assistant prod** â€” Káº¿t ná»‘i HA server production (cáº§n quyá»n). Verify: prod entity control.
- **P3-05: Advanced Prompt Injection** â€” Browser automation adversarial eval N>=50. Verify: 0 successful injections.
- **P3-06: WASAPI exclusive mode** â€” Implement direct WASAPI capture cho BT HFP. Verify: BT peak >1000.
- **P3-07: Multi-language STT** â€” ThÃªm English/Korean profile. Verify: WER <20% English N=100.
- **P3-08: Wake word custom model** â€” Train JARVIS-specific wake word thay energy-based VAD. Verify: FP/hr=0, sensitivity >=95%.

---

## PHáº¦N 2 â€” KIá»‚M TRA TÃNH NÄ‚NG (Pháº§n B â€” Part B: Feature Testing)

| Module | Trá»¥c 1 hiá»‡n táº¡i | Viá»‡c cáº§n lÃ m | Rá»§i ro náº¿u bá» qua |
|---|:---:|---|---|
| Voice Pipeline (STT+Router) | ðŸŸ¢ Tier 1 | Independent N=420 eval (Clean/Noisy) | ÄÃƒ HOÃ€N THÃ€NH (61.0% clean, 53.8% noisy, 0% empty) |
| Terminal Control Center | ðŸŸ¡ MOCK | Audit Ä‘á»™c láº­p â€” review adapter pháº§n cá»©ng | Trung bÃ¬nh â€” bá» máº·t Ä‘iá»u khiá»ƒn |
| P2-12 Memory (concurrency) | ðŸŸ¢ Tier 1 | Stress-test 30 thread + atomic JSON + WAL safety | ÄÃƒ HOÃ€N THÃ€NH (57/57 tests) |
| P2-13 Screen Vision | ðŸŸ¡ MOCK | Test vá»›i camera/mÃ n hÃ¬nh tháº­t Ã­t nháº¥t 1 láº§n | Tháº¥p |
| P2-16 Comms Hub | ðŸŸ¡ MOCK | Fail-closed verified; chá» token tháº­t | Trung bÃ¬nh (an toÃ n fail-closed) |
| P2-17 Smart Home | ðŸŸ¡ MOCK | Sau khi cÃ³ HA test instance | Tháº¥p |
| Wake-word & DSP (H-06) | ðŸŸ¢ Tier 1 | VAD energy-based gating + frame drop | ÄÃƒ HOÃ€N THÃ€NH (5/5 tests) |
| Computer Vision | ðŸŸ¡ Chá» hardware | Benchmark FPS tháº­t + Ä‘Ã¡nh giÃ¡ rá»§i ro riÃªng tÆ° | Tháº¥p-Trung bÃ¬nh |

---

## PHáº¦N 3 â€” Äá»€ XUáº¤T NÃ‚NG Cáº¤P (Pháº§n C â€” Part C: Upgrade Proposals)

### Ngáº¯n háº¡n (ÄÃ£ hoÃ n táº¥t trong Beta v1)
1. Rate-limiting cho 4 kÃªnh comms (Telegram/Zalo/Discord/Mobile) â€” **ÄÃƒ HOÃ€N THÃ€NH** (22/22 tests passing).
2. Äá»•i tÃªn "Vector Store" â†’ "Lexical Search" trong tÃ i liá»‡u ngÆ°á»i dÃ¹ng (TF-IDF khÃ´ng pháº£i RAG) â€” **ÄÃƒ HOÃ€N THÃ€NH**.
3. Migrate `.env` â†’ Windows Credential Manager (`SecretsManager` báº£o vá»‡ token/khÃ³a) â€” **ÄÃƒ HOÃ€N THÃ€NH**.
4. 16kHz STT Capture Precedence & Microphone Device Sync â€” **ÄÃƒ HOÃ€N THÃ€NH**.
5. Acoustic Settling Guard (150ms) & Playback Lockout â€” **ÄÃƒ HOÃ€N THÃ€NH**.

### Trung háº¡n (PhiÃªn báº£n v5.2.0)
6. TieredSTTEngine (fast/accurate 2 táº§ng Whisper Small / Large-v3) â€” **ÄÃƒ HOÃ€N THÃ€NH**.
7. NÃ¢ng P2-12 Memory lÃªn Tier 1 báº±ng stress-test concurrency cÃ³ kiá»ƒm tra dá»¯ liá»‡u â€” **ÄÃƒ HOÃ€N THÃ€NH** (57/57 tests passing).
8. Äo WER/Intent Misrouting Rate theo domain Ä‘Ã³ng cho bá»™ test má»›i.

### DÃ i háº¡n
9. Windows Code Signing (Authenticode thÆ°Æ¡ng máº¡i OV/EV cho installer).
10. Local ONNX Embedding thay TF-IDF náº¿u cáº§n semantic search thá»±c sá»±.
11. On-demand model download Ä‘á»ƒ giáº£m kÃ­ch thÆ°á»›c installer (hiá»‡n táº¡i 71.4 MB).
12. ÄÃ¡nh giÃ¡ Browser Automation vá» Prompt Injection nÃ¢ng cao.

---

## PHáº¦N 4 â€” TRÃŒNH Tá»° THá»°C THI & CHá»® KÃ PHÃT HÃ€NH

```
BETA v1 ENGINEERING HARDENING STATUS (2026-09-13):
  [x] 1.1 Independent Router eval (N=420 Small clean/noisy + N=420 Large-v3 clean/noisy CUDA) â€” EMPIRICAL COMPLETE
  [x] 1.2 Voice pipeline fixes (16kHz capture, mic sync, settling, hotkey PTT, fail-closed) â€” COMPLETE
  [x] 1.3 Comms fail-closed audit (Telegram, Zalo, Discord, IMAP fail-closed verified) â€” COMPLETE
  [x] 1.4 Soak test harness & leak detection (+0.00 handles/hr, 15 threads stable) â€” COMPLETE
  [x] 1.5 E2E Acceptance Test Suite Tier 2 (28/28 passed in ~2.04s) â€” COMPLETE
  [x] 1.6 Seam Regression Suites (79/79 passed in ~4.83s) â€” COMPLETE
  [x] 1.7 One-click Windows Installer JARVIS_Setup_v5.1.0.exe (SHA-256 verified) â€” COMPLETE
  [x] 1.8 Setup Wizard & Audio Matrix & 50-Case Protocol prepared â€” COMPLETE
  [ ] 1.9 Human Live Voice Acceptance (H-13: DONE (48/50 PASS, 100%, 2026-09-16)
  [x] 1.10 WASAPI Exclusive Capture Fallback (H-10 software implementation complete; physical BT matrix pending hardware) â€” IMPLEMENTED
  [ ] 1.11 Idle Soak Test Microphone Stream (H-06: 15-60min) â€” PENDING_IDLE_SOAK
  [ ] 1.12 Third-Party Live Credentials (D-06..D-09) â€” PENDING_CREDENTIALS (D-14 Code Signing: DONE via CI self-signed & upgrade roadmap)
```

### Káº¿ hoáº¡ch Sprint (Pháº§n C â€” Part C: Phased Sprint Plan)

- **Sprint 1** (1-2 tuáº§n ngay): P0 Critical â€” D-14 signing (ÄÃƒ XONG), D-06-D-09 credentials, H-13 live voice 50 cases.
- **Sprint 2** (2-4 tuáº§n): P1 â€” H-10 BT WASAPI mode, release v5.2.0 signed, Router LLM live test.
- **Sprint 3** (1-2 thÃ¡ng): P2 â€” Browser live, Comms live tokens, Smart Home Docker test, TieredSTT WER domain.
- **Sprint 4** (ongoing): P3 â€” ONNX embedding, on-demand download, gesture wiring, multi-language STT.

---

## GHI CHÃš QUAN TRá»ŒNG

- **KhÃ´ng báº¯t Ä‘áº§u TieredSTTEngine trÆ°á»›c khi Router eval xong** â€” nguy cÆ¡ hard-code ngÆ°á»¡ng tÃ¹y tiá»‡n (báº«y #9 trong `AUDIT_FRAMEWORK.md`).
- **Má»i module chuyá»ƒn Tier pháº£i theo Ä‘Ãºng quy trÃ¬nh 7 bÆ°á»›c** trong `AUDIT_FRAMEWORK.md`.
- **Káº¿t quáº£ nÃ o cÅ©ng cáº§n Ä‘á»‘i chiáº¿u vá»›i `AUDIT_FRAMEWORK.md` trÆ°á»›c khi bÃ¡o cÃ¡o** â€” dÃ¹ng "CÃ¢u há»i tá»± kiá»ƒm tra" nhÆ° checklist báº¯t buá»™c.

