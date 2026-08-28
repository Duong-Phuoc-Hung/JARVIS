"""
jarvis/hardware/monitor.py
==========================
Hardware Telemetry Collector and S.M.A.R.T. Disk Health Prober.
Features:
  - F-20: Multi-tier hardware telemetry collector (CPU, GPU, RAM, VRAM, fan speeds).
  - F-21: S.M.A.R.T. disk health diagnostics and filesystem volume capacity prober.
  - F-22: Threshold checking with debouncing and bilingual voice summaries.
"""
from __future__ import annotations

import ctypes
import json
import logging
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

log = logging.getLogger("jarvis.hardware.monitor")


# ---------------------------------------------------------------------------
# Win32 Ctypes Structures for Zero-Dependency Telemetry
# ---------------------------------------------------------------------------

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


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


def _filetime_to_uint64(ft: FILETIME) -> int:
    return (ft.dwHighDateTime << 32) + ft.dwLowDateTime


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class DiskSmartMetrics:
    """Detailed S.M.A.R.T. and volume metrics for a storage drive."""
    drive: str                                   # e.g. "C:" or "\\\\.\\PHYSICALDRIVE0"
    status: str = "PASSED"                      # "PASSED", "WARNING", "FAILING", "UNKNOWN"
    model: str = ""                             # e.g. "NVMe SSD"
    media_type: str = "SSD"                     # "SSD", "HDD", "NVMe"
    temperature_c: int | None = None         # Storage temperature in °C
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    percent_used: float = 0.0
    reallocated_sectors: int = 0
    reported_uncorrectable_errors: int = 0
    wear_range_delta_life_pct: int | None = None
    power_on_hours: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "drive": self.drive,
            "status": self.status,
            "model": self.model,
            "media_type": self.media_type,
            "temperature_c": self.temperature_c,
            "total_bytes": self.total_bytes,
            "used_bytes": self.used_bytes,
            "free_bytes": self.free_bytes,
            "percent_used": round(self.percent_used, 1),
            "reallocated_sectors": self.reallocated_sectors,
            "reported_uncorrectable_errors": self.reported_uncorrectable_errors,
            "wear_range_delta_life_pct": self.wear_range_delta_life_pct,
            "power_on_hours": self.power_on_hours,
        }


# Alias for backward compatibility with tests
DiskSmartStatus = DiskSmartMetrics


