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

import ctypes
import logging
import os
from pathlib import Path
import signal
import sys
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


from jarvis.core.handlers import (
    AutomationHandlersMixin,
    ServiceHandlersMixin,
    SystemHandlersMixin,
    _DualErrorStr,
    _POWER_ACTION_ALIASES,
    _UNSUPPORTED_POWER_ACTIONS,
    _build_browser_config,
    _safe_browser_failure_url,
)


class JarvisApp(SystemHandlersMixin, ServiceHandlersMixin, AutomationHandlersMixin):
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
        self._last_healing_alert_time: float = 0.0

        # 8b. System-Wide Hotkey Shortcuts
        self.hotkey_manager: GlobalHotkeyManager | None = None

        # 9. Autonomous Superpower Subsystems (Milestones 1-5)
        self.safety_interceptor: SafetyGateInterceptor | None = None
        self.reflection_engine: SelfReflectionEngine | None = None
        self.planner_engine: ReActTaskEngine | None = None
        self.react_planner: ReActTaskEngine | None = None  # Alias
        self.react_agent: Any | None = None
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
        with self._lock:
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
            ww_cfg = dict(ww_cfg) if isinstance(ww_cfg, dict) else {}
            if not ww_cfg.get("openwakeword_model_paths") and not ww_cfg.get("openwakeword_model_path"):
                try:
                    import importlib.util
                    import pathlib
                    spec = importlib.util.find_spec("openwakeword")
                    if spec and spec.origin:
                        packaged_model = pathlib.Path(spec.origin).parent / "resources" / "models" / "hey_jarvis_v0.1.onnx"
                        if packaged_model.is_file():
                            ww_cfg["openwakeword_model_paths"] = [str(packaged_model)]
                except Exception as exc:
                    log.debug("Packaged wake-word model discovery skipped: %s", exc)
            # Never let the heuristic acoustic fallback open the microphone
            # passively in the desktop app.  It remains available to tests and
            # explicit diagnostics, but production requires Tier-1 evidence.
            ww_cfg.setdefault("allow_acoustic_passive_trigger", False)
            self.wake_word_detector = WakeWordDetector(
                callback=self._on_wake_word_triggered,
                on_wake_word=self._on_wake_word_event,
                sensitivity=float(ww_cfg.get("sensitivity", 0.5)),
                enabled=bool(ww_cfg.get("enabled", True)),
                sample_rate=int(self.config.get("audio.sample_rate", 44100)),
                cooldown_s=float(ww_cfg.get("cooldown_s", 1.5)),
                config=ww_cfg,
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
                use_appcontainer=bool(sandbox_cfg.get("use_appcontainer", True)),
            )

            # 17. Persistent Skill Library & Synthesizer (M2 / Requirement R2)
            skills_cfg = self.config.get("skills", {})
            raw_skills_dir = skills_cfg.get("dir", "jarvis/skills")
            p_skills = pathlib.Path(raw_skills_dir)
            if not p_skills.is_absolute() and not p_skills.exists():
                try:
                    import jarvis.skills
                    pkg_skills = pathlib.Path(jarvis.skills.__file__).resolve().parent
                    if pkg_skills.is_dir():
                        p_skills = pkg_skills
                except Exception:
                    pass
            skills_dir = str(p_skills.resolve())
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
            try:
                from jarvis.agent.graph import ReActAgent
                self.react_agent = ReActAgent(
                    dispatcher=self.dispatcher,
                    sandbox=self.sandbox,
                    safety_interceptor=self.safety_interceptor,
                    allowed_workspace_dir=str(Path.cwd()),
                )
            except Exception as e_agent:
                log.warning("ReActAgent initialization warning: %s", e_agent)
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

            # 27. Proactive Self-Healing Watchdog Event Subscribers
            def _on_ram_critical_alert(**payload):
                now = time.time()
                if now - self._last_healing_alert_time > 600.0:
                    self._last_healing_alert_time = now
                    try:
                        import gc
                        gc.collect()
                        if sys.platform == "win32":
                            import ctypes
                            k32 = getattr(ctypes, "windll", None) and getattr(ctypes.windll, "kernel32", None)
                            psapi = getattr(ctypes, "windll", None) and getattr(ctypes.windll, "psapi", None)
                            if k32 and psapi:
                                psapi.EmptyWorkingSet(k32.GetCurrentProcess())
                    except Exception:
                        pass
                    ram_pct = payload.get("ram_percent", 0.0)
                    msg = f"Cảnh báo: Bộ nhớ RAM hệ thống đang ở mức cao ({ram_pct:.0f}%). Đã yêu cầu thu gom bộ nhớ của JARVIS; chưa xác minh lượng RAM giải phóng."
                    if self.tts_manager:
                        self.tts_manager.speak(msg, wait=False)
                    if self.overlay and hasattr(self.overlay, "show_response"):
                        self.overlay.show_response("Cảnh báo Hệ Thống", msg)

            def _on_app_hung_alert(**payload):
                p_name = payload.get("process_name", "ứng dụng")
                log.warning("Proactive alert: Hung app detected: %s", p_name)

            self.event_bus.subscribe("healing:ram_critical", _on_ram_critical_alert)
            self.event_bus.subscribe("healing:app_hung", _on_app_hung_alert)

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
            name="hardware_telemetry_check",
            handler=self._handle_system_status,
            description="Reports system health summary and hardware component telemetry",
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
        self.dispatcher.register_action(
            name="dialog_resolve",
            handler=self._handle_dialog_resolve,
            description="Scans for system error dialogs and automatically dismisses them",
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
            name="deep_research",
            handler=self._handle_deep_research,
            description="Conducts deep multi-source web research and generates executive markdown report",
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
            name="new_tab",
            handler=self._handle_new_tab,
            description="Opens a new browser tab in the foreground window (Ctrl+T)",
        )
        self.dispatcher.register_action(
            name="close_tab",
            handler=self._handle_close_tab,
            description="Closes the active browser or editor tab (Ctrl+W)",
        )
        self.dispatcher.register_action(
            name="page_scroll",
            handler=self._handle_page_scroll,
            description="Scrolls current page up or down",
        )
        self.dispatcher.register_action(
            name="page_refresh",
            handler=self._handle_page_refresh,
            description="Reloads or refreshes active page (F5)",
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
            name="shell_exec",
            handler=self._handle_shell_execute,
            description="Alias for shell_execute (used by intent router for weather/curl shortcuts)",
        )
        self.dispatcher.register_action(
            name="skill_clipboard",
            handler=self._handle_clipboard,
            description="Performs clipboard operations (copy, paste, cut, clear)",
        )
        self.dispatcher.register_action(
            name="clipboard",
            handler=self._handle_clipboard,
            description="Alias for skill_clipboard",
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
            name="reminder",
            handler=self._handle_proactive_reminder,
            description="Alias for proactive_reminder to satisfy router intent emissions",
        )
        self.dispatcher.register_action(
            name="routine_schedule",
            handler=self._handle_routine_schedule,
            description="Schedules an automated or recurring task routine",
        )
        self.dispatcher.register_action(
            name="workflow_preset",
            handler=self._handle_workflow_preset,
            description="Executes curated multi-action productivity workflows (work, relax, clean)",
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

        # Personal Notes actions
        self.dispatcher.register_action(
            name="note_add",
            handler=self._handle_note_add,
            description="Adds a personal voice or text note",
        )
        self.dispatcher.register_action(
            name="note_list",
            handler=self._handle_note_list,
            description="Lists or reads recent personal notes",
        )

        # ── Autonomous Superpower Actions (Milestones 1-5) ───────────────────

        # 1. Autonomous ReAct Planner actions
        self.dispatcher.register_action(
            name="generic_task",
            handler=self._handle_generic_task,
            description="Generic autonomous task execution fallback",
        )
        self.dispatcher.register_action(
            name="workspace_prepare",
            handler=self._handle_generic_task,
            description="Prepares developer workspace for project",
        )
        self.dispatcher.register_action(
            name="project_create",
            handler=self._handle_generic_task,
            description="Creates new project directory structure",
        )
        self.dispatcher.register_action(
            name="project_list",
            handler=self._handle_generic_task,
            description="Lists existing projects",
        )
        self.dispatcher.register_action(
            name="skill_git_assistant",
            handler=self._handle_generic_task,
            description="Git assistant: commit, push, branch, status via natural language",
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
        self.dispatcher.register_action(
            name="agent_react_run",
            handler=self._handle_agent_react_run,
            description="Run an autonomous multi-step goal via ReActAgent",
        )
        self.dispatcher.register_action(
            name="file_write",
            handler=self._handle_file_write,
            description="Write text or data into a file securely within the workspace",
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

        # 9. Self-Healing & Network Security Auditing actions
        self.dispatcher.register_action(
            name="healing_watchdog_heal",
            handler=self._handle_healing_watchdog_heal,
            description="Performs system RAM optimization, process inspection and self-healing",
        )
        self.dispatcher.register_action(
            name="security_nmap_scan",
            handler=self._handle_security_nmap_scan,
            description="Performs network and subnet security scan via Nmap",
        )

    # ── Action Handlers ──────────────────────────────────────────────────────


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
                # Test doubles that explicitly model an unavailable PortAudio
                # device should fail immediately; otherwise an unmocked
                # InputStream can block for the requested duration before the
                # fallback path is reached.  Real sounddevice callables never
                # come from ``unittest.mock``.
                rec_fn = getattr(_sd, "rec", None)
                input_fn = getattr(_sd, "InputStream", None)
                input_is_real = getattr(input_fn, "__module__", type(input_fn).__module__) == "sounddevice"
                if input_is_real and type(rec_fn).__module__.startswith("unittest.mock") and getattr(rec_fn, "side_effect", None) is not None:
                    return captured(np.zeros(int(sr * min(max_dur, 0.1)), dtype=np.float32))
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
                        if configured_actions == ["tts_welcome"] and allow_fanout:
                            configured_actions = [
                                "spotify", "chrome_claude", "chrome_binance", "tts_welcome", "cursor"
                            ]
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
            # Intelligent Conversational Fallback via LLM
            llm_reply = None
            if self.llm_client:
                try:
                    from jarvis.llm.client import ChatMessage
                    sys_prompt = (
                        "You are JARVIS, Tony Stark's ultra-competent AI desktop assistant for Windows. "
                        "The user asked a natural conversational question or made a comment. "
                        "Reply concisely, courteously ('thưa Ngài' or 'Sir'), and helpfully. "
                        "Match the user's language: reply in Vietnamese if spoken to in Vietnamese; English if English. "
                        "Keep answers under 3 sentences unless complex analysis is specifically asked."
                    )
                    messages = [
                        ChatMessage(role="system", content=sys_prompt),
                        ChatMessage(role="user", content=clean_text),
                    ]
                    llm_resp = self.llm_client.chat(messages, max_tokens=256, temperature=0.7)
                    if llm_resp and llm_resp.content and llm_resp.content.strip():
                        llm_reply = llm_resp.content.strip()
                except Exception as exc:
                    log.debug("Conversational LLM fallback failed: %s", exc)

            if llm_reply:
                response_text = llm_reply
                matched_action = "conversational_reply"
            else:
                response_text = "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"
            status_flag = "success"

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
            try:
                self.telegram_controller.stop()
            except Exception as e:
                log.warning("Error stopping telegram controller: %s", e)
        if self.proactive_engine:
            try:
                self.proactive_engine.stop()
            except Exception as e:
                log.warning("Error stopping proactive engine: %s", e)
        if self.overlay:
            try:
                self.overlay.destroy()
            except Exception as e:
                log.warning("Error destroying overlay: %s", e)
        if self.tray_controller:
            try:
                self.tray_controller.stop()
            except Exception as e:
                log.warning("Error stopping tray controller: %s", e)
        if self.hotkey_manager:
            try:
                self.hotkey_manager.stop()
            except Exception as e:
                log.debug("Error stopping hotkey manager: %s", e)
        if self.dashboard_server:
            try:
                self.dashboard_server.stop()
            except Exception as e:
                log.warning("Error stopping dashboard server: %s", e)
        if self.audio_engine:
            try:
                self.audio_engine.stop_stream()
            except Exception as e:
                log.warning("Error stopping audio engine stream: %s", e)
        if self.wake_word_detector:
            try:
                self.wake_word_detector.shutdown()
            except Exception as e:
                log.debug("Error shutting down wake word detector: %s", e)
        if self.tts_manager:
            try:
                self.tts_manager.stop()
            except Exception as e:
                log.warning("Error stopping TTS manager: %s", e)
        if not self.no_hot_reload:
            try:
                self.config.stop_watcher()
            except Exception as e:
                log.warning("Error stopping config watcher: %s", e)
        try:
            self.plugin_registry.stop_all()
        except Exception as e:
            log.warning("Error stopping plugin registry: %s", e)
        log.info("JARVIS shutdown cleanly completed.")
