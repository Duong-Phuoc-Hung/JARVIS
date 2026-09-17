# JARVIS Comprehensive Risk Register: P0, P1 & Hardware-Blocked Gates (R10)

**Document Version**: 1.0.0  
**Target Release**: JARVIS v5.2.0 (Windows 11 / Windows 10 64-bit)  
**Governance Standard**: `AGENTS.md §2` (Anti-Fabrication Principle), `AGENTS.md §5` (Three-Tier Verdict Discipline), & `docs/AUDIT_FRAMEWORK.md`  
**Current Operational Posture**: **`CONDITIONAL GO — Internal Beta Pilot Only`**  
**Product GA Release Posture**: **`NO-GO`** (Pending closure of 5 hardware-blocked acceptance gates)

---

## 1. Executive Summary & Verdict Framework

This Risk Register establishes the authoritative accounting of all architectural, operational, and environmental risks for JARVIS v5.2.0. In compliance with `AGENTS.md §5` (Three-Tier Verdict Discipline), project readiness is evaluated across distinct tiers to prevent false claims of production readiness:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              THREE-TIER VERDICT DISCIPLINE                             │
├──────────────────────────┬─────────────────────────────────────────────────────────────┤
│ 1. Engineering Tier      │ PASS engineering: Code complete, 2,424 unit tests pass,     │
│                          │ 0 regressions, adversarial audits passed.                   │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 2. Fail-Closed Tier      │ PASS fail-closed: All unconfigured services return canonical│
│                          │ status codes (NOT_CONFIGURED, UNAVAILABLE, TOOL_NOT_FOUND). │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 3. Runtime Physical Tier │ PENDING runtime: Hardware-dependent modules await physical   │
│                          │ execution on real peripherals, clean VMs, and human tester. │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Internal Beta Pilot      │ CONDITIONAL GO: Safe for closed developer workstation test. │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Product GA Release       │ NO-GO: Blocked until all 5 hardware-blocked gates pass.     │
└──────────────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 2. P0 Risk Register (Blockers — Critical Integrity)

A **P0 Risk** represents a critical defect, vulnerability, or failure mode that causes data loss, system instability, uncontrolled execution cascades, false-positive safety violations, or violates core fail-closed invariants. **Zero open technical P0s are permitted in release candidate code.**

### 2.1 Codebase P0 Audit: 0 Open Architectural / Technical P0s

An exhaustive audit of the JARVIS codebase confirms that there are **0 open architectural or code-level P0 blockers**. All previously identified P0 risks have been resolved, verified with unit/adversarial tests, and committed:

| Historical P0 ID | Subsystem | Description & Root Cause | Implemented Resolution & Commit | Verification Evidence |
|---|---|---|---|---|
| **P0-A01** | `jarvis/planner/engine.py` | **Planner Simulated Success**: Handler fallback returned `{"simulated": True}` on missing action, and direct handler errors were masked into `ActionResult(success=True)`. | Excised simulation fallback at commit `c532805`. Planner strictly returns `ActionResult(success=False, code="HANDLER_NOT_FOUND")` and propagates handler error codes. | `tests/test_adversarial_m1_planner_failclosed.py` (27 tests pass) |
| **P0-A02** | `jarvis/core/runaway_guard.py` | **Audio/App Runaway Trigger Cascades**: Acoustic self-feedback or rapid intent triggers could spawn multiple Spotify, Chrome, or audio streams indefinitely. | Implemented `PassiveTriggerGuard` (5 triggers / 60s window, 120s lockout) and `LaunchDedupeGuard` (5.0s deduplication per target app key). | `tests/unit/test_runaway_guard.py` + `tests/test_adversarial_p0_runaway.py` pass |
| **P0-A03** | `jarvis/tts/manager.py` | **SAPI5 COM Initialization Thread Safety**: Windows SAPI5 COM voice crashes with `CoInitialize has not been called` in daemon worker threads. | Initialized COM with `pythoncom.CoInitialize()` in `_worker_thread()` before dispatch, paired with `pythoncom.CoUninitialize()` in `finally:` block. | `tests/unit/test_tts_com_safety.py` (10 consecutive calls pass) |
| **P0-A04** | `jarvis/ui/terminal/theme.py` | **Health Status Vocabulary Drift**: 11 files used fragmented terms (`PASS`, `FAILED`, `OFFLINE`, `AVAILABLE`), causing attribute lookups to fail or render incorrectly. | Standardized `StatusLevel` to exactly 5 states: `READY`, `LIMITED`, `BLOCKED`, `ERROR`, `UNAVAILABLE`. Standardized all 52 callsites across 11 files. | `tests/unit/test_terminal_theme_vocabulary.py` (AST zero-drift check passes) |
| **P0-A05** | `jarvis/planner/safety_interceptor.py` | **Safety Classifier High-Risk Gap**: High-impact outbound comms (Email, Zalo, Discord) and physical Home Assistant actuation ran without confirmation. | Expanded `HIGH_RISK_ACTIONS` and dynamic prefixes in `safety_interceptor.py`. Mandated 30-second token confirmation flow; preserved read-only queries. | `tests/unit/test_action_dispatcher_safety.py` + `test_home_assistant_authoritative.py` (17 tests pass) |

