"""
jarvis/proactive/health_monitor.py
==================================
Proactive System Health & Battery Monitor for JARVIS.
Features:
  - Continuous telemetry polling (CPU, RAM, Disk free space, CPU Temp, Battery level).
  - Threshold breach detection:
      * CPU > 90.0%
      * RAM > 85.0%
      * Disk Free < 10.0 GB
      * CPU Temperature > 85.0°C
      * Battery < 20.0% (and not charging)
  - Hysteresis & cooldown debouncing per alert type to prevent notification spam.
  - Automated TTS speech alerts and Overlay notifications.
"""
from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

logger = logging.getLogger("jarvis.proactive.health_monitor")


@dataclass
class HealthAlert:
    """Represents a system health threshold alert."""
    alert_type: str            # 'cpu', 'ram', 'disk', 'cpu_temp', 'battery'
    level: str                 # 'WARNING', 'CRITICAL'
    value: float               # Observed metric value
    threshold: float           # Violated threshold
    message: str               # Spoken alert in Vietnamese
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_type": self.alert_type,
            "level": self.level,
            "value": round(self.value, 1),
            "threshold": round(self.threshold, 1),
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class SystemHealthMonitor:
    """
    Background Telemetry Watchdog with Hysteresis & Cooldown Guards.
    """

    def __init__(
        self,
        hardware_monitor: Any | None = None,
        telemetry_provider: Any | None = None,
        tts_callback: Callable[[str], None] | None = None,
        overlay_callback: Callable[[str, str], None] | None = None,
        check_interval_seconds: float = 5.0,
        cpu_threshold: float = 90.0,
        ram_threshold: float = 85.0,
        disk_min_free_gb: float = 10.0,
        temp_threshold_c: float = 85.0,
        battery_min_percent: float = 20.0,
        cooldown_seconds: float = 60.0,
        hysteresis_delta: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self.hardware_monitor = hardware_monitor
        self.telemetry_provider = telemetry_provider
        self.tts_callback = tts_callback
        self.overlay_callback = overlay_callback
        self.check_interval_seconds = check_interval_seconds

        # Configurable thresholds
        self.cpu_threshold = float(cpu_threshold)
        self.ram_threshold = float(ram_threshold)
        self.disk_min_free_gb = float(disk_min_free_gb)
        self.temp_threshold_c = float(temp_threshold_c)
        self.battery_min_percent = float(battery_min_percent)
        self.cooldown_seconds = float(cooldown_seconds)
        self.hysteresis_delta = float(hysteresis_delta)
        self.enabled = enabled

        # State tracking for debouncing & hysteresis
        self._last_alert_times: dict[str, float] = {}
        self._active_alert_states: dict[str, bool] = {
            "cpu": False,
            "ram": False,
            "disk": False,
            "cpu_temp": False,
            "battery": False,
        }

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._last_metrics: dict[str, Any] = {}

    # ──────────────────────────────────────────────────────────────────────────
    # Telemetry Acquisition
    # ──────────────────────────────────────────────────────────────────────────

    def collect_telemetry(self) -> dict[str, Any]:
        """
        Gathers system telemetry from injected hardware monitor, provider, psutil, or win32 ctypes.
        """
        # 1. Custom telemetry provider (used in tests or special setups)
        if self.telemetry_provider is not None:
            p = self.telemetry_provider
            cpu_pct = getattr(p, "cpu_percent", 0.0)
            ram_pct = getattr(p, "ram_percent", 0.0)
            cpu_temp = getattr(p, "cpu_temp_c", None)
            disk_free_gb = getattr(p, "disk_free_gb", None)
            if disk_free_gb is None and hasattr(p, "disks") and isinstance(p.disks, dict):
                c_disk = p.disks.get("C:") or next(iter(p.disks.values()), None)
                if c_disk:
                    free_bytes = getattr(c_disk, "free_bytes", 0)
                    disk_free_gb = free_bytes / (1024.0 ** 3) if free_bytes else 50.0
            if disk_free_gb is None:
                disk_free_gb = 50.0

            battery_pct = getattr(p, "battery_percent", None)
            battery_plugged = getattr(p, "battery_plugged", True)

            return {
                "cpu_percent": float(cpu_pct),
                "ram_percent": float(ram_pct),
                "cpu_temp_c": float(cpu_temp) if cpu_temp is not None else None,
                "disk_free_gb": float(disk_free_gb),
                "disk_drive": getattr(p, "disk_drive", "C:"),
                "battery_percent": float(battery_pct) if battery_pct is not None else None,
                "battery_plugged": bool(battery_plugged),
            }

        # 2. Existing HardwareMonitor instance
        if self.hardware_monitor is not None:
            try:
                metrics = self.hardware_monitor.get_metrics(use_cache=False)
                cpu_pct = metrics.cpu_percent
                ram_pct = metrics.ram_percent
                cpu_temp = metrics.cpu_temp_c

                # Calculate minimum free space across disks
                min_free_gb = 100.0
                min_drive = "C:"
                if metrics.disks:
                    for d_name, d_stat in metrics.disks.items():
                        free_gb = d_stat.free_bytes / (1024.0 ** 3) if d_stat.free_bytes > 0 else 50.0
                        if free_gb < min_free_gb:
                            min_free_gb = free_gb
                            min_drive = d_name

                batt_pct, batt_plugged = self._probe_battery()
                return {
                    "cpu_percent": float(cpu_pct),
                    "ram_percent": float(ram_pct),
                    "cpu_temp_c": float(cpu_temp) if cpu_temp is not None else None,
                    "disk_free_gb": float(min_free_gb),
                    "disk_drive": min_drive,
                    "battery_percent": batt_pct,
                    "battery_plugged": batt_plugged,
                }
            except Exception as e:
                logger.debug("Error probing hardware_monitor: %s", e)

        # 3. Direct psutil / platform fallback
        cpu_pct = 0.0
        ram_pct = 0.0
        cpu_temp = None
        disk_free_gb = 50.0
        disk_drive = "C:"

        if HAS_PSUTIL:
            try:
                cpu_pct = float(psutil.cpu_percent(interval=None))
                ram_pct = float(psutil.virtual_memory().percent)
                disk_usage = psutil.disk_usage("C:\\" if sys.platform == "win32" else "/")
                disk_free_gb = float(disk_usage.free) / (1024.0 ** 3)
            except Exception as e:
                logger.debug("psutil telemetry fallback error: %s", e)

        batt_pct, batt_plugged = self._probe_battery()
        return {
            "cpu_percent": cpu_pct,
            "ram_percent": ram_pct,
            "cpu_temp_c": cpu_temp,
            "disk_free_gb": disk_free_gb,
            "disk_drive": disk_drive,
            "battery_percent": batt_pct,
            "battery_plugged": batt_plugged,
        }

    def _probe_battery(self) -> tuple[float | None, bool]:
        """Probes battery percentage and AC charging state."""
        # 1. psutil
        if HAS_PSUTIL:
            try:
                batt = psutil.sensors_battery()
                if batt is not None:
                    return float(batt.percent), bool(batt.power_plugged)
            except Exception:
                pass

        # 2. Win32 SYSTEM_POWER_STATUS
        if sys.platform == "win32":
            try:
                class SYSTEM_POWER_STATUS(ctypes.Structure):
                    _fields_ = [
                        ("ACLineStatus", ctypes.c_byte),
                        ("BatteryFlag", ctypes.c_byte),
                        ("BatteryLifePercent", ctypes.c_byte),
                        ("SystemStatusFlag", ctypes.c_byte),
                        ("BatteryLifeTime", ctypes.c_ulong),
                        ("BatteryFullLifeTime", ctypes.c_ulong),
                    ]

                sps = SYSTEM_POWER_STATUS()
                if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
                    ac_plugged = sps.ACLineStatus == 1
                    pct = int(sps.BatteryLifePercent)
                    if 0 <= pct <= 100:
                        return float(pct), ac_plugged
            except Exception:
                pass

        return None, True

    # ──────────────────────────────────────────────────────────────────────────
    # Telemetry Analysis & Alert Dispatching
    # ──────────────────────────────────────────────────────────────────────────

    def check_telemetry(self, now: float | None = None) -> list[HealthAlert]:
        """
        Gathers current metrics, evaluates against thresholds with hysteresis & cooldown,
        and fires alerts if violated.
        Returns list of newly triggered HealthAlert objects.
        """
        if not self.enabled:
            return []

        current_time = time.time() if now is None else float(now)
        telemetry = self.collect_telemetry()
        alerts: list[HealthAlert] = []

        with self._lock:
            self._last_metrics = telemetry

            # 1. CPU Utilization Check (> 90.0%)
            cpu_val = telemetry.get("cpu_percent", 0.0)
            if cpu_val > self.cpu_threshold:
                if self._can_alert("cpu", current_time):
                    self._active_alert_states["cpu"] = True
                    self._last_alert_times["cpu"] = current_time
                    alerts.append(HealthAlert(
                        alert_type="cpu",
                        level="CRITICAL",
                        value=cpu_val,
                        threshold=self.cpu_threshold,
                        message=f"Cảnh báo: CPU đang hoạt động quá tải ở mức {cpu_val:.1f}%.",
                        details={"cpu_percent": cpu_val},
                        timestamp=current_time,
                    ))
            elif cpu_val < (self.cpu_threshold - self.hysteresis_delta):
                self._active_alert_states["cpu"] = False

            # 2. RAM Utilization Check (> 85.0%)
            ram_val = telemetry.get("ram_percent", 0.0)
            if ram_val > self.ram_threshold:
                if self._can_alert("ram", current_time):
                    self._active_alert_states["ram"] = True
                    self._last_alert_times["ram"] = current_time
                    alerts.append(HealthAlert(
                        alert_type="ram",
                        level="CRITICAL",
                        value=ram_val,
                        threshold=self.ram_threshold,
                        message=f"Cảnh báo: Bộ nhớ RAM đang sử dụng {ram_val:.1f}%, vượt ngưỡng an toàn.",
                        details={"ram_percent": ram_val},
                        timestamp=current_time,
                    ))
            elif ram_val < (self.ram_threshold - self.hysteresis_delta):
                self._active_alert_states["ram"] = False

            # 3. Disk Free Space Check (< 10.0 GB)
            disk_free_val = telemetry.get("disk_free_gb", 50.0)
            disk_drive = telemetry.get("disk_drive", "C:")
            if disk_free_val < self.disk_min_free_gb:
                if self._can_alert("disk", current_time):
                    self._active_alert_states["disk"] = True
                    self._last_alert_times["disk"] = current_time
                    alerts.append(HealthAlert(
                        alert_type="disk",
                        level="WARNING",
                        value=disk_free_val,
                        threshold=self.disk_min_free_gb,
                        message=f"Cảnh báo: Dung lượng ổ đĩa {disk_drive} chỉ còn {disk_free_val:.1f} GB.",
                        details={"drive": disk_drive, "free_gb": disk_free_val},
                        timestamp=current_time,
                    ))
            elif disk_free_val > (self.disk_min_free_gb + 2.0):
                self._active_alert_states["disk"] = False

            # 4. CPU Temperature Check (> 85.0°C)
            temp_val = telemetry.get("cpu_temp_c")
            if temp_val is not None and temp_val > self.temp_threshold_c:
                if self._can_alert("cpu_temp", current_time):
                    self._active_alert_states["cpu_temp"] = True
                    self._last_alert_times["cpu_temp"] = current_time
                    alerts.append(HealthAlert(
                        alert_type="cpu_temp",
                        level="CRITICAL",
                        value=temp_val,
                        threshold=self.temp_threshold_c,
                        message=f"Cảnh báo: Nhiệt độ CPU đạt {temp_val:.1f}°C, cần hạ tải.",
                        details={"temp_c": temp_val},
                        timestamp=current_time,
                    ))
            elif temp_val is not None and temp_val < (self.temp_threshold_c - self.hysteresis_delta):
                self._active_alert_states["cpu_temp"] = False

            # 5. Battery Check (< 20.0% and not plugged in)
            batt_val = telemetry.get("battery_percent")
            batt_plugged = telemetry.get("battery_plugged", True)
            if batt_val is not None and batt_val < self.battery_min_percent and not batt_plugged:
                if self._can_alert("battery", current_time):
                    self._active_alert_states["battery"] = True
                    self._last_alert_times["battery"] = current_time
                    alerts.append(HealthAlert(
                        alert_type="battery",
                        level="WARNING",
                        value=batt_val,
                        threshold=self.battery_min_percent,
                        message=f"Thưa Ngài, pin thiết bị còn {batt_val:.0f}%, vui lòng kết nối bộ sạc.",
                        details={"battery_percent": batt_val, "plugged": batt_plugged},
                        timestamp=current_time,
                    ))
            elif batt_val is not None and (batt_val > (self.battery_min_percent + self.hysteresis_delta) or batt_plugged):
                self._active_alert_states["battery"] = False

        # Dispatch alerts to TTS and Overlay
        for alert in alerts:
            self._dispatch_alert(alert)

        return alerts

    def _can_alert(self, alert_type: str, current_time: float) -> bool:
        """Evaluates cooldown timer to prevent alert spamming."""
        last_t = self._last_alert_times.get(alert_type, 0.0)
        return (current_time - last_t) >= self.cooldown_seconds

    def _dispatch_alert(self, alert: HealthAlert) -> None:
        """Dispatches alert to TTS vocalizer and UI Overlay."""
        logger.warning("HEALTH ALERT [%s]: %s", alert.alert_type, alert.message)

        if self.tts_callback:
            try:
                self.tts_callback(alert.message)
            except Exception as e:
                logger.error("Error dispatching health alert TTS: %s", e)

        if self.overlay_callback:
            try:
                title = f"⚠️ Cảnh báo ({alert.alert_type.upper()})"
                self.overlay_callback(title, alert.message)
            except Exception as e:
                logger.error("Error dispatching health alert overlay: %s", e)

    def get_latest_metrics(self) -> dict[str, Any]:
        """Returns the most recent collected metrics snapshot."""
        with self._lock:
            return dict(self._last_metrics)

    def reset_cooldowns(self) -> None:
        """Flushes all alert cooldown timestamps."""
        with self._lock:
            self._last_alert_times.clear()
            for k in self._active_alert_states:
                self._active_alert_states[k] = False

    # ──────────────────────────────────────────────────────────────────────────
    # Background Thread Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Starts background telemetry monitoring loop."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._run_loop,
                name="SystemHealthMonitorWorker",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info("SystemHealthMonitor started.")

    def stop(self) -> None:
        """Stops background telemetry monitoring loop."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None
        logger.info("SystemHealthMonitor stopped.")

    def is_running(self) -> bool:
        """Checks if the background telemetry loop is active."""
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def _run_loop(self) -> None:
        """Periodic background polling loop."""
        while not self._stop_event.is_set():
            try:
                self.check_telemetry()
            except Exception as e:
                logger.error("Unexpected error in SystemHealthMonitor check: %s", e)
            self._stop_event.wait(timeout=self.check_interval_seconds)