@dataclass
class HardwareMetrics:
    """Comprehensive snapshot of hardware sensor metrics."""
    cpu_percent: float                          # Total CPU utilization (0.0 to 100.0)
    cpu_temp_c: float | None                 # CPU package temperature in °C (or None)
    gpu_percent: float | None                # GPU utilization % (or None if no dedicated GPU)
    gpu_temp_c: float | None                 # GPU temperature in °C (or None)
    ram_percent: float                          # RAM utilization (0.0 to 100.0)
    vram_used_gb: float | None               # VRAM used in GB (or None)
    smart_status: str                           # Overall S.M.A.R.T. health ("PASSED", "WARNING", "FAILING")
    per_cpu_percent: list[float] = field(default_factory=list)
    cpu_freq_mhz: float | None = None
    gpu_fan_speed_rpm: int | None = None
    gpu_fan_percent: int | None = None
    vram_total_gb: float | None = None
    ram_total_bytes: int = 0
    ram_used_bytes: int = 0
    disks: dict[str, DiskSmartMetrics] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to JSON-serializable dictionary."""
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "cpu_temp_c": round(self.cpu_temp_c, 1) if self.cpu_temp_c is not None else None,
            "per_cpu_percent": [round(c, 1) for c in self.per_cpu_percent],
            "cpu_freq_mhz": round(self.cpu_freq_mhz, 1) if self.cpu_freq_mhz is not None else None,
            "gpu_percent": round(self.gpu_percent, 1) if self.gpu_percent is not None else None,
            "gpu_temp_c": round(self.gpu_temp_c, 1) if self.gpu_temp_c is not None else None,
            "gpu_fan_speed_rpm": self.gpu_fan_speed_rpm,
            "gpu_fan_percent": self.gpu_fan_percent,
            "ram_percent": round(self.ram_percent, 1),
            "ram_total_bytes": self.ram_total_bytes,
            "ram_used_bytes": self.ram_used_bytes,
            "vram_used_gb": round(self.vram_used_gb, 2) if self.vram_used_gb is not None else None,
            "vram_total_gb": round(self.vram_total_gb, 2) if self.vram_total_gb is not None else None,
            "smart_status": self.smart_status,
            "disks": {k: v.to_dict() for k, v in self.disks.items()},
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# HardwareMonitor Engine
# ---------------------------------------------------------------------------

class HardwareMonitor:
    """
    Multi-source hardware telemetry collector and S.M.A.R.T. diagnostic engine.
    Probes CPU, GPU, RAM, VRAM, thermal counters, and storage drives via Win32 ctypes,
    PowerShell CIM, nvidia-smi, and psutil with resilient zero-crash fallback.
    """

    def __init__(
        self,
        provider: Any | None = None,
        cpu_temp_threshold: float = 85.0,
        ram_threshold: float = 90.0,
        gpu_temp_threshold: float = 85.0,
        disk_free_threshold_gb: float = 10.0,
        alert_cooldown_s: float = 5.0,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.provider = provider
        self.config = config or {}

        # Config overrides
        hw_cfg = self.config.get("hardware", {})
        thresh_cfg = hw_cfg.get("thresholds", {})

        self.cpu_temp_threshold = thresh_cfg.get("cpu_temp_c", cpu_temp_threshold)
        self.ram_threshold = thresh_cfg.get("ram_percent", ram_threshold)
        self.gpu_temp_threshold = thresh_cfg.get("gpu_temp_c", gpu_temp_threshold)
        self.disk_free_threshold_gb = thresh_cfg.get("disk_free_gb", disk_free_threshold_gb)
        self.alert_cooldown_s = hw_cfg.get("alert_cooldown_s", alert_cooldown_s)

        # Alert tracking
        self.last_alert_time: float = 0.0
        self.last_alert_times: dict[str, float] = {}

        # CPU calculation state for kernel32.GetSystemTimes
        self._prev_idle_time: int | None = None
        self._prev_kernel_time: int | None = None
        self._prev_user_time: int | None = None
        self._prev_times_ts: float = 0.0

        # Subprocess cache for PowerShell CIM queries to avoid spamming
        self._cached_cim_temp: float | None = None
        self._cached_cim_temp_ts: float = 0.0
        self._cached_disks: dict[str, DiskSmartMetrics] = {}
        self._cached_disks_ts: float = 0.0

        # Check nvidia-smi presence
        self._nvidia_smi_path: str | None = shutil.which("nvidia-smi")

    # -----------------------------------------------------------------------
    # Core Telemetry Collection
    # -----------------------------------------------------------------------

    def get_metrics(self, use_cache: bool = True) -> HardwareMetrics:
        """Collect and return real-time system metrics snapshot."""
        # 1. Test Mock Provider (Tier 1)
        if self.provider is not None:
            return self._get_metrics_from_provider()

        # 2. Live System Probing (Tier 2-5)
        ram_pct, ram_total, ram_used = self._probe_ram()
        cpu_pct, per_cpu, cpu_freq = self._probe_cpu()
        cpu_temp = self._probe_cpu_temperature()
        gpu_pct, gpu_temp, vram_used_gb, vram_total_gb, fan_rpm, fan_pct = self._probe_gpu()
        disks = self.get_disk_smart_status(use_cache=use_cache)
        smart_status = self._aggregate_smart_status(disks)

        return HardwareMetrics(
            cpu_percent=cpu_pct,
            cpu_temp_c=cpu_temp,
            per_cpu_percent=per_cpu,
            cpu_freq_mhz=cpu_freq,
            gpu_percent=gpu_pct,
            gpu_temp_c=gpu_temp,
            gpu_fan_speed_rpm=fan_rpm,
            gpu_fan_percent=fan_pct,
            ram_percent=ram_pct,
            ram_total_bytes=ram_total,
            ram_used_bytes=ram_used,
            vram_used_gb=vram_used_gb,
            vram_total_gb=vram_total_gb,
            smart_status=smart_status,
            disks=disks,
            timestamp=time.time(),
        )

    def _get_metrics_from_provider(self) -> HardwareMetrics:
        """Extract metrics from injected mock provider in tests."""
        p = self.provider

        cpu_pct = getattr(p, "cpu_percent", 0.0)
        cpu_temp = getattr(p, "cpu_temp_c", None)
        per_cpu = getattr(p, "per_cpu_percent", [])
        cpu_freq = getattr(p, "cpu_freq_mhz", None)

        # GPU metrics
        gpu_pct = getattr(p, "gpu_util_percent", getattr(p, "gpu_percent", None))
        gpu_temp = getattr(p, "gpu_temp_c", None)
        fan_rpm = getattr(p, "gpu_fan_speed_rpm", None)
        fan_pct = getattr(p, "gpu_fan_percent", None)

        # VRAM metrics
        vram_used_gb = None
        if hasattr(p, "vram_used_bytes") and p.vram_used_bytes is not None:
            vram_used_gb = p.vram_used_bytes / (1024.0 ** 3)
        elif hasattr(p, "vram_used_gb"):
            vram_used_gb = p.vram_used_gb

        vram_total_gb = None
        if hasattr(p, "vram_total_bytes") and p.vram_total_bytes is not None:
            vram_total_gb = p.vram_total_bytes / (1024.0 ** 3)
        elif hasattr(p, "vram_total_gb"):
            vram_total_gb = p.vram_total_gb

        # RAM metrics
        ram_pct = getattr(p, "ram_percent", 0.0)
        ram_total = getattr(p, "ram_total_bytes", 0)
        ram_used = getattr(p, "ram_used_bytes", 0)

        # Disk & S.M.A.R.T.
        disks: dict[str, DiskSmartMetrics] = {}
        if hasattr(p, "smart_drives") and isinstance(p.smart_drives, dict):
            for k, v in p.smart_drives.items():
                if isinstance(v, DiskSmartMetrics):
                    disks[k] = v
                else:
                    disks[k] = DiskSmartMetrics(
                        drive=getattr(v, "drive", k),
                        status=getattr(v, "status", "PASSED"),
                        temperature_c=getattr(v, "temperature_c", 35),
                        reallocated_sectors=getattr(v, "reallocated_sectors", 0),
                        reported_uncorrectable_errors=getattr(v, "reported_uncorrectable_errors", 0),
                        wear_range_delta_life_pct=getattr(v, "wear_range_delta_life_pct", 99),
                        power_on_hours=getattr(v, "power_on_hours", 1000),
                    )

        smart_status = "PASSED"
        if "C:" in disks:
            smart_status = disks["C:"].status
        elif disks:
            smart_status = self._aggregate_smart_status(disks)

        return HardwareMetrics(
            cpu_percent=cpu_pct,
            cpu_temp_c=cpu_temp,
            per_cpu_percent=per_cpu,
            cpu_freq_mhz=cpu_freq,
            gpu_percent=gpu_pct,
            gpu_temp_c=gpu_temp,
            gpu_fan_speed_rpm=fan_rpm,
            gpu_fan_percent=fan_pct,
            ram_percent=ram_pct,
            ram_total_bytes=ram_total,
            ram_used_bytes=ram_used,
            vram_used_gb=vram_used_gb,
            vram_total_gb=vram_total_gb,
            smart_status=smart_status,
            disks=disks,
            timestamp=time.time(),
        )

    # -----------------------------------------------------------------------
    # Probing Layers
    # -----------------------------------------------------------------------

    def _probe_ram(self) -> tuple[float, int, int]:
        """Probes RAM percentage, total bytes, and used bytes via Win32 ctypes / psutil."""
        # Method A: Win32 GlobalMemoryStatusEx (sub-millisecond)
        if sys.platform == "win32":
            try:
                kernel32 = getattr(ctypes.windll, "kernel32", None)
                if kernel32 and hasattr(kernel32, "GlobalMemoryStatusEx"):
                    mem_status = MEMORYSTATUSEX()
                    mem_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                    if kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_status)):
                        total = int(mem_status.ullTotalPhys)
                        avail = int(mem_status.ullAvailPhys)
                        used = total - avail
                        pct = float(mem_status.dwMemoryLoad)
                        return pct, total, used
            except Exception as e:
                log.debug("GlobalMemoryStatusEx probe failed: %s", e)

        # Method B: psutil fallback
        if HAS_PSUTIL:
            try:
                vm = psutil.virtual_memory()
                return float(vm.percent), int(vm.total), int(vm.used)
            except Exception:
                pass

        return 0.0, 0, 0

    def _probe_cpu(self) -> tuple[float, list[float], float | None]:
        """Probes CPU total percent, per-CPU percent list, and frequency."""
        # Method A: psutil if available
        if HAS_PSUTIL:
            try:
                total_pct = float(psutil.cpu_percent(interval=None))
                per_cpu = [float(c) for c in psutil.cpu_percent(interval=None, percpu=True)]
                freq = None
                try:
                    cpufreq = psutil.cpu_freq()
                    if cpufreq:
                        freq = float(cpufreq.current)
                except Exception:
                    pass
                return total_pct, per_cpu, freq
            except Exception as e:
                log.debug("psutil cpu probe failed: %s", e)

        # Method B: Win32 GetSystemTimes delta via kernel32
        if sys.platform == "win32":
            try:
                kernel32 = getattr(ctypes.windll, "kernel32", None)
                if kernel32 and hasattr(kernel32, "GetSystemTimes"):
                    idle_ft = FILETIME()
                    kernel_ft = FILETIME()
                    user_ft = FILETIME()
                    if kernel32.GetSystemTimes(ctypes.byref(idle_ft), ctypes.byref(kernel_ft), ctypes.byref(user_ft)):
                        idle = _filetime_to_uint64(idle_ft)
                        kernel = _filetime_to_uint64(kernel_ft)
                        user = _filetime_to_uint64(user_ft)
                        now = time.time()

                        if self._prev_idle_time is not None:
                            d_idle = idle - self._prev_idle_time
                            d_kernel = kernel - self._prev_kernel_time
                            d_user = user - self._prev_user_time
                            total_sys = d_kernel + d_user
                            busy = total_sys - d_idle

                            self._prev_idle_time = idle
                            self._prev_kernel_time = kernel
                            self._prev_user_time = user
                            self._prev_times_ts = now

                            if total_sys > 0 and busy >= 0:
                                pct = min(100.0, max(0.0, (busy / total_sys) * 100.0))
                                return round(pct, 1), [round(pct, 1)], None

                        self._prev_idle_time = idle
                        self._prev_kernel_time = kernel
                        self._prev_user_time = user
                        self._prev_times_ts = now
            except Exception as e:
                log.debug("GetSystemTimes probe failed: %s", e)

        return 0.0, [], None

    def _probe_cpu_temperature(self) -> float | None:
        """Probes CPU package temperature via psutil / PowerShell CIM ThermalZone."""
        # 1. psutil sensors_temperatures (Linux or Windows with compatible drivers)
        if HAS_PSUTIL and hasattr(psutil, "sensors_temperatures"):
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for key in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"):
                        if key in temps and temps[key]:
                            return float(temps[key][0].current)
                    for key, entries in temps.items():
                        if entries:
                            return float(entries[0].current)
            except Exception:
                pass

        # 2. PowerShell CIM ThermalZone (Windows 10/11 ACPI Thermal Zone)
        now = time.time()
        if now - self._cached_cim_temp_ts < 4.0 and self._cached_cim_temp is not None:
            return self._cached_cim_temp

        if sys.platform == "win32":
            try:
                # Query Win32_PerfFormattedData_Counters_ThermalZoneInformation
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-CimInstance -ClassName Win32_PerfFormattedData_Counters_ThermalZoneInformation -ErrorAction SilentlyContinue | Select-Object -ExpandProperty HighPrecisionTemperature | ConvertTo-Json",
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
                if proc.returncode == 0 and proc.stdout.strip():
                    raw_str = proc.stdout.strip()
                    data = json.loads(raw_str)
                    val = data[0] if isinstance(data, list) else data
                    # HighPrecisionTemperature is in tenths of Kelvin (e.g. 3572 = 84.0°C)
                    if isinstance(val, (int, float)) and val > 2732:
                        temp_c = round((float(val) - 2732.0) / 10.0, 1)
                        self._cached_cim_temp = temp_c
                        self._cached_cim_temp_ts = now
                        return temp_c
            except Exception as e:
                log.debug("PowerShell ThermalZone CIM query failed: %s", e)

        return None

    def _probe_gpu(self) -> tuple[float | None, float | None, float | None, float | None, int | None, int | None]:
        """
        Probes dedicated GPU telemetry via nvidia-smi CLI.
        Returns: (gpu_percent, gpu_temp_c, vram_used_gb, vram_total_gb, fan_rpm, fan_pct)
        """
        if not self._nvidia_smi_path:
            return None, None, None, None, None, None

        try:
            cmd = [
                self._nvidia_smi_path,
                "--query-gpu=utilization.gpu,temperature.gpu,memory.total,memory.used,fan.speed",
                "--format=csv,noheader,nounits",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            if proc.returncode == 0 and proc.stdout.strip():
                line = proc.stdout.strip().splitlines()[0]
                tokens = [t.strip() for t in line.split(",")]
                if len(tokens) >= 4:
                    def _parse_flt(val: str) -> float | None:
                        try:
                            return float(val) if val not in ("[N/A]", "N/A", "") else None
                        except ValueError:
                            return None

                    gpu_pct = _parse_flt(tokens[0])
                    gpu_temp = _parse_flt(tokens[1])
                    vram_total_mb = _parse_flt(tokens[2])
                    vram_used_mb = _parse_flt(tokens[3])
                    vram_total_gb = round(vram_total_mb / 1024.0, 2) if vram_total_mb is not None else None
                    vram_used_gb = round(vram_used_mb / 1024.0, 2) if vram_used_mb is not None else None

                    fan_pct = None
                    if len(tokens) >= 5:
                        f_val = _parse_flt(tokens[4])
                        if f_val is not None:
                            fan_pct = int(f_val)

                    return gpu_pct, gpu_temp, vram_used_gb, vram_total_gb, None, fan_pct
        except Exception as e:
            log.debug("nvidia-smi probe failed: %s", e)

        return None, None, None, None, None, None

    # -----------------------------------------------------------------------
    # S.M.A.R.T. Disk Health Probing (F-21)
    # -----------------------------------------------------------------------

    def get_disk_smart_status(self, use_cache: bool = True) -> dict[str, DiskSmartMetrics]:
        """Query detailed S.M.A.R.T. and volume metrics for all disks."""
        if self.provider is not None:
            metrics = self._get_metrics_from_provider()
            return metrics.disks

        now = time.time()
        if use_cache and (now - self._cached_disks_ts < 5.0) and self._cached_disks:
            return self._cached_disks

        disks: dict[str, DiskSmartMetrics] = {}

        # 1. Query Partitions & Free Space via psutil or Win32 GetDiskFreeSpaceExW
        if HAS_PSUTIL:
            try:
                for part in psutil.disk_partitions(all=False):
                    drive_letter = part.mountpoint[:2].upper() if len(part.mountpoint) >= 2 else part.mountpoint
                    if not drive_letter:
                        continue
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                        disks[drive_letter] = DiskSmartMetrics(
                            drive=drive_letter,
                            status="PASSED",
                            total_bytes=int(usage.total),
                            used_bytes=int(usage.used),
                            free_bytes=int(usage.free),
                            percent_used=float(usage.percent),
                        )
                    except Exception:
                        pass
            except Exception as e:
                log.debug("psutil disk partition query failed: %s", e)

        # 2. Win32 GetDiskFreeSpaceExW Fallback
        if not disks and sys.platform == "win32":
            for letter in ("C:", "D:", "E:"):
                root = f"{letter}\\"
                try:
                    kernel32 = getattr(ctypes.windll, "kernel32", None)
                    if kernel32 and hasattr(kernel32, "GetDiskFreeSpaceExW"):
                        free_avail = ctypes.c_uint64()
                        total = ctypes.c_uint64()
                        free_total = ctypes.c_uint64()
                        if kernel32.GetDiskFreeSpaceExW(root, ctypes.byref(free_avail), ctypes.byref(total), ctypes.byref(free_total)):
                            t_val = int(total.value)
                            f_val = int(free_avail.value)
                            u_val = t_val - f_val
                            pct = round((u_val / t_val) * 100.0, 1) if t_val > 0 else 0.0
                            disks[letter] = DiskSmartMetrics(
                                drive=letter,
                                status="PASSED",
                                total_bytes=t_val,
                                used_bytes=u_val,
                                free_bytes=f_val,
                                percent_used=pct,
                            )
                except Exception:
                    pass

        # 3. Query S.M.A.R.T. Failure Prediction via PowerShell CIM
        if sys.platform == "win32":
            try:
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-CimInstance -Namespace 'root\\wmi' -ClassName 'MSStorageDriver_FailurePredictStatus' -ErrorAction SilentlyContinue | Select-Object InstanceName, Active, PredictFailure | ConvertTo-Json",
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
                if proc.returncode == 0 and proc.stdout.strip():
                    data = json.loads(proc.stdout.strip())
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        predict_fail = bool(item.get("PredictFailure", False))
                        if predict_fail:
                            for d in disks.values():
                                d.status = "FAILING"
            except Exception as e:
                log.debug("S.M.A.R.T. failure prediction probe failed: %s", e)

        # Fallback default if nothing detected
        if not disks:
            disks["C:"] = DiskSmartMetrics(drive="C:", status="PASSED")

        self._cached_disks = disks
        self._cached_disks_ts = now
        return disks

    def _aggregate_smart_status(self, disks: dict[str, DiskSmartMetrics]) -> str:
        """Aggregates overall SMART status across all monitored drives."""
        if not disks:
            return "PASSED"
        statuses = [d.status for d in disks.values()]
        if "FAILING" in statuses or "CRITICAL" in statuses:
            return "FAILING"
        if "WARNING" in statuses or "Degraded" in statuses:
            return "WARNING"
        if all(s == "PASSED" for s in statuses):
            return "PASSED"
        return "PASSED"

    # -----------------------------------------------------------------------
    # Threshold Analyzer & Voice Alerts (F-22)
    # -----------------------------------------------------------------------

    def check_thresholds(self) -> list[dict[str, Any]]:
        """
        Evaluate current metrics against thresholds with debouncing.
        Returns list of structured alert objects.
        """
        metrics = self.get_metrics(use_cache=False)
        alerts: list[dict[str, Any]] = []
        now = time.time()

        # 1. CPU Temperature Check
        if metrics.cpu_temp_c is not None and metrics.cpu_temp_c >= self.cpu_temp_threshold:
            last_t = self.last_alert_times.get("cpu", self.last_alert_time)
            level = "CRITICAL" if metrics.cpu_temp_c >= 95.0 else "WARNING"
            if (now - last_t) >= self.alert_cooldown_s or (level == "CRITICAL" and (now - last_t) >= 1.0):
                alerts.append({
                    "component": "cpu",
                    "level": level,
                    "value": metrics.cpu_temp_c,
                    "threshold": self.cpu_temp_threshold,
                    "message": f"Nhiệt độ CPU cao: {metrics.cpu_temp_c:.1f}°C",
                    "message_en": f"High CPU temperature: {metrics.cpu_temp_c:.1f}°C",
                    "timestamp": now,
                })
                self.last_alert_times["cpu"] = now
                self.last_alert_time = now

        # 2. RAM Pressure Check
        if metrics.ram_percent >= self.ram_threshold:
            last_t = self.last_alert_times.get("ram", 0.0)
            if (now - last_t) >= self.alert_cooldown_s:
                alerts.append({
                    "component": "ram",
                    "level": "CRITICAL",
                    "value": metrics.ram_percent,
                    "threshold": self.ram_threshold,
                    "message": f"Bộ nhớ RAM quá tải: {metrics.ram_percent:.1f}%",
                    "message_en": f"RAM memory overloaded: {metrics.ram_percent:.1f}%",
                    "timestamp": now,
                })
                self.last_alert_times["ram"] = now

        # 3. GPU Temperature Check
        if metrics.gpu_temp_c is not None and metrics.gpu_temp_c >= self.gpu_temp_threshold:
            last_t = self.last_alert_times.get("gpu", 0.0)
            level = "CRITICAL" if metrics.gpu_temp_c >= 95.0 else "WARNING"
            if (now - last_t) >= self.alert_cooldown_s:
                alerts.append({
                    "component": "gpu",
                    "level": level,
                    "value": metrics.gpu_temp_c,
                    "threshold": self.gpu_temp_threshold,
                    "message": f"Nhiệt độ GPU cao: {metrics.gpu_temp_c:.1f}°C",
                    "message_en": f"High GPU temperature: {metrics.gpu_temp_c:.1f}°C",
                    "timestamp": now,
                })
                self.last_alert_times["gpu"] = now

        # 4. S.M.A.R.T. Disk Degradation Check
        for drive_name, disk in metrics.disks.items():
            if disk.status in ("WARNING", "FAILING"):
                last_t = self.last_alert_times.get(f"smart_{drive_name}", 0.0)
                if (now - last_t) >= (self.alert_cooldown_s * 2):
                    alerts.append({
                        "component": "disk_smart",
                        "drive": drive_name,
                        "level": "CRITICAL" if disk.status == "FAILING" else "WARNING",
                        "message": f"Cảnh báo: Ổ đĩa {drive_name} phát hiện lỗi S.M.A.R.T.",
                        "message_en": f"Warning: Drive {drive_name} reported S.M.A.R.T. degradation",
                        "timestamp": now,
                    })
                    self.last_alert_times[f"smart_{drive_name}"] = now

        return alerts

    def get_voice_summary(self, lang: str = "vi") -> str:
        """Format concise speech summary for vocal status reports."""
        m = self.get_metrics()
        lang_clean = (lang or "vi").lower()

        if lang_clean.startswith("en"):
            temp_clause = f"CPU temperature is {m.cpu_temp_c:.0f} degrees Celsius. " if m.cpu_temp_c is not None else ""
            return (
                f"System status: CPU usage is {m.cpu_percent:.0f} percent. "
                f"{temp_clause}"
                f"RAM usage is {m.ram_percent:.0f} percent. "
                f"Storage drive status is {m.smart_status}."
            )

        # Default Vietnamese format matching R7, F-22 and test suite assertions
        temp_clause = f"Nhiệt độ CPU là {m.cpu_temp_c:.0f} độ C. " if m.cpu_temp_c is not None else ""
        return (
            f"Tình trạng hệ thống: CPU đang sử dụng {m.cpu_percent:.0f} phần trăm. "
            f"{temp_clause}"
            f"RAM đang sử dụng {m.ram_percent:.0f} phần trăm. "
            f"Ổ đĩa trạng thái {m.smart_status}."
        )
