# Specification Mining Report & Acceptance Contracts

**Author**: Spec Miner 3 (E2E Testing Track)  
**Target Workspace**: `d:/Software GitCode/JARVIS`  
**Primary Authoritative Specifications**:  
- `d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md` (Requirements R1 - R15)  
- `d:/Software GitCode/JARVIS/PROJECT.md` (Features F-01 to F-43 & Interface Contracts)  
- `d:/Software GitCode/JARVIS/TEST_INFRA.md` (4-Tier Headless Test Framework)  
- `d:/Software GitCode/JARVIS/jarvis-main/jarvis.py` (Legacy Monolith Implementation & Tuning Knobs)  
**Date**: 2026-08-22  

---

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Audio Timing | Double Clap Detection | Detects 2 transients spaced 0.05s - 0.35s with 0.45s cooldown | Stream of PCM audio blocks (`float32` array, 44.1kHz, 40ms block) | `GestureEvent(type="double_clap", timestamp=float, confidence=float)` | Ignored if gap < 0.05s or > 0.35s; ignores sub-threshold RMS (< 0.012) | `jarvis-main/jarvis.py:64-70,1008-1038`, `PROJECT.md:F-05` |
| 2 | Audio Timing | Triple Clap Detection | Detects 3 consecutive transients with inter-clap gaps in [0.05s, 0.40s], total window <= 0.85s | Stream of PCM audio blocks | `GestureEvent(type="triple_clap", timestamp=float)` | State resets if gap between any consecutive clap exceeds 0.40s | `PROJECT.md:F-06`, `ORIGINAL_REQUEST.md:R3` |
| 3 | Audio Timing | Clap-Pause-Clap Rhythm | Detects syncopated rhythm: initial clap -> pause (0.50s - 1.20s silence) -> resolving clap | Stream of PCM audio blocks | `GestureEvent(type="clap_pause_clap", timestamp=float)` | Resets if sound occurs during pause phase or resolving clap exceeds 1.50s | `PROJECT.md:F-07`, `ORIGINAL_REQUEST.md:R3` |
| 4 | Audio Timing | Adaptive Noise Floor & Schmitt Trigger | Computes EMA noise floor ($\alpha=0.992$) and enforces retrigger hysteresis (0.55x threshold) | Raw mono audio blocks (`np.ndarray`) | Updated noise floor float & armed boolean state | Clamped to $10^{-7}$; updates only when $RMS < noise\_floor \times 2.2$ | `jarvis-main/jarvis.py:64-71,994-1013`, `PROJECT.md:F-03` |
| 5 | Audio Timing | Microphone Auto-Probe | Scans all input devices and selects loudest device if default RMS < 0.001 | Hardware audio devices list | Active device index (`int`) | If all devices silent, falls back to default device index 0 without crashing | `jarvis-main/jarvis.py:72-75,153-247`, `PROJECT.md:F-04` |
| 6 | Configuration | Config Hot-Reload Watcher | Detects YAML/JSON/`.env` changes and reloads configuration in <= 5s without restart | File modification event on `config.yaml` / `config.json` | Updated `JarvisConfig` object dispatched to registered callbacks | Syntax/schema errors logged as warning; keeps prior valid in-memory config | `PROJECT.md:F-10`, `ORIGINAL_REQUEST.md:R4`, `PROJECT.md:110-115` |
| 7 | Configuration | Dynamic Plugin Reconfiguration | Enables/disables plugins and updates runtime parameters dynamically | Dynamic plugin dictionary / event payload | Updated plugin registry state | Defective plugin initialization isolated; does not halt event bus | `PROJECT.md:F-08,F-09`, `ORIGINAL_REQUEST.md:R4` |
| 8 | Hardware & Infra | Telemetry Metric Polling | Periodically collects CPU %, CPU Temp (°C), GPU %, GPU Temp, RAM %, VRAM, and Disk space | Polling interval timer (default 5.0s) | `HardwareTelemetry` data structure | Unavailable sensors (e.g. non-NVIDIA GPU, VM) return `None`/`N/A` gracefully | `PROJECT.md:F-20`, `ORIGINAL_REQUEST.md:R7` |
| 9 | Hardware & Infra | RAM Threshold Alert | Triggers warning & self-healing evaluation when RAM utilization > 90.0% | System virtual memory percentage (`psutil.virtual_memory().percent`) | Spoken voice alert + event trigger to `HealingWatchdog` | Debounced to prevent continuous alert loops (min 60s cooldown) | `ORIGINAL_REQUEST.md:R7,R15`, `PROJECT.md:F-22,F-41` |
| 10 | Hardware & Infra | CPU Overheating Warnings | Triggers voice alert when CPU temperature exceeds 85.0°C (warning) or 95.0°C (critical) | CPU thermal sensor reading (°C) via WMI/CIM/psutil | Synthesized voice alert: "Cảnh báo: Nhiệt độ CPU..." | Missing thermal sensors log debug message and bypass alert | `ORIGINAL_REQUEST.md:R7`, `PROJECT.md:F-20,F-22` |
| 11 | Hardware & Infra | S.M.A.R.T. Disk Health Check | Evaluates disk failure prediction, bad sector count, SSD wear-out, and drive temp | `smartctl` output or WMI `MSStorageDriver_FailurePredictStatus` | `SMARTHealthReport(status="HEALTHY"\|"WARNING"\|"CRITICAL")` | Missing `smartctl` falls back to WMI disk status query | `PROJECT.md:F-21`, `ORIGINAL_REQUEST.md:R7` |
| 12 | Hardware & Infra | Voice Hardware Status Query | Responds to voice command ("Jarvis, tình trạng hệ thống?") with comprehensive hardware summary | Transcribed user intent `SystemStatusQuery` | Synthesized spoken speech summary | Missing metrics omitted from speech string seamlessly | `ORIGINAL_REQUEST.md:R7`, `PROJECT.md:F-22` |
| 13 | Biometric Security | Face Enrollment & Verification | Matches live webcam video frames against enrolled owner 128-d face encodings | Video stream frames (`np.ndarray`) | `AuthResult(authenticated=True/False, confidence=float)` | Webcam unavailable falls back to bypass mode or logs error | `PROJECT.md:F-33`, `ORIGINAL_REQUEST.md:R12` |
| 14 | Biometric Security | Biometric Privilege Gate | Intercepts high-risk actions (Nmap, shell execution, credential access) if unauthenticated | Requested action name + `SecurityContext` | Permission granted (`bool`) or `AccessDeniedError` | Blocked action logs security warning and speaks access requirement | `PROJECT.md:F-34,F-23`, `ORIGINAL_REQUEST.md:R8,R12` |
| 15 | Biometric Security | Intruder Detection & Auto-Lock | Stranger face detected -> Win32 `LockWorkStation()` + webcam photo snapshot + Telegram alert | Webcam frame with unmatched face persisting >= 1.0s | Workstation locked, `.jpg` saved to cache, photo sent to Telegram | Missing Telegram token logs photo locally without crashing | `PROJECT.md:F-35`, `ORIGINAL_REQUEST.md:R12` |
| 16 | Biometric Security | Headless Biometric Bypass Mode | Allows test runners and headless servers to bypass camera authentication | Config flag `BIOMETRIC_BYPASS=true` / `JARVIS_BIOMETRIC_BYPASS=1` | `SecurityContext(authenticated=True, auth_method="bypass")` | Warning logged in production if bypass enabled | `ORIGINAL_REQUEST.md:R12`, `PROJECT.md:87` |
| 17 | Self-Healing | Unresponsive App Detection | Scans top-level windows using Win32 `IsHungAppWindow(hwnd)` to find frozen processes | Windows HWND enumeration via `EnumWindows` | List of `HungProcessInfo(pid=int, name=str, hwnd=int)` | Protected OS system processes (explorer, csrss) strictly filtered out | `PROJECT.md:F-42`, `ORIGINAL_REQUEST.md:R15` |
| 18 | Self-Healing | Autonomous Memory Reclamation | Terminates hung/memory-hog processes when RAM > 90% or app is frozen | Target process PID & configured healing mode | Process terminated (`terminate()` -> `kill()`), RAM reclaimed | If process fails to terminate, logs permission error and skips | `PROJECT.md:F-43,F-41`, `ORIGINAL_REQUEST.md:R15` |
| 19 | Self-Healing | Spoken Healing Voice Report | Announces remediation action taken and current RAM level via TTS | Process name + post-healing RAM utilization % | Synthesized speech: "Hệ thống bị quá tải. Đã xử lý: [Name]. RAM: X%" | If TTS fails, status logged to disk | `ORIGINAL_REQUEST.md:R15`, `PROJECT.md:F-43` |
| 20 | Comms Hub | Telegram Whitelist Security Gate | Intercepts incoming Telegram bot messages and rejects non-whitelisted user IDs | Telegram update payload with `from_user.id` | Message processed or dropped with 403 Forbidden | Unauthorized access logged with intruder user ID | `PROJECT.md:F-38`, `ORIGINAL_REQUEST.md:R14` |
| 21 | Comms Hub | Telegram Remote Bot Control | Executes remote `/status`, `/lock`, and action commands from authorized Telegram users | Telegram text commands (`/status`, `/lock`, `/exec`) | Telegram reply message with formatted status / execution result | Invalid commands return help syntax | `PROJECT.md:F-38`, `ORIGINAL_REQUEST.md:R14` |
| 22 | Comms Hub | IMAP Priority Email Reader | Connects via IMAP SSL (port 993), polls unread emails from priority senders | IMAP server host, port, credentials, unread flags | Parsed `EmailMessage` list (sender, subject, body text) | Connection/auth failure logs warning and schedules retry | `PROJECT.md:F-39`, `ORIGINAL_REQUEST.md:R14` |
| 23 | Comms Hub | IMAP Email LLM Summary & TTS | Summarizes unread priority emails using LLM and reads aloud via TTS | Raw email body text + metadata | Spoken summary: "Email mới từ [Sender] về [Subject]. Tóm tắt: [...]" | Truncates emails > 10,000 chars before LLM prompt | `PROJECT.md:F-39`, `ORIGINAL_REQUEST.md:R14` |
| 24 | Data Analytics | Dataset Ingestion & Statistics | Ingests CSV/XLSX and computes full descriptive statistics & correlations | File path to `.csv` or `.xlsx` | `DataSummaryReport` (mean, median, std, min, max, percentiles, correlation) | Malformed/empty file raises `DataIngestionError` with diagnostics | `PROJECT.md:F-28`, `ORIGINAL_REQUEST.md:R10` |
| 25 | Data Analytics | Monte Carlo Simulation Bounds | Runs $N$ probabilistic iterations ($N \in [10^3, 10^5]$) to calculate P5, P50, P95 bounds | Simulation parameters (distribution type, mean, std, target, iterations) | `SimulationResult(mean=float, std_err=float, p5=float, p50=float, p95=float, p_target=float)` | Invalid parameter bounds (e.g. std <= 0) raise validation error | `PROJECT.md:F-29`, `ORIGINAL_REQUEST.md:R10` |
| 26 | Data Analytics | Multi-Format Document Exporter | Exports structured analytical reports to DOCX, PDF, and PPTX with embedded charts | `DataSummaryReport`, `SimulationResult`, matplotlib figures | Output `.docx`, `.pdf`, `.pptx` files on disk | Missing optional libraries (python-docx/pptx) trigger graceful fallback | `PROJECT.md:F-30`, `ORIGINAL_REQUEST.md:R10` |
| 27 | Data Analytics | Voice Executive Summary | Generates concise vocal summary of dataset metrics and Monte Carlo probabilities | Analysis and simulation result metrics | Spoken text: "Đã hoàn thành phân tích [File]. Giá trị trung bình... Xác suất..." | TTS failure logged without aborting file export | `ORIGINAL_REQUEST.md:R10`, `PROJECT.md:F-30` |

