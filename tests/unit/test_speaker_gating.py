"""
tests/unit/test_speaker_gating.py
=================================
Acoustic Authority & Speaker-Attributed Intent Gating Unit Tests (Argon Sovereign Frontier 2).
Validates:
  - SAFE_INTENT_ALLOWLIST: read-only queries (weather, time, web search, media/spotify, volume/brightness)
    are permitted for all acoustic sources (guests, ambient noise, similarity < 0.70).
  - PRIVILEGED_INTENT_ALLOWLIST: OS power, file deletion, shell execution, terminal control
    strictly require Cosine Similarity >= 0.70 against enrolled master voiceprint.
  - Fail-closed transactional rejection with UNAUTHORIZED_VOICE status on unauthenticated speech.
  - File management discrimination: browsing is permitted, deletion requires acoustic authority.
  - Integration with ActionDispatcher and SafetyGateInterceptor.
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.audio.voiceprint import (
    DEFAULT_MASTER_SIMILARITY_THRESHOLD,
    PRIVILEGED_INTENT_ALLOWLIST,
    SAFE_INTENT_ALLOWLIST,
    VoiceBiometricsGate,
    VoiceBiometricsManager,
)
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult, ActionStatus, PrivilegeLevel, RequesterContext
from jarvis.planner.safety_interceptor import SafetyGateInterceptor


@pytest.fixture
def voice_gate(tmp_path) -> VoiceBiometricsGate:
    """Creates an isolated VoiceBiometricsGate instance with temp storage."""
    mgr = VoiceBiometricsManager(storage_path=tmp_path / "voiceprints.json", allow_unregistered_when_empty=False)
    # Enroll a dummy master profile so we are not in onboarding mode
    dummy_audio = np.ones(16000, dtype=np.float32) * 0.1
    mgr.enroll(speaker_name="master", audio=dummy_audio, threshold=0.70)
    return VoiceBiometricsGate(manager=mgr, threshold=DEFAULT_MASTER_SIMILARITY_THRESHOLD)


class TestVoiceBiometricsGate:
    """Direct unit tests for VoiceBiometricsGate."""

    def test_safe_intents_allowed_for_unverified_speakers(self, voice_gate: VoiceBiometricsGate) -> None:
        """Weather, time, web search, spotify, volume are allowed for guest/low-similarity speakers."""
        safe_actions = ["weather", "time", "web_search", "spotify", "system_volume", "system_brightness"]
        for act in safe_actions:
            # Low similarity / guest speaker (e.g. 0.25)
            is_auth, status, score = voice_gate.verify_intent_authority(
                action_name=act,
                payload={},
                speaker_similarity=0.25,
            )
            assert is_auth is True, f"Action '{act}' should be permitted for all speakers"
            assert status == "SAFE_INTENT_ALLOWED"
            assert score == 0.25

    def test_privileged_intents_rejected_for_low_similarity(self, voice_gate: VoiceBiometricsGate) -> None:
        """System power, terminal control, shell execution fail-closed when similarity < 0.70."""
        priv_actions = ["system_power", "terminal_control", "code_execution", "shell_exec", "system_shutdown"]
        for act in priv_actions:
            # Ambient speech / guest similarity (0.55 < 0.70)
            is_auth, status, score = voice_gate.verify_intent_authority(
                action_name=act,
                payload={},
                speaker_similarity=0.55,
            )
            assert is_auth is False, f"Action '{act}' must be rejected for similarity < 0.70"
            assert status == "UNAUTHORIZED_VOICE"
            assert score == 0.55

    def test_privileged_intents_allowed_for_master_authority(self, voice_gate: VoiceBiometricsGate) -> None:
        """Privileged actions succeed when speaker similarity >= 0.70."""
        priv_actions = ["system_power", "terminal_control", "code_execution", "shell_exec"]
        for act in priv_actions:
            is_auth, status, score = voice_gate.verify_intent_authority(
                action_name=act,
                payload={},
                speaker_similarity=0.88,
            )
            assert is_auth is True, f"Action '{act}' must succeed for master speaker"
            assert status == "AUTHORIZED_MASTER_VOICE"
            assert score == 0.88

    def test_file_management_deletion_requires_privilege(self, voice_gate: VoiceBiometricsGate) -> None:
        """File management: browsing/reading is safe, deletion requires master authority."""
        # Case A: Browsing / opening a directory -> safe
        is_auth, status, _ = voice_gate.verify_intent_authority(
            action_name="file_management",
            payload={"action": "open", "path": "C:/Users"},
            speaker_similarity=0.30,
        )
        assert is_auth is True
        assert status == "SAFE_INTENT_ALLOWED"

        # Case B: File deletion -> privileged, rejected for low similarity
        is_auth, status, _ = voice_gate.verify_intent_authority(
            action_name="file_management",
            payload={"action": "delete", "target": "important_file.txt"},
            speaker_similarity=0.30,
        )
        assert is_auth is False
        assert status == "UNAUTHORIZED_VOICE"

        # Case C: File deletion -> master authorized (similarity >= 0.70)
        is_auth, status, _ = voice_gate.verify_intent_authority(
            action_name="file_management",
            payload={"action": "delete", "target": "temp.log"},
            speaker_similarity=0.78,
        )
        assert is_auth is True
        assert status == "AUTHORIZED_MASTER_VOICE"

    def test_context_metadata_similarity_resolution(self, voice_gate: VoiceBiometricsGate) -> None:
        """Resolves speaker similarity automatically from RequesterContext metadata."""
        ctx_guest = RequesterContext(
            requester_id="user_voice",
            metadata={"speaker_similarity": 0.42, "voice": True},
        )
        is_auth, status, score = voice_gate.verify_intent_authority(
            action_name="system_power",
            payload={"action": "shutdown"},
            context=ctx_guest,
        )
        assert is_auth is False
        assert status == "UNAUTHORIZED_VOICE"
        assert score == 0.42

        ctx_master = RequesterContext(
            requester_id="user_voice",
            metadata={"speaker_similarity": 0.91, "voice": True},
        )
        is_auth, status, score = voice_gate.verify_intent_authority(
            action_name="system_power",
            payload={"action": "shutdown"},
            context=ctx_master,
        )
        assert is_auth is True
        assert status == "AUTHORIZED_MASTER_VOICE"
        assert score == 0.91


class TestActionDispatcherVoiceGating:
    """Integration tests for ActionDispatcher with VoiceBiometricsGate."""

    def test_dispatcher_allows_safe_voice_action_for_guest(self, voice_gate: VoiceBiometricsGate) -> None:
        """Dispatcher permits safe intent (e.g. system_volume) even when voice similarity is low."""
        dispatcher = ActionDispatcher(voice_gate=voice_gate)
        dispatched_levels = []

        def mock_volume(**kwargs):
            lvl = kwargs.get("level", 50)
            dispatched_levels.append(lvl)
            return ActionResult(action_name="system_volume", success=True, data={"level": lvl})

        dispatcher.register_action("system_volume", mock_volume)

        guest_ctx = RequesterContext(
            requester_id="user_voice",
            metadata={"voice": True, "speaker_similarity": 0.20},
        )
        res = dispatcher.dispatch_action("system_volume", payload={"level": 70}, requester=guest_ctx)
        assert res.success is True
        assert dispatched_levels == [70]

    def test_dispatcher_rejects_privileged_action_for_unauthorized_voice(self, voice_gate: VoiceBiometricsGate) -> None:
        """Dispatcher blocks privileged action (e.g. system_power) when voice similarity < 0.70."""
        dispatcher = ActionDispatcher(voice_gate=voice_gate)

        def mock_power(**kwargs):
            return ActionResult(action_name="system_power", success=True)

        dispatcher.register_action("system_power", mock_power)

        guest_ctx = RequesterContext(
            requester_id="user_voice",
            metadata={"voice": True, "speaker_similarity": 0.45},
        )
        res = dispatcher.dispatch_action(
            "system_power",
            payload={"action": "shutdown"},
            requester=guest_ctx,
        )
        assert res.success is False
        assert res.error_code == "UNAUTHORIZED_VOICE"
        assert "Không đủ thẩm quyền âm học" in res.error

    def test_dispatcher_passes_privileged_action_for_master_voice(self, voice_gate: VoiceBiometricsGate) -> None:
        """Dispatcher passes voice gate for master voice (similarity >= 0.70)."""
        dispatcher = ActionDispatcher(voice_gate=voice_gate)

        def mock_exec(**kwargs):
            return ActionResult(action_name="terminal_control", success=True, data={"cmd": "dir"})

        dispatcher.register_action("terminal_control", mock_exec)

        master_ctx = RequesterContext(
            requester_id="user_voice",
            metadata={"voice": True, "speaker_similarity": 0.85},
        )
        res = dispatcher.dispatch_action(
            "terminal_control",
            payload={"command": "dir"},
            requester=master_ctx,
        )
        assert res.success is True
        assert res.data == {"cmd": "dir"}


class TestSafetyInterceptorVoiceGating:
    """Integration tests for SafetyGateInterceptor with VoiceBiometricsGate."""

    def test_safety_interceptor_delegates_to_voice_gate(self, voice_gate: VoiceBiometricsGate) -> None:
        interceptor = SafetyGateInterceptor(voice_gate=voice_gate)
        ok, status, score = interceptor.verify_voice_authority(
            action_name="system_power",
            parameters={"action": "reboot"},
            speaker_similarity=0.35,
        )
        assert ok is False
        assert status == "UNAUTHORIZED_VOICE"
        assert score == 0.35

        ok, status, score = interceptor.verify_voice_authority(
            action_name="weather",
            parameters={},
            speaker_similarity=0.35,
        )
        assert ok is True
        assert status == "SAFE_INTENT_ALLOWED"

    def test_file_read_with_delete_in_path_is_safe(self, voice_gate: VoiceBiometricsGate) -> None:
        """Reading/opening a file whose path contains 'delete' must not be misclassified as privileged."""
        is_auth, status, score = voice_gate.verify_intent_authority(
            action_name="file_management",
            payload={"action": "open", "path": "docs/how_to_delete_cache.txt"},
            speaker_similarity=0.20,
        )
        assert is_auth is True
        assert status == "SAFE_INTENT_ALLOWED"

    def test_file_vietnamese_xoa_is_privileged(self, voice_gate: VoiceBiometricsGate) -> None:
        """Vietnamese deletion action 'xóa' is recognized as privileged and rejected for low similarity."""
        is_auth, status, score = voice_gate.verify_intent_authority(
            action_name="file_management",
            payload={"action": "xóa", "target": "data.db"},
            speaker_similarity=0.30,
        )
        assert is_auth is False
        assert status == "UNAUTHORIZED_VOICE"

    def test_dispatcher_catches_voice_prefix_without_metadata(self, voice_gate: VoiceBiometricsGate) -> None:
        """Requester ID 'voice_client' or 'voice:terminal' is intercepted by voice gate even without metadata."""
        dispatcher = ActionDispatcher(voice_gate=voice_gate)

        def mock_power(**kwargs):
            return ActionResult(action_name="system_power", success=True)

        dispatcher.register_action("system_power", mock_power)

        req_ctx = RequesterContext(requester_id="voice_client", metadata={})
        res = dispatcher.dispatch_action("system_power", payload={"action": "shutdown"}, requester=req_ctx)
        assert res.success is False
        assert res.error_code == "UNAUTHORIZED_VOICE"
