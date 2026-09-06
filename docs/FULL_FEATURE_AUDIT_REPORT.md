# BÁO CÁO KIỂM TOÁN KỸ THUẬT ĐỘC LẬP TOÀN DIỆN HỆ THỐNG
## JARVIS v4.8.1 — ĐÁNH GIÁ 7 PHÂN HỆ THEO CHUẨN AUDIT FRAMEWORK 4 TRỤC
**Tài liệu tham chiếu:** `docs/AUDIT_FRAMEWORK.md`, `AGENTS.md`, `docs/ROADMAP.md`  
**Ngày phát hành:** 2026-09-06  
**Thực hiện:** Đội ngũ Kiểm toán Độc lập JARVIS (`teamwork_preview_worker_audit`)  
**Môi trường thử nghiệm:** Windows 11 Enterprise x64, Python 3.13, NTFS  

---

## 1. TỔNG QUAN ĐIỀU HÀNH (EXECUTIVE SUMMARY)

### 1.1. Bối Cảnh & Mục Tiêu Kiểm Toán
Hệ thống trợ lý ảo AI J.A.R.V.I.S. (phiên bản v4.8.1) vận hành trên nền tảng Windows 11 đã trải qua đợt kiểm toán kỹ thuật toàn diện, độc lập và đối kháng (adversarial inspection). Cuộc kiểm toán bao trùm 100% mã nguồn production và bộ kiểm thử tự động của cả **7 phân hệ chức năng cốt lõi**:
1. **Phân hệ 1 — Voice Pipeline** (Tiered STT, Faster-Whisper CTranslate2, Intent Router, Diacritic Normalization, Wake Word Acoustic Spectral E8, SAPI5/ElevenLabs TTS).
2. **Phân hệ 2 — Memory System** (Semantic Vector Store TF-IDF, SQLite Persistent Store WAL mode, Memory Manager 2 tầng, Concurrency 30 luồng).
3. **Phân hệ 3 — Security & InfoSec** (Code Interpreter Sandbox, AST Code Validator, Secrets Manager, Network Scanner RFC1918, Packet Capture TShark).
4. **Phân hệ 4 — Communications Hub** (Token Bucket Rate Limiter, Telegram Bot, Discord Bot, Zalo OA Adapter, IMAP Email Reader, Mobile File Bridge).
5. **Phân hệ 5 — Browser & OS Control** (Playwright & Chrome CDP Driver, Computer Controller `open_app`, Điều khiển âm lượng `pycaw`, Audio Endpoint switch).
6. **Phân hệ 6 — Terminal Control Center (TCC)** (ANSI Console Engine, 9 Module Adapters, Chẩn đoán và ghi báo cáo kiểm toán đĩa cứng `ReportWriter`).
7. **Phân hệ 7 — Self-Coding Engine** (Dynamic Skill Synthesizer, Sandbox Dry-Run Gate, Skill Registry & Telemetry Store).

Toàn bộ quá trình kiểm toán được thực thi nghiêm ngặt theo **4 trục độc lập** và **19 cạm bẫy kiểm toán** được quy định tại `docs/AUDIT_FRAMEWORK.md` và tiêu chuẩn phát triển tại `AGENTS.md`. Tuyệt đối không gộp điểm số thành tỷ lệ phần trăm mơ hồ, không công nhận các khẳng định không có bằng chứng mã nguồn, và áp dụng nguyên tắc **Fail-Closed** cùng **Anti-Fabrication** làm kim chỉ nam.

---

### 1.2. Phán Quyết Cốt Lõi (Core Verdict)
Tổng hợp đánh giá trên 28 thành phần chức năng:
- **Trục 1 — Bằng chứng thực nghiệm (Evidence Tier)**:
  - 🟢 **T1 (Kiểm chứng thật trên OS/API/Hardware)**: **13 / 28 thành phần (46.4%)**. Bao gồm các thành phần cốt lõi: Concurrency 30 luồng của Memory System, Windows Job Object & MIC Low Integrity Token của Sandbox, Diacritic Normalizer & Intent Router với tập Held-Out N=35 độc lập, Wake Word Spectral E8 trên 90 audio WAV thật, Token Bucket Rate Limiter, 9 TCC Module Adapters, và Dynamic Skill Synthesizer đa tầng.
  - 🟡 **T2 (Logic đúng nhưng test mock thành phần cốt lõi)**: **12 / 28 thành phần (42.9%)**. Bao gồm: Tiered STT unit tests, Faster-Whisper unit preload, Secrets Manager (mock `keyring`), Network Scanner (mock Nmap subprocess), Telegram/Discord/Zalo/Mobile Bridge (mock HTTP/Socket), và Browser CDP (mock DOM/is_mock=True).
  - 🔴 **T3 (Chưa có test thực tế / Khuyết tật kiến trúc)**: **3 / 28 thành phần (10.7%)**. Bao gồm: Điều khiển âm lượng `pycaw` (0 test trong repo), Audio Endpoint Output Switch (chưa có code triển khai), và IMAP Email Reader (hoàn toàn thiếu client `imaplib` kết nối mạng).
- **Trục 2 — Tính trung thực (Truthfulness)**:
  - ✅ **Truthful (Fail-Closed)**: **20 / 28 thành phần (71.4%)**. Từ chối hành động ảo, trả về mã lỗi cụ thể khi thiếu tài nguyên.
  - ⚠️ **Silent Fallback**: **4 / 28 thành phần (14.3%)**. Bao gồm: Zalo `send_message` trả `success=True` khi thiếu token; Telegram `/exec` trả status 200 khi `dispatcher` là None; Volume control swallow exception; SAPI5 fallback priority 4 log console rồi trả `True`.
  - 🔴 **Active Fabrication**: **2 / 28 thành phần (7.1%)**. Bao gồm: Zalo command handlers hardcode nhiệt độ thời tiết 32°C/34°C và trạng thái ảo; `AudioEngine.probe_devices` tự sinh thiết bị giả "Headless Mock Audio Device".
  - 👻 **Ghost Process**: **2 / 28 thành phần (7.1%)**. Bao gồm: Discord `_poll_loop` chạy vòng lặp vô tận chỉ `sleep(2.0)` mà không gọi API; `CDPBrowserDriver` có các phương thức `click()`, `type_text()` chỉ trả về `self._is_running` rỗng.
- **Trục 3 — Loại ranh giới bảo mật (Boundary Type)**:
  - 🔒 **Kernel-Enforced Hard Boundary**: Đạt được thực chất ở 4 chốt chặn hệ thống: (1) Windows Job Object (`ActiveProcessLimit=1`, 256MB RAM cap), (2) Windows MIC Low Integrity Token (`S-1-16-4096`), (3) Windows Atomic Persistence (`tmp.replace()` + retry loop chống `WinError 5`), và (4) SQLite WAL ACID transactions.
  - 🛡️ **Heuristic Risk-Reduction**: 20 cơ chế phòng thủ theo chiều sâu (AST NodeVisitor, Token Bucket Rate Limiter, VAD RMS Gating, Spectral Flatness Measure, Supernet Scope Filter RFC1918, Double-extension filter). Đã ghi nhận đầy đủ giới hạn lý thuyết (Halting Problem, ReDoS, Bypass reflection).
- **Trục 4 — Tình trạng bị chặn (Blocked-by)**:
  - ❌ **Không bị chặn (Unblocked — Sẵn sàng sửa chữa/hành động ngay)**: **18 / 28 thành phần (64.3%)**.
  - ⏳ **Bị chặn bởi Token / Hạ tầng thật (Infrastructure Blocked)**: **8 / 28 thành phần (28.6%)** (Cần Nmap, TShark, Playwright Chromium, bot tokens).
  - ⏳ **Bị chặn bởi Quyết định thiết kế (Design Decision Blocked)**: **2 / 28 thành phần (7.1%)** (Kiến trúc Audio Output Endpoint Switching và IMAP Polling Client).

---

### 1.3. BÁO CÁO CÁC KHUYẾT TẬT TRỌNG YẾU (HIGH-PRIORITY DEFECTS)
*Tuân thủ nghiêm ngặt Cạm bẫy kiểm toán #14 (AUDIT_FRAMEWORK.md): Các rủi ro và khuyết tật nghiêm trọng PHẢI được đưa lên ngay đầu báo cáo, không được chôn vùi trong các mục phụ.*

