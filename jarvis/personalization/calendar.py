"""
jarvis/personalization/calendar.py
==================================
Calendar & Executive Schedule Provider for JARVIS.
Parses local RFC 5545 (.ics) calendar files, custom schedules (schedules.json),
and user profile daily routines to generate daily agendas and executive briefings.

Zero-external-dependency, thread-safe with Windows Atomic Persistence.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jarvis.core.paths import data_path
from jarvis.utils.atomic_io import atomic_write_json
from jarvis.personalization.profile import UserProfile, get_user_profile_manager

logger = logging.getLogger("jarvis.personalization.calendar")


@dataclass
class CalendarEvent:
    """Represents a scheduled meeting, appointment, or routine event."""
    event_id: str
    title: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    location: str = ""
    description: str = ""
    is_all_day: bool = False
    source: str = "local"  # "ics", "schedules_json", "routine"

    def is_today(self, target_date: datetime.date | None = None) -> bool:
        """Check whether this event falls on the specified date (default: today)."""
        ref_date = target_date or datetime.date.today()
        return self.start_time.date() == ref_date or (
            self.start_time.date() <= ref_date <= self.end_time.date()
        )

    @property
    def time_range_str(self) -> str:
        """Human-readable time string, e.g. '09:30 - 10:30' or 'Cả ngày'."""
        if self.is_all_day:
            return "Cả ngày"
        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "location": self.location,
            "description": self.description,
            "is_all_day": self.is_all_day,
            "source": self.source,
            "time_range": self.time_range_str,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalendarEvent:
        st = datetime.datetime.fromisoformat(data["start_time"])
        et = datetime.datetime.fromisoformat(data["end_time"])
        return cls(
            event_id=data.get("event_id", ""),
            title=data.get("title", "Sự kiện"),
            start_time=st,
            end_time=et,
            location=data.get("location", ""),
            description=data.get("description", ""),
            is_all_day=bool(data.get("is_all_day", False)),
            source=data.get("source", "schedules_json"),
        )


class CalendarScheduleProvider:
    """
    Consolidated Calendar and Schedule Provider.
    Aggregates events from:
      1. Local `.ics` iCalendar export files located in `%LOCALAPPDATA%/JARVIS/calendars/`
      2. Structured JSON schedule records from `%LOCALAPPDATA%/JARVIS/schedules.json`
      3. Recurring user routines defined in `UserProfile.daily_routines`
    """

    def __init__(
        self,
        calendar_dir: Path | None = None,
        schedules_file: Path | None = None,
    ) -> None:
        self.calendar_dir: Path = calendar_dir or data_path("calendars")
        self.schedules_file: Path = schedules_file or data_path("schedules.json")
        self._save_lock: threading.RLock = threading.RLock()
        self._profile_mgr = get_user_profile_manager()

        # Ensure directory exists
        try:
            self.calendar_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.debug("Failed creating calendar directory: %s", exc)

    def parse_ics_file(self, file_path: Path) -> list[CalendarEvent]:
        """
        Robust, zero-dependency RFC 5545 iCalendar (.ics) parser.
        Unfolds multi-line headers and extracts VEVENT blocks.
        """
        if not file_path.is_file():
            return []

        events: list[CalendarEvent] = []
        try:
            raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
            # Unfold continuation lines (lines beginning with space or tab)
            unfolded = re.sub(r"\r?\n[ \t]", "", raw_text)
            lines = unfolded.splitlines()

            in_vevent = False
            current: dict[str, str] = {}
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line == "BEGIN:VEVENT":
                    in_vevent = True
                    current = {}
                    continue
                elif line == "END:VEVENT":
                    in_vevent = False
                    ev = self._build_event_from_ics_props(current, file_path.stem)
                    if ev is not None:
                        events.append(ev)
                    continue

                if in_vevent and ":" in line:
                    parts = line.split(":", 1)
                    key = parts[0].split(";")[0].upper().strip()
                    val = parts[1].strip()
                    current[key] = val

        except Exception as exc:
            logger.warning("Failed parsing ics file %s: %s", file_path, exc)

        return events

    def _build_event_from_ics_props(self, props: dict[str, str], source_name: str) -> CalendarEvent | None:
        """Convert parsed ICS properties to a CalendarEvent."""
        dtstart_raw = props.get("DTSTART")
        if not dtstart_raw:
            return None

        summary = props.get("SUMMARY", "Sự kiện không tiêu đề")
        location = props.get("LOCATION", "")
        description = props.get("DESCRIPTION", "")
        uid = props.get("UID", f"ics_{abs(hash(summary + dtstart_raw))}")

        start_dt, is_all_day = self._parse_ics_datetime(dtstart_raw)
        if start_dt is None:
            return None

        dtend_raw = props.get("DTEND")
        if dtend_raw:
            end_dt, _ = self._parse_ics_datetime(dtend_raw)
            if end_dt is None:
                end_dt = start_dt + datetime.timedelta(hours=1)
        else:
            end_dt = start_dt + datetime.timedelta(hours=1)

        return CalendarEvent(
            event_id=uid,
            title=summary,
            start_time=start_dt,
            end_time=end_dt,
            location=location,
            description=description,
            is_all_day=is_all_day,
            source=f"ics:{source_name}",
        )

    def _parse_ics_datetime(self, raw: str) -> tuple[datetime.datetime | None, bool]:
        """Parse RFC 5545 datetime or date format."""
        raw = raw.replace("-", "").replace(":", "")
        # Date only: YYYYMMDD
        if len(raw) == 8 and raw.isdigit():
            try:
                d = datetime.date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
                dt = datetime.datetime.combine(d, datetime.time.min)
                return dt, True
            except ValueError:
                return None, False

        # DateTime format: YYYYMMDDTHHMMSS or YYYYMMDDTHHMMSSZ
        clean = raw.rstrip("Z")
        if "T" in clean:
            date_part, time_part = clean.split("T", 1)
            if len(date_part) == 8 and len(time_part) >= 6:
                try:
                    dt = datetime.datetime(
                        int(date_part[:4]),
                        int(date_part[4:6]),
                        int(date_part[6:8]),
                        int(time_part[:2]),
                        int(time_part[2:4]),
                        int(time_part[4:6]),
                    )
                    return dt, False
                except ValueError:
                    return None, False

        return None, False

    def load_json_schedules(self) -> list[CalendarEvent]:
        """Load custom events from schedules.json."""
        if not self.schedules_file.is_file():
            return []

        events: list[CalendarEvent] = []
        try:
            raw = json.loads(self.schedules_file.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        try:
                            events.append(CalendarEvent.from_dict(item))
                        except Exception:
                            pass
        except Exception as exc:
            logger.debug("Failed loading schedules.json: %s", exc)

        return events

    def add_event(
        self,
        title: str,
        start_time: datetime.datetime,
        end_time: datetime.datetime | None = None,
        location: str = "",
        description: str = "",
        is_all_day: bool = False,
    ) -> CalendarEvent:
        """Add and persist a new custom calendar event to schedules.json."""
        if end_time is None:
            end_time = start_time + datetime.timedelta(hours=1)

        ev_id = f"evt_{int(start_time.timestamp())}_{abs(hash(title)) % 10000}"
        event = CalendarEvent(
            event_id=ev_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            location=location,
            description=description,
            is_all_day=is_all_day,
            source="schedules_json",
        )

        with self._save_lock:
            existing = self.load_json_schedules()
            # Replace if same id
            existing = [e for e in existing if e.event_id != ev_id]
            existing.append(event)
            data_to_write = [e.to_dict() for e in existing]
            atomic_write_json(self.schedules_file, data_to_write)

        return event

    def _extract_routine_events(self, profile: UserProfile, target_date: datetime.date) -> list[CalendarEvent]:
        """Convert UserProfile.daily_routines to synthetic CalendarEvents for today."""
        events: list[CalendarEvent] = []
        routines = getattr(profile, "daily_routines", None) or []
        if not routines:
            return events

        for idx, routine in enumerate(routines):
            # Parse routine like "08:00 - Morning Briefing" or "14:00 Code Review"
            m = re.match(r"^(\d{1,2}):(\d{2})\s*(?:[-–:]\s*)?(.*)$", routine.strip())
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2))
                title = m.group(3).strip() or "Lịch trình thường nhật"
                st = datetime.datetime.combine(target_date, datetime.time(hour, minute))
                et = st + datetime.timedelta(minutes=45)
                events.append(CalendarEvent(
                    event_id=f"routine_{idx}_{hour}_{minute}",
                    title=title,
                    start_time=st,
                    end_time=et,
                    location="Bàn làm việc",
                    source="routine",
                ))
            else:
                st = datetime.datetime.combine(target_date, datetime.time(9, 0))
                events.append(CalendarEvent(
                    event_id=f"routine_{idx}",
                    title=routine,
                    start_time=st,
                    end_time=st + datetime.timedelta(hours=1),
                    source="routine",
                ))

        return events

    def get_today_events(self, target_date: datetime.date | None = None) -> list[CalendarEvent]:
        """
        Aggregate all events for the given date (default today) from all sources:
        .ics files, schedules.json, and daily routines.
        """
        ref_date = target_date or datetime.date.today()
        all_events: list[CalendarEvent] = []

        # 1. Parse all .ics files in calendar_dir
        if self.calendar_dir.is_dir():
            for ics_file in self.calendar_dir.glob("*.ics"):
                all_events.extend(self.parse_ics_file(ics_file))

        # 2. Parse schedules.json
        all_events.extend(self.load_json_schedules())

        # 3. Add routines if no specific calendar events exist
        profile = self._profile_mgr.get_profile()
        routine_events = self._extract_routine_events(profile, ref_date)

        # Filter for ref_date
        today_events = [e for e in all_events if e.is_today(ref_date)]

        if not today_events and routine_events:
            today_events.extend(routine_events)

        # Sort chronologically by start_time
        today_events.sort(key=lambda e: e.start_time)
        return today_events

    def format_markdown_schedule(self, events: list[CalendarEvent] | None = None) -> str:
        """Format events list into clean Markdown for executive briefing."""
        ev_list = events if events is not None else self.get_today_events()
        if not ev_list:
            return "- *Không có sự kiện hoặc cuộc họp nào được lên lịch hôm nay. Chủ nhân có thể hoàn toàn tập trung vào nghiên cứu và phát triển.*"

        lines = []
        for ev in ev_list:
            loc_str = f" ({ev.location})" if ev.location else ""
            lines.append(f"- **{ev.time_range_str}**: {ev.title}{loc_str}")
        return "\n".join(lines)

    def format_speech_schedule(
        self,
        events: list[CalendarEvent] | None = None,
        honorific: str = "Chủ nhân",
    ) -> str:
        """Format events into concise natural Vietnamese speech text for TTS."""
        ev_list = events if events is not None else self.get_today_events()
        if not ev_list:
            return f"Lịch trình hôm nay trống, {honorific} có trọn vẹn thời gian để tập trung phát triển."

        count = len(ev_list)
        first_ev = ev_list[0]
        t_str = first_ev.start_time.strftime("%H giờ %M") if not first_ev.is_all_day else "cả ngày"

        if count == 1:
            return f"Hôm nay {honorific} có một sự kiện là '{first_ev.title}' vào lúc {t_str}."
        else:
            return f"Hôm nay {honorific} có {count} sự kiện được lên lịch, sự kiện sớm nhất là '{first_ev.title}' lúc {t_str}."
