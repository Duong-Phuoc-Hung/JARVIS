"""
jarvis/personalization/onboarding.py
====================================
Personal Onboarding Wizard for JARVIS.
Guides the user to configure their identity, honorifics, workspace preferences,
and communication tone to transform JARVIS into their personal AI companion.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from jarvis.personalization.profile import (
    PersonaTone,
    UserProfile,
    UserProfileManager,
    get_user_profile_manager,
)

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("jarvis.personalization.onboarding")


class PersonalOnboardingWizard:
    """Interactive onboarding wizard configuring personal identity for JARVIS."""

    def __init__(
        self,
        interactive: bool = True,
        profile_manager: UserProfileManager | None = None,
    ) -> None:
        self.interactive = interactive
        self.profile_mgr = profile_manager or get_user_profile_manager()

    def run(self) -> dict[str, Any]:
        """Execute full personal onboarding flow."""
        self._print_banner()

        current = self.profile_mgr.get_profile()

        # Step 1: User Name & Honorific
        user_name, honorific = self._step_name_and_honorific(current)

        # Step 2: Assistant Identity & Tone
        asst_name, tone = self._step_assistant_and_tone(current)

        # Step 3: Workspace & Tools
        workspace, preferred_apps = self._step_workspace_and_tools(current)

        # Step 4: Work Hours & Briefing
        start_hr, end_hr, briefing_enabled = self._step_habits(current)

        # Step 5: Save Profile Atomically
        updated_profile = self.profile_mgr.update_profile(
            user_name=user_name,
            honorific=honorific,
            assistant_name=asst_name,
            tone=tone,
            primary_workspace=workspace,
            preferred_apps=preferred_apps,
            work_start_hour=start_hr,
            work_end_hour=end_hr,
            daily_briefing_enabled=briefing_enabled,
        )

        self._print_completion(updated_profile)
        self._vocalize_welcome(updated_profile)

        return updated_profile.to_dict()

    def _print_banner(self) -> None:
        print("\n" + "=" * 70)
        print("   👑 QUY TRÌNH THIẾT LẬP DANH TÍNH CÁ NHÂN — JARVIS SOVEREIGN")
        print("=" * 70)
        print("Chào mừng bạn! Quy trình này sẽ định hình danh xưng, phong cách")
        print("và thói quen để JARVIS phục vụ độc quyền cho riêng bạn.\n")

    def _step_name_and_honorific(self, current: UserProfile) -> tuple[str, str]:
        print("-" * 70)
        print("BƯỚC 1/4: TÊN GỌI & DANH XƯNG CỦA BẠN")
        print("-" * 70)

        user_name = current.user_name
        honorific = current.honorific

        if self.interactive and sys.stdin.isatty():
            try:
                name_in = input(f"Tên của bạn [mặc định: {user_name}]: ").strip()
                if name_in:
                    user_name = name_in

                print("\nChọn cách xưng hô bạn muốn JARVIS gọi:")
                print("  [1] 'Chủ nhân' (Phong cách Tony Stark / Iron Man)")
                print("  [2] 'Boss'")
                print("  [3] 'Anh'")
                print("  [4] 'Chị'")
                print("  [5] 'Bạn'")
                print("  [6] Tự nhập danh xưng khác")

                choice = input("Lựa chọn [1-6, mặc định: 1]: ").strip()
                if choice == "2":
                    honorific = "Boss"
                elif choice == "3":
                    honorific = "Anh"
                elif choice == "4":
                    honorific = "Chị"
                elif choice == "5":
                    honorific = "Bạn"
                elif choice == "6":
                    custom_h = input("Nhập danh xưng tùy chỉnh: ").strip()
                    if custom_h:
                        honorific = custom_h
                else:
                    honorific = "Chủ nhân"
            except EOFError:
                pass

        print(f"-> Danh xưng xác lập: '{honorific} {user_name}'\n")
        return user_name, honorific

    def _step_assistant_and_tone(self, current: UserProfile) -> tuple[str, PersonaTone]:
        print("-" * 70)
        print("BƯỚC 2/4: DANH TÍNH & PHONG CÁCH CỦA TRỢ LÝ")
        print("-" * 70)

        asst_name = current.assistant_name
        tone = current.tone

        if self.interactive and sys.stdin.isatty():
            try:
                asst_in = input(f"Tên gọi của trợ lý [mặc định: {asst_name}]: ").strip()
                if asst_in:
                    asst_name = asst_in

                print("\nChọn phong thái giao tiếp của trợ lý:")
                print("  [1] Dí dỏm, súc tích & thông minh (Iron Man JARVIS style - Khuyên dùng)")
                print("  [2] Trang trọng, tối giản, chuyên nghiệp 100%")
                print("  [3] Ấm áp, thân thiện, chu đáo đồng hành")

                choice = input("Lựa chọn [1-3, mặc định: 1]: ").strip()
                if choice == "2":
                    tone = PersonaTone.FORMAL_CONCISE
                elif choice == "3":
                    tone = PersonaTone.FRIENDLY_HELPFUL
                else:
                    tone = PersonaTone.IRON_MAN_WITTY
            except EOFError:
                pass

        tone_label = {
            PersonaTone.IRON_MAN_WITTY: "Dí dỏm & Súc tích",
            PersonaTone.FORMAL_CONCISE: "Trang trọng & Tối giản",
            PersonaTone.FRIENDLY_HELPFUL: "Thân thiện & Chu đáo",
        }.get(tone, "Chuẩn mực")

        print(f"-> Trợ lý: '{asst_name}' | Phong thái: '{tone_label}'\n")
        return asst_name, tone

    def _step_workspace_and_tools(self, current: UserProfile) -> tuple[str, list[str]]:
        print("-" * 70)
        print("BƯỚC 3/4: THƯ MỤC DỰ ÁN & CÔNG CỤ LÀM VIỆC ƯU TIÊN")
        print("-" * 70)

        workspace = current.primary_workspace
        preferred_apps = list(current.preferred_apps)

        if self.interactive and sys.stdin.isatty():
            try:
                ws_in = input(f"Thư mục làm việc / code chính [mặc định: {workspace}]: ").strip()
                if ws_in:
                    workspace = ws_in

                apps_in = input(f"Các ứng dụng bạn hay mở (cách nhau bởi dấu phẩy) [mặc định: {', '.join(preferred_apps)}]: ").strip()
                if apps_in:
                    preferred_apps = [a.strip() for a in apps_in.split(",") if a.strip()]
            except EOFError:
                pass

        print(f"-> Thư mục dự án: {workspace}")
        print(f"-> Ứng dụng ưu tiên: {', '.join(preferred_apps)}\n")
        return workspace, preferred_apps

    def _step_habits(self, current: UserProfile) -> tuple[int, int, bool]:
        print("-" * 70)
        print("BƯỚC 4/4: GIỜ LÀM VIỆC & BÁO CÁO ĐẦU NGÀY (EXECUTIVE BRIEFING)")
        print("-" * 70)

        start_hr = current.work_start_hour
        end_hr = current.work_end_hour
        briefing_enabled = current.daily_briefing_enabled

        if self.interactive and sys.stdin.isatty():
            try:
                hr_in = input(f"Giờ bắt đầu làm việc buổi sáng (0-23) [mặc định: {start_hr}]: ").strip()
                if hr_in.isdigit():
                    start_hr = int(hr_in)

                bf_in = input("Kích hoạt Báo Cáo Buổi Sáng (Morning Briefing) tự động? [Y/n, mặc định: Y]: ").strip().lower()
                if bf_in in ("n", "no", "false", "0"):
                    briefing_enabled = False
                else:
                    briefing_enabled = True
            except EOFError:
                pass

        status_str = "BẬT" if briefing_enabled else "TẮT"
        print(f"-> Giờ làm việc: {start_hr}:00 — {end_hr}:00 | Báo cáo đầu ngày: {status_str}\n")
        return start_hr, end_hr, briefing_enabled

    def _print_completion(self, profile: UserProfile) -> None:
        print("=" * 70)
        print(f"✨ HOÀN TẤT THIẾT LẬP HỒ SƠ! {profile.assistant_name} ĐÃ NHẬN DIỆN CHỦ NHÂN.")
        print("=" * 70)
        print(f"  • Danh xưng     : {profile.honorific} {profile.user_name}")
        print(f"  • Trợ lý        : {profile.assistant_name}")
        print(f"  • Phong cách    : {profile.tone.value}")
        print(f"  • Workspace     : {profile.primary_workspace}")
        print(f"  • Morning Report: {'Có' if profile.daily_briefing_enabled else 'Không'}")
        print("-" * 70)
        print(f"Chào mừng {profile.honorific}! Bây giờ {profile.assistant_name} đã sẵn sàng phục vụ bạn.\n")

    def _vocalize_welcome(self, profile: UserProfile) -> None:
        """Attempt vocal welcome via TTS if audio subsystem is available."""
        greeting = profile.generate_greeting()
        try:
            from jarvis.tts.manager import TTSManager
            tts = TTSManager()
            tts.speak(greeting)
        except Exception as exc:
            logger.debug(f"TTS greeting skipped during onboarding: {exc}")


def run_onboarding_auto() -> dict[str, Any]:
    """Automated verification mode for test suites and headless environments."""
    wizard = PersonalOnboardingWizard(interactive=False)
    return wizard.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS Personal Onboarding Wizard")
    parser.add_argument("--auto", action="store_true", help="Run in automated headless test mode")
    args = parser.parse_args()

    wiz = PersonalOnboardingWizard(interactive=not args.auto)
    res = wiz.run()
    if args.auto:
        print("\nJSON Output:")
        print(json.dumps(res, indent=2, ensure_ascii=False))
