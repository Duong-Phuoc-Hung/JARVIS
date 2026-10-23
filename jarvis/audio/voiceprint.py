"""
jarvis/audio/voiceprint.py
==========================
Argon Sovereign Acoustic Authority & Speaker-Attributed Intent Gating Subsystem.
Connects 64-dimensional acoustic voiceprint verification directly to security gating:
- Evaluates Cosine Similarity against enrolled master voiceprint (tau >= 0.70).
- SAFE_INTENT_ALLOWLIST: Read-only & non-destructive intents allowed for all speakers.
- PRIVILEGED_INTENT_ALLOWLIST: OS control, file deletion, and shell execution requiring
  strict biometric verification.
- Fail-closed transactional rejection with UNAUTHORIZED_VOICE status on unauthenticated speech.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from jarvis.audio.biometrics import (
    DEFAULT_PROFILE_PATH,
    DEFAULT_VERIFICATION_THRESHOLD,
    VoiceBiometricsManager,
    VoiceprintProfile,
    compute_cosine_similarity,
    extract_voiceprint,
)

logger = logging.getLogger("jarvis.audio.voiceprint")

# Cosine similarity threshold for Master biometric authority
DEFAULT_MASTER_SIMILARITY_THRESHOLD: float = 0.70

# Intents permitted for any acoustic source (Guests, TV background, Ambient speech)
SAFE_INTENT_ALLOWLIST: set[str] = {
    # Weather & Environmental
    "weather", "weather_query", "get_weather",
    # Clock & Calendar
    "time", "time_query", "get_time", "date_query", "get_date",
    # Information & Web Search
    "web_search", "google_search", "search_web", "general_query", "wiki_search",
    # Media Playback (Non-destructive)
    "spotify", "spotify_play", "media_control", "play_music", "pause_music",
    # Queries & Display Status
    "system_volume", "system_brightness", "hardware_status_query", "system_status",
    "note_read", "notes_list", "reminder_list", "timer_status", "device_read",
    "greeting_chat", "generic_llm_response", "tts_stop",
}

# Intents requiring Master Acoustic Authority (Similarity >= 0.70)
PRIVILEGED_INTENT_ALLOWLIST: set[str] = {
    # System Power & OS State
    "system_power", "power_action", "system_shutdown", "system_reboot",
    "os_shutdown", "os_reboot", "os_sleep", "os_lock",
    # File Operations (especially Deletion)
    "file_management", "delete_file", "file_delete", "delete_folder",
    "remove_directory", "format_disk", "registry_edit",
    # Shell Execution & Code Sandboxing
    "terminal_control", "code_execution", "shell_exec", "shell_execute",
    "shell_command", "sandbox_execute_code", "sandbox_python_exec",
    "powershell_exec", "cmd_exec", "bash_exec",
    # Subagents & Process Life Cycle
    "taskkill", "os_kill_process", "subagent_spawn", "subagent_kill",
}


@dataclass(frozen=True)
class VoiceAuthorityDecision:
    """Immutable audit record of an acoustic authority gate decision."""
    is_authorized: bool
    status_code: str
    similarity_score: float
    threshold: float
    action_name: str
    speaker_name: str
    is_privileged: bool
    reason: str


class VoiceBiometricsGate:
    """
    Biometric Security Gate enforcing Intent-Tiered Acoustic Privilege.
    Prevents unauthorized ambient noise, TV dialogue, or guest speech from
    executing privileged system or destructive commands.
    """

    def __init__(
        self,
        manager: VoiceBiometricsManager | None = None,
        threshold: float = DEFAULT_MASTER_SIMILARITY_THRESHOLD,
        safe_intents: set[str] | None = None,
        privileged_intents: set[str] | None = None,
    ) -> None:
        self.manager = manager or VoiceBiometricsManager()
        self.threshold = float(threshold)
        self.safe_intents = set(safe_intents or SAFE_INTENT_ALLOWLIST)
        self.privileged_intents = set(privileged_intents or PRIVILEGED_INTENT_ALLOWLIST)

    def is_privileged_intent(
        self,
        action_name: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """
        Determines whether the given action and payload constitute a privileged command
        that strictly requires Master Voiceprint authentication.
        """
        clean_action = str(action_name or "").strip().lower()

        # Explicit allowlist check
        if clean_action in self.safe_intents:
            return False

        # File management requires inspection: read/open is normal, deletion is privileged
        if clean_action == "file_management":
            if not isinstance(payload, dict):
                return True  # Fail-closed if payload unspecified
            op = str(payload.get("action") or payload.get("operation") or "").strip().lower()
            if op in ("delete", "remove", "erase", "truncate", "drop", "clean"):
                return True
            # Check parameter strings for delete keywords
            payload_str = str(payload).lower()
            if any(k in payload_str for k in ("delete", "remove", "xóa", "xoa")):
                return True
            return False

        # System power check: non-destructive query is safe, shutdown/restart/sleep is privileged
        if clean_action in ("system_power", "power_action"):
            return True

        if clean_action in self.privileged_intents:
            return True

        # Check action prefixes
        risky_prefixes = (
            "delete_", "remove_", "drop_", "truncate_", "format_", "destroy_",
            "system_shutdown", "system_reboot", "shell_", "terminal_", "sandbox_",
        )
        if any(clean_action.startswith(p) for p in risky_prefixes):
            return True

        return False

    def verify_intent_authority(
        self,
        action_name: str,
        payload: dict[str, Any] | None = None,
        speaker_similarity: float | None = None,
        speaker_audio: np.ndarray | None = None,
        speaker_name: str = "master",
        context: Any | None = None,
    ) -> tuple[bool, str, float]:
        """
        Verifies acoustic authority for an intent.

        Args:
            action_name: Target action identifier.
            payload: Parameters for the action.
            speaker_similarity: Pre-computed Cosine similarity (optional).
            speaker_audio: Raw speech audio buffer for on-the-fly extraction (optional).
            speaker_name: Target master speaker name (default: 'master').
            context: Optional RequesterContext with metadata.

        Returns:
            (is_authorized, status_code, similarity_score)
        """
        is_priv = self.is_privileged_intent(action_name, payload)

        # 1. Safe Intent: Always authorized for all acoustic sources
        if not is_priv:
            sim = float(speaker_similarity) if speaker_similarity is not None else 1.0
            return True, "SAFE_INTENT_ALLOWED", sim

        # 2. Privileged Intent: Must verify against master voiceprint
        sim = self._resolve_similarity(
            speaker_similarity=speaker_similarity,
            speaker_audio=speaker_audio,
            speaker_name=speaker_name,
            context=context,
        )

        # If no profile enrolled yet and manager allows onboarding
        if getattr(self.manager, "enrolled_speakers", None) is not None:
            if len(self.manager.enrolled_speakers) == 0 and self.manager.allow_unregistered_when_empty:
                logger.info(
                    "Acoustic gate ONBOARDING mode (0 enrolled profiles). Allowing action '%s'",
                    action_name,
                )
                return True, "ONBOARDING_ALLOWED", 1.0

        if sim >= self.threshold:
            logger.info(
                "Acoustic authority PASSED for privileged action '%s': similarity=%.4f >= %.2f",
                action_name, sim, self.threshold,
            )
            return True, "AUTHORIZED_MASTER_VOICE", sim

        # Fail-closed rejection
        logger.warning(
            "Acoustic authority DENIED for privileged action '%s': similarity=%.4f < %.2f (UNAUTHORIZED_VOICE)",
            action_name, sim, self.threshold,
        )
        return False, "UNAUTHORIZED_VOICE", sim

    def _resolve_similarity(
        self,
        speaker_similarity: float | None = None,
        speaker_audio: np.ndarray | None = None,
        speaker_name: str = "master",
        context: Any | None = None,
    ) -> float:
        """Resolves cosine similarity score from available parameters or context."""
        if speaker_similarity is not None:
            return float(speaker_similarity)

        # Inspect context metadata
        if context is not None:
            ctx_sim = getattr(context, "speaker_similarity", None)
            if ctx_sim is not None:
                return float(ctx_sim)
            if hasattr(context, "metadata") and isinstance(context.metadata, dict):
                if "speaker_similarity" in context.metadata:
                    return float(context.metadata["speaker_similarity"])
                if "similarity" in context.metadata:
                    return float(context.metadata["similarity"])

        # Compute on-the-fly if audio buffer provided
        if speaker_audio is not None and getattr(speaker_audio, "size", 0) > 0:
            match, spk, score = self.manager.verify_speaker(speaker_audio, speaker_name=speaker_name)
            return float(score)

        return 0.0


__all__ = [
    "VoiceBiometricsGate",
    "VoiceAuthorityDecision",
    "SAFE_INTENT_ALLOWLIST",
    "PRIVILEGED_INTENT_ALLOWLIST",
    "DEFAULT_MASTER_SIMILARITY_THRESHOLD",
    "VoiceBiometricsManager",
    "VoiceprintProfile",
    "extract_voiceprint",
    "compute_cosine_similarity",
]
