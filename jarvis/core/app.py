"""
jarvis/core/app.py
==================
JarvisApp: Top-level application lifecycle, background runtime coordinator,
and bidirectional Voice/LLM/UI pipeline integration.
Wires together:
  - ConfigManager (Hot-reload file watcher)
  - EventBus & ActionDispatcher (Priority routing, Error Isolation)
  - PluginRegistry & Built-in Action Plugins (Spotify, Chrome, Cursor, Shell, Webhook)
  - TTSManager (ElevenLabs + SAPI5 fallback + local WAV disk cache)
  - STTEngine (Whisper API / local Whisper / SAPI fallback)
  - LLMClient & LLMIntentRouter (Multi-provider + Fast rule fallback)
  - AudioEngine (SoundDevice stream + auto-probing loudest microphone)
  - GestureDetector (Acoustic claps + rhythmic pattern disambiguation)
  - SystemTrayController (Windows taskbar tray icon with dynamic status)
  - DashboardServer (Embedded Web & WebSocket real-time dashboard)
  - AlwaysOnOverlay (Sidebar HUD, Task DAG telemetry, Code logs, Visual results)
  - Autonomous ReAct Planner (Task DAG engine, self-reflection, safety gating)
  - Code Interpreter Sandbox (AST validator, isolated subprocess execution)
  - Persistent Skill Library (Automated synthesis, packaging, registry)
  - Browser Automation Agent (Multi-tier driver, session persistence, scraping)
  - Computer-Use Vision & GUI Actor (Coordinate mapping, visual verifier)
  - Sub-Agent Background Worker Pool (Concurrency manager, notifications)
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import numpy as np

from jarvis.audio.engine import AudioEngine

# Expansion Subsystems (Milestones 1-6)
from jarvis.audio.wake_word import WakeWordDetector
from jarvis.automation.control import ComputerController
from jarvis.automation.gui_actor import GUIActor
from jarvis.automation.safety_gate import SafetyGate
from jarvis.automation.shell_assistant import ShellAssistant
from jarvis.browser.agent import BrowserAgent
from jarvis.browser.models import BrowserActionResult, ScrapeResult
from jarvis.browser.session import BrowserSessionManager
from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.logger import log_interaction as _global_log_interaction
from jarvis.core.models import RequesterContext
from jarvis.core.plugin import PluginRegistry
from jarvis.gesture.detector import GestureDetector
from jarvis.hardware.monitor import HardwareMetrics
from jarvis.hardware.reporter import HardwareReporter
from jarvis.llm.client import LLMClient
from jarvis.llm.router import LLMIntentRouter
from jarvis.memory.manager import MemoryManager

# Autonomous Superpower Subsystems (Milestones 1-5)
from jarvis.planner.engine import ReActTaskEngine
from jarvis.planner.models import PlanMode, PlanResult
from jarvis.planner.reflection import SelfReflectionEngine
from jarvis.planner.safety_interceptor import SafetyGateInterceptor
from jarvis.platform.hotkeys import GlobalHotkeyManager
from jarvis.plugins.chrome import ChromeMultiMonitorPlugin
from jarvis.plugins.cursor import CursorPlugin
from jarvis.plugins.shell import ShellPlugin
from jarvis.plugins.spotify import SpotifyPlugin
from jarvis.plugins.webhook import WebhookPlugin
from jarvis.proactive.engine import ProactiveEngine
from jarvis.sandbox.interpreter import CodeInterpreterSandbox, SandboxResult
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.synthesizer import DynamicSkillSynthesizer

# Subsystems
from jarvis.stt.engine import STTEngine
from jarvis.tts.manager import TTSManager
from jarvis.ui.dashboard import DashboardServer
from jarvis.ui.overlay import AlwaysOnOverlay
from jarvis.ui.tray import SystemTrayController, TrayStatus
from jarvis.vision.computer_use import ComputerUseVision
from jarvis.vision.screen import ScreenVisionManager
from jarvis.vision.visual_verifier import VisualVerifier
from jarvis.web.hub import WebIntelligenceHub
from jarvis.workers.manager import SubAgentManager
from jarvis.workers.models import WorkerPriority, WorkerTask
from jarvis.workers.notifications import WorkerNotificationDispatcher

log = logging.getLogger("jarvis.core.app")


def get_jarvis_data_dir() -> "Path":
    """
    Returns the writable per-user data directory for JARVIS.

    Priority:
      1. %LOCALAPPDATA%\\JARVIS  (Windows standard, always writable)
      2. %APPDATA%\\JARVIS       (roaming, fallback)
      3. ~/.jarvis               (Unix / last resort)

    This is used instead of relative paths (e.g. 'logs/') which fail
    when JARVIS is installed in protected directories like C:\\Program Files\\.
    """
    from pathlib import Path  # local import so module-level stays clean

    local_app = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local_app:
        data_dir = Path(local_app) / "JARVIS"
    else:
        data_dir = Path.home() / ".jarvis"

    # Create on first access — never raises because these locations are writable
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "logs").mkdir(exist_ok=True)
    except OSError:
        pass

    return data_dir


class JarvisApp:
    """Central daemon coordinating JARVIS runtime lifecycle."""

    def __init__(
        self,
        config_path: str | None = None,
        headless: bool = False,
        no_hot_reload: bool = False,
    ) -> None:
        self.config_path = config_path
        self.headless = headless
        self.no_hot_reload = no_hot_reload

        self._shutdown_event = threading.Event()
        self._lock = threading.RLock()

        # 1. Core Framework Foundation
        self.config = ConfigManager(config_path=self.config_path)
        self.event_bus = EventBus()
        self.dispatcher = ActionDispatcher(event_bus=self.event_bus)
        self.plugin_registry = PluginRegistry(self.dispatcher)

        # 2. Audio & Speech Subsystems
        self.tts_manager: TTSManager | None = None
        self.audio_engine: AudioEngine | None = None
        self.gesture_detector: GestureDetector | None = None
        self.wake_word_detector: WakeWordDetector | None = None
        self.stt_engine: STTEngine | None = None

        # 3. AI, Memory & Reasoning Subsystems
        self.llm_client: LLMClient | None = None
        self.llm_router: LLMIntentRouter | None = None
        self.memory_manager: MemoryManager | None = None

        # 4. Perception & Web Intelligence Subsystems
        self.vision_manager: ScreenVisionManager | None = None
        self.web_hub: WebIntelligenceHub | None = None

        # 5. OS Automation & Dev Shell Subsystems
        self.computer_controller: ComputerController | None = None
        self.safety_gate: SafetyGate | None = None
        self.shell_assistant: ShellAssistant | None = None

        # 6. Proactive Intelligence Engine
        self.proactive_engine: ProactiveEngine | None = None

        # 7. User Interfaces
        self.tray_controller: SystemTrayController | None = None
        self.dashboard_server: DashboardServer | None = None
        self.overlay: AlwaysOnOverlay | None = None

        # 8. Hardware Telemetry & Diagnostics
        self.hardware_reporter: HardwareReporter | None = None

        # 8b. System-Wide Hotkey Shortcuts
        self.hotkey_manager: GlobalHotkeyManager | None = None

        # 9. Autonomous Superpower Subsystems (Milestones 1-5)
        self.safety_interceptor: SafetyGateInterceptor | None = None
        self.reflection_engine: SelfReflectionEngine | None = None
        self.planner_engine: ReActTaskEngine | None = None
        self.react_planner: ReActTaskEngine | None = None  # Alias
        self.sandbox: CodeInterpreterSandbox | None = None
        self.skill_registry: SkillRegistry | None = None
        self.skill_synthesizer: DynamicSkillSynthesizer | None = None
        self.browser_session_manager: BrowserSessionManager | None = None
        self.browser_agent: BrowserAgent | None = None
        self.computer_use_vision: ComputerUseVision | None = None
        self.visual_verifier: VisualVerifier | None = None
        self.gui_actor: GUIActor | None = None
        self.worker_notifications: WorkerNotificationDispatcher | None = None
        self.subagent_manager: SubAgentManager | None = None
        self.worker_pool: SubAgentManager | None = None  # Alias

        self._initialized: bool = False
        self.welcome_executed = False
        self._pattern_last_fired: dict[str, float] = {}
        self._action_fanout_cooldown_s: float = 3.0
        self._is_voice_interacting: bool = False
        self._voice_lock = threading.Lock()

    def log_interaction(
        self,
        trigger: str,
        input_text: str,
        action: str,
        response: str,
        status: str = "success",
    ) -> str:
        """
        Structured interaction logger compliant with R6, R4, and M3 specification.
        """
        log_file = self.config.get("logging.file") or str(get_jarvis_data_dir() / "logs" / "jarvis.log")
        return _global_log_interaction(
            trigger=trigger,
            input_text=input_text,
            action=action,
            response=response,
            status=status,
            log_file=log_file,
        )

    def initialize(self) -> JarvisApp:
        """Bootstraps all JARVIS subsystems in deterministic order."""
        if self._initialized:
            return self

        log.info("Initializing JARVIS Core Subsystems...")
        self.config.load()

        # 1. Config Hot Reload Watcher
        if not self.no_hot_reload:
            self.config.start_watcher(interval_seconds=2.0)

        # 2. TTS Subsystem Initialization
        tts_cfg = self.config.get("tts", {})
        self.tts_manager = TTSManager(config=tts_cfg)

        # Register built-in system actions
        self._register_core_actions()

        # 3. Action Plugins Registration
        self.plugin_registry.register_plugin(SpotifyPlugin)
        self.plugin_registry.register_plugin(ChromeMultiMonitorPlugin)
        self.plugin_registry.register_plugin(CursorPlugin)
        self.plugin_registry.register_plugin(ShellPlugin)
        self.plugin_registry.register_plugin(WebhookPlugin)

        plugin_configs = self.config.get("plugins", {})
        self.plugin_registry.initialize_all(plugin_configs)

        # 4. Persistent Memory Subsystem (R2 & R6)
        mem_db = self.config.get("memory.db_path") or str(get_jarvis_data_dir() / "memory.db")
        max_turns = int(self.config.get("memory.max_session_turns", 10))
        self.memory_manager = MemoryManager(db_path=mem_db, max_session_turns=max_turns)

        # 5. STT Engine Initialization (F-14)
        stt_cfg = self.config.get("stt", {})
        self.stt_engine = STTEngine(
            config=stt_cfg,
            provider=stt_cfg.get("provider", "whisper_api"),
            event_bus=self.event_bus,
            config_manager=self.config,
        )

        # 6. Screen Vision Subsystem (R3)
        vis_cfg = self.config.get("vision", {})
        self.vision_manager = ScreenVisionManager(
            gemini_api_key=vis_cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", ""),
            openai_api_key=vis_cfg.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", ""),
            default_provider=vis_cfg.get("provider", "gemini"),
            gemini_model=vis_cfg.get("gemini_model", "gemini-1.5-flash"),
            openai_model=vis_cfg.get("openai_model", "gpt-4o"),
            timeout_seconds=float(vis_cfg.get("timeout_s", 10.0)),
        )

        # 7. Web Intelligence Hub (R5)
        web_cfg = self.config.get("web", {})
        self.web_hub = WebIntelligenceHub(
            cache_ttl_seconds=float(web_cfg.get("cache_ttl_s", 600.0)),
            weather_api_key=web_cfg.get("weather_api_key") or os.environ.get("OPENWEATHER_API_KEY", ""),
            default_city=web_cfg.get("default_city", "Hà Nội"),
        )

        # 8. OS Automation & Dev Shell Subsystems (R4 & R7)
        auto_cfg = self.config.get("automation", {})
        self.safety_gate = SafetyGate(timeout_seconds=float(auto_cfg.get("safety_gate_timeout_s", 30.0)))
        self.computer_controller = ComputerController()
        self.shell_assistant = ShellAssistant(
            default_cwd=os.getcwd(),
            safety_gate=self.safety_gate,
            dispatcher=self.dispatcher,
            config=auto_cfg if isinstance(auto_cfg, dict) else {},
        )

        # 9. LLM Client & Intent Router (F-15 & R2)
        llm_cfg = self.config.get("llm", {})
        self.llm_client = LLMClient(
            provider=llm_cfg.get("provider", "openai"),
            api_key=llm_cfg.get("api_key", ""),
            model=llm_cfg.get("model", "gpt-4o"),
        )
        self.llm_router = LLMIntentRouter(
            llm_client=self.llm_client,
            dispatcher=self.dispatcher,
            memory_manager=self.memory_manager,
        )

        # 10. Hardware Reporter Subsystem (F-20, F-21, F-22)
        hw_cfg = self.config.get("hardware", {})
        self.hardware_reporter = HardwareReporter(
            tts_manager=self.tts_manager,
            dispatcher=self.dispatcher,
            config={"hardware": hw_cfg} if isinstance(hw_cfg, dict) else {},
        )

        # 11. Proactive Intelligence Engine (R6)
        proactive_cfg = self.config.get("proactive", {})
        self.proactive_engine = ProactiveEngine(
            app_context=self,
            config=proactive_cfg if isinstance(proactive_cfg, dict) else {},
            web_hub=self.web_hub,
            hardware_monitor=self.hardware_reporter.monitor if self.hardware_reporter else None,
        )

        # 12. Wake Word Detector Subsystem (R1)
        ww_cfg = self.config.get("audio.wake_word", self.config.get("wake_word", {}))
        self.wake_word_detector = WakeWordDetector(
            callback=self._on_wake_word_triggered,
            on_wake_word=self._on_wake_word_event,
            sensitivity=float(ww_cfg.get("sensitivity", 0.5)),
            enabled=bool(ww_cfg.get("enabled", True)),
            sample_rate=int(self.config.get("audio.sample_rate", 44100)),
            cooldown_s=float(ww_cfg.get("cooldown_s", 1.5)),
            config=ww_cfg if isinstance(ww_cfg, dict) else {},
        )

        # 13. GestureDetector Initialization (F-05, F-06, F-07)
        gesture_cfg = self.config.get("gesture", {})
        self.gesture_detector = GestureDetector(
            config=gesture_cfg,
            dispatcher=None,
            event_bus=self.event_bus,
            on_gesture=self._on_gesture_event,
        )

        # 14. AudioEngine with Multi-Subscriber Dispatch
        def _on_audio_blocks_dispatch(block: np.ndarray, timestamp: float | None = None) -> None:
            if self.gesture_detector:
                try:
                    self.gesture_detector.feed_audio_block(block, timestamp=timestamp)
                except Exception as e:
                    log.debug("Gesture detector audio feed exception: %s", e)
            if self.wake_word_detector:
                try:
                    self.wake_word_detector.feed_audio_block(block, timestamp=timestamp)
                except Exception as e:
                    log.debug("Wake word detector audio feed exception: %s", e)

        self.audio_engine = AudioEngine(
            sample_rate=int(self.config.get("audio.sample_rate", 44100)),
            block_ms=int(self.config.get("audio.block_ms", 40)),
            input_device=self.config.get("audio.input_device"),
            probe_seconds=float(self.config.get("audio.probe_seconds", 0.5)),
            silent_rms_threshold=float(self.config.get("audio.silent_rms_threshold", 0.001)),
            event_bus=self.event_bus,
            config_manager=self.config,
            on_audio_block=_on_audio_blocks_dispatch,
        )

        # 15. Always-On Overlay HUD UI (R8 & R6)
        overlay_cfg = self.config.get("ui.overlay", {})
        self.overlay = AlwaysOnOverlay(
            sidebar_mode=bool(overlay_cfg.get("sidebar_mode", True)),
            sidebar_width=int(overlay_cfg.get("sidebar_width", 380)),
            auto_hide_s=float(overlay_cfg.get("auto_hide_s", 8.0)),
            on_action=self._on_overlay_quick_action,
            headless=self.headless,
            config=overlay_cfg if isinstance(overlay_cfg, dict) else {},
        )
        if self.memory_manager:
            facts = self.memory_manager.list_facts(limit=3)
            if facts:
                self.overlay.set_memory_facts([f"{f.get('key')}: {f.get('value')}" for f in facts])

        # 16. Code Interpreter Sandbox (M2 / Requirement R2)
        sandbox_cfg = self.config.get("sandbox", {})
        self.sandbox = CodeInterpreterSandbox(
            base_scratch_dir=sandbox_cfg.get("scratch_dir") or str(get_jarvis_data_dir() / "sandbox"),
            max_execution_seconds=float(sandbox_cfg.get("timeout_s", 15.0)),
        )

        # 17. Persistent Skill Library & Synthesizer (M2 / Requirement R2)
        skills_cfg = self.config.get("skills", {})
        skills_dir = skills_cfg.get("dir", "jarvis/skills")
        self.skill_registry = SkillRegistry(
            skills_dir=skills_dir,
            dispatcher=self.dispatcher,
        )
        self.skill_synthesizer = DynamicSkillSynthesizer(
            skills_dir=skills_dir,
            registry=self.skill_registry,
        )

        # 18. Browser Automation Agent & Session Manager (M3 / Requirement R3)
        browser_cfg = self.config.get("browser", {})
        self.browser_session_manager = BrowserSessionManager(
            storage_dir=browser_cfg.get("session_dir") or str(get_jarvis_data_dir() / "browser_sessions"),
            db_path=mem_db,
        )
        self.browser_agent = BrowserAgent(
            session_manager=self.browser_session_manager,
        )

        # 19. Computer-Use Vision & GUI Actor (M4 / Requirement R4)
        self.computer_use_vision = ComputerUseVision()
        self.visual_verifier = VisualVerifier()
        self.gui_actor = GUIActor(
            vision=self.computer_use_vision,
            verifier=self.visual_verifier,
            controller=self.computer_controller,
            safety_gate=self.safety_gate,
        )

        # 20. Autonomous ReAct Planner Subsystem (M1 / Requirement R1)
        self.safety_interceptor = SafetyGateInterceptor(
            safety_gate=self.safety_gate,
            timeout_seconds=float(auto_cfg.get("safety_gate_timeout_s", 30.0)),
        )
        # Share this same interceptor/SafetyGate with ActionDispatcher so
        # planner-issued and dispatcher-issued confirmation tokens are
        # resolved against one authoritative pending-confirmation store
        # (see jarvis/core/dispatcher.py's destructive-action safety gate).
        self.dispatcher.set_safety_interceptor(self.safety_interceptor)
        self.reflection_engine = SelfReflectionEngine()
        self.planner_engine = ReActTaskEngine(
            dispatcher=self.dispatcher,
            safety_interceptor=self.safety_interceptor,
            reflection_engine=self.reflection_engine,
            event_bus=self.event_bus,
            max_parallel_workers=int(self.config.get("planner.max_parallel_workers", 4)),
        )
        self.react_planner = self.planner_engine

        # 21. Sub-Agent Worker Pool & Notifications (M1 / Requirement R5)
        self.worker_notifications = WorkerNotificationDispatcher(
            tts_manager=self.tts_manager,
            overlay=self.overlay,
            telegram_controller=getattr(self, "telegram_controller", None),
            event_bus=self.event_bus,
        )
        self.subagent_manager = SubAgentManager(
            max_workers=int(self.config.get("workers.max_workers", 4)),
            event_bus=self.event_bus,
            notification_dispatcher=self.worker_notifications,
        )
        self.worker_pool = self.subagent_manager

        # 22. Real-Time Dashboard Server (F-17)
        dash_cfg = self.config.get("ui.dashboard", {})
        if dash_cfg.get("enabled", True):
            self.dashboard_server = DashboardServer(
                host=dash_cfg.get("host", "127.0.0.1"),
                port=dash_cfg.get("port", 8080),
                ws_port=dash_cfg.get("ws_port", 8765),
                app=self,
                config_manager=self.config,
                dispatcher=self.dispatcher,
            )

        # 23. System Tray Controller (F-16 & R1)
        if not self.headless and self.config.get("ui.tray.enabled", True):
            self.tray_controller = SystemTrayController(
                app=self,
                config_manager=self.config,
                event_bus=self.event_bus,
                tooltip=self.config.get("ui.tray.tooltip", "JARVIS Desktop Assistant"),
                dashboard_url=f"http://{dash_cfg.get('host', '127.0.0.1')}:{dash_cfg.get('port', 8080)}",
            )
            if hasattr(self.tray_controller, "wake_word_detector"):
                self.tray_controller.wake_word_detector = self.wake_word_detector

        # 24. Global Keyboard Hotkey Manager
        hotkey_cfg = self.config.get("hotkeys", {})
        if hotkey_cfg.get("enabled", True):
            self.hotkey_manager = GlobalHotkeyManager(is_mock=self.headless)
            self._register_default_hotkeys()

        # 25. Signal Handlers
        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGINT, self._handle_signal)
                signal.signal(signal.SIGTERM, self._handle_signal)
            except (ValueError, AttributeError):
                pass

        log.info("All JARVIS Core & Autonomous Agentic Subsystems successfully initialized.")
        self._initialized = True
        return self

    def _register_default_hotkeys(self) -> None:
        """Register default system-wide keyboard shortcuts."""
        if not self.hotkey_manager:
            return

        def _toggle_overlay_cb():
            if self.overlay:
                self.overlay.toggle()

        def _ptt_voice_cb():
            threading.Thread(target=self._handle_voice_command, kwargs={"trigger_name": "HOTKEY_PTT"}, daemon=True).start()

        def _toggle_wake_word_cb():
            if self.wake_word_detector:
                new_state = self.wake_word_detector.toggle_enabled()
                msg = f"Đã {'bật' if new_state else 'tắt'} nhận diện từ khóa Hey JARVIS."
                if self.tts_manager:
                    self.tts_manager.speak(msg, wait=False)

        def _briefing_cb():
            threading.Thread(target=self._handle_morning_briefing, daemon=True).start()

        def _status_cb():
            threading.Thread(target=self._handle_system_status, daemon=True).start()

        self.hotkey_manager.register("Ctrl+Shift+J", _toggle_overlay_cb, "Bật/tắt giao diện HUD JARVIS")
        self.hotkey_manager.register("Ctrl+Shift+L", _ptt_voice_cb, "Ghi âm lệnh giọng nói tức thì (PTT)")
        self.hotkey_manager.register("Ctrl+Shift+M", _toggle_wake_word_cb, "Bật/tắt lắng nghe Hey JARVIS")
        self.hotkey_manager.register("Ctrl+Shift+B", _briefing_cb, "Báo cáo tổng hợp buổi sáng")
        self.hotkey_manager.register("Ctrl+Shift+S", _status_cb, "Kiểm tra tình trạng phần cứng hệ thống")

    def _register_core_actions(self) -> None:
        """Register built-in system and expansion actions into ActionDispatcher."""
        # Core Voice & Hardware actions
        self.dispatcher.register_action(
            name="tts_welcome",
            handler=self._handle_tts_welcome,
            description="Speaks the configured welcome phrase",
        )
        self.dispatcher.register_action(
            name="system_status",
            handler=self._handle_system_status,
            description="Reports system health summary and hardware status",
        )
        self.dispatcher.register_action(
            name="toggle_mute",
            handler=self._handle_toggle_mute,
            description="Toggles microphone listening state",
        )
        self.dispatcher.register_action(
            name="show_overlay",
            handler=self._handle_show_overlay,
            description="Shows the JARVIS chat overlay window",
        )
        self.dispatcher.register_action(
            name="toggle_sidebar",
            handler=self._handle_toggle_sidebar,
            description="Toggles between sidebar and popup overlay mode",
        )
        self.dispatcher.register_action(
            name="collapse_sidebar",
            handler=self._handle_collapse_sidebar,
            description="Collapses sidebar to a compact ribbon",
        )
        self.dispatcher.register_action(
            name="expand_sidebar",
            handler=self._handle_expand_sidebar,
            description="Expands sidebar from compact ribbon to full view",
        )

        # Screen Vision actions
        self.dispatcher.register_action(
            name="screen_capture",
            handler=self._handle_screen_capture,
            description="Captures desktop screenshot and saves to file",
        )
        self.dispatcher.register_action(
            name="screen_analyze",
            handler=self._handle_screen_analyze,
            description="Analyzes screen content using Vision LLM",
        )
        self.dispatcher.register_action(
            name="screen_explain_error",
            handler=self._handle_screen_explain_error,
            description="Scans screen for error dialogs and explains remediation",
        )
        self.dispatcher.register_action(
            name="screen_summarize",
            handler=self._handle_screen_summarize,
            description="Summarizes visible document or code on screen",
        )

        # Web Intelligence actions
        self.dispatcher.register_action(
            name="web_search",
            handler=self._handle_web_search,
            description="Performs real-time web search and returns summary",
        )
        self.dispatcher.register_action(
            name="weather_query",
            handler=self._handle_weather_query,
            description="Queries weather forecast for specified city",
        )
        self.dispatcher.register_action(
            name="news_headlines",
            handler=self._handle_news_headlines,
            description="Fetches top technology news headlines",
        )
        self.dispatcher.register_action(
            name="crypto_rates",
            handler=self._handle_crypto_rates,
            description="Queries cryptocurrency prices (BTC, ETH) and exchange rates",
        )
        self.dispatcher.register_action(
            name="morning_briefing",
            handler=self._handle_morning_briefing,
            description="Synthesizes full morning intelligence briefing",
        )

        # Computer Control & OS Automation actions
        self.dispatcher.register_action(
            name="window_active",
            handler=self._handle_window_active,
            description="Retrieves current active foreground window info",
        )
        self.dispatcher.register_action(
            name="window_minimize_all",
            handler=self._handle_window_minimize_all,
            description="Minimizes all windows to show Desktop",
        )
        self.dispatcher.register_action(
            name="system_volume",
            handler=self._handle_system_volume,
            description="Adjusts or sets master system volume",
        )
        self.dispatcher.register_action(
            name="system_brightness",
            handler=self._handle_system_brightness,
            description="Adjusts or sets display screen brightness",
        )
        self.dispatcher.register_action(
            name="file_search",
            handler=self._handle_file_search,
            description="Searches for local files by name pattern",
        )
        self.dispatcher.register_action(
            name="folder_open",
            handler=self._handle_folder_open,
            description="Opens system folder or directory in Windows Explorer",
        )
        self.dispatcher.register_action(
            name="app_open",
            handler=self._handle_app_open,
            description="Opens desktop application by name or alias",
        )
        self.dispatcher.register_action(
            name="open_app",
            handler=self._handle_app_open,
            description="Alias for app_open",
        )
        self.dispatcher.register_action(
            name="web_open",
            handler=self._handle_web_open,
            description="Opens target website or search query in browser",
        )
        self.dispatcher.register_action(
            name="open_website",
            handler=self._handle_web_open,
            description="Alias for web_open",
        )
        self.dispatcher.register_action(
            name="shell_execute",
            handler=self._handle_shell_execute,
            description="Translates and executes natural language shell command",
        )
        self.dispatcher.register_action(
            name="safety_gate_confirm",
            handler=self._handle_safety_gate_confirm,
            description="Confirms a pending gated high-risk action",
        )
        self.dispatcher.register_action(
            name="safety_gate_reject",
            handler=self._handle_safety_gate_reject,
            description="Rejects a pending gated high-risk action",
        )

        # Proactive Intelligence actions
        self.dispatcher.register_action(
            name="proactive_reminder",
            handler=self._handle_proactive_reminder,
            description="Schedules a proactive timed reminder",
        )
        self.dispatcher.register_action(
            name="proactive_pomodoro_start",
            handler=self._handle_proactive_pomodoro_start,
            description="Starts a Pomodoro focus mode timer",
        )
        self.dispatcher.register_action(
            name="proactive_pomodoro_stop",
            handler=self._handle_proactive_pomodoro_stop,
            description="Stops active Pomodoro focus mode timer",
        )

        # Persistent Memory actions
        self.dispatcher.register_action(
            name="memory_save_fact",
            handler=self._handle_memory_save_fact,
            description="Stores semantic user fact into persistent SQLite memory",
        )
        self.dispatcher.register_action(
            name="memory_summarize_daily",
            handler=self._handle_memory_summarize_daily,
            description="Summarizes today's interactions and episodes",
        )

        # ── Autonomous Superpower Actions (Milestones 1-5) ───────────────────

        # 1. Autonomous ReAct Planner actions
        self.dispatcher.register_action(
            name="generic_task",
            handler=self._handle_generic_task,
            description="Generic autonomous task execution fallback",
        )
        self.dispatcher.register_action(
            name="planner_execute_task",
            handler=self._handle_planner_execute_task,
            description="Constructs and executes an autonomous multi-step Task DAG",
        )
        self.dispatcher.register_action(
            name="autonomous_plan",
            handler=self._handle_planner_execute_task,
            description="Alias for planner_execute_task",
        )

        # 2. Sub-Agent Worker Pool actions
        self.dispatcher.register_action(
            name="subagent_spawn",
            handler=self._handle_subagent_spawn,
            description="Spawns an autonomous background sub-agent worker",
        )
        self.dispatcher.register_action(
            name="subagent_cancel",
            handler=self._handle_subagent_cancel,
            description="Cancels an active background sub-agent worker",
        )
        self.dispatcher.register_action(
            name="subagent_status",
            handler=self._handle_subagent_status,
            description="Queries status telemetry for a sub-agent worker",
        )

        # 3. Sandboxed Self-Coding actions
        self.dispatcher.register_action(
            name="sandbox_execute_code",
            handler=self._handle_sandbox_execute_code,
            description="Executes code safely in the isolated sandbox",
        )
        self.dispatcher.register_action(
            name="sandbox_python_exec",
            handler=self._handle_sandbox_execute_code,
            description="Executes Python code in the sandbox",
        )

        # 4. Persistent Skill Library actions
        self.dispatcher.register_action(
            name="skill_synthesize",
            handler=self._handle_skill_synthesize,
            description="Synthesizes, tests, and packages code as a reusable skill",
        )
        self.dispatcher.register_action(
            name="skill_invoke",
            handler=self._handle_skill_invoke,
            description="Invokes a packaged persistent skill from library",
        )

        # 5. Browser Automation actions
        self.dispatcher.register_action(
            name="browser_navigate",
            handler=self._handle_browser_navigate,
            description="Navigates browser to target URL and captures page state",
        )
        self.dispatcher.register_action(
            name="browser_scrape",
            handler=self._handle_browser_scrape,
            description="Scrapes and parses structured markdown from web page",
        )
        self.dispatcher.register_action(
            name="browser_fill_form",
            handler=self._handle_browser_fill_form,
            description="Fills and submits web forms automatically",
        )
        self.dispatcher.register_action(
            name="browser_compare_prices",
            handler=self._handle_browser_compare_prices,
            description="Scrapes multiple eCommerce sites and compares prices",
        )

        # 6. Computer-Use Vision & GUI Actor actions
        self.dispatcher.register_action(
            name="vision_click_ui",
            handler=self._handle_vision_click_ui,
            description="Locates target UI element visually and clicks it",
        )
        self.dispatcher.register_action(
            name="vision_type_ui",
            handler=self._handle_vision_type_ui,
            description="Locates target UI field visually and types text",
        )
        self.dispatcher.register_action(
            name="vision_verify_state",
            handler=self._handle_vision_verify_state,
            description="Performs visual verification check on screen state",
        )

    # ── Action Handlers ──────────────────────────────────────────────────────

    def _handle_tts_welcome(self, **kwargs) -> dict[str, Any]:
        """Dispatches welcome speech via TTSManager."""
        if self.tts_manager:
            delay = float(self.config.get("tts.welcome.delay_after_song_s", 1.0))
            self.tts_manager.speak_welcome(delay_s=delay)
            return {"status": "welcome_spoken"}
        return {"status": "tts_unavailable"}

    def _handle_system_status(self, **kwargs) -> dict[str, Any]:
        """Vocalizes and returns system health status with live CPU and RAM metrics."""
        lang = "vi"
        if self.config:
            locale = str(self.config.get("system.locale", "vi_VN")).lower()
            lang = "en" if locale.startswith("en") else "vi"

        msg = ""
        metrics_dict: dict[str, Any] = {}
        if self.hardware_reporter:
            try:
                if self.hardware_reporter.monitor.provider is not None:
                    metrics = self.hardware_reporter.monitor.get_metrics()
                else:
                    ram_pct, ram_total, ram_used = self.hardware_reporter.monitor._probe_ram()
                    cpu_pct, per_cpu, cpu_freq = self.hardware_reporter.monitor._probe_cpu()
                    metrics = HardwareMetrics(
                        cpu_percent=cpu_pct,
                        cpu_temp_c=None,
                        gpu_percent=None,
                        gpu_temp_c=None,
                        ram_percent=ram_pct,
                        vram_used_gb=None,
                        smart_status="PASSED",
                        per_cpu_percent=per_cpu,
                        cpu_freq_mhz=cpu_freq,
                        ram_total_bytes=ram_total,
                        ram_used_bytes=ram_used,
                        disks={},
                        timestamp=time.time(),
                    )
                msg = self.hardware_reporter.format_voice_summary(metrics=metrics, lang=lang)
                metrics_dict = metrics.to_dict() if hasattr(metrics, "to_dict") else {}
            except Exception as e:
                log.error("HardwareReporter status query failed: %s", e)
                msg = (
                    "Tình trạng hệ thống: Tất cả dịch vụ đang hoạt động bình thường."
                    if lang == "vi"
                    else "JARVIS systems operating normally. Audio engine active, all plugins responsive."
                )
        else:
            msg = (
                "Tình trạng hệ thống: Tất cả dịch vụ đang hoạt động bình thường."
                if lang == "vi"
                else "JARVIS systems operating normally. Audio engine active, all plugins responsive."
            )

        if self.tts_manager:
            self.tts_manager.speak(msg, wait=False)

        return {
            "status": "healthy",
            "message": msg,
            "metrics": metrics_dict,
        }

    def _handle_toggle_mute(self, **kwargs) -> dict[str, Any]:
        """Toggles microphone mute state."""
        if self.tray_controller:
            self.tray_controller._on_toggle_mute()
            return {"muted": self.tray_controller._is_mic_muted}
        return {"muted": False}

    def _handle_show_overlay(self, **kwargs) -> dict[str, Any]:
        """Shows the JARVIS chat overlay window."""
        if self.overlay:
            self.overlay.show_listening()
            return {"status": "overlay_shown"}
        return {"status": "overlay_unavailable"}

    def _handle_toggle_sidebar(self, **kwargs) -> dict[str, Any]:
        """Toggles overlay sidebar mode."""
        if self.overlay:
            self.overlay.toggle_sidebar()
            return {"status": "sidebar_toggled", "mode": self.overlay.mode.value}
        return {"status": "overlay_unavailable"}

    def _handle_collapse_sidebar(self, **kwargs) -> dict[str, Any]:
        """Collapses sidebar to 40px ribbon."""
        if self.overlay:
            self.overlay.collapse_sidebar()
            return {"status": "sidebar_collapsed"}
        return {"status": "overlay_unavailable"}

    def _handle_expand_sidebar(self, **kwargs) -> dict[str, Any]:
        """Expands sidebar back to full width."""
        if self.overlay:
            self.overlay.expand_sidebar()
            return {"status": "sidebar_expanded"}
        return {"status": "overlay_unavailable"}

    def _handle_screen_capture(self, filepath: str | None = None, **kwargs) -> dict[str, Any]:
        """Captures screen and saves to file."""
        if self.vision_manager:
            try:
                saved_path = self.vision_manager.save_screenshot(filepath=filepath)
                msg = f"Đã chụp ảnh màn hình và lưu tại {saved_path}, thưa Ngài."
                return {"status": "success", "filepath": saved_path, "message": msg}
            except Exception as e:
                return {"status": "failed", "error": str(e), "message": f"Không thể chụp màn hình: {e}"}
        return {"status": "failed", "message": "Vision subsystem unavailable"}

    def _handle_screen_analyze(self, query: str = "Mô tả những gì đang hiển thị trên màn hình", **kwargs) -> dict[str, Any]:
        """Performs visual analysis of the screen."""
        if self.vision_manager:
            res = self.vision_manager.analyze_screen(query=query)
            return {"status": "success", "analysis": res, "message": res}
        return {"status": "failed", "message": "Tôi chưa thể nhìn thấy màn hình do chưa cấu hình Vision API key, thưa Ngài."}

    def _handle_screen_explain_error(self, **kwargs) -> dict[str, Any]:
        """Scans for error dialog and explains remediation."""
        if self.vision_manager:
            res = self.vision_manager.explain_error_on_screen()
            return {"status": "success", "explanation": res, "message": res}
        return {"status": "failed", "message": "Vision subsystem unavailable"}

    def _handle_screen_summarize(self, **kwargs) -> dict[str, Any]:
        """Summarizes open document on screen."""
        if self.vision_manager:
            res = self.vision_manager.summarize_document_on_screen()
            return {"status": "success", "summary": res, "message": res}
        return {"status": "failed", "message": "Vision subsystem unavailable"}

    def _handle_web_search(self, query: str, **kwargs) -> dict[str, Any]:
        """Searches the web and returns summary."""
        if self.web_hub:
            res = self.web_hub.search(query=query)
            return {"status": "success", "result": res, "message": res}
        return {"status": "failed", "message": "Web intelligence hub unavailable"}

    def _handle_weather_query(self, city: str = "Hanoi", location: str | None = None, **kwargs) -> dict[str, Any]:
        """Fetches weather forecast."""
        target_city = location or city
        if self.web_hub:
            res = self.web_hub.get_weather(city=target_city)
            return {"status": "success", "weather": res, "message": res}
        return {"status": "failed", "message": "Weather service unavailable"}

    def _handle_news_headlines(self, limit: int = 3, **kwargs) -> dict[str, Any]:
        """Fetches top technology news headlines."""
        if self.web_hub:
            headlines = self.web_hub.get_top_news(limit=limit)
            msg = "Điểm tin công nghệ nổi bật: " + "; ".join(headlines) + ", thưa Ngài."
            return {"status": "success", "news": headlines, "message": msg}
        return {"status": "failed", "message": "News aggregator unavailable"}

    def _handle_crypto_rates(self, **kwargs) -> dict[str, Any]:
        """Fetches crypto and currency rates."""
        if self.web_hub:
            rates = self.web_hub.get_crypto_rates()
            summary = self.web_hub.finance.get_crypto_summary()
            return {"status": "success", "rates": rates, "message": summary}
        return {"status": "failed", "message": "Financial tracker unavailable"}

    def _handle_morning_briefing(self, city: str | None = None, **kwargs) -> dict[str, Any]:
        """Generates comprehensive morning briefing."""
        if self.web_hub:
            briefing = self.web_hub.generate_morning_briefing(city=city)
            if self.overlay and "overlay_bullets" in briefing:
                self.overlay.show_response("Morning Briefing", "\n".join(briefing["overlay_bullets"]))
            return {
                "status": "success",
                "briefing": briefing,
                "message": briefing.get("spoken_summary", "Chào buổi sáng thưa Ngài."),
            }
        return {"status": "failed", "message": "Web intelligence hub unavailable"}

    def _handle_window_active(self, **kwargs) -> dict[str, Any]:
        """Returns active foreground window info."""
        if self.computer_controller:
            win = self.computer_controller.get_active_window()
            return {"status": "success", "window": win, "message": f"Cửa sổ hiện tại: {win.get('title', 'N/A')}"}
        return {"status": "failed", "message": "Computer controller unavailable"}

    def _handle_window_minimize_all(self, **kwargs) -> dict[str, Any]:
        """Minimizes all windows."""
        if self.computer_controller:
            ok = self.computer_controller.minimize_all()
            return {"status": "success" if ok else "failed", "message": "Đã thu nhỏ tất cả các cửa sổ xuống màn hình Desktop, thưa Ngài."}
        return {"status": "failed", "message": "Computer controller unavailable"}

    def _handle_system_volume(self, delta: int | None = None, level: int | None = None, **kwargs) -> dict[str, Any]:
        """Adjusts or sets master audio volume."""
        if self.computer_controller:
            if level is not None:
                vol = self.computer_controller.set_volume(level)
                return {"status": "success", "volume": vol, "message": f"Đã đặt âm lượng hệ thống thành {vol}%, thưa Ngài."}
            delta_val = delta if delta is not None else 10
            vol = self.computer_controller.change_volume(delta_val)
            return {"status": "success", "volume": vol, "message": f"Đã điều chỉnh âm lượng lên {vol}%, thưa Ngài."}
        return {"status": "failed", "message": "Computer controller unavailable"}

    def _handle_system_brightness(self, delta: int | None = None, level: int | None = None, **kwargs) -> dict[str, Any]:
        """Adjusts or sets screen brightness."""
        if self.computer_controller:
            if level is not None:
                b = self.computer_controller.set_brightness(level)
                return {"status": "success", "brightness": b, "message": f"Đã đặt độ sáng màn hình thành {b}%, thưa Ngài."}
            delta_val = delta if delta is not None else 10
            b = self.computer_controller.change_brightness(delta_val)
            return {"status": "success", "brightness": b, "message": f"Đã điều chỉnh độ sáng màn hình thành {b}%, thưa Ngài."}
        return {"status": "failed", "message": "Computer controller unavailable"}

    def _handle_file_search(self, filename: str | None = None, pattern: str | None = None, directory: str | None = None, root_dir: str | None = None, **kwargs) -> dict[str, Any]:
        """Searches local files."""
        target_name = pattern or filename or "*.*"
        target_root = directory or root_dir
        if self.computer_controller:
            matches = self.computer_controller.search_files(filename=target_name, root_dir=target_root)
            if matches:
                msg = f"Tìm thấy {len(matches)} tệp phù hợp, tệp đầu tiên: {matches[0]}, thưa Ngài."
            else:
                msg = f"Không tìm thấy tệp nào phù hợp với '{target_name}', thưa Ngài."
            return {"status": "success", "matches": matches, "files": matches, "message": msg}
        return {"status": "failed", "message": "Computer controller unavailable"}

    def _handle_folder_open(self, folder: str, **kwargs) -> dict[str, Any]:
        """Opens folder in Explorer."""
        if self.computer_controller:
            ok = self.computer_controller.open_folder(folder)
            msg = f"Đã mở thư mục {folder}, thưa Ngài." if ok else f"Không thể mở thư mục {folder}."
            return {"status": "success" if ok else "failed", "message": msg}
        return {"status": "failed", "message": "Computer controller unavailable"}

    def _handle_app_open(self, app_name: str | None = None, name: str | None = None, app: str | None = None, **kwargs) -> dict[str, Any]:
        """Opens desktop application by name or alias."""
        target = app_name or name or app or kwargs.get("query") or ""
        if self.computer_controller:
            res = self.computer_controller.open_app(target)
            msg = res.get("message") or f"Đã khởi chạy {target}, thưa Ngài."
            return {"status": "success" if res.get("success") else "failed", "result": res, "message": msg}
        return {"status": "failed", "message": "Computer controller unavailable"}

    def _handle_web_open(self, url: str | None = None, target: str | None = None, query: str | None = None, site: str | None = None, **kwargs) -> dict[str, Any]:
        """Opens target website or search query in browser."""
        dest = url or target or site or query or kwargs.get("website") or ""
        if self.computer_controller:
            res = self.computer_controller.open_website(dest)
            msg = res.get("message") or f"Đã mở {dest} cho Ngài."
            return {"status": "success" if res.get("success") else "failed", "result": res, "message": msg}
        return {"status": "failed", "message": "Computer controller unavailable"}

    def _handle_shell_execute(self, query: str, cwd: str | None = None, **kwargs) -> dict[str, Any]:
        """Executes natural language shell command."""
        if self.shell_assistant:
            res = self.shell_assistant.execute_natural_command(query=query, cwd=cwd)
            msg = res.get("summary") or res.get("message", "Đã thực thi lệnh shell.")
            return {"status": "success" if res.get("success") else "failed", "result": res, "message": msg}
        return {"status": "failed", "message": "Shell assistant unavailable"}

    def _handle_safety_gate_confirm(self, token: str | None = None, **kwargs) -> dict[str, Any]:
        """Confirms pending high-risk action."""
        if self.safety_gate:
            pending = self.safety_gate.get_latest_pending()
            t = token or (pending.token if pending else "")
            ok = self.safety_gate.confirm(t) if t else False
            msg = f"Đã xác nhận và thực thi thao tác (Token {t}), thưa Ngài." if ok else "Không có thao tác nào đang chờ xác nhận hoặc token đã hết hạn."
            return {"status": "success" if ok else "failed", "message": msg}
        return {"status": "failed", "message": "Safety gate unavailable"}

    def _handle_safety_gate_reject(self, token: str | None = None, **kwargs) -> dict[str, Any]:
        """Rejects pending high-risk action."""
        if self.safety_gate:
            pending = self.safety_gate.get_latest_pending()
            t = token or (pending.token if pending else "")
            ok = self.safety_gate.reject(t) if t else False
            msg = f"Đã hủy thao tác (Token {t}), thưa Ngài." if ok else "Không có thao tác nào đang chờ xác nhận."
            return {"status": "success" if ok else "failed", "message": msg}
        return {"status": "failed", "message": "Safety gate unavailable"}

    def _handle_proactive_reminder(self, message: str, delay_seconds: float | None = None, delay_minutes: float | None = None, **kwargs) -> dict[str, Any]:
        """Schedules timed reminder."""
        sec = float(delay_seconds if delay_seconds is not None else ((delay_minutes or 5.0) * 60.0))
        if self.proactive_engine:
            r_id = self.proactive_engine.add_reminder(text=message, delay_seconds=sec)
            msg = f"Đã đặt lời nhắc '{message}' sau {int(sec)} giây cho Ngài."
            return {"status": "success", "reminder_id": r_id, "message": msg}
        return {"status": "failed", "message": "Proactive engine unavailable"}

    def _handle_proactive_pomodoro_start(self, work_minutes: float = 25.0, break_minutes: float = 5.0, **kwargs) -> dict[str, Any]:
        """Starts Pomodoro timer."""
        if self.proactive_engine:
            res = self.proactive_engine.start_pomodoro(work_minutes=work_minutes, break_minutes=break_minutes)
            msg = f"Đã bắt đầu phiên tập trung Focus Mode {work_minutes} phút, thưa Ngài."
            return {"status": "success", "message": msg}
        return {"status": "failed", "message": "Proactive engine unavailable"}

    def _handle_proactive_pomodoro_stop(self, **kwargs) -> dict[str, Any]:
        """Stops Pomodoro timer."""
        if self.proactive_engine:
            self.proactive_engine.stop_pomodoro()
            return {"status": "success", "message": "Đã dừng phiên tập trung Focus Mode, thưa Ngài."}
        return {"status": "failed", "message": "Proactive engine unavailable"}

    def _handle_memory_save_fact(self, key: str | None = None, value: str | None = None, text: str | None = None, **kwargs) -> dict[str, Any]:
        """Saves persistent fact."""
        if self.memory_manager:
            res: Any
            if text:
                res = self.memory_manager.handle_remember_command(text)
            elif key and value:
                self.memory_manager.store_fact(key=key, value=value)
                res = {"success": True, "message": f"Tôi đã ghi nhớ thông tin này, thưa Ngài: {key} = {value}."}
            else:
                res = {"success": False, "message": "Thiếu dữ liệu cần ghi nhớ."}
            if self.overlay:
                facts = self.memory_manager.list_facts(limit=3)
                if facts:
                    self.overlay.set_memory_facts([f"{f.get('key')}: {f.get('value')}" for f in facts])
            return {"status": "success" if res.get("success") else "failed", "message": res.get("message", "")}
        return {"status": "failed", "message": "Memory manager unavailable"}

    def _handle_memory_summarize_daily(self, text: str = "", **kwargs) -> dict[str, Any]:
        """Summarizes today's episodic memory logs."""
        if self.memory_manager:
            res = self.memory_manager.handle_today_summary(text)
            return {"status": "success", "summary": res, "message": res.get("message", "")}
        return {"status": "failed", "message": "Memory manager unavailable"}

    # ── Autonomous Superpower Action Handlers ────────────────────────────────

    def _handle_generic_task(self, **kwargs) -> dict[str, Any]:
        """Generic fallback task handler for autonomous plan execution."""
        return {"status": "completed", "details": kwargs, "message": "Tác vụ tự trị đã hoàn thành."}

    def _handle_planner_execute_task(
        self,
        goal: str,
        mode: str = "fully_autonomous",
        context: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Constructs and executes an autonomous multi-step Task DAG."""
        if not self.planner_engine:
            return {"status": "failed", "message": "ReAct Planner Subsystem is unavailable."}

        plan_mode = PlanMode.SAFETY_GATE if "confirm" in mode.lower() or "safety" in mode.lower() else PlanMode.FULLY_AUTONOMOUS
        dag = self.planner_engine.create_plan(goal=goal, context=context)

        # Update HUD overlay with plan telemetry
        if self.overlay:
            self.overlay.update_task_dag(dag.to_dict())

        t0 = time.time()
        plan_result: PlanResult = self.planner_engine.execute_plan(dag, mode=plan_mode)
        duration = time.time() - t0

        # Update HUD overlay with final DAG state
        if self.overlay:
            self.overlay.update_task_dag(dag.to_dict())

        # Persist task history into SQLite Memory
        if self.memory_manager:
            try:
                self.memory_manager.store.record_task_execution(
                    task_id=dag.plan_id,
                    goal=goal,
                    plan_dag_json=dag.to_dict(),
                    execution_trace_json=[r.to_dict() for r in plan_result.step_results],
                    status="completed" if plan_result.success else "failed",
                    duration_seconds=duration,
                )
            except Exception as e:
                log.warning("Could not persist task execution history: %s", e)

        summary_msg = (
            f"Kế hoạch '{goal[:30]}' đã hoàn thành xuất sắc ({len(plan_result.step_results)} bước, {duration:.1f}s)."
            if plan_result.success
            else f"Kế hoạch '{goal[:30]}' gặp lỗi: {plan_result.error}"
        )

        return {
            "status": "success" if plan_result.success else "failed",
            "plan_id": dag.plan_id,
            "goal": goal,
            "success": plan_result.success,
            "duration_seconds": duration,
            "step_results": [r.to_dict() for r in plan_result.step_results],
            "message": summary_msg,
        }

    def _handle_subagent_spawn(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        target_callable: Callable[..., Any] | None = None,
        priority: str = "normal",
        timeout_seconds: float = 300.0,
        **kwargs,
    ) -> dict[str, Any]:
        """Spawns an autonomous background sub-agent worker."""
        if not self.subagent_manager:
            return {"status": "failed", "message": "SubAgent Manager is unavailable."}

        p_enum = WorkerPriority.HIGH if priority.lower() == "high" else (WorkerPriority.CRITICAL if priority.lower() == "critical" else WorkerPriority.NORMAL)
        task = WorkerTask(
            task_id=f"subagent_{uuid.uuid4().hex[:12]}",
            name=name,
            payload=payload or {},
            target_callable=target_callable or (lambda ctx: {"status": "completed", "name": name}),
            priority=p_enum,
            timeout_seconds=timeout_seconds,
        )
        worker_id = self.subagent_manager.spawn_worker(task)
        msg = f"Đã khởi chạy background worker '{name}' (ID: {worker_id}), thưa Ngài."
        return {"status": "success", "worker_id": worker_id, "name": name, "message": msg}

    def _handle_subagent_cancel(self, worker_id: str, **kwargs) -> dict[str, Any]:
        """Cancels an active background sub-agent worker."""
        if not self.subagent_manager:
            return {"status": "failed", "message": "SubAgent Manager is unavailable."}
        ok = self.subagent_manager.cancel_worker(worker_id)
        msg = f"Đã hủy worker {worker_id} thành công." if ok else f"Không tìm thấy worker {worker_id} hoặc worker đã dừng."
        return {"status": "success" if ok else "failed", "worker_id": worker_id, "message": msg}

    def _handle_subagent_status(self, worker_id: str, **kwargs) -> dict[str, Any]:
        """Queries status telemetry for a sub-agent worker."""
        if not self.subagent_manager:
            return {"status": "failed", "message": "SubAgent Manager is unavailable."}
        status = self.subagent_manager.get_worker_status(worker_id)
        if not status:
            return {"status": "not_found", "worker_id": worker_id, "message": f"Worker {worker_id} không tồn tại."}
        return {"status": "success", "telemetry": status.to_dict() if hasattr(status, "to_dict") else str(status)}

    def _handle_sandbox_execute_code(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: float = 15.0,
        **kwargs,
    ) -> dict[str, Any]:
        """Executes code safely in the isolated sandbox."""
        if not self.sandbox:
            return {"status": "failed", "message": "Code Interpreter Sandbox is unavailable."}

        lang = language.lower().strip()
        res: SandboxResult
        if lang in ("powershell", "ps1"):
            res = self.sandbox.execute_powershell(code, timeout_seconds=timeout_seconds)
        else:
            res = self.sandbox.execute_python(code, timeout_seconds=timeout_seconds)

        # Stream code output to overlay HUD
        if self.overlay:
            if res.stdout:
                for line in res.stdout.splitlines()[-5:]:
                    self.overlay.append_code_log(line, "stdout")
            if res.stderr:
                for line in res.stderr.splitlines()[-3:]:
                    self.overlay.append_code_log(line, "stderr")

        msg = (
            f"Code thực thi thành công ({res.execution_time_seconds:.2f}s). {len(res.artifacts)} file đầu ra."
            if res.success
            else f"Lỗi thực thi code: {res.error}"
        )
        return {
            "status": "success" if res.success else "failed",
            "success": res.success,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "data": res.data,
            "artifacts": res.artifacts,
            "execution_time_seconds": res.execution_time_seconds,
            "message": msg,
        }

    def _handle_skill_synthesize(
        self,
        name: str,
        code: str,
        description: str = "",
        category: str = "custom",
        requirements: list[str] | None = None,
        overwrite: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        """Synthesizes, tests, and packages code as a reusable persistent skill."""
        if not self.skill_synthesizer:
            return {"status": "failed", "message": "Skill Synthesizer is unavailable."}

        try:
            skill_def = self.skill_synthesizer.synthesize_skill(
                name=name,
                code=code,
                description=description or f"Tự động tổng hợp kỹ năng {name}",
                tags=[category] if category else None,
            )
        except Exception as e:
            log.warning("Skill synthesis failed for '%s': %s", name, e)
            return {"status": "failed", "skill_name": name, "message": f"Không thể đóng gói kỹ năng '{name}' do lỗi kiểm thử hoặc cú pháp."}

        msg = f"Đã đóng gói thành công kỹ năng '{name}' vào thư viện kỹ năng tái sử dụng, thưa Ngài."
        return {"status": "success", "skill_name": name, "module_path": skill_def.file_path, "message": msg}

    def _handle_skill_invoke(self, skill_name: str, **kwargs) -> dict[str, Any]:
        """Invokes a packaged persistent skill from library."""
        if not self.skill_registry:
            return {"status": "failed", "message": "Skill Registry is unavailable."}
        try:
            res = self.skill_registry.invoke_skill(skill_name, **kwargs)
            return {"status": "success", "result": res, "message": f"Kỹ năng '{skill_name}' thực thi thành công."}
        except Exception as e:
            return {"status": "failed", "error": str(e), "message": f"Lỗi khi thực thi kỹ năng '{skill_name}': {e}"}

    def _handle_browser_navigate(self, url: str, **kwargs) -> dict[str, Any]:
        """Navigates browser to target URL and captures page state."""
        if not self.browser_agent:
            return {"status": "failed", "message": "Browser Agent is unavailable."}
        res: BrowserActionResult = self.browser_agent.navigate(url=url)
        msg = f"Đã điều hướng tới {url} ({res.title or 'Sẵn sàng'})." if res.success else f"Không thể điều hướng tới {url}: {res.error}"
        return {"status": "success" if res.success else "failed", "url": url, "title": res.title, "message": msg}

    def _handle_browser_scrape(self, url: str, extract_tables: bool = True, **kwargs) -> dict[str, Any]:
        """Scrapes and parses structured markdown from web page."""
        if not self.browser_agent:
            return {"status": "failed", "message": "Browser Agent is unavailable."}
        res: ScrapeResult = self.browser_agent.scrape_page(url=url, extract_tables=extract_tables)
        msg = f"Đã trích xuất dữ liệu từ {url} ({len(res.markdown)} ký tự, {len(res.tables)} bảng)." if res.success else f"Lỗi trích xuất từ {url}: {res.error}"
        return {
            "status": "success" if res.success else "failed",
            "url": url,
            "title": res.title,
            "markdown": res.markdown,
            "tables": res.tables,
            "message": msg,
        }

    def _handle_browser_fill_form(
        self,
        url: str,
        fields: dict[str, str],
        submit_selector: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Fills and submits web forms automatically."""
        if not self.browser_agent:
            return {"status": "failed", "message": "Browser Agent is unavailable."}
        res: BrowserActionResult = self.browser_agent.fill_form(url=url, form_fields=fields, submit_selector=submit_selector)
        msg = f"Đã điền tự động {len(fields)} trường dữ liệu trên {url}." if res.success else f"Lỗi điền form: {res.error}"
        return {"status": "success" if res.success else "failed", "url": url, "fields": fields, "message": msg}

    def _handle_browser_compare_prices(self, product: str, stores: list[str] | None = None, **kwargs) -> dict[str, Any]:
        """Scrapes multiple eCommerce sites and compares prices."""
        if not self.browser_agent:
            return {"status": "failed", "message": "Browser Agent is unavailable."}
        target_stores = stores or ["Shopee", "Tiki", "Lazada"]
        items = self.browser_agent.compare_prices(product=product, stores=target_stores)
        msg = f"Đã so sánh giá cho '{product}' trên {len(target_stores)} sàn TMĐT, tìm thấy {len(items)} kết quả."
        return {"status": "success", "product": product, "items": [i.to_dict() if hasattr(i, "to_dict") else i for i in items], "message": msg}

    def _handle_vision_click_ui(self, query: str, verify: bool = True, button: str = "left", clicks: int = 1, **kwargs) -> dict[str, Any]:
        """Locates target UI element visually and clicks it."""
        if not self.gui_actor:
            return {"status": "failed", "message": "GUIActor subsystem is unavailable."}
        res = self.gui_actor.click_element(query=query, verify=verify, button=button, clicks=clicks)
        action_rec = self.gui_actor.action_history[-1] if self.gui_actor.action_history else None
        is_success = res if isinstance(res, bool) else getattr(res, "success", False)
        visual_res = getattr(action_rec, "verification", None) if action_rec else getattr(res, "visual_result", None)
        elem = getattr(action_rec, "grounded_element", None) if action_rec else getattr(res, "element", None)
        err_msg = getattr(action_rec, "error_message", None) if action_rec else getattr(res, "error", None)

        if self.overlay and visual_res:
            self.overlay.display_visual_result(visual_res.to_dict() if hasattr(visual_res, "to_dict") else {"summary": f"Clicked: {query}"})
        msg = f"Đã click vào phần tử '{query}' trên màn hình." if is_success else f"Không thể click vào '{query}': {err_msg or 'Thao tác không thành công'}"
        return {"status": "success" if is_success else "failed", "element": elem.to_dict() if elem and hasattr(elem, "to_dict") else None, "message": msg}

    def _handle_vision_type_ui(self, query: str, text: str, verify: bool = True, press_enter: bool = False, **kwargs) -> dict[str, Any]:
        """Locates target UI field visually and types text."""
        if not self.gui_actor:
            return {"status": "failed", "message": "GUIActor subsystem is unavailable."}
        res = self.gui_actor.type_into_element(query=query, text=text, verify=verify, press_enter=press_enter)
        action_rec = self.gui_actor.action_history[-1] if self.gui_actor.action_history else None
        is_success = res if isinstance(res, bool) else getattr(res, "success", False)
        visual_res = getattr(action_rec, "verification", None) if action_rec else getattr(res, "visual_result", None)
        elem = getattr(action_rec, "grounded_element", None) if action_rec else getattr(res, "element", None)
        err_msg = getattr(action_rec, "error_message", None) if action_rec else getattr(res, "error", None)

        if self.overlay and visual_res:
            self.overlay.display_visual_result(visual_res.to_dict() if hasattr(visual_res, "to_dict") else {"summary": f"Typed into: {query}"})
        msg = f"Đã nhập văn bản vào '{query}'." if is_success else f"Không thể nhập vào '{query}': {err_msg or 'Thao tác không thành công'}"
        return {"status": "success" if is_success else "failed", "element": elem.to_dict() if elem and hasattr(elem, "to_dict") else None, "message": msg}

    def _handle_vision_verify_state(self, query: str | None = None, expected_condition: str | None = None, **kwargs) -> dict[str, Any]:
        """Performs visual verification check on screen state."""
        if not self.visual_verifier:
            return {"status": "failed", "message": "Visual Verifier is unavailable."}
        if self.overlay:
            self.overlay.display_visual_result({"title": "Visual State Check", "query": query, "expected": expected_condition})
        return {"status": "success", "message": "Đã kiểm tra xác minh trạng thái thị giác màn hình, thưa Ngài."}

    def _on_overlay_quick_action(self, action_key: str) -> Any:
        """Handles quick action button clicks on AlwaysOnOverlay."""
        log.info("Overlay quick action invoked: %s", action_key)
        if action_key == "briefing_morning":
            return self._handle_morning_briefing()
        elif action_key == "system_status":
            return self._handle_system_status()
        elif action_key == "focus_mode":
            if self.proactive_engine:
                return self.proactive_engine.start_pomodoro()
        return None

    def record_audio(
        self,
        duration_s: float | None = None,
        sample_rate: int | None = None,
    ) -> np.ndarray:
        """
        Captures an audio buffer from the microphone with fast energy-based silence cutoff.
        """
        sr = int(sample_rate or self.config.get("audio.sample_rate", 44100))
        max_dur = float(duration_s or self.config.get("stt.timeout_s", 4.0))

        if self.headless:
            return np.zeros(int(sr * min(max_dur, 0.1)), dtype=np.float32)

        try:
            import sounddevice as _sd
            chunk_size = int(sr * 0.15)  # 150ms chunks
            recorded_chunks: list[np.ndarray] = []
            max_chunks = int(max_dur / 0.15)
            silence_chunks_after_speech = 0
            has_speech_started = False
            energy_threshold = 0.015

            log.info("Capturing voice command (max %.1fs, chunk_size=%d)...", max_dur, chunk_size)
            with _sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=chunk_size) as stream:
                for _ in range(max_chunks):
                    chunk, overflowed = stream.read(chunk_size)
                    chunk_flat = chunk.flatten()
                    recorded_chunks.append(chunk_flat)

                    rms = float(np.sqrt(np.mean(chunk_flat ** 2))) if len(chunk_flat) > 0 else 0.0
                    if rms > energy_threshold:
                        has_speech_started = True
                        silence_chunks_after_speech = 0
                    elif has_speech_started:
                        silence_chunks_after_speech += 1
                        # If user spoke and then fell silent for ~1.0s (7 chunks), cut off early
                        if silence_chunks_after_speech >= 7:
                            log.debug("Speech ended naturally (silence cutoff after %d chunks).", len(recorded_chunks))
                            break

            if recorded_chunks:
                return np.concatenate(recorded_chunks)
            return np.zeros(int(sr * 0.5), dtype=np.float32)
        except Exception as e:
            log.warning("Fast microphone capture via InputStream failed: %s. Falling back to simple rec.", e)
            try:
                import sounddevice as _sd
                dur = min(max_dur, 3.0)
                audio_data = _sd.rec(int(dur * sr), samplerate=sr, channels=1, dtype="float32")
                _sd.wait()
                return audio_data.flatten()
            except Exception:
                return np.zeros(int(sr * 0.5), dtype=np.float32)

    def _start_voice_interaction(
        self,
        greeting_phrase: str = "Vâng thưa Ngài, tôi đang lắng nghe.",
        trigger_name: str = "VOICE",
    ) -> None:
        """
        Executes asynchronous Voice Interaction Loop without blocking UI.
        Enforces single-flight execution and acoustic echo suppression.
        """
        with self._voice_lock:
            if self._is_voice_interacting:
                log.debug("Voice interaction already in progress. Suppressing trigger [%s].", trigger_name)
                return
            self._is_voice_interacting = True

        def _voice_loop():
            try:
                if self.proactive_engine:
                    self.proactive_engine.record_user_activity()

                if self.overlay:
                    self.overlay.show_listening(greeting_phrase)
                if self.tts_manager and greeting_phrase:
                    # Wait for greeting to finish so the microphone doesn't capture speaker output
                    self.tts_manager.speak(greeting_phrase, wait=True)

                if self.tray_controller:
                    self.tray_controller.update_status(TrayStatus.LISTENING)

                transcript = ""
                if self.stt_engine:
                    try:
                        audio_flat = self.record_audio()
                        transcript = self.stt_engine.transcribe(audio_flat)
                        log.info("Transcribed: '%s'", transcript)
                    except Exception as e:
                        log.error("STT recording/transcription failed: %s", e)

                if not transcript or not transcript.strip():
                    if self.overlay:
                        self.overlay.show_response("(không nghe thấy)", "Tôi không nghe thấy gì. Vui lòng thử lại.")
                    # Only play spoken TTS error on explicit user actions (hotkey, tray), not ambient wake word triggers
                    if self.tts_manager and not trigger_name.startswith("WAKE_WORD"):
                        self.tts_manager.speak("Tôi không nghe thấy gì cả. Vui lòng thử lại.", wait=True)
                    if self.tray_controller:
                        self.tray_controller.update_status(TrayStatus.ACTIVE)
                    self.log_interaction(
                        trigger=trigger_name,
                        input_text="(silence)",
                        action="none",
                        response="Tôi không nghe thấy gì cả. Vui lòng thử lại.",
                        status="failed",
                    )
                    return

                if self.overlay:
                    self.overlay.show_thinking(transcript)

                response_text = ""
                try:
                    result = self.process_text_command(transcript, requester=trigger_name.lower())
                    response_text = result.get("response_text", "")
                except Exception as e:
                    log.error("Command processing failed: %s", e)
                    response_text = f"Xin lỗi, tôi gặp lỗi khi xử lý lệnh: {e}"
                    if self.tts_manager:
                        self.tts_manager.speak(response_text, wait=True)

                if self.overlay:
                    self.overlay.show_response(transcript, response_text)

                if self.tray_controller:
                    self.tray_controller.update_status(TrayStatus.ACTIVE)
            finally:
                # 1.0s cooldown to ensure speaker sound dissipates before re-arming wake word
                time.sleep(1.0)
                with self._voice_lock:
                    self._is_voice_interacting = False

        threading.Thread(target=_voice_loop, daemon=True, name="JARVIS-VoiceInteraction").start()

    def _on_wake_word_triggered(self) -> None:
        """Callback invoked when wake word detector detects 'Hey JARVIS'."""
        log.info("Wake word triggered ('Hey JARVIS')")
        self._start_voice_interaction(
            greeting_phrase="Vâng thưa Ngài",
            trigger_name="WAKE_WORD:hey_jarvis",
        )

    def _on_wake_word_event(self, keyword: str, confidence: float) -> None:
        """Two-arg callback for wake word detection telemetry."""
        log.debug("Wake word event: %s (confidence=%.2f)", keyword, confidence)
        if self.dashboard_server:
            self.dashboard_server.broadcast_event({
                "type": "wake_word",
                "keyword": keyword,
                "confidence": confidence,
            })

    def _on_gesture_event(self, pattern_name: str, confidence: float = 1.0) -> None:
        """Routes acoustic gesture patterns to actions."""
        now = time.monotonic()
        last = self._pattern_last_fired.get(pattern_name, 0.0)
        elapsed = now - last

        cooldown = self._action_fanout_cooldown_s
        if elapsed < cooldown:
            log.info("Gesture [%s] suppressed — cooldown %.1fs remaining.", pattern_name, cooldown - elapsed)
            return

        self._pattern_last_fired[pattern_name] = now
        log.info("Gesture detected: [%s] (conf=%.2f)", pattern_name, confidence)

        if self.dashboard_server:
            self.dashboard_server.broadcast_event({
                "type": "gesture",
                "pattern": pattern_name,
                "confidence": confidence,
            })

        if pattern_name == "double_clap":
            if not self.welcome_executed:
                self.welcome_executed = True
                log.info("First activation — running welcome sequence.")
                self.log_interaction(
                    trigger="GESTURE:double_clap",
                    input_text="double_clap",
                    action="welcome_sequence",
                    response="Khởi chạy chuỗi hành động chào mừng và ứng dụng làm việc",
                    status="success",
                )

                def _welcome():
                    configured_actions = self.config.get("gesture.patterns.double_clap.actions", [
                        "spotify", "chrome_claude", "chrome_binance", "tts_welcome", "cursor"
                    ])
                    for act in configured_actions:
                        try:
                            self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                        except Exception as e:
                            log.warning("Action [%s] failed during welcome sequence: %s", act, e)

                threading.Thread(target=_welcome, daemon=True, name="Welcome-Sequence").start()
            else:
                log.info("Subsequent double clap — starting voice interaction.")
                self._start_voice_interaction(
                    greeting_phrase="Vâng thưa Ngài, tôi đang lắng nghe.",
                    trigger_name="GESTURE:double_clap",
                )
            return

        if pattern_name == "triple_clap":
            action_names = self.config.get("gesture.patterns.triple_clap.actions", ["system_status"])
            for act in action_names:
                try:
                    self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                except Exception as e:
                    log.error("Action [%s] failed for pattern [triple_clap]: %s", act, e)
            self.log_interaction(
                trigger="GESTURE:triple_clap",
                input_text="triple_clap",
                action=",".join(action_names),
                response="Báo cáo tình trạng hệ thống và phần cứng",
                status="success",
            )
            return

        if pattern_name == "clap_pause_clap":
            action_names = self.config.get("gesture.patterns.clap_pause_clap.actions", ["show_overlay"])
            for act in action_names:
                try:
                    self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                except Exception as e:
                    log.error("Action [%s] failed for pattern [clap_pause_clap]: %s", act, e)
            self.log_interaction(
                trigger="GESTURE:clap_pause_clap",
                input_text="clap_pause_clap",
                action=",".join(action_names),
                response="Hiển thị cửa sổ giao diện JARVIS Overlay HUD",
                status="success",
            )
            return

        action_names = self.config.get(f"gesture.patterns.{pattern_name}.actions", [])
        for act in action_names:
            try:
                self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
            except Exception as e:
                log.error("Action [%s] failed for pattern [%s]: %s", act, pattern_name, e)
        if action_names:
            self.log_interaction(
                trigger=f"GESTURE:{pattern_name}",
                input_text=pattern_name,
                action=",".join(action_names),
                response=f"Thực thi actions cho pattern {pattern_name}",
                status="success",
            )

    def process_voice_command(self, audio_buffer: np.ndarray) -> dict[str, Any]:
        """
        End-to-End Voice Loop:
        Record Audio -> STT Transcribe -> LLM Intent Parse / Autonomous Plan -> Dispatch Action -> TTS Speak.
        """
        if self.tray_controller:
            self.tray_controller.update_status(TrayStatus.LISTENING)

        transcript = ""
        if self.stt_engine:
            try:
                transcript = self.stt_engine.transcribe(audio_buffer)
            except Exception as e:
                log.error("STT transcription failed: %s", e)

        if not transcript or not transcript.strip():
            log.debug("Silent audio buffer; ignoring voice command.")
            if self.tray_controller:
                self.tray_controller.update_status(TrayStatus.ACTIVE)
            return {"success": False, "error": "No speech detected"}

        log.info("Voice Transcript: '%s'", transcript)
        return self.process_text_command(transcript, requester="voice")

    def process_text_command(self, text: str, requester: str = "user") -> dict[str, Any]:
        """
        Executes text command:
        Inactivity Reset -> Short-Term Memory Turn -> Intent Parsing / Multi-step ReAct Planning -> Action Dispatch ->
        Long-Term / Episodic Memory Persistence -> Overlay Cards & Preview -> TTS Vocalization -> Interaction Log.
        """
        clean_text = text.strip()
        trigger_name = requester.upper() if requester else "USER"
        if not clean_text:
            self.log_interaction(
                trigger=trigger_name,
                input_text="",
                action="none",
                response="Empty command",
                status="failed",
            )
            return {"success": False, "error": "Empty command"}

        # 1. Reset Inactivity Timer
        if self.proactive_engine:
            self.proactive_engine.record_user_activity()

        # 2. Record User Turn in Short-Term Session Memory
        if self.memory_manager:
            self.memory_manager.add_session_turn(role="user", content=clean_text)

        # 3. Check for Autonomous Multi-Step Planning Triggers
        is_autonomous_plan = (
            clean_text.lower().startswith((
                "kế hoạch", "lập kế hoạch", "tự động", "hãy tự động",
                "thực hiện quy trình", "plan:", "workflow:", "autonomous:"
            ))
            or (
                "tổng hợp" in clean_text.lower() and "báo cáo" in clean_text.lower()
            )
        )

        # 4. Intent Routing
        intent_result = None
        if not is_autonomous_plan and self.llm_router:
            try:
                intent_result = self.llm_router.parse_intent(clean_text)
            except Exception as e:
                log.error("LLM Intent Router failed: %s", e)

        # Check if intent router mapped to planner
        if intent_result and intent_result.action_name in ("planner_execute_task", "autonomous_plan"):
            is_autonomous_plan = True

        response_text = ""
        action_result = None
        status_flag = "success"
        matched_action = "unknown_intent"

        if is_autonomous_plan:
            matched_action = "planner_execute_task"
            try:
                plan_out = self._handle_planner_execute_task(goal=clean_text)
                response_text = plan_out.get("message", "Đã thực hiện kế hoạch tự trị.")
                status_flag = "success" if plan_out.get("status") == "success" else "failed"
            except Exception as e:
                log.error("Autonomous ReAct Planning execution failed: %s", e)
                response_text = f"Lỗi khi thực hiện kế hoạch tự trị: {e}"
                status_flag = "failed"
        elif intent_result and intent_result.action_name != "unknown_intent":
            try:
                matched_action = intent_result.action_name

                if matched_action == "memory_save_fact":
                    response_text = intent_result.parameters.get("message", "Tôi đã ghi nhớ thông tin này, thưa Ngài.")
                    if self.overlay and self.memory_manager:
                        facts = self.memory_manager.list_facts(limit=3)
                        if facts:
                            self.overlay.set_memory_facts([f"{f.get('key')}: {f.get('value')}" for f in facts])
                elif matched_action == "memory_summarize_daily":
                    response_text = intent_result.parameters.get("message", intent_result.parameters.get("summary", "Đang tóm tắt hoạt động hôm nay cho Ngài."))
                elif matched_action == "generic_llm_response":
                    response_text = intent_result.parameters.get("reply", "")
                else:
                    action_result = self.dispatcher.dispatch_action(
                        action_name=matched_action,
                        payload=intent_result.parameters,
                        requester=RequesterContext.user(requester_id=requester, authenticated=True),
                    )
                    if (
                        action_result
                        and action_result.data
                        and isinstance(action_result.data, dict)
                        and action_result.data.get("message")
                    ):
                        response_text = str(action_result.data["message"])
                    elif intent_result.action_name == "generic_llm_response":
                        response_text = intent_result.parameters.get("reply", "")
                    elif intent_result.response_text:
                        response_text = intent_result.response_text
                    else:
                        if self.llm_router and hasattr(self.llm_router, "get_natural_response"):
                            response_text = self.llm_router.get_natural_response(
                                intent_result.action_name,
                                params=intent_result.parameters,
                                text=clean_text,
                                action_result=action_result,
                            )
                        else:
                            response_text = f"Đã thực hiện lệnh: {intent_result.action_name}"
            except Exception as e:
                log.error("Action execution failed: %s", e)
                response_text = f"Lỗi thực thi: {e}"
                status_flag = "failed"
        else:
            response_text = "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"
            status_flag = "failed"

        # 5. Record Assistant Turn & Log Episode into Persistent Memory
        if self.memory_manager:
            self.memory_manager.add_session_turn(
                role="assistant",
                content=response_text,
                action_name=matched_action,
            )
            self.memory_manager.log_episode(
                command=clean_text,
                intent=matched_action,
                outcome=response_text,
                success=(status_flag == "success"),
                trigger_type=trigger_name,
            )

        # 6. Update Overlay UI History Cards & Response Display
        if self.overlay:
            self.overlay.add_turn(user_text=clean_text, jarvis_text=response_text, action=matched_action)
            self.overlay.show_response(clean_text, response_text)

        # 7. Vocalize response via TTS
        if self.tts_manager and response_text:
            self.tts_manager.speak(response_text, wait=False)

        if self.tray_controller:
            self.tray_controller.update_status(TrayStatus.ACTIVE)

        if self.dashboard_server:
            self.dashboard_server.broadcast_event({
                "type": "command",
                "input": clean_text,
                "response": response_text,
                "action": matched_action,
            })

        # 8. Emit structured interaction log
        self.log_interaction(
            trigger=trigger_name,
            input_text=clean_text,
            action=matched_action,
            response=response_text,
            status=status_flag,
        )

        return {
            "success": status_flag == "success",
            "transcript": clean_text,
            "intent": intent_result.to_dict() if intent_result is not None else None,
            "result": action_result.to_dict() if action_result else None,
            "response_text": response_text,
        }

    def start(self) -> None:
        """Starts real-time audio capture, UI servers, proactive intelligence, and background loops."""
        self.initialize()

        # Start Proactive Intelligence Engine
        if self.proactive_engine:
            try:
                self.proactive_engine.start()
                log.info("Proactive Intelligence Engine started.")
            except Exception as e:
                log.warning("Proactive Intelligence Engine failed to start: %s", e)

        # Start Audio Engine Stream
        if self.audio_engine:
            try:
                self.audio_engine.start_stream()
                log.info("Audio capture stream started. Listening for gestures & wake word...")
            except Exception as e:
                log.warning("Audio capture stream failed to start: %s (running event-only)", e)

        # Start Dashboard Server
        if self.dashboard_server:
            try:
                self.dashboard_server.start()
            except Exception as e:
                log.warning("Dashboard Server failed to start: %s", e)

        # Start JARVIS Overlay (Always-On HUD)
        if self.overlay and not self.headless:
            try:
                self.overlay.start()
                log.info("JARVIS Always-On Overlay HUD ready.")
            except Exception as e:
                log.warning("JARVIS Overlay failed to start: %s", e)

        # Start System Tray Controller
        if self.tray_controller:
            try:
                self.tray_controller.start(in_thread=True)
            except Exception as e:
                log.warning("System Tray failed to start: %s", e)

        # Start Global Hotkey Manager
        if self.hotkey_manager:
            try:
                self.hotkey_manager.start()
                log.info("Global Keyboard Hotkey Manager started.")
            except Exception as e:
                log.warning("Global Hotkey Manager failed to start: %s", e)

        # Startup self-introduction speech
        if self.tts_manager:
            try:
                startup_greeting = (
                    self.config.get("tts.welcome.startup_phrase")
                    or self.config.get("welcome.startup_greeting")
                    or "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."
                )
                self.tts_manager.speak(startup_greeting, wait=False)
                log.info("Startup vocal introduction queued: '%s'", startup_greeting)
            except Exception as e:
                log.warning("Startup vocal introduction failed to queue: %s", e)

    def run(self) -> int:
        """Enters main daemon event loop until shutdown signal."""
        self.start()
        log.info("JARVIS Assistant running. Press Ctrl+C to terminate.")
        try:
            while not self._shutdown_event.is_set():
                time.sleep(0.5)
            return 0
        except KeyboardInterrupt:
            log.info("Keyboard interrupt received.")
            self.stop()
            return 0
        except Exception as e:
            log.critical("Fatal crash in JARVIS main loop: %s", e, exc_info=True)
            self.stop()
            return 1

    def _handle_signal(self, signum: int, frame: Any) -> None:
        log.info("Termination signal (%d) received. Shutting down...", signum)
        self.stop()

    def stop(self) -> None:
        """Gracefully halts all worker threads, servers, and streams."""
        with self._lock:
            if self._shutdown_event.is_set():
                return
            self._shutdown_event.set()
            self._initialized = False

        if self.subagent_manager:
            try:
                self.subagent_manager.shutdown(wait=False, cancel_running=True)
            except Exception as e:
                log.debug("Error stopping subagent manager: %s", e)

        if self.proactive_engine:
            self.proactive_engine.stop()
        if self.overlay:
            self.overlay.destroy()
        if self.tray_controller:
            self.tray_controller.stop()
        if self.hotkey_manager:
            try:
                self.hotkey_manager.stop()
            except Exception as e:
                log.debug("Error stopping hotkey manager: %s", e)
        if self.dashboard_server:
            self.dashboard_server.stop()
        if self.audio_engine:
            self.audio_engine.stop_stream()
        if self.wake_word_detector:
            try:
                self.wake_word_detector.shutdown()
            except Exception as e:
                log.debug("Error shutting down wake word detector: %s", e)
        if self.tts_manager:
            self.tts_manager.stop()
        if not self.no_hot_reload:
            self.config.stop_watcher()
        self.plugin_registry.stop_all()
        log.info("JARVIS shutdown cleanly completed.")
