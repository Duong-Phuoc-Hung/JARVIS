"""
jarvis/hardware/reporter.py
===========================
Hardware Telemetry Reporter, Natural Language Speech Synthesizer, and Alerting Bridge.
Features:
  - F-22: Formats natural language speech summaries in Vietnamese and English.
  - Component-specific diagnostics (CPU, RAM, GPU, S.M.A.R.T. storage).
  - Generates Markdown diagnostic dashboard reports.
  - Integrates with TTSManager and ActionDispatcher for real-time proactive warnings.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from jarvis.hardware.monitor import HardwareMetrics, HardwareMonitor

log = logging.getLogger("jarvis.hardware.reporter")


class HardwareReporter:
    """
    Diagnostic report generator, natural language query engine, and voice alerting bridge.
    """

    def __init__(
        self,
        monitor: HardwareMonitor | None = None,
        tts_manager: Any | None = None,
        dispatcher: Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.config = config or {}
        self.monitor = monitor or HardwareMonitor(config=self.config)
        self.tts_manager = tts_manager
        self.dispatcher = dispatcher
        self.voice_alerts_enabled = self.config.get("hardware", {}).get("voice_alerts", True)

    def format_voice_summary(self, metrics: HardwareMetrics | None = None, lang: str = "vi") -> str:
        """Generate human-like spoken response for system status inquiry."""
        if metrics is None:
            return self.monitor.get_voice_summary(lang=lang)

        lang_clean = (lang or "vi").lower()
        if lang_clean.startswith("en"):
            temp_clause = f"CPU temperature is {metrics.cpu_temp_c:.0f} degrees Celsius. " if metrics.cpu_temp_c is not None else ""
            gpu_clause = f"GPU temperature is {metrics.gpu_temp_c:.0f} degrees Celsius. " if metrics.gpu_temp_c is not None else ""
            return (
                f"System status: CPU usage is {metrics.cpu_percent:.0f} percent. "
                f"{temp_clause}"
                f"{gpu_clause}"
                f"RAM usage is {metrics.ram_percent:.0f} percent. "
                f"Storage drive status is {metrics.smart_status}."
            )

        temp_clause = f"Nhiệt độ CPU là {metrics.cpu_temp_c:.0f} độ C. " if metrics.cpu_temp_c is not None else ""
        gpu_clause = f"Nhiệt độ GPU là {metrics.gpu_temp_c:.0f} độ C. " if metrics.gpu_temp_c is not None else ""
        return (
            f"Tình trạng hệ thống: CPU đang sử dụng {metrics.cpu_percent:.0f} phần trăm. "
            f"{temp_clause}"
            f"{gpu_clause}"
            f"RAM đang sử dụng {metrics.ram_percent:.0f} phần trăm. "
            f"Ổ đĩa trạng thái {metrics.smart_status}."
        )

    def format_component_summary(
        self,
        component: str,
        metrics: HardwareMetrics | None = None,
        lang: str = "vi",
    ) -> str:
        """Generate targeted voice answer for specific component (cpu, ram, gpu, disk)."""
        m = metrics or self.monitor.get_metrics()
        c_clean = component.lower().strip()
        is_en = (lang or "vi").lower().startswith("en")

        if "cpu" in c_clean:
            temp_part = f"nhiệt độ {m.cpu_temp_c:.0f} độ C, " if m.cpu_temp_c is not None else ""
            if is_en:
                temp_en = f"temperature is {m.cpu_temp_c:.0f} degrees Celsius, " if m.cpu_temp_c is not None else ""
                return f"CPU {temp_en}utilization is {m.cpu_percent:.0f} percent."
            return f"CPU {temp_part}mức sử dụng {m.cpu_percent:.0f} phần trăm."

        elif "ram" in c_clean or "memory" in c_clean or "bộ nhớ" in c_clean:
            used_gb = m.ram_used_bytes / (1024.0 ** 3) if m.ram_total_bytes > 0 else 0.0
            tot_gb = m.ram_total_bytes / (1024.0 ** 3) if m.ram_total_bytes > 0 else 0.0
            if is_en:
                return f"RAM usage is {m.ram_percent:.0f} percent ({used_gb:.1f} GB of {tot_gb:.1f} GB)."
            return f"Bộ nhớ RAM đang sử dụng {m.ram_percent:.0f} phần trăm."

        elif "gpu" in c_clean or "card" in c_clean or "đồ họa" in c_clean:
            if m.gpu_percent is None and m.gpu_temp_c is None:
                if is_en:
                    return "No dedicated GPU sensor detected."
                return "Không phát hiện cảm biến card đồ họa rời."
            gpu_pct = m.gpu_percent or 0.0
            temp_part = f", nhiệt độ {m.gpu_temp_c:.0f} độ C" if m.gpu_temp_c is not None else ""
            if is_en:
                temp_en = f", temperature is {m.gpu_temp_c:.0f} degrees Celsius" if m.gpu_temp_c is not None else ""
                return f"GPU utilization is {gpu_pct:.0f} percent{temp_en}."
            return f"GPU đang sử dụng {gpu_pct:.0f} phần trăm{temp_part}."

        elif "disk" in c_clean or "ổ cứng" in c_clean or "smart" in c_clean:
            main_disk = m.disks.get("C:")
            free_gb = (main_disk.free_bytes / (1024.0 ** 3)) if main_disk and main_disk.free_bytes > 0 else None
            free_part = f", dung lượng trống {free_gb:.1f} GB" if free_gb is not None else ""
            if is_en:
                free_en = f", free space {free_gb:.1f} GB" if free_gb is not None else ""
                return f"Storage health status is {m.smart_status}{free_en}."
            return f"Trạng thái ổ đĩa {m.smart_status}{free_part}."

        return self.format_voice_summary(metrics=m, lang=lang)

    def format_markdown_report(self, metrics: HardwareMetrics | None = None) -> str:
        """Format comprehensive Markdown diagnostic dashboard report."""
        m = metrics or self.monitor.get_metrics()
        now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m.timestamp))

        lines = [
            "# 🖥️ JARVIS Hardware Diagnostics Report",
            f"**Timestamp**: `{now_str}`",
            "",
            "## 1. System Core Telemetry",
            f"- **CPU Usage**: `{m.cpu_percent:.1f}%`",
            f"- **CPU Temperature**: `{f'{m.cpu_temp_c:.1f}°C' if m.cpu_temp_c is not None else 'N/A'}`",
            f"- **CPU Frequency**: `{f'{m.cpu_freq_mhz:.0f} MHz' if m.cpu_freq_mhz is not None else 'N/A'}`",
            f"- **RAM Usage**: `{m.ram_percent:.1f}%` ({m.ram_used_bytes / (1024**3):.1f} GB / {m.ram_total_bytes / (1024**3):.1f} GB)",
            "",
            "## 2. Dedicated GPU Metrics",
            f"- **GPU Load**: `{f'{m.gpu_percent:.1f}%' if m.gpu_percent is not None else 'N/A'}`",
            f"- **GPU Temperature**: `{f'{m.gpu_temp_c:.1f}°C' if m.gpu_temp_c is not None else 'N/A'}`",
            f"- **GPU Fan**: `{f'{m.gpu_fan_percent}%' if m.gpu_fan_percent is not None else 'N/A'}`",
            f"- **VRAM Usage**: `{f'{m.vram_used_gb:.2f} GB' if m.vram_used_gb is not None else 'N/A'}` / `{f'{m.vram_total_gb:.2f} GB' if m.vram_total_gb is not None else 'N/A'}`",
            "",
            "## 3. Storage Volumes & S.M.A.R.T. Health",
            f"- **Overall S.M.A.R.T. Status**: `{m.smart_status}`",
            "",
            "| Drive | Status | Used Space | Total Space | Usage % | Temp |",
            "|---|---|---|---|---|---|",
        ]

        for d_name, d in m.disks.items():
            tot_gb = d.total_bytes / (1024**3) if d.total_bytes > 0 else 0.0
            used_gb = d.used_bytes / (1024**3) if d.total_bytes > 0 else 0.0
            temp_str = f"{d.temperature_c}°C" if d.temperature_c is not None else "N/A"
            lines.append(
                f"| `{d.drive}` | `{d.status}` | `{used_gb:.1f} GB` | `{tot_gb:.1f} GB` | `{d.percent_used:.1f}%` | `{temp_str}` |"
            )

        return "\n".join(lines)

    def format_json_telemetry(self, metrics: HardwareMetrics | None = None) -> str:
        """Export serialized telemetry snapshot for WebSocket dashboard."""
        m = metrics or self.monitor.get_metrics()
        return json.dumps(m.to_dict(), indent=2)

    def process_voice_query(self, query_text: str, lang: str = "vi") -> str:
        """
        Parse natural language voice query and return synthesized voice answer.
        Supports: 'tình trạng hệ thống', 'nhiệt độ cpu', 'bộ nhớ ram', 'ổ cứng'.
        """
        q = (query_text or "").lower().strip()

        if any(k in q for k in ("nhiệt độ cpu", "cpu nóng", "xung nhịp cpu", "cpu")):
            return self.format_component_summary("cpu", lang=lang)
        if any(k in q for k in ("bộ nhớ", "ram", "dung lượng ram", "memory")):
            return self.format_component_summary("ram", lang=lang)
        if any(k in q for k in ("gpu", "card đồ họa", "card màn hình", "vram")):
            return self.format_component_summary("gpu", lang=lang)
        if any(k in q for k in ("ổ cứng", "dung lượng đĩa", "smart", "ổ c", "disk", "storage")):
            return self.format_component_summary("disk", lang=lang)

        return self.format_voice_summary(lang=lang)

    def poll_and_alert(self, speak: bool = True) -> list[dict[str, Any]]:
        """
        Execute threshold check; if breached, publish alert event and vocalize speech warning.
        """
        alerts = self.monitor.check_thresholds()
        if not alerts:
            return []

        for alert in alerts:
            msg = alert.get("message", "")
            log.warning("Hardware alert: [%s] %s (%s)", alert.get("level"), alert.get("component"), msg)

            # Speak alert if TTS manager provided and voice alerts enabled
            if speak and self.voice_alerts_enabled and self.tts_manager is not None:
                try:
                    if hasattr(self.tts_manager, "speak"):
                        self.tts_manager.speak(msg, wait=False)
                except Exception as e:
                    log.error("Failed to speak hardware alert: %s", e)

            # Dispatch event if event dispatcher is available
            if self.dispatcher is not None and hasattr(self.dispatcher, "publish"):
                try:
                    self.dispatcher.publish("hardware.alert", **alert)
                except Exception as e:
                    log.error("Failed to publish hardware.alert event: %s", e)

        return alerts
