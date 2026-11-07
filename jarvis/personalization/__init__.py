"""
jarvis/personalization/__init__.py
==================================
Personal AI Companion & Identity Layer for JARVIS.
Provides user identity modeling, personalization profiles, executive morning briefings,
and interactive personal onboarding.
"""
from __future__ import annotations

from jarvis.personalization.briefing import BriefingReport, ExecutiveBriefingEngine
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
]
