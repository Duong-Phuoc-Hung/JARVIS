# Comprehensive Architecture & Survey Report
## Systems Under Investigation: R4 (Computer Control), R7 (Natural Language Shell), R8 (Always-On Intelligent Overlay)

- **Date**: 2026-08-24
- **Author**: Explorer Survey 3
- **Target Workspace**: `d:/Software GitCode/JARVIS`
- **Scope**: Requirements R4, R7, R8, System Health-Check & Integration Points

---

## Executive Summary

JARVIS is evolving from an acoustic gesture and voice-reactive assistant into an autonomous, proactive, always-on Personal AI system for Windows. This report details the complete architectural design, API specifications, component hierarchies, safety flow gates, and verification strategies for:
1. **R4 — Computer Control**: OS-level window orchestration, mouse/keyboard/clipboard automation, volume & brightness modulation, local file indexing & search, and a two-stage voice confirmation safety gate.
2. **R7 — Natural Language Shell**: Semantic command parsing for developer workflows (dev servers, git, package managers, Docker, netstat), an adversarial command regex safety gate, and intelligent multi-line stdout summarization optimized for Vietnamese TTS vocalization.
3. **R8 — Always-On Intelligent Overlay**: An Iron Man Arc Reactor HUD sidebar interface built on an enhanced thread-safe Tkinter canvas engine featuring dockable/collapsible sidebar mode (40px collapsed), 5-turn conversational history cards, quick action buttons, persistent memory previews, a 5-second real-time CPU/RAM/Battery status bar, dynamic multi-bar audio waveform spectrum visualization, and corner floating badge minimization.
4. **Health-Check & Integration**: CLI diagnostics matrix (`python -m jarvis health-check`), `JarvisApp` runtime coordination, configuration schemas, and regression test suites guaranteeing 100% pass across all 537+ existing tests plus ≥ 20 new tests.

---

## Part 1: Architecture Plan for R4 (Computer Control)

### 1.1 Objective & System Boundary
The Computer Control subsystem enables JARVIS to manipulate the Windows operating system environment through voice commands while preserving system stability, user responsiveness, and strict safety boundaries for destructive actions.

### 1.2 Module Organization
```
jarvis/
├── platform/
│   └── windows.py            # Low-level ctypes Win32 API layer (DPI v2, EnumWindows, SendInput)
├── automation/
│   ├── __init__.py
│   ├── control.py            # High-level OS controller (window, mouse, keyboard, clipboard, volume, brightness)
│   ├── file_search.py        # Fast local file indexer & folder launcher
│   ├── vm.py                 # Hypervisor VM manager (existing F-31)
│   └── workspace.py          # Developer workspace recipe manager (existing F-32)
```

---

### 1.3 Detailed Component Architecture

#### A. Window Management
`jarvis/platform/windows.py` already includes Per-Monitor DPI v2 awareness, multi-monitor enumeration, cloaking checks, and `AttachThreadInput`-assisted foreground focusing. For R4, the high-level `ComputerController` (`jarvis/automation/control.py`) will provide:

1. **Active Window Introspection**:
   - Query foreground window handle, title, process name, bounds, minimized/maximized state via `platform_win32.get_active_window()`.
2. **Minimize All / Show Desktop ("minimize tất cả", "hiện màn hình chính")**:
   - Implementation: Trigger `win32_platform.send_hotkey("win", "d")` or invoke `Shell.Application.ToggleDesktop()` through ctypes COM wrapper.
3. **Close Active Window / Close Tab ("đóng cửa sổ này", "đóng tab này")**:
   - Close Tab: Trigger `win32_platform.send_hotkey("ctrl", "w")`.
   - Close Window: Post `WM_CLOSE` to foreground window handle via `platform_win32.close_window(active_hwnd)` or fallback to `win32_platform.send_hotkey("alt", "f4")`.
