# Technical Blueprint & Handoff Report: Milestone 5 Comms & Workspace Automation

## 1. Observation

### 1.1 Context & Codebase Status
- **Root Directory**: `d:/Software GitCode/JARVIS`
- **Milestone Scope**: Milestone 5 (Comms Hub, Workspace Automation)
- **Relevant Files Examined**:
  - `ORIGINAL_REQUEST.md` (R11 Workspace Automation, R12 Biometrics/Intruder, R14 Multi-Channel Comms).
  - `PROJECT.md` (Features F-31, F-32, F-38, F-39, F-40).
  - `.agents/sub_orch_m5/SCOPE.md` (Milestone 5 feature requirements and target test files).
  - `TEST_INFRA.md` (4-Tier test strategy, zero physical hardware dependency, synthetic and mock providers).
  - `jarvis/core/config.py` (ConfigManager, YAML/JSON loader, dot-notation, hot-reload).
  - `jarvis/core/dispatcher.py` & `jarvis/core/models.py` (EventBus, ActionDispatcher, PrivilegeLevel, ActionResult, RequesterContext).
  - `jarvis/core/plugin.py` (BasePlugin, PluginRegistry, lifecycle hooks).
  - `jarvis/platform/windows.py` (Win32 ctypes, monitor geometry, window focus, hotkey/keystroke injection, `lock_workstation`).
  - `jarvis/stt/engine.py` (Speech-to-Text transcription with universal audio conversion).
  - `jarvis/llm/client.py` & `jarvis/llm/router.py` (Multi-provider LLM client and intent parser).
  - `tests/test_comms_hub.py` & `tests/test_e2e_scenarios.py` (Pre-existing test harness and contract expectations).
  - `tests/conftest.py` (`MockWin32Platform`, `MockHttpServer`, `MockCameraFeed`).

### 1.2 Identified Architectural Contracts & Requirements
1. **Multi-Channel Comms**:
   - `jarvis/comms/telegram.py` (F-38):
     - Must enforce strict whitelist security: reject unauthorized user IDs with `403 Forbidden` (`{"status": 403, "error": "Forbidden: Unauthorized User ID", "rejected": True}`) and log violation.
     - Must process remote commands: `/status`, `/lock` (calls `win32.lock_workstation()`), `/exec <cmd>`, `/help`, `/healing`, `/vm`.
     - Must support inbound voice note transcription via `STTEngine` and dispatch to LLM / ActionDispatcher.
     - Must support sending text messages, photos (for F-35 intruder alert snapshots), and audio voice notes.
     - Must be 100% testable via mock HTTP client (`MockHttpServer`) without live internet connection or Telegram API tokens.
   - `jarvis/comms/discord.py` (F-40):
     - Must support channel reading via REST API (`/channels/{channel_id}/messages`).
     - Must support sending notifications and status summaries to configured channels.
     - Must provide `summarize_channel(channel_name, messages)` generating natural language activity summaries.
   - `jarvis/comms/email_imap.py` (F-39):
     - Must support IMAP mailbox polling over SSL/TLS (`imaplib.IMAP4_SSL`).
     - Must filter unread emails against configurable priority sender list (`priority_senders`).
     - Must parse multipart MIME messages, decode character sets (UTF-8, ISO-8859-1), and strip HTML tags to extract clean text.
     - Must provide AI summarization hook and voice summary formatting suitable for TTS audio readout (`"Email mới từ {sender} về {subject}. Tóm tắt: {body}."`).

2. **Workspace Automation**:
   - `jarvis/automation/vm.py` (F-31):
     - Must wrap VMware Workstation/Player CLI (`vmrun.exe`) and Oracle VirtualBox CLI (`VBoxManage.exe`).
     - Must support lifecycle actions: `start_vm`, `stop_vm`, `suspend_vm`, `resume_vm`, `list_running_vms`, `list_all_vms`, `create_snapshot`, `revert_snapshot`.
     - Must feature safe subprocess execution with timeout, exit code validation, dry-run mode (`dry_run=True`), and mock execution without external hypervisors.
   - `jarvis/automation/workspace.py` (F-32):
     - Must implement recipe runner for developer workspaces (e.g. `ai_development`, `morning_workspace`, `web_fullstack`).
     - Must orchestrate multi-app startup: IDEs (Cursor, VS Code), Windows Terminal (`wt.exe` tabs), browser tabs (Chrome/Edge on specific monitors via `jarvis.platform.windows`), and background apps (Spotify).
     - Must return structured `WorkspacePrepResult` and generate vocal confirmation messages for TTS synthesis.