### 2.2 Operational P0s for General Availability (GA)

While code-level P0s are 0, transitioning from **Internal Beta Pilot** to **General Availability (GA)** requires addressing two operational release hazards:

1. **Unverified Human Voice Usability (H-13)**: Distributing a desktop voice assistant without empirical validation by a native speaker in a live room creates an extreme risk of end-user abandonment.
2. **Untrusted Installation & Clean-Machine Runtime Integrity**: Distributing an installer binary without clean-machine VM installation, update, and rollback validation poses a risk of host system corruption or installer crash on vanilla Windows 11 machines.

#### Accepted-Risk Statement for Internal Beta Pilot:
> For the **Internal Beta Pilot**, the system is operated exclusively on the primary developer workstation (`Duong-Phuoc-Hung`) by the primary user. In this closed environment, acoustic parameters are tuned, terminal controls provide direct oversight, and all unconfigured services fail closed safely. Therefore, the operational GA blockers are accepted for the Internal Beta Pilot under `CONDITIONAL GO`.

---

## 3. P1 Pre-GA Risk Register (High-Severity Operational & Ecosystem Risks)

The following high-severity (P1) risks must be actively mitigated prior to commercial or general public release:

| Risk ID | Category | Risk Description | Impact | Probability | Owner | Technical Mitigation Strategy | ETA / Milestone | Accepted-Risk Statement for Beta Pilot |
|---|---|---|:---:|:---:|---|---|:---:|---|
| **P1-01** | External APIs | **Third-Party API Rate Limits & Quotas**: Exceeding free/tier quotas on OpenAI, Gemini, ElevenLabs, or OpenWeatherMap causes service degradation. | Medium | Medium | Primary User | Integrated `TokenBucketRateLimiter`, TTLCache (600s), Tier-1 offline rule router (handles 99.5% of common commands offline), and `wttr.in` zero-key weather fallback. | Pre-GA | Pilot volume is low (<50 calls/day); offline fallbacks ensure system stability when API keys are absent or rate-limited. |
| **P1-02** | Packaging & Security | **Windows SmartScreen Prompt on Self-Signed Authenticode**: Free CI pipeline generates self-signed certificate, triggering SmartScreen "Unknown Publisher" warning on clean machines. | High | High | Release Engineer | Binary is Authenticode signed with SHA-256 digest and RFC-3161 timestamping; users click "More info → Run anyway". Roadmap documented in `docs/signing/production_signing_upgrade.md` to acquire Azure Code Signing / Sectigo CA. | Pre-GA (Phase 4) | Pilot user installs directly from source repository (`.venv`) or explicitly whitelists local self-signed binary. |
| **P1-03** | System Resources | **GPU VRAM Allocation Contention**: Simultaneous execution of Faster-Whisper `large-v3` (~3GB VRAM) and local Vision/LLM models causes CUDA Out-Of-Memory (OOM). | High | Low | Primary User | `AudioEngine` defaults to `small` model (~800MB VRAM); `large-v3` is loaded on demand. System automatically falls back to CPU FP32/INT8 execution if CUDA OOM occurs. | Pre-GA | Developer workstation possesses dedicated NVIDIA RTX GPU with sufficient VRAM for pilot workloads. |
| **P1-04** | Audio Drivers | **Bluetooth HFP Driver Variation Across Windows Stacks**: Incompatible Bluetooth drivers (Broadcom, Intel, Realtek) hold exclusive audio sessions resulting in `PaError -9999`. | Medium | Medium | Primary User | Implemented two-tier capture fallback: PortAudio → WASAPI Exclusive mode (16kHz mono) → fail-closed MOCK mode. Config flag `use_wasapi_exclusive` enabled. | Pre-GA | Pilot operates primarily via wired USB microphone or Realtek internal microphone array (Tier-1 verified). |
| **P1-05** | Persistence | **SQLite Memory Store Growth & Concurrency Lock**: Extended multi-turn dialogs and semantic embeddings could cause SQLite database locks or excessive disk consumption. | Low | Low | Primary User | `logs/memory.db` configured in SQLite WAL (Write-Ahead Logging) mode with 30-thread concurrency verification; vector store utilizes atomic thread-safe file snapshots. | Pre-GA | Pilot session database size remains <50MB; automated vacuum maintenance scheduled. |
| **P1-06** | Browser Sandbox | **Playwright Chromium Memory Accumulation**: Long-running browser automation sessions retain background renderer processes. | Medium | Low | Primary User | Browser controller terminates headless Chromium instances on idle timeout; CDP attachment uses ephemeral connections. | Pre-GA | Browser automation is disabled by default (`labs.enabled = False`). |