4. **App Switching & Specific App Focusing ("chuyển sang Chrome", "focus Cursor", "Alt Tab")**:
   - "Alt Tab": `win32_platform.send_hotkey("alt", "tab")`.
   - Named Focus: `focus_app_by_name(name: str)` enumerates top-level visible windows via `platform_win32.list_windows()`, searches titles and process names (case-insensitive fuzzy substring), and brings matching HWND to foreground with thread unlock.

#### B. Mouse, Keyboard & Clipboard Automation
1. **Mouse Automation**:
   - Coordinates calculation mapped to primary or target monitor virtual desktop bounds.
   - Core API:
     ```python
     def mouse_click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1) -> bool
     def mouse_move(x: int, y: int, smooth: bool = True) -> bool
     def mouse_scroll(clicks: int) -> bool
     ```
   - Primary engine: `pyautogui` when installed, with a pure zero-dependency Win32 ctypes fallback using `user32.SetCursorPos(x, y)` and `user32.SendInput` / `user32.mouse_event(MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP)`.
2. **Keyboard Automation**:
   - Text entry: `type_text(text: str)` uses `platform_win32.type_unicode_text(text)` (`KEYEVENTF_UNICODE` 64-bit aligned input).
   - Hotkey injection: `send_hotkey(*keys: str)` maps symbolic keys (`ctrl`, `shift`, `alt`, `win`, `enter`, `esc`, `tab`, `space`, arrows) through `VK_MAP`.
3. **Clipboard Management**:
   - "JARVIS, copy cái này": Dispatches `send_hotkey("ctrl", "c")`, pauses 100ms, then reads clipboard text.
   - "JARVIS, dán vào đây": Injects `send_hotkey("ctrl", "v")`.
   - Clipboard Read/Write API: Zero-dependency Win32 ctypes using `user32.OpenClipboard`, `user32.GetClipboardData(CF_UNICODETEXT)`, `user32.SetClipboardData`, and `user32.CloseClipboard` (with `pyperclip` / `win32clipboard` as fallback).

#### C. Volume & Display Brightness Control
1. **Master Volume Modulation ("tăng âm lượng", "giảm âm lượng", "tắt tiếng")**:
   - Relative Change: `change_volume(delta_percent: int)`:
     - Fast zero-dependency method: Injects `VK_VOLUME_UP (0xAF)` or `VK_VOLUME_DOWN (0xAE)` keystrokes (each keystroke is 2%, so +10% sends 5 key strokes).
     - Precise method: Uses `pycaw` (`IAudioEndpointVolume`) or Win32 COM `MMDeviceEnumerator` to get/set exact scalar level (0.0 to 1.0) and query mute state.
   - "tăng âm lượng" -> +10%
   - "giảm âm lượng" -> -10%
   - "tắt tiếng" / "bật tiếng" -> toggles `VK_VOLUME_MUTE (0xAD)`
2. **Display Brightness Modulation ("tăng độ sáng", "giảm độ sáng", "đặt độ sáng 70%")**:
   - Implementation:
     - Method 1: `screen_brightness_control` library if available.
     - Method 2: WMI / PowerShell CIM method: `(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, <val>)`.
     - Method 3: Win32 DXVA2 API `dxva2.dll!SetMonitorBrightness`.
   - Fallback: Graceful degradation returning `"Không thể điều chỉnh độ sáng trên màn hình hiện tại."` if monitor is external desktop without DDC/CI.

#### D. File Search & System Folder Launcher
1. **File Search ("tìm file X", "tìm tài liệu Y")**:
   - Search Roots: User Home (`~`), `Desktop`, `Downloads`, `Documents`, `Pictures`, `Videos`, `d:/Software GitCode`.
   - Search Algorithm: Bounded `os.scandir()` tree traversal with depth limit (max_depth=4) and exclusion list (`node_modules`, `.git`, `.venv`, `__pycache__`, `AppData`, `Temp`).
   - Returns top 5 matches with relative path, size (KB/MB), and last modified date.
   - If exact single match found, offer voice prompt to open immediately via `os.startfile(match_path)`.