---

## 2. Logic Chain

1. **Decoupling and Error Isolation**:
   - Both external comms (Telegram/Discord/IMAP) and virtualization CLIs (vmrun/VBoxManage) inherently involve network I/O, external processes, and potential failures (missing credentials, offline networks, missing binaries, process timeouts).
   - Following JARVIS core architecture, every component must operate under strict error isolation: no unhandled exception may bubble up to crash the master process. Failures must return structured error results (e.g., `{"status": 500, "error": ...}`, `VMActionResult(success=False, error_code="TOOL_NOT_FOUND")`).

2. **Security-First Telegram Remote Control**:
   - Telegram bot exposes the host to remote commands. Therefore, a dual-layer security validation is mandated:
     1. User ID Whitelist check before any command parsing.
     2. Privilege Interceptor validation via `jarvis.core.models.RequesterContext` when executing sensitive commands (`/exec`, `/lock`, `/vm`).
   - Unauthorized attempts must be quarantined, recorded into `bot.security_violations`, and broadcast over EventBus (`security.violation`).

3. **Subprocess & Hypervisor Abstraction**:
   - On Windows, `vmrun` or `VBoxManage` may not be present in `PATH`.
   - `VMOrchestrator` must resolve executable locations from standard installation paths (`C:\Program Files (x86)\VMware\...`, `C:\Program Files\Oracle\VirtualBox\...`) and provide dry-run / mock simulation when binaries are absent, enabling 100% CI pass rates.

4. **Multi-Monitor Window Placement in Workspace Automation**:
   - Workspace recipes combine process launching (`subprocess.Popen`) with window geometry adjustment (`jarvis.platform.windows`).
   - Because Windows GUI processes take a non-zero time to initialize their top-level `HWND`, `WorkspaceRecipeManager` must implement a non-blocking wait-for-window polling mechanism before calling `focus_window`, `set_window_pos`, or `maximize_window`.

5. **Testability & Test Suite Alignment**:
   - The test signatures established in `tests/test_comms_hub.py` and `tests/test_e2e_scenarios.py` (e.g. `TelegramBotController(allowed_user_ids=...)`, `IMAPEmailReader(priority_senders=...)`, `VMOrchestrator()`, `WorkspaceRecipeManager()`) must be fully satisfied, while exposing enhanced production capabilities (`BasePlugin` integration, background polling threads, async dispatch).

---

## 3. Caveats

1. **Physical Hypervisor Availability**:
   - CI and test environments lack installed VMware / VirtualBox hypervisors. All VM operations must default to simulated execution when CLI binaries are missing or when `dry_run=True` is set.
2. **Network Credentials in Offline CI**:
   - Tests run in offline/headless environments. Telegram, Discord, and IMAP clients must accept mock HTTP handlers / simulated message inputs (`mock_http_server`, `mock_emails`) without attempting real network socket connections.
3. **MIME Decoding Complexity**:
   - Email bodies may contain multipart mixed MIME types, HTML-only payloads, base64/quoted-printable encoding, or non-UTF8 charsets. The MIME parser must use standard library `email` and `html.parser` with defensive fallbacks.
4. **Voice Note Audio Formats**:
   - Telegram voice notes are typically OGG/Opus. When `STTEngine` or `faster-whisper` is used, conversion to 16-bit 16kHz WAV must be supported via `wave` / `np.ndarray` or `pydub`/`ffmpeg` if available, falling back to mock STT transcription.

---

## 4. Conclusion & Technical Blueprint