---

## Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Double Clap Detection | Continuous white noise at 85 dB | Exponential moving average adapts noise floor upwards; `quiet_gate = floor * 2.2` stops updates during loud audio; no false trigger. |
| 2 | Double Clap Detection | Single loud impulse (e.g. door slam) | Arms first clap at $t_1$; second transient never arrives; after 0.35s window expires, state resets to un-triggered cleanly. |
| 3 | Double Clap Detection | Ultra-fast double transient separated by 20ms (< 0.05s) | Filtered out as mechanical bounce/echo (`gap < MIN_DOUBLE_GAP_S`); does not advance double clap state. |
| 4 | Double Clap Detection | Claps spaced exactly 0.34s apart (boundary condition) | Successfully detected as double clap (`0.05s <= gap <= 0.35s`); dispatches action and initiates 0.45s cooldown. |
| 5 | Double Clap Detection | Claps spaced 0.36s apart (boundary condition) | First clap expires; second clap is treated as a new first clap; no double-clap event dispatched. |
| 6 | Triple Clap Detection | 2 claps separated by 0.20s followed by silence | Double clap does not prematurely trigger if triple-clap detector is active, or disambiguator resolves to double-clap after 0.40s timeout. |
| 7 | Clap-Pause-Clap Detection | Continuous claps (clap-clap-clap-clap) with no pause | Rejected by clap-pause-clap detector because audio level in pause window ([0.5s, 1.2s]) exceeds noise floor threshold. |
| 8 | Config Hot-Reload | `config.yaml` saved with invalid YAML syntax (corrupted indentation) | `ConfigManager` catches `yaml.YAMLError`, logs line number warning, and retains current active in-memory configuration without crashing. |
| 9 | Config Hot-Reload | Rapid repeated file saves (3 modifications in 200ms) | Debounces file change events; executes single atomic reload of the final file version within 5.0 seconds. |
| 10 | Hardware Monitor | Host has no discrete GPU or runs in virtualized CI container | `HardwareMonitor` catches missing `pynvml` / WMI GPU classes; reports GPU metrics as `None` or `{}` without raising uncaught exceptions. |
| 11 | Hardware Monitor | RAM fluctuates between 89.9% and 90.1% every second | Hysteresis threshold and alert cooldown timer (60s) prevent spamming voice alerts and redundant healing cycles. |
| 12 | Hardware Monitor | WMI CPU temperature query returns `NotSupported` / permission denied | Gracefully falls back to `psutil.cpu_percent()` only; logs single diagnostic warning without crashing telemetry loop. |
| 13 | S.M.A.R.T. Prober | Virtual disk (VMDK/VHDX) where S.M.A.R.T. attributes are unavailable | Returns `SMARTHealthReport(status="UNKNOWN", details={"virtual_drive": True})`; skips bad sector checks. |
| 14 | Biometric Gate | High-privilege action (`nmap_scan`) called when `SecurityContext.authenticated = False` | `ActionDispatcher` halts execution immediately, returns `ActionResult(success=False, error="BiometricAuthRequired")`, and speaks vocal warning. |
| 15 | Biometric Security | Webcam disconnected or unavailable when action triggered | In default mode: denies privileged access; in bypass mode (`BIOMETRIC_BYPASS=true`): grants access and logs audit record. |
| 16 | Intruder Detection | Live webcam detects unknown face in frame | Evaluates unknown face for >= 1.0s to avoid transient glitches; triggers Win32 `LockWorkStation()`, saves snapshot, dispatches Telegram photo alert. |
| 17 | Intruder Detection | Pitch black webcam frame (average pixel intensity < 5) | Classified as camera occlusion or dark room; does NOT trigger false-positive intruder workstation lock. |
| 18 | Process Watchdog | Critical Windows system process (`explorer.exe` or `dwm.exe`) becomes unresponsive | `HealingWatchdog` identifies PID, checks protected OS whitelist, and strictly aborts termination; logs advisory warning only. |
| 19 | Process Watchdog | Hung user process (e.g. `chrome.exe`) ignores graceful `SIGTERM` / `WM_CLOSE` | Watchdog waits 3.0s timeout; proceeds to force-kill via `process.kill()` (`SIGKILL` / `TerminateProcess`); verifies RAM drop. |
| 20 | Process Watchdog | Zero processes are hung when RAM > 90% | Identifies top non-whitelisted memory consumer process; triggers configured advisory alert or policy-driven restart. |
| 21 | Telegram Hub | Unauthorized Telegram user sends `/status` or `/lock` | Interceptor verifies sender ID against `TELEGRAM_ALLOWED_USER_IDS`; drops message, returns 403 Forbidden, and logs security event with sender ID. |
| 22 | Telegram Hub | Telegram API server unreachable or bot token invalid | Polling worker catches network exception, logs warning, implements exponential backoff retry; does not block main JARVIS daemon. |
| 23 | IMAP Email Hub | Unread email contains 50,000-character raw HTML/Base64 dump | IMAP parser strips HTML tags, extracts plain text, and truncates to 10,000 characters before passing to LLM summarizer. |
| 24 | Data Analytics | Ingested CSV file contains missing values (`NaN`) and mixed data types | `DataAnalyticsEngine` handles `NaN` in pandas calculations without division-by-zero or crash; notes missing value counts in report. |
| 25 | Monte Carlo Engine | User requests Monte Carlo simulation with 0 iterations or negative standard deviation | Validation schema rejects inputs; raises `ValueError` with clear validation message: "Iterations must be >= 1000, std > 0". |
| 26 | Document Exporter | Target export directory `reports/` does not exist on disk | Exporter automatically creates parent directories recursively (`Path.mkdir(parents=True, exist_ok=True)`) before writing `.docx`/`.pdf`. |