2. **Special System Folders ("mở thư mục Downloads", "mở Desktop", "mở ổ D")**:
   - Maps Vietnamese tokens (`downloads`, `tải về`, `desktop`, `màn hình chính`, `documents`, `tài liệu`, `pictures`, `ảnh`, `music`, `nhạc`) to resolved absolute paths via `os.path.expanduser` / `os.environ["USERPROFILE"]`.
   - Launches via `os.startfile(folder_path)` or `subprocess.Popen(["explorer.exe", folder_path])`.
3. **Screen Capture ("chụp màn hình")**:
   - Captures screen via `PIL.ImageGrab.grab()` or Win32 GDI `BitBlt`.
   - Saves file to Desktop: `~/Desktop/JARVIS_Screenshot_YYYYMMDD_HHMMSS.png`.
   - Vocalizes: `"Đã chụp màn hình và lưu tại Desktop, thưa Ngài."`

---

### 1.4 Voice Confirmation Safety Gate for Destructive Actions

Destructive operations (e.g. file deletion, permanent removal, formatting, terminating critical system processes, reboot/shutdown) must be gated by a two-phase confirmation protocol.

```
                  User Speech: "JARVIS, xóa thư mục test"
                                    │
                                    ▼
                         LLMIntentRouter Parsing
                                    │
                     Is Action Destructive / Dangerous?
                                    │
                                    ├─── No ───► Dispatch Action Immediately
                                    │
                                   Yes
                                    │
                                    ▼
               Create Pending Confirmation Entry in Session:
               - action_id: UUID
               - action_name: "file_delete"
               - payload: {"target": "d:/test"}
               - expires_at: now + 30.0s
                                    │
                                    ▼
                  JARVIS Speaks & Displays Confirmation Prompt:
   "Thưa Ngài, thao tác xóa thư mục test có thể làm mất dữ liệu. Ngài có chắc chắn muốn thực hiện không?"
                                    │
                                    ▼
                         Listen for Voice Response
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
      Affirmative ("có",      Negative ("không",       Timeout (>30s)
      "đồng ý", "xác nhận",   "hủy", "thôi",           or No Input
      "yes", "confirm")       "cancel", "no")               │
            │                       │                       │
            ▼                       ▼                       ▼
      Execute Action          Cancel Action          Auto-Cancel Action
      & Speak Result          & Speak "Đã hủy"       & Speak "Đã hủy do hết giờ"
```

#### State Machine Specification:
- **Pending Store**: `_pending_confirmation: Optional[PendingConfirmation]` in `JarvisApp` with mutex lock.
- **Affirmative Tokens**: `có`, `đồng ý`, `xác nhận`, `chắc chắn`, `thực hiện`, `được`, `yes`, `confirm`, `proceed`.
- **Negative Tokens**: `không`, `hủy`, `dừng lại`, `thôi`, `bỏ qua`, `cancel`, `no`, `abort`.
- **Auto-Expiration**: 30.0 seconds timeout window. Any command spoken other than confirmation clears the pending gate.

---

## Part 2: Architecture Plan for R7 (Natural Language Shell)

### 2.1 Objective & System Boundary
The Natural Language Shell enables developers and power users to control software development and operating system toolchains using conversational Vietnamese or English, without having to recall exact syntax or flags.

### 2.2 Module Organization
```
jarvis/
├── automation/
│   └── shell_assistant.py     # NL Shell Parser, Safety Gate, Execution Manager & Output Summarizer
└── plugins/
    └── shell.py               # Low-level Subprocess Plugin with ADMIN privilege check
```

---

### 2.3 Command Classification & Translation Table

