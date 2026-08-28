"""
jarvis/ui/overlay.py
====================
JARVIS Always-On Intelligent Overlay HUD (Iron Man Arc Reactor Style).
Milestone 5 (R6 & R8) Enhanced Implementation:
  - AlwaysOnOverlay (with backwards-compatible JarvisOverlay alias).
  - Sidebar Mode: Dockable to right side of screen (380px width, expandable/collapsible to 40px ribbon, draggable, topmost, alpha transparency).
  - 5-Turn Conversation History: Scrollable/stacked card display showing user queries and JARVIS responses for the last 5 turns.
  - Autonomous Task DAG Telemetry: Live visualization of plan goals, steps, dependency graph, and step completion statuses.
  - Live Code Log Streaming: Real-time stdout/stderr log stream display for sandboxed self-coding and script execution.
  - Visual Result Card Rendering: Formatted visual inspection cards for screenshot diffs, OCR bounding boxes, and image artifacts.
  - Quick Action Buttons: Interactive HUD buttons for "Briefing Sáng", "System Status", "Focus Mode", "Tối giản / Thu gọn".
  - Memory Facts Preview: Widget displaying top 3 persistent facts JARVIS remembers about the user.
  - 5s Realtime Status Bar: Live CPU %, RAM %, and Battery % (via Win32 GetSystemPowerStatus / psutil / GlobalMemoryStatusEx) updated on 5s tick.
  - Audio Waveform Spectrum Analyzer: 11-bar Canvas dynamic waveform visualizer animating when JARVIS is listening, thinking, or speaking.
  - Floating Arc Reactor Icon: Minimize mode to a compact floating Arc Reactor icon at screen corner.
  - Thread Safety & Headless Tolerance: All UI mutations scheduled via Tkinter event queue (`root.after`), headless CI environments gracefully handle missing DISPLAY/X11/Win32 GUI.
"""
from __future__ import annotations

import ctypes
import logging
import math
import random
import sys
import threading
import time
import tkinter as tk
from collections import deque
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from tkinter import font as tkfont
from typing import Any

logger = logging.getLogger("jarvis.ui.overlay")