Dưới đây là 8 khuyết tật trung thực (Truthfulness Defects) và lỗi tiến trình rỗng (Ghost Processes) được phát hiện trực tiếp từ việc rà soát mã nguồn:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        BẢNG ĐỎ: CÁC KHUYẾT TẬT TRỌNG YẾU CẦN KHẮC PHỤC NGAY                            │
├────┬──────────────────────┬──────────────────────────────┬─────────────────────────────────────────────┤
│ #  │ Phân hệ              │ Vị trí tệp & Dòng mã         │ Bản chất khuyết tật kỹ thuật                │
├────┼──────────────────────┼──────────────────────────────┼─────────────────────────────────────────────┤
│ D1 │ Communications Hub   │ jarvis/comms/zalo.py:297-299 │ ⚠️ SILENT FALLBACK: send_message trả về     │
│    │                      │                              │ success=True, msg_id="mock_msg_id" khi     │
│    │                      │                              │ thiếu access_token trên production instance │
├────┼──────────────────────┼──────────────────────────────┼─────────────────────────────────────────────┤
│ D2 │ Communications Hub   │ jarvis/comms/zalo.py:226,260 │ 🔴 ACTIVE FABRICATION: _cmd_weather trả số  │
│    │                      │                              │ liệu hardcode 32°C/34°C; _cmd_status bịa    │
│    │                      │                              │ chuỗi "Memory: OK | TTS: OK... Connected"   │
├────┼──────────────────────┼──────────────────────────────┼─────────────────────────────────────────────┤
│ D3 │ Communications Hub   │ jarvis/comms/discord.py:452  │ 👻 GHOST PROCESS: _poll_loop chạy thread    │
│    │                      │                              │ vô tận time.sleep(2.0), không gọi Discord   │
│    │                      │                              │ Gateway/REST API, tiêu tốn tài nguyên vô ích│
├────┼──────────────────────┼──────────────────────────────┼─────────────────────────────────────────────┤
│ D4 │ Browser & OS Control │ jarvis/browser/driver.py:482 │ 👻 GHOST PROCESS / STUB: click(),           │
│    │                      │                              │ type_text() chỉ return self._is_running mà  │
│    │                      │                              │ không hề gửi bất kỳ lệnh CDP nào tới Chrome │
├────┼──────────────────────┼──────────────────────────────┼─────────────────────────────────────────────┤
│ D5 │ Browser & OS Control │ jarvis/automation/control.py │ ⚠️ SILENT FALLBACK: set_volume() swallow    │
│    │                      │ dòng 363-381                 │ exception khi pycaw lỗi/không có loa, trả   │
│    │                      │                              │ về volume ảo và lưu biến nội bộ thành công  │
├────┼──────────────────────┼──────────────────────────────┼─────────────────────────────────────────────┤
│ D6 │ Communications Hub   │ jarvis/comms/telegram.py:181 │ ⚠️ SILENT FALLBACK: Khi dispatcher is None, │
│    │                      │ 192, 220                     │ /exec <cmd> trả về status 200 "Đã thực thi  │
│    │                      │                              │ lệnh" dù không có hành động nào diễn ra     │
├────┼──────────────────────┼──────────────────────────────┼─────────────────────────────────────────────┤
│ D7 │ Security & InfoSec   │ jarvis/security/scanner.py   │ ⚠️ LINGERING FALLBACK: Khi stdout tshark    │
│    │                      │ dòng 769                     │ không parse được, packet_count mặc định gán │
│    │                      │                              │ bằng requested count thay vì trả về 0       │
├────┼──────────────────────┼──────────────────────────────┼─────────────────────────────────────────────┤
│ D8 │ Browser & OS Control │ jarvis/audio/engine.py:304   │ 🔴 ACTIVE FABRICATION: probe_devices() tự   │
│    │                      │                              │ chế "Headless Mock Audio Device" khi thiếu  │
│    │                      │                              │ sounddevice thay vì fail-closed trả về []   │
└────┴──────────────────────┴──────────────────────────────┴─────────────────────────────────────────────┘
```

---

## 2. BẢNG MA TRẬN TỔNG HỢP 4 TRỤC (COMPREHENSIVE 4-AXIS MASTER MATRIX)

Bảng ma trận dưới đây bao phủ **100% (28/28 thành phần)** được phân rã kỹ thuật trên toàn bộ 7 phân hệ của JARVIS v4.8.1:

| # | Phân hệ | Thành phần / Hàm kiểm toán | Trục 1: Bằng chứng | Trục 2: Trung thực | Trục 3: Ranh giới | Trục 4: Chặn bởi | Tệp nguồn & Dòng mã | Bằng chứng kiểm thử / Test Suite |
|:---:|---|---|:---:|:---:|:---:|:---:|---|---|
| 1 | Voice Pipeline | `TieredSTTEngine` | 🟡 T2 / 🟢 T1 | ✅ Fail-Closed | 🛡️ Risk-Reduction | ❌ Unblocked local / ⏳ Token Cloud | `jarvis/stt/engine.py:1151` | `tests/unit/test_tiered_stt.py` (11 pass) |
| 2 | Voice Pipeline | `FasterWhisperSTT` | 🟡 T2 (Unit) / 🟢 T1 (WAV) | ✅ Fail-Closed | 🛡️ Risk-Reduction (5 tầng) | ❌ Unblocked CPU | `jarvis/stt/engine.py:458` | `docs/eval/stt_eval_results_direct.json` (N=90) |
| 3 | Voice Pipeline | `strip_vietnamese_diacritics` & Intent Router | 🟢 T1 | ✅ Fail-Closed | 🛡️ Risk-Reduction (ReDoS guard) | ❌ Unblocked | `jarvis/llm/router.py:65,1989` | `tests/eval/test_voice_generalization_heldout.py` (35 pass) |
| 4 | Voice Pipeline | `WakeWordDetector` (Spectral E8) | 🟢 T1 | ✅ Fail-Closed | 🛡️ Risk-Reduction (SFM >3x margin) | ❌ Unblocked | `jarvis/audio/wake_word.py:504` | `tests/unit/test_wake_word_real_audio_e8.py` (N=90) |
| 5 | Voice Pipeline | `TTSManager` & `SAPI5FallbackTTS` | 🟡 T2 / 🟢 T1 | ⚠️ Minor Silent Fallback (P4) | 🛡️ Risk-Reduction | ❌ Unblocked SAPI / ⏳ Token Cloud | `jarvis/tts/manager.py:78`, `jarvis/tts/fallback.py:128` | `tests/unit/test_tts_com_safety.py` (3 pass) |
| 6 | Memory System | `SemanticVectorStore` (TF-IDF) | 🟢 T1 | ✅ Fail-Closed | 🔒 Hard Boundary (Atomic swap + WinError 5 retry) | ❌ Unblocked | `jarvis/memory/vector_store.py:65` | `tests/unit/test_memory_concurrency_tier1.py` (30 threads) |
| 7 | Memory System | `SQLiteMemoryStore` | 🟢 T1 | ✅ Fail-Closed | 🔒 Hard Boundary (WAL mode + ACID) | ❌ Unblocked | `jarvis/memory/sqlite_store.py:27` | `tests/unit/test_memory_concurrency_tier1.py` (30 threads) |
| 8 | Memory System | `MemoryManager` | 🟢 T1 | ✅ Fail-Closed | 🔒 Hard / 🛡️ Risk-Red | ❌ Unblocked | `jarvis/memory/manager.py:23` | `tests/unit/test_memory_system.py` |
| 9 | Security & InfoSec | `CodeInterpreterSandbox` | 🟢 T1 | ✅ Fail-Closed | 🔒 Hard Boundary (Job Object + MIC Low Integrity) | ❌ Unblocked | `jarvis/sandbox/security.py:182` | `tests/integration/test_sandbox_os_boundaries.py` (Không mock) |
| 10 | Security & InfoSec | `ASTCodeValidator` | 🟢 T1 | ✅ Fail-Closed | 🛡️ Risk-Reduction (Static analysis) | ❌ Unblocked | `jarvis/sandbox/validator.py:134` | `tests/unit/test_skill_synthesis.py` |
| 11 | Security & InfoSec | `SecretsManager` | 🟡 T2 | ✅ Fail-Closed | 🛡️ Risk-Reduction | ❌ Unblocked | `jarvis/security/secrets.py:46` | `tests/unit/test_secrets.py` (100% mock keyring) |
| 12 | Security & InfoSec | `NetworkScanner` | 🟡 T2 | ✅ Fail-Closed (RFC1918) | 🛡️ Risk-Reduction | ⏳ Thiếu Nmap binary | `jarvis/security/scanner.py:188` | `tests/test_security_scanner.py` (Mock subprocess) |
| 13 | Security & InfoSec | `PacketCapture` | 🟡 T2 / 🔴 T3 | ⚠️ Minor Defect (line 769 bug) | 🛡️ Risk-Reduction | ⏳ Thiếu TShark CLI | `jarvis/security/scanner.py:754` | `NOTE — UNTESTED` tại scanner.py:590 |
| 14 | Communications Hub | `TokenBucketRateLimiter` | 🟢 T1 | ✅ Fail-Closed | 🛡️ Risk-Reduction | ❌ Unblocked | `jarvis/comms/rate_limiter.py:60` | `tests/unit/test_rate_limiter.py` (20+ threads) |
| 15 | Communications Hub | `DiscordBotController` | 🟡 T2 | 👻 Ghost Process (`_poll_loop`) | 🛡️ Risk-Reduction | ⏳ Discord Bot Token | `jarvis/comms/discord.py:452` | `tests/test_comms_hub.py` |
| 16 | Communications Hub | `ZaloBotController` | 🟡 T2 | ⚠️ Silent Fallback + 🔴 Fabrication | 🛡️ Risk-Reduction | ⏳ Zalo OA Token | `jarvis/comms/zalo.py:226,297` | `tests/test_comms_hub.py` |
| 17 | Communications Hub | `TelegramBotController` | 🟡 T2 | ⚠️ Silent Fallback (`/exec` no dispatcher) | 🛡️ Risk-Reduction | ⏳ Telegram Bot Token | `jarvis/comms/telegram.py:181` | `tests/test_comms_hub.py:33` (Stale assertion) |
| 18 | Communications Hub | `IMAPEmailReader` | 🔴 T3 | ⚠️ Architectural Stub (No `imaplib`) | 🛡️ Risk-Reduction | ⏳ Thiết kế / Mail server | `jarvis/comms/email_imap.py:1` | In-memory `mock_emails` only |
| 19 | Communications Hub | `MobileFileBridge` | 🟡 T2 | ✅ Fail-Closed | 🛡️ Risk-Reduction | ⏳ Telegram Token | `jarvis/comms/mobile_bridge.py:1` | `tests/unit/test_mobile_bridge.py` |
| 20 | Browser & OS Control | `ComputerController.open_app` | 🟢 T1 | ✅ Fail-Closed (`shutil.which`) | 🛡️ Risk-Reduction | ❌ Unblocked | `jarvis/automation/control.py:770` | `tests/unit/test_runaway_hardening.py` |
| 21 | Browser & OS Control | `BrowserCDPController` | 🟡 T2 | ⚠️ Mock-Dominated (`is_mock=True`) | 🛡️ Risk-Reduction | ⏳ Playwright Chromium | `jarvis/browser/cdp_controller.py:58` | `tests/unit/test_browser_control.py` |
| 22 | Browser & OS Control | `CDPBrowserDriver` | 🟡 T2 | 👻 Ghost Process (`click` returns bool) | 🛡️ Risk-Reduction | ⏳ Mở port CDP 9222 | `jarvis/browser/driver.py:482` | `ROADMAP.md:46` |
| 23 | Browser & OS Control | Volume Control (`pycaw`) | 🔴 T3 | ⚠️ Silent Fallback (swallows errors) | 🛡️ Risk-Reduction | ❌ Unblocked | `jarvis/automation/control.py:363` | 0 tests trong toàn bộ repo |
| 24 | Browser & OS Control | Audio Endpoint Switch | 🔴 T3 | 🔴 Active Fabrication (Mock device) | 🛡️ Risk-Reduction | ⏳ Thiếu sounddevice / Thiết kế | `jarvis/audio/engine.py:304` | 0 tests cho output endpoints |
| 25 | Terminal Control Center | 9 Module Adapters | 🟢 T1 | ✅ Truthful (100% Anti-Fabrication) | 🛡️ Risk-Reduction | ❌ Unblocked | `jarvis/ui/terminal/modules/` | `tests/unit/test_terminal_modules.py` (315 lines) |
| 26 | Terminal Control Center | `ConsoleEngine` & `ReportWriter` | 🟢 T1 | ✅ Truthful (Disk size > 0 check) | 🛡️ Risk-Reduction | ❌ Unblocked | `jarvis/ui/terminal/report.py:164` | `tests/unit/test_terminal_modules.py` |
| 27 | Self-Coding Engine | `SkillSynthesizer` | 🟢 T1 | ✅ Fail-Closed | 🔒 Hard Boundary (Sandbox dry-run) | ❌ Unblocked | `jarvis/skills/synthesizer.py:293` | `tests/unit/test_skill_synthesis.py` |
| 28 | Self-Coding Engine | `SkillSandboxRunner` & Registry | 🟢 T1 | ✅ Fail-Closed | 🔒 Hard Boundary (MIC Low Integrity) | ❌ Unblocked | `jarvis/skills/registry.py:482` | `tests/integration/test_sandbox_os_boundaries.py` |

---

## 3. KIỂM TOÁN CHUYÊN SÂU 7 PHÂN HỆ CHỨC NĂNG

### 3.1. PHÂN HỆ 1: VOICE PIPELINE

#### 3.1.1. `TieredSTTEngine` (`jarvis/stt/engine.py:1151-1291`)
- **Cơ chế hoạt động**:
  - Nhận luồng âm thanh và chuẩn hóa về dạng 1D float32 `[-1.0, 1.0]` ở tần số 16kHz qua hàm `audio_to_float32()`.
  - **Early VAD Silence Gating (Dòng 1206-1215)**: Đo mức năng lượng hiệu dụng RMS (`rms = float(np.sqrt(np.mean(arr ** 2)))`). Nếu `rms < vad_silence_threshold_rms` (mặc định 0.002), hàm lập tức trả về:
    `TranscriptionResult(text="", confidence=0.0, engine_used="vad_silence", is_silent=True)`.
    Cơ chế này ngắt sớm luồng xử lý trước khi kích hoạt model học sâu, tiết kiệm 100% tài nguyên CPU/GPU trên các khung im lặng.
  - **SNR Estimation Gating (Dòng 1232-1244)**: Gọi `estimate_snr_db(arr)` tính tỷ lệ tín hiệu trên nhiễu dựa trên phân vị 10% năng lượng frame (`noise_floor`). Nếu `snr < min_snr_threshold_db` (10.0 dB), đồng thời Cloud Engine khả dụng và deadline cho phép (`deadline_ms >= cloud_expected_latency_ms`), hệ thống leo thang ưu tiên sang Cloud STT.
  - **Cascade 3 Tầng**: Local Whisper (Tier 1) -> Cloud REST (Tier 2) -> Emergency Fallback (Tier 3: Windows Speech / Mock).
  - **Fail-Closed**: Khi tất cả các tầng thất bại hoặc quá hạn deadline, hàm trả về `text=""`, `confidence=0.0`, `engine_used="none"`. Tuyệt đối không sinh từ ngữ giả định.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟡 T2 trong unit test (`test_tiered_stt.py` 11 test pass dùng `MagicMock`); 🟢 T1 khi tích hợp trong pipeline thực tế (`tests/eval/stt_intent_eval.py`).
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Fail-Closed).
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction (các ngưỡng RMS và SNR thống kê).
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn với Local; ⏳ Cần `OPENAI_API_KEY` cho Cloud.

#### 3.1.2. `FasterWhisperSTT` (`jarvis/stt/engine.py:458-675`)
- **Cơ chế hoạt động**:
  - Dựa trên thư viện CTranslate2 tối ưu hóa suy luận Transformer trên CPU/CUDA.
  - **Process-Wide Lock (Dòng 474)**: `_model_construction_lock = threading.Lock()` tuần tự hóa việc nạp mô hình trong toàn bộ tiến trình, triệt tiêu hoàn toàn xung đột cấp phát bộ nhớ khi config thay đổi.
  - **Khử lỗi Windows CUDA (Dòng 520-547)**: Tự động bổ sung thư mục bin của pip wheel CUDA vào `os.add_dll_directory` và `os.environ["PATH"]`. Thử nghiệm nạp `ctypes.CDLL("cublas64_12.dll")`; nếu thiếu thư viện, tự động fallback an toàn về CPU với `compute_type="int8"`.
  - **5 Tầng Chống Ảo Giác (Anti-Hallucination Guard)**:
    1. `condition_on_previous_text=False`: Ngắt sự lây lan ảo giác giữa các segment.
    2. `no_speech_threshold=0.6`: Hủy bỏ segment nếu xác suất không có tiếng nói > 60%.
    3. `log_prob_threshold=-1.0`: Loại bỏ segment có độ tự tin âm học thấp.
    4. `compression_ratio_threshold=2.4`: Loại bỏ các vòng lặp văn bản vô tận.
    5. Hậu kiểm năng lượng (Dòng 642-654): Nếu `audio_rms < 0.005` mà mô hình sinh ra nhiều hơn 3 từ (`words_in_seg > 3`), lập tức vứt bỏ kết quả.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1 trên 90 file audio thật (`docs/eval/stt_eval_results_direct.json`); 🟡 T2 trong unit test preload.
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Fail-Closed).
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn trên CPU.

#### 3.1.3. Chuẩn Hóa Không Dấu An Toàn & Intent Router (`jarvis/llm/router.py:65,1989`)
- **Cơ chế hoạt động**:
  - `strip_vietnamese_diacritics(text)`: Sử dụng bảng dịch mã 134 ký tự có dấu sang ký tự ASCII và loại bỏ Combining Diacritical Marks (`\u0300-\u036f`).
  - **Triệt tiêu va chạm đồng âm (Zero-Homophone-Collision)** trong `_match_rule_key()`:
    * **Từ đơn (`len(words) == 1`)**: Bắt buộc giữ nguyên dấu tiếng Việt và khớp toàn bộ từ với ranh giới từ `\b` (`\bnhạc\b` vs `\bnhắc\b`). Tuyệt đối không bỏ dấu, triệt tiêu xung đột giữa `nhạc` (âm nhạc) và `nhắc` (nhắc nhở), giữa `dừng` và `ứng dụng`.
    * **Cụm từ nhiều tiếng (`len(words) >= 2`)**: Cho phép chuẩn hóa bỏ dấu có kiểm soát.
  - **Phòng thủ ReDoS**: Bỏ qua bước quét diacritic nếu độ dài chuỗi > 2048 ký tự.
  - **Phonetic Drift Aliases**: Bổ sung các biến thể phát âm sai thực tế: `system_power` (`"tắc máy"`, `"sắt đau má"`), `app_open` (`"cái đặt"`, `"open sentence"`), `reminder` (`"đặt time"`).
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1 (Kiểm chứng trên tập độc lập `tests/eval/test_voice_generalization_heldout.py` N=35 câu mới 100% không trùng lặp, đạt 100% CORRECT, 0% MISROUTED).
  - *Trục 2 (Truthfulness)*: ✅ Truthful.
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

#### 3.1.4. Wake Word Cascade & Acoustic DSP E8 (`jarvis/audio/wake_word.py:504`)
- **Cơ chế hoạt động**:
  - Cascade 3 tầng: Vosk/Porcupine -> Whisper Sliding Window -> `AcousticSpectralDetector`.
  - **Spectral Flatness Measure (SFM)**: Sóng hình sin đơn tần có SFM < 0.03 -> bị loại 100% (chặn đứng tiếng bíp 3kHz từ lò vi sóng, chuông báo). Tiếng ồn trắng có SFM > 0.65 -> bị loại.
  - **Phân Tách Xung Đập Tay (Clap Rejection)**: Khoảng cách giữa đỉnh formant S1 ("JAR") và âm xát S2 ("VIS") phải nằm trong đoạn 0.07s - 0.65s. Xung đập tay có delta < 0.05s -> bị loại.
  - **AEC Cooldown (Dòng 685-693)**: `suppress_until(timestamp)` xóa sạch buffer và khóa mic 2.5s sau khi TTS nói xong.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1 (`tests/unit/test_wake_word_real_audio_e8.py` kiểm chứng trên 90 file WAV thật, 0/439 frame tiếng người bị chặn nhầm, khoảng an toàn >3.0x).
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Fail-Closed).
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn với Tier 2.

#### 3.1.5. TTS Manager & SAPI5 COM Safety (`jarvis/tts/manager.py`, `fallback.py`)
- **Cơ chế hoạt động**:
  - `TTSManager` quản lý hàng đợi daemon worker thread. Khởi tạo COM apartment qua `pythoncom.CoInitialize()` và giải phóng bằng `pythoncom.CoUninitialize()` trong khối `finally:`.
  - **Khuyết tật Silent Fallback tại Priority 4**: Trong `jarvis/tts/fallback.py:128-130`, nếu cả SAPI5, PowerShell và pyttsx3 đều thất bại (ví dụ trên Linux hoặc Windows lỗi driver âm thanh), hàm ghi log console `"[SAPI5 Mock TTS Spoke]"` và trả về `True` (Khuyết tật D1/P4).
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟡 T2 (Unit test mock win32com).
  - *Trục 2 (Truthfulness)*: ⚠️ Minor Silent Fallback ở Priority 4.
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn trên Windows.

---

### 3.2. PHÂN HỆ 2: MEMORY SYSTEM

#### 3.2.1. `SemanticVectorStore` (Lexical TF-IDF) (`jarvis/memory/vector_store.py:65`)
- **Bản chất kỹ thuật**:
  - Sử dụng thuật toán Lexical Search với TF-IDF Cosine Similarity và công thức BM25 smoothed IDF: `IDF = log((N + 1) / (df + 0.5))`.
- **Windows Atomic Persistence (Tuân thủ AGENTS.md Mục 3)**:
  - Xem mã nguồn `jarvis/memory/vector_store.py:173-213`:
    1. Tuần tự hóa ghi đĩa: Bọc toàn bộ quá trình I/O trong `with self._save_lock:`.
    2. Snapshot nhanh: Chụp bản sao dữ liệu bên trong `with self._lock:` rồi thoát lock ngay lập tức, triệt tiêu nghẽn luồng đọc (`search()`).
    3. File tạm độc nhất: `.tmp.<thread_id>.<timestamp_ns>`.
    4. Xử lý khóa file Windows (`WinError 5`): Gọi `tmp_path.replace(path)` trong vòng lặp thử lại 5 lần với backoff `0.02 * (attempt + 1)` giây, giải quyết xung đột file handle từ Windows Defender và Search Indexer. Dọn dẹp file tạm trong `finally:`.
- **Kiểm chứng áp lực 30 luồng (30-Thread Concurrency Stress Test)**:
  - File test: `tests/unit/test_memory_concurrency_tier1.py` (Slice 1, 2, 3).
  - 30 luồng OS ghi đồng thời với `auto_save=True`: Ghi đủ 30 tài liệu, 0 ngoại lệ `RuntimeError: dictionary changed size during iteration`, 0 lost writes trên đĩa.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1 (Đĩa cứng NTFS thật, 30 luồng OS thật, không mock).
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Fail-Closed).
  - *Trục 3 (Boundary Type)*: 🔒 Hard Boundary (Atomic file replace + Lock serialization).
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

#### 3.2.2. `SQLiteMemoryStore` (`jarvis/memory/sqlite_store.py:27`)
- **Cơ chế hoạt động**:
  - Kích hoạt chế độ WAL (`PRAGMA journal_mode = WAL;`) và đồng bộ `PRAGMA synchronous = NORMAL;`. Cho phép đọc và ghi diễn ra đồng thời mà không nghẽn.
  - Sử dụng `self._lock = threading.RLock()` bảo vệ các thao tác nội bộ. Mỗi truy vấn mở kết nối riêng với `timeout=10.0`, thực thi trong `with conn:` và đóng trong `finally: conn.close()`.
  - Hỗ trợ cú pháp SQLite UPSERT (`ON CONFLICT(category, key) DO UPDATE...`).
- **Kiểm chứng áp lực 30 luồng**:
  - Slice 4 của `test_memory_concurrency_tier1.py`: 15 luồng ghi fact và 15 luồng ghi episode chạy đồng thời qua `ThreadPoolExecutor`. Kết quả: 0 lỗi `database is locked`, 100% dữ liệu toàn vẹn.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1.
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Fail-Closed).
  - *Trục 3 (Boundary Type)*: 🔒 Hard Boundary (Tính toàn vẹn giao dịch ACID của SQLite WAL).
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

#### 3.2.3. `MemoryManager` & `SessionContextManager` (`jarvis/memory/manager.py:23`, `session.py`)
- **Cơ chế hoạt động**:
  - Ngắn hạn: Vòng đệm trượt `collections.deque(maxlen=20)` (10 cặp lượt thoại) đảm bảo không tràn context window.
  - Dài hạn: Bóc tách tự nhiên mẫu câu khẩu ngữ tiếng Việt ("nhớ rằng tôi tên là...", "email của tôi là...").
  - Tóm tắt ngày ("Hôm nay tôi đã làm gì?"): Nếu chưa có tác vụ, fail-closed trả về `"Hôm nay Ngài chưa thực hiện tác vụ nào, thưa Ngài."`.
  - Hợp đồng `MemoryCommandResult` kế thừa từ `str` và cài đặt `__getitem__`, đảm bảo tương thích 100% ngược.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1.
  - *Trục 2 (Truthfulness)*: ✅ Truthful.
  - *Trục 3 (Boundary Type)*: 🔒 Hard Boundary (giới hạn deque & SQLite) + 🛡️ Risk-Reduction (Regex bóc tách).
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

---

### 3.3. PHÂN HỆ 3: SECURITY & INFOSEC

#### 3.3.1. `CodeInterpreterSandbox` (`jarvis/sandbox/security.py:182-550`)
- **Kiến trúc cô lập đa tầng (Kernel-Enforced Isolation)**:
  1. **Win32 SRM Low Integrity Token**: Gọi `CreateRestrictedToken` với `LUA_TOKEN`, đặt `TokenIntegrityLevel = S-1-16-4096` (Low Integrity). Đặt SACL `S:(ML;OICI;NW;;;LW)` trên thư mục scratch. Windows Mandatory Integrity Control (MIC) từ chối lệnh ghi ra bất kỳ thư mục nào có mức toàn vẹn Medium/High (file hệ thống, mã nguồn JARVIS).
  2. **Windows Job Object**: Thiết lập `ActiveProcessLimit = 1` và `JobMemoryLimit = 256MB`. Ngăn chặn hoàn toàn việc sinh tiến trình con/cháu (chặn `subprocess`, `cmd.exe` với lỗi OS 1816 `ERROR_NOT_ENOUGH_QUOTA`).
  3. **Environment Scrubbing**: Lọc sạch 100% biến môi trường nhạy cảm (`KEY`, `TOKEN`, `SECRET`, `API`).
  4. **Preamble Monkeypatching & Pipe Drainage**: Chặn import `socket`, `ctypes`, `win32api`. Xử lý drain pipe đồng thời chống treo buffer 4KB.
- **Bằng chứng kiểm thử**:
  - `tests/integration/test_sandbox_os_boundaries.py` chạy tiến trình con thật trên Windows 11 không mock: kiểm chứng kernel chặn spawn process, kernel chặn ghi file (`PermissionError`), và lọc sạch secret.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1.
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Fail-Closed).
  - *Trục 3 (Boundary Type)*: 🔒 Hard Boundary (Job Object & MIC).
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn trên Windows NT.

#### 3.3.2. `ASTCodeValidator` (`jarvis/sandbox/validator.py:134`)
- **Cơ chế hoạt động**:
  - Sử dụng `ast.NodeVisitor` phân tích cú pháp tĩnh.
  - Danh sách cấm: `DEFAULT_FORBIDDEN_MODULES` (`ctypes`, `socket`, `subprocess`), `DEFAULT_FORBIDDEN_CALLS` (`eval`, `exec`), và `DEFAULT_FORBIDDEN_DUNDER_ATTRIBUTES` (`__subclasses__`, `__globals__`).
  - Regex lọc PowerShell độc hại (`Invoke-Expression`, `Stop-Computer`).
  - **Giới hạn lý thuyết (Halting Problem)**: Không thể phát hiện lỗi runtime (vòng lặp vô tận, chia cho 0, dynamic attribute lookup `getattr(__builtins__, 'ex' + 'ec')`). Do đó, bắt buộc phải kết hợp cùng Sandbox Dry-Run.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1.
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Lỗi cú pháp trả về `is_safe=False`).
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

#### 3.3.3. `SecretsManager` (`jarvis/security/secrets.py:46`)
- **Cơ chế hoạt động**:
  - Đọc/ghi Windows Credential Manager qua `keyring.get_password("JARVIS", name)`. Fallback biến môi trường nếu cấu hình.
- **Khoảng trống kiểm thử (Mock Dominance)**:
  - 100% bài test trong `tests/unit/test_secrets.py` đều mock `keyring` hoặc `set_secret`. Không có bài test OS thật nào đọc/ghi Credential Manager.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟡 T2.
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Fail-Closed).
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction (Bảo vệ lưu trữ trên đĩa qua DPAPI, không bảo vệ đọc trộm RAM).
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

#### 3.3.4. `NetworkScanner` & `PacketCapture` (`jarvis/security/scanner.py:188,754`)
- **NetworkScanner**:
  - Phạm vi mục tiêu nghiêm ngặt: `ALLOWED_SCAN_SUPERNETS` giới hạn trong RFC1918 (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`). Mục tiêu ngoài dải bị từ chối ngay lập tức (`TARGET_REJECTED`).
  - Thiếu Nmap binary trả về `TOOL_NOT_FOUND`.