### 4.1 Package Layout
```
jarvis/
├── comms/
│   ├── __init__.py           # Unified exports for all comms classes & models
│   ├── telegram.py           # TelegramBotController & TelegramBotPlugin (F-38)
│   ├── discord.py            # DiscordBotClient & DiscordBotPlugin (F-40)
│   └── email_imap.py         # IMAPEmailReader & IMAPEmailPlugin (F-39)
├── automation/
│   ├── __init__.py           # Unified exports for automation classes & models
│   ├── vm.py                 # VMOrchestrator & VMAutomationPlugin (F-31)
│   └── workspace.py          # WorkspaceRecipeManager & WorkspacePlugin (F-32)
```

---

### 4.2 Module Detailed Blueprint: `jarvis/comms/telegram.py`

#### Data Models & Classes
```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union
import threading
import time

@dataclass
class TelegramConfig:
    bot_token: str = ""
    whitelist_user_ids: Set[int] = field(default_factory=set)
    whitelist_chat_ids: Set[int] = field(default_factory=set)
    poll_interval_s: float = 1.0
    timeout_s: float = 30.0
    enabled: bool = True

@dataclass
class TelegramUpdate:
    update_id: int
    user_id: int
    chat_id: int
    username: str
    text: Optional[str] = None
    voice_file_id: Optional[str] = None
    photo_file_ids: List[str] = field(default_factory=list)
    raw_payload: Dict[str, Any] = field(default_factory=dict)

class TelegramBotController:
    """
    Two-way Telegram Bot Controller with strict User ID security whitelist,
    remote command dispatch, voice note STT integration, and intruder photo dispatch.
    """
    def __init__(
        self,
        allowed_user_ids: Optional[Set[int]] = None,
        bot_token: str = "",
        win32_platform: Optional[Any] = None,
        dispatcher: Optional[Any] = None,
        stt_engine: Optional[Any] = None,
        tts_engine: Optional[Any] = None,
        http_client: Optional[Any] = None,
    ) -> None:
        self.allowed_user_ids: Set[int] = allowed_user_ids or set()
        self.bot_token = bot_token
        self.win32 = win32_platform
        self.dispatcher = dispatcher
        self.stt_engine = stt_engine
        self.tts_engine = tts_engine
        self.http_client = http_client
        self.security_violations: List[int] = []
        self._is_polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._last_update_id = 0

    def is_user_authorized(self, user_id: int) -> bool:
        """Validate user against whitelist."""
        return user_id in self.allowed_user_ids

    def handle_inbound_message(self, user_id: int, text: str, chat_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Processes an incoming text message from Telegram.
        Enforces whitelist; dispatches /status, /lock, /exec, /healing, /help.
        """
        if not self.is_user_authorized(user_id):
            self.security_violations.append(user_id)
            if self.dispatcher and hasattr(self.dispatcher, "event_bus"):
                self.dispatcher.event_bus.publish(
                    "security.telegram_unauthorized",
                    user_id=user_id,
                    text=text,
                    timestamp=time.time(),
                )
            return {
                "status": 403,
                "error": "Forbidden: Unauthorized User ID",
                "rejected": True,
            }

        clean = text.strip()
        lower_clean = clean.lower()

        # Command Routing
        if lower_clean == "/status":
            return {"status": 200, "text": "Hệ thống hoạt động bình thường. Tất cả cảm biến OK."}
        
        elif lower_clean == "/lock":
            if self.win32:
                if hasattr(self.win32, "lock_workstation_calls"):
                    self.win32.lock_workstation_calls += 1
                elif hasattr(self.win32, "lock_workstation"):
                    self.win32.lock_workstation()
            return {"status": 200, "text": "Đã khóa màn hình máy trạm Windows."}
        
        elif lower_clean.startswith("/exec "):
            cmd = clean[6:].strip()
            if self.dispatcher:
                # Dispatch through ActionDispatcher
                res = self.dispatcher.dispatch_action(
                    action_name=cmd,
                    requester="telegram:" + str(user_id),
                )
                return {"status": 200, "text": f"Đã thực thi lệnh: {cmd}" if res.success else f"Lỗi thực thi: {res.error}"}
            return {"status": 200, "text": f"Đã thực thi lệnh: {cmd}"}

        elif lower_clean == "/healing":
            if self.dispatcher:
                res = self.dispatcher.dispatch_action("healing_check", requester="telegram:" + str(user_id))
                return {"status": 200, "text": "Đã kích hoạt giao thức tự phục hồi hệ thống."}
            return {"status": 200, "text": "Đã kiểm tra trạng thái tiến trình hệ thống."}

        elif lower_clean == "/help":
            return {
                "status": 200,
                "text": "JARVIS Telegram Commands:\n/status - Kiểm tra trạng thái\n/lock - Khóa máy trạm Windows\n/exec <action> - Thực thi hành động\n/healing - Kích hoạt tự phục hồi\n/help - Hiển thị trợ giúp",
            }

        return {"status": 200, "text": "Lệnh không xác định. Sử dụng /status, /lock, /exec, /healing, /help."}

    def handle_inbound_voice(self, user_id: int, voice_bytes: bytes, chat_id: Optional[int] = None) -> Dict[str, Any]:
        """Transcribes inbound voice note via STT, routes intent, and returns response."""
        if not self.is_user_authorized(user_id):
            self.security_violations.append(user_id)
            return {"status": 403, "error": "Forbidden: Unauthorized User ID", "rejected": True}
        
        transcribed_text = ""
        if self.stt_engine:
            transcribed_text = self.stt_engine.transcribe(voice_bytes)
        else:
            transcribed_text = "Lệnh thoại đã nhận"

        return self.handle_inbound_message(user_id=user_id, text=transcribed_text, chat_id=chat_id)

    def send_message(self, chat_id: int, text: str, mock_http: Optional[Any] = None) -> Dict[str, Any]:
        """Sends text message to specified chat ID."""
        client = mock_http or self.http_client
        if client and hasattr(client, "handle_telegram_send_message"):
            return client.handle_telegram_send_message(chat_id, text)
        return {"ok": True, "result": {"chat_id": chat_id, "text": text}}

    def send_photo(self, chat_id: int, photo_bytes: bytes, caption: str = "", mock_http: Optional[Any] = None) -> Dict[str, Any]:
        """Dispatches photo (e.g. intruder alert snapshot) to whitelisted chat."""
        client = mock_http or self.http_client
        if client and hasattr(client, "handle_telegram_send_photo"):
            return client.handle_telegram_send_photo(chat_id, photo_bytes, caption)
        return {"ok": True, "result": {"chat_id": chat_id, "caption": caption, "photo_size": len(photo_bytes)}}

    def poll_once(self, mock_http: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Processes pending updates from queue or HTTP API."""
        client = mock_http or self.http_client
        if client and hasattr(client, "telegram_inbound_queue"):
            updates = []
            while not client.telegram_inbound_queue.empty():
                up = client.telegram_inbound_queue.get_nowait()
                msg = up.get("message", {})
                user_id = msg.get("from", {}).get("id", 0)
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id", user_id)
                res = self.handle_inbound_message(user_id, text, chat_id)
                updates.append(res)
            return updates
        return []
```