| Natural Language Query (VI/EN) | Intent / Target | Inferred Shell Command | Working Directory Context |
|---|---|---|---|
| "chạy server", "start dev server", "bật server" | Dev Server | `npm start` or `npm run dev` (if `package.json`), `python manage.py runserver` (if Django), `uvicorn app:app --reload` (if FastAPI), `python main.py` | Active Project Directory (`default_project_dir`) |
| "git status project JARVIS", "kiểm tra git" | VCS Status | `git status -s` or `git status` | `d:/Software GitCode/JARVIS` |
| "cài đặt package requests", "install package lodash" | Package Manager | `pip install <pkg>` (for Python project/packages) or `npm install <pkg>` (for Node packages) | Active Project Directory |
| "restart Docker", "khởi động lại docker" | Container Runtime | `docker restart $(docker ps -q)` or `Restart-Service docker` (Windows Service) | System CWD |
| "kiểm tra port 8080", "port 8080 đang chạy gì" | Network Diagnostic | `netstat -ano | findstr :<port>` or `powershell "Get-NetTCPConnection -LocalPort <port>"` | System CWD |
| "xem ip máy tính", "địa chỉ ip" | Network Interface | `ipconfig | findstr IPv4` | System CWD |
| "dọn dẹp thư mục tạm", "clear temp" | Maintenance | `Remove-Item -Path $env:TEMP\* -Recurse -Force` *(Gated)* | System TEMP |

---

### 2.4 Destructive Command Safety Filter (Adversarial Regex Gate)

All commands generated by the Natural Language parser or requested directly must pass through the `CommandSafetyInspector` before execution:

1. **High-Risk Regex Blacklist**:
   ```python
   DANGEROUS_PATTERNS = [
       r"\brm\s+-[rf]{1,2}\b",             # rm -rf / rm -r
       r"\brmdir\s+/[sq]\b",              # rmdir /s /q
       r"\bdel\s+/[sqf]\b",               # del /f /q /s
       r"\berase\b",                      # erase
       r"\bformat\s+[a-z]:\b",            # format C:
       r"\bdrop\s+(database|table)\b",    # SQL drop
       r"\bdelete\s+from\b",              # SQL delete without where
       r"\btruncate\s+table\b",           # SQL truncate
       r"\btaskkill\s+/[fF]\s+/im\s+(explorer|csrss|lsass|svchost)\.exe", # Killing system processes
       r"\bgit\s+reset\s+--hard\b",       # git destructive reset
       r"\bgit\s+clean\s+-[fF][dD]?[xX]?",# git destructive clean
       r"\bdd\s+if=",                     # disk dump
       r"\bmkfs\b",                       # format filesystem
       r"\bdiskpart\b",                   # disk partitioning
       r"\bRemove-Item\b.*-Recurse",       # PowerShell recursive deletion
   ]
   ```
2. **Safety Enforcement**:
   - If any dangerous pattern matches:
     - Mark command as `requires_confirmation = True`, `danger_level = "CRITICAL"`.
     - Suspend execution and route to Voice Confirmation Safety Gate.
     - Prompt: `"Lệnh này chứa thao tác có thể gây mất dữ liệu: '{command}'. Ngài có chắc chắn muốn thực thi không?"`
     - Only upon affirmative voice confirmation will `subprocess.Popen` / `subprocess.run` be invoked.

---

### 2.5 Output Summarization Engine for Vietnamese TTS

Raw CLI outputs often exceed dozens or hundreds of lines (e.g. `npm install`, `git status`, `netstat`). Vocalizing raw stdout over TTS causes cognitive overload. R7 includes specialized parsers and a generic fallback summarizer:

```
                          Subprocess Execution Completed
                                        │
                                        ▼
                           Check stdout line count
                                        │
                   ┌────────────────────┴────────────────────┐
                   │                                         │
             <= 10 lines                                > 10 lines
                   │                                         │
                   ▼                                         ▼
         Format Clean Output                      Trigger Output Summarizer
                                                             │
                                        ┌────────────────────┴────────────────────┐
                                        │                                         │
                            Specialized Tool Matcher                      Generic Fallback
                                        │                                         │
                         ├── git status: "Nhánh main: 3 files..."        ├── Online: LLM One-Shot Summary
                         ├── netstat: "Port 8080 đang dùng..."           └── Offline: First 3 + Last 2 lines + Total
                         ├── pip/npm: "Đã cài đặt thành công..."
                         └── docker: "4 containers đang chạy..."
```