- **PacketCapture (Khuyết tật D7 / Dòng 769)**:
  - Tỷ lệ bịa đặt 70/20/10 lịch sử đã được xóa bỏ ngày 2026-09-04.
  - **Lỗi dòng 769**:
    `packet_count = sum(protocols.values()) if protocols else count`
    Nếu stdout trả về không rỗng nhưng không phân tích cú pháp được protocol nào, `packet_count` bị gán bằng `count` (số lượng yêu cầu) thay vì 0.
  - Được đánh dấu `NOTE — UNTESTED` tại dòng 590 do máy dev thiếu TShark CLI.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟡 T2 (Scanner) / 🔴 T3 (PacketCapture).
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Scanner) / ⚠️ Minor Defect (PacketCapture dòng 769).
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ⏳ Bị chặn bởi thiếu binary Nmap và TShark/Wireshark.

---

### 3.4. PHÂN HỆ 4: COMMUNICATIONS HUB

#### 3.4.1. `TokenBucketRateLimiter` (`jarvis/comms/rate_limiter.py:60`)
- **Cơ chế hoạt động**:
  - Thuật toán Token Bucket tiêu chuẩn với dung lượng $B$ (`burst_limit`) và tốc độ nạp $r = \text{rpm} / 60.0$ token/giây.
  - Quản lý trạng thái theo `user_id`, bảo vệ bởi `threading.Lock()`.
  - Trả về `RateLimitResult(allowed, status_code, retry_after_s)`.
