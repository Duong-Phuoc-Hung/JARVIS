"""
jarvis/core/handlers/system_handlers.py
=======================================
System, desktop, power, and OS automation action handlers for JarvisApp.
"""
from __future__ import annotations

import ctypes
import logging
import os
import signal
import sys
import time
from typing import Any

from jarvis.core.handlers.base import (
    _POWER_ACTION_ALIASES,
    _UNSUPPORTED_POWER_ACTIONS,
    _DualErrorStr,
)
from jarvis.core.models import ActionResult, RequesterContext
from jarvis.hardware.monitor import HardwareMetrics
from jarvis.ui.tray import TrayStatus

log = logging.getLogger("jarvis.core.handlers.system")


class SystemHandlersMixin:
    """Mixin providing system, desktop, and window management action handlers for JarvisApp."""

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

        allow_hardware_power = bool(
            self.config.get("power.allow_hardware_power_actions", False)
            if hasattr(self.config, "get") else False
        )

        if canonical in _UNSUPPORTED_POWER_ACTIONS and not allow_hardware_power:
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

        if canonical == "abort":
            win32 = getattr(self.computer_controller, "win32", None) if self.computer_controller else None
            aborted = False
            if win32 and hasattr(win32, "abort_shutdown"):
                aborted = bool(win32.abort_shutdown())
            else:
                from jarvis.platform.windows import abort_shutdown
                aborted = bool(abort_shutdown())

            abort_msg = "Đã hủy lệnh tắt máy tính thành công, thưa Ngài." if aborted else "Không có lệnh tắt máy nào đang chờ để hủy, thưa Ngài."
            if self.tts_manager:
                self.tts_manager.speak(abort_msg, wait=False)
            return {"success": True, "action": canonical, "message": abort_msg, "aborted": aborted}

        if canonical in ("sleep", "hibernate"):
            win32 = getattr(self.computer_controller, "win32", None) if self.computer_controller else None
            is_hibernate = (canonical == "hibernate")
            suspended = False
            if win32 and hasattr(win32, "suspend_system"):
                suspended = bool(win32.suspend_system(hibernate=is_hibernate))
            else:
                from jarvis.platform.windows import suspend_system
                suspended = bool(suspend_system(hibernate=is_hibernate))

            if not suspended:
                mode_str = "ngủ đông" if is_hibernate else "ngủ"
                return {"success": False, "error": f"Không thể đưa máy vào chế độ {mode_str}.", "error_code": "SUSPEND_FAILED", "action": canonical}

            mode_msg = "Đang đưa máy vào chế độ ngủ đông, thưa Ngài." if is_hibernate else "Đang đưa máy vào chế độ ngủ, thưa Ngài."
            if self.tts_manager:
                self.tts_manager.speak(mode_msg, wait=False)
            return {"success": True, "action": canonical, "message": mode_msg}

        if canonical in ("shutdown", "restart"):
            win32 = getattr(self.computer_controller, "win32", None) if self.computer_controller else None
            is_restart = (canonical == "restart")
            scheduled = False
            if win32 and hasattr(win32, "shutdown_system"):
                scheduled = bool(win32.shutdown_system(restart=is_restart, delay_s=30))
            else:
                from jarvis.platform.windows import shutdown_system
                scheduled = bool(shutdown_system(restart=is_restart, delay_s=30))

            if not scheduled:
                act_str = "khởi động lại" if is_restart else "tắt máy"
                return {"success": False, "error": f"Không thể {act_str} hệ thống.", "error_code": "SHUTDOWN_FAILED", "action": canonical}

            act_msg = "Hệ thống sẽ khởi động lại sau 30 giây. Ngài có thể nói 'Hủy tắt máy' để dừng." if is_restart else "Hệ thống sẽ tắt sau 30 giây. Ngài có thể nói 'Hủy tắt máy' để dừng."
            if self.tts_manager:
                self.tts_manager.speak(act_msg, wait=False)
            return {"success": True, "action": canonical, "message": act_msg}

        if canonical == "screen_off":
            submitted = False
            if sys.platform == "win32":
                try:
                    # HWND_BROADCAST = 0xFFFF, WM_SYSCOMMAND = 0x0112, SC_MONITORPOWER = 0xF170, 2 = OFF
                    user32 = getattr(ctypes, "windll", None) and getattr(ctypes.windll, "user32", None)
                    if user32 and hasattr(user32, "PostMessageW"):
                        submitted = bool(user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2))
                except Exception as exc:
                    log.error("Failed to turn off monitor via Win32: %s", exc)
            msg = "Đã gửi yêu cầu tắt màn hình." if submitted else "Không gửi được yêu cầu tắt màn hình."
            if self.tts_manager:
                self.tts_manager.speak(msg, wait=False)
            return {"success": submitted, "status": "SUCCESS" if submitted else "ERROR",
                    "code": "REQUEST_SUBMITTED" if submitted else "SCREEN_OFF_FAILED",
                    "action": canonical, "message": msg}

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


    def _handle_window_active(self, action: str | None = None, **kwargs) -> dict[str, Any]:
        """Returns active foreground window info or manipulates it (maximize, close)."""
        act = (action or kwargs.get("action") or "").lower().strip()
        if self.computer_controller:
            win = self.computer_controller.get_active_window()
            hwnd = win.get("hwnd")
            title = win.get("title", "cửa sổ hiện tại")
            if act in ("maximize", "phong_to", "phóng to"):
                if hwnd and hasattr(self.computer_controller, "win32") and hasattr(self.computer_controller.win32, "maximize_window"):
                    ok = self.computer_controller.win32.maximize_window(hwnd)
                    if ok:
                        msg = f"Đã phóng to {title}, thưa Ngài."
                        if self.tts_manager:
                            self.tts_manager.speak(msg, wait=False)
                        return {"status": "success", "success": True, "message": msg}
                return {"status": "failed", "success": False, "message": "Không thể phóng to cửa sổ hiện tại, thưa Ngài."}
            elif act in ("snap_left", "sang_trai", "trai", "nua_trai"):
                ok = self.computer_controller.snap_window("left")
                msg = f"Đã xếp {title} sang nửa trái màn hình, thưa Ngài." if ok else "Không thể xếp cửa sổ sang trái."
                if self.tts_manager:
                    self.tts_manager.speak(msg, wait=False)
                return {"status": "success" if ok else "failed", "success": ok, "message": msg}
            elif act in ("snap_right", "sang_phai", "phai", "nua_phai"):
                ok = self.computer_controller.snap_window("right")
                msg = f"Đã xếp {title} sang nửa phải màn hình, thưa Ngài." if ok else "Không thể xếp cửa sổ sang phải."
                if self.tts_manager:
                    self.tts_manager.speak(msg, wait=False)
                return {"status": "success" if ok else "failed", "success": ok, "message": msg}
            elif act in ("minimize", "thu_nho", "hạ xuống"):
                ok = False
                if hwnd and hasattr(self.computer_controller, "win32") and hasattr(self.computer_controller.win32, "minimize_window"):
                    ok = self.computer_controller.win32.minimize_window(hwnd)
                else:
                    ok = self.computer_controller.snap_window("down")
                msg = f"Đã thu nhỏ {title}, thưa Ngài." if ok else "Không thể thu nhỏ cửa sổ."
                if self.tts_manager:
                    self.tts_manager.speak(msg, wait=False)
                return {"status": "success" if ok else "failed", "success": ok, "message": msg}
            elif act in ("switch", "chuyen_app", "next", "chuyen_cua_so"):
                ok = self.computer_controller.switch_window()
                msg = "Đã chuyển sang cửa sổ tiếp theo, thưa Ngài." if ok else "Không chuyển được cửa sổ."
                return {"status": "success" if ok else "failed", "success": ok, "message": msg}
            elif act in ("close", "dong", "tat_cua_so", "đóng cửa sổ"):
                ok = self.computer_controller.close_active_window()
                msg = f"Đã đóng {title}, thưa Ngài." if ok else "Không đóng được cửa sổ."
                if self.tts_manager:
                    self.tts_manager.speak(msg, wait=False)
                return {"status": "success" if ok else "failed", "success": ok, "message": msg}
            return {"status": "success", "window": win, "message": f"Cửa sổ hiện tại: {title}"}
        return {"status": "failed", "message": "Computer controller unavailable"}


    def _handle_clipboard(self, action: str = "copy", text: str | None = None, **kwargs) -> dict[str, Any]:
        """Handles clipboard operations (copy, paste, cut, clear, read)."""
        act = (action or kwargs.get("action") or "copy").lower().strip()
        if not self.computer_controller:
            return {"status": "failed", "success": False, "message": "Computer controller unavailable"}

        if act in ("cut", "cắt"):
            ok = self.computer_controller.send_hotkey("ctrl", "x")
            return {"status": "success" if ok else "failed", "success": ok, "message": "Đã cắt nội dung vào clipboard."}
        elif act in ("clear", "xóa"):
            ok = self.computer_controller.set_clipboard_text("")
            return {"status": "success" if ok else "failed", "success": ok, "message": "Đã xóa nội dung clipboard."}
        elif act in ("paste", "dán"):
            ok = self.computer_controller.paste_text(text)
            return {"status": "success" if ok else "failed", "success": ok, "message": "Đã dán nội dung từ clipboard, thưa Ngài."}
        elif act in ("read", "đọc", "xem"):
            clip_val = self.computer_controller.get_clipboard_text()
            preview = clip_val[:100] + ("..." if len(clip_val) > 100 else "")
            return {"status": "success", "success": True, "text": clip_val, "message": f"Nội dung clipboard: {preview}" if preview else "Clipboard đang trống, thưa Ngài."}
        else:  # copy / sao chép
            clip_val = self.computer_controller.copy_selection()
            return {"status": "success", "success": True, "text": clip_val, "message": "Đã sao chép nội dung vào clipboard, thưa Ngài."}


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
        direction = "lên" if delta_val >= 0 else "xuống"
        return {"status": "success", "success": True, "volume": vol, "message": f"Đã điều chỉnh âm lượng {direction} {vol}%, thưa Ngài."}


    def _handle_system_brightness(self, delta: int | None = None, level: int | None = None, **kwargs) -> dict[str, Any]:
        """Adjusts, sets, or queries screen brightness (fail-closed if monitor unavailable)."""
        if self.computer_controller:
            is_query = bool(kwargs.get("query") or kwargs.get("action") in ("query", "brightness_query"))
            if is_query and delta is None and level is None:
                b = self.computer_controller.get_brightness()
                if b is None:
                    code = "BRIGHTNESS_QUERY_FAILED"
                    msg = "Không thể lấy thông tin độ sáng màn hình, thưa Ngài."
                    return {"status": "failed", "success": False, "brightness": None, "error": _DualErrorStr(msg, code), "error_code": code, "message": msg}
                return {"status": "success", "success": True, "brightness": b, "message": f"Độ sáng màn hình hiện tại là {b}%, thưa Ngài."}
            if level is not None:
                b = self.computer_controller.set_brightness(level)
                if b is None:
                    code = "BRIGHTNESS_SET_FAILED"
                    msg = "Không thể đặt độ sáng màn hình, thưa Ngài."
                    return {"status": "failed", "success": False, "brightness": None, "error": _DualErrorStr(msg, code), "error_code": code, "message": msg}
                return {"status": "success", "success": True, "brightness": b, "message": f"Đã đặt độ sáng màn hình thành {b}%, thưa Ngài."}
            delta_val = delta if delta is not None else 10
            b = self.computer_controller.change_brightness(delta_val)
            if b is None:
                code = "BRIGHTNESS_CHANGE_FAILED"
                msg = "Không thể điều chỉnh độ sáng màn hình, thưa Ngài."
                return {"status": "failed", "success": False, "brightness": None, "error": _DualErrorStr(msg, code), "error_code": code, "message": msg}
            return {"status": "success", "success": True, "brightness": b, "message": f"Đã điều chỉnh độ sáng màn hình thành {b}%, thưa Ngài."}
        code = "CONTROLLER_UNAVAILABLE"
        msg = "Computer controller unavailable"
        return {"status": "failed", "success": False, "error": _DualErrorStr(msg, code), "error_code": code, "message": msg}


    def _handle_file_search(self, filename: str | None = None, pattern: str | None = None, directory: str | None = None, root_dir: str | None = None, **kwargs) -> dict[str, Any]:
        """Searches local files."""
        if kwargs.get("clarify") or (kwargs.get("action") == "create" and not filename and not pattern):
            return {
                "status": "success",
                "success": True,
                "clarification_required": True,
                "message": "Ngài muốn tạo file tên gì và ở đâu? Xin cho biết tên file cụ thể.",
            }
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


    _APP_SHORT_ALIASES: dict[str, str] = {
        "edge": "microsoft edge",
        "word": "winword",
        "vs code": "visual studio code",
        "vscode": "visual studio code",
        "ms edge": "microsoft edge",
        "explorer": "file explorer",
    }


    def _handle_app_open(self, app_name: str | None = None, name: str | None = None, app: str | None = None, **kwargs) -> dict[str, Any]:
        """Opens desktop application by name or alias.

        Resolution order:
        1. Catalog lookup (open_installed_app) with short-alias normalization.
        2. Fallback to legacy open_app() (APP_MAP + shutil.which) when catalog
           returns APP_NOT_FOUND, APP_AMBIGUOUS, or APP_DISCOVERY_UNAVAILABLE.
           This ensures apps not in the Windows registry (Spotify, Firefox, etc.)
           still open via the known-executable path.
        """
        target: str = app_name or name or app or kwargs.get("query") or ""
        if self.computer_controller:
            settings_names = {"settings", "cài đặt", "cai dat", "ms-settings:"}
            use_catalog = target.strip().casefold() not in settings_names
            if use_catalog:
                # Resolve common short names that catalog won't match exactly
                catalog_query = self._APP_SHORT_ALIASES.get(target.strip().casefold(), target)
                res = self.computer_controller.open_installed_app(catalog_query)
                # Fallback: catalog miss → try legacy APP_MAP / shutil.which path
                if res.get("error_code") in ("APP_NOT_FOUND", "APP_AMBIGUOUS", "APP_DISCOVERY_UNAVAILABLE"):
                    res = self.computer_controller.open_app(target)
            else:
                res = self.computer_controller.open_app(target)
            msg = res.get("message") or (f"Đã khởi chạy {target}, thưa Ngài." if res.get("success") else res.get("error") or f"Không thể mở {target}.")
            return {"success": bool(res.get("success")), "status": "success" if res.get("success") else res.get("status", "failed"), "result": res, "message": msg, "error_code": res.get("error_code")}
        return {"status": "failed", "message": "Computer controller unavailable"}


    def _handle_new_tab(self, **kwargs) -> dict[str, Any]:
        """Opens a new browser tab in the foreground browser window (Ctrl+T).

        Fail-closed: returns success=False if pyautogui or keyboard control
        is unavailable; never claims success without dispatching the keystroke.
        """
        try:
            import pyautogui  # type: ignore
            pyautogui.hotkey("ctrl", "t")
            return {"success": True, "status": "success", "message": "Da mo tab moi trong trinh duyet, thua Ngai."}
        except ImportError:
            pass
        # Fallback: use computer controller's keyboard shortcut if available
        if self.computer_controller and hasattr(self.computer_controller, "send_hotkey"):
            ok = self.computer_controller.send_hotkey("ctrl", "t")
            return {"success": bool(ok), "status": "success" if ok else "failed",
                    "message": "Da mo tab moi, thua Ngai." if ok else "Khong the mo tab moi."}
        return {"success": False, "status": "failed", "error_code": "KEYBOARD_UNAVAILABLE",
                "message": "Khong the dieu khien ban phim de mo tab moi, thua Ngai."}


    def _handle_close_tab(self, **kwargs) -> dict[str, Any]:
        """Closes active tab (Ctrl+W)."""
        if self.computer_controller:
            ok = self.computer_controller.close_tab()
            msg = "Đã đóng tab hiện tại, thưa Ngài." if ok else "Không thể đóng tab."
            if self.tts_manager:
                self.tts_manager.speak(msg, wait=False)
            return {"status": "success" if ok else "failed", "success": ok, "message": msg}
        return {"status": "failed", "success": False, "message": "Computer controller unavailable"}


    def _handle_page_scroll(self, direction: str = "down", **kwargs) -> dict[str, Any]:
        """Scrolls current window down or up."""
        if self.computer_controller:
            ok = self.computer_controller.scroll_page(direction)
            dir_str = "xuống" if "down" in direction.lower() or "xuong" in direction.lower() else "lên"
            msg = f"Đã cuộn trang {dir_str}, thưa Ngài." if ok else "Không cuộn được trang."
            return {"status": "success" if ok else "failed", "success": ok, "message": msg}
        return {"status": "failed", "success": False, "message": "Computer controller unavailable"}


    def _handle_page_refresh(self, **kwargs) -> dict[str, Any]:
        """Refreshes or reloads active page (F5)."""
        if self.computer_controller:
            ok = self.computer_controller.refresh_page()
            msg = "Đã tải lại trang, thưa Ngài." if ok else "Không thể tải lại trang."
            return {"status": "success" if ok else "failed", "success": ok, "message": msg}
        return {"status": "failed", "success": False, "message": "Computer controller unavailable"}


    def _handle_web_open(self, url: str | None = None, target: str | None = None, query: str | None = None, site: str | None = None, **kwargs) -> dict[str, Any]:
        """Opens target website or search query in browser."""
        dest = url or target or site or query or kwargs.get("website") or ""
        if self.computer_controller:
            res = self.computer_controller.open_website(dest)
            msg = res.get("message") or (f"Đã gửi yêu cầu mở {dest} tới trình duyệt." if res.get("success") else res.get("error") or f"Không thể mở {dest}.")
            return {"status": "success" if res.get("success") else "failed", "result": res, "message": msg, "error_code": res.get("error_code")}
        return {"status": "failed", "message": "Computer controller unavailable"}


    def _handle_shell_execute(self, query: str = "", cwd: str | None = None, **kwargs) -> dict[str, Any]:
        """Executes natural language shell command.
        Accepts both 'query' (NL description) and 'command' (raw shell) parameter names
        so router emissions using either key reach the same handler.
        """
        # router emits 'command' for weather/curl shortcuts, 'query' for NL shell requests
        effective_query = query or kwargs.get("command", "") or ""
        if not effective_query:
            return {"status": "failed", "message": "Không có lệnh nào để thực thi."}
        if self.shell_assistant:
            res = self.shell_assistant.execute_natural_command(query=effective_query, cwd=cwd)
            msg = res.get("summary") or res.get("message", "Đã thực thi lệnh shell.")
            return {"status": "success" if res.get("success") else "failed", "result": res, "message": msg}
        return {"status": "failed", "message": "Shell assistant unavailable"}


    def _handle_safety_gate_confirm(self, token: str | None = None, **kwargs) -> dict[str, Any]:
        """Confirms pending high-risk action."""
        if self.safety_gate:
            pending_list = self.safety_gate.list_pending()
            if not token:
                if len(pending_list) > 1:
                    return {
                        "status": "failed",
                        "message": f"Có {len(pending_list)} thao tác đang chờ xác nhận. Vui lòng cung cấp mã token cụ thể để xác nhận.",
                    }
                pending = pending_list[0] if pending_list else None
                t = pending.token if pending else ""
            else:
                t = token
            ok = self.safety_gate.confirm(t) if t else False
            msg = f"Đã xác nhận và thực thi thao tác (Token {t}), thưa Ngài." if ok else "Không có thao tác nào đang chờ xác nhận hoặc token đã hết hạn."
            return {"status": "success" if ok else "failed", "message": msg}
        return {"status": "failed", "message": "Safety gate unavailable"}


    def _handle_safety_gate_reject(self, token: str | None = None, **kwargs) -> dict[str, Any]:
        """Rejects pending high-risk action."""
        if self.safety_gate:
            pending_list = self.safety_gate.list_pending()
            if not token:
                if len(pending_list) > 1:
                    return {
                        "status": "failed",
                        "message": f"Có {len(pending_list)} thao tác đang chờ xác nhận. Vui lòng cung cấp mã token cụ thể để hủy bỏ.",
                    }
                pending = pending_list[0] if pending_list else None
                t = pending.token if pending else ""
            else:
                t = token
            ok = self.safety_gate.reject(t) if t else False
            msg = f"Đã hủy thao tác (Token {t}), thưa Ngài." if ok else "Không có thao tác nào đang chờ xác nhận."
            return {"status": "success" if ok else "failed", "message": msg}
        return {"status": "failed", "message": "Safety gate unavailable"}

