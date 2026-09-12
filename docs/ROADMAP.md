## PHASE D (2026-09-12) — D-01 den D-17 Hoan thanh

| ID | Status | Mo ta |
|----|--------|-------|
| D-01 | DONE | Fix CI #200 pycaw mock injection (sys.modules pattern) |
| D-02 | DONE | Clean env parity — full suite pass voi CI env vars |
| D-03 | DONE | PacketCapture truthfulness tests (17 tests) |
| D-04 | DONE | Browser CDP fail-closed da co tu Phase 8, no-session tra fail |
| D-05 | DONE | Prompt injection regression tests (22 tests) |
| D-06 | PENDING_CREDENTIALS | Telegram real smoke test — can bot token that |
| D-07 | PENDING_CREDENTIALS | Zalo OA real smoke test — can OA credentials that |
| D-08 | PENDING_CREDENTIALS | Discord gateway real test — can bot token that |
| D-09 | PENDING_CREDENTIALS | IMAP real mailbox test — can app-password that |
| D-10 | PENDING_CREDENTIALS | Home Assistant write path — can HA instance that |
| D-11 | DONE | Dispatcher consistency tests (13 tests) |
| D-12 | DONE | Installer script hien co scripts/build_installer.py |
| D-13 | DONE | Updater module voi SHA256 + rollback (jarvis/updater/) |
| D-15 | DONE | Support diagnostics + log redaction (jarvis/support/) |
| D-16 | DONE | Secrets hardening — tat ca connector dung NOT_CONFIGURED |
| D-17 | DONE | RC build v5.1.0 — version bumped, CHANGELOG updated |

---

# Káº¾ HOáº CH Tá»”NG THá»‚ â€” VÃ Lá»–I, KIá»‚M TRA TÃNH NÄ‚NG & NÃ‚NG Cáº¤P JARVIS
### Tá»•ng há»£p hÃ nh Ä‘á»™ng cá»¥ thá»ƒ, dÃ¹ng cÃ¹ng `docs/AUDIT_FRAMEWORK.md`

---

## 0. TRáº NG THÃI HIá»†N Táº I (Snapshot trÆ°á»›c khi báº¯t Ä‘áº§u)