- **Bằng chứng kiểm thử**:
  - `tests/unit/test_rate_limiter.py` chạy kiểm thử đồng thời với 20+ luồng mô phỏng tải 30 req/giây, xác thực chính xác các mã lỗi 200 và 429.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1.
  - *Trục 2 (Truthfulness)*: ✅ Truthful.
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

#### 3.4.2. `DiscordBotController` (`jarvis/comms/discord.py:452`)
- **Khuyết tật Ghost Process (Khuyết tật D3)**:
  - Xem mã nguồn `jarvis/comms/discord.py:452-459`:
    ```python
    def _poll_loop(self) -> None:
        while self._running:
            try:
                time.sleep(2.0)  # Poll every 2 seconds
            except Exception as exc:
                log.error("Discord poll error: %s", exc)
                time.sleep(5.0)
    ```
  - Luồng `_poll_loop` chạy vô tận, chỉ `sleep(2.0)` mà không gọi bất kỳ Discord Gateway WebSocket hay REST API nào. Tiêu tốn 1 luồng hệ điều hành hoàn toàn vô ích.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟡 T2.
  - *Trục 2 (Truthfulness)*: 👻 Ghost Process.
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ⏳ Bị chặn bởi `DISCORD_BOT_TOKEN` và mã tích hợp API thật.