---

## 1. Observation

### 1.1 Direct Baseline Implementation Quotes (`jarvis-main/jarvis.py`)
- **Signal Processing Constants** (`jarvis.py:60-75`):
  ```python
  SAMPLE_RATE = 44100
  BLOCK_MS = 40
  CHANNELS = 1
  SPIKE_RATIO = 7.0
  COOLDOWN_S = 0.45
  MIN_DOUBLE_GAP_S = 0.05
  MAX_DOUBLE_GAP_S = 0.35
  RETRIGGER_RATIO = 0.55
  NOISE_FLOOR_ALPHA = 0.992
  MIN_RMS = 0.012
  QUIET_GATE_MULT = 2.2
  INPUT_PROBE_S = 0.5
  INPUT_SILENT_RMS = 0.001
  ```
- **Clap Detection State Machine** (`jarvis.py:994-1038`):
  ```python
  level = rms_mono(data)
  quiet_gate = noise_floor * QUIET_GATE_MULT
  if level < quiet_gate:
      noise_floor = NOISE_FLOOR_ALPHA * noise_floor + (1.0 - NOISE_FLOOR_ALPHA) * level
      noise_floor = max(noise_floor, 1e-7)

  threshold = max(noise_floor * SPIKE_RATIO, MIN_RMS)
  now = time.monotonic()
  retrigger_level = threshold * RETRIGGER_RATIO

  if level < retrigger_level:
      spike_armed = True

  if spike_armed and level >= threshold and (now - last_logged_double) >= COOLDOWN_S:
      spike_armed = False
      if first_clap_time is None:
          first_clap_time = now
      else:
          gap = now - first_clap_time
          if gap < MIN_DOUBLE_GAP_S:
              pass
          elif gap <= MAX_DOUBLE_GAP_S:
              first_clap_time = None
              last_logged_double = now
              # Trigger Double Clap Action Workflow
          else:
              first_clap_time = now
  ```