#### Specialized Summary Rules:
1. **`git status`**:
   - Parses active branch, commits ahead/behind, count of modified files, count of untracked files, count of staged files.
   - Example Output: `"Nhánh main: Đang có 3 tệp đã sửa đổi và 1 tệp chưa theo dõi, thưa Ngài."`
2. **`netstat` / Port Diagnostic**:
   - Parses whether port is bound (`LISTENING`, `ESTABLISHED`), process ID, and looks up process name via `win32_platform`.
   - Example Output: `"Port 8080 đang mở, được sử dụng bởi tiến trình python.exe với PID 15420, thưa Ngài."`
3. **`pip install` / `npm install`**:
   - Parses package name, added packages count, or error messages.
   - Example Output: `"Đã cài đặt thành công gói requests, thưa Ngài."`
4. **`docker ps` / `docker restart`**:
   - Parses active container names, images, status.
   - Example Output: `"Docker daemon đã khởi động lại, hiện có 3 container đang chạy ổn định."`
5. **Generic Fallback (> 10 lines)**:
   - Formats: `"Lệnh đã thực thi thành công với {N} dòng kết quả. Tóm tắt: {Line 1}, {Line 2}... Thưa Ngài."`

---

## Part 3: Architecture Plan for R8 (Always-On Intelligent Overlay)

### 3.1 UI Framework Choice & Technical Rationale

| Evaluation Metric | Tkinter (Custom Canvas HUD) | CustomTkinter | PyQt6 / PySide6 |
|---|---|---|---|
| **Zero Heavy Dependencies** | **Excellent** (Built-in Python stdlib) | **Good** (Requires `customtkinter` pip) | **Poor** (Requires 80MB+ Qt binaries & DLLs) |
| **Startup Latency** | **< 40ms** (Instant launch) | ~150ms | ~400ms - 800ms |
| **Headless / CI Testing** | **Native** (Seamless mock root / offscreen) | Requires display emulation | Complex `QTest` & `xvfb` setup |
| **Transparency & Always-on-Top** | Supported via `-alpha`, `-topmost`, `overrideredirect` | Supported | Supported |
| **Waveform Animation Performance** | **60 FPS** via lightweight Canvas lines | Moderate | High |
| **Recommendation** | **SELECTED** (Zero bloat, guaranteed CI stability) | Alternate | Not recommended for core overlay |

**Decision**: Build the upgraded Always-On Intelligent Overlay using an enhanced modular **Tkinter Canvas HUD** architecture.

---

### 3.2 UI Component Hierarchy & Visual Layout

```
+-------------------------------------------------------------------------+
| [O] J.A.R.V.I.S HUD SIDEBAR                         [―] [◀/▶] [✕]      |
+-------------------------------------------------------------------------+
| [● ONLINE] CPU: 14% | RAM: 42% (6.7/16 GB) | BAT: ⚡ 85% (5s Refresh)   |
+-------------------------------------------------------------------------+
| SPECTRUM ANALYZER / WAVEFORM (Dynamic 11-bar Canvas)                    |
|   |||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||         |
|   [ ▂▃▅▆▇█▇▆▅▃▂ ] Listening / Speaking State Animation                  |
+-------------------------------------------------------------------------+
| PERSISTENT MEMORY PREVIEW (Top 3 Facts)                                 |
| ◈ Chủ nhân: Hưng | ◈ Dự án: JARVIS AI | ◈ Nhạc: Lofi Work              |
+-------------------------------------------------------------------------+
| CONVERSATION HISTORY (Last 5 Turns - Scrollable Card Stack)             |
| ┌─────────────────────────────────────────────────────────────────────┐ |
| │ [Turn 1] User: "thời tiết hôm nay"                                  │ |
| │          JARVIS: "Hà Nội hôm nay 28°C, trời nhiều mây, thưa Ngài."  │ |
| │ [Turn 2] User: "kiểm tra port 8080"                                 │ |
| │          JARVIS: "Port 8080 đang chạy bởi python.exe (PID 14220)."  │ |
| │ [Turn 3] User: "tăng âm lượng"                                      │ |
| │          JARVIS: "Đã tăng âm lượng lên 70%."                        │ |
| │ [Turn 4] User: "git status"                                         │ |
| │          JARVIS: "Nhánh main: 2 files modified."                    │ |
| │ [Turn 5] User: "bật đèn bàn"                                        │ |
| │          JARVIS: "Đang bật đèn bàn làm việc cho Ngài."              │ |
| └─────────────────────────────────────────────────────────────────────┘ |
+-------------------------------------------------------------------------+
| QUICK ACTION BUTTONS                                                    |
| [ 🌅 Briefing ] [ 📊 System Status ] [ 🎯 Focus Mode ] [ 🧹 Clean RAM ]  |
+-------------------------------------------------------------------------+
| TOOLTIP / HOTKEY HINT: "💡 Double clap hoặc 'Hey JARVIS' để kích hoạt"  |
+-------------------------------------------------------------------------+
```

