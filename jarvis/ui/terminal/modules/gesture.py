"""
jarvis/ui/terminal/modules/gesture.py
========================================
Gesture Control module adapter.

Preserves a real, audited distinction: the acoustic clap GestureDetector
IS wired to ActionDispatcher.dispatch_action() when a dispatcher is
supplied; HandGestureTracker only emits Python callbacks and has no
ActionDispatcher wiring anywhere in this codebase (confirmed by
inspection of jarvis/gesture/hand_tracker.py). This module never blurs
that distinction into a single "gestures work" status.

No camera loop is ever started from this menu or from [A].
"""
from __future__ import annotations

from jarvis.gesture.detector import GestureDetector
from jarvis.ui.terminal.context import TerminalContext, run_timed
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.theme import StatusLevel

MODULE = "GESTURE"


def _hand_tracker_module():
    import jarvis.gesture.hand_tracker as mod
    return mod


def _camera_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        mod = _hand_tracker_module()
        available = mod.HandGestureTracker().is_backend_available()
        status = StatusLevel.AVAILABLE if available else StatusLevel.OFFLINE
        fields = [("Camera Backend (cv2/mediapipe)", "AVAILABLE" if available else "NOT INSTALLED")]
        return ActionOutcome(status=status, title="Camera Status", fields=fields)
    return run_timed(body)


def _gesture_engine_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            GestureDetector()
            acoustic_ok = True
        except Exception:
            acoustic_ok = False
        mod = _hand_tracker_module()
        hand_ok = mod.HandGestureTracker().is_backend_available()
        fields = [
            ("Acoustic Clap Detector", "AVAILABLE" if acoustic_ok else "ERROR"),
            ("Hand Gesture Tracker", "AVAILABLE" if hand_ok else "LIMITED (cv2/mediapipe missing)"),
        ]
        status = StatusLevel.AVAILABLE if acoustic_ok else StatusLevel.LIMITED
        return ActionOutcome(status=status, title="Gesture Engine Status", fields=fields)
    return run_timed(body)


def _test_recognition(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        return ActionOutcome(
            status=StatusLevel.LIMITED, title="Test Gesture Recognition",
            detail_lines=["Live gesture recognition requires a real camera feed; this terminal "
                          "UI does not open the camera. See 'Camera Status' / 'Gesture Engine "
                          "Status' for backend availability."],
        )
    return run_timed(body)


def _gesture_mapping(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            detector = GestureDetector()
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="Gesture Mapping", error_reason=str(e))
        patterns = getattr(detector, "patterns", None)
        if not patterns:
            return ActionOutcome(status=StatusLevel.LIMITED, title="Gesture Mapping",
                                  detail_lines=["Pattern-to-action mapping is not introspectable "
                                                "from a standalone GestureDetector instance."])
        fields = [(str(k), str(v)) for k, v in list(patterns.items())[:10]]
        return ActionOutcome(status=StatusLevel.PASS, title="Gesture Mapping", fields=fields)
    return run_timed(body)


def _os_action_integration(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        fields = [
            ("Acoustic Clap - Recognition", "AVAILABLE"),
            ("Acoustic Clap - OS Action Wiring", "AVAILABLE (dispatches via ActionDispatcher when running)"),
            ("Hand Gesture - Recognition", "AVAILABLE" if _hand_tracker_module().HandGestureTracker().is_backend_available() else "LIMITED"),
            ("Hand Gesture - OS Action Wiring", "LIMITED (emits callbacks only, not wired to ActionDispatcher)"),
        ]
        return ActionOutcome(status=StatusLevel.PARTIAL, title="OS Action Integration Status", fields=fields)
    return run_timed(body)


def build_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="ges_camera", key="1", label="Camera Status",
                   description="cv2/mediapipe backend availability", handler=lambda: _camera_status(ctx),
                   safe_for_batch=True, help_text="Checks backend availability; never opens the camera."),
        MenuAction(id="ges_engine", key="2", label="Gesture Engine Status",
                   description="Acoustic + hand-gesture engine availability",
                   handler=lambda: _gesture_engine_status(ctx), safe_for_batch=True,
                   help_text="Constructs both engines to confirm they initialize cleanly."),
        MenuAction(id="ges_test", key="3", label="Test Gesture Recognition",
                   description="Live recognition test (requires camera -- not wired here)",
                   handler=lambda: _test_recognition(ctx), safe_for_batch=False,
                   help_text="Always LIMITED in this build -- no camera loop is started."),
        MenuAction(id="ges_mapping", key="4", label="Gesture Mapping",
                   description="Configured pattern-to-action mapping",
                   handler=lambda: _gesture_mapping(ctx), safe_for_batch=True,
                   help_text="Shows the acoustic detector's pattern-to-action table, if available."),
        MenuAction(id="ges_os", key="5", label="OS Action Integration Status",
                   description="Recognition vs real OS-action wiring, per engine",
                   handler=lambda: _os_action_integration(ctx), safe_for_batch=True,
                   help_text="Clarifies that hand gestures are recognized but not wired to real "
                              "OS actions, unlike acoustic claps."),
    ]
    return MenuScreen(
        id="gesture", title="GESTURE CONTROL", breadcrumb=["MAIN", "GESTURE"],
        actions=actions, batch_label="Run All Safe Diagnostics",
        help_intro="No camera loop is ever started from this menu or from [A].",
    )
