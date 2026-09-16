"""
tests/unit/test_h08_audio_control_truthfulness.py
====================================================
H-08 contract tests: microphone (toggle_mute) and speaker/system
(system_volume) control truthfulness.

Covers, per the H-08 audit:
  MIC:     JarvisApp._handle_toggle_mute() -> AudioEngine.pause_stream()/
           resume_stream() -- explicit desired-state mute/unmute
           idempotency, bare toggle, tray/headless state synchronization,
           backend unavailable/exception, failed backend never mutates
           visible state. (Confirmed already correct prior to this pass;
           these tests lock in that contract.)
  SPEAKER: JarvisApp._handle_system_volume() -> ComputerController.
           set_volume()/change_volume()/mute_volume() -- exact volume,
           delta, mute/unmute idempotency, backend unavailable/failure,
           failed backend never claims success, clear Vietnamese failure
           wording. (Confirmed BROKEN prior to this pass: `mute` was
           silently discarded by the handler, and ComputerController.
           mute_volume() wrote its cached state before ever confirming a
           real backend result and could fabricate success via a blind
           toggle-hotkey fallback on any pycaw failure -- both fixed.)
  ROUTER:  Vietnamese/English mic vs speaker terminology never cross-
           routes; volume delta aliases keep their correct parameters.

All mocked/faked via the shared tests/conftest.py virtual pycaw endpoint
and AudioEngine's own in-process threading.Event -- this file never
touches real Windows volume or real microphone hardware state.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from jarvis.core.app import JarvisApp
from jarvis.llm.router import IntentResult, LLMIntentRouter


def _make_app() -> JarvisApp:
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    return app


def _router() -> LLMIntentRouter:
    return LLMIntentRouter(llm_client=None, dispatcher=None, fast_path_enabled=True)


class _FakeTray:
    """Minimal tray_controller double exposing only what _handle_toggle_mute() reads/writes."""

    def __init__(self, muted: bool = False) -> None:
        self._is_mic_muted = muted
        self.status_updates: list = []

    def update_status(self, status) -> None:
        self.status_updates.append(status)

    def stop(self) -> None:
        """No-op: satisfies JarvisApp.stop()'s tray_controller.stop() call."""


# ============================================================================
# MIC: toggle_mute -> AudioEngine.pause_stream()/resume_stream()
# ============================================================================


class TestMicDesiredStateTruthfulness(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _make_app()

    def tearDown(self) -> None:
        self.app.stop()

    def test_1_explicit_mute_from_unmuted(self) -> None:
        self.app._mic_muted = False
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertTrue(result.success)
        self.assertTrue(result.data["muted"])
        self.assertTrue(self.app._mic_muted)

    def test_2_explicit_mute_when_already_muted_is_idempotent(self) -> None:
        self.app._mic_muted = True
        r1 = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertTrue(r1.success)
        self.assertTrue(r1.data["muted"])
        r2 = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertTrue(r2.success)
        self.assertTrue(r2.data["muted"])
        self.assertTrue(self.app._mic_muted, "repeating mute=True must not accidentally resume")

    def test_3_explicit_unmute_from_muted(self) -> None:
        self.app._mic_muted = True
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": False})
        self.assertTrue(result.success)
        self.assertFalse(result.data["muted"])
        self.assertFalse(self.app._mic_muted)

    def test_4_explicit_unmute_when_already_unmuted_is_idempotent(self) -> None:
        self.app._mic_muted = False
        r1 = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": False})
        self.assertTrue(r1.success)
        self.assertFalse(r1.data["muted"])
        r2 = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": False})
        self.assertTrue(r2.success)
        self.assertFalse(r2.data["muted"])
        self.assertFalse(self.app._mic_muted, "repeating mute=False must not accidentally pause")

    def test_5_toggle_twice_returns_to_original_state(self) -> None:
        self.app._mic_muted = False
        r1 = self.app.dispatcher.dispatch_action("toggle_mute", payload={})
        self.assertTrue(r1.success)
        self.assertTrue(r1.data["muted"])
        r2 = self.app.dispatcher.dispatch_action("toggle_mute", payload={})
        self.assertTrue(r2.success)
        self.assertFalse(r2.data["muted"])
        self.assertFalse(self.app._mic_muted)

    def test_6_tray_state_synchronization(self) -> None:
        tray = _FakeTray(muted=False)
        self.app.tray_controller = tray
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertTrue(result.success)
        self.assertEqual(tray._is_mic_muted, result.data["muted"])
        self.assertTrue(tray._is_mic_muted)

        result2 = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": False})
        self.assertEqual(tray._is_mic_muted, result2.data["muted"])
        self.assertFalse(tray._is_mic_muted)

    def test_7_headless_state_synchronization(self) -> None:
        self.app.tray_controller = None
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertTrue(result.success)
        self.assertEqual(self.app._mic_muted, result.data["muted"])
        self.assertTrue(self.app._mic_muted)

        result2 = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": False})
        self.assertEqual(self.app._mic_muted, result2.data["muted"])
        self.assertFalse(self.app._mic_muted)

    def test_8_audio_engine_unavailable(self) -> None:
        self.app.audio_engine = None
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "AUDIO_ENGINE_UNAVAILABLE")

    def test_9_pause_stream_exception(self) -> None:
        self.app._mic_muted = False
        self.app.audio_engine.pause_stream = MagicMock(side_effect=RuntimeError("no audio device"))
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "AUDIO_ENGINE_EXCEPTION")

    def test_10_resume_stream_exception(self) -> None:
        self.app._mic_muted = True
        self.app.audio_engine.resume_stream = MagicMock(side_effect=RuntimeError("no audio device"))
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": False})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "AUDIO_ENGINE_EXCEPTION")

    def test_11_failed_backend_does_not_mutate_visible_state(self) -> None:
        self.app.tray_controller = None
        self.app._mic_muted = False
        self.app.audio_engine.pause_stream = MagicMock(side_effect=RuntimeError("boom"))
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertFalse(result.success)
        self.assertFalse(
            self.app._mic_muted,
            "a failed pause_stream() call must not leave _mic_muted flipped to True",
        )


