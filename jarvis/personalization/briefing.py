"""
jarvis/personalization/briefing.py
==================================
Executive Morning Briefing Engine.
Collects system vitals, Git workspace health, memory facts, and produces
an Iron-Man style daily intelligence briefing for the user.
"""
from __future__ import annotations

import datetime
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis.personalization.profile import (
    PersonaTone,
    UserProfile,
    UserProfileManager,
    get_user_profile_manager,
)
from jarvis.personalization.calendar import CalendarScheduleProvider, CalendarEvent

logger = logging.getLogger("jarvis.personalization.briefing")


@dataclass
class BriefingReport:
    """Consolidated intelligence briefing document."""
    timestamp: float
    formatted_date_time: str
    greeting: str
    system_vitals: dict[str, Any]
    git_workspace_summary: list[dict[str, Any]]
    remembered_facts: list[str]
    summary_markdown: str
    speech_script: str
    schedule_events: list[dict[str, Any]] = field(default_factory=list)


class ExecutiveBriefingEngine:
    """
    Synthesizes real-time hardware status, Git repositories state, and user memory
    into an executive briefing delivered via text or natural speech.
    """

    def __init__(
        self,
        profile_manager: UserProfileManager | None = None,
        memory_manager: Any = None,
        schedule_provider: CalendarScheduleProvider | None = None,
    ) -> None:
        self.profile_mgr = profile_manager or get_user_profile_manager()
        self.memory_mgr = memory_manager
        self.schedule_provider = schedule_provider or CalendarScheduleProvider()

    def generate_morning_briefing(self) -> BriefingReport:
        """Generate a complete intelligence briefing report."""
        profile: UserProfile = self.profile_mgr.get_profile()
        now = datetime.datetime.now()

        # 1. Date & Time formatting (Vietnamese)
        days_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        day_str = days_vi[now.weekday()]
        date_time_str = f"{now.strftime('%H:%M')} — {day_str}, ngày {now.strftime('%d/%m/%Y')}"

        # 2. Personalized Greeting
        greeting = profile.generate_greeting(now.hour)

        # 3. System Vitals
        vitals = self.collect_system_vitals()

        # 4. Workspace Scan
        git_summaries = self.scan_git_workspace(profile.primary_workspace)

        # 5. Calendar & Schedule
        schedule_events = self.schedule_provider.get_today_events(now.date())

        # 6. Memory Facts
        facts = self.collect_memory_facts()

        # 7. Synthesize Markdown text & Speech script
        summary_md, speech_text = self._compose_briefing(
            profile=profile,
            greeting=greeting,
            date_time_str=date_time_str,
            vitals=vitals,
            git_summaries=git_summaries,
            schedule_events=schedule_events,
            facts=facts,
        )

        return BriefingReport(
            timestamp=time.time(),
            formatted_date_time=date_time_str,
            greeting=greeting,
            system_vitals=vitals,
            git_workspace_summary=git_summaries,
            remembered_facts=facts,
            summary_markdown=summary_md,
            speech_script=speech_text,
            schedule_events=[e.to_dict() for e in schedule_events],
        )

    def collect_system_vitals(self) -> dict[str, Any]:
        """Collect host CPU, RAM, Battery, and Disk statistics."""
        vitals: dict[str, Any] = {
            "cpu_percent": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "ram_percent": 0.0,
            "battery_percent": None,
            "battery_charging": None,
            "disk_free_gb": 0.0,
        }

        # Disk
        try:
            total, used, free = shutil.disk_usage("C:\\")
            vitals["disk_free_gb"] = round(free / (1024 ** 3), 1)
        except Exception:
            pass

        # Hardware metrics via psutil / Win32
        try:
            import psutil
            vitals["cpu_percent"] = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            vitals["ram_used_gb"] = round(mem.used / (1024 ** 3), 1)
            vitals["ram_total_gb"] = round(mem.total / (1024 ** 3), 1)
            vitals["ram_percent"] = mem.percent

            batt = psutil.sensors_battery()
            if batt is not None:
                vitals["battery_percent"] = int(batt.percent)
                vitals["battery_charging"] = bool(batt.power_plugged)
        except Exception:
            # Fallback to pure Win32 GlobalMemoryStatusEx
            try:
                import ctypes
                from ctypes import wintypes

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
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                vitals["ram_percent"] = stat.dwMemoryLoad
                vitals["ram_total_gb"] = round(stat.ullTotalPhys / (1024 ** 3), 1)
                vitals["ram_used_gb"] = round((stat.ullTotalPhys - stat.ullAvailPhys) / (1024 ** 3), 1)
            except Exception:
                pass

        return vitals

    def scan_git_workspace(self, workspace_path: str, max_repos: int = 4) -> list[dict[str, Any]]:
        """
        Scan workspace directory for top Git repositories and report branch & uncommitted status.
        """
        results: list[dict[str, Any]] = []
        p = Path(workspace_path)
        if not p.exists() or not p.is_dir():
            return results

        candidate_dirs = [d for d in p.iterdir() if d.is_dir() and (d / ".git").exists()]
        if (p / ".git").exists() and p not in candidate_dirs:
            candidate_dirs.insert(0, p)
        for repo_dir in candidate_dirs[:max_repos]:
            info: dict[str, Any] = {
                "name": repo_dir.name,
                "path": str(repo_dir),
                "branch": "unknown",
                "clean": True,
                "uncommitted_files": 0,
            }
            try:
                # Get current branch
                _cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
                branch_out = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(repo_dir),
                    creationflags=_cflags,
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                if branch_out.returncode == 0:
                    info["branch"] = branch_out.stdout.strip()

                # Get status
                _cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
                status_out = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(repo_dir),
                    creationflags=_cflags,
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                if status_out.returncode == 0:
                    lines = [l for l in status_out.stdout.strip().splitlines() if l.strip()]
                    info["uncommitted_files"] = len(lines)
                    info["clean"] = (len(lines) == 0)

                results.append(info)
            except Exception as exc:
                logger.debug(f"Git check skipped for {repo_dir.name}: {exc}")

        return results

    def collect_memory_facts(self) -> list[str]:
        """Fetch remembered personal facts about the user from MemoryManager or SQLite."""
        if self.memory_mgr is not None and hasattr(self.memory_mgr, "store"):
            try:
                facts = self.memory_mgr.store.get_facts(limit=3)
                if facts:
                    return [f.content if hasattr(f, "content") else str(f) for f in facts]
            except Exception:
                pass
        return []

    def _compose_briefing(
        self,
        profile: UserProfile,
        greeting: str,
        date_time_str: str,
        vitals: dict[str, Any],
        git_summaries: list[dict[str, Any]],
        schedule_events: list[CalendarEvent],
        facts: list[str],
    ) -> tuple[str, str]:
        """Generate Markdown document and concise audio speech script."""
        h = profile.honorific

        # Markdown synthesis
        md_lines = [
            f"# 🌅 Báo Cáo Buổi Sáng — {profile.assistant_name} Executive Briefing",
            f"> **Thời gian**: {date_time_str} | **Đối tượng**: {h} {profile.user_name}\n",
            f"{greeting}\n",
            "### 💻 Tình Trạng Phần Cứng & Hệ Thống",
            f"- **CPU**: `{vitals['cpu_percent']}%` hoạt động",
            f"- **RAM**: `{vitals['ram_used_gb']} GB` / `{vitals['ram_total_gb']} GB` ({vitals['ram_percent']}%)",
            f"- **Ổ cứng (C:)**: Còn trống `{vitals['disk_free_gb']} GB`",
        ]

        if vitals.get("battery_percent") is not None:
            plug_str = " (Đang cắm sạc)" if vitals.get("battery_charging") else " (Đang dùng pin)"
            md_lines.append(f"- **Pin**: `{vitals['battery_percent']}%`{plug_str}")

        # Calendar Schedule Section
        md_lines.append("\n### 📅 Lịch Trình & Sự Kiện Hôm Nay")
        md_lines.append(self.schedule_provider.format_markdown_schedule(schedule_events))

        if git_summaries:
            md_lines.append("\n### 📂 Tình Trạng Dự Án (Workspace)")
            for g in git_summaries:
                status_icon = "🟢 Sạch" if g["clean"] else f"🟡 {g['uncommitted_files']} tệp chưa commit"
                md_lines.append(f"- **{g['name']}** (nhánh `{g['branch']}`): {status_icon}")

        if facts:
            md_lines.append("\n### 🧠 Ghi Nhớ Cá Nhân")
            for f in facts:
                md_lines.append(f"- {f}")

        summary_md = "\n".join(md_lines)

        # Speech script synthesis (Natural Vietnamese spoken format)
        speech_parts = [greeting]
        speech_parts.append(f"Hôm nay là {date_time_str.split('—')[-1].strip()}.")

        # Hardware vitals in speech
        if vitals.get("battery_percent") is not None and vitals["battery_percent"] <= 20 and not vitals.get("battery_charging"):
            speech_parts.append(f"Lưu ý pin máy tính hiện còn {vitals['battery_percent']}%, {h} nên cắm sạc.")
        else:
            speech_parts.append(f"Tài nguyên hệ thống ổn định, RAM dùng {vitals['ram_percent']}%.")

        # Schedule in speech
        sched_speech = self.schedule_provider.format_speech_schedule(schedule_events, honorific=h)
        speech_parts.append(sched_speech)

        # Git status in speech
        unclean_repos = [g for g in git_summaries if not g["clean"]]
        if unclean_repos:
            repo_names = ", ".join(r["name"] for r in unclean_repos)
            speech_parts.append(f"Tại workspace, dự án {repo_names} hiện còn tệp chưa commit.")
        elif git_summaries:
            speech_parts.append("Các kho mã nguồn trong workspace đều đã sạch sẽ và đồng bộ.")

        speech_parts.append(f"Mọi công cụ đã sẵn sàng, chúc {h} một ngày làm việc đại thắng.")
        speech_script = " ".join(speech_parts)

        return summary_md, speech_script

    def speak_briefing(self, report: BriefingReport | None = None, tts_manager: Any = None) -> bool:
        """Deliver the morning briefing via speech synthesis."""
        rep = report or self.generate_morning_briefing()
        try:
            if tts_manager is not None and hasattr(tts_manager, "speak"):
                tts_manager.speak(rep.speech_script)
                return True

            # Attempt auto-import TTSManager
            from jarvis.tts.manager import TTSManager
            tts = TTSManager()
            tts.speak(rep.speech_script)
            return True
        except Exception as exc:
            logger.warning(f"Could not vocalize executive briefing: {exc}")
            return False