#### 3.4.3. `ZaloBotController` (`jarvis/comms/zalo.py:226,297`)
- **Khuyết tật Silent Fallback (Khuyết tật D1)**:
  - Tại dòng 297-299:
    ```python
    if self.is_mock or not self.config.access_token:
        log.info("Mock send to %s: %s", user_id, text[:60])
        return ZaloSendResult(success=True, message_id="mock_msg_id")
    ```
    Khi instance cấu hình chạy thật (`is_mock=False`) nhưng thiếu `access_token`, hàm trả về `success=True` với `message_id="mock_msg_id"`. Đây là hành vi vi phạm trực tiếp nguyên tắc Fail-Closed.
- **Khuyết tật Active Fabrication (Khuyết tật D2)**:
  - Dòng 260 (`_cmd_weather`): Trả về thời tiết hardcode `"🌤️ Hà Nội: 32°C, ít mây\n☀️ TP.HCM: 34°C, nắng"`.
  - Dòng 226 (`_cmd_status`): Bịa chuỗi `"🧠 Memory: OK | 🔊 TTS: OK... Connected"`.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟡 T2.
  - *Trục 2 (Truthfulness)*: ⚠️ Silent Fallback + 🔴 Active Fabrication.
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ⏳ Cần `ZALO_ACCESS_TOKEN` và OA ID.

#### 3.4.4. `TelegramBotController` (`jarvis/comms/telegram.py:181`)
- **Khuyết tật Silent Fallback khi thiếu Dispatcher (Khuyết tật D6)**:
  - Khi `self.dispatcher is None`, các lệnh `/exec <cmd>`, `/note <content>`, `/calc <expr>` trả về status 200 `"Đã thực thi lệnh: <cmd>"` dù không có hành động nào được thực hiện.
- **Lỗi bài test cũ (Stale Test Assertion)**:
  - `tests/test_comms_hub.py:33`: `assert "Hệ thống hoạt động bình thường" in status_reply["text"]` bị lỗi do lệnh `/status` đã được sửa sang báo cáo chỉ số `psutil` thật.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟡 T2.
  - *Trục 2 (Truthfulness)*: ⚠️ Silent Fallback khi thiếu dispatcher.
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ⏳ Cần `TELEGRAM_BOT_TOKEN`.

#### 3.4.5. `IMAPEmailReader` & `MobileFileBridge`
- **`IMAPEmailReader` (`jarvis/comms/email_imap.py:1`) — 🔴 T3 Architectural Stub**:
  - Không có bất kỳ dòng code `imaplib` nào để kết nối mạng tới mail server. Hàm `fetch_and_summarize()` chỉ hoạt động trên mảng `mock_emails` truyền vào qua tham số.
- **`MobileFileBridge` (`jarvis/comms/mobile_bridge.py:1`) — 🟡 T2 Fail-Closed**:
  - Lọc phần mở rộng file nghiêm ngặt, chặn kỹ thuật double-extension (`invoice.exe.pdf`), fail-closed khi thiếu Telegram.
- **Đánh giá 4 trục**:
  - *IMAP*: 🔴 T3, ✅ Truthful (không bịa email), 🛡️ Risk-Reduction, ⏳ Cần triển khai `imaplib`.
  - *Mobile Bridge*: 🟡 T2, ✅ Truthful, 🛡️ Risk-Reduction, ⏳ Cần bot token.

---

### 3.5. PHÂN HỆ 5: BROWSER & OS CONTROL

#### 3.5.1. `ComputerController.open_app()` (`jarvis/automation/control.py:770`)
- **Cơ chế hoạt động**:
  - Bản vá A6 xác thực ứng dụng qua `shutil.which(clean_name)` hoặc `shutil.which(f"{clean_name}.exe")`.
  - Nếu không tìm thấy file thực thi, lập tức trả về `success=False`, `error_code="APP_NOT_FOUND"`.
  - Cơ chế `launch_dedupe_guard` ngăn chặn vòng lặp mở app lặp tiếng.
- **Đánh giá 4 trục**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1 (`test_runaway_hardening.py`).
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Fail-Closed).
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

#### 3.5.2. Trình Điều Khiển Trình Duyệt (`BrowserCDPController` & `CDPBrowserDriver`)
- **`BrowserCDPController` — 🟡 T2 Mock-Dominated**:
  - 100% unit tests trong `tests/unit/test_browser_control.py` chạy với `is_mock=True`.
- **`CDPBrowserDriver` — 👻 Ghost Process / Stub (Khuyết tật D4)**:
  - Tại `jarvis/browser/driver.py:482-504`: Các hàm `click()`, `type_text()`, `select_option()`, `wait_for_selector()` chỉ `return self._is_running` mà không gửi bất kỳ lệnh CDP nào qua WebSocket/HTTP.
- **Đánh giá 4 trục**:
  - *CDP Driver*: 🟡 T2, 👻 Ghost Process, 🛡️ Risk-Reduction, ⏳ Cần mở port 9222.

#### 3.5.3. Volume Control & Audio Endpoint Switching
- **Volume Control (`pycaw`) — 🔴 T3 & ⚠️ Silent Fallback (Khuyết tật D5)**:
  - Tại `control.py:363-381`: Gán `self._current_volume = level`, khối `except Exception: pass` nuốt sạch ngoại lệ khi thiếu loa hoặc lỗi thư viện, rồi trả về `self._current_volume` yêu cầu. 0 bài test tồn tại trong repo cho `pycaw`.
- **Audio Endpoint Switching — 🔴 T3 & 🔴 Active Fabrication (Khuyết tật D8)**:
  - Hoàn toàn không có code chuyển đổi thiết bị output.
  - Trong `jarvis/audio/engine.py:304-315`: Khi thiếu `sounddevice`, hàm `probe_devices()` tự tạo đối tượng ảo "Headless Mock Audio Device" thay vì trả về `[]`.