# ============================================================================
# SPEAKER: system_volume -> ComputerController.set_volume()/change_volume()/
# mute_volume() -> real pycaw speaker endpoint
# ============================================================================


class TestSpeakerVolumeTruthfulness(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _make_app()

    def tearDown(self) -> None:
        self.app.stop()

    def test_12_exact_volume_success(self) -> None:
        result = self.app.dispatcher.dispatch_action("system_volume", payload={"level": 42})
        self.assertTrue(result.success)
        self.assertEqual(result.data["volume"], 42)

    def test_13_delta_success(self) -> None:
        self.app.dispatcher.dispatch_action("system_volume", payload={"level": 50})
        result = self.app.dispatcher.dispatch_action("system_volume", payload={"delta": 10})
        self.assertTrue(result.success)
        self.assertEqual(result.data["volume"], 60)

    def test_14_speaker_mute_success(self) -> None:
        result = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": True})
        self.assertTrue(result.success)
        self.assertTrue(result.data["muted"])
        self.assertTrue(self.app.computer_controller.is_muted())

    def test_15_repeated_speaker_mute_idempotent(self) -> None:
        r1 = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": True})
        r2 = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": True})
        self.assertTrue(r1.success and r2.success)
        self.assertTrue(r1.data["muted"])
        self.assertTrue(r2.data["muted"], "repeating mute=True must not accidentally unmute")
        self.assertTrue(self.app.computer_controller.is_muted())

    def test_16_speaker_unmute_success(self) -> None:
        self.app.dispatcher.dispatch_action("system_volume", payload={"mute": True})
        result = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": False})
        self.assertTrue(result.success)
        self.assertFalse(result.data["muted"])
        self.assertFalse(self.app.computer_controller.is_muted())

    def test_17_repeated_speaker_unmute_idempotent(self) -> None:
        self.app.dispatcher.dispatch_action("system_volume", payload={"mute": True})
        r1 = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": False})
        r2 = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": False})
        self.assertFalse(r1.data["muted"])
        self.assertFalse(r2.data["muted"], "repeating mute=False must not accidentally re-mute")
        self.assertFalse(self.app.computer_controller.is_muted())

    def test_18_computer_controller_unavailable(self) -> None:
        """
        H-08 review fix: computer_controller unavailable must produce a
        clear Vietnamese "error" (what process_text_command() actually
        speaks) and a stable "error_code" -- not just a bare success=False
        with no actionable/human-readable reason.
        """
        self.app.computer_controller = None
        result = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": True})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "COMPUTER_CONTROLLER_UNAVAILABLE")
        self.assertIn("Không thể", result.error)

    def test_19_failed_backend_does_not_claim_success(self) -> None:
        """pycaw endpoint reachable but SetMute()/GetMute() genuinely fails
        (mute_volume() returns None) -- must never fabricate a muted value
        or report success merely because a cached _is_muted might exist."""
        self.app.computer_controller.mute_volume = MagicMock(return_value=None)
        result = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": True})
        self.assertFalse(result.success)
        self.assertIsNone(result.data.get("muted"))

    def test_20_correct_vietnamese_failure_message_and_error_code(self) -> None:
        self.app.computer_controller.mute_volume = MagicMock(return_value=None)

        mute_result = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": True})
        self.assertEqual(mute_result.error_code, "VOLUME_MUTE_FAILED")
        self.assertIn("Không thể", mute_result.error)
        self.assertIn("tắt tiếng", mute_result.error)

        unmute_result = self.app.dispatcher.dispatch_action("system_volume", payload={"mute": False})
        self.assertEqual(unmute_result.error_code, "VOLUME_MUTE_FAILED")
        self.assertIn("Không thể", unmute_result.error)
        self.assertIn("bật tiếng", unmute_result.error)

    def test_21_exact_level_failure_uses_vietnamese_error_not_machine_code(self) -> None:
        """H-08 review fix: "error" must hold clear Vietnamese text, not
        the raw "VOLUME_SET_FAILED"-style constant -- that belongs only
        in "error_code"."""
        self.app.computer_controller.set_volume = MagicMock(return_value=None)
        result = self.app.dispatcher.dispatch_action("system_volume", payload={"level": 80})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "VOLUME_SET_FAILED")
        self.assertNotEqual(result.error, "VOLUME_SET_FAILED")
        self.assertIn("Không thể", result.error)

    def test_22_delta_failure_uses_vietnamese_error_not_machine_code(self) -> None:
        self.app.computer_controller.change_volume = MagicMock(return_value=None)
        result = self.app.dispatcher.dispatch_action("system_volume", payload={"delta": 10})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "VOLUME_CHANGE_FAILED")
        self.assertNotEqual(result.error, "VOLUME_CHANGE_FAILED")
        self.assertIn("Không thể", result.error)

    def test_23_process_text_command_speaks_vietnamese_not_machine_code_on_volume_failure(self) -> None:
        """
        End-to-end proof: the actual text process_text_command() returns
        (what TTS speaks / what the caller sees) for a volume failure must
        be the clear Vietnamese message, never a raw VOLUME_*_FAILED /
        COMPUTER_CONTROLLER_UNAVAILABLE machine code -- this is exactly
        what ActionDispatcher._normalize_handler_outcome()'s "error"-first
        precedence surfaces, and is why "error" must hold Vietnamese text.
        """
        self.app.llm_router.parse_intent = lambda text: IntentResult(
            action_name="system_volume", parameters={"level": 80}, response_text=None,
        )
        self.app.computer_controller.set_volume = MagicMock(return_value=None)

        result = self.app.process_text_command("chỉnh âm lượng lên mức 80", requester="user")
        self.assertFalse(result["success"])
        self.assertNotIn("VOLUME_SET_FAILED", result["response_text"])
        self.assertNotIn("COMPUTER_CONTROLLER_UNAVAILABLE", result["response_text"])
        self.assertIn("Không thể", result["response_text"])

    def test_24_process_text_command_speaks_vietnamese_when_controller_unavailable(self) -> None:
        self.app.llm_router.parse_intent = lambda text: IntentResult(
            action_name="system_volume", parameters={"mute": True}, response_text=None,
        )
        self.app.computer_controller = None

        result = self.app.process_text_command("tắt tiếng", requester="user")
        self.assertFalse(result["success"])
        self.assertNotIn("COMPUTER_CONTROLLER_UNAVAILABLE", result["response_text"])
        self.assertIn("Không thể", result["response_text"])