### 1.2 Authoritative Requirement Specifications (`ORIGINAL_REQUEST.md`)
- **R3 Audio Gestures**: "Phát hiện nhiều kiểu gesture: double clap, triple clap, clap-pause-clap, v.v. Mỗi pattern có thể gán action/workflow khác nhau qua file cấu hình, không cần sửa code."
- **R4 Hot-Reload**: "Người dùng có thể thêm, bật/tắt, sắp xếp lại actions qua file JSON/YAML. Hỗ trợ hot-reload: thay đổi config có hiệu lực ngay không cần restart (trong vòng 5 giây)."
- **R7 Hardware Diagnostics**: "Giám sát phần cứng chuyên sâu: nhiệt độ CPU/GPU, tốc độ quạt, mức sử dụng RAM/VRAM, tuổi thọ và tình trạng ổ cứng (S.M.A.R.T. data). Khi vượt ngưỡng cảnh báo, JARVIS tự động thông báo bằng giọng nói."
- **R8 & R12 Biometric Gating & Security**: "Tất cả lệnh này [Nmap, CLI security] chỉ kích hoạt được sau khi qua xác thực sinh trắc học (R12)... Nếu phát hiện khuôn mặt lạ khi máy đang chạy, tự động khóa màn hình Windows (LockWorkStation) và gửi cảnh báo (qua Telegram)."
- **R14 Multi-Channel Comms**: "Telegram Bot API, Discord Bot, và IMAP... Có thể nhận lệnh điều khiển từ xa qua Telegram (bảo mật bằng whitelist user ID)."
- **R15 Self-Healing Protocol**: "Giám sát liên tục tài nguyên hệ thống. Khi RAM vượt 90%, hoặc phát hiện tiến trình 'Not Responding' (Chrome, VMware, v.v.), JARVIS tự động kill tiến trình gây lỗi, giải phóng bộ nhớ, và báo cáo bằng giọng nói: 'Hệ thống bị quá tải. Đã xử lý: [tên tiến trình]. RAM hiện tại: X%'."
- **R10 Data Processing & Simulation**: "Nhận file dữ liệu (CSV, Excel) và thực hiện phân tích thống kê... mô phỏng Monte Carlo đơn giản. Kết quả xuất ra báo cáo (PDF/DOCX) hoặc slide thuyết trình (PPTX)... tóm tắt kết quả bằng giọng nói."