---

### 3.3 Key Features & Implementation Mechanics

#### A. Sidebar Mode (Right-Screen Docking, Collapsible to 40px, Draggable)
- **Docking Coordinates**:
  - Full width: `W = 380px`, `H = screen_height - taskbar_offset (approx 40px)`.
  - Position: `X = screen_width - W`, `Y = 0`.
- **Collapsed Ribbon (40px)**:
  - Width collapses to `40px`.
  - Displays vertical cyber strip with pulsing mini Arc Reactor core, CPU load indicator, and an expand icon `◀`.
  - Hover or click expands smoothly back to `380px`.
- **Draggable & Auto-Snap**:
  - Dragging the top header allows undocking into a floating window.
  - If dragged within 60px of the right screen edge, it snaps back into docked sidebar mode.

#### B. 5-Turn Conversation History Display
- Backing store: `collections.deque(maxlen=5)` storing `TurnRecord(user_text, jarvis_text, action_name, timestamp)`.
- Renders conversational bubble cards with distinct styling:
  - User message: Warm Amber Gold `#ffa500`, aligned right.
  - JARVIS message: Luminescent Cyan `#00f0ff`, aligned left with `◈` indicator.
  - Action Badge: Subtle dark cyan pill (e.g. `[Shell]`, `[Spotify]`, `[Hardware]`).
- Auto-scrolls to newest message on update.

#### C. Quick Action Panel
Configured cyber buttons with direct event dispatchers:
1. `🌅 Morning Briefing`: Dispatches `briefing_morning` action (R5 Web Intelligence).
2. `📊 System Status`: Dispatches `system_status` action (Hardware telemetry).
3. `🎯 Focus Mode`: Dispatches `focus_mode_start` (25-min Pomodoro timer + DND).
4. `🧹 RAM Optimizer`: Dispatches `healing_watchdog_heal` (Memory optimization).
5. `📁 Downloads`: Opens `~/Downloads` via `folder_open`.

#### D. Memory Preview Widget (Top 3 Facts)
- Subscribes to R2 Memory System (`logs/memory.db`).
- Queries top 3 highest-priority or most frequently accessed user facts (e.g. User Name, Current Active Project, Music Preference).
- Displays in compact horizontal badges: `◈ Tên: Hưng | ◈ Dự án: JARVIS | ◈ Nhạc: Lofi`.

#### E. Realtime 5-Second Status Bar (CPU, RAM, Battery)
- Background worker schedules updates every 5.0 seconds via Tk `after(5000)`.
- CPU & RAM: Retrieved from `HardwareMonitor` or Win32 `GlobalMemoryStatusEx`.
- Battery Prober via Win32 ctypes `kernel32.GetSystemPowerStatus`:
  ```python
  class SYSTEM_POWER_STATUS(ctypes.Structure):
      _fields_ = [
          ("ACLineStatus", wintypes.BYTE),         # 1: Online (AC), 0: Offline (Battery)
          ("BatteryFlag", wintypes.BYTE),          # 1: High, 2: Low, 4: Critical, 8: Charging
          ("BatteryLifePercent", wintypes.BYTE),   # 0-100% or 255 (Unknown)
          ("Reserved1", wintypes.BYTE),
          ("BatteryLifeTime", wintypes.DWORD),
          ("BatteryFullLifeTime", wintypes.DWORD),
      ]
  ```