---

## 4. Hardware-Blocked Acceptance Gates Register (The 5 Definitive Gates)

Five acceptance gates cannot be closed by software unit tests or simulated doubles alone. They require physical hardware, external infrastructure, or human participation. In accordance with `AGENTS.md §2`, these gates are documented with complete transparency:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        THE 5 HARDWARE-BLOCKED GATES                              │
├────┬─────────────────────────────┬───────────────────────────┬──────────────────┤
│ #  │ Gate Identifier             │ Truthful Current Status   │ Blocking Root    │
├────┼─────────────────────────────┼───────────────────────────┼──────────────────┤
│ 1  │ TShark / Npcap Live Capture │ TOOL_NOT_FOUND            │ Npcap UAC Driver │
│ 2  │ Home Assistant Live Hub     │ UNAVAILABLE               │ Physical LAN Hub │
│ 3  │ Clean-Machine VM Lifecycle  │ CI_SIGNATURE_ONLY         │ Clean Windows VM │
│ 4  │ Voice Acceptance (H-13)     │ PENDING_HUMAN_EXECUTION   │ Human Tester     │
│ 5  │ Bluetooth HFP Audio Capture │ SOFTWARE_PASS_ONLY        │ BT Headset HW    │
└────┴─────────────────────────────┴───────────────────────────┴──────────────────┘
```

---

### 4.1 Gate 1: TShark / Npcap Live Packet Capture (`R7a`, `R11`)

- **Subsystem**: `jarvis.security.scanner.PacketCapture` (`jarvis/security/scanner.py`)
- **Truthful Current Status**: **`TOOL_NOT_FOUND`** (Tier 2 Fail-Closed PASS, Tier 1 Live Capture BLOCKED)
- **Root Cause & Blocker Description**:
  `tshark.exe` is absent from host `PATH` and default installation paths (`C:\Program Files\Wireshark\tshark.exe`). While `winget install WiresharkFoundation.Wireshark` is available, Wireshark packet capture relies on the **Npcap kernel-mode packet filter driver**. Installing Npcap requires an interactive Windows User Account Control (UAC) elevation prompt, which cannot be approved non-interactively by headless terminal commands or automated CI/CD runners.
- **Exact PASS Criteria (Observable Metric)**:
  1. Wireshark and Npcap installed with driver service running (`sc query npcap` returns `RUNNING`).
  2. `resolve_tshark_binary()` resolves a valid path to `tshark.exe`.
  3. Invoking `PacketCapture().capture_packets(interface="Ethernet", count=10)` executes a real child process and returns `PacketCaptureResult`:
     - `status == "SUCCESS"`
     - `packet_count > 0`
     - `protocols` dictionary contains genuine parsed protocol counters (e.g. `{"tcp": 8, "udp": 2}`)
     - Child process exit code 0; duration > 0.0s.
  4. Real stdout/stderr output captured verbatim in `docs/eval/tshark_live_evidence_v2.md`.
- **Needed Hardware / Environment**: Physical Windows 11 host with active Network Interface Card (NIC) and an interactive Administrator session to approve the Npcap UAC dialog.
- **Responsible Owner**: Primary User (Administrator).
- **Accepted-Risk Statement for Internal Beta Pilot**:
  Network packet inspection is classified as an experimental tool protected by `@require_labs("tshark_capture")` and disabled by default (`labs.enabled = False`). When invoked without the binary, `capture_packets()` fails closed safely with `TOOL_NOT_FOUND` and returns 0 packets without crashing the host.

---

### 4.2 Gate 2: Home Assistant Local / LAN Instance (`R7d`)

- **Subsystem**: `jarvis.smart_home.home_assistant.HomeAssistantClient` (`jarvis/smart_home/home_assistant.py`)
- **Truthful Current Status**: **`UNAVAILABLE`** (Tier 2 Fail-Closed PASS, Tier 1 Live Actuation BLOCKED)
- **Root Cause & Blocker Description**:
  Empirical network probes to `http://homeassistant.local:8123` fail with `[Errno 11001] getaddrinfo failed` (DNS resolution failure), and probes to `http://localhost:8123` time out. No Home Assistant OS, Container, or Core server instance is running on the local host or connected local area network.