---

## 2. Logic Chain & Specification Contracts

### 2.1 Audio Timing & Acoustic Gesture Engine Contract

#### Mathematical & State Machine Model:
1. **Audio Sampling**: Monophonic PCM stream at $f_s = 44,100\text{ Hz}$. Analyzed in blocks of $N = \lfloor f_s \times 0.040 \rfloor = 1,764\text{ samples}$.
2. **RMS Level**:
   $$\text{RMS} = \sqrt{\frac{1}{N} \sum_{i=1}^{N} x_i^2}$$
3. **Noise Floor Filter**:
   $$\text{floor}_{t} = \begin{cases} 
   0.992 \cdot \text{floor}_{t-1} + 0.008 \cdot \text{RMS}_t & \text{if } \text{RMS}_t < 2.2 \cdot \text{floor}_{t-1} \\
   \text{floor}_{t-1} & \text{otherwise}
   \end{cases}$$
   Clamped to $\text{floor} \ge 10^{-7}$.
4. **Transient Detection Threshold**:
   $$\text{Threshold} = \max\left(7.0 \cdot \text{floor}, 0.012\right)$$
   $$\text{RetriggerThreshold} = 0.55 \cdot \text{Threshold}$$

#### Pattern Recognition Timing Specifications:
- **Double Clap (`F-05`)**:
  - Valid interval: $\Delta t \in [0.05\text{s}, 0.35\text{s}]$.
  - Debounce cooldown: $T_{\text{cooldown}} = 0.45\text{s}$.
  - Maximum detection latency: $\le 3.0\text{s}$.
