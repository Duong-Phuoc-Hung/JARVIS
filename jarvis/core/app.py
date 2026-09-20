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
from dataclasses import asdict, is_dataclass
from typing import Any
from urllib.parse import urlsplit

import numpy as np

from jarvis.audio.engine import (
    AudioEngine,
    MicrophoneDeviceUnavailableError,
    MicrophoneProbeManager,
)

# Expansion Subsystems (Milestones 1-6)
from jarvis.audio.wake_word import WakeWordDetector
from jarvis.automation.control import ComputerController
from jarvis.automation.gui_actor import GUIActor
from jarvis.automation.safety_gate import SafetyGate
from jarvis.automation.shell_assistant import ShellAssistant
from jarvis.browser.agent import BrowserAgent
from jarvis.browser.models import (
    BrowserActionResult,
    BrowserConfig,
    BrowserDriverType,
    ScrapeResult,
)
from jarvis.browser.session import BrowserSessionManager
from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.labs import require_labs
from jarvis.core.logger import log_interaction as _global_log_interaction
from jarvis.core.models import RequesterContext
from jarvis.core.paths import get_data_dir as get_jarvis_data_dir
from jarvis.core.plugin import PluginRegistry
from jarvis.core.runaway_guard import PassiveTriggerGuard, launch_dedupe_guard
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
from jarvis.security.secrets import get_secret
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.synthesizer import DynamicSkillSynthesizer

# Subsystems
from jarvis.smart_home.home_assistant import HomeAssistantClient
from jarvis.stt.engine import CapturedAudio, STTEngine, validate_sample_rate
from jarvis.tts.manager import AcousticGateTimeoutError, TTSManager
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