# ============================================================================
# ROUTER: mic vs speaker terminology separation
# ============================================================================


class TestH08RouterSeparation(unittest.TestCase):
    def setUp(self) -> None:
        self.router = _router()

    def test_25_mic_aliases_route_only_to_toggle_mute_with_correct_desired_state(self) -> None:
        cases = [
            ("tắt mic", "toggle_mute", True),
            ("tat mic", "toggle_mute", True),
            ("bật mic", "toggle_mute", False),
            ("bat mic", "toggle_mute", False),
            ("mute mic", "toggle_mute", True),
            ("unmute mic", "toggle_mute", False),
        ]
        for text, expected_action, expected_muted in cases:
            with self.subTest(text=text):
                r = self.router.parse_intent(text)
                self.assertEqual(r.action_name, expected_action)
                self.assertEqual(r.parameters.get("muted"), expected_muted)

    def test_26_speaker_mute_aliases_route_only_to_system_volume(self) -> None:
        cases = [
            ("tắt tiếng", "system_volume", True),
            ("tat tieng", "system_volume", True),
            ("mute", "system_volume", True),
            ("bật tiếng", "system_volume", False),
            ("bat tieng", "system_volume", False),
            ("unmute", "system_volume", False),
        ]
        for text, expected_action, expected_mute in cases:
            with self.subTest(text=text):
                r = self.router.parse_intent(text)
                self.assertEqual(r.action_name, expected_action)
                self.assertEqual(r.parameters.get("mute"), expected_mute)

    def test_27_mic_and_speaker_terminology_does_not_cross_route(self) -> None:
        mic_texts = ["tắt mic", "bật mic", "mute mic", "unmute mic", "toggle mic", "bật tắt mic"]
        for text in mic_texts:
            with self.subTest(text=text):
                r = self.router.parse_intent(text)
                self.assertEqual(r.action_name, "toggle_mute")
                self.assertNotIn("mute", r.parameters, "mic route must never carry the speaker 'mute' key")

        speaker_texts = ["tắt tiếng", "bật tiếng", "mute", "unmute"]
        for text in speaker_texts:
            with self.subTest(text=text):
                r = self.router.parse_intent(text)
                self.assertEqual(r.action_name, "system_volume")
                self.assertNotIn("muted", r.parameters, "speaker route must never carry the mic 'muted' key")

    def test_28_volume_delta_aliases_preserve_correct_parameters(self) -> None:
        cases = [
            ("tăng âm lượng", {"delta": 10}),
            ("giảm âm lượng", {"delta": -10}),
            ("volume up", {"delta": 10}),
            ("volume down", {"delta": -10}),
        ]
        for text, expected_params in cases:
            with self.subTest(text=text):
                r = self.router.parse_intent(text)
                self.assertEqual(r.action_name, "system_volume")
                for key, value in expected_params.items():
                    self.assertEqual(r.parameters.get(key), value)

    def test_29_mute_phrases_do_not_misclassify_as_increase(self) -> None:
        """
        H-08 review fix: "tắt hết âm thanh"/"tắt hết tiếng" previously
        misclassified as an INCREASE, because the token "hết" (also used
        in "hết cỡ" = max out volume) was checked before MUTE. "tắt"
        (mute) must always win regardless of what follows it.
        """
        cases = [
            ("tắt hết âm thanh", {"mute": True}),
            ("tắt hết tiếng", {"mute": True}),
            ("tắt hẳn tiếng", {"mute": True}),
            ("bật lại tiếng", {"mute": False}),
        ]
        for text, expected_params in cases:
            with self.subTest(text=text):
                r = self.router.parse_intent(text)
                self.assertEqual(r.action_name, "system_volume")
                self.assertEqual(r.parameters, expected_params)

    def test_30_het_co_still_correctly_means_increase(self) -> None:
        """Regression guard: fixing the "tắt hết" collision above must not
        break the genuine "hết cỡ" (max out) increase case."""
        r = self.router.parse_intent("loa hết cỡ")
        self.assertEqual(r.action_name, "system_volume")
        self.assertEqual(r.parameters.get("delta"), 10)
        self.assertNotIn("mute", r.parameters)

    def test_31_explicit_numeric_deltas_are_preserved_not_collapsed(self) -> None:
        cases = [
            ("tăng âm lượng lên 20", {"delta": 20}),
            ("giảm âm lượng xuống 20", {"delta": -20}),
        ]
        for text, expected_params in cases:
            with self.subTest(text=text):
                r = self.router.parse_intent(text)
                self.assertEqual(r.action_name, "system_volume")
                self.assertEqual(r.parameters, expected_params)

    def test_32_exact_level_phrases_produce_level_not_delta(self) -> None:
        cases = [
            ("chỉnh âm lượng lên mức 50", 50),
            ("chỉnh âm thanh mức 30", 30),
        ]
        for text, expected_level in cases:
            with self.subTest(text=text):
                r = self.router.parse_intent(text)
                self.assertEqual(r.action_name, "system_volume")
                self.assertEqual(r.parameters.get("level"), expected_level)
                self.assertNotIn("delta", r.parameters)
                self.assertNotIn("mute", r.parameters)

    def test_33_ambiguous_volume_phrase_stays_under_system_volume_with_clarify(self) -> None:
        """
        H-08 final contract correction: a bare "adjust the volume" request
        with no direction/level/mute verb is genuinely ambiguous, but MUST
        stay under the established system_volume P0 routing contract
        (tests/unit/test_router_p0.py, tests/eval/routing_eval_n150.py) --
        never reclassified to unknown_intent. The explicit
        {"clarify": True} parameter is what signals "ask, don't execute"
        to _handle_system_volume(), not a different action_name.
        """
        cases = ["điều chỉnh âm lượng", "dieu chinh am luong", "vặn loa"]
        for text in cases:
            with self.subTest(text=text):
                r = self.router.parse_intent(text)
                self.assertEqual(r.action_name, "system_volume")
                self.assertEqual(r.parameters, {"clarify": True})
                self.assertIsNotNone(r.response_text)
                self.assertNotIn("Đang điều chỉnh âm lượng", r.response_text)
                # Must genuinely ask for clarification, offering all four
                # real options, not a generic "I don't understand".
                for expected_word in ("tăng", "giảm", "tắt tiếng", "bật tiếng"):
                    self.assertIn(expected_word, r.response_text)