- **Triple Clap (`F-06`)**:
  - Three transient peaks $(t_1, t_2, t_3)$ satisfying:
    $$\Delta t_1 = t_2 - t_1 \in [0.05\text{s}, 0.40\text{s}]$$
    $$\Delta t_2 = t_3 - t_2 \in [0.05\text{s}, 0.40\text{s}]$$
    $$\text{Total Duration } (t_3 - t_1) \le 0.85\text{s}$$
  - Post-trigger cooldown: $0.50\text{s}$.
- **Clap-Pause-Clap (`F-07`)**:
  - Transient 1 at $t_1$.
  - Pause duration: Silence where $\text{RMS} < \text{Threshold}$ for $\Delta t_{\text{pause}} \in [0.50\text{s}, 1.20\text{s}]$.
  - Resolving transient at $t_3 \in [t_1 + 0.55\text{s}, t_1 + 1.50\text{s}]$.
  - Post-trigger cooldown: $0.60\text{s}$.

---

### 2.2 Configuration Hot-Reload Contract

- **Latency Contract**: Configuration changes to `.env`, `config.yaml`, or `config.json` must be detected and fully applied within $\le 5.0\text{s}$ without process termination.
- **Atomic Swap & Error Isolation**:
  ```python
  class ConfigManager:
      def reload_if_changed(self) -> bool:
          # Check mtime / hash
          # Parse into temporary staging object
          # Validate pydantic schema
          # If valid: atomic swap self._config = staged_config; invoke callbacks
          # If invalid: log error, preserve existing self._config, return False
  ```
- **Callback Signature**: `Callable[[JarvisConfig], None]` invoked synchronously or in daemon threads upon successful reload.

---

### 2.3 Hardware Telemetry & Threshold Diagnostics Contract

- **Polling Frequency**: $0.2\text{ Hz}$ (every $5.0\text{s}$).
- **Monitored Telemetry Schema**:
  ```python
  @dataclass
  class HardwareTelemetry:
      cpu_percent: float          # 0.0 - 100.0%
      cpu_temp_c: Optional[float] # in °C
      gpu_percent: Optional[float]# 0.0 - 100.0%
      gpu_temp_c: Optional[float] # in °C
      ram_percent: float          # 0.0 - 100.0%
      ram_used_gb: float
      ram_total_gb: float
      vram_used_mb: Optional[float]
      vram_total_mb: Optional[float]
      disk_free_gb: float
      disk_free_percent: float
      smart_status: str           # "HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"
  ```
- **Alert Rules & Voice Feedback**:
  - `RAM_CRITICAL`: $\text{RAM} > 90.0\% \implies$ Alert + trigger healing evaluation.
  - `CPU_OVERHEAT`: $\text{CPU Temp} \ge 85.0^\circ\text{C} \implies$ Alert: `"Cảnh báo: Nhiệt độ CPU đạt [X] độ C."`
  - `CPU_THROTTLE`: $\text{CPU Temp} \ge 95.0^\circ\text{C} \implies$ Alert: `"Nguy hiểm: CPU quá nhiệt, hệ thống đang bị bóp hiệu năng!"`
  - `S.M.A.R.T._FAIL`: `PredictFailure == True` or bad sectors $> 50 \implies$ Alert: `"Cảnh báo: Ổ cứng có dấu hiệu hỏng hóc vật lý."`
  - Voice query contract for `"Jarvis, tình trạng hệ thống?"`: Synthesizes concise summary of CPU, RAM, Disk, and S.M.A.R.T. status.

