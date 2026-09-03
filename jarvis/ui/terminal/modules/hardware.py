"""
jarvis/ui/terminal/modules/hardware.py
========================================
Hardware Diagnostics module adapter. Thin wrapper over jarvis.hardware --
no probing logic is reimplemented here.
"""
from __future__ import annotations

from jarvis.hardware.monitor import HardwareMonitor
from jarvis.hardware.reporter import HardwareReporter
from jarvis.ui.terminal.context import TerminalContext, run_timed
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.theme import StatusLevel

MODULE = "HARDWARE"


def _monitor(ctx: TerminalContext) -> HardwareMonitor:
    mon = ctx.state.get("hw_monitor")
    if mon is None:
        mon = HardwareMonitor()
        ctx.state["hw_monitor"] = mon
    return mon


def _reporter(ctx: TerminalContext) -> HardwareReporter:
    rep = ctx.state.get("hw_reporter")
    if rep is None:
        rep = HardwareReporter(monitor=_monitor(ctx), tts_manager=None, dispatcher=None)
        ctx.state["hw_reporter"] = rep
    return rep


def _system_snapshot(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            metrics = _monitor(ctx).get_metrics(use_cache=True)
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="System Snapshot",
                                  error_reason=str(e))
        fields = [
            ("CPU", f"{metrics.cpu_percent:.1f} %"),
            ("RAM", f"{metrics.ram_percent:.1f} %"),
            ("GPU", f"{metrics.gpu_percent:.1f} %" if metrics.gpu_percent is not None else "N/A"),
            ("Disks Detected", str(len(metrics.disks))),
        ]
        return ActionOutcome(status=StatusLevel.PASS, title="System Snapshot", fields=fields,
                              structured_data=metrics.to_dict())
    return run_timed(body)


def _cpu_ram(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            metrics = _monitor(ctx).get_metrics(use_cache=True)
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="CPU / RAM Monitor", error_reason=str(e))
        fields = [
            ("CPU Usage", f"{metrics.cpu_percent:.1f} %"),
            ("CPU Temp", f"{metrics.cpu_temp_c:.1f} C" if metrics.cpu_temp_c is not None else "N/A"),
            ("RAM Usage", f"{metrics.ram_percent:.1f} %"),
        ]
        return ActionOutcome(status=StatusLevel.PASS, title="CPU / RAM Monitor", fields=fields)
    return run_timed(body)


def _gpu_vram(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            metrics = _monitor(ctx).get_metrics(use_cache=True)
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="GPU / VRAM Monitor", error_reason=str(e))
        if metrics.gpu_percent is None:
            return ActionOutcome(
                status=StatusLevel.LIMITED, title="GPU / VRAM Monitor",
                fields=[("GPU", "N/A"), ("VRAM", "N/A")],
                detail_lines=["No dedicated GPU detected, or nvidia-smi is unavailable on this host."],
            )
        fields = [
            ("GPU Usage", f"{metrics.gpu_percent:.1f} %"),
            ("GPU Temp", f"{metrics.gpu_temp_c:.1f} C" if metrics.gpu_temp_c is not None else "N/A"),
            ("VRAM Used", f"{metrics.vram_used_gb:.2f} GB" if metrics.vram_used_gb is not None else "N/A"),
        ]
        return ActionOutcome(status=StatusLevel.PASS, title="GPU / VRAM Monitor", fields=fields)
    return run_timed(body)


def _drive_detail(ctx: TerminalContext, drive: str) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            disks = _monitor(ctx).get_disk_smart_status(use_cache=True)
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title=f"Drive {drive}", error_reason=str(e))
        d = disks.get(drive)
        if d is None:
            return ActionOutcome(status=StatusLevel.SKIPPED, title=f"Drive {drive}",
                                  detail_lines=["This drive is no longer present (disappeared since last refresh)."])
        fields = [
            ("Status", d.status), ("Model", d.model or "N/A"), ("Media Type", d.media_type or "N/A"),
            ("Temperature", f"{d.temperature_c:.1f} C" if d.temperature_c is not None else "N/A"),
            ("Percent Used", f"{d.percent_used:.1f} %" if d.percent_used is not None else "N/A"),
            ("Power-On Hours", str(d.power_on_hours) if d.power_on_hours is not None else "N/A"),
        ]
        status = StatusLevel.PASS if str(d.status).upper() in ("PASSED", "OK", "HEALTHY") else StatusLevel.LIMITED
        return ActionOutcome(status=status, title=f"Drive {drive}", fields=fields, structured_data=d.__dict__)
    return run_timed(body)


