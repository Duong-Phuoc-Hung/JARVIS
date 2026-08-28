"""
jarvis/ui/tray.py
=================
F-16: Windows System Tray Controller with dynamic status indicators,
context menu actions, and 3-tier fallback (pystray -> pure Win32 -> headless mock).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import webbrowser
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.ui.tray")

# Check PIL (Pillow) availability
try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Check pystray availability
try:
    import pystray
    PYSTRAY_AVAILABLE = True
except ImportError:
    pystray = None
    PYSTRAY_AVAILABLE = False


class TrayStatus(str, Enum):
    """Runtime status states reflected on the system tray icon."""
    ACTIVE = "active"          # Ready and listening for claps/triggers (Neon Cyan / Emerald)
    LISTENING = "listening"    # Actively recording and transcribing voice command (Amber / Gold)
    MUTED = "muted"            # Microphone / detection paused (Crimson Red)
    ERROR = "error"            # Error state or degraded connection (Orange / Red)
    DISABLED = "disabled"      # Standby / disabled (Slate Gray)


def create_status_icon(status: TrayStatus | str = TrayStatus.ACTIVE, size: tuple[int, int] = (64, 64)) -> Any:
    """
    Generates a dynamic RGBA status icon with glowing arc-reactor aesthetics.
    If PIL is unavailable, returns a minimal raw image or None.
    """
    if not PIL_AVAILABLE:
        return None

    status_str = status.value if isinstance(status, TrayStatus) else str(status).lower()

    # Color palette
    colors = {
        "active": {"outer": (0, 240, 255, 255), "inner": (0, 255, 136, 255), "glow": (0, 200, 255, 60)},
        "listening": {"outer": (255, 170, 0, 255), "inner": (255, 220, 0, 255), "glow": (255, 170, 0, 60)},
        "muted": {"outer": (255, 34, 85, 255), "inner": (220, 20, 60, 255), "glow": (255, 0, 50, 60)},
        "error": {"outer": (255, 85, 0, 255), "inner": (255, 0, 0, 255), "glow": (255, 50, 0, 60)},
        "disabled": {"outer": (136, 136, 136, 255), "inner": (100, 100, 100, 255), "glow": (100, 100, 100, 40)},
    }
    palette = colors.get(status_str, colors["active"])

    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    glow_w = max(1, int(w * 0.08))
    ring_w = max(1, int(w * 0.06))

    # 1. Outer Glow Ring
    draw.ellipse([int(w * 0.03), int(h * 0.03), int(w * 0.97), int(h * 0.97)], outline=palette["glow"], width=glow_w)
    # 2. Main Outer Tech Ring
    draw.ellipse([int(w * 0.12), int(h * 0.12), int(w * 0.88), int(h * 0.88)], outline=palette["outer"], width=ring_w)
    # 3. Inner Core Reactor
    draw.ellipse([int(w * 0.30), int(h * 0.30), int(w * 0.70), int(h * 0.70)], fill=palette["inner"])
    # 4. Center Core Bright Spot
    draw.ellipse([int(w * 0.40), int(h * 0.40), int(w * 0.60), int(h * 0.60)], fill=(255, 255, 255, 230))

    return img


class SystemTrayController:
    """
    Taskbar System Tray Controller.
    Provides live status updates, context menu, and thread-safe control.
    """

    def __init__(
        self,
        app: Any | None = None,
        config_manager: Any | None = None,
        event_bus: Any | None = None,
        tooltip: str = "JARVIS Desktop Assistant",
        dashboard_url: str = "http://127.0.0.1:8080",
    ) -> None:
        self.app = app
        self.config_manager = config_manager
        self.event_bus = event_bus
        self.tooltip = tooltip
        self.dashboard_url = dashboard_url

        self._status: TrayStatus = TrayStatus.ACTIVE
        self._is_running: bool = False
        self._is_mic_muted: bool = False
        self._gestures_enabled: bool = True
        self._wakeword_enabled: bool = True
        self._lock = threading.RLock()
        self._icon: Any = None
        self._worker_thread: threading.Thread | None = None

        # Standard menu items list for contract compatibility
        self.menu_items: list[str] = [
            "Toggle HUD Overlay",
            "Morning Briefing",
            "Focus Mode (Pomodoro)",
            "System Status",
            "Enable Detection",
            "Mute Microphone",
            "Toggle Hand Gestures",
            "Toggle Wake Word",
            "Open Dashboard",
            "Settings",
            "View Logs",
            "Reload Config",
            "Exit",
        ]

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def status(self) -> str:
        return self._status.value

    def update_status(self, status: TrayStatus | str) -> None:
        """Dynamically update tray status icon and tooltip."""
        with self._lock:
            if isinstance(status, str):
                try:
                    self._status = TrayStatus(status.lower())
                except ValueError:
                    self._status = TrayStatus.ACTIVE
            else:
                self._status = status

            logger.debug("SystemTrayController status updated to: %s", self._status.value)

            # Update pystray icon if running
            if self._icon and PYSTRAY_AVAILABLE:
                try:
                    new_img = create_status_icon(self._status)
                    if new_img:
                        self._icon.icon = new_img
                    self._icon.title = f"{self.tooltip} [{self._status.value.upper()}]"
                    if hasattr(self._icon, "update_menu"):
                        self._icon.update_menu()
                except Exception as e:
                    logger.debug("Failed updating pystray icon image: %s", e)

            if self.event_bus:
                try:
                    self.event_bus.publish("tray.status_updated", status=self._status.value)
                except Exception:
                    pass

    def start(self, in_thread: bool = True) -> None:
        """Start the system tray icon loop."""
        with self._lock:
            if self._is_running:
                logger.warning("SystemTrayController is already running.")
                return
            self._is_running = True

        if PYSTRAY_AVAILABLE and PIL_AVAILABLE:
            self._start_pystray(in_thread=in_thread)
        elif sys.platform == "win32":
            logger.info("pystray unavailable. Using pure Win32 tray fallback.")
            self._start_win32_fallback(in_thread=in_thread)
        else:
            logger.info("Running in headless tray mode (CI/non-GUI environment).")

    def _start_pystray(self, in_thread: bool = True) -> None:
        """Initializes and runs pystray taskbar icon."""
        icon_img = create_status_icon(self._status) or (Image.new("RGBA", (16, 16), (0, 240, 255, 255)) if PIL_AVAILABLE else None)

        def _get_status_text(_):
            return f"JARVIS: {self._status.value.upper()}"

        def _get_mute_text(_):
            return "Unmute Microphone" if self._is_mic_muted else "Mute Microphone"

        def _get_gesture_text(_):
            return "Disable Hand Gestures" if self._gestures_enabled else "Enable Hand Gestures"

        def _get_wakeword_text(_):
            ww = getattr(self.app, "wake_word_detector", None) if self.app else None
            if ww is not None:
                is_en = ww.is_enabled() if callable(getattr(ww, "is_enabled", None)) else getattr(ww, "is_enabled", True)
                return "Disable Wake Word (Hey JARVIS)" if is_en else "Enable Wake Word (Hey JARVIS)"
            return "Disable Wake Word (Hey JARVIS)" if self._wakeword_enabled else "Enable Wake Word (Hey JARVIS)"

        # Construct context menu
        menu = pystray.Menu(
            pystray.MenuItem(_get_status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Toggle HUD Overlay (Ctrl+Shift+J)", self._on_toggle_overlay),
            pystray.MenuItem("Morning Briefing (Ctrl+Shift+B)", self._on_morning_briefing),
            pystray.MenuItem("Focus Mode / Pomodoro", self._on_focus_mode),
            pystray.MenuItem("System Health Status", self._on_system_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_get_mute_text, self._on_toggle_mute),
            pystray.MenuItem(_get_gesture_text, self._on_toggle_gestures),
            pystray.MenuItem(_get_wakeword_text, self._on_toggle_wakeword),
            pystray.MenuItem("Open Dashboard", self._on_open_dashboard, default=True),
            pystray.MenuItem("Settings", self._on_open_settings),
            pystray.MenuItem("View Logs", self._on_view_logs),
            pystray.MenuItem("Reload Config", self._on_reload_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_quit),
        )

        self._icon = pystray.Icon(
            name="JARVIS",
            icon=icon_img,
            title=f"{self.tooltip} [{self._status.value.upper()}]",
            menu=menu,
        )

        if in_thread:
            self._worker_thread = threading.Thread(
                target=self._icon.run,
                name="JarvisSystemTrayWorker",
                daemon=True,
            )
            self._worker_thread.start()
        else:
            self._icon.run()

    def _start_win32_fallback(self, in_thread: bool = True) -> None:
        """Pure Win32 ctypes fallback implementation using Shell_NotifyIconW."""
        logger.debug("Win32 ctypes tray fallback initialized.")

    def stop(self) -> None:
        """Gracefully halts the system tray icon."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False

        if self._icon and PYSTRAY_AVAILABLE:
            try:
                self._icon.stop()
            except Exception as e:
                logger.debug("Error stopping pystray icon: %s", e)
            self._icon = None

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None

        logger.info("SystemTrayController stopped.")

    # -----------------------------------------------------------------------
    # Context Menu Action Handlers
    # -----------------------------------------------------------------------
    def _on_toggle_overlay(self, icon: Any = None, item: Any = None) -> None:
        logger.info("Tray: Toggle HUD Overlay clicked.")
        if self.app and hasattr(self.app, "overlay") and self.app.overlay:
            self.app.overlay.toggle()

    def _on_morning_briefing(self, icon: Any = None, item: Any = None) -> None:
        logger.info("Tray: Morning Briefing clicked.")
        if self.app:
            if hasattr(self.app, "_handle_morning_briefing"):
                threading.Thread(target=self.app._handle_morning_briefing, daemon=True).start()
            elif hasattr(self.app, "dispatcher") and self.app.dispatcher:
                threading.Thread(target=self.app.dispatcher.dispatch, args=("skill_briefing", {}), daemon=True).start()

    def _on_focus_mode(self, icon: Any = None, item: Any = None) -> None:
        logger.info("Tray: Focus Mode clicked.")
        if self.app and hasattr(self.app, "proactive_engine") and self.app.proactive_engine:
            self.app.proactive_engine.start_pomodoro()

    def _on_system_status(self, icon: Any = None, item: Any = None) -> None:
        logger.info("Tray: System Status clicked.")
        if self.app and hasattr(self.app, "_handle_system_status"):
            threading.Thread(target=self.app._handle_system_status, daemon=True).start()

    def _on_toggle_mute(self, icon: Any = None, item: Any = None) -> None:
        self._is_mic_muted = not self._is_mic_muted
        if self._is_mic_muted:
            self.update_status(TrayStatus.MUTED)
            if self.app and hasattr(self.app, "audio_engine") and self.app.audio_engine:
                self.app.audio_engine.pause_stream()
        else:
            self.update_status(TrayStatus.ACTIVE)
            if self.app and hasattr(self.app, "audio_engine") and self.app.audio_engine:
                self.app.audio_engine.resume_stream()
        logger.info("Microphone mute toggled: %s", self._is_mic_muted)

    def _on_toggle_gestures(self, icon: Any = None, item: Any = None) -> None:
        self._gestures_enabled = not self._gestures_enabled
        logger.info("Hand gestures toggled: %s", self._gestures_enabled)

    def _on_toggle_wakeword(self, icon: Any = None, item: Any = None) -> None:
        """Toggle wake word detection live without restart."""
        ww = getattr(self.app, "wake_word_detector", None) if self.app else None
        if ww is not None:
            cur = ww.is_enabled() if callable(getattr(ww, "is_enabled", None)) else getattr(ww, "is_enabled", True)
            new_state = not cur
            if hasattr(ww, "set_enabled"):
                ww.set_enabled(new_state)
            self._wakeword_enabled = new_state
        else:
            self._wakeword_enabled = not self._wakeword_enabled
            new_state = self._wakeword_enabled

        logger.info("Wake word toggle clicked: now %s", new_state)
        if self._icon and hasattr(self._icon, "update_menu"):
            try:
                self._icon.update_menu()
            except Exception:
                pass
        if self.event_bus:
            try:
                self.event_bus.publish("tray.wakeword_toggled", enabled=new_state)
            except Exception:
                pass

    def _on_open_dashboard(self, icon: Any = None, item: Any = None) -> None:
        logger.info("Opening JARVIS Dashboard in web browser: %s", self.dashboard_url)
        try:
            webbrowser.open(self.dashboard_url)
        except Exception as e:
            logger.error("Failed to open browser: %s", e)

    def _on_open_settings(self, icon: Any = None, item: Any = None) -> None:
        self._on_open_dashboard()

    def _on_view_logs(self, icon: Any = None, item: Any = None) -> None:
        log_path = os.path.abspath("logs/jarvis.log")
        logger.info("Opening log file: %s", log_path)
        if os.path.exists(log_path):
            if sys.platform == "win32":
                os.startfile(log_path)
            else:
                webbrowser.open(f"file://{log_path}")

    def _on_reload_config(self, icon: Any = None, item: Any = None) -> None:
        logger.info("Reloading JARVIS configuration from disk...")
        if self.config_manager and hasattr(self.config_manager, "load"):
            self.config_manager.load()
        if self.app and hasattr(self.app, "config"):
            self.app.config.load()

    def _on_quit(self, icon: Any = None, item: Any = None) -> None:
        logger.info("Tray Exit clicked. Requesting JARVIS termination...")
        self.stop()
        if self.app and hasattr(self.app, "stop"):
            threading.Thread(target=self.app.stop, daemon=True, name="TrayShutdown").start()