---

### 2.4 Biometric Security, Access Gating & Intruder Auto-Lock Contract

- **Security Context Model**:
  ```python
  @dataclass
  class SecurityContext:
      authenticated: bool
      user_id: Optional[str]
      auth_method: Literal["biometric", "bypass", "password", "none"]
      session_expiry: float
  ```
- **Biometric Interception Rule**:
  - Any plugin with `security_level = "HIGH"` (e.g. `nmap_scanner`, `tshark_capture`, `admin_shell`) MUST call `ActionDispatcher.is_authorized(action_name, security_context)`.
  - If `authenticated == False` and `auth_method != "bypass"`:
    - Action execution is ABORTED.
    - Security violation is logged with timestamp and trigger source.
    - Voice warning is spoken: `"Yêu cầu xác thực sinh trắc học để thực hiện hành động này."`
- **Intruder Auto-Lock & Alert Protocol**:
  - Continuous webcam face verification: Computes Euclidean distance $d$ to enrolled face embeddings.
  - Intruder condition: Detected face has $\min(d) > 0.60$ for continuous duration $\ge 1.0\text{s}$.
  - Autonomous Execution Sequence:
    1. `ctypes.windll.user32.LockWorkStation()` invoked immediately.
    2. Camera frame saved to `.cache/security/intruder_{timestamp}.jpg`.
    3. Telegram Bot dispatches alert text + photo snapshot to `TELEGRAM_ALLOWED_USER_IDS`.

---

### 2.5 Process Watchdog & Self-Healing Protocol Contract

- **Detection Mechanism (`IsHungAppWindow`)**:
  - Enumerates top-level desktop windows via Win32 `EnumWindows`.
  - Calls `user32.IsHungAppWindow(hwnd) -> BOOL`.
  - Maps `hwnd` to process PID via `user32.GetWindowThreadProcessId`.
- **System Whitelist Protection**:
  - Under NO circumstance shall the watchdog terminate:
    `["explorer.exe", "dwm.exe", "csrss.exe", "smss.exe", "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe", "System", "Registry", "python.exe"]`.
- **Autonomous Remediation & Voice Reporting**:
  - Mode: `AUTONOMOUS` (auto-kill enabled) vs `ADVISORY` (alert only).
  - Termination sequence:
    1. Send graceful termination (`process.terminate()`).
    2. Wait up to $3.0\text{s}$.
    3. If still active, send forceful termination (`process.kill()`).
  - Voice Announcement Formula:
    `"Hệ thống bị quá tải. Đã xử lý: {process_name}. RAM hiện tại: {ram_percent:.1f}%."`

---

### 2.6 Multi-Channel Communications Hub Contract

- **Telegram Bot Whitelist Gate**:
  - Configuration: `TELEGRAM_ALLOWED_USER_IDS: List[int]` in `config.yaml` / `.env`.
  - Security Interceptor:
    ```python
    def handle_telegram_message(update: Update, context: CallbackContext) -> None:
        user_id = update.effective_user.id
        if user_id not in config.telegram_allowed_user_ids:
            logger.warning(f"Unauthorized Telegram access attempt from ID {user_id}")
            update.message.reply_text("403 Forbidden: Unauthorized User ID.")
            return
        # Execute authorized command
    ```
- **IMAP Email Reader & Summary Formatting**:
  - Filters: Unread messages (`UNSEEN`) from priority senders list.
  - Summary Prompt Template: Summarizes key points into 1-2 Vietnamese sentences.
  - Spoken Output Contract:
    `"Email mới từ {sender_name} về tiêu đề {subject}. Tóm tắt: {llm_summary}."`

---

### 2.7 Data Analytics, Monte Carlo Simulation & Document Export Contract

- **Descriptive Statistics Calculation**:
  - Input: `.csv` or `.xlsx` file path.
  - Output metrics: Mean, Median, Std Dev, Min, 25%, 75%, Max, Skewness, Kurtosis, Null Count.
- **Monte Carlo Simulation Model**:
  - Parameter bounds: Iterations $N \in [1,000, 100,000]$ (default $10,000$).
  - Outputs:
    - Expected Value: $\mu$
    - Standard Error: $\text{SE} = \frac{\sigma}{\sqrt{N}}$
    - Confidence Intervals: P5, P10, P50 (Median), P90, P95, P99.
    - Probability of Target Attainment: $P(X \ge \text{Target})$.
