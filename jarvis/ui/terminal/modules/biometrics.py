"""
jarvis/ui/terminal/modules/biometrics.py
===========================================
Biometric Security module adapter.

Camera capture is intentionally NOT wired into the terminal UI in this
build -- Enroll Face / Verify Identity report LIMITED truthfully rather
than fabricating a recognition/enrollment result. No raw embeddings are
ever displayed or saved -- only enrolled labels/counts.
"""
from __future__ import annotations

from jarvis.ui.terminal.context import TerminalContext, run_timed
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.theme import StatusLevel

MODULE = "BIOMETRICS"


def _biometrics_module():
    import jarvis.vision.biometrics as mod
    return mod


def _engine(ctx: TerminalContext):
    eng = ctx.state.get("bio_engine")
    if eng is not None:
        return eng
    mod = _biometrics_module()
    eng = mod.BiometricsEngine()
    ctx.state["bio_engine"] = eng
    return eng


def _biometric_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        mod = _biometrics_module()
        cv2_ok = mod.cv2 is not None
        fr_ok = getattr(mod, "face_recognition", None) is not None
        try:
            _engine(ctx)
            storage_ok = True
        except Exception:
            storage_ok = False
        fields = [
            ("cv2", "AVAILABLE" if cv2_ok else "NOT INSTALLED"),
            ("face_recognition", "AVAILABLE" if fr_ok else "NOT INSTALLED"),
            ("Embedding Storage", "AVAILABLE" if storage_ok else "ERROR"),
        ]
        if cv2_ok and fr_ok and storage_ok:
            status = StatusLevel.AVAILABLE
        elif storage_ok:
            status = StatusLevel.LIMITED
        else:
            status = StatusLevel.ERROR
        return ActionOutcome(status=status, title="Biometric Status", fields=fields)
    return run_timed(body)


def _enrolled_profiles(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            engine = _engine(ctx)
            labels = sorted(engine.storage.enrolled_faces.keys())
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="Enrolled Profiles", error_reason=str(e))
        if not labels:
            return ActionOutcome(status=StatusLevel.LIMITED, title="Enrolled Profiles",
                                  detail_lines=["No profiles enrolled."])
        fields = [(f"Profile {i + 1}", label) for i, label in enumerate(labels)]
        return ActionOutcome(status=StatusLevel.PASS, title="Enrolled Profiles", fields=fields,
                              structured_data={"profile_count": len(labels)})
    return run_timed(body)


def _enroll_face(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        return ActionOutcome(
            status=StatusLevel.LIMITED, title="Enroll Face",
            detail_lines=["Camera capture is not wired into the terminal UI in this build. "
                          "No enrollment was performed -- this screen never fabricates success."],
        )
    return run_timed(body)


def _verify_identity(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        return ActionOutcome(
            status=StatusLevel.LIMITED, title="Verify Identity",
            detail_lines=["Camera capture is not wired into the terminal UI in this build. "
                          "No verification was performed -- this screen never fabricates a match."],
        )
    return run_timed(body)


def _surveillance_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            engine = _engine(ctx)
            count = len(engine.storage.enrolled_faces)
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="Surveillance Status", error_reason=str(e))
        fields = [("Surveillance Loop", "NOT RUNNING"), ("Enrolled Profiles", str(count))]
        return ActionOutcome(status=StatusLevel.LIMITED, title="Surveillance Status", fields=fields,
                              detail_lines=["No continuous surveillance loop is started from this menu."])
    return run_timed(body)


def _security_configuration(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            engine = _engine(ctx)
            tolerance = getattr(engine, "tolerance", None)
            bypass = getattr(engine, "bypass_mode", False)
        except Exception as e:
            return ActionOutcome(status=StatusLevel.ERROR, title="Security Configuration", error_reason=str(e))
        fields = [
            ("Match Tolerance", str(tolerance)),
            ("Bypass Mode", "ENABLED (!!)" if bypass else "DISABLED"),
        ]
        status = StatusLevel.LIMITED if bypass else StatusLevel.PASS
        return ActionOutcome(status=status, title="Security Configuration", fields=fields)
    return run_timed(body)


def build_menu(ctx: TerminalContext) -> MenuScreen:
    actions = [
        MenuAction(id="bio_status", key="1", label="Biometric Status",
                   description="cv2 / face_recognition availability", handler=lambda: _biometric_status(ctx),
                   safe_for_batch=True, help_text="Reports optional-dependency availability."),
        MenuAction(id="bio_profiles", key="2", label="Enrolled Profiles",
                   description="List enrolled profile labels (no raw embeddings)",
                   handler=lambda: _enrolled_profiles(ctx), safe_for_batch=True,
                   help_text="Lists enrolled labels only -- never displays raw embedding vectors."),
        MenuAction(id="bio_enroll", key="3", label="Enroll Face",
                   description="Enroll a new face profile (uses the camera)",
                   handler=lambda: _enroll_face(ctx), read_only=False, requires_confirmation=True,
                   side_effect_level="state_change", safe_for_batch=False,
                   help_text="Would use the camera to enroll a face; not wired in this build."),
        MenuAction(id="bio_verify", key="4", label="Verify Identity",
                   description="Verify against enrolled profiles (uses the camera)",
                   handler=lambda: _verify_identity(ctx), requires_confirmation=True, safe_for_batch=False,
                   help_text="Would use the camera to verify identity; not wired in this build."),
        MenuAction(id="bio_surveillance", key="5", label="Surveillance Status",
                   description="Surveillance loop status", handler=lambda: _surveillance_status(ctx),
                   safe_for_batch=True, help_text="Confirms no continuous surveillance loop is active."),
        MenuAction(id="bio_config", key="6", label="Security Configuration",
                   description="Match tolerance / bypass mode", handler=lambda: _security_configuration(ctx),
                   safe_for_batch=True, help_text="Shows current tolerance and bypass-mode configuration."),
    ]
    return MenuScreen(
        id="biometrics", title="BIOMETRIC SECURITY", breadcrumb=["MAIN", "BIOMETRICS"],
        actions=actions, batch_label="Run All Safe Security Checks",
        help_intro="[A] never enrolls or verifies a face -- only status/configuration checks.",
    )
