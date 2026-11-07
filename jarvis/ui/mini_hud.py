"""
jarvis/ui/mini_hud.py
=====================
Mini Floating Ambient HUD (Dynamic Island Pill for Windows).
Ultra-lightweight, non-intrusive desktop companion displaying real-time AI states,
listening waveforms, system vitals, and one-click voice interaction.
Consumes 0.00 MiB VRAM and 0% CPU when idle. Headless-safe.
"""
from __future__ import annotations

import logging
import math
import sys
import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from jarvis.personalization.profile import UserProfile, get_user_profile_manager

logger = logging.getLogger("jarvis.ui.mini_hud")


class HUDState(str, Enum):
    """Visual states of the floating HUD pill."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ALERT = "alert"


class MiniAmbientHUD:
    """
    Sleek, transparent floating desktop widget positioned at the screen edge.
    Visualizes JARVIS's cognitive state in real-time.
    """

    def __init__(
        self,
        on_click_callback: Callable[[], None] | None = None,
        on_briefing_callback: Callable[[], None] | None = None,
        initial_x: int | None = None,
        initial_y: int | None = None,
        headless: bool = False,
    ) -> None:
        self.on_click_cb = on_click_callback
        self.on_briefing_cb = on_briefing_callback
        self.initial_x = initial_x
        self.initial_y = initial_y
        self.headless = headless or ("pytest" in sys.modules) or (sys.platform != "win32" and not sys.stdin.isatty())

        self.profile_mgr = get_user_profile_manager()
        self.state: HUDState = HUDState.IDLE
        self.status_text: str = "Sẵn sàng"
        self.is_compact: bool = False
        self._live_audio_level: float = 0.0
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._root: Any = None
        self._canvas: Any = None
        self._anim_phase: float = 0.0
        self._drag_data: dict[str, int] = {"x": 0, "y": 0}
        self._vitals: dict[str, Any] = {"cpu": 0, "ram": 0}

    def start(self) -> None:
        """Start the HUD loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_ui_thread, daemon=True, name="JARVIS-MiniHUD")
        self._thread.start()

    def stop(self) -> None:
        """Stop and tear down the HUD window safely."""
        self._running = False
        if self._root is not None:
            try:
                self._root.after(0, self._destroy_window)
            except Exception:
                pass

    def _destroy_window(self) -> None:
        try:
            if self._root is not None:
                self._root.quit()
                self._root.destroy()
        except Exception:
            pass
        finally:
            self._root = None

    def set_state(self, state: HUDState, text: str | None = None) -> None:
        """Update current cognitive status and text indicator."""
        self.state = state
        if text is not None:
            self.status_text = text
        else:
            profile = self.profile_mgr.get_profile()
            h = profile.honorific
            state_labels = {
                HUDState.IDLE: f"{profile.assistant_name}: Sẵn sàng ({h})",
                HUDState.LISTENING: "🎤 Đang lắng nghe...",
                HUDState.THINKING: "🧠 Đang suy nghĩ...",
                HUDState.SPEAKING: "💬 Đang phản hồi...",
                HUDState.ALERT: "⚠️ Cảnh báo hệ thống",
            }
            self.status_text = state_labels.get(state, f"{profile.assistant_name}: Sẵn sàng")

    def _run_ui_thread(self) -> None:
        """Internal Tkinter message loop thread."""
        if self.headless:
            logger.info("MiniAmbientHUD running in headless/mock mode (no Win32 GUI).")
            while self._running:
                time.sleep(0.5)
            return

        try:
            import tkinter as tk
            root = tk.Tk()
            self._root = root

            root.title("JARVIS Mini HUD")
            root.overrideredirect(True)      # Borderless frameless window
            root.attributes("-topmost", True) # Always on top
            root.attributes("-alpha", 0.92)  # High-tech semi-transparency

            # Pill dimensions
            width, height = 270, 44
            screen_w = root.winfo_screenwidth()
            pos_x = self.initial_x if self.initial_x is not None else (screen_w - width - 24)
            pos_y = self.initial_y if self.initial_y is not None else 32
            root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

            # Canvas for custom high-tech rendering
            bg_color = "#0a0e17"
            canvas = tk.Canvas(
                root,
                width=width,
                height=height,
                bg=bg_color,
                highlightthickness=1,
                highlightbackground="#00f0ff",
            )
            canvas.pack(fill="both", expand=True)
            self._canvas = canvas

            # Draggable window event bindings
            canvas.bind("<Button-1>", self._on_mouse_down)
            canvas.bind("<B1-Motion>", self._on_mouse_drag)
            canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
            canvas.bind("<Double-Button-1>", self._on_double_click)
            canvas.bind("<Button-3>", self._on_right_click)

            # Start animation tick
            self.set_state(HUDState.IDLE)
            self._tick_animation()

            root.mainloop()
        except Exception as exc:
            logger.warning(f"MiniAmbientHUD GUI initialization failed: {exc}. Falling back to headless.")
            while self._running:
                time.sleep(0.5)

    def _on_mouse_down(self, event: Any) -> None:
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self._drag_data["moved"] = 0

    def _on_mouse_drag(self, event: Any) -> None:
        if self._root is None:
            return
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        self._drag_data["moved"] = abs(dx) + abs(dy)
        new_x = self._root.winfo_x() + dx
        new_y = self._root.winfo_y() + dy
        self._root.geometry(f"+{new_x}+{new_y}")

    def toggle_compact(self) -> None:
        """Toggle between minimal Arc Reactor icon (48x48) and full Dynamic Island pill (270x44)."""
        self.is_compact = not self.is_compact
        if self._root is not None and self._canvas is not None:
            try:
                w, h = (48, 48) if self.is_compact else (270, 44)
                cur_x = self._root.winfo_x()
                cur_y = self._root.winfo_y()
                self._root.geometry(f"{w}x{h}+{cur_x}+{cur_y}")
                self._canvas.config(width=w, height=h)
            except Exception as exc:
                logger.debug(f"Failed toggling HUD compact mode: {exc}")

    def feed_audio_energy(self, level: float) -> None:
        """Update live audio energy level (0.0 to 1.0) for responsive waveform rendering."""
        self._live_audio_level = max(0.0, min(1.0, float(level)))

    def _on_double_click(self, event: Any) -> None:
        self.toggle_compact()

    def _on_mouse_up(self, event: Any) -> None:
        # If clicked without dragging, trigger callback or toggle state
        if self._drag_data.get("moved", 0) < 5:
            if self.on_click_cb is not None:
                try:
                    self.on_click_cb()
                except Exception as exc:
                    logger.debug(f"HUD click callback error: {exc}")
            else:
                self._cycle_state()

    def _on_right_click(self, event: Any) -> None:
        if self._root is None:
            return
        try:
            import tkinter as tk
            menu = tk.Menu(self._root, tearoff=0, bg="#101827", fg="#00f0ff")
            if self.on_briefing_cb:
                menu.add_command(label="🌅 Báo Cáo Buổi Sáng", command=self.on_briefing_cb)
            menu.add_command(label="🔄 Chuyển Trạng Thái", command=self._cycle_state)
            menu.add_command(label="📐 Thu Nhỏ / Phóng To", command=self.toggle_compact)
            menu.add_separator()
            menu.add_command(label="❌ Đóng HUD", command=self.stop)
            menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    def _cycle_state(self) -> None:
        states = [HUDState.IDLE, HUDState.LISTENING, HUDState.THINKING, HUDState.SPEAKING]
        idx = (states.index(self.state) + 1) % len(states)
        self.set_state(states[idx])

    def _tick_animation(self) -> None:
        """High-FPS animation timer updating waveform bars and state aura."""
        if not self._running or self._canvas is None:
            return

        self._anim_phase += 0.15
        self._render_hud_elements()

        # Reschedule next frame (~30 FPS)
        if self._root is not None:
            self._root.after(33, self._tick_animation)

    def _render_hud_elements(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return

        canvas.delete("all")
        width, height = 270, 44

        # 1. State indicator (Arc-Reactor dot with pulse aura)
        aura_colors = {
            HUDState.IDLE: ("#00f0ff", "#004455"),
            HUDState.LISTENING: ("#ffaa00", "#553300"),
            HUDState.THINKING: ("#cc66ff", "#441155"),
            HUDState.SPEAKING: ("#00ff88", "#004422"),
            HUDState.ALERT: ("#ff3366", "#551122"),
        }
        fg_col, aura_col = aura_colors.get(self.state, ("#00f0ff", "#004455"))

        if self.is_compact:
            # Compact Mode: 48x48 centered glowing Arc Reactor
            cx, cy = 24, 24
            pulse_r = 14 + 4 * math.sin(self._anim_phase)
            canvas.create_oval(cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r, outline=aura_col, width=2)
            canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill=fg_col, outline="")
            return

        cx, cy = 20, 22
        # Pulsing ring
        pulse_r = 8 + 3 * math.sin(self._anim_phase)
        canvas.create_oval(cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r, outline=aura_col, width=2)
        # Inner glowing core
        canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=fg_col, outline="")

        # 2. Status Text
        canvas.create_text(
            40,
            22,
            text=self.status_text,
            fill="#e0f8ff",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )

        # 3. Dynamic Waveform Spectrum (5 mini bars on the right, modulated by audio energy)
        bar_x = 220
        audio_boost = self._live_audio_level * 12.0
        for i in range(5):
            if self.state in (HUDState.LISTENING, HUDState.SPEAKING):
                h = 4 + audio_boost + 8 * abs(math.sin(self._anim_phase * 1.5 + i * 0.7))
            elif self.state == HUDState.THINKING:
                h = 4 + 6 * abs(math.sin(self._anim_phase * 2.0 + i * 0.5))
            else:
                h = 4
            bx = bar_x + i * 7
            canvas.create_line(bx, cy - h / 2, bx, cy + h / 2, fill=fg_col, width=2, capstyle="round")