- Dynamic Color Logic:
  - Normal (< 70% CPU/RAM, > 30% Batt): `#00ff88` (Emerald Green)
  - Warning (70-85% CPU/RAM, 15-30% Batt): `#ffaa00` (Amber Gold)
  - Alert (> 85% CPU/RAM, < 15% Batt): `#ff3366` (Crimson Red)

#### F. Dynamic Voice Waveform Spectrum Visualization
- Rendered on a dedicated Tkinter `Canvas` (340x48 px).
- 11 vertical spectrum bars with gradient fill (`#00f0ff` -> `#00ff88`).
- **State Behaviors**:
  - `IDLE`: Flat baseline glow with gentle 1-bar heartbeat animation.
  - `LISTENING`: Dynamic oscillating bar heights synchronized with incoming audio RMS power or 120ms randomized acoustic spectrum simulation.
  - `THINKING`: Wave propagation animation (sinusoidal sweep left-to-right).
  - `SPEAKING`: Pulsing high-amplitude vocal spectrum matching TTS output.

#### G. Minimize to Floating Corner Arc Reactor Badge
- Minimize button `―` shrinks the entire overlay to a 48x48 floating translucent circular badge at bottom-right corner.
- Badge features a glowing Arc Reactor SVG/Canvas ring.
- Clicking the badge restores full sidebar or popup mode.

---

## Part 4: Health-Check & Integration Points

### 4.1 CLI Health-Check Diagnostics Matrix (`jarvis/cli.py`)

The CLI `python -m jarvis health-check` must be expanded to diagnose all new systems without failing when optional hardware or keys are absent.

```
============================================================
 JARVIS System Health Diagnostics (v1.0.0)
============================================================
[*] Operating System: win32 (Windows 11 Build 22631)
[*] Python Version: 3.13.2 (C:\Python313\python.exe)
[+] Audio Subsystem: sounddevice OK (2 input devices found)
    - Default Input: [1] Microphone Array (Realtek Audio)
[+] TTS Engine: ElevenLabs API Key configured (SAPI5 fallback ready)
[+] STT Engine: Whisper API configured (Web Speech fallback ready)
[+] LLM Provider: Gemini / OpenAI (API Key loaded)
[+] Windows Win32 API: Available (2 monitors detected, Per-Monitor DPI v2 OK)
[+] Computer Control (R4): SendInput, PyAutoGUI, Windows ctypes OK
[+] NL Shell (R7): Python, Git, Docker detected; Safety Gate Active
[+] UI Subsystem (R8): Tkinter GUI available; Always-On Overlay ready
[+] Persistent Memory (R2): logs/memory.db SQLite accessible
[+] Hardware Telemetry: CPU, RAM, Battery probers nominal
[+] Configuration: 12 root sections loaded
============================================================
 Diagnostics completed successfully. (All green)
```

### 4.2 Application Integration Points (`jarvis/core/app.py`)

`JarvisApp` coordinates the lifecycle of all subsystems:

```python
# In JarvisApp.initialize():
self.computer_controller = ComputerController(win32=platform_win32)
self.shell_assistant = ShellAssistant(dispatcher=self.dispatcher, config=self.config)
self.overlay = AlwaysOnOverlay(config=self.config.get("ui.overlay", {}))

# Register R4 actions:
self.dispatcher.register_action("window_minimize_all", self.computer_controller.minimize_all)
self.dispatcher.register_action("window_close_tab", self.computer_controller.close_tab)
self.dispatcher.register_action("window_close_active", self.computer_controller.close_active_window)
self.dispatcher.register_action("window_focus_app", self.computer_controller.focus_app)
self.dispatcher.register_action("media_volume_change", self.computer_controller.change_volume)
self.dispatcher.register_action("display_brightness_change", self.computer_controller.change_brightness)
self.dispatcher.register_action("file_search", self.computer_controller.search_files)
self.dispatcher.register_action("folder_open", self.computer_controller.open_folder)
self.dispatcher.register_action("take_screenshot", self.computer_controller.take_screenshot)

# Register R7 actions:
self.dispatcher.register_action("shell_nl_exec", self.shell_assistant.execute_nl_command)
self.dispatcher.register_action("git_status_query", self.shell_assistant.git_status)
self.dispatcher.register_action("port_check", self.shell_assistant.check_port)
```