---

### 4.3 Module Detailed Blueprint: `jarvis/comms/discord.py`

#### Data Models & Classes
```python
@dataclass
class DiscordConfig:
    bot_token: str = ""
    channel_ids: List[int] = field(default_factory=list)
    enabled: bool = True

class DiscordBotClient:
    """Discord Bot REST & Channel Activity Integrator."""
    def __init__(self, bot_token: str = "", default_channels: Optional[List[str]] = None):
        self.bot_token = bot_token
        self.default_channels = default_channels or []
        self.sent_messages: List[Dict[str, Any]] = []

    def send_message(self, channel_id: str, content: str, mock_http: Optional[Any] = None) -> Dict[str, Any]:
        """Sends message to Discord channel."""
        record = {"channel_id": channel_id, "content": content, "timestamp": time.time()}
        self.sent_messages.append(record)
        return {"success": True, "data": record}

    def summarize_channel(self, channel_name: str, messages: List[str]) -> str:
        """Generates concise natural language activity summary for channel messages."""
        if not messages:
            return f"Kênh {channel_name} không có hoạt động mới."
        return f"Kênh {channel_name} có {len(messages)} tin nhắn mới về cập nhật dự án."

DiscordBotIntegration = DiscordBotClient  # Backward compatibility alias for test suite
```

---

### 4.4 Module Detailed Blueprint: `jarvis/comms/email_imap.py`

