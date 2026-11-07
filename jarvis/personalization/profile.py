"""
jarvis/personalization/profile.py
=================================
User Profile & Personalization Subsystem.
Follows AGENTS.md Windows Atomic Persistence standards and Anti-Fabrication principles.
Stores user identity, honorifics, daily work habits, preferred tools, and communication tone.
"""
from __future__ import annotations

import datetime
import enum
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jarvis.core.paths import data_path
from jarvis.utils.atomic_io import atomic_write_json

logger = logging.getLogger("jarvis.personalization.profile")


class PersonaTone(str, enum.Enum):
    """Voice & conversational attitude of the personal AI."""
    IRON_MAN_WITTY = "iron_man_witty"      # Witty, razor-sharp, suave and polite like Tony Stark's JARVIS
    FORMAL_CONCISE = "formal_concise"      # Strictly professional, zero small-talk, maximum efficiency
    FRIENDLY_HELPFUL = "friendly_helpful"  # Warm, empathetic, encouraging personal companion


@dataclass
class UserProfile:
    """Master model capturing the user's personal identity and system preferences."""
    user_name: str = "Hưng"
    honorific: str = "Chủ nhân"
    assistant_name: str = "JARVIS"
    tone: PersonaTone = PersonaTone.IRON_MAN_WITTY
    primary_workspace: str = "d:\\Software GitCode"
    preferred_apps: list[str] = field(default_factory=lambda: ["Cursor", "VS Code", "Chrome", "Terminal", "Spotify"])
    work_start_hour: int = 8
    work_end_hour: int = 18
    daily_briefing_enabled: bool = True
    email_address: str = ""
    custom_rules: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to serializable JSON dictionary."""
        data = asdict(self)
        data["tone"] = self.tone.value if isinstance(self.tone, PersonaTone) else str(self.tone)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserProfile:
        """Create a UserProfile instance from raw dictionary data with validation."""
        if not isinstance(data, dict):
            return cls()

        tone_str = data.get("tone", PersonaTone.IRON_MAN_WITTY.value)
        try:
            tone_enum = PersonaTone(tone_str)
        except (ValueError, KeyError):
            tone_enum = PersonaTone.IRON_MAN_WITTY

        preferred_apps = data.get("preferred_apps")
        if not isinstance(preferred_apps, list):
            preferred_apps = ["Cursor", "VS Code", "Chrome", "Terminal", "Spotify"]

        custom_rules = data.get("custom_rules")
        if not isinstance(custom_rules, list):
            custom_rules = []

        return cls(
            user_name=str(data.get("user_name", "Hưng")).strip() or "Hưng",
            honorific=str(data.get("honorific", "Chủ nhân")).strip() or "Chủ nhân",
            assistant_name=str(data.get("assistant_name", "JARVIS")).strip() or "JARVIS",
            tone=tone_enum,
            primary_workspace=str(data.get("primary_workspace", "d:\\Software GitCode")).strip(),
            preferred_apps=preferred_apps,
            work_start_hour=int(data.get("work_start_hour", 8)),
            work_end_hour=int(data.get("work_end_hour", 18)),
            daily_briefing_enabled=bool(data.get("daily_briefing_enabled", True)),
            email_address=str(data.get("email_address", "")).strip(),
            custom_rules=custom_rules,
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )

    def generate_greeting(self, hour: int | None = None) -> str:
        """
        Generate contextual personalized greeting based on current time of day
        and selected communication tone.
        """
        if hour is None:
            hour = datetime.datetime.now().hour

        h = self.honorific
        u = self.user_name

        if 5 <= hour < 12:
            time_of_day = "buổi sáng"
        elif 12 <= hour < 18:
            time_of_day = "buổi chiều"
        else:
            time_of_day = "buổi tối"

        if self.tone == PersonaTone.IRON_MAN_WITTY:
            if time_of_day == "buổi sáng":
                return f"Chào buổi sáng {h} {u}. Hệ thống đã trực chiến 100%, sẵn sàng cùng {h} tạo nên đột phá hôm nay."
            elif time_of_day == "buổi chiều":
                return f"Chào buổi chiều {h}. Tôi vẫn đang giám sát toàn bộ tiến trình, {h} cần xử lý tác vụ nào tiếp theo?"
            else:
                return f"Đã về đêm rồi {h} {u}. Tôi vẫn giữ kết nối bảo vệ hệ thống, đừng quên nghỉ ngơi điều độ nhé."

        elif self.tone == PersonaTone.FORMAL_CONCISE:
            return f"Xin chào {h} {u}. Báo cáo {self.assistant_name} đã sẵn sàng nhận lệnh."

        else:  # FRIENDLY_HELPFUL
            return f"Chào {h} {u}! Chúc {h} một {time_of_day} tràn đầy năng lượng và hiệu quả. Tôi có thể giúp gì cho {h} bây giờ?"

    def generate_system_persona_prompt(self) -> str:
        """
        Generate prompt injection string ensuring all downstream LLM calls
        respect user identity, honorifics, workspace context, and tone.
        """
        rules_text = ""
        if self.custom_rules:
            rules_text = "\nNguyên tắc riêng của chủ nhân:\n" + "\n".join(f"- {r}" for r in self.custom_rules)

        tone_desc = {
            PersonaTone.IRON_MAN_WITTY: "Dí dỏm, thông minh, sắc sảo, lịch thiệp và tự tin như JARVIS của Tony Stark. Trả lời súc tích, giải quyết thẳng vào vấn đề.",
            PersonaTone.FORMAL_CONCISE: "Trang trọng, tuyệt đối chuẩn xác, không phiếm đàm, tập trung 100% vào hiệu suất.",
            PersonaTone.FRIENDLY_HELPFUL: "Ấm áp, chu đáo, nhiệt tình hỗ trợ và khích lệ.",
        }.get(self.tone, "Súc tích và thông minh.")

        return (
            f"=== THÔNG TIN DANH TÍNH CHỦ NHÂN & CÁ NHÂN HÓA ===\n"
            f"- Tên trợ lý: {self.assistant_name}\n"
            f"- Tên người dùng: {self.user_name}\n"
            f"- Danh xưng bắt buộc khi nói chuyện: '{self.honorific}' (hoặc '{self.honorific} {self.user_name}')\n"
            f"- Tông giọng tương tác: {tone_desc}\n"
            f"- Thư mục dự án chính: {self.primary_workspace}\n"
            f"- Ứng dụng ưu tiên: {', '.join(self.preferred_apps)}\n"
            f"{rules_text}\n"
            f"=================================================="
        )


class UserProfileManager:
    """
    Thread-safe User Profile repository managing persistence in LocalAppData/JARVIS/user_profile.json
    using Windows Atomic Persistence standards.
    """

    def __init__(self, profile_path: Path | None = None) -> None:
        self.profile_path: Path = profile_path or data_path("user_profile.json")
        self._save_lock: threading.RLock = threading.RLock()
        self._cache_lock: threading.RLock = threading.RLock()
        self._profile: UserProfile | None = None

    def get_profile(self) -> UserProfile:
        """Retrieve current cached UserProfile or load from persistent storage."""
        with self._cache_lock:
            if self._profile is not None:
                return self._profile

        # Load from disk
        return self.load_profile()

    def update_profile(
        self,
        user_name: str | None = None,
        honorific: str | None = None,
        assistant_name: str | None = None,
        tone: PersonaTone | str | None = None,
        primary_workspace: str | None = None,
        preferred_apps: list[str] | None = None,
        work_start_hour: int | None = None,
        work_end_hour: int | None = None,
        daily_briefing_enabled: bool | None = None,
        email_address: str | None = None,
        custom_rules: list[str] | None = None,
    ) -> UserProfile:
        """
        Update selected fields on user profile and atomically persist to disk.
        """
        with self._cache_lock:
            current = self.get_profile()

            tone_enum = current.tone
            if tone is not None:
                if isinstance(tone, PersonaTone):
                    tone_enum = tone
                else:
                    try:
                        tone_enum = PersonaTone(str(tone))
                    except (ValueError, KeyError):
                        pass

            updated = UserProfile(
                user_name=current.user_name if user_name is None else str(user_name).strip(),
                honorific=current.honorific if honorific is None else str(honorific).strip(),
                assistant_name=current.assistant_name if assistant_name is None else str(assistant_name).strip(),
                tone=tone_enum,
                primary_workspace=current.primary_workspace if primary_workspace is None else str(primary_workspace).strip(),
                preferred_apps=list(current.preferred_apps if preferred_apps is None else preferred_apps),
                work_start_hour=current.work_start_hour if work_start_hour is None else int(work_start_hour),
                work_end_hour=current.work_end_hour if work_end_hour is None else int(work_end_hour),
                daily_briefing_enabled=current.daily_briefing_enabled if daily_briefing_enabled is None else bool(daily_briefing_enabled),
                email_address=current.email_address if email_address is None else str(email_address).strip(),
                custom_rules=list(current.custom_rules if custom_rules is None else custom_rules),
                created_at=current.created_at,
                updated_at=time.time(),
            )
            self._profile = updated

        self.save_profile()
        return updated

    def save_profile(self) -> bool:
        """
        Save cached user profile to disk using atomic rename and retry backoff.
        """
        with self._save_lock:
            with self._cache_lock:
                if self._profile is None:
                    self._profile = self._load_from_disk_unsafe()
                snapshot = self._profile.to_dict()

            try:
                self.profile_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(self.profile_path, snapshot, indent=2, ensure_ascii=False)
                logger.info(f"User profile atomically persisted to {self.profile_path}")
                return True
            except Exception as exc:
                logger.error(f"Failed to persist user profile to {self.profile_path}: {exc}")
                return False

    def load_profile(self) -> UserProfile:
        """Load profile from disk or initialize with sane defaults."""
        with self._save_lock:
            profile = self._load_from_disk_unsafe()
            with self._cache_lock:
                self._profile = profile
            return profile

    def _load_from_disk_unsafe(self) -> UserProfile:
        if not self.profile_path.exists():
            default_profile = self._detect_host_defaults()
            return default_profile

        try:
            import json
            raw_text = self.profile_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            return UserProfile.from_dict(data)
        except Exception as exc:
            logger.warning(f"Could not parse user profile at {self.profile_path}: {exc}. Using host defaults.")
            return self._detect_host_defaults()

    def _detect_host_defaults(self) -> UserProfile:
        """Autodetect host username and primary Git repository directory."""
        user_env = os.environ.get("USERNAME") or os.environ.get("USER") or "Hưng"
        workspace = "d:\\Software GitCode"
        if not Path(workspace).exists():
            home_projects = Path.home() / "source" / "repos"
            if home_projects.exists():
                workspace = str(home_projects)
            else:
                workspace = str(Path.home())

        return UserProfile(
            user_name=user_env,
            honorific="Chủ nhân",
            assistant_name="JARVIS",
            tone=PersonaTone.IRON_MAN_WITTY,
            primary_workspace=workspace,
            preferred_apps=["Cursor", "VS Code", "Chrome", "Terminal", "Spotify"],
            daily_briefing_enabled=True,
        )

    def reset_to_default(self) -> UserProfile:
        """Reset profile to host default values and overwrite file."""
        defaults = self._detect_host_defaults()
        with self._cache_lock:
            self._profile = defaults
        self.save_profile()
        return defaults


_GLOBAL_PROFILE_MANAGER: UserProfileManager | None = None
_GLOBAL_PROFILE_LOCK = threading.Lock()


def get_user_profile_manager(profile_path: Path | None = None) -> UserProfileManager:
    """Return canonical global UserProfileManager singleton."""
    global _GLOBAL_PROFILE_MANAGER
    if profile_path is not None:
        return UserProfileManager(profile_path=profile_path)

    with _GLOBAL_PROFILE_LOCK:
        if _GLOBAL_PROFILE_MANAGER is None:
            _GLOBAL_PROFILE_MANAGER = UserProfileManager()
        return _GLOBAL_PROFILE_MANAGER
