"""
tests/unit/test_user_profile.py
===============================
Unit test suite for UserProfile, PersonaTone, and UserProfileManager.
Verifies Windows atomic persistence, schema integrity, and greeting synthesis.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.personalization.profile import (
    PersonaTone,
    UserProfile,
    UserProfileManager,
    get_user_profile_manager,
)


def test_user_profile_defaults_and_serialization():
    profile = UserProfile(
        user_name="Hưng",
        honorific="Chủ nhân",
        assistant_name="JARVIS",
        tone=PersonaTone.IRON_MAN_WITTY,
    )

    data = profile.to_dict()
    assert data["user_name"] == "Hưng"
    assert data["honorific"] == "Chủ nhân"
    assert data["assistant_name"] == "JARVIS"
    assert data["tone"] == "iron_man_witty"
    assert "Cursor" in data["preferred_apps"]

    restored = UserProfile.from_dict(data)
    assert restored.user_name == "Hưng"
    assert restored.honorific == "Chủ nhân"
    assert restored.assistant_name == "JARVIS"
    assert restored.tone == PersonaTone.IRON_MAN_WITTY


def test_user_profile_greetings_by_tone_and_hour():
    profile = UserProfile(
        user_name="Hưng",
        honorific="Chủ nhân",
        tone=PersonaTone.IRON_MAN_WITTY,
    )

    # Morning
    morning_greet = profile.generate_greeting(hour=8)
    assert "buổi sáng" in morning_greet
    assert "Chủ nhân Hưng" in morning_greet

    # Afternoon
    afternoon_greet = profile.generate_greeting(hour=14)
    assert "buổi chiều" in afternoon_greet
    assert "Chủ nhân" in afternoon_greet

    # Night
    night_greet = profile.generate_greeting(hour=22)
    assert "về đêm" in night_greet

    # Formal tone
    profile.tone = PersonaTone.FORMAL_CONCISE
    formal_greet = profile.generate_greeting(hour=9)
    assert "sẵn sàng nhận lệnh" in formal_greet

    # Friendly tone
    profile.tone = PersonaTone.FRIENDLY_HELPFUL
    friendly_greet = profile.generate_greeting(hour=9)
    assert "tràn đầy năng lượng" in friendly_greet


def test_user_profile_system_persona_prompt():
    profile = UserProfile(
        user_name="Alex",
        honorific="Boss",
        assistant_name="FRIDAY",
        tone=PersonaTone.IRON_MAN_WITTY,
        custom_rules=["Luôn cung cấp drop-in code", "Không dùng placeholder"],
    )

    prompt = profile.generate_system_persona_prompt()
    assert "Tên trợ lý: FRIDAY" in prompt
    assert "Tên người dùng: Alex" in prompt
    assert "'Boss'" in prompt
    assert "Luôn cung cấp drop-in code" in prompt


def test_user_profile_manager_atomic_save_and_load(tmp_path: Path):
    profile_file = tmp_path / "user_profile_test.json"
    mgr = UserProfileManager(profile_path=profile_file)

    # Initially file does not exist, defaults returned
    p1 = mgr.get_profile()
    assert p1.user_name != ""

    # Update profile
    p2 = mgr.update_profile(
        user_name="Tony",
        honorific="Ngài Stark",
        assistant_name="JARVIS",
        tone=PersonaTone.IRON_MAN_WITTY,
        primary_workspace=str(tmp_path),
    )
    assert p2.user_name == "Tony"
    assert p2.honorific == "Ngài Stark"
    assert profile_file.exists()

    # Load in new manager instance from same file
    mgr2 = UserProfileManager(profile_path=profile_file)
    p3 = mgr2.load_profile()
    assert p3.user_name == "Tony"
    assert p3.honorific == "Ngài Stark"
    assert p3.primary_workspace == str(tmp_path)


def test_user_profile_manager_reset(tmp_path: Path):
    profile_file = tmp_path / "user_profile_reset.json"
    mgr = UserProfileManager(profile_path=profile_file)
    mgr.update_profile(user_name="TempUser", honorific="Bro")

    assert mgr.get_profile().user_name == "TempUser"

    res = mgr.reset_to_default()
    assert res.honorific == "Chủ nhân"
    assert mgr.get_profile().honorific == "Chủ nhân"


def test_build_jarvis_system_prompt_personalization():
    from jarvis.llm.router import build_jarvis_system_prompt

    custom_profile = UserProfile(
        user_name="Tony Stark",
        honorific="Ngài Stark",
        assistant_name="JARVIS",
        tone=PersonaTone.IRON_MAN_WITTY,
        primary_workspace="d:\\Projects\\IronMan",
    )

    prompt = build_jarvis_system_prompt(user_profile=custom_profile)
    assert "Tên trợ lý: JARVIS" in prompt
    assert "Tên người dùng: Tony Stark" in prompt
    assert "Danh xưng bắt buộc khi nói chuyện: 'Ngài Stark'" in prompt
    assert "d:\\Projects\\IronMan" in prompt
    assert "Always address the user according to their personalized honorific" in prompt