class TestAmbiguousVolumeClarification(unittest.TestCase):
    """
    End-to-end proof that an ambiguous volume phrase produces a genuine,
    successful clarification response with ZERO hardware side effects --
    routed through the REAL router (jarvis/llm/router.py), the REAL
    dispatcher, and the REAL _handle_system_volume(clarify=True) branch.
    Only the ComputerController backend methods are mocked.
    """

    def setUp(self) -> None:
        self.app = _make_app()

    def tearDown(self) -> None:
        self.app.stop()

    def test_34_ambiguous_volume_command_never_touches_computer_controller(self) -> None:
        self.app.computer_controller.set_volume = MagicMock()
        self.app.computer_controller.change_volume = MagicMock()
        self.app.computer_controller.mute_volume = MagicMock()

        # Real router path -- no monkeypatching of parse_intent().
        result = self.app.process_text_command("điều chỉnh âm lượng", requester="user")

        self.assertTrue(result["success"])  # an honest clarification, not a failure
        self.assertEqual(result["intent"]["action_name"], "system_volume")
        self.assertTrue(result["result"]["data"]["clarification_required"])
        self.assertIn("Xin nói rõ hơn", result["response_text"])
        self.assertNotIn("Đã điều chỉnh", result["response_text"])
        self.assertNotIn("Đang điều chỉnh âm lượng", result["response_text"])
        self.app.computer_controller.set_volume.assert_not_called()
        self.app.computer_controller.change_volume.assert_not_called()
        self.app.computer_controller.mute_volume.assert_not_called()

    def test_35_ambiguous_volume_command_via_no_diacritic_phrasing(self) -> None:
        """Same proof for the no-diacritic phrasing, via the real router."""
        self.app.computer_controller.set_volume = MagicMock()
        self.app.computer_controller.change_volume = MagicMock()
        self.app.computer_controller.mute_volume = MagicMock()

        result = self.app.process_text_command("dieu chinh am luong", requester="user")

        self.assertTrue(result["success"])
        self.assertEqual(result["intent"]["action_name"], "system_volume")
        self.assertNotIn("Đã điều chỉnh", result["response_text"])
        self.app.computer_controller.set_volume.assert_not_called()
        self.app.computer_controller.change_volume.assert_not_called()
        self.app.computer_controller.mute_volume.assert_not_called()

    def test_36_handler_clarify_branch_runs_before_computer_controller_check(self) -> None:
        """
        Direct unit proof of the handler contract: clarify=True must
        short-circuit BEFORE the `if not self.computer_controller` check
        and before any backend call -- so it works even with no
        computer_controller at all, which a real fabricated-hardware
        failure could never do.
        """
        self.app.computer_controller = None
        result = self.app._handle_system_volume(clarify=True)
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["success"])
        self.assertTrue(result["clarification_required"])
        self.assertIn("Xin nói rõ hơn", result["message"])


if __name__ == "__main__":
    unittest.main()