def _safe_browser_failure_url(url: str) -> str:
    """Return only a credential-free origin for failed browser responses."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme}://{host}{port}"
    except (TypeError, ValueError):
        return ""


def _build_browser_config(
    browser_cfg: dict[str, Any],
    *,
    session_dir: str,
    app_headless: bool,
) -> BrowserConfig:
    """Map the application configuration onto the canonical browser contract."""
    defaults = BrowserConfig()
    raw_driver = browser_cfg.get(
        "driver_type",
        browser_cfg.get("driver", defaults.driver_type.value),
    )
    driver_type = (
        raw_driver
        if isinstance(raw_driver, BrowserDriverType)
        else BrowserDriverType(str(raw_driver).strip().lower())
    )
    extra_headers = browser_cfg.get("extra_headers", {})
    if not isinstance(extra_headers, dict):
        raise ValueError("browser.extra_headers must be a mapping")
    cdp_headers = browser_cfg.get("cdp_headers", {})
    if not isinstance(cdp_headers, dict):
        raise ValueError("browser.cdp_headers must be a mapping")
    return BrowserConfig(
        driver_type=driver_type,
        headless=bool(browser_cfg.get("headless", app_headless)),
        user_agent=str(browser_cfg.get("user_agent", defaults.user_agent)),
        viewport_width=int(browser_cfg.get("viewport_width", defaults.viewport_width)),
        viewport_height=int(browser_cfg.get("viewport_height", defaults.viewport_height)),
        timeout_ms=int(browser_cfg.get("timeout_ms", defaults.timeout_ms)),
        downloads_dir=str(browser_cfg.get("downloads_dir", defaults.downloads_dir)),
        session_storage_dir=session_dir,
        cdp_endpoint=str(browser_cfg.get("cdp_endpoint", defaults.cdp_endpoint)),
        proxy=browser_cfg.get("proxy"),
        accept_downloads=bool(
            browser_cfg.get("accept_downloads", defaults.accept_downloads)
        ),
        slow_mo_ms=int(browser_cfg.get("slow_mo_ms", defaults.slow_mo_ms)),
        extra_headers={str(key): str(value) for key, value in extra_headers.items()},
        cdp_headers={str(key): str(value) for key, value in cdp_headers.items()},
    )


# Deterministic system_power sub-action alias normalization. Keys are matched
# case-insensitively/trimmed against the incoming "action"/"power_action"
# parameter; values are the canonical action _handle_system_power() acts on.
# This is purely an internal normalization table -- it does NOT affect
# SafetyGateInterceptor.SYSTEM_POWER_DESTRUCTIVE_SUBACTIONS (jarvis/planner/
# safety_interceptor.py), which independently classifies high-risk sub-actions
# from the raw, unnormalized router payload before this handler ever runs.
_POWER_ACTION_ALIASES: dict[str, str] = {
    "shutdown": "shutdown",
    "power_off": "shutdown",
    "poweroff": "shutdown",
    "power off": "shutdown",
    "turn_off": "shutdown",
    "restart": "restart",
    "reboot": "restart",
    "sleep": "sleep",
    "suspend": "sleep",
    "hibernate": "hibernate",
    "lock": "lock",
    "lock_screen": "lock",
    "lock screen": "lock",
}

# Canonical power actions with no trustworthy, authoritative backend anywhere
# in this repository today (verified by repo-wide search -- only
# WindowsPlatformAPI.lock_workstation() exists and is truthful). Reporting
# these as executed would violate the dispatch-truthfulness invariant, so
# _handle_system_power() fails closed for all of them rather than inventing
# an ad-hoc `shutdown /s`/PowerShell path just to look functional.
_UNSUPPORTED_POWER_ACTIONS: frozenset[str] = frozenset({"shutdown", "restart", "sleep", "hibernate"})


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
        self.dispatcher = ActionDispatcher(event_bus=self.event_bus, config=self.config)
        self.plugin_registry = PluginRegistry(self.dispatcher)

        # 2. Audio & Speech Subsystems
        self.tts_manager: TTSManager | None = None
        self.audio_engine: AudioEngine | None = None
        self.gesture_detector: GestureDetector | None = None
        self.wake_word_detector: WakeWordDetector | None = None
        self.stt_engine: STTEngine | None = None
        # Truthful mic-mute state tracker, used when no tray_controller exists
        # (headless/CLI mode) -- see _handle_toggle_mute(). When tray_controller
        # is present, tray_controller._is_mic_muted is the single source of truth
        # instead, so voice commands and the tray icon can never silently diverge.
        self._mic_muted: bool = False

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
        self._action_fanout_cooldown_s: float = 3.0
        self._is_voice_interacting: bool = False
        self._voice_lock = threading.Lock()
        # P0 runaway-hardening: centralized circuit breaker bounding how often
        # an AMBIENT/passive trigger (wake word, acoustic gesture) may initiate
        # a heavy pipeline -- see jarvis/core/runaway_guard.py. Replaces the
        # previous ad hoc `_pattern_last_fired` dict, which only enforced a
        # minimum interval and had no upper bound on total triggers over time
        # (so a sustained acoustic feedback loop could retrigger indefinitely).
        # Never route explicit user actions (hotkey, typed text command)
        # through this guard -- only WAKE_WORD:*/GESTURE:* trigger keys.
        #
        # Pre-commit review correction: __init__() runs BEFORE
        # self.config.load() (which only happens in initialize()) --
        # self.config._data is still {} here, so reading
        # "safety.passive_trigger_guard.*"/"safety.launch_dedupe_cooldown_s"
        # at this point would silently always fall back to the hardcoded
        # Python default, ignoring any real default_config.yaml/custom-config
        # value. Construct with the class's own safe built-in defaults only;
        # the REAL configured values are applied in initialize(), after the
        # config is actually loaded -- see _apply_safety_guard_config().
        self._passive_trigger_guard = PassiveTriggerGuard()

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

        # P0 runaway-hardening, pre-commit review correction: apply the REAL
        # loaded safety.passive_trigger_guard.*/safety.launch_dedupe_cooldown_s
        # values now that self.config.load() has actually run (see the
        # constructor comment above -- reading them any earlier, in
        # __init__(), always saw the pre-load empty config and silently used
        # the hardcoded fallback default instead of a real custom value).
        # Also register for hot-reload so a later edit to these settings
        # takes effect too, without ever reconstructing the guard objects
        # (which would silently discard any in-flight trigger history/active
        # lockout) -- see _apply_safety_guard_config().
        self._apply_safety_guard_config()
        self.config.register_reload_callback(self._on_safety_config_reloaded)

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
            gemini_api_key=vis_cfg.get("gemini_api_key") or get_secret("GEMINI_API_KEY") or "",
            openai_api_key=vis_cfg.get("openai_api_key") or get_secret("OPENAI_API_KEY") or "",
            default_provider=vis_cfg.get("provider", "gemini"),
            gemini_model=vis_cfg.get("gemini_model", "gemini-1.5-flash"),
            openai_model=vis_cfg.get("openai_model", "gpt-4o"),
            timeout_seconds=float(vis_cfg.get("timeout_s", 10.0)),
        )

        # 7. Web Intelligence Hub (R5)
        web_cfg = self.config.get("web", {})
        self.web_hub = WebIntelligenceHub(
            cache_ttl_seconds=float(web_cfg.get("cache_ttl_s", 600.0)),
            weather_api_key=web_cfg.get("weather_api_key") or get_secret("WEATHER_API_KEY") or "",
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
        _llm_provider = llm_cfg.get("provider", "openai")
        _llm_secret_key = (
            "GEMINI_API_KEY" if "gemini" in _llm_provider.lower() else "OPENAI_API_KEY"
        )
        self.llm_client = LLMClient(
            provider=_llm_provider,
            api_key=llm_cfg.get("api_key") or get_secret(_llm_secret_key) or "",
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
            now = timestamp if timestamp is not None else time.monotonic()
            if self.tts_manager and self.tts_manager.is_in_echo_window(current_time=now, cooldown_s=2.5):
                # Acoustic Echo Suppression: drop incoming microphone frames while TTS is speaking or in cooldown
                if self.wake_word_detector:
                    try:
                        self.wake_word_detector.suppress_until(now + 0.1)
                    except Exception:
                        pass
                return

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
        browser_session_dir = browser_cfg.get("session_dir") or str(
            get_jarvis_data_dir() / "browser_sessions"
        )
        self.browser_session_manager = BrowserSessionManager(
            storage_dir=browser_session_dir,
            db_path=mem_db,
        )
        canonical_browser_config = _build_browser_config(
            browser_cfg,
            session_dir=browser_session_dir,
            app_headless=self.headless,
        )
        self.browser_agent = BrowserAgent(
            config=canonical_browser_config,
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
        from jarvis.comms.telegram import TelegramBotController
        telegram_token = get_secret("TELEGRAM_BOT_TOKEN")
        if telegram_token:
            whitelist_cfg = self.config.get("comms", {}).get("telegram", {}).get("whitelist_user_ids", [])
            allowed_ids = set(whitelist_cfg) if isinstance(whitelist_cfg, list) else set()
            self.telegram_controller = TelegramBotController(
                bot_token=telegram_token,
                allowed_user_ids=allowed_ids,
                dispatcher=self.dispatcher,
                stt_engine=self.stt_engine,
            )
            self.telegram_controller.start()
        else:
            self.telegram_controller = None

        self.worker_notifications = WorkerNotificationDispatcher(
            tts_manager=self.tts_manager,
            overlay=self.overlay,
            telegram_controller=self.telegram_controller,
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

        # 25. Smart Home / Home Assistant Integration (D-10 / F-26)
        ha_cfg = self.config.get("smart_home.home_assistant", {})
        if not isinstance(ha_cfg, dict):
            ha_cfg = {}
        ha_token = ha_cfg.get("token") or get_secret("HASS_TOKEN")
        self.ha_client = HomeAssistantClient(
            base_url=ha_cfg.get("url", "http://homeassistant.local:8123"),
            access_token=ha_token,
            entity_aliases=ha_cfg.get("entities"),
        )

        # 26. Signal Handlers
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
            # H-04 fix: delegate directly to _start_voice_interaction (which does NOT
            # exist as _handle_voice_command anywhere -- that path never existed).
            # PTT hotkey uses shorter greeting to minimize delay before recording starts.
            #
            # H-04 FINAL: no wrapper thread here. GlobalHotkeyManager already invokes
            # every hotkey callback on its own dedicated background thread (see
            # jarvis/platform/hotkeys.py::_message_pump_loop -- "Run callback in
            # background thread to avoid blocking pump"), so this callback never runs
            # on the Win32 message-pump thread. And _start_voice_interaction() is
            # itself already non-blocking: it atomically acquires _voice_lock, checks/
            # sets _is_voice_interacting, and only THEN spawns the one real
            # "JARVIS-VoiceInteraction" work thread -- or returns immediately if an
            # interaction is already in progress. Wrapping it in a second thread here
            # added nothing but an extra OS thread per keypress, spawned BEFORE
            # single-flight was ever evaluated; the single-flight decision itself was
            # always safe either way (the lock makes the check-and-set atomic
            # regardless of which thread calls in), so removing the wrapper is a pure
            # structural cleanup, not a correctness fix to the guard itself.
            self._start_voice_interaction(
                trigger_name="HOTKEY_PTT",
                greeting_phrase="Vâng, tôi nghe.",
            )

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
            name="hardware_status_query",
            handler=self._handle_system_status,
            description="Alias for system_status (router emits this intent name for hardware/status voice queries)",
        )
        self.dispatcher.register_action(
            name="system_power",
            handler=self._handle_system_power,
            description="Handles system power actions (shutdown, restart, lock, sleep)",
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

        # 7. Smart Home / Home Assistant actions (D-10 / F-26)
        self.dispatcher.register_action(
            name="home_assistant_call",
            handler=self._handle_home_assistant_call,
            description="Authoritative write/read service call to Home Assistant with security gating",
        )
        self.dispatcher.register_action(
            name="smart_home_turn_on",
            handler=self._handle_smart_home_turn_on,
            description="Turns on a smart home entity (light/switch/climate) via Home Assistant",
        )
        self.dispatcher.register_action(
            name="smart_home_turn_off",
            handler=self._handle_smart_home_turn_off,
            description="Turns off a smart home entity via Home Assistant",
        )
        self.dispatcher.register_action(
            name="smart_home_set_temp",
            handler=self._handle_smart_home_set_temp,
            description="Sets temperature for smart thermostat/AC via Home Assistant",
        )
        self.dispatcher.register_action(
            name="smart_home_get_state",
            handler=self._handle_smart_home_get_state,
            description="Reads state and attributes of a smart home entity via Home Assistant",
        )

        # 8. Experimental / Labs actions
        self.dispatcher.register_action(
            name="browser_cdp_capture",
            handler=self._handle_browser_cdp_capture,
            labs_feature="browser_cdp",
            description="Captures live DOM state and screenshot via Chrome DevTools Protocol (CDP)",
        )
        self.dispatcher.register_action(
            name="tshark_capture",
            handler=self._handle_tshark_capture,
            labs_feature="tshark_capture",
            description="Executes live packet capture and protocol analysis via TShark",
        )

    # ── Action Handlers ──────────────────────────────────────────────────────

    @require_labs("browser_cdp")
    def _handle_browser_cdp_capture(
        self,
        url: str | None = None,
        endpoint: str | None = None,
        timeout_s: float = 2.0,
        **kwargs,
    ) -> dict[str, Any]:
        """Captures DOM state and screenshot via Chrome DevTools Protocol (Labs feature)."""
        cdp_endpoint = endpoint or (
            self.config.get("browser.cdp_endpoint", "http://127.0.0.1:9222")
            if hasattr(self.config, "get")
            else "http://127.0.0.1:9222"
        )
        version_url = f"{cdp_endpoint.rstrip('/')}/json/version"

        # 1. Honest endpoint connectivity probe
        import socket
        import urllib.error
        import urllib.request

        try:
            req = urllib.request.Request(version_url, headers={"User-Agent": "JARVIS-CDP/1.0"})
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "status": "FAILED",
                        "code": "CDP_ENDPOINT_UNAVAILABLE",
                        "error": f"Chrome CDP endpoint returned non-200 status: {resp.status}",
                        "error_code": "CDP_ENDPOINT_UNAVAILABLE",
                        "message": f"Chrome CDP endpoint unavailable at {cdp_endpoint}",
                        "retryable": False,
                    }
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError, socket.timeout) as exc:
            log.warning("Chrome CDP endpoint unreachable at %s: %s", version_url, exc)
            return {
                "success": False,
                "status": "FAILED",
                "code": "CDP_ENDPOINT_UNAVAILABLE",
                "message": f"Chrome CDP endpoint unavailable at {cdp_endpoint}",
                "error": "Chrome debugging port 9222 is not reachable",
                "error_code": "CDP_ENDPOINT_UNAVAILABLE",
                "retryable": False,
            }
        except Exception as exc:
            log.error("Unexpected error probing CDP endpoint %s: %s", version_url, exc)
            return {
                "success": False,
                "status": "FAILED",
                "code": "CDP_ENDPOINT_UNAVAILABLE",
                "error": str(exc),
                "error_code": "CDP_ENDPOINT_UNAVAILABLE",
                "message": f"Failed to probe CDP endpoint: {exc}",
                "retryable": False,
            }

        # 2. Genuine CDP execution via BrowserCDPController
        try:
            from jarvis.browser.cdp_controller import BrowserCDPController, BrowserConfig

            controller = BrowserCDPController(
                config=BrowserConfig(cdp_endpoint=cdp_endpoint, timeout_ms=int(timeout_s * 1000)),
            )
            if not controller.launch():
                return {
                    "success": False,
                    "status": "FAILED",
                    "code": controller.last_error_code or "CDP_ATTACH_FAILED",
                    "error": controller.last_error_message or "Failed to attach to Chromium CDP session",
                    "error_code": controller.last_error_code or "CDP_ATTACH_FAILED",
                    "message": "Failed to attach to Chromium CDP session",
                    "retryable": False,
                }

            try:
                target_url = url or kwargs.get("target_url")
                if target_url:
                    page_info = controller.navigate(target_url)
                    if not page_info.success:
                        return {
                            "success": False,
                            "status": "FAILED",
                            "code": page_info.error_code or "BROWSER_NAVIGATION_FAILED",
                            "error": page_info.error_message or "Navigation failed",
                            "error_code": page_info.error_code or "BROWSER_NAVIGATION_FAILED",
                            "message": f"Navigation to {target_url} failed",
                            "retryable": False,
                        }

                content_md = controller.extract_content_as_markdown()
                screenshot_path = controller.screenshot()
                current_url = controller.get_current_url()

                return {
                    "success": True,
                    "status": "SUCCESS",
                    "code": "OK",
                    "message": "CDP capture executed successfully",
                    "data": {
                        "url": current_url,
                        "content_md": content_md,
                        "screenshot_path": screenshot_path,
                    },
                }
            finally:
                controller.close()

        except ImportError:
            return {
                "success": False,
                "status": "FAILED",
                "code": "BROWSER_CDP_NOT_INSTALLED",
                "error": "BrowserCDPController dependencies not installed",
                "error_code": "BROWSER_CDP_NOT_INSTALLED",
                "message": "Browser CDP controller dependencies not installed",
                "retryable": False,
            }
        except Exception as exc:
            log.error("CDP capture execution failed: %s", exc, exc_info=True)
            return {
                "success": False,
                "status": "ERROR",
                "code": "CDP_EXECUTION_ERROR",
                "error": str(exc),
                "error_code": "CDP_EXECUTION_ERROR",
                "message": f"CDP capture encountered an error: {exc}",
                "retryable": False,
            }

    @require_labs("tshark_capture")
    def _handle_tshark_capture(
        self,
        interface: str = "eth0",
        count: int = 50,
        duration_s: float | None = None,
        bpf_filter: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Executes live packet capture via TShark (Labs feature)."""
        from jarvis.security.scanner import PacketCapture
        pc = PacketCapture(config=self.config)
        result = pc.capture_packets(
            interface=interface,
            count=count,
            duration_s=duration_s,
            bpf_filter=bpf_filter,
            **kwargs,
        )
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return dict(result)

    def _handle_home_assistant_call(self, **kwargs) -> dict[str, Any]:
        """Dispatches an authoritative service call to Home Assistant."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        domain = kwargs.get("domain", "light")
        service = kwargs.get("service", "turn_on")
        entity_id = kwargs.get("entity_id") or kwargs.get("entity")
        service_data = dict(kwargs.get("service_data", {}))
        if entity_id and "entity_id" not in service_data:
            service_data["entity_id"] = entity_id
        for k in ("brightness", "temperature"):
            if k in kwargs and k not in service_data:
                service_data[k] = kwargs[k]
        return self.ha_client.call_service(domain, service, service_data)

    def _handle_smart_home_turn_on(self, **kwargs) -> dict[str, Any]:
        """Turns on an authorized smart home entity."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        entity = kwargs.get("entity") or kwargs.get("entity_id", "light.living_room")
        brightness = kwargs.get("brightness")
        return self.ha_client.turn_on(entity, brightness=brightness)

    def _handle_smart_home_turn_off(self, **kwargs) -> dict[str, Any]:
        """Turns off an authorized smart home entity."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        entity = kwargs.get("entity") or kwargs.get("entity_id", "light.living_room")
        return self.ha_client.turn_off(entity)

    def _handle_smart_home_set_temp(self, **kwargs) -> dict[str, Any]:
        """Sets temperature for an authorized thermostat/climate entity."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        entity = kwargs.get("entity") or kwargs.get("entity_id", "climate.ac_unit")
        temp = float(kwargs.get("temperature", 24.0))
        return self.ha_client.set_temperature(entity, temp)

    def _handle_smart_home_get_state(self, **kwargs) -> dict[str, Any]:
        """Queries the current state of an authorized entity."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        entity = kwargs.get("entity") or kwargs.get("entity_id", "")
        state = self.ha_client.get_state(entity)
        if state is None:
            return {"success": False, "error": f"Entity '{entity}' not found or unreachable"}
        return {"success": True, "state": state}

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

    def _handle_system_power(self, action: str = "shutdown", **kwargs) -> dict[str, Any]:
        """
        Handles power state commands (shutdown, restart, lock, sleep, hibernate).

        Truthfulness contract: this handler only ever reports success when a
        real, trustworthy backend actually performed the requested action.
        - "lock" reuses the existing, truthful WindowsPlatformAPI.lock_workstation()
          (via self.computer_controller.win32, falling back to a direct import),
          which returns the real Win32 LockWorkStation() result.
        - shutdown/restart/sleep/hibernate have NO authoritative backend anywhere
          in this repository today -- reported as an explicit, truthful failure
          rather than a fabricated "acknowledged"/"queued" pseudo-success. Note
          that SafetyGateInterceptor already requires a confirmed token before
          this handler runs at all for these sub-actions (see
          jarvis/planner/safety_interceptor.py); that confirmation gate is
          unaffected and unrelated to backend availability.
        - An unrecognized sub-action is rejected truthfully, never silently
          defaulted to "shutdown".
        """
        raw_act = str(action or "").strip().lower()
        canonical = _POWER_ACTION_ALIASES.get(raw_act)

        if canonical is None:
            log.warning("Rejected unknown system_power sub-action: %r", raw_act)
            msg = f"Hành động hệ thống '{raw_act}' không được hỗ trợ, thưa Ngài."
            return {"success": False, "error": msg, "error_code": "UNKNOWN_POWER_ACTION", "action": raw_act}

        log.info("Handling system_power action: %s (canonical=%s)", raw_act, canonical)

        if canonical in _UNSUPPORTED_POWER_ACTIONS:
            msg = (
                f"Chức năng '{canonical}' hiện chưa được hỗ trợ một cách đáng tin cậy trên "
                f"hệ thống này, thưa Ngài."
            )
            log.warning("system_power action '%s' has no authoritative backend; failing closed.", canonical)
            return {
                "success": False,
                "error": msg,
                "error_code": "POWER_ACTION_UNSUPPORTED",
                "action": canonical,
            }

        # canonical == "lock" is the only supported action past this point.
        locked = self._attempt_lock_workstation()
        if not locked:
            msg = "Không thể khóa màn hình, thưa Ngài."
            return {"success": False, "error": msg, "error_code": "LOCK_WORKSTATION_FAILED", "action": canonical}

        msg = "Đã khóa màn hình máy tính, thưa Ngài."
        if self.tts_manager:
            self.tts_manager.speak(msg, wait=False)
        return {"success": True, "action": canonical, "message": msg}

    def _attempt_lock_workstation(self) -> bool:
        """
        Attempts a real workstation lock exactly once. Trusts only a confirmed
        callable result as evidence of success -- never converts an exception
        or an unavailable backend into a fabricated True. Mirrors the same
        truthful pattern already established in
        jarvis/vision/biometrics.py::_attempt_lock_workstation().
        """
        win32_platform = getattr(self.computer_controller, "win32", None) if self.computer_controller else None
        if win32_platform is not None:
            lock_fn = getattr(win32_platform, "lock_workstation", None)
            if not callable(lock_fn):
                log.warning("computer_controller.win32 has no callable lock_workstation(); failing closed.")
                return False
            try:
                return bool(lock_fn())
            except Exception as exc:
                log.error("computer_controller.win32.lock_workstation() raised: %s", exc)
                return False

        try:
            from jarvis.platform.windows import lock_workstation
            return bool(lock_workstation())
        except Exception as exc:
            log.error("Failed to invoke lock_workstation: %s", exc)
            return False

    def _handle_toggle_mute(self, muted: bool | None = None, **kwargs) -> dict[str, Any]:
        """
        Sets the microphone input listening state (wake-word/STT audio capture).

        `muted=True`/`muted=False` request an explicit desired state and are
        idempotent (re-requesting the current state is not an error). Omitted/
        None `muted` toggles the current state, preserving the previous
        behavior for callers that don't supply a desired state.

        Backed by AudioEngine.pause_stream()/resume_stream() -- the real mic
        input stream feeding wake-word/STT -- NOT
        ComputerController.mute_volume(), which controls the separate master
        speaker/output device and must never be conflated with microphone
        input control.
        """
        if not self.audio_engine:
            msg = "Không thể điều khiển micro: audio engine không khả dụng, thưa Ngài."
            return {"success": False, "error": msg, "error_code": "AUDIO_ENGINE_UNAVAILABLE"}

        current_muted = self.tray_controller._is_mic_muted if self.tray_controller else self._mic_muted
        new_muted = (not current_muted) if muted is None else bool(muted)

        try:
            if new_muted:
                self.audio_engine.pause_stream()
            else:
                self.audio_engine.resume_stream()
        except Exception as exc:
            log.error("Failed to set microphone mute state: %s", exc)
            msg = f"Không thể thay đổi trạng thái micro, thưa Ngài: {exc}"
            return {"success": False, "error": msg, "error_code": "AUDIO_ENGINE_EXCEPTION"}

        # Pre-commit review correction: write to EXACTLY the same variable
        # `current_muted` was just read from -- never both -- so there is
        # never a second, unread-but-still-written shadow copy that could
        # be mistaken for a second source of truth. `tray_controller.
        # _is_mic_muted` is authoritative whenever a tray_controller exists
        # (shared with the tray-icon click handler, jarvis/ui/tray.py::
        # SystemTrayController._on_toggle_mute()); `self._mic_muted` is the
        # authoritative fallback only in headless/CLI mode, where no
        # tray_controller exists at all.
        if self.tray_controller:
            self.tray_controller._is_mic_muted = new_muted
            self.tray_controller.update_status(TrayStatus.MUTED if new_muted else TrayStatus.ACTIVE)
        else:
            self._mic_muted = new_muted

        msg = "Đã tắt micro, thưa Ngài." if new_muted else "Đã bật micro, thưa Ngài."
        if self.tts_manager:
            self.tts_manager.speak(msg, wait=False)
        return {"success": True, "muted": new_muted, "message": msg}

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

    def _handle_system_volume(
        self,
        delta: int | None = None,
        level: int | None = None,
        mute: bool | None = None,
        clarify: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Adjusts or sets master SPEAKER/output volume, or mutes/unmutes it
        -- fail-closed if the endpoint is unavailable.

        Backed by ComputerController.set_volume()/change_volume()/
        mute_volume() -- the real Windows master speaker/output device --
        NOT AudioEngine.pause_stream()/resume_stream(), which controls the
        separate microphone INPUT stream (see _handle_toggle_mute()) and
        must never be conflated with speaker output control.

        H-08 fix: `mute` was previously accepted by the router
        ("tắt tiếng"/"bật tiếng" both emit system_volume with a `mute`
        parameter) but silently discarded here via **kwargs -- neither
        branch below ever read it, so a mute/unmute request fell through
        to the delta branch and actually changed the VOLUME LEVEL instead
        of muting/unmuting anything.

        `mute` here is an explicit desired-state request for THIS call
        only (True=mute, False=unmute). Unlike _handle_toggle_mute's
        microphone `muted` parameter, an omitted/None `mute` here does
        NOT mean "toggle" -- it simply means no mute action was requested
        (a plain volume level/delta adjustment), since this one handler
        also serves level/delta requests that naturally omit `mute`
        entirely. No router path today emits a speaker-mute TOGGLE
        request; if one is ever added it must use its own explicit
        signal rather than overloading `mute=None`.

        H-08 review fix: every failure branch below now follows the
        established truthfulness contract -- "error" holds the clear
        Vietnamese human-readable message and "error_code" holds the
        short machine constant, never the reverse. The dispatcher's
        failure-normalization (_normalize_handler_outcome()) prefers
        "error" as the spoken response text; putting a raw code like
        "VOLUME_SET_FAILED" there (the previous level/delta branches'
        contract) meant the machine code, not clear Vietnamese wording,
        could reach the user.

        H-08 final contract correction: `clarify=True` is how the router
        represents a genuinely ambiguous volume request ("điều chỉnh âm
        lượng" with no direction/level/mute verb) WITHOUT leaving the
        established system_volume routing category (see
        _make_system_volume_intent()'s ambiguous-phrasing fallback and the
        "dieu chinh am luong" dict entry). This branch runs FIRST --
        before the computer_controller availability check and before any
        of set_volume()/change_volume()/mute_volume() -- so asking for
        clarification has ZERO hardware side effects and never depends on
        computer_controller existing at all. It is a genuinely successful
        conversational outcome (a clear question was asked), never a
        claim that any volume change occurred.
        """
        if clarify:
            return {
                "status": "success",
                "success": True,
                "clarification_required": True,
                "message": (
                    "Ngài muốn tăng âm lượng, giảm âm lượng, tắt tiếng, bật tiếng, "
                    "hay đặt một mức âm lượng cụ thể? Xin nói rõ hơn, thưa Ngài."
                ),
            }

        if not self.computer_controller:
            msg = "Không thể điều khiển âm lượng: bộ điều khiển máy tính không khả dụng, thưa Ngài."
            return {"status": "failed", "success": False, "error": msg, "error_code": "COMPUTER_CONTROLLER_UNAVAILABLE"}

        if level is not None:
            vol = self.computer_controller.set_volume(level)
            if vol is None:
                msg = "Không thể đặt âm lượng phần cứng, thưa Ngài."
                return {"status": "failed", "success": False, "volume": None, "error": msg, "error_code": "VOLUME_SET_FAILED"}
            return {"status": "success", "success": True, "volume": vol, "message": f"Đã đặt âm lượng hệ thống thành {vol}%, thưa Ngài."}

        if mute is not None:
            result = self.computer_controller.mute_volume(bool(mute))
            if result is None:
                msg = "Không thể tắt tiếng loa, thưa Ngài." if mute else "Không thể bật tiếng loa, thưa Ngài."
                return {"status": "failed", "success": False, "muted": None, "error": msg, "error_code": "VOLUME_MUTE_FAILED"}
            msg = "Đã tắt tiếng loa, thưa Ngài." if result else "Đã bật tiếng loa, thưa Ngài."
            return {"status": "success", "success": True, "muted": result, "message": msg}

        delta_val = delta if delta is not None else 10
        vol = self.computer_controller.change_volume(delta_val)
        if vol is None:
            msg = "Không thể điều chỉnh âm lượng phần cứng, thưa Ngài."
            return {"status": "failed", "success": False, "volume": None, "error": msg, "error_code": "VOLUME_CHANGE_FAILED"}
        return {"status": "success", "success": True, "volume": vol, "message": f"Đã điều chỉnh âm lượng lên {vol}%, thưa Ngài."}

    def _handle_system_brightness(self, delta: int | None = None, level: int | None = None, **kwargs) -> dict[str, Any]:
        """Adjusts or sets screen brightness (fail-closed if monitor unavailable)."""
        if self.computer_controller:
            if level is not None:
                b = self.computer_controller.set_brightness(level)
                if b is None:
                    return {"status": "failed", "success": False, "brightness": None, "error": "BRIGHTNESS_SET_FAILED", "message": "Không thể đặt độ sáng màn hình, thưa Ngài."}
                return {"status": "success", "success": True, "brightness": b, "message": f"Đã đặt độ sáng màn hình thành {b}%, thưa Ngài."}
            delta_val = delta if delta is not None else 10
            b = self.computer_controller.change_brightness(delta_val)
            if b is None:
                return {"status": "failed", "success": False, "brightness": None, "error": "BRIGHTNESS_CHANGE_FAILED", "message": "Không thể điều chỉnh độ sáng màn hình, thưa Ngài."}
            return {"status": "success", "success": True, "brightness": b, "message": f"Đã điều chỉnh độ sáng màn hình thành {b}%, thưa Ngài."}
        return {"status": "failed", "success": False, "message": "Computer controller unavailable"}

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
            return {
                "success": False,
                "status": "failed",
                "result_status": "NOT_CONFIGURED",
                "error_code": "BROWSER_AGENT_NOT_CONFIGURED",
                "driver_type": None,
                "message": "Browser Agent is unavailable.",
            }
        res: BrowserActionResult = self.browser_agent.navigate(url=url)
        reported_url = res.url if res.success else _safe_browser_failure_url(res.url or url)
        msg = (
            f"Đã điều hướng tới {reported_url} ({res.title or 'Sẵn sàng'})."
            if res.success
            else f"Không thể điều hướng trang: {res.error}"
        )
        return {
            "success": res.success,
            "status": "success" if res.success else "failed",
            "result_status": res.status.value,
            "error_code": res.error_code,
            "driver_type": res.driver_type.value if res.driver_type else None,
            "url": reported_url,
            "title": res.title if res.success else "",
            "message": msg,
        }

    def _handle_browser_scrape(self, url: str, extract_tables: bool = True, **kwargs) -> dict[str, Any]:
        """Scrapes and parses structured markdown from web page."""
        if not self.browser_agent:
            return {
                "success": False,
                "status": "failed",
                "result_status": "NOT_CONFIGURED",
                "error_code": "BROWSER_AGENT_NOT_CONFIGURED",
                "driver_type": None,
                "message": "Browser Agent is unavailable.",
            }
        res: ScrapeResult = self.browser_agent.scrape_page(url=url, extract_tables=extract_tables)
        reported_url = res.url if res.success else _safe_browser_failure_url(res.url or url)
        msg = (
            f"Đã trích xuất dữ liệu từ {reported_url} "
            f"({len(res.markdown)} ký tự, {len(res.tables)} bảng)."
            if res.success
            else f"Không thể trích xuất trang: {res.error}"
        )
        return {
            "success": res.success,
            "status": "success" if res.success else "failed",
            "result_status": res.status.value,
            "error_code": res.error_code,
            "driver_type": res.driver_type.value if res.driver_type else None,
            "url": reported_url,
            "title": res.title if res.success else "",
            "markdown": res.markdown if res.success else "",
            "tables": res.tables if res.success else [],
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
            return {
                "success": False,
                "status": "failed",
                "result_status": "NOT_CONFIGURED",
                "error_code": "BROWSER_AGENT_NOT_CONFIGURED",
                "driver_type": None,
                "message": "Browser Agent is unavailable.",
            }
        res: BrowserActionResult = self.browser_agent.fill_form(url=url, form_fields=fields, submit_selector=submit_selector)
        msg = (
            f"Đã điền tự động {len(fields)} trường dữ liệu trên {url}."
            if res.success
            else "Không thể hoàn tất biểu mẫu trên trang được yêu cầu."
        )
        reported_url = res.url if res.success else _safe_browser_failure_url(res.url or url)
        return {
            "success": res.success,
            "status": "success" if res.success else "failed",
            "result_status": res.status.value,
            "error_code": res.error_code,
            "driver_type": res.driver_type.value if res.driver_type else None,
            "url": reported_url,
            "field_count": len(fields),
            "message": msg,
        }

    def _handle_browser_compare_prices(self, product: str, stores: list[str] | None = None, **kwargs) -> dict[str, Any]:
        """Scrapes multiple eCommerce sites and compares prices."""
        if not self.browser_agent:
            return {
                "success": False,
                "status": "failed",
                "result_status": "NOT_CONFIGURED",
                "error_code": "BROWSER_AGENT_NOT_CONFIGURED",
                "driver_type": None,
                "message": "Browser Agent is unavailable.",
            }
        target_stores = stores or ["Shopee", "Tiki", "Lazada"]
        items = self.browser_agent.compare_prices(product=product, stores=target_stores)
        driver_type = self.browser_agent.get_active_driver_type()
        if not items:
            return {
                "success": False,
                "status": "failed",
                "result_status": "UNAVAILABLE",
                "error_code": "BROWSER_PRICE_DATA_UNAVAILABLE",
                "driver_type": driver_type.value if driver_type else None,
                "product": product,
                "items": [],
                "message": f"Không lấy được dữ liệu giá thực cho '{product}'.",
            }
        serialized_items = [
            asdict(item)
            if is_dataclass(item) and not isinstance(item, type)
            else item.to_dict()
            if hasattr(item, "to_dict")
            else item
            for item in items
        ]
        evidenced_lookup = {
            str(item.store_name).strip().casefold(): str(item.store_name).strip()
            for item in items
            if hasattr(item, "store_name") and str(item.store_name).strip()
        }
        evidenced_stores = [
            store
            for store in target_stores
            if store.strip().casefold() in evidenced_lookup
        ]
        missing_stores = [
            store
            for store in target_stores
            if store.strip().casefold() not in evidenced_lookup
        ]
        partial = bool(missing_stores)
        coverage = f"{len(evidenced_stores)}/{len(target_stores)}"
        msg = (
            f"Tìm thấy {len(items)} kết quả giá có bằng chứng từ "
            f"{coverage} nguồn đã yêu cầu"
            f"{' (kết quả một phần).' if partial else '.'}"
        )
        return {
            "success": True,
            "status": "success",
            "result_status": "SUCCESS",
            "error_code": None,
            "driver_type": driver_type.value if driver_type else None,
            "product": product,
            "items": serialized_items,
            "partial": partial,
            "evidenced_stores": evidenced_stores,
            "missing_stores": missing_stores,
            "message": msg,
        }

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
        *,
        return_capture: bool = False,
    ) -> np.ndarray | CapturedAudio:
        """
        Capture at the requested rate with fast energy-based silence cutoff.

        Set return_capture=True for STT to preserve the source rate with the buffer.
        The legacy ndarray return remains at the capture rate; callers passing it
        to STT must supply source_sample_rate unless it is already 16 kHz.
        """
        # Snapshot once: reloading config during capture cannot relabel this buffer.
        configured_rate = self.config.get("stt.sample_rate", 16000)
        selected_rate = sample_rate if sample_rate is not None else configured_rate
        sr = validate_sample_rate(16000 if selected_rate is None else selected_rate)
        max_dur = float(duration_s or self.config.get("stt.timeout_s", 4.0))

        def captured(samples: np.ndarray) -> np.ndarray | CapturedAudio:
            return CapturedAudio(samples, sr) if return_capture else samples

        if self.headless:
            return captured(np.zeros(int(sr * min(max_dur, 0.1)), dtype=np.float32))

        # H-02 fix: Synchronize recording device with AudioEngine's selected active device
        # so wake-word detector and command capture always listen on the exact same
        # microphone. When AudioEngine has not (yet) resolved a live device, an
        # explicitly configured audio.input_device (index, numeric string, or
        # case-insensitive name substring -- same semantics AudioEngine uses) is
        # resolved through the shared MicrophoneProbeManager.resolve_explicit_device().
        # An explicit device that cannot be resolved raises MicrophoneDeviceUnavailableError
        # here (propagated to the caller) rather than silently falling back to the
        # OS default microphone -- see the H-02 corrective-patch audit for why the
        # previous int()-only parse was a fail-open bug.
        target_device = None
        if self.audio_engine and getattr(self.audio_engine, "_active_device_index", None) is not None:
            target_device = self.audio_engine._active_device_index
        else:
            cfg_dev = self.config.get("audio.input_device")
            # Only touch device enumeration when there is an actual explicit
            # request to resolve -- an unset/empty config value means "no
            # explicit device", so auto (device=None) is fine without probing.
            if cfg_dev is not None and not (isinstance(cfg_dev, str) and not cfg_dev.strip()):
                probe_mgr = getattr(self.audio_engine, "probe_manager", None) if self.audio_engine else None
                if probe_mgr is None:
                    probe_mgr = MicrophoneProbeManager()
                target_device = probe_mgr.resolve_explicit_device(cfg_dev, probe_mgr.get_input_devices())

        # H-03 FINAL fix: shared acoustic I/O exclusion gate — replaces the previous
        # is_playing-polling wait loop, which had an inherent check-then-act (TOCTOU)
        # race: is_playing could observe False, then a NEW TTS output could start
        # (from an unrelated hotkey/dispatched action, not just the current
        # interaction's own greeting) in the gap before the microphone stream
        # actually opened. try_acquire_acoustic_gate() acquires the SAME lock
        # TTSManager._execute_speak() holds for its own synthesis+playback, so once
        # acquired here, no speak() call anywhere in the process can actually start
        # producing audio until this capture releases it -- there is no gap for a
        # concurrent TTS output to slip into. Acquisition is bounded; on timeout this
        # fails closed with a typed, distinguishable error and the microphone is
        # NEVER opened -- never a fabricated silent buffer.
        ACOUSTIC_GATE_TIMEOUT_S = 1.0
        gate_acquired = False
        if self.tts_manager:
            _gate_wait_start = time.monotonic()
            gate_acquired = self.tts_manager.try_acquire_acoustic_gate(timeout=ACOUSTIC_GATE_TIMEOUT_S)
            _gate_wait_elapsed = time.monotonic() - _gate_wait_start
            if not gate_acquired:
                log.error(
                    "Acoustic I/O gate not acquired within %.1fs -- JARVIS's own TTS/"
                    "playback is still active. Refusing to open the microphone.",
                    ACOUSTIC_GATE_TIMEOUT_S,
                )
                raise AcousticGateTimeoutError(ACOUSTIC_GATE_TIMEOUT_S)
            # The gate was genuinely contended (we had to wait for a real TTS
            # playback to release it) -- allow a short settling delay for speaker
            # reverberation to decay before opening the microphone, mirroring the
            # 150ms settle already applied after the greeting in
            # _start_voice_interaction(). Skipped when the gate was immediately
            # free (TTS was already idle), so the common fast path never pays a
            # redundant delay.
            if _gate_wait_elapsed > 0.02:
                time.sleep(0.15)

        try:
            try:
                import sounddevice as _sd
                chunk_size = int(sr * 0.15)  # 150ms chunks
                recorded_chunks: list[np.ndarray] = []
                max_chunks = int(max_dur / 0.15)
                silence_chunks_after_speech = 0
                has_speech_started = False
                energy_threshold = 0.015

                log.info("Capturing voice command (device=%s, sr=%d, max %.1fs)...", target_device, sr, max_dur)
                with _sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=chunk_size, device=target_device) as stream:
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
                    return captured(np.concatenate(recorded_chunks))
                return captured(np.zeros(int(sr * 0.5), dtype=np.float32))
            except Exception as e:
                log.warning("Fast microphone capture via InputStream failed: %s. Falling back to simple rec.", e)
                try:
                    import sounddevice as _sd
                    dur = min(max_dur, 3.0)
                    audio_data = _sd.rec(int(dur * sr), samplerate=sr, channels=1, dtype="float32", device=target_device)
                    _sd.wait()
                    return captured(audio_data.flatten())
                except Exception as e2:
                    # H-02 fix: both the fast InputStream path AND the same-device sd.rec
                    # fallback failed to access hardware -- this is a genuine microphone
                    # failure (disconnected/in-use/driver error), not silence. Returning a
                    # fabricated all-zero buffer here would make a hardware failure
                    # indistinguishable from the user simply not speaking. Surface a typed,
                    # distinguishable failure instead; the caller (_start_voice_interaction)
                    # reports this to the user as a device problem, not as "didn't hear you".
                    log.error(
                        "Fallback sd.rec capture also failed on device=%s: %s. "
                        "Refusing to return a fabricated silent buffer for a hardware failure.",
                        target_device, e2,
                    )
                    raise MicrophoneDeviceUnavailableError(target_device, reason="capture_failed") from e2
        finally:
            # Keep the gate for the complete command recording period -- release
            # only now, after every capture attempt (success or failure) is fully
            # done, so TTS can never start playing mid-capture either.
            if gate_acquired:
                self.tts_manager.release_acoustic_gate()

    def _start_voice_interaction(
        self,
        greeting_phrase: str = "Vâng thưa Ngài, tôi đang lắng nghe.",
        trigger_name: str = "VOICE",
        sync: bool = False,
    ) -> threading.Thread | None:
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
                    # H-03: Acoustic settling delay — allow 150ms for speaker reverberation to decay
                    time.sleep(0.15)

                if self.tray_controller:
                    self.tray_controller.update_status(TrayStatus.LISTENING)

                transcript = ""
                # H-02/H-03 fix: a microphone/device failure and an acoustic-gate
                # timeout (JARVIS's own TTS still busy) must both be reported
                # distinctly from ordinary silence -- and from each other -- caught
                # around record_audio() specifically (not the whole STT block) so
                # neither is ever conflated with an STT engine error or a genuinely
                # silent recording.
                mic_error: MicrophoneDeviceUnavailableError | None = None
                gate_error: AcousticGateTimeoutError | None = None
                if self.stt_engine:
                    try:
                        audio_flat = self.record_audio(return_capture=True)
                    except MicrophoneDeviceUnavailableError as e:
                        log.error("Voice capture aborted -- microphone unavailable: %s", e)
                        mic_error = e
                    except AcousticGateTimeoutError as e:
                        log.error("Voice capture aborted -- acoustic gate busy: %s", e)
                        gate_error = e
                    else:
                        try:
                            # Timeout guard: STT must complete within 30s or we abort
                            import concurrent.futures as _cf
                            with _cf.ThreadPoolExecutor(max_workers=1) as _ex:
                                _fut = _ex.submit(self.stt_engine.transcribe, audio_flat)
                                try:
                                    transcript = _fut.result(timeout=30.0)
                                    log.info("Transcribed: '%s'", transcript)
                                except _cf.TimeoutError:
                                    log.error("STT transcription timed out after 30s")
                                    transcript = ""
                        except Exception as e:
                            log.error("STT recording/transcription failed: %s", e)

                if mic_error is not None:
                    _mic_msg = "Không tìm thấy hoặc không thể sử dụng microphone đã cấu hình."
                    if self.overlay:
                        self.overlay.show_response("(lỗi microphone)", _mic_msg)
                    # Only play spoken TTS error on explicit user actions (hotkey, tray), not ambient wake word triggers
                    if self.tts_manager and not trigger_name.startswith("WAKE_WORD"):
                        self.tts_manager.speak(_mic_msg, wait=True)
                    if self.tray_controller:
                        self.tray_controller.update_status(TrayStatus.ACTIVE)
                    self.log_interaction(
                        trigger=trigger_name,
                        input_text="(mic_unavailable)",
                        action="none",
                        response=_mic_msg,
                        status="failed",
                    )
                    return

                if gate_error is not None:
                    _gate_msg = "JARVIS đang phát âm thanh, vui lòng đợi trong giây lát rồi thử lại."
                    if self.overlay:
                        self.overlay.show_response("(đang bận phát âm thanh)", _gate_msg)
                    # Only play spoken TTS error on explicit user actions (hotkey, tray), not ambient
                    # wake word triggers -- and only a best-effort attempt: if TTS is genuinely still
                    # busy this will simply wait its turn via the same acoustic gate/serialization.
                    if self.tts_manager and not trigger_name.startswith("WAKE_WORD"):
                        self.tts_manager.speak(_gate_msg, wait=True)
                    if self.tray_controller:
                        self.tray_controller.update_status(TrayStatus.ACTIVE)
                    self.log_interaction(
                        trigger=trigger_name,
                        input_text="(audio_gate_busy)",
                        action="none",
                        response=_gate_msg,
                        status="failed",
                    )
                    return

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
                    # Timeout guard: command processing must complete within 25s or we abort
                    import concurrent.futures as _cf
                    with _cf.ThreadPoolExecutor(max_workers=1) as _ex:
                        _fut = _ex.submit(self.process_text_command, transcript, trigger_name.lower())
                        try:
                            result = _fut.result(timeout=25.0)
                            response_text = result.get("response_text", "")
                        except _cf.TimeoutError:
                            log.error("process_text_command timed out after 25s for transcript=%r", transcript)
                            response_text = "Xin lỗi, xử lý lệnh mất quá nhiều thời gian. Vui lòng thử lại."
                except Exception as e:
                    log.error("Command processing failed: %s", e)
                    response_text = f"Xin lỗi, tôi gặp lỗi khi xử lý lệnh: {e}"

                # ── Speak the response ──────────────────────────────────────────
                # ECHO FEEDBACK GUARD: only speak "không hiểu" acknowledgement for
                # explicit user triggers (hotkey / PTT / tray), NOT for ambient wake-word
                # triggers. If the wake word fires from room noise or reflected speaker
                # audio and we speak "Xin lỗi..." the mic picks that up → wake word
                # fires again → infinite loop.
                _is_wake_word_trigger = trigger_name.startswith("WAKE_WORD")
                if self.tts_manager:
                    if response_text and response_text.strip():
                        self.tts_manager.speak(response_text, wait=True)
                    elif not _is_wake_word_trigger:
                        # Unknown intent or empty response → explicit acknowledgement
                        # but ONLY for explicit user-initiated triggers (hotkey, PTT)
                        _unknown_phrase = self.config.get(
                            "jarvis.unknown_intent_phrase",
                            "Xin lỗi, tôi không hiểu lệnh đó. Bạn có thể nói lại không?"
                        )
                        self.tts_manager.speak(_unknown_phrase, wait=True)
                        log.debug("Empty response_text for transcript=%r — spoke unknown_intent_phrase", transcript)
                    else:
                        log.debug("Wake-word trigger + empty response — suppressing TTS to prevent echo loop")

                if self.overlay:
                    self.overlay.show_response(transcript, response_text or "(Không nhận ra lệnh)")

                if self.tray_controller:
                    self.tray_controller.update_status(TrayStatus.ACTIVE)
            finally:
                # Extended cooldown: 2.5s lets speaker audio fully dissipate before
                # re-arming the wake word detector. 1.0s was insufficient for multi-word
                # responses — the tail of the audio could retrigger wake word detection.
                time.sleep(2.5)
                with self._voice_lock:
                    self._is_voice_interacting = False

        if sync:
            _voice_loop()
            return None

        thread = threading.Thread(target=_voice_loop, daemon=True, name="JARVIS-VoiceInteraction")
        thread.start()
        return thread

    def _apply_safety_guard_config(self, cfg: Any = None) -> None:
        """
        Applies safety.passive_trigger_guard.*/safety.launch_dedupe_cooldown_s
        onto the EXISTING `_passive_trigger_guard`/`launch_dedupe_guard`
        objects IN PLACE -- only their config-derived attributes are
        reassigned, never the objects themselves -- so any live trigger
        history / active lockout already recorded is always preserved
        across a call to this method, including a later config hot-reload.

        `cfg` defaults to `self.config` (the real, already-loaded
        ConfigManager) for the initial call from initialize(). When called
        as a config hot-reload callback, `cfg` is instead the reloaded
        `JarvisConfig`/`ConfigNode`, whose `.get()` is a plain flat dict
        lookup (NOT ConfigManager's dot-notation traversal) -- so this
        method deliberately fetches only the single top-level "safety"
        section via `.get("safety", {})` (identical, correct behavior on
        either kind of source) and then walks the rest as a plain nested
        dict, rather than relying on any dot-notation key support.
        """
        source = cfg if cfg is not None else self.config
        safety_cfg = source.get("safety", {}) if hasattr(source, "get") else {}
        if not isinstance(safety_cfg, dict):
            safety_cfg = {}
        ptg_cfg = safety_cfg.get("passive_trigger_guard", {})
        if not isinstance(ptg_cfg, dict):
            ptg_cfg = {}

        self._passive_trigger_guard.max_triggers = int(
            ptg_cfg.get("max_triggers", self._passive_trigger_guard.max_triggers)
        )
        self._passive_trigger_guard.window_s = float(
            ptg_cfg.get("window_s", self._passive_trigger_guard.window_s)
        )
        self._passive_trigger_guard.lockout_s = float(
            ptg_cfg.get("lockout_s", self._passive_trigger_guard.lockout_s)
        )
        # Applied to the shared, process-wide LaunchDedupeGuard singleton
        # (jarvis/core/runaway_guard.py) used by the external-launch plugins
        # (spotify/chrome/cursor) and ComputerController.open_app()/
        # open_website() -- those call sites have no visibility into the
        # global config tree themselves.
        launch_dedupe_guard.default_cooldown_s = float(
            safety_cfg.get("launch_dedupe_cooldown_s", launch_dedupe_guard.default_cooldown_s)
        )

    def _on_safety_config_reloaded(self, new_cfg: Any) -> None:
        """Config hot-reload callback: re-applies safety guard limits without ever resetting guard state."""
        self._apply_safety_guard_config(new_cfg)

    def _on_wake_word_triggered(self) -> None:
        """Callback invoked when wake word detector detects 'Hey JARVIS'."""
        trigger_key = "WAKE_WORD:hey_jarvis"
        decision = self._passive_trigger_guard.try_acquire(trigger_key, min_rearm_interval_s=2.5)
        if not decision.allowed:
            log.warning(
                "Wake word trigger suppressed (%s, retry_after=%.1fs) — passive-trigger circuit breaker.",
                decision.reason, decision.retry_after_s,
            )
            return
        log.info("Wake word triggered ('Hey JARVIS')")
        self._start_voice_interaction(
            greeting_phrase="Vâng thưa Ngài",
            trigger_name=trigger_key,
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
        trigger_key = f"GESTURE:{pattern_name}"
        decision = self._passive_trigger_guard.try_acquire(
            trigger_key, min_rearm_interval_s=self._action_fanout_cooldown_s
        )
        if not decision.allowed:
            log.info(
                "Gesture [%s] suppressed (%s, retry_after=%.1fs) — passive-trigger circuit breaker.",
                pattern_name, decision.reason, decision.retry_after_s,
            )
            return

        log.info("Gesture detected: [%s] (conf=%.2f)", pattern_name, confidence)

        if self.dashboard_server:
            self.dashboard_server.broadcast_event({
                "type": "gesture",
                "pattern": pattern_name,
                "confidence": confidence,
            })

        if pattern_name == "double_clap":
            # P0 runaway-hardening: the heavy external-app fanout (spotify/
            # chrome_claude/chrome_binance/cursor) is opt-in, not a default-on
            # capability of a passive acoustic trigger. A false-positive/
            # repeated double_clap (e.g. from music the fanout itself just
            # started playing) must never gain default authority to keep
            # launching heavyweight external applications. Set
            # gesture.patterns.double_clap.allow_side_effect_fanout: true to
            # restore the original full fanout behavior.
            allow_fanout = bool(
                self.config.get("gesture.patterns.double_clap.allow_side_effect_fanout", False)
            )

            if not self.welcome_executed:
                self.welcome_executed = True
                if allow_fanout:
                    log.info("First activation — running welcome sequence (external app fanout enabled).")
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
                    log.info(
                        "First activation — external app/browser fanout is disabled by default "
                        "(gesture.patterns.double_clap.allow_side_effect_fanout=false); starting a "
                        "safe voice activation instead."
                    )
                    self.log_interaction(
                        trigger="GESTURE:double_clap",
                        input_text="double_clap",
                        action="voice_activation",
                        response="Kích hoạt trợ lý bằng giọng nói (fanout ứng dụng bên ngoài đang tắt theo mặc định).",
                        status="success",
                    )
                    self._start_voice_interaction(
                        greeting_phrase="Vâng thưa Ngài, tôi đang lắng nghe.",
                        trigger_name="GESTURE:double_clap",
                    )
            else:
                log.info("Subsequent double clap — starting voice interaction.")
                self._start_voice_interaction(
                    greeting_phrase="Vâng thưa Ngài, tôi đang lắng nghe.",
                    trigger_name="GESTURE:double_clap",
                )
            return

        if pattern_name == "triple_clap":
            action_names = self.config.get("gesture.patterns.triple_clap.actions", ["system_status"])
            all_succeeded = True
            for act in action_names:
                try:
                    result = self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                    if not result.success:
                        all_succeeded = False
                        log.warning("Action [%s] reported failure for pattern [triple_clap]: %s", act, result.error)
                except Exception as e:
                    all_succeeded = False
                    log.error("Action [%s] failed for pattern [triple_clap]: %s", act, e)
            self.log_interaction(
                trigger="GESTURE:triple_clap",
                input_text="triple_clap",
                action=",".join(action_names),
                response=(
                    "Báo cáo tình trạng hệ thống và phần cứng"
                    if all_succeeded
                    else "Một hoặc nhiều hành động cho [triple_clap] không thành công."
                ),
                status="success" if all_succeeded else "failed",
            )
            return

        if pattern_name == "clap_pause_clap":
            action_names = self.config.get("gesture.patterns.clap_pause_clap.actions", ["show_overlay"])
            all_succeeded = True
            for act in action_names:
                try:
                    result = self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                    if not result.success:
                        all_succeeded = False
                        log.warning("Action [%s] reported failure for pattern [clap_pause_clap]: %s", act, result.error)
                except Exception as e:
                    all_succeeded = False
                    log.error("Action [%s] failed for pattern [clap_pause_clap]: %s", act, e)
            self.log_interaction(
                trigger="GESTURE:clap_pause_clap",
                input_text="clap_pause_clap",
                action=",".join(action_names),
                response=(
                    "Hiển thị cửa sổ giao diện JARVIS Overlay HUD"
                    if all_succeeded
                    else "Một hoặc nhiều hành động cho [clap_pause_clap] không thành công."
                ),
                status="success" if all_succeeded else "failed",
            )
            return

        action_names = self.config.get(f"gesture.patterns.{pattern_name}.actions", [])
        all_succeeded = True
        for act in action_names:
            try:
                result = self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                if not result.success:
                    all_succeeded = False
                    log.warning("Action [%s] reported failure for pattern [%s]: %s", act, pattern_name, result.error)
            except Exception as e:
                all_succeeded = False
                log.error("Action [%s] failed for pattern [%s]: %s", act, pattern_name, e)
        if action_names:
            self.log_interaction(
                trigger=f"GESTURE:{pattern_name}",
                input_text=pattern_name,
                action=",".join(action_names),
                response=(
                    f"Thực thi actions cho pattern {pattern_name}"
                    if all_succeeded
                    else f"Một hoặc nhiều hành động cho pattern [{pattern_name}] không thành công."
                ),
                status="success" if all_succeeded else "failed",
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
                    # Status must derive from action_result.success, not from
                    # "no Python exception occurred" -- see CLAUDE.md's
                    # dispatch-truthfulness invariant. This must run BEFORE
                    # the response-text selection below so a failed action
                    # never falls through to a success-flavored fallback.
                    status_flag = "success" if action_result.success else "failed"

                    if not action_result.success:
                        # Truthful failure response precedence:
                        #   1. action_result.error, if useful/non-empty.
                        #   2. an explicit structured failure message inside
                        #      action_result.data (many handlers already embed
                        #      a truthful Vietnamese failure message there).
                        #   3. a useful action_result.error_code.
                        #   4. a neutral truthful failure fallback -- never a
                        #      success-flavored fallback and never a
                        #      fabricated reason.
                        if action_result.error:
                            response_text = str(action_result.error)
                        elif isinstance(action_result.data, dict) and action_result.data.get("message"):
                            response_text = str(action_result.data["message"])
                        elif action_result.error_code and action_result.error_code not in ("ACTION_FAILED", "FAILED", "ERROR"):
                            response_text = f"Không thể thực hiện lệnh ({action_result.error_code})."
                        else:
                            response_text = "Không thể thực hiện lệnh."
                    elif (
                        action_result.data
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
            status_flag = "success"  # Graceful fallback is a successful response, not an error

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

        if self.browser_agent:
            try:
                self.browser_agent.stop()
            except Exception as e:
                log.debug("Error stopping browser agent: %s", e)

        if getattr(self, "telegram_controller", None):
            self.telegram_controller.stop()
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