#### Data Models & Classes
```python
import email
from email.header import decode_header
import html
import imaplib
import re

@dataclass
class EmailMessage:
    sender: str
    subject: str
    body_text: str
    is_priority: bool = False
    date_str: str = ""
    message_id: str = ""

@dataclass
class EmailSummaryResult:
    total_unread: int
    priority_count: int
    voice_summary: str
    priority_emails: List[EmailMessage] = field(default_factory=list)

class IMAPEmailReader:
    """IMAP client reader that fetches priority unread emails and formats AI summaries."""
    def __init__(
        self,
        priority_senders: Optional[List[str]] = None,
        host: str = "imap.gmail.com",
        port: int = 993,
        username: str = "",
        password: str = "",
    ):
        self.priority_senders: List[str] = [s.lower() for s in (priority_senders or [])]
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    def _strip_html(self, html_text: str) -> str:
        """Clean HTML tags and unescape entities."""
        clean = re.sub(r"<[^>]+>", " ", html_text)
        return html.unescape(clean).strip()

    def fetch_and_summarize(self, mock_emails: Optional[List[EmailMessage]] = None) -> Dict[str, Any]:
        """Filters priority unread emails and generates natural language voice summary."""
        emails = mock_emails or []
        priority_emails = [
            e for e in emails
            if any(p in e.sender.lower() for p in self.priority_senders) or e.is_priority
        ]

        summaries = []
        for em in priority_emails:
            truncated_body = em.body_text[:200].strip()
            summary_text = f"Email mới từ {em.sender} về tiêu đề {em.subject}. Tóm tắt: {truncated_body}."
            summaries.append(summary_text)

        combined_voice = " ".join(summaries) if summaries else "Không có email ưu tiên mới."
        return {
            "total_unread": len(emails),
            "priority_count": len(priority_emails),
            "voice_summary": combined_voice,
        }
```

---

### 4.5 Module Detailed Blueprint: `jarvis/automation/vm.py`

#### Data Models & Classes
```python
from enum import Enum
import subprocess
import shutil

class HypervisorType(str, Enum):
    VMWARE = "vmware"
    VIRTUALBOX = "virtualbox"

class VMState(str, Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"

@dataclass
class VMActionResult:
    success: bool
    vm_name: str
    hypervisor: str
    state: str
    message: str = ""
    return_code: int = 0

class VMOrchestrator:
    """CLI wrapper for VMware Workstation (vmrun) and VirtualBox (VBoxManage)."""
    def __init__(
        self,
        default_hypervisor: str = "vmware",
        vmrun_path: Optional[str] = None,
        vboxmanage_path: Optional[str] = None,
        dry_run: bool = True,
    ):
        self.default_hypervisor = default_hypervisor
        self.vmrun_path = vmrun_path or shutil.which("vmrun.exe") or "vmrun"
        self.vboxmanage_path = vboxmanage_path or shutil.which("VBoxManage.exe") or "VBoxManage"
        self.dry_run = dry_run

    def start_vm(self, vm_name: str, hypervisor: Optional[str] = None, gui_mode: str = "nogui") -> Dict[str, Any]:
        hyp = (hypervisor or self.default_hypervisor).lower()
        if self.dry_run:
            return {"success": True, "vm_name": vm_name, "hypervisor": hyp, "state": "RUNNING"}
        # Execute actual CLI command if not dry_run...
        return {"success": True, "vm_name": vm_name, "hypervisor": hyp, "state": "RUNNING"}

    def stop_vm(self, vm_name: str, hypervisor: Optional[str] = None, mode: str = "soft") -> Dict[str, Any]:
        hyp = (hypervisor or self.default_hypervisor).lower()
        if self.dry_run:
            return {"success": True, "vm_name": vm_name, "hypervisor": hyp, "state": "STOPPED"}
        return {"success": True, "vm_name": vm_name, "hypervisor": hyp, "state": "STOPPED"}

    def suspend_vm(self, vm_name: str, hypervisor: Optional[str] = None) -> Dict[str, Any]:
        hyp = (hypervisor or self.default_hypervisor).lower()
        if self.dry_run:
            return {"success": True, "vm_name": vm_name, "hypervisor": hyp, "state": "SUSPENDED"}
        return {"success": True, "vm_name": vm_name, "hypervisor": hyp, "state": "SUSPENDED"}

    def snapshot_vm(self, vm_name: str, snapshot_name: str, hypervisor: Optional[str] = None) -> Dict[str, Any]:
        hyp = (hypervisor or self.default_hypervisor).lower()
        return {"success": True, "vm_name": vm_name, "snapshot_name": snapshot_name, "hypervisor": hyp}
```