class OverlayState(str, Enum):
    """Lifecycle states of the JARVIS HUD overlay."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    RESPONSE = "response"
    HIDDEN = "hidden"


class OverlayMode(str, Enum):
    """Display layout mode of the JARVIS HUD."""
    SIDEBAR = "sidebar"
    POPUP = "popup"
    ARC_REACTOR = "arc_reactor"


@dataclass
class TurnRecord:
    """Represents a single conversational turn in the 5-turn history queue."""
    user_text: str
    jarvis_text: str
    action: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_text": self.user_text,
            "jarvis_text": self.jarvis_text,
            "action": self.action,
            "timestamp": self.timestamp,
        }


# Iron Man HUD Palette
COLORS: dict[str, str] = {
    "bg": "#0a0e1a",
    "bg_card": "#101827",
    "bg_card_user": "#1a1c29",
    "border": "#00f0ff",
    "border_dim": "#004455",
    "title": "#00f0ff",
    "user_label": "#ffa500",
    "user_text": "#ffe0a0",
    "jarvis_label": "#00f0ff",
    "jarvis_text": "#c0f8ff",
    "status": "#00cc88",
    "status_listening": "#ffa500",
    "status_thinking": "#cc88ff",
    "status_running": "#38bdf8",
    "dot": "#00f0ff",
    "tooltip": "#558899",
    "close_btn": "#666677",
    "btn_bg": "#122030",
    "btn_border": "#007799",
    "btn_fg": "#00f0ff",
    "btn_hover": "#004466",
    "bar_cyan": "#00f0ff",
    "bar_emerald": "#00ff88",
    "bar_amber": "#ffa500",
    "bar_crimson": "#ff3366",
    "arc_core": "#00f0ff",
    "arc_ring": "#007799",
    "arc_glow": "#80ffff",
    "badge_bg": "#0d1b2a",
    "badge_border": "#005577",
    "badge_text": "#a0e8ff",
    "log_stdout": "#a0e8ff",
    "log_stderr": "#ff6b81",
    "dag_pending": "#94a3b8",
    "dag_running": "#38bdf8",
    "dag_completed": "#4ade80",
    "dag_failed": "#f87171",
}

# 10-step gradient from deep warm amber to radiant gold
BREATHING_GRADIENT: list[str] = [
    "#B8860B",  # 0: Dark Goldenrod
    "#C89418",  # 1: Deep Amber
    "#DAA520",  # 2: Goldenrod
    "#E6B800",  # 3: Rich Amber Gold
    "#FFC710",  # 4: Warm Gold
    "#FFD700",  # 5: Pure Gold
    "#FFE042",  # 6: Bright Gold
    "#FFEC8B",  # 7: Light Goldenrod
    "#FFF3B8",  # 8: Pale Glowing Gold
    "#FFF8DC",  # 9: Cornsilk / Luminescent Peak
]

FONT_FAMILY = "Consolas"


def _safe_probe_battery() -> tuple[int | None, bool]:
    """Safely reads system battery percentage and AC charging status."""
    if sys.platform == "win32":
        try:
            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", wintypes.BYTE),
                    ("BatteryFlag", wintypes.BYTE),
                    ("BatteryLifePercent", wintypes.BYTE),
                    ("SystemStatusFlag", wintypes.BYTE),
                    ("BatteryLifeTime", wintypes.DWORD),
                    ("BatteryFullLifeTime", wintypes.DWORD),
                ]
            sps = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
                pct = int(sps.BatteryLifePercent) if sps.BatteryLifePercent <= 100 else None
                charging = bool(sps.ACLineStatus == 1 or (sps.BatteryFlag & 8))
                return pct, charging
        except Exception:
            pass

    try:
        import psutil
        batt = psutil.sensors_battery()
        if batt is not None:
            return int(batt.percent), bool(batt.power_plugged)
    except Exception:
        pass

    return None, False


def _safe_probe_cpu_ram() -> tuple[float, float]:
    """Safely reads CPU percent and RAM percent."""
    try:
        import psutil
        cpu = float(psutil.cpu_percent(interval=None))
        ram = float(psutil.virtual_memory().percent)
        return cpu, ram
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return 12.0, float(stat.dwMemoryLoad)
        except Exception:
            pass

    return 0.0, 0.0


class AlwaysOnOverlay:
    """
    Always-On Intelligent Overlay HUD for JARVIS (R6 & R8).
    Supports:
      - Sidebar Docking (380px expanded / 40px ribbon collapsed)
      - 5-Turn Conversation History Cards
      - Autonomous Task DAG Telemetry & Step Tracking (`update_task_dag`)
      - Live Code Log Streaming (`append_code_log`)
      - Visual Result Card Rendering (`display_visual_result`)
      - Quick Action Buttons & Memory Facts Preview
      - 5s Realtime CPU/RAM/Battery Status Bar
      - Dynamic 11-Bar Audio Waveform Spectrum Analyzer
      - Floating Arc Reactor Badge & 100% Thread-Safe Headless CI Resilience
    """

    def __init__(
        self,
        width: int = 380,
        height: int = 680,
        sidebar_width: int = 380,
        collapsed_width: int = 40,
        margin_right: int = 16,
        margin_bottom: int = 40,
        auto_hide_s: float = 8.0,
        sidebar_mode: bool = True,
        on_close: Callable[[], None] | None = None,
        on_action: Callable[[str], Any] | None = None,
        headless: bool = False,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._width = width
        self._height = height
        self._sidebar_width = sidebar_width
        self._collapsed_width = collapsed_width
        self._margin_right = margin_right
        self._margin_bottom = margin_bottom
        self._auto_hide_s = auto_hide_s
        self._on_close = on_close
        self._on_action = on_action
        self._headless = headless
        self._config = config or {}

        # Mode & Expansion State
        self._mode: OverlayMode = OverlayMode.SIDEBAR if sidebar_mode else OverlayMode.POPUP
        self._is_collapsed: bool = False
        self._is_minimized: bool = False

        # State Tracking
        self._state: OverlayState = OverlayState.IDLE
        self._visible: bool = False
        self._user_text: str = ""
        self._jarvis_text: str = ""
        self._status_text: str = "Sẵn sàng"
        self._hint_text: str = ""

        # 5-Turn Conversation History Queue
        self._history: deque[TurnRecord] = deque(maxlen=5)

        # Autonomous Task DAG State Telemetry
        self._current_dag: dict[str, Any] | None = None

        # Live Code Interpreter Log Stream (Buffer of 100 entries)
        self._code_logs: deque[dict[str, Any]] = deque(maxlen=100)

        # Visual Result Cards
        self._visual_results: list[dict[str, Any]] = []

        # Persistent Memory Preview Facts (Top 3)
        self._memory_facts: list[str] = [
            "Chủ nhân: Hưng",
            "Dự án: JARVIS AI",
            "Nhạc: Lofi Work",
        ]

        # Realtime Hardware Telemetry (5s update)
        self._cpu_percent: float = 0.0
        self._ram_percent: float = 0.0
        self._battery_percent: int | None = None
        self._is_charging: bool = False
        self._telemetry_interval_ms: int = 5000

        # Audio Waveform Spectrum Analyzer (11 Bars)
        self._waveform_bars: list[float] = [0.1] * 11
        self._waveform_phase: float = 0.0
        self._waveform_interval_ms: int = 60

        # Quick Action Callbacks Registry
        self._action_callbacks: dict[str, Callable[[], Any]] = {}
        self._setup_default_action_callbacks()

        # Tkinter & Threading
        self._root: tk.Tk | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._is_running = False
        self._lock = threading.RLock()

        # Animation & Timer Job Handles
        self._breathing_job: str | None = None
        self._breathing_index: int = 0
        self._breathing_direction: int = 1
        self._breathing_interval_ms: int = 120

        self._typing_job: str | None = None
        self._typing_index: int = 0
        self._typing_interval_ms: int = 350
        self._current_transcript: str = ""

        self._hide_job: str | None = None
        self._waveform_job: str | None = None
        self._telemetry_job: str | None = None

        # Drag Window Geometry Tracking
        self._drag_x: int = 0
        self._drag_y: int = 0

        # Tkinter Widget References
        self._main_container: tk.Frame | None = None
        self._ribbon_container: tk.Frame | None = None
        self._arc_badge_container: tk.Frame | None = None
        self._status_dot: tk.Label | None = None
        self._status_var: tk.StringVar | None = None
        self._user_var: tk.StringVar | None = None
        self._jarvis_var: tk.StringVar | None = None
        self._hint_var: tk.StringVar | None = None
        self._telemetry_var: tk.StringVar | None = None
        self._memory_var: tk.StringVar | None = None
        self._waveform_canvas: tk.Canvas | None = None
        self._history_frame: tk.Frame | None = None
        self._dag_frame: tk.Frame | None = None
        self._code_log_frame: tk.Frame | None = None
        self._visual_result_frame: tk.Frame | None = None

    # =========================================================================
    # Public Properties for Observability & Testing
    # =========================================================================

    @property
    def state(self) -> OverlayState:
        return self._state

    @property
    def mode(self) -> OverlayMode:
        return self._mode

    @property
    def is_visible(self) -> bool:
        return self._visible

    @property
    def is_sidebar_mode(self) -> bool:
        return self._mode == OverlayMode.SIDEBAR

    @property
    def is_collapsed(self) -> bool:
        return self._is_collapsed

    @property
    def is_minimized(self) -> bool:
        return self._is_minimized

    @property
    def user_text(self) -> str:
        return self._user_text

    @property
    def jarvis_text(self) -> str:
        return self._jarvis_text

    @property
    def status_text(self) -> str:
        return self._status_text

    @property
    def hint_text(self) -> str:
        return self._hint_text

    @property
    def is_headless(self) -> bool:
        return self._headless or (self._root is None)

    @property
    def memory_facts(self) -> list[str]:
        with self._lock:
            return list(self._memory_facts)

    @property
    def cpu_percent(self) -> float:
        return self._cpu_percent

    @property
    def ram_percent(self) -> float:
        return self._ram_percent

    @property
    def battery_percent(self) -> int | None:
        return self._battery_percent

    @property
    def is_charging(self) -> bool:
        return self._is_charging

    @property
    def waveform_bars(self) -> list[float]:
        with self._lock:
            return list(self._waveform_bars)

    @property
    def current_dag(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._current_dag) if self._current_dag else None

    @property
    def code_logs(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._code_logs)

    @property
    def visual_results(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._visual_results)

    @property
    def latest_visual_result(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._visual_results[-1]) if self._visual_results else None

    # =========================================================================
    # Lifecycle & UI Controls
    # =========================================================================

    def start(self) -> None:
        """Starts the Tkinter UI event loop in a dedicated daemon thread."""
        if self._headless:
            self._ready.set()
            self._is_running = True
            self.probe_system_metrics()
            return

        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._run_tk,
            daemon=True,
            name="JARVIS-AlwaysOnOverlay",
        )
        self._thread.start()
        if not self._ready.wait(timeout=3.0):
            logger.warning("AlwaysOnOverlay initialization timed out; falling back to headless mode.")
            self._headless = True
            self._is_running = True

    def show_listening(self, prompt: str | None = None, hint: str | None = None) -> None:
        """Activates LISTENING state and starts breathing dot & waveform animations."""
        actual_prompt = prompt or hint or "🎤 Đang lắng nghe..."
        actual_hint = hint or ""
        self._schedule(lambda: self._do_show_listening(actual_prompt, actual_hint))

    def show_thinking(self, transcript: str = "", user_text: str | None = None) -> None:
        """Activates THINKING state and starts dynamic typing dots & waveform animations."""
        actual_transcript = user_text if user_text is not None else transcript
        self._schedule(lambda: self._do_show_thinking(actual_transcript))

    def show_response(
        self,
        transcript: str = "",
        response: str | None = None,
        duration_s: float | None = None,
        hint: str = "💡 Double clap để hỏi tiếp",
        jarvis_text: str | None = None,
        user_text: str | None = None,
        action: str = "",
    ) -> None:
        """Activates RESPONSE state, renders text, records conversation turn, and sets auto-hide."""
        actual_transcript = user_text if user_text is not None else (transcript if response is not None else self._current_transcript)
        actual_response = jarvis_text if jarvis_text is not None else (response if response is not None else transcript)
        dur = duration_s if duration_s is not None else self._auto_hide_s
        self._schedule(lambda: self._do_show_response(actual_transcript, actual_response, dur, hint, action))

    def hide(self) -> None:
        """Cancels active animations and withdraws the overlay window."""
        self._schedule(self._do_hide)

    def destroy(self) -> None:
        """Gracefully destroys Tkinter root and stops background timers."""
        with self._lock:
            self._is_running = False
            self._cancel_all_animations()
            self._state = OverlayState.HIDDEN
            self._visible = False
            if self._root:
                try:
                    self._root.after(0, self._root.destroy)
                except Exception as e:
                    logger.debug("Error destroying overlay root: %s", e)
                self._root = None

    # =========================================================================
    # Task DAG, Code Stream & Visual Result Card Telemetry (Milestone 5)
    # =========================================================================

    def update_task_dag(self, dag_data: dict[str, Any]) -> None:
        """
        Updates the HUD Task DAG telemetry and renders active plan progression.
        Thread-safe: schedules UI update onto Tkinter thread or headless buffer.
        """
        with self._lock:
            self._current_dag = dict(dag_data) if dag_data else None

        self._schedule(self._render_task_dag)

    def append_code_log(self, log_line: str, stream: str = "stdout") -> None:
        """
        Appends a code interpreter log line (stdout/stderr) to HUD stream telemetry.
        Thread-safe: updates internal buffer and schedules UI refresh.
        """
        clean_line = str(log_line).rstrip("\r\n")
        entry = {
            "text": clean_line,
            "stream": stream.lower(),
            "timestamp": time.time(),
        }
        with self._lock:
            self._code_logs.append(entry)

        self._schedule(self._render_code_logs)

    def display_visual_result(self, result_info: dict[str, Any]) -> None:
        """
        Displays a visual result card (e.g. computer-use bounding box, visual diff, OCR summary).
        Thread-safe: adds to visual results history and refreshes UI.
        """
        with self._lock:
            self._visual_results.append(dict(result_info))

        self._schedule(self._render_visual_result)

    def clear_code_logs(self) -> None:
        """Clears the live code log buffer."""
        with self._lock:
            self._code_logs.clear()
        self._schedule(self._render_code_logs)

    def clear_visual_results(self) -> None:
        """Clears visual result cards."""
        with self._lock:
            self._visual_results.clear()
        self._schedule(self._render_visual_result)

    # =========================================================================
    # Sidebar, Collapse, Docking & Minimize Features
    # =========================================================================

    def toggle_sidebar(self) -> None:
        """Toggles between Sidebar mode and Floating Popup mode."""
        self._schedule(self._do_toggle_sidebar)

    def collapse_sidebar(self) -> None:
        """Collapses sidebar to a 40px ribbon at the right edge."""
        self._schedule(self._do_collapse_sidebar)

    def expand_sidebar(self) -> None:
        """Expands 40px ribbon back to full 380px sidebar."""
        self._schedule(self._do_expand_sidebar)

    def toggle_collapse(self) -> None:
        """Toggles collapse/expand state in sidebar mode."""
        if self._is_collapsed:
            self.expand_sidebar()
        else:
            self.collapse_sidebar()

    def minimize_to_arc_reactor(self) -> None:
        """Minimizes overlay into a compact floating Arc Reactor icon at corner."""
        self._schedule(self._do_minimize_to_arc_reactor)

    def restore_from_arc_reactor(self) -> None:
        """Restores overlay from floating Arc Reactor icon to normal view."""
        self._schedule(self._do_restore_from_arc_reactor)

    def toggle_minimize(self) -> None:
        """Toggles minimize mode to Arc Reactor icon."""
        if self._is_minimized:
            self.restore_from_arc_reactor()
        else:
            self.minimize_to_arc_reactor()

    def toggle(self) -> None:
        """Toggles overlay visibility and expansion state."""
        if self._is_collapsed or self._is_minimized or self._state == OverlayState.HIDDEN:
            self.expand_sidebar()
            self.show()
        else:
            self.collapse_sidebar()

    def dock_to_right(self) -> None:
        """Snaps window to the right edge of screen."""
        self._schedule(self._do_dock_to_right)

    # =========================================================================
    # Conversation History & Memory Facts Management
    # =========================================================================

    def add_turn(self, user_text: str, jarvis_text: str, action: str = "") -> TurnRecord:
        """Adds a conversation turn to the 5-turn history queue and updates UI."""
        record = TurnRecord(
            user_text=user_text,
            jarvis_text=jarvis_text,
            action=action,
            timestamp=time.time(),
        )
        with self._lock:
            self._history.append(record)
        self._schedule(self._render_history_cards)
        return record

    def get_history(self) -> list[dict[str, Any]]:
        """Returns the list of up to 5 conversation turns."""
        with self._lock:
            return [t.to_dict() for t in self._history]

    def clear_history(self) -> None:
        """Clears all conversation turns from history."""
        with self._lock:
            self._history.clear()
        self._schedule(self._render_history_cards)

    def set_memory_facts(self, facts: list[str]) -> None:
        """Updates the top 3 persistent memory facts preview."""
        with self._lock:
            self._memory_facts = list(facts[:3])
        formatted = " | ".join(f"◈ {f}" for f in self._memory_facts)
        if self._memory_var:
            self._schedule(lambda: self._memory_var.set(formatted) if self._memory_var else None)

    # =========================================================================
    # Quick Actions & Telemetry
    # =========================================================================

    def register_action_callback(self, action_key: str, callback: Callable[[], Any]) -> None:
        """Registers a handler callback for interactive quick action buttons."""
        with self._lock:
            self._action_callbacks[action_key] = callback

    def trigger_quick_action(self, action_key: str) -> Any:
        """Dispatches quick action trigger to registered handler or on_action callback."""
        with self._lock:
            handler = self._action_callbacks.get(action_key)

        if handler:
            try:
                return handler()
            except Exception as e:
                logger.error("Error in action callback for '%s': %s", action_key, e)
                return None

        if self._on_action:
            try:
                return self._on_action(action_key)
            except Exception as e:
                logger.error("Error in on_action handler for '%s': %s", action_key, e)
                return None

        return None

    def update_telemetry(
        self,
        cpu_percent: float | None = None,
        ram_percent: float | None = None,
        battery_percent: int | None = None,
        is_charging: bool | None = None,
    ) -> dict[str, Any]:
        """Manually updates hardware telemetry and refreshes UI status bar."""
        with self._lock:
            if cpu_percent is not None:
                self._cpu_percent = float(cpu_percent)
            if ram_percent is not None:
                self._ram_percent = float(ram_percent)
            if battery_percent is not None:
                self._battery_percent = int(battery_percent) if battery_percent >= 0 else None
            if is_charging is not None:
                self._is_charging = bool(is_charging)

            summary = {
                "cpu_percent": self._cpu_percent,
                "ram_percent": self._ram_percent,
                "battery_percent": self._battery_percent,
                "is_charging": self._is_charging,
            }

        self._schedule(self._update_telemetry_label)
        return summary

    def probe_system_metrics(self) -> dict[str, Any]:
        """Probes CPU, RAM, and Battery from OS subsystems and updates telemetry."""
        cpu, ram = _safe_probe_cpu_ram()
        bat, charging = _safe_probe_battery()
        return self.update_telemetry(
            cpu_percent=cpu,
            ram_percent=ram,
            battery_percent=bat,
            is_charging=charging,
        )

    def update_audio_level(self, level: float | list[float]) -> None:
        """Updates 11-bar waveform spectrum analyzer with audio RMS or bar levels."""
        with self._lock:
            if isinstance(level, (int, float)):
                rms = min(1.0, max(0.0, float(level)))
                weights = [0.15, 0.35, 0.60, 0.85, 0.95, 1.0, 0.95, 0.85, 0.60, 0.35, 0.15]
                self._waveform_bars = [
                    min(1.0, max(0.05, rms * w + random.uniform(-0.04, 0.04)))
                    for w in weights
                ]
            elif isinstance(level, list):
                bars = list(level[:11])
                while len(bars) < 11:
                    bars.append(0.05)
                self._waveform_bars = [min(1.0, max(0.05, float(b))) for b in bars]

        self._schedule(self._draw_waveform_canvas)

    # =========================================================================
    # Internal Setup & Actions
    # =========================================================================

    def _setup_default_action_callbacks(self) -> None:
        self._action_callbacks["briefing_morning"] = lambda: self._do_action_briefing()
        self._action_callbacks["system_status"] = lambda: self._do_action_status()
        self._action_callbacks["focus_mode"] = lambda: self._do_action_focus()
        self._action_callbacks["toggle_collapse"] = lambda: self.toggle_collapse()

    def _do_action_briefing(self) -> str:
        self.show_response(
            transcript="Briefing Sáng",
            response="Hà Nội 28°C, trời đẹp. Lịch: 9h Họp team, 14h Review. 3 tin công nghệ mới.",
        )
        return "briefing_triggered"

    def _do_action_status(self) -> str:
        self.probe_system_metrics()
        bat_str = f", Pin: {self._battery_percent}%" if self._battery_percent is not None else ""
        self.show_response(
            transcript="System Status",
            response=f"CPU: {self._cpu_percent:.1f}% | RAM: {self._ram_percent:.1f}%{bat_str}. Mọi dịch vụ JARVIS hoạt động bình thường.",
        )
        return "status_triggered"

    def _do_action_focus(self) -> str:
        self.show_response(
            transcript="Focus Mode",
            response="Đã kích hoạt Focus Mode 25 phút. Chúc Ngài làm việc hiệu quả.",
        )
        return "focus_triggered"

    # =========================================================================
    # Internal Tkinter Loop & UI Construction
    # =========================================================================

    def _run_tk(self) -> None:
        try:
            self._root = tk.Tk()
            self._build_ui()
            self._is_running = True
            self._ready.set()
            self._start_telemetry_loop()
            self._start_waveform_loop()
            self._root.mainloop()
        except (tk.TclError, RuntimeError, Exception) as e:
            logger.warning("Tkinter GUI unavailable (%s); operating in headless mode.", e)
            self._headless = True
            self._root = None
            self._is_running = True
            self._ready.set()

    def _get_screen_dimensions(self) -> tuple[int, int]:
        if self._root:
            try:
                return self._root.winfo_screenwidth(), self._root.winfo_screenheight()
            except Exception:
                pass
        return 1920, 1080

    def _build_ui(self) -> None:
        root = self._root
        if not root:
            return

        root.overrideredirect(True)
        try:
            root.attributes("-topmost", True)
            root.attributes("-alpha", 0.95)
        except Exception:
            pass
        root.configure(bg=COLORS["bg"])
        root.resizable(False, False)

        sw, sh = self._get_screen_dimensions()
        curr_w = self._sidebar_width if self._mode == OverlayMode.SIDEBAR else self._width
        curr_h = min(self._height, sh - self._margin_bottom)
        x = max(0, sw - curr_w - (0 if self._mode == OverlayMode.SIDEBAR else self._margin_right))
        y = 0 if self._mode == OverlayMode.SIDEBAR else max(0, sh - curr_h - self._margin_bottom)

        root.geometry(f"{curr_w}x{curr_h}+{x}+{y}")
        root.withdraw()

        # Outer Neon Border
        self._outer_frame = tk.Frame(root, bg=COLORS["border"], padx=1, pady=1)
        self._outer_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Main Container (Expanded Sidebar / Popup)
        self._main_container = tk.Frame(self._outer_frame, bg=COLORS["bg"], padx=10, pady=6)
        self._main_container.pack(fill=tk.BOTH, expand=True)

        # 2. Ribbon Container (40px Collapsed Ribbon)
        self._ribbon_container = tk.Frame(self._outer_frame, bg=COLORS["bg"], padx=2, pady=8)

        # 3. Arc Reactor Badge Container (52x52 Minimized Badge)
        self._arc_badge_container = tk.Frame(self._outer_frame, bg=COLORS["bg"], padx=2, pady=2)

        self._build_main_hud_content(self._main_container)
        self._build_ribbon_content(self._ribbon_container)
        self._build_arc_badge_content(self._arc_badge_container)

        # Drag Window Bindings
        root.bind("<ButtonPress-1>", self._on_drag_start)
        root.bind("<B1-Motion>", self._on_drag)
        root.bind("<ButtonRelease-1>", self._on_drag_end)

    def _build_main_hud_content(self, parent: tk.Frame) -> None:
        # A. Header Bar
        header = tk.Frame(parent, bg=COLORS["bg"])
        header.pack(fill=tk.X, pady=(0, 2))

        title_lbl = tk.Label(
            header,
            text="◈  J.A.R.V.I.S  HUD",
            font=tkfont.Font(family=FONT_FAMILY, size=10, weight="bold"),
            fg=COLORS["title"],
            bg=COLORS["bg"],
            cursor="fleur",
        )
        title_lbl.pack(side=tk.LEFT)

        ctrl_frame = tk.Frame(header, bg=COLORS["bg"])
        ctrl_frame.pack(side=tk.RIGHT)

        min_btn = tk.Label(
            ctrl_frame,
            text=" ◯ ",
            font=tkfont.Font(family=FONT_FAMILY, size=8),
            fg=COLORS["arc_core"],
            bg=COLORS["bg"],
            cursor="hand2",
        )
        min_btn.pack(side=tk.LEFT)
        min_btn.bind("<Button-1>", lambda e: self.minimize_to_arc_reactor())

        collapse_btn = tk.Label(
            ctrl_frame,
            text=" ◀ ",
            font=tkfont.Font(family=FONT_FAMILY, size=8),
            fg=COLORS["btn_fg"],
            bg=COLORS["bg"],
            cursor="hand2",
        )
        collapse_btn.pack(side=tk.LEFT)
        collapse_btn.bind("<Button-1>", lambda e: self.collapse_sidebar())

        close_btn = tk.Label(
            ctrl_frame,
            text=" ✕ ",
            font=tkfont.Font(family=FONT_FAMILY, size=8),
            fg=COLORS["close_btn"],
            bg=COLORS["bg"],
            cursor="hand2",
        )
        close_btn.pack(side=tk.LEFT)
        close_btn.bind("<Button-1>", lambda e: self._do_hide())

        # Header Divider
        tk.Frame(parent, height=1, bg=COLORS["border_dim"]).pack(fill=tk.X, pady=(0, 3))

        # B. Realtime 5s Telemetry Status Bar
        telemetry_frame = tk.Frame(parent, bg=COLORS["bg_card"], padx=4, pady=2, relief=tk.FLAT)
        telemetry_frame.pack(fill=tk.X, pady=(0, 4))

        self._status_dot = tk.Label(
            telemetry_frame,
            text="●",
            font=tkfont.Font(family=FONT_FAMILY, size=8),
            fg=COLORS["dot"],
            bg=COLORS["bg_card"],
        )
        self._status_dot.pack(side=tk.LEFT, padx=(0, 4))

        self._status_var = tk.StringVar(value=self._status_text)
        tk.Label(
            telemetry_frame,
            textvariable=self._status_var,
            font=tkfont.Font(family=FONT_FAMILY, size=8, weight="bold"),
            fg=COLORS["status"],
            bg=COLORS["bg_card"],
        ).pack(side=tk.LEFT)

        self._telemetry_var = tk.StringVar(value="CPU: 0% | RAM: 0%")
        tk.Label(
            telemetry_frame,
            textvariable=self._telemetry_var,
            font=tkfont.Font(family=FONT_FAMILY, size=8),
            fg=COLORS["bar_cyan"],
            bg=COLORS["bg_card"],
        ).pack(side=tk.RIGHT)

        # C. Dynamic 11-Bar Waveform Spectrum Analyzer Canvas
        wave_frame = tk.Frame(parent, bg=COLORS["bg"], pady=1)
        wave_frame.pack(fill=tk.X, pady=(0, 3))

        self._waveform_canvas = tk.Canvas(
            wave_frame,
            width=350,
            height=26,
            bg=COLORS["bg_card"],
            highlightthickness=1,
            highlightbackground=COLORS["border_dim"],
        )
        self._waveform_canvas.pack(fill=tk.X, expand=True)

        # D. Memory Facts Preview Widget (Top 3 Facts)
        mem_frame = tk.Frame(parent, bg=COLORS["badge_bg"], padx=4, pady=2)
        mem_frame.pack(fill=tk.X, pady=(0, 4))

        mem_title = tk.Label(
            mem_frame,
            text="🧠 BỘ NHỚ:",
            font=tkfont.Font(family=FONT_FAMILY, size=7, weight="bold"),
            fg=COLORS["title"],
            bg=COLORS["badge_bg"],
        )
        mem_title.pack(side=tk.LEFT, padx=(0, 4))

        self._memory_var = tk.StringVar(value=" | ".join(f"◈ {f}" for f in self._memory_facts))
        tk.Label(
            mem_frame,
            textvariable=self._memory_var,
            font=tkfont.Font(family=FONT_FAMILY, size=7),
            fg=COLORS["badge_text"],
            bg=COLORS["badge_bg"],
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # E. Active Transcript & Response Box
        chat_box = tk.Frame(parent, bg=COLORS["bg_card"], padx=6, pady=4)
        chat_box.pack(fill=tk.X, pady=(0, 4))

        user_row = tk.Frame(chat_box, bg=COLORS["bg_card"])
        user_row.pack(fill=tk.X, pady=(0, 2))
        tk.Label(
            user_row,
            text="Ngài:",
            font=tkfont.Font(family=FONT_FAMILY, size=8, weight="bold"),
            fg=COLORS["user_label"],
            bg=COLORS["bg_card"],
            width=6,
            anchor="nw",
        ).pack(side=tk.LEFT)
        self._user_var = tk.StringVar(value=self._user_text)
        tk.Label(
            user_row,
            textvariable=self._user_var,
            font=tkfont.Font(family=FONT_FAMILY, size=8),
            fg=COLORS["user_text"],
            bg=COLORS["bg_card"],
            justify=tk.LEFT,
            wraplength=280,
            anchor="nw",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        jarvis_row = tk.Frame(chat_box, bg=COLORS["bg_card"])
        jarvis_row.pack(fill=tk.X)
        tk.Label(
            jarvis_row,
            text="JARVIS:",
            font=tkfont.Font(family=FONT_FAMILY, size=8, weight="bold"),
            fg=COLORS["jarvis_label"],
            bg=COLORS["bg_card"],
            width=6,
            anchor="nw",
        ).pack(side=tk.LEFT)
        self._jarvis_var = tk.StringVar(value=self._jarvis_text)
        tk.Label(
            jarvis_row,
            textvariable=self._jarvis_var,
            font=tkfont.Font(family=FONT_FAMILY, size=8),
            fg=COLORS["jarvis_text"],
            bg=COLORS["bg_card"],
            justify=tk.LEFT,
            wraplength=280,
            anchor="nw",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # F. Autonomous Telemetry Sections (Task DAG, Live Logs, Visual Cards)
        self._dag_frame = tk.Frame(parent, bg=COLORS["bg"])
        self._dag_frame.pack(fill=tk.X, pady=(0, 2))

        self._code_log_frame = tk.Frame(parent, bg=COLORS["bg"])
        self._code_log_frame.pack(fill=tk.X, pady=(0, 2))

        self._visual_result_frame = tk.Frame(parent, bg=COLORS["bg"])
        self._visual_result_frame.pack(fill=tk.X, pady=(0, 2))

        # G. 5-Turn Conversation History Display
        hist_header = tk.Frame(parent, bg=COLORS["bg"])
        hist_header.pack(fill=tk.X, pady=(2, 1))
        tk.Label(
            hist_header,
            text="📜 LỊCH SỬ HỘI THOẠI (5 TURNS)",
            font=tkfont.Font(family=FONT_FAMILY, size=7, weight="bold"),
            fg=COLORS["tooltip"],
            bg=COLORS["bg"],
        ).pack(side=tk.LEFT)

        self._history_frame = tk.Frame(parent, bg=COLORS["bg"])
        self._history_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        self._render_history_cards()

        # H. Interactive Quick Action Buttons
        btn_frame = tk.Frame(parent, bg=COLORS["bg"])
        btn_frame.pack(fill=tk.X, pady=(0, 2))

        self._create_quick_button(btn_frame, "🌅 Briefing", lambda: self.trigger_quick_action("briefing_morning"))
        self._create_quick_button(btn_frame, "📊 Status", lambda: self.trigger_quick_action("system_status"))
        self._create_quick_button(btn_frame, "🎯 Focus", lambda: self.trigger_quick_action("focus_mode"))
        self._create_quick_button(btn_frame, "◀ Thu gọn", lambda: self.collapse_sidebar())

        # I. Footer Tooltip Hint
        footer_frame = tk.Frame(parent, bg=COLORS["bg"])
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(1, 0))

        self._hint_var = tk.StringVar(value=self._hint_text)
        tk.Label(
            footer_frame,
            textvariable=self._hint_var,
            font=tkfont.Font(family=FONT_FAMILY, size=7, slant="italic"),
            fg=COLORS["tooltip"],
            bg=COLORS["bg"],
            anchor="center",
        ).pack(fill=tk.X)

    def _create_quick_button(self, parent: tk.Frame, label: str, command: Callable[[], Any]) -> tk.Button:
        btn = tk.Button(
            parent,
            text=label,
            font=tkfont.Font(family=FONT_FAMILY, size=7, weight="bold"),
            fg=COLORS["btn_fg"],
            bg=COLORS["btn_bg"],
            activebackground=COLORS["btn_hover"],
            activeforeground=COLORS["btn_fg"],
            relief=tk.FLAT,
            padx=3,
            pady=2,
            cursor="hand2",
            command=command,
        )
        btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        return btn

    def _build_ribbon_content(self, parent: tk.Frame) -> None:
        """Builds content for the 40px collapsed sidebar ribbon."""
        expand_btn = tk.Label(
            parent,
            text="▶",
            font=tkfont.Font(family=FONT_FAMILY, size=11, weight="bold"),
            fg=COLORS["btn_fg"],
            bg=COLORS["bg"],
            cursor="hand2",
        )
        expand_btn.pack(pady=(4, 8))
        expand_btn.bind("<Button-1>", lambda e: self.expand_sidebar())

        core_lbl = tk.Label(
            parent,
            text="◈",
            font=tkfont.Font(family=FONT_FAMILY, size=12),
            fg=COLORS["arc_core"],
            bg=COLORS["bg"],
            cursor="hand2",
        )
        core_lbl.pack(pady=4)
        core_lbl.bind("<Button-1>", lambda e: self.expand_sidebar())

        tk.Label(
            parent,
            text="J\nA\nR\nV\nI\nS",
            font=tkfont.Font(family=FONT_FAMILY, size=8, weight="bold"),
            fg=COLORS["border_dim"],
            bg=COLORS["bg"],
        ).pack(expand=True)

    def _build_arc_badge_content(self, parent: tk.Frame) -> None:
        """Builds content for the 52x52 minimized Arc Reactor floating badge."""
        canvas = tk.Canvas(
            parent,
            width=48,
            height=48,
            bg=COLORS["bg"],
            highlightthickness=0,
            cursor="hand2",
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        canvas.create_oval(4, 4, 44, 44, outline=COLORS["arc_ring"], width=2)
        canvas.create_oval(12, 12, 36, 36, outline=COLORS["border"], width=2)
        canvas.create_oval(18, 18, 30, 30, fill=COLORS["arc_core"], outline=COLORS["arc_glow"])

        canvas.bind("<Button-1>", lambda e: self.restore_from_arc_reactor())

    # =========================================================================
    # Drag-and-Drop & Snapping Mechanics
    # =========================================================================

    def _on_drag_start(self, e: Any) -> None:
        self._drag_x, self._drag_y = e.x, e.y

    def _on_drag(self, e: Any) -> None:
        if self._root:
            new_x = self._root.winfo_x() + (e.x - self._drag_x)
            new_y = self._root.winfo_y() + (e.y - self._drag_y)
            self._root.geometry(f"+{new_x}+{new_y}")

    def _on_drag_end(self, e: Any) -> None:
        if not self._root:
            return
        sw, sh = self._get_screen_dimensions()
        curr_x = self._root.winfo_x()
        curr_w = self._root.winfo_width()

        if (sw - (curr_x + curr_w)) < 60:
            self._do_dock_to_right()

    def _do_dock_to_right(self) -> None:
        self._mode = OverlayMode.SIDEBAR
        if not self._root:
            return
        sw, sh = self._get_screen_dimensions()
        w = self._collapsed_width if self._is_collapsed else self._sidebar_width
        h = min(self._height, sh - self._margin_bottom)
        x = max(0, sw - w)
        y = 0
        self._root.geometry(f"{w}x{h}+{x}+{y}")

    # =========================================================================
    # State Transition Handlers
    # =========================================================================

    def _do_show_listening(self, prompt: str, hint: str = "") -> None:
        self._cancel_all_animations()
        self._state = OverlayState.LISTENING
        self._visible = True
        self._current_transcript = ""

        self._user_text = prompt
        self._jarvis_text = ""
        self._status_text = "Đang lắng nghe giọng nói"
        self._hint_text = hint

        if self._user_var:
            self._user_var.set(self._user_text)
        if self._jarvis_var:
            self._jarvis_var.set(self._jarvis_text)
        if self._status_var:
            self._status_var.set(self._status_text)
        if self._hint_var:
            self._hint_var.set(self._hint_text)

        if self._root:
            try:
                self._root.deiconify()
                self._root.lift()
                self._root.attributes("-topmost", True)
            except Exception:
                pass
            self._start_breathing_animation()
            self._start_waveform_loop()

    def _do_show_thinking(self, transcript: str) -> None:
        self._cancel_all_animations()
        self._state = OverlayState.THINKING
        self._visible = True
        self._current_transcript = transcript

        self._user_text = transcript
        self._jarvis_text = "⟳ Đang xử lý..."
        self._status_text = "AI đang suy nghĩ"
        self._hint_text = ""

        if self._user_var:
            self._user_var.set(self._user_text)
        if self._jarvis_var:
            self._jarvis_var.set(self._jarvis_text)
        if self._status_var:
            self._status_var.set(self._status_text)
        if self._hint_var:
            self._hint_var.set(self._hint_text)

        if self._status_dot:
            try:
                self._status_dot.configure(fg=COLORS["status_thinking"])
            except Exception:
                pass

        if self._root:
            try:
                self._root.deiconify()
            except Exception:
                pass
            self._start_typing_animation()
            self._start_waveform_loop()

    def _do_show_response(self, transcript: str, response: str, duration_s: float, hint: str, action: str = "") -> None:
        self._cancel_all_animations()
        self._state = OverlayState.RESPONSE
        self._visible = True

        display_resp = response if len(response) <= 240 else response[:237] + "..."
        self._user_text = transcript
        self._jarvis_text = display_resp
        self._status_text = "Hoàn thành"
        self._hint_text = hint

        self.add_turn(user_text=transcript, jarvis_text=display_resp, action=action)

        if self._user_var:
            self._user_var.set(self._user_text)
        if self._jarvis_var:
            self._jarvis_var.set(self._jarvis_text)
        if self._status_var:
            self._status_var.set(self._status_text)
        if self._hint_var:
            self._hint_var.set(self._hint_text)

        if self._status_dot:
            try:
                self._status_dot.configure(fg=COLORS["status"])
            except Exception:
                pass

        if self._root:
            try:
                self._root.deiconify()
                self._hide_job = self._root.after(int(duration_s * 1000), self._do_hide)
            except Exception:
                pass
            self._start_waveform_loop()

    def _do_hide(self) -> None:
        self._cancel_all_animations()
        self._state = OverlayState.HIDDEN
        self._visible = False
        self._user_text = ""
        self._jarvis_text = ""
        self._status_text = "Sẵn sàng"
        self._hint_text = ""

        if self._user_var:
            self._user_var.set("")
        if self._jarvis_var:
            self._jarvis_var.set("")
        if self._status_var:
            self._status_var.set(self._status_text)
        if self._hint_var:
            self._hint_var.set("")

        if self._status_dot:
            try:
                self._status_dot.configure(fg=COLORS["dot"])
            except Exception:
                pass

        if self._root:
            try:
                self._root.withdraw()
            except Exception:
                pass

        if self._on_close:
            try:
                self._on_close()
            except Exception as e:
                logger.error("Error in on_close callback: %s", e)

    # =========================================================================
    # Layout Toggle Implementations
    # =========================================================================

    def _do_toggle_sidebar(self) -> None:
        if self._mode == OverlayMode.SIDEBAR:
            self._mode = OverlayMode.POPUP
            if self._root:
                sw, sh = self._get_screen_dimensions()
                curr_w = self._width
                curr_h = min(self._height, sh - self._margin_bottom)
                x = max(0, sw - curr_w - self._margin_right)
                y = max(0, sh - curr_h - self._margin_bottom)
                self._root.geometry(f"{curr_w}x{curr_h}+{x}+{y}")
        else:
            self._mode = OverlayMode.SIDEBAR
            self._is_collapsed = False
            self._do_dock_to_right()

    def _do_collapse_sidebar(self) -> None:
        self._is_collapsed = True
        self._is_minimized = False
        if self._root:
            if self._main_container:
                self._main_container.pack_forget()
            if self._arc_badge_container:
                self._arc_badge_container.pack_forget()
            if self._ribbon_container:
                self._ribbon_container.pack(fill=tk.BOTH, expand=True)

            sw, sh = self._get_screen_dimensions()
            h = min(self._height, sh - self._margin_bottom)
            x = max(0, sw - self._collapsed_width)
            self._root.geometry(f"{self._collapsed_width}x{h}+{x}+0")

    def _do_expand_sidebar(self) -> None:
        self._is_collapsed = False
        self._is_minimized = False
        if self._root:
            if self._ribbon_container:
                self._ribbon_container.pack_forget()
            if self._arc_badge_container:
                self._arc_badge_container.pack_forget()
            if self._main_container:
                self._main_container.pack(fill=tk.BOTH, expand=True)

            sw, sh = self._get_screen_dimensions()
            h = min(self._height, sh - self._margin_bottom)
            x = max(0, sw - self._sidebar_width)
            self._root.geometry(f"{self._sidebar_width}x{h}+{x}+0")

    def _do_minimize_to_arc_reactor(self) -> None:
        self._is_minimized = True
        if self._root:
            if self._main_container:
                self._main_container.pack_forget()
            if self._ribbon_container:
                self._ribbon_container.pack_forget()
            if self._arc_badge_container:
                self._arc_badge_container.pack(fill=tk.BOTH, expand=True)

            sw, sh = self._get_screen_dimensions()
            x = max(0, sw - 56 - self._margin_right)
            y = max(0, sh - 56 - self._margin_bottom)
            self._root.geometry(f"52x52+{x}+{y}")

    def _do_restore_from_arc_reactor(self) -> None:
        self._is_minimized = False
        if self._is_collapsed:
            self._do_collapse_sidebar()
        else:
            self._do_expand_sidebar()

    # =========================================================================
    # History Cards, Task DAG, Code Logs, and Visual Result Rendering
    # =========================================================================

    def _render_history_cards(self) -> None:
        if not self._history_frame:
            return

        for child in self._history_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        turns = self.get_history()
        if not turns:
            lbl = tk.Label(
                self._history_frame,
                text="Chưa có hội thoại gần đây.",
                font=tkfont.Font(family=FONT_FAMILY, size=7, slant="italic"),
                fg=COLORS["border_dim"],
                bg=COLORS["bg"],
            )
            lbl.pack(pady=4)
            return

        for idx, turn in enumerate(turns):
            card = tk.Frame(self._history_frame, bg=COLORS["bg_card"], padx=4, pady=2)
            card.pack(fill=tk.X, pady=1)

            u_txt = turn["user_text"]
            if len(u_txt) > 36:
                u_txt = u_txt[:33] + "..."
            j_txt = turn["jarvis_text"]
            if len(j_txt) > 42:
                j_txt = j_txt[:39] + "..."

            card_row = tk.Frame(card, bg=COLORS["bg_card"])
            card_row.pack(fill=tk.X)

            tk.Label(
                card_row,
                text=f"T{idx + 1} 👤",
                font=tkfont.Font(family=FONT_FAMILY, size=7, weight="bold"),
                fg=COLORS["user_label"],
                bg=COLORS["bg_card"],
            ).pack(side=tk.LEFT)

            tk.Label(
                card_row,
                text=u_txt,
                font=tkfont.Font(family=FONT_FAMILY, size=7),
                fg=COLORS["user_text"],
                bg=COLORS["bg_card"],
            ).pack(side=tk.LEFT, padx=2)

            resp_row = tk.Frame(card, bg=COLORS["bg_card"])
            resp_row.pack(fill=tk.X)

            tk.Label(
                resp_row,
                text="   🤖",
                font=tkfont.Font(family=FONT_FAMILY, size=7, weight="bold"),
                fg=COLORS["jarvis_label"],
                bg=COLORS["bg_card"],
            ).pack(side=tk.LEFT)

            tk.Label(
                resp_row,
                text=j_txt,
                font=tkfont.Font(family=FONT_FAMILY, size=7),
                fg=COLORS["jarvis_text"],
                bg=COLORS["bg_card"],
            ).pack(side=tk.LEFT, padx=2)

    def _render_task_dag(self) -> None:
        """Renders active Task DAG plan progression into HUD."""
        if not self._dag_frame:
            return

        for child in self._dag_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        with self._lock:
            dag = self._current_dag

        if not dag:
            return

        card = tk.Frame(self._dag_frame, bg=COLORS["badge_bg"], padx=6, pady=4, highlightthickness=1, highlightbackground=COLORS["border_dim"])
        card.pack(fill=tk.X, pady=2)

        goal = dag.get("goal", "Autonomous Task Plan")
        plan_id = dag.get("plan_id", "plan")
        nodes = dag.get("nodes", []) or dag.get("steps", [])

        header_row = tk.Frame(card, bg=COLORS["badge_bg"])
        header_row.pack(fill=tk.X)

        tk.Label(
            header_row,
            text=f"🎯 PLAN: {goal[:28]}...",
            font=tkfont.Font(family=FONT_FAMILY, size=7, weight="bold"),
            fg=COLORS["title"],
            bg=COLORS["badge_bg"],
        ).pack(side=tk.LEFT)

        tk.Label(
            header_row,
            text=f"[{len(nodes)} steps]",
            font=tkfont.Font(family=FONT_FAMILY, size=7),
            fg=COLORS["tooltip"],
            bg=COLORS["badge_bg"],
        ).pack(side=tk.RIGHT)

        for n in nodes[:4]:
            step_name = n.get("action_name") or n.get("name") or n.get("step_id", "step")
            status = n.get("status", "pending").lower()
            if status in ("completed", "success"):
                icon = "✓"
                color = COLORS["dag_completed"]
            elif status in ("running", "executing"):
                icon = "⟳"
                color = COLORS["dag_running"]
            elif status in ("failed", "error"):
                icon = "✕"
                color = COLORS["dag_failed"]
            else:
                icon = "○"
                color = COLORS["dag_pending"]

            step_row = tk.Frame(card, bg=COLORS["badge_bg"])
            step_row.pack(fill=tk.X, padx=4, pady=1)

            tk.Label(
                step_row,
                text=f"{icon} {step_name}",
                font=tkfont.Font(family=FONT_FAMILY, size=7),
                fg=color,
                bg=COLORS["badge_bg"],
            ).pack(side=tk.LEFT)

    def _render_code_logs(self) -> None:
        """Renders live code interpreter stdout/stderr log stream into HUD."""
        if not self._code_log_frame:
            return

        for child in self._code_log_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        with self._lock:
            logs = list(self._code_logs)[-3:]

        if not logs:
            return

        card = tk.Frame(self._code_log_frame, bg="#050810", padx=4, pady=2, highlightthickness=1, highlightbackground=COLORS["border_dim"])
        card.pack(fill=tk.X, pady=1)

        tk.Label(
            card,
            text="💻 CODE STREAM:",
            font=tkfont.Font(family=FONT_FAMILY, size=7, weight="bold"),
            fg=COLORS["bar_cyan"],
            bg="#050810",
        ).pack(anchor="w")

        for item in logs:
            text = item.get("text", "")
            stream = item.get("stream", "stdout")
            fg_color = COLORS["log_stderr"] if stream == "stderr" else COLORS["log_stdout"]
            if len(text) > 46:
                text = text[:43] + "..."
            tk.Label(
                card,
                text=f"> {text}",
                font=tkfont.Font(family=FONT_FAMILY, size=7),
                fg=fg_color,
                bg="#050810",
                anchor="w",
            ).pack(fill=tk.X)

    def _render_visual_result(self) -> None:
        """Renders visual verification and grounding cards into HUD."""
        if not self._visual_result_frame:
            return

        for child in self._visual_result_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        with self._lock:
            res = self._visual_results[-1] if self._visual_results else None

        if not res:
            return

        card = tk.Frame(self._visual_result_frame, bg=COLORS["bg_card"], padx=4, pady=2, highlightthickness=1, highlightbackground=COLORS["bar_emerald"])
        card.pack(fill=tk.X, pady=1)

        title = res.get("title") or res.get("type") or "Visual Result"
        diff_pct = res.get("diff_percent")
        diff_str = f" (Diff: {diff_pct:.1f}%)" if diff_pct is not None else ""

        tk.Label(
            card,
            text=f"👁 {title}{diff_str}",
            font=tkfont.Font(family=FONT_FAMILY, size=7, weight="bold"),
            fg=COLORS["bar_emerald"],
            bg=COLORS["bg_card"],
        ).pack(anchor="w")

        desc = res.get("description") or res.get("summary") or res.get("text") or ""
        if desc:
            if len(desc) > 50:
                desc = desc[:47] + "..."
            tk.Label(
                card,
                text=desc,
                font=tkfont.Font(family=FONT_FAMILY, size=7),
                fg=COLORS["badge_text"],
                bg=COLORS["bg_card"],
                anchor="w",
            ).pack(fill=tk.X)

    # =========================================================================
    # Waveform Spectrum Analyzer Canvas Drawing & Loop
    # =========================================================================

    def _start_waveform_loop(self) -> None:
        if self._waveform_job is None and self._root and not self._headless:
            self._animate_waveform_step()

    def _animate_waveform_step(self) -> None:
        if not self._root or not self._is_running:
            return

        self._waveform_phase += 0.25
        with self._lock:
            if self._state == OverlayState.LISTENING:
                weights = [0.15, 0.35, 0.60, 0.85, 0.95, 1.0, 0.95, 0.85, 0.60, 0.35, 0.15]
                self._waveform_bars = [
                    min(1.0, max(0.1, w * (0.6 + 0.4 * math.sin(self._waveform_phase + i)) + random.uniform(-0.05, 0.05)))
                    for i, w in enumerate(weights)
                ]
            elif self._state == OverlayState.THINKING:
                self._waveform_bars = [
                    0.2 + 0.6 * max(0.0, math.sin(self._waveform_phase + (i / 11.0) * math.pi * 2))
                    for i in range(11)
                ]
            elif self._state == OverlayState.RESPONSE:
                self._waveform_bars = [
                    min(1.0, max(0.15, 0.5 * (1.0 + math.sin(self._waveform_phase * 1.5 + i * 0.5))))
                    for i in range(11)
                ]
            else:
                self._waveform_bars = [
                    0.08 + 0.05 * math.sin(self._waveform_phase * 0.5 + i * 0.2)
                    for i in range(11)
                ]

        self._draw_waveform_canvas()

        try:
            self._waveform_job = self._root.after(self._waveform_interval_ms, self._animate_waveform_step)
        except Exception:
            self._waveform_job = None

    def _draw_waveform_canvas(self) -> None:
        if not self._waveform_canvas or not self._root:
            return

        try:
            self._waveform_canvas.delete("all")
            width = self._waveform_canvas.winfo_width() or 340
            height = self._waveform_canvas.winfo_height() or 26

            bar_count = 11
            bar_width = max(6, int((width - (bar_count - 1) * 6) / bar_count))
            gap = max(2, int((width - bar_count * bar_width) / (bar_count + 1)))

            bars = self.waveform_bars
            for i in range(min(bar_count, len(bars))):
                val = bars[i]
                bar_h = max(3, int(val * (height - 4)))
                x0 = gap + i * (bar_width + gap)
                x1 = x0 + bar_width
                y0 = int((height - bar_h) / 2)
                y1 = y0 + bar_h

                if self._state == OverlayState.LISTENING:
                    color = COLORS["bar_amber"] if i in (4, 5, 6) else COLORS["bar_cyan"]
                elif self._state == OverlayState.THINKING:
                    color = COLORS["status_thinking"]
                elif self._state == OverlayState.RESPONSE:
                    color = COLORS["bar_emerald"] if val > 0.6 else COLORS["bar_cyan"]
                else:
                    color = COLORS["border_dim"]

                self._waveform_canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
        except Exception as e:
            logger.debug("Error rendering waveform canvas: %s", e)

    # =========================================================================
    # Realtime 5s Telemetry Status Loop
    # =========================================================================

    def _start_telemetry_loop(self) -> None:
        if self._telemetry_job is None and self._root and not self._headless:
            self._telemetry_tick()

    def _telemetry_tick(self) -> None:
        if not self._root or not self._is_running:
            return

        self.probe_system_metrics()
        try:
            self._telemetry_job = self._root.after(self._telemetry_interval_ms, self._telemetry_tick)
        except Exception:
            self._telemetry_job = None

    def _update_telemetry_label(self) -> None:
        if not self._telemetry_var:
            return

        bat_part = ""
        if self._battery_percent is not None:
            charge_icon = "⚡" if self._is_charging else "🔋"
            bat_part = f" | {charge_icon}{self._battery_percent}%"

        text = f"CPU:{self._cpu_percent:.0f}% | RAM:{self._ram_percent:.0f}%{bat_part}"
        self._telemetry_var.set(text)

    # =========================================================================
    # Animation Implementations (Breathing Dot & Dynamic Typing Dots)
    # =========================================================================

    def _start_breathing_animation(self) -> None:
        self._breathing_index = 0
        self._breathing_direction = 1
        self._animate_breathing_dot()

    def _animate_breathing_dot(self) -> None:
        if not self._root or not self._visible or self._state != OverlayState.LISTENING:
            return

        color = BREATHING_GRADIENT[self._breathing_index]
        if self._status_dot:
            try:
                self._status_dot.configure(fg=color)
            except Exception:
                return

        if self._breathing_direction == 1:
            if self._breathing_index < len(BREATHING_GRADIENT) - 1:
                self._breathing_index += 1
            else:
                self._breathing_direction = -1
                self._breathing_index -= 1
        else:
            if self._breathing_index > 0:
                self._breathing_index -= 1
            else:
                self._breathing_direction = 1
                self._breathing_index += 1

        try:
            self._breathing_job = self._root.after(
                self._breathing_interval_ms,
                self._animate_breathing_dot,
            )
        except Exception:
            self._breathing_job = None

    def _start_typing_animation(self) -> None:
        self._typing_index = 0
        self._animate_typing_dots()

    def _animate_typing_dots(self) -> None:
        if not self._root or not self._visible or self._state != OverlayState.THINKING:
            return

        dots = "." * (self._typing_index + 1)
        self._typing_index = (self._typing_index + 1) % 3

        if self._jarvis_var:
            try:
                self._jarvis_var.set(f"⟳ Đang xử lý{dots}")
            except Exception:
                return
        if self._status_var:
            try:
                self._status_var.set(f"AI đang suy nghĩ{dots}")
            except Exception:
                pass

        try:
            self._typing_job = self._root.after(
                self._typing_interval_ms,
                self._animate_typing_dots,
            )
        except Exception:
            self._typing_job = None

    def _cancel_all_animations(self) -> None:
        if self._root:
            for job_attr in ("_breathing_job", "_typing_job", "_hide_job", "_waveform_job", "_telemetry_job"):
                job = getattr(self, job_attr, None)
                if job:
                    try:
                        self._root.after_cancel(job)
                    except Exception:
                        pass
        self._breathing_job = None
        self._typing_job = None
        self._hide_job = None
        self._waveform_job = None
        self._telemetry_job = None

    def _schedule(self, fn: Callable[[], None]) -> None:
        """Dispatches work safely to Tkinter event thread or runs immediately in headless mode."""
        if self._headless or not self._root:
            try:
                fn()
            except Exception as e:
                logger.debug("Headless execution error: %s", e)
            return

        try:
            self._root.after(0, fn)
        except Exception as e:
            logger.debug("Failed to schedule Tk action: %s", e)
            try:
                fn()
            except Exception:
                pass


JarvisOverlay = AlwaysOnOverlay

__all__ = [
    "OverlayState",
    "OverlayMode",
    "TurnRecord",
    "AlwaysOnOverlay",
    "JarvisOverlay",
    "COLORS",
    "BREATHING_GRADIENT",
    "FONT_FAMILY",
]