- **Exact PASS Criteria (Observable Metric)**:
  1. Home Assistant server reachable over HTTP/HTTPS with response status 200/401.
  2. `HomeAssistantClient.is_configured` evaluates to `True` with a valid, non-placeholder Long-Lived Access Token.
  3. **Read Path Verification**: `client.get_state("light.living_room")` returns genuine entity JSON containing `state` and `attributes`.
  4. **Write Path Verification**: `client.call_service("light", "turn_on", {"entity_id": "light.living_room"})` returns `ActionResult(status=ActionStatus.SUCCESS, code="OK")`, and the physical/emulated appliance changes state.
  5. Real HTTP request and response payloads recorded verbatim in `docs/eval/ha_evidence_v2.md`.
- **Needed Hardware / Environment**: Dedicated Home Assistant server (Raspberry Pi, Home Assistant Green, or Docker container) on LAN, configured with at least one smart light or switch entity.
- **Responsible Owner**: Primary User (Home Automation Lead).
- **Accepted-Risk Statement for Internal Beta Pilot**:
  The smart home module reports canonical health status `StatusLevel.UNAVAILABLE` in the terminal UI and returns `code="CONNECTION_FAILED"` (`retryable=True`). High-risk actuation is strictly protected by the 30-second user confirmation gate in `safety_interceptor.py`.

---

### 4.3 Gate 3: Clean-Machine VM Installer, Update & Rollback Testing (`R7e`, `D-12`, `D-13`)

- **Subsystem**: Installer package (`dist/installer/JARVIS_Setup_v5.1.0.exe`), standalone binary (`dist/JARVIS.exe`), and auto-updater (`jarvis/workers/updater.py`).
- **Truthful Current Status**: **`CI_INTEGRITY_PASS / PRODUCTION_TRUST_PENDING`** (Binary built and Authenticode signed; clean-machine execution pending)
- **Root Cause & Blocker Description**:
  The developer workstation has Python 3.13, Git, CUDA, PyInstaller, and development libraries installed. Validating that a non-technical end-user can install JARVIS on a pristine Windows machine requires testing on a clean virtual machine containing no pre-existing Python runtime, environment variables, or development dependencies.
- **Exact PASS Criteria (Observable Metric)**:
  1. Fresh Windows 11 64-bit VM snapshot without Python or Git installed.
  2. Download `JARVIS_Setup_v5.1.0.exe` or `JARVIS_v5.2.0_windows_x64.zip`.
  3. Run installer: desktop shortcut created, Start Menu entry registered, system tray initializes upon launch.
  4. Verify SmartScreen prompt workflow ("More info → Run anyway") operates as expected for self-signed binaries.
  5. Execute basic voice/text commands in frozen PyInstaller runtime.
  6. **Auto-Updater Test**: Trigger update check, download mock new version, verify SHA-256 checksum, perform atomic replace on restart.
  7. **Rollback Test**: Inject corrupted update payload, verify updater aborts replace due to hash mismatch, and restores previous operational version cleanly.
- **Needed Hardware / Environment**: Hyper-V, VMware Workstation, or VirtualBox hypervisor with a clean Windows 11 guest snapshot.
- **Responsible Owner**: Primary User / Release Engineer.
- **Accepted-Risk Statement for Internal Beta Pilot**:
  For the Internal Beta Pilot, JARVIS is executed directly from the verified Python virtual environment (`.venv`) on the development workstation. Standalone distribution to external users is deferred until GA.

---

### 4.4 Gate 4: Live Human Voice Acceptance Testing (H-13)

- **Subsystem**: Speech-to-Text & Intent Router Pipeline (`TieredSTTEngine`, `FasterWhisperSTT`, `IntentRouter`, `ActionDispatcher`).
- **Truthful Current Status**: **`PENDING_HUMAN_EXECUTION`** (Protocol established in `docs/eval/beta_voice_50_live_acceptance_protocol.md`; automated mock integration passing 28/28).
- **Root Cause & Blocker Description**:
  Automated tests inject pre-recorded audio buffers or mock STT text strings. They cannot evaluate acoustic room reverberation, microphone background noise, distance attenuation (50–80 cm), Vietnamese regional accent variations, or audio buffer synchronization under live operating conditions. Under `AGENTS.md §2`, automated tests cannot substitute for human voice validation.