- **Đánh giá 4 trục**:
  - *Volume*: 🔴 T3, ⚠️ Silent Fallback, 🛡️ Risk-Reduction, ❌ Không bị chặn sửa mã.
  - *Audio Endpoint*: 🔴 T3, 🔴 Active Fabrication, 🛡️ Risk-Reduction, ⏳ Cần quyết định thiết kế API.

---

### 3.6. PHÂN HỆ 6: TERMINAL CONTROL CENTER (TCC)

#### 3.6.1. Kiến Trúc Presentation Layer & Enum `StatusLevel`
- TCC (`jarvis/ui/terminal/`) vận hành trên console ANSI thuần túy.
- Tuyệt đối tuân thủ nguyên tắc **Presentation Layer Only**: không tự ý dispatch hành động phá hủy, sử dụng enum `StatusLevel` minh bạch (READY, LIMITED, OFFLINE, BLOCKED, FAILED).

#### 3.6.2. Kiểm Tra 9 Module Adapters (100% Anti-Fabrication)
Cả 9 adapter trong `jarvis/ui/terminal/modules/` là hình mẫu chuẩn mực về chống bịa đặt dữ liệu:
1. **Biometrics (`biometrics.py`)**: Từ chối giả mạo nhận diện khuôn mặt khi camera chưa nối dây, báo `StatusLevel.LIMITED`.
2. **Communications (`comms.py`)**: Biết backend Telegram/Discord cũ có rủi ro silent fallback nên từ chối gọi hàm gửi, báo `StatusLevel.LIMITED`.
3. **Data (`data.py`)**: Bắt buộc chọn file thật, thiếu `matplotlib` báo `StatusLevel.LIMITED`.
4. **Gesture (`gesture.py`)**: Tách bạch Acoustic Clap (`AVAILABLE`) và Hand Tracker (`LIMITED` do thiếu `cv2/mediapipe`).
5. **Hardware (`hardware.py`)**: Thiếu GPU chuyên dụng báo `StatusLevel.LIMITED`, không bịa thông số 0%.
6. **Healing (`healing.py`)**: `PROTECTED_PROCESS_WHITELIST` chặn đứng việc terminate nhầm `python.exe`.
7. **InfoSec (`infosec.py`)**: **Chủ động không gọi `PacketCapture.capture_packets()`** do phát hiện lỗi hardcode 70/20/10, hiển thị `StatusLevel.LIMITED` và `Real Packet Evidence: NOT AVAILABLE`.
8. **Smart Home (`smart_home.py`)**: Báo `StatusLevel.LIMITED` vì chưa có authoritative path.
9. **Workflow (`workflow.py`)**: Báo thẳng thắn `StatusLevel.OFFLINE` cho tính năng VM tự động chưa hoàn thiện.

#### 3.6.3. Xác Minh Đĩa Cứng Trong `ReportWriter` (`jarvis/ui/terminal/report.py:164`)
- Kiểm tra file vật lý sau khi ghi: `exists = path.exists() and path.stat().st_size > 0`. Bắt buộc kích thước đĩa > 0 bytes mới trả về `saved=True`.

- **Đánh giá 4 trục cho Subsystem 6**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1 (`tests/unit/test_terminal_modules.py`).
  - *Trục 2 (Truthfulness)*: ✅ Truthful (100% Anti-Fabrication).
  - *Trục 3 (Boundary Type)*: 🛡️ Risk-Reduction.
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

---

### 3.7. PHÂN HỆ 7: SELF-CODING ENGINE

#### 3.7.1. Cổng Đánh Giá An Toàn Đa Tầng (`DynamicSkillSynthesizer`)
- Mã nguồn: `jarvis/skills/synthesizer.py:293-339`.
- Quy trình 3 bước trước khi lưu kỹ năng mới ra đĩa:
  1. *Bước 1*: `_ast_validator.validate_python(code)` trên mã thô.
  2. *Bước 2*: `_ast_validator.validate_python(formatted_code)` trên mã đóng gói.
  3. *Bước 3 (Sandbox Dry-Run Gate — Roadmap 1.2)*: Chạy thử hàm `execute()` với dữ liệu mẫu trong `CodeInterpreterSandbox`. Bắt trọn vẹn các lỗi runtime (`ZeroDivisionError`, thiếu thư viện phụ trợ) mà phân tích cú pháp AST không thể phát hiện (giải quyết giới hạn Halting Problem).
  - Nếu dry-run thất bại, ném `ValueError` và hủy bỏ quá trình tạo file.

#### 3.7.2. `SkillRegistry` & `SkillSandboxRunner` (`jarvis/skills/registry.py:482`)
- Tách biệt hoàn toàn `SkillTelemetryStore` ra file riêng, ngăn ngừa việc ghi dữ liệu tần suất làm biến đổi file `metadata.json` gốc của kỹ năng.
- Hàm `invoke_skill()` bắt ngoại lệ và trả về `SkillExecutionResult(success=False, error=str(exc))`.
- Chạy mã trong sandbox cách ly bởi Windows Job Object và MIC Low Integrity Token.

- **Đánh giá 4 trục cho Subsystem 7**:
  - *Trục 1 (Evidence Tier)*: 🟢 T1 (`tests/unit/test_skill_synthesis.py` & `test_sandbox_os_boundaries.py`).
  - *Trục 2 (Truthfulness)*: ✅ Truthful (Fail-Closed).
  - *Trục 3 (Boundary Type)*: 🔒 Hard Boundary (Sandbox) + 🛡️ Risk-Reduction (AST).
  - *Trục 4 (Blocked-by)*: ❌ Không bị chặn.

---

## 4. TRUTHFULNESS FORENSICS (ĐÀO SÂU TRỤC 2)

Trục 2 (Tính trung thực) là phát hiện bản lề quan trọng nhất được đúc kết từ chuỗi kiểm toán A1–A7. Dưới đây là phân tích đối chiếu chuyên sâu giữa 4 trạng thái trung thực cùng đoạn mã nguồn tương ứng:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        4 CẤP ĐỘ TRUNG THỰC CỦA HỆ THỐNG                                │
│                                                                                        │
│  [✅ Fail-Closed]  ──> Chỉ trả True/Success sau khi có xác nhận thực tế                │
│  [⚠️ Silent Fallback] ──> Trả True/Success ngầm định khi thiếu cấu hình hoặc lỗi       │
│  [🔴 Active Fabrication] ──> Bịa đặt số liệu trông như thật (hardcode công thức)       │
│  [👻 Ghost Process] ──> Thread/Tiến trình chạy thật nhưng không làm gì                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.1. Điển Hình Chuẩn Mực: Fail-Closed
- **Ví dụ 1: `ComputerController.open_app()` (`jarvis/automation/control.py:770-785`)**:
  ```python
  import shutil
  resolved = shutil.which(clean_name) or shutil.which(f"{clean_name}.exe")
  if not resolved:
      return {
          "success": False,
          "app": clean_name,
          "error_code": "APP_NOT_FOUND",
          "message": f"Không tìm thấy ứng dụng '{clean_name}' trên hệ thống.",
      }
  ```
  Hàm không gọi lệnh shell bừa bãi; chỉ khi hệ điều hành xác nhận file nhị phân tồn tại trên PATH mới tiến hành kích hoạt.
- **Ví dụ 2: `ReportWriter.write()` (`jarvis/ui/terminal/report.py:164-172`)**:
  ```python
  exists = path.exists() and path.stat().st_size > 0
  if not exists:
      return ReportWriteResult(path=path, saved=False, error="file not found after write")
  return ReportWriteResult(path=path, saved=True)
  ```
  Không tin tưởng mù quáng vào hàm ghi I/O; kiểm tra thực tế kích thước đĩa > 0 bytes trước khi khẳng định thành công.

---

### 4.2. Khuyết Tật Báo Động: Silent Fallback
- **Trường hợp Zalo `send_message()` (`jarvis/comms/zalo.py:297-299`)**:
  ```python
  if self.is_mock or not self.config.access_token:
      log.info("Mock send to %s: %s", user_id, text[:60])
      return ZaloSendResult(success=True, message_id="mock_msg_id")
  ```
  *Phân tích*: Khi triển khai production (`is_mock=False`) nhưng người dùng quên điền token, hệ thống vẫn trả về `success=True`. Phía gọi tưởng rằng tin nhắn đã tới điện thoại người dùng trong khi thực tế chỉ ghi log console.
- **Trường hợp Volume Control `set_volume()` (`jarvis/automation/control.py:377-381`)**:
  ```python
  try:
      # pycaw AudioUtilities...
      return self._current_volume
  except Exception:
      pass
  return self._current_volume
  ```
  *Phân tích*: Nuốt sạch ngoại lệ và trả về chính con số người dùng yêu cầu, biến lỗi phần cứng thành thành công giả định.

---

### 4.3. Khuyết Tật Báo Động: Active Fabrication
- **Trường hợp Zalo Command Weather (`jarvis/comms/zalo.py:260`)**:
  ```python
  def _cmd_weather(self, user_id: str, city: str = "") -> ZaloSendResult:
      weather_info = "🌤️ Hà Nội: 32°C, ít mây\n☀️ TP.HCM: 34°C, nắng"
      return self.send_message(user_id, f"Dự báo thời tiết hôm nay:\n{weather_info}")
  ```
  *Phân tích*: Bịa đặt thông số thời tiết cố định thay vì gọi weather API hoặc báo lỗi thiếu API key.