- **Export Format & File Delivery**:
  - **DOCX**: Multi-section Word document with formatted tables and embedded chart PNGs.
  - **PDF**: Formatted analytical report with headers, footers, and page numbers.
  - **PPTX**: 4-slide executive presentation deck.
  - **Voice Output**:
    `"Đã hoàn thành phân tích {filename}. Giá trị trung bình là {mean:.2f}, trung vị là {median:.2f}. Mô phỏng Monte Carlo {iterations:,} lần cho thấy xác suất đạt mục tiêu là {prob:.1f}% trong khoảng tin cậy 95% từ {p5:.2f} đến {p95:.2f}."`

---

## 3. Caveats & Assumptions

1. **Hardware Dependencies & Headless CI Isolation**:
   - Win32 APIs (`LockWorkStation`, `IsHungAppWindow`, `EnumDisplayMonitors`) are specific to Windows desktop sessions. In headless CI (Linux/Windows GitHub Actions), all Win32 calls must be intercepted by `MockWin32Platform`.
   - Audio microphone streams and webcam feeds must be fully mockable via `MockAudioStream` and synthetic frame generators without physical hardware.
2. **Third-Party Executables (Nmap, TShark, Smartctl)**:
   - JARVIS functions as a wrapper and orchestrator. If binaries are absent from `%PATH%`, the system must gracefully raise structured errors rather than crashing with unhandled `FileNotFoundError`.
3. **External Cloud APIs (ElevenLabs, OpenAI, Telegram, Home Assistant)**:
   - In offline or test environments, mock fixtures must simulate valid JSON/PCM responses, and the system must gracefully fall back to local alternatives (e.g. `pyttsx3` for TTS).

---

## 4. Conclusion & Acceptance Validation Criteria

The specification contracts mined above establish the authoritative ground truth for JARVIS across all 7 assigned operational domains. Any implementation or test suite must strictly satisfy the following validation criteria:

1. **Audio Timing**: Double clap must strictly adhere to $0.05\text{s} \le \Delta t \le 0.35\text{s}$ with $0.45\text{s}$ cooldown; Triple clap and Clap-Pause-Clap must be accurately disambiguated.
2. **Config Hot-Reload**: File modifications must take effect within $\le 5.0\text{s}$ without restarting or losing in-memory state during syntax errors.
3. **Hardware Thresholds**: RAM $> 90\%$ and CPU Temp $> 85^\circ\text{C}$ must trigger vocal alerts and self-healing evaluation.
4. **Biometric Security**: High-privilege actions (Nmap, admin shell) must be blocked without biometric authorization; stranger face must trigger `LockWorkStation()`, photo capture, and Telegram notification.
5. **Process Watchdog**: `IsHungAppWindow()` must detect frozen apps; protected OS processes (`explorer.exe`, etc.) must never be killed; RAM reclamation must be reported via voice.
6. **Communications**: Telegram bot must enforce whitelist user ID gating with 403 response on unauthorized messages; IMAP emails must be summarized and formatted for TTS.
7. **Data Analytics**: CSV/XLSX statistics must compute accurate descriptive metrics; Monte Carlo simulation must output P5-P95 confidence bounds; reports must export to DOCX/PDF with accompanying voice summary.

---

## 5. Verification Method

To independently verify these specifications against the project codebase and automated test suites:

1. **Execute E2E Unit & Integration Test Suites**:
   ```powershell
   python -m pytest tests/test_audio_dsp.py tests/test_gesture_detector.py tests/test_config.py tests/test_hardware_monitor.py tests/test_self_healing.py tests/test_biometrics.py tests/test_security_scanner.py tests/test_comms_hub.py tests/test_data_analytics.py -v
   ```
2. **Verify Timing Boundaries via Synthetic Fixtures**:
   - Run `test_gesture_detector.py` with synthetic double clap at $\Delta t = 0.04\text{s}$ (assert rejected) and $\Delta t = 0.20\text{s}$ (assert accepted).
3. **Verify Security Interceptor**:
   - Run `test_security_scanner.py` with `SecurityContext(authenticated=False)` and assert `AccessDeniedError` / `BiometricAuthRequired`.
4. **Verify Hot-Reload Latency**:
   - Run `test_config.py` modifying temporary YAML file and assert reload callback fires within $< 5.0\text{s}$.
5. **Invalidation Conditions**:
   - Any modification violating the $0.05-0.35\text{s}$ double clap timing, the 5s config reload latency, the 90% RAM threshold, or the biometric security gate invalidates specification compliance.
