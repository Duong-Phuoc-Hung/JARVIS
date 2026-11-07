"""
tests/unit/test_calendar_provider.py
====================================
Unit test suite for CalendarScheduleProvider, CalendarEvent, and Executive Briefing integration.
Verifies RFC 5545 (.ics) parsing, schedules.json atomic persistence, and speech synthesis.
"""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from jarvis.personalization.briefing import ExecutiveBriefingEngine
from jarvis.personalization.calendar import CalendarEvent, CalendarScheduleProvider
from jarvis.personalization.profile import PersonaTone, UserProfile, UserProfileManager


def test_calendar_event_properties():
    now = datetime.datetime.now()
    start_dt = now.replace(hour=10, minute=0, second=0, microsecond=0)
    end_dt = now.replace(hour=11, minute=30, second=0, microsecond=0)

    event = CalendarEvent(
        event_id="evt_test_1",
        title="Họp kiến trúc JARVIS",
        start_time=start_dt,
        end_time=end_dt,
        location="Phòng lab",
    )

    assert event.is_today(now.date()) is True
    yesterday = now.date() - datetime.timedelta(days=1)
    assert event.is_today(yesterday) is False
    assert event.time_range_str == "10:00 - 11:30"

    d = event.to_dict()
    assert d["title"] == "Họp kiến trúc JARVIS"
    assert d["location"] == "Phòng lab"

    restored = CalendarEvent.from_dict(d)
    assert restored.event_id == event.event_id
    assert restored.title == event.title


def test_calendar_ics_parser(tmp_path: Path):
    cal_dir = tmp_path / "calendars"
    cal_dir.mkdir()
    ics_file = cal_dir / "team_calendar.ics"

    today_str = datetime.date.today().strftime("%Y%m%d")
    sample_ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//JARVIS Test Calendar//EN
BEGIN:VEVENT
UID:uid_sample_123@jarvis.ai
DTSTART:{today_str}T090000Z
DTEND:{today_str}T100000Z
SUMMARY:Sprint 31 Demo Meeting
LOCATION:Google Meet
DESCRIPTION:Trình diễn tính năng mới của JARVIS
END:VEVENT
BEGIN:VEVENT
UID:uid_sample_456@jarvis.ai
DTSTART:{today_str}T140000Z
DTEND:{today_str}T153000Z
SUMMARY:Review Code Base
LOCATION:Offline
END:VEVENT
END:VCALENDAR
"""
    ics_file.write_text(sample_ics, encoding="utf-8")

    provider = CalendarScheduleProvider(calendar_dir=cal_dir, schedules_file=tmp_path / "sched.json")
    events = provider.parse_ics_file(ics_file)

    assert len(events) == 2
    assert events[0].title == "Sprint 31 Demo Meeting"
    assert events[0].location == "Google Meet"
    assert events[1].title == "Review Code Base"


def test_schedules_json_add_and_persistence(tmp_path: Path):
    sched_file = tmp_path / "schedules.json"
    provider = CalendarScheduleProvider(calendar_dir=tmp_path / "cals", schedules_file=sched_file)

    now = datetime.datetime.now()
    st = now.replace(hour=15, minute=0, second=0, microsecond=0)
    et = now.replace(hour=16, minute=0, second=0, microsecond=0)

    ev = provider.add_event(
        title="Kiểm tra hệ thống âm học",
        start_time=st,
        end_time=et,
        location="Phòng Audio",
    )
    assert ev.event_id.startswith("evt_")
    assert sched_file.is_file()

    # Load again in new provider instance
    provider2 = CalendarScheduleProvider(calendar_dir=tmp_path / "cals", schedules_file=sched_file)
    today_events = provider2.get_today_events()
    assert len(today_events) == 1
    assert today_events[0].title == "Kiểm tra hệ thống âm học"

    # Markdown & Speech formatting
    md = provider2.format_markdown_schedule(today_events)
    assert "15:00 - 16:00" in md
    assert "Kiểm tra hệ thống âm học" in md

    speech = provider2.format_speech_schedule(today_events, honorific="Chủ nhân")
    assert "Kiểm tra hệ thống âm học" in speech
    assert "15 giờ 00" in speech


def test_executive_briefing_with_calendar_integration(tmp_path: Path):
    prof_file = tmp_path / "user_prof.json"
    sched_file = tmp_path / "schedules.json"
    cal_dir = tmp_path / "cals"
    cal_dir.mkdir()

    pm = UserProfileManager(profile_path=prof_file)
    pm.update_profile(user_name="Hưng", honorific="Chủ nhân", tone=PersonaTone.IRON_MAN_WITTY)

    prov = CalendarScheduleProvider(calendar_dir=cal_dir, schedules_file=sched_file)
    now = datetime.datetime.now()
    prov.add_event(
        title="Thử nghiệm Dynamic Island HUD",
        start_time=now.replace(hour=9, minute=30, second=0, microsecond=0),
        end_time=now.replace(hour=10, minute=30, second=0, microsecond=0),
    )

    engine = ExecutiveBriefingEngine(profile_manager=pm, schedule_provider=prov)
    report = engine.generate_morning_briefing()

    assert len(report.schedule_events) == 1
    assert report.schedule_events[0]["title"] == "Thử nghiệm Dynamic Island HUD"
    assert "### 📅 Lịch Trình & Sự Kiện Hôm Nay" in report.summary_markdown
    assert "Thử nghiệm Dynamic Island HUD" in report.summary_markdown
    assert "Thử nghiệm Dynamic Island HUD" in report.speech_script
