"""
jarvis/personalization/__init__.py
==================================
Personal AI Companion & Identity Layer for JARVIS (v9.1.0+).
Provides user identity modeling, personalization profiles, executive morning briefings,
smart calendar schedule provider, and interactive personal onboarding.
"""
from __future__ import annotations

from jarvis.personalization.briefing import BriefingReport, ExecutiveBriefingEngine
from jarvis.personalization.calendar import CalendarEvent, CalendarScheduleProvider
from jarvis.personalization.onboarding import PersonalOnboardingWizard
from jarvis.personalization.profile import (
    PersonaTone,
    UserProfile,
    UserProfileManager,
    get_user_profile_manager,
)

__all__ = [
    "PersonaTone",
    "UserProfile",
    "UserProfileManager",
    "get_user_profile_manager",
    "BriefingReport",
    "ExecutiveBriefingEngine",
    "PersonalOnboardingWizard",
    "CalendarEvent",
    "CalendarScheduleProvider",
]