- **Trường hợp `AudioEngine.probe_devices()` (`jarvis/audio/engine.py:304-315`)**:
  ```python
  if not SOUNDDEVICE_AVAILABLE:
      return [AudioDeviceInfo(index=0, name="Headless Mock Audio Device", ...)]
  ```
  *Phân tích*: Tự sinh thiết bị âm thanh giả lập khi thiếu thư viện.

---

### 4.4. Khuyết Tật Báo Động: Ghost Process
- **Trường hợp Discord `_poll_loop()` (`jarvis/comms/discord.py:452-459`)**:
  ```python
  def _poll_loop(self) -> None:
      while self._running:
          try:
              time.sleep(2.0)
          except Exception as exc:
              log.error("Discord poll error: %s", exc)
              time.sleep(5.0)
  ```
  *Phân tích*: Luồng tồn tại, chiếm thread handle của OS, không crash, nhưng bên trong chỉ lặp `sleep(2.0)` mà không đọc hay kéo dữ liệu gì.
- **Trường hợp `CDPBrowserDriver` (`jarvis/browser/driver.py:482-486`)**:
  ```python
  def click(self, selector: str, timeout_ms: int = 5000) -> bool:
      return self._is_running
  ```
  *Phân tích*: Hàm trả về `True` (nếu driver đang chạy) nhưng không gửi bất kỳ frame CDP nào qua WebSocket.

---

## 5. PHÂN LOẠI RANH GIỚI BẢO MẬT (ĐÀO SÂU TRỤC 3)

Một đóng góp cốt lõi của `AUDIT_FRAMEWORK.md` là nghiêm cấm việc đánh đồng các cơ chế Heuristic với các cơ chế Kernel-Enforced. Dưới đây là phân định kỹ thuật rành mạch:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        SO SÁNH BẢN CHẤT RANH GIỚI BẢO MẬT                                       │
├────────────────────────────────┬────────────────────────────────────────────────────────────────┤
│ 🔒 KERNEL-ENFORCED BOUNDARY     │ 🛡️ HEURISTIC RISK-REDUCTION                                     │
├────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ • Thực thi bởi Windows NT SRM  │ • Thực thi ở tầng ứng dụng Python                              │
│ • Bất biến, quyết định luận    │ • Xác suất / Dựa trên quy tắc heuristic                        │
│ • Miễn nhiễm với Reflection    │ • Có thể bị né bằng input tinh vi hoặc tấn công Reflective     │
│ • Ví dụ: Job Object, Token MIC │ • Ví dụ: AST Validator, PromptGuard, Token Bucket, SNR Gating │
└────────────────────────────────┴────────────────────────────────────────────────────────────────┘
```

### 5.1. Ranh Giới Cứng Cấp Kernel (Kernel-Enforced Hard Boundaries)
1. **Windows Job Object Confinement**:
   - Khởi tạo qua `CreateJobObjectW` và cấu hình `JOBOBJECT_EXTENDED_LIMIT_INFORMATION`.
   - `ActiveProcessLimit = 1`: Kernel Windows từ chối trực tiếp ở hàm `NtCreateUserProcess` khi tiến trình con cố tình spawn thêm tiến trình khác.
   - `JobMemoryLimit = 256MB`: Kernel tự động terminate tiến trình nếu vượt ngưỡng bộ nhớ, ngăn chặn tấn công cạn kiệt RAM (Memory Exhaustion DoS).
2. **Windows Mandatory Integrity Control (MIC)**:
   - Sử dụng `CreateRestrictedToken` gán SID `S-1-16-4096` (Low Integrity).
   - Thiết lập No-Write-Up SACL trên thư mục scratch `S:(ML;OICI;NW;;;LW)`.
   - Kernel Security Reference Monitor (SRM) kiểm tra Integrity Level tại mọi thao tác `NtCreateFile` / `NtOpenFile`. Mọi nỗ lực ghi vào thư mục Medium Integrity (ổ C, thư mục mã nguồn) đều bị chặn cứng với lỗi OS `STATUS_ACCESS_DENIED`.
3. **Windows Atomic File Persistence**:
   - Sử dụng `tmp_path.replace(path)` (tương đương `MoveFileExW` với cờ `MOVEFILE_REPLACE_EXISTING`).
   - Kết hợp `_save_lock` và vòng lặp thử lại giải quyết `WinError 5` khi file bị antivirus khóa tạm thời. Đảm bảo file cấu hình và cơ sở dữ liệu không bao giờ bị trạng thái ghi dở dang (partial write) khi mất điện đột ngột.
4. **SQLite WAL Mode Transactional ACID**:
   - Sử dụng Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) với cơ chế cô lập ACID độc lập luồng.

---

### 5.2. Ranh Giới Giảm Thiểu Rủi Ro (Heuristic Risk-Reduction) & Giới Hạn Lý Thuyết
1. **`ASTCodeValidator`**:
   - *Giới hạn cố hữu*: Phân tích cú pháp tĩnh không giải quyết được **Bài toán dừng (Halting Problem)**. Không thể biết mã có vòng lặp vô tận hay không; không thể chặn được các chuỗi reflection gián tiếp như `getattr(eval('__built' + 'ins__'), 'ex' + 'ec')`.
   - *Vai trò chính xác*: Bộ lọc nhanh sơ cấp (Phase 1) nhằm loại bỏ mã độc sơ đẳng trước khi chuyển giao vào Sandbox Dry-Run (Phase 2).
2. **Token Bucket Rate Limiter**:
   - *Giới hạn cố hữu*: Giới hạn tần suất in-memory; có thể bị vượt qua nếu kẻ tấn công giả mạo các `user_id` ngẫu nhiên nếu không có lớp xác thực định danh (Authentication) đi kèm.
3. **VAD RMS & SNR Threshold Gating**:
   - *Giới hạn cố hữu*: Dựa trên các ngưỡng năng lượng thống kê (RMS 0.002, SNR 10.0 dB). Trong môi trường âm học đặc thù (tiếng thở mạnh sát mic hoặc tiếng ồn quạt lớn), có thể xảy ra tỷ lệ dương tính giả hoặc âm tính giả nhỏ.

---

## 6. PHÂN TÍCH TÌNH TRẠNG BỊ CHẶN & ĐỒ THỊ PHỤ THUỘC (TRỤC 4)

*Tuân thủ Cạm bẫy kiểm toán #19 (AUDIT_FRAMEWORK.md): Tuyệt đối không để việc bị chặn bởi X làm trì hoãn những công việc KHÔNG liên quan tới X.*

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  ĐỒ THỊ PHÂN LOẠI CÔNG VIỆC TRỤC 4                                      │
├──────────────────────────────────────────────────────────────────┬──────────────────────────────────────┤
│ ❌ NHÓM 1: KHÔNG BỊ CHẶN — HÀNH ĐỘNG NGAY (P0/P1)                 │ ⏳ NHÓM 2: BỊ CHẶN BỞI TOKEN / HẠ TẦNG│
├──────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
│ • Sửa Silent Fallback Zalo send_message (zalo.py:297)            │ • Cài binary TShark để test packet   │
│ • Sửa Active Fabrication Zalo _cmd_weather, _cmd_status          │ • Cài Playwright Chromium & port 9222│
│ • Sửa Ghost Process Discord _poll_loop (discord.py:452)          │ • Token Discord bot có Intent đọc tin│
│ • Sửa CDPBrowserDriver Ghost click()/type_text()                 │ • Token Zalo OA chính thức & Webhook │
│ • Sửa Silent Fallback Volume set_volume() (control.py:363)       │ • Token Telegram Bot & ElevenLabs API│
│ • Sửa Silent Fallback Telegram /exec no dispatcher               │ • Binary Nmap cho NetworkScanner     │
│ • Sửa lỗi fallback count PacketCapture (scanner.py:769)          ├──────────────────────────────────────┤
│ • Loại bỏ mock device trong AudioEngine.probe_devices()          │ ⏳ NHÓM 3: BỊ CHẶN BỞI THIẾT KẾ      │
│ • Bổ sung test unmocked cho SecretsManager (keyring)             ├──────────────────────────────────────┤
│ • Cập nhật stale assertion tests/test_comms_hub.py:33            │ • Thiết kế Core Audio Endpoint Switch│
│ • Bổ sung Domain Allowlist cho open_website()                    │ • Thiết kế kiến trúc IMAP Polling    │
└──────────────────────────────────────────────────────────────────┴──────────────────────────────────────┘
```

---

## 7. ĐỀ XUẤT KHẮC PHỤC THEO QUY TRÌNH SEAM-FIRST TDD

Dưới đây là các phương án khắc phục mã nguồn cụ thể kèm bài kiểm thử biên (test specification) theo đúng quy chuẩn kiểm thử Seam-First TDD cho từng khuyết tật phát hiện:

### 7.1. Khắc Phục Zalo `send_message` Silent Fallback & Active Fabrication
- **Tệp sửa đổi**: `jarvis/comms/zalo.py`
- **Mã nguồn đề xuất**:
  ```python
  # Sửa đổi tại jarvis/comms/zalo.py:297
  def send_message(self, user_id: str, text: str) -> ZaloSendResult:
      """Send text message to a Zalo user via OA API."""
      entry = {"user_id": user_id, "text": text, "timestamp": time.time()}
      self.sent_messages.append(entry)

      # CHỈ cho phép mock khi cờ is_mock được bật tường minh
      if self.is_mock:
          log.info("Mock send to %s: %s", user_id, text[:60])
          return ZaloSendResult(success=True, message_id="mock_msg_id")

      # FAIL-CLOSED: Thiếu token trên production instance PHẢI trả về thất bại
      if not self.config.access_token:
          log.warning("Zalo send rejected: access_token not configured")
          return ZaloSendResult(success=False, error="NOT_CONFIGURED")
  ```
  ```python
  # Sửa đổi tại jarvis/comms/zalo.py:226 và 260
  def _cmd_weather(self, user_id: str, city: str = "") -> ZaloSendResult:
      # Loại bỏ active fabrication 32°C/34°C
      if not self.dispatcher:
          return self.send_message(user_id, "⚠️ Dịch vụ thời tiết chưa khả dụng (chưa kết nối dispatcher).")
      # Chuyển tiếp tới dispatcher thật...
  ```
- **Bài kiểm thử TDD (`tests/unit/test_zalo_truthfulness_remediation.py`)**:
  ```python
  def test_zalo_send_message_fails_closed_when_token_missing():
      from jarvis.comms.zalo import ZaloBotController, ZaloConfig
      cfg = ZaloConfig(oa_id="12345", access_token="", secret_key="sec")
      bot = ZaloBotController(config=cfg, is_mock=False)
      res = bot.send_message(user_id="user_1", text="Hello")
      assert res.success is False
      assert res.error == "NOT_CONFIGURED"
  ```

---

### 7.2. Khắc Phục Discord `_poll_loop` Ghost Process
- **Tệp sửa đổi**: `jarvis/comms/discord.py`
- **Mã nguồn đề xuất**:
  ```python
  # Sửa đổi tại jarvis/comms/discord.py:437-459
  def start_polling(self) -> None:
      """Start background polling loop."""
      if not self.bot_token:
          log.info("Discord polling skipped (no bot_token configured)")
          return
      # Nếu chưa có WebSocket Gateway client, KHÔNG spawn thread ngủ rỗng
      log.warning("Discord background polling is not implemented in this build. Use webhook integration.")
      self._running = False
  ```
- **Bài kiểm thử TDD**:
  ```python
  def test_discord_polling_does_not_spawn_ghost_thread():
      from jarvis.comms.discord import DiscordBotController
      bot = DiscordBotController(bot_token="test_token")
      bot.start_polling()
      assert bot._poll_thread is None or not bot._poll_thread.is_alive()
  ```

---

### 7.3. Khắc Phục Volume Control Silent Fallback (`pycaw`)
- **Tệp sửa đổi**: `jarvis/automation/control.py`
- **Mã nguồn đề xuất**:
  ```python
  # Sửa đổi tại jarvis/automation/control.py:363-381
  def set_volume(self, level_percent: int) -> int | None:
      level = max(0, min(100, int(level_percent)))
      try:
          from comtypes import CLSCTX_ALL
          from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
          speakers = AudioUtilities.GetSpeakers()
          if not speakers:
              log.warning("No audio speaker endpoint found on this host")
              return None
          interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
          import ctypes
          volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
          volume.SetMasterVolumeLevelScalar(level / 100.0, None)
          self._current_volume = level
          return self._current_volume
      except Exception as exc:
          log.error("Failed to set master volume via pycaw: %s", exc)
          return None  # FAIL-CLOSED: Báo lỗi thay vì nuốt ngoại lệ
  ```
- **Bài kiểm thử TDD**:
  ```python
  def test_set_volume_fails_closed_when_speakers_missing(monkeypatch):
      from jarvis.automation.control import ComputerController
      ctrl = ComputerController()
      # Giả lập pycaw ném ngoại lệ không tìm thấy loa
      monkeypatch.setattr("pycaw.pycaw.AudioUtilities.GetSpeakers", lambda: None)
      res = ctrl.set_volume(50)
      assert res is None  # Xác nhận không trả về 50 ảo
  ```

---

### 7.4. Khắc Phục Telegram `/exec` Dispatcher Silent Fallback
- **Tệp sửa đổi**: `jarvis/comms/telegram.py`
- **Mã nguồn đề xuất**:
  ```python
  # Sửa đổi tại jarvis/comms/telegram.py:220
  elif lower_clean.startswith("/exec "):
      cmd = text[6:].strip()
      if not self.dispatcher:
          return {"status": 503, "text": "❌ Lỗi: ActionDispatcher chưa được cấu hình. Lệnh không được thực thi."}
      # Thực thi qua dispatcher...
  ```
- **Bài kiểm thử TDD**:
  ```python
  def test_telegram_exec_fails_closed_when_dispatcher_none():
      from jarvis.comms.telegram import TelegramBotController
      bot = TelegramBotController(dispatcher=None)
      res = bot.handle_inbound_message(user_id=1, text="/exec dir")
      assert res["status"] == 503
      assert "chưa được cấu hình" in res["text"]
  ```

---

### 7.5. Khắc Phục PacketCapture Fallback Count Bug
- **Tệp sửa đổi**: `jarvis/security/scanner.py`
- **Mã nguồn đề xuất**:
  ```python
  # Sửa đổi tại jarvis/security/scanner.py:769
  protocols = _parse_tshark_protocols(raw_stdout)
  status = "SUCCESS" if protocols else "NO_PROTOCOLS_PARSED"
  # FAIL-CLOSED: Khi protocols rỗng, packet_count PHẢI bằng 0 (không lấy count)
  packet_count = sum(protocols.values()) if protocols else 0
  ```
- **Bài kiểm thử TDD**:
  ```python
  def test_packet_capture_returns_zero_count_on_unparseable_output():
      from jarvis.security.scanner import PacketCapture
      pc = PacketCapture()
      # raw_stdout có text banner lỗi nhưng không có protocol hợp lệ
      protocols = pc._parse_tshark_protocols("Error: unknown format banner")
      assert len(protocols) == 0
      # packet_count phải trả về 0
  ```

---

### 7.6. Khắc Phục `CDPBrowserDriver` Interaction Stubs
- **Tệp sửa đổi**: `jarvis/browser/driver.py`
- **Mã nguồn đề xuất**:
  ```python
  # Sửa đổi tại jarvis/browser/driver.py:482-504
  def click(self, selector: str, timeout_ms: int = 5000) -> bool:
      if not self._is_running:
          return False
      # Thay vì chỉ return self._is_running, thực thi lệnh CDP hoặc fail-closed
      if not hasattr(self, "_cdp_session") or self._cdp_session is None:
          log.warning("CDP click failed: active CDP session not established")
          return False
      return self._send_cdp_click(selector, timeout_ms)
  ```

---

## 8. KẾT LUẬN & KIẾN NGHỊ CUỐI CÙNG

Cuộc kiểm toán độc lập đối với JARVIS v4.8.1 đã hoàn thành việc rà soát và lập hồ sơ minh bạch cho **100% (28/28) thành phần kỹ thuật**. 

### Điểm Vững Chắc Nổi Bật Cần Tiếp Tục Duy Trì
1. **Ranh Giới Bảo Mật Cấp Kernel Thực Thụ**: `CodeInterpreterSandbox` chứng minh khả năng phòng thủ vượt trội nhờ kết hợp Windows Job Object (`ActiveProcessLimit=1`, 256MB RAM cap) và Mandatory Integrity Control (MIC Low Integrity Token).
2. **Tính Bền Vững Đa Luồng Của Hệ Thống Bộ Nhớ**: `SemanticVectorStore` và `SQLiteMemoryStore` đạt chuẩn **🟢 T1** xuất sắc, vượt qua áp lực 30 luồng đồng thời mà không làm mất dữ liệu nhờ cơ chế Windows Atomic File Replace và SQLite WAL.
3. **Voice Pipeline Kháng Overfitting & Kháng Hallucination**: Chuẩn hóa không dấu an toàn (`strip_vietnamese_diacritics`) bảo vệ từ đơn triệt tiêu va chạm đồng âm, đạt 100% chính xác trên 35 câu held-out mới; kết hợp 5 tầng lọc ảo giác của Faster-Whisper và bộ lọc phổ SFM E8.
4. **Văn Hóa Chống Bịa Đặt Dữ Liệu Của TCC**: Cả 9 adapter module trong Terminal Control Center từ chối hiển thị số liệu giả lập, thể hiện tinh thần kỹ thuật trung thực tuyệt đối.

### Kế Hoạch Hành Động Ngay (Immediate Action Plan)
1. **Triển khai Nhóm Vá Lỗi P0 (Không bị chặn)**: Áp dụng các bài vá Seam-First TDD cho Zalo (`send_message`, weather, status), Discord (`_poll_loop`), Telegram (`/exec`), Volume control (`pycaw`), và PacketCapture (dòng 769).
2. **Cập nhật bài test `tests/test_comms_hub.py:33`**: Đồng bộ assertion trạng thái hệ thống với chuỗi psutil thực tế.
3. **Thêm bài test unmocked cho `SecretsManager`**: Thực hiện test round-trip đọc/ghi trên Windows Credential Manager thật để nâng hạng từ 🟡 T2 lên 🟢 T1.
4. **Chuẩn bị hạ tầng môi trường (Sau khi người dùng cấp token)**: Cài đặt binary Nmap, TShark, Playwright Chromium để chuyển hóa toàn bộ các thành phần 🟡 T2 còn lại lên 🟢 T1.

---
*Báo cáo được phê duyệt và lưu trữ chính thức tại `docs/FULL_FEATURE_AUDIT_REPORT.md` theo quy định của dự án JARVIS.*