---

## Part 5: Comprehensive Verification & Test Strategy

### 5.1 New Unit & Integration Tests (Target: ≥ 20 Tests)

| Test Module | Test Case Description | Target System |
|---|---|---|
| `test_computer_control.py` | `test_minimize_all_sends_win_d` | R4 Window Management |
| `test_computer_control.py` | `test_close_tab_and_close_window` | R4 Window Management |
| `test_computer_control.py` | `test_focus_app_by_name` | R4 Window Management |
| `test_computer_control.py` | `test_volume_up_down_mute` | R4 Volume Control |
| `test_computer_control.py` | `test_display_brightness_control` | R4 Brightness Control |
| `test_computer_control.py` | `test_file_search_and_folder_open` | R4 File Search |
| `test_computer_control.py` | `test_take_screenshot_saves_desktop` | R4 Screen Capture |
| `test_safety_gate.py` | `test_destructive_file_delete_requires_confirmation` | R4 Safety Gate |
| `test_safety_gate.py` | `test_destructive_action_confirmed_executes` | R4 Safety Gate |
| `test_safety_gate.py` | `test_destructive_action_rejected_cancels` | R4 Safety Gate |
| `test_safety_gate.py` | `test_destructive_action_timeout_expires` | R4 Safety Gate |
| `test_shell_assistant.py` | `test_parse_dev_server_command` | R7 NL Shell |
| `test_shell_assistant.py` | `test_git_status_vietnamese_summary` | R7 NL Shell |
| `test_shell_assistant.py` | `test_port_check_netstat_parsing` | R7 NL Shell |
| `test_shell_assistant.py` | `test_dangerous_shell_command_intercepted` | R7 Safety Gate |
| `test_shell_assistant.py` | `test_output_summarizer_exceeding_10_lines` | R7 Output Summarizer |
| `test_always_on_overlay.py`| `test_sidebar_docking_and_collapse_40px` | R8 Overlay UI |
| `test_always_on_overlay.py`| `test_conversation_history_max_5_turns` | R8 Overlay UI |
| `test_always_on_overlay.py`| `test_quick_action_buttons_dispatch` | R8 Overlay UI |
| `test_always_on_overlay.py`| `test_status_bar_cpu_ram_battery_probe` | R8 Status Bar |
| `test_always_on_overlay.py`| `test_waveform_canvas_state_transitions` | R8 Waveform |
| `test_always_on_overlay.py`| `test_minimize_to_corner_badge` | R8 Overlay UI |
| `test_cli_health_check.py` | `test_health_check_reports_all_new_systems` | Health-Check CLI |

### 5.2 Regression Prevention Strategy
1. **Mocking Win32 APIs**: Use existing `tests/mocks/win32_mocks.py` to ensure all tests run cleanly on any OS and headless CI without requiring active hardware displays or physical audio inputs.
2. **Mocking Subprocess**: Unit tests for R7 shell execution mock `subprocess.run` / `subprocess.Popen` to verify command construction and safety gating without executing destructive OS commands.
3. **Headless Tkinter**: All overlay tests use `headless=True` or mock Tkinter root to avoid blocking GUI loops.
4. **Zero Double-Dispatch**: Keep gesture detector and dispatcher decoupled as established in M1-M4.

---

## Conclusion & Implementation Readiness

The architectural blueprints for R4 (Computer Control), R7 (Natural Language Shell), and R8 (Always-On Intelligent Overlay) provide an exhaustive, zero-ambiguity design. All interfaces, data structures, regex safety filters, confirmation state machines, UI hierarchies, and test matrices are fully mapped and ready for parallel execution by implementation workers.