- **Exact PASS Criteria (Observable Metric)**:
  1. A native Vietnamese speaker sits 50–80 cm from the physical microphone in a quiet room (<45 dBA).
  2. Speaks all 50 predefined utterances across the 10 core workflows documented in `docs/eval/beta_voice_50_live_acceptance_protocol.md` using wake word ("JARVIS ơi") or hotkey (`Ctrl+Shift+L`).
  3. **Task-Level Success Threshold**: **≥ 95% (at least 48/50 utterances passed)**.
  4. Each utterance logged with Whisper transcribed text, router predicted intent, dispatcher status, and observer sign-off.
- **Needed Hardware / Environment**: Calibrated PC microphone (internal array or external USB mic), quiet acoustic environment, and human operator.
- **Responsible Owner**: Primary User (Voice Evaluator).
- **Accepted-Risk Statement for Internal Beta Pilot**:
  Independent acoustic evaluations across 840 pre-recorded WAV trials (Whisper Small & Large-v3 across Clean and Noisy acoustic conditions) demonstrated 0.0% silent dropouts (`STT_EMPTY = 0`), 1.0%–3.3% bounded misrouting, and 99.5% router accuracy on independent Vietnamese utterances.

---

### 4.5 Gate 5: Bluetooth HFP Audio Capture Physical Verification (H-10)

- **Subsystem**: `jarvis.audio.engine.AudioEngine` (`_stream_worker`).
- **Truthful Current Status**: **`SOFTWARE_PASS_ONLY`** (WASAPI Exclusive capture implemented; physical Bluetooth headset pairing unverified).
- **Root Cause & Blocker Description**:
  PortAudio fails with `PaError -9999` (paDeviceUnavailable) on Windows when opening Bluetooth Hands-Free Profile (HFP) input streams due to exclusive OS session locking. The software remediation implements a two-tier fallback: standard PortAudio → WASAPI Exclusive mode (16kHz mono, `sd.WasapiSettings(exclusive=True)`) → fail-closed MOCK mode. Software unit tests pass 10/10, but live signal capture on physical BT hardware requires physical devices.
- **Exact PASS Criteria (Observable Metric)**:
  1. Bluetooth headset (AirPods, LY-Z5202, etc.) paired and connected to Windows 11 host.
  2. `AudioEngine` initialized with `JARVIS_INPUT_DEVICE` set to the Bluetooth HFP device index.
  3. Stream initializes in WASAPI Exclusive mode without raising `PaError -9999`.
  4. Spoken test utterance produces non-zero audio buffer with RMS signal peak > 0.02.
  5. Results and device metadata documented in `docs/eval/audio_hardware_compatibility_matrix.md`.
- **Needed Hardware / Environment**: Host Bluetooth 5.0+ adapter and paired Bluetooth HFP headset.
- **Responsible Owner**: Primary User.
- **Accepted-Risk Statement for Internal Beta Pilot**:
  The primary user operates using wired USB audio or the Realtek internal microphone array (Tier-1 verified). If Bluetooth HFP is selected and fails, the engine falls back to MOCK mode fail-closed with explicit log warning.

---

## 5. Release Gate Decision Tree (Transition from CONDITIONAL GO to Full GO)

To transition JARVIS from **`CONDITIONAL GO — Internal Beta Pilot`** to **`GO — General Availability Release`**, the following conditions must be satisfied:

```
                          [ CURRENT STATE: CONDITIONAL GO ]
                                         │
        ┌────────────────────────────────┴────────────────────────────────┐
        ▼                                                                 ▼
[ Governance Gates: R9 & R10 ]                                [ Runtime Hardware Gates ]
  ✅ R9: docs/credentials_registry.md                            Gate 1: TShark / Npcap Live Test
  ✅ R10: docs/risk_register.md                                  Gate 2: Home Assistant Write Path
                                                                 Gate 3: Clean VM Install/Rollback
                                                                 Gate 4: 50 Live Voice Utterances (≥95%)
                                                                 Gate 5: Bluetooth HFP Physical Audio
        │                                                                 │
        └────────────────────────────────┬────────────────────────────────┘
                                         ▼
                            Are all 5 Hardware Gates CLOSED?
                                ├── NO  ──> Maintain CONDITIONAL GO (Beta Pilot Only)
                                └── YES ──> Advance Verdict to FULL PRODUCT GO
```

All team members, automated agents, and auditors must reference this document as the single source of truth for project risk posture.