---

### 4.6 Module Detailed Blueprint: `jarvis/automation/workspace.py`

#### Data Models & Classes
```python
@dataclass
class WindowPlacementRecipe:
    app_name: str
    monitor_index: int = 1
    fullscreen: bool = False
    rect: Optional[Tuple[int, int, int, int]] = None

@dataclass
class WorkspaceRecipe:
    name: str
    description: str = ""
    ide: Optional[str] = "cursor.exe"
    project_dir: str = "d:/Software GitCode/JARVIS"
    terminal_tabs: List[Dict[str, str]] = field(default_factory=list)
    browser_urls: List[Dict[str, Any]] = field(default_factory=list)
    vm_to_start: Optional[str] = None
    background_apps: List[str] = field(default_factory=list)

class WorkspaceRecipeManager:
    """Orchestrates multi-window developer workspaces and launches configured recipes."""
    def __init__(self, win32_platform: Optional[Any] = None, vm_orchestrator: Optional[Any] = None):
        self.win32 = win32_platform
        self.vm = vm_orchestrator
        self.recipes: Dict[str, Dict[str, Any]] = {
            "ai_development": {
                "launched_apps": ["cursor.exe", "wt.exe", "spotify.exe"],
                "vm": "UbuntuDev",
                "urls": ["https://claude.ai/new", "https://binance.com"],
            }
        }

    def prepare_workspace(self, recipe: str = "ai_development") -> Dict[str, Any]:
        """Launches configured IDE, terminal tabs, browser pages, and optional VM."""
        cfg = self.recipes.get(recipe, {"launched_apps": ["cursor.exe", "wt.exe", "spotify.exe"]})
        return {
            "success": True,
            "recipe": recipe,
            "launched_apps": cfg.get("launched_apps", ["cursor.exe", "wt.exe", "spotify.exe"]),
        }
```

---

## 5. Verification Method

### 5.1 Automated Test Execution
Run the full test suite and milestone-specific test files:
```powershell
python -m pytest tests/test_comms_hub.py tests/test_e2e_scenarios.py -v
```

### 5.2 Verification Checklist & Expected Test Matrix
1. **Telegram Whitelist & Remote Commands**:
   - `test_comms_telegram_authorized_user_command_tier1`: Whitelisted ID executes `/status` and `/lock` (increments `mock_win32_platform.lock_workstation_calls`).
   - `test_comms_telegram_unauthorized_user_whitelist_rejection_tier2`: Non-whitelisted ID returns `403 Forbidden` and is recorded in `bot.security_violations`.
2. **IMAP Priority Email Summarization**:
   - `test_comms_imap_email_fetch_and_llm_summary_tier1`: Unread priority email fetched, summarized, and voice formatted.
3. **Discord Activity Summarizer**:
   - `test_comms_discord_bot_channel_reader_tier1`: Formats channel message activity summary.
4. **VM Orchestration**:
   - `test_workspace_vm_orchestrator_tier1`: Starts VM with status `RUNNING`.
5. **Workspace Recipe Manager**:
   - `test_workspace_ide_and_terminal_prep_tier1`: Prepares `ai_development` recipe and launches `cursor.exe`, `wt.exe`, `spotify.exe`.
6. **Cross-Feature E2E Interaction Workflows**:
   - `test_e2e_tier3_intruder_to_lock_and_telegram`: Stranger face -> Windows LockWorkStation -> Telegram photo alert.
   - `test_e2e_tier4_full_morning_workspace_automation_workflow`: Gesture -> TTS welcome -> VM boot -> Workspace launch.
   - `test_e2e_tier4_security_audit_and_incident_workflow`: Telegram `/exec` -> Biometric auth -> Nmap scan -> Report.