def build_storage_menu(ctx: TerminalContext) -> MenuScreen:
    """Dynamic submenu: one entry per REAL detected drive (never assumes
    C:/D:/E: exist). Handles zero/one/many drives and drives disappearing
    between refreshes without crashing."""
    try:
        disks = _monitor(ctx).get_disk_smart_status(use_cache=True)
    except Exception:
        disks = {}
    actions = []
    for i, (drive, d) in enumerate(sorted(disks.items()), start=1):
        label = f"{drive}  {d.model or 'Unknown'}"
        actions.append(MenuAction(
            id=f"hw_drive_{drive}", key=str(i), label=label, description=str(d.status),
            handler=lambda drv=drive: _drive_detail(ctx, drv), safe_for_batch=True,
        ))
    return MenuScreen(
        id="hardware_storage", title="STORAGE / SMART", breadcrumb=["MAIN", "HARDWARE", "STORAGE"],
        actions=actions, batch_label="Check All Drives",
        help_intro="No drive is assumed to exist -- this list is built from real detection each visit.",
    )


def _sensors_alerts(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            alerts = _monitor(ctx).check_thresholds()
            metrics = _monitor(ctx).get_metrics(use_cache=True)
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="Sensor & Alert Status", error_reason=str(e))
        temp_known = metrics.cpu_temp_c is not None or metrics.gpu_temp_c is not None
        status = StatusLevel.PASS if temp_known else StatusLevel.LIMITED
        fields = [
            ("Active Alerts", str(len(alerts))),
            ("CPU Temp Sensor", "AVAILABLE" if metrics.cpu_temp_c is not None else "UNAVAILABLE"),
            ("GPU Temp Sensor", "AVAILABLE" if metrics.gpu_temp_c is not None else "UNAVAILABLE"),
        ]
        detail = [f"- {a}" for a in alerts] if alerts else []
        return ActionOutcome(status=status, title="Sensor & Alert Status", fields=fields, detail_lines=detail)
    return run_timed(body)


def build_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="hw_snapshot", key="1", label="System Snapshot",
                   description="One-time hardware summary (CPU/RAM/GPU/disks)",
                   handler=lambda: _system_snapshot(ctx), safe_for_batch=True,
                   help_text="Reads a one-time hardware summary via HardwareMonitor.get_metrics()."),
        MenuAction(id="hw_cpu_ram", key="2", label="CPU / RAM Monitor",
                   description="Live CPU and memory telemetry",
                   handler=lambda: _cpu_ram(ctx), safe_for_batch=True,
                   help_text="Displays current CPU and RAM utilization/temperature."),
        MenuAction(id="hw_gpu_vram", key="3", label="GPU / VRAM Monitor",
                   description="GPU utilization, temperature, VRAM",
                   handler=lambda: _gpu_vram(ctx), safe_for_batch=True,
                   help_text="Displays GPU telemetry via nvidia-smi; LIMITED if no GPU is detected."),
        MenuAction(id="hw_storage", key="4", label="Storage / SMART",
                   description="Detected drives and SMART health status",
                   is_submenu=True, submenu_id="hardware_storage", safe_for_batch=False,
                   help_text="Drills into a per-drive detail menu, built from real detection."),
        MenuAction(id="hw_sensors", key="5", label="Sensor & Alert Status",
                   description="Threshold alerts and sensor availability",
                   handler=lambda: _sensors_alerts(ctx), safe_for_batch=True,
                   help_text="Runs HardwareMonitor.check_thresholds() and reports sensor availability."),
    ]
    return MenuScreen(
        id="hardware", title="HARDWARE DIAGNOSTICS", breadcrumb=["MAIN", "HARDWARE"],
        actions=actions, batch_label="Run All Checks",
        help_intro="Read-only hardware telemetry via jarvis.hardware. All checks are safe to batch.",
    )