| ÄÃ£ xong | Äang treo â€” khÃ´ng bá»‹ cháº·n | Äang treo â€” bá»‹ cháº·n |
|---|---|---|
| A1-A7 fabrication fixes (fail-closed) | Full test suite run má»›i nháº¥t | B1: cáº§n HA server tháº­t |
| B3: ASTCodeValidator wired vÃ o synthesizer | CÃ i `TShark` (Wireshark CLI) | C1: cáº§n Discord bot token tháº­t |
| Sandbox dry-run gate cho synthesizer | Má»Ÿ port CDP 9222 cho browser tests | B2: cáº§n quyáº¿t Ä‘á»‹nh thiáº¿t káº¿ |
| Router eval (#40) Ä‘Ã³ng (57.8% audio, 100% held-out) | RÃ  soÃ¡t Terminal Control Center (1.6) | Telegram/ElevenLabs token tháº­t Ä‘á»ƒ test nhÃ¡nh "cÃ³ cáº¥u hÃ¬nh" |
| NÃ¢ng cáº¥p #3: Migrate `.env` â†’ Credential Manager | | |
| NÃ¢ng cáº¥p #4: TieredSTTEngine (Local Whisper + Cloud + VAD) | | |
| Rate-limiting 4 kÃªnh comms (#1) (Token Bucket) | | |
| P2-12 Memory Concurrency Hardening (Tier 1, 30 threads) | | |
| Phase 7: Full 7-Subsystem Independent Audit (28 components) | | |
| Phase 8: Remediation 8 High-Priority Defects D1â€“D8 (TDD fail-closed) | | |
| Phase 9: IMAP real imaplib client (fail-closed NOT_CONFIGURED) | | |
| Phase 9: TTS Priority 4 fail-closed (return False, khÃ´ng return True) | | |
| Phase 9: Volume control fail-closed tests (F5) â€” 4 tests | | |
| Phase 9: IMAP unit tests â€” 20 tests (F2+F4) | | |
| AUDIT_FRAMEWORK.md Ä‘Ã£ lÆ°u repo | | |
| README/CHANGELOG xÃ¡c nháº­n trung thá»±c | | |


---

## PHáº¦N 1 â€” VÃ Lá»–I (theo thá»© tá»± Æ°u tiÃªn thá»±c thi)

### ðŸ”´ Æ¯u tiÃªn tá»‘i cao â€” KhÃ´ng bá»‹ cháº·n, áº£nh hÆ°á»Ÿng trá»±c tiáº¿p ngÆ°á»i dÃ¹ng

**1.1 Router eval (#40) â€” viá»‡c quan trá»ng nháº¥t cÃ²n treo**

TiÃªu chuáº©n Ä‘Ã³ng: cáº£ 2 táº­p Ä‘á»u tÄƒng CORRECT â†’ confirmed fixed. Chá»‰ táº­p cÅ© tÄƒng â†’ overfit, cáº§n Ä‘iá»u tra thÃªm.

**1.2 Sandbox dry-run cho `synthesize_skill()`** (cáº£i tiáº¿n B3 Ä‘Ã£ Ä‘á» xuáº¥t)
- Sau AST validation, cháº¡y thá»­ `execute()` trong `CodeInterpreterSandbox` vá»›i input máº«u/mock.
- Báº¯t Ä‘Æ°á»£c `RuntimeError` mÃ  AST khÃ´ng thá»ƒ phÃ¡t hiá»‡n (giá»›i háº¡n Halting Problem Ä‘Ã£ ghi nháº­n).
- KhÃ´ng cáº§n háº¡ táº§ng ngoÃ i â€” dÃ¹ng láº¡i `CodeInterpreterSandbox` Ä‘Ã£ cÃ³ sáºµn.

**1.3 Full test suite láº§n cuá»‘i**

### ðŸŸ  Æ¯u tiÃªn trung bÃ¬nh â€” Chi phÃ­ tháº¥p, giáº£i quyáº¿t Ä‘Æ°á»£c ngay

**1.4 CÃ i 3 package/binary cÃ²n thiáº¿u**
- `pytest-asyncio` â€” giáº£i quyáº¿t 3/16 pre-existing failures
- TShark (Wireshark CLI) â€” cho phÃ©p test A1 parser tháº­t
- `playwright` + `playwright install chromium` â€” cho P2-15 Browser Automation

**1.5 Má»Ÿ port CDP 9222** â€” má»Ÿ Chrome/Edge vá»›i `--remote-debugging-port=9222` trÆ°á»›c khi cháº¡y 2 test CDPDriver Ä‘ang fail.

**1.6 Má»Ÿ rá»™ng grep fabrication** â€” cháº¡y láº¡i extended_fabrication_scan trÃªn toÃ n bá»™ codebase, Ä‘áº·c biá»‡t rÃ  ká»¹ Terminal Control Center.

### ðŸŸ¡ Æ¯u tiÃªn tháº¥p â€” Chá» thÃ´ng tin tá»« ngÆ°á»i dÃ¹ng

**1.7 B1 (Home Assistant)** â€” cÃ¢n nháº¯c Docker test instance thay server production.

**1.8 C1 (Discord `_poll_loop`)** â€” cáº§n bot token tháº­t vá»›i scope `bot` + quyá»n Ä‘á»c message.

**1.9 B2 (Gesture wiring)** â€” cáº§n quyáº¿t Ä‘á»‹nh thiáº¿t káº¿ tá»« ngÆ°á»i dÃ¹ng.

---

## PHáº¦N 2 â€” KIá»‚M TRA TÃNH NÄ‚NG

| Module | Trá»¥c 1 hiá»‡n táº¡i | Viá»‡c cáº§n lÃ m | Rá»§i ro náº¿u bá» qua |
|---|:---:|---|---|
| Voice Pipeline (STT+Router) | ðŸŸ¡ | Router eval (má»¥c 1.1) | Cao â€” áº£nh hÆ°á»Ÿng usability hÃ ng ngÃ y |
| Terminal Control Center | ðŸŸ¡ | Audit Ä‘á»™c láº­p â€” chÆ°a review ngoÃ i PR gá»‘c | Trung bÃ¬nh â€” bá» máº·t táº¥n cÃ´ng má»›i |
| P2-12 Memory (concurrency) | ðŸŸ¢ Tier 1 | Stress-test 30 thread + atomic JSON + WAL safety | ÄÃƒ HOÃ€N THÃ€NH (57/57 tests) |
| P2-13 Screen Vision | ðŸŸ¡ MOCK | Test vá»›i camera/mÃ n hÃ¬nh tháº­t Ã­t nháº¥t 1 láº§n | Tháº¥p |
| P2-16 Comms Hub | ðŸŸ¡ MOCK | Sau khi cÃ³ token tháº­t | Trung bÃ¬nh |
| P2-17 Smart Home | ðŸŸ¡ MOCK | Sau khi cÃ³ HA test instance | Tháº¥p |
| E8-b (wake word biÃªn) | ðŸ”´ ChÆ°a audit | Thu máº«u giá»ng kháº½/qua loa | Trung bÃ¬nh |
| Computer Vision | ðŸ”´ ChÆ°a audit | Benchmark FPS tháº­t + Ä‘Ã¡nh giÃ¡ rá»§i ro riÃªng tÆ° | Tháº¥p-Trung bÃ¬nh |

### Viá»‡c kiá»ƒm tra bá»• sung cho module Ä‘Ã£ "Done"
- **A1 (scanner.py)**: khi cÃ i TShark, test `_parse_tshark_protocols()` vá»›i output tháº­t.
- **E6 (subprocess encoding)**: xÃ¡c nháº­n encoding tháº­t cá»§a Windows console â€” chÆ°a cÃ³ xÃ¡c nháº­n dá»©t Ä‘iá»ƒm.

---

## PHáº¦N 3 â€” Äá»€ XUáº¤T NÃ‚NG Cáº¤P

### Ngáº¯n háº¡n
1. Rate-limiting cho 4 kÃªnh comms (Telegram/Zalo/Discord/Mobile) â€” **ÄÃƒ HOÃ€N THÃ€NH** (22/22 tests passing).
2. Äá»•i tÃªn "Vector Store" â†’ "Lexical Search" trong tÃ i liá»‡u ngÆ°á»i dÃ¹ng (TF-IDF khÃ´ng pháº£i RAG) â€” **ÄÃƒ HOÃ€N THÃ€NH**.
3. Migrate `.env` â†’ Windows Credential Manager (`SecretsManager` Ä‘Ã£ viáº¿t nhÆ°ng chÆ°a wire production) â€” **ÄÃƒ HOÃ€N THÃ€NH**.

### Trung háº¡n (chá»‰ sau khi Router eval #40 xong)
4. TieredSTTEngine (fast/accurate 2 táº§ng) â€” **ÄÃƒ HOÃ€N THÃ€NH**.
5. Äo WER/Intent Misrouting Rate theo domain Ä‘Ã³ng cho bá»™ test má»›i.
6. NÃ¢ng P2-12 Memory lÃªn Tier 1 báº±ng stress-test concurrency cÃ³ kiá»ƒm tra dá»¯ liá»‡u â€” **ÄÃƒ HOÃ€N THÃ€NH** (57/57 tests passing).

### DÃ i háº¡n
7. Windows Code Signing (Authenticode).
8. Local ONNX Embedding thay TF-IDF náº¿u cáº§n semantic search tháº­t sá»±.
9. On-demand model download Ä‘á»ƒ giáº£m kÃ­ch thÆ°á»›c installer.
10. ÄÃ¡nh giÃ¡ Browser Automation vá» Prompt Injection (vector V3 tá»« threat model, chÆ°a cÃ³ giáº£i phÃ¡p).

---

## PHáº¦N 4 â€” TRÃŒNH Tá»° THá»°C THI

```
TUáº¦N NÃ€Y (khÃ´ng cáº§n chá» ai):
  [ ] 1.1 Router eval (90 file + 20 cÃ¢u má»›i) â€” BÃO CÃO Káº¾T QUáº¢ TRÆ¯á»šC
  [ ] 1.2 Sandbox dry-run cho synthesizer
  [ ] 1.3 Full test suite láº§n cuá»‘i
  [ ] 1.4 CÃ i pytest-asyncio, TShark, playwright
  [ ] 1.5 Má»Ÿ CDP port 9222, cháº¡y láº¡i 2 test browser
  [x] 1.6 Má»Ÿ rá»™ng grep fabrication & Kiá»ƒm toÃ¡n toÃ n diá»‡n 7 phÃ¢n há»‡ â€” ÄÃƒ HOÃ€N THÃ€NH (FULL_FEATURE_AUDIT_REPORT.md & test_audit_adversarial_probes.py)
  [x] NÃ¢ng cáº¥p ngáº¯n háº¡n #1 (rate-limit), #2 (Ä‘á»•i tÃªn Vector Store) â€” ÄÃƒ HOÃ€N THÃ€NH
  [x] NÃ¢ng cáº¥p ngáº¯n háº¡n #3 (migrate secrets) â€” ÄÃƒ HOÃ€N THÃ€NH

SAU KHI CÃ“ THÃ”NG TIN Tá»ª NGÆ¯á»œI DÃ™NG (B1/B2/C1):
  [ ] 1.7-1.9 theo thá»© tá»± thÃ´ng tin nháº­n Ä‘Æ°á»£c
  [ ] NÃ¢ng P2-16, P2-17 lÃªn Tier cao hÆ¡n

SAU KHI ROUTER EVAL XONG (#40 Ä‘Ã³ng):
  [x] NÃ¢ng cáº¥p trung háº¡n #4 (TieredSTTEngine) â€” ÄÃƒ HOÃ€N THÃ€NH (11/11 tests, VAD silence gating, SNR gating, multi-tier fallback)
  [x] NÃ¢ng cáº¥p trung háº¡n #6 (P2-12 Memory Tier 1) â€” ÄÃƒ HOÃ€N THÃ€NH (57/57 tests passing, atomic persistence)
  [ ] #5 (WER biÃªn) náº¿u cáº§n thÃªm Ä‘á»™ chÃ­nh xÃ¡c

DÃ€I Háº N:
  [ ] #7-10 theo lá»‹ch phÃ¡t triá»ƒn tá»± chá»n
```

---

## GHI CHÃš QUAN TRá»ŒNG

- **KhÃ´ng báº¯t Ä‘áº§u TieredSTTEngine trÆ°á»›c khi Router eval xong** â€” nguy cÆ¡ hard-code ngÆ°á»¡ng tÃ¹y tiá»‡n (báº«y #9 trong AUDIT_FRAMEWORK.md).
- **Má»i module chuyá»ƒn Tier pháº£i theo Ä‘Ãºng quy trÃ¬nh 7 bÆ°á»›c** trong AUDIT_FRAMEWORK.md.
- **Káº¿t quáº£ nÃ o cÅ©ng cáº§n Ä‘á»‘i chiáº¿u vá»›i AUDIT_FRAMEWORK.md trÆ°á»›c khi bÃ¡o cÃ¡o** â€” dÃ¹ng "CÃ¢u há»i tá»± kiá»ƒm tra" nhÆ° checklist báº¯t buá»™c.

---

*Káº¿ hoáº¡ch nÃ y tá»•ng há»£p toÃ n bá»™ hÃ nh Ä‘á»™ng cÃ²n treo, káº¿t há»£p vá»›i AUDIT_FRAMEWORK.md. Cáº­p nháº­t pháº§n "Tráº¡ng thÃ¡i hiá»‡n táº¡i" má»—i khi hoÃ n thÃ nh má»™t má»¥c.*

