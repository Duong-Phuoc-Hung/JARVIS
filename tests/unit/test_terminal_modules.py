"""
tests/unit/test_terminal_modules.py
======================================
Structural safety + truthfulness tests for the real product-module
adapters (jarvis/ui/terminal/modules/*.py). These call the REAL backend
constructors (all confirmed side-effect-free at construction time), but
never touch real hardware/network/camera/mic, never scan a public target,
never send a real message, and never terminate a process.
"""
from __future__ import annotations

import os

import pytest

from jarvis.core.config import ConfigManager
from jarvis.ui.terminal.console import TerminalConsole
from jarvis.ui.terminal.context import TerminalContext
from jarvis.ui.terminal.modules import (
    biometrics,
    comms,
    data,
    gesture,
    healing,
    infosec,
    smart_home,
)
from jarvis.ui.terminal.report import ReportWriter
from jarvis.ui.terminal.session import SessionHistory
from jarvis.ui.terminal.theme import StatusLevel, TerminalTheme


def _make_ctx(line_source=None) -> TerminalContext:
    theme = TerminalTheme(color_enabled=False)
    console = TerminalConsole(theme=theme, line_source=line_source, out=lambda t: None)
    cfg = ConfigManager()
    cfg.load()
    return TerminalContext(theme=theme, console=console, session=SessionHistory(),
                            report_writer=ReportWriter(), config=cfg, start_jarvis=lambda: False)


# -- InfoSec: scan-scope truthfulness -----------------------------------------

def test_infosec_never_permits_a_public_scan_target():
    ctx = _make_ctx(line_source=lambda: "8.8.8.8")
    screen = infosec.build_menu(ctx)
    validate_action = next(a for a in screen.actions if a.id == "infosec_validate")
    outcome = validate_action.handler()
    assert outcome.status == StatusLevel.BLOCKED
    assert "infosec_target" not in ctx.state


def test_infosec_allows_a_real_rfc1918_target():
    ctx = _make_ctx(line_source=lambda: "192.168.1.0/24")
    screen = infosec.build_menu(ctx)
    validate_action = next(a for a in screen.actions if a.id == "infosec_validate")
    outcome = validate_action.handler()
    assert outcome.status == StatusLevel.PASS
    assert ctx.state["infosec_target"] == "192.168.1.0/24"


def test_infosec_batch_not_visible_with_only_one_eligible_action():
    """Before a target is validated, only 'Security Tools Status' is
    batch-eligible -- [A] requires >= 2, so it must not be offered yet."""
    ctx = _make_ctx()
    screen = infosec.build_menu(ctx)
    assert len(screen.batch_eligible()) == 1
    assert screen.batch_visible() is False


def test_infosec_batch_visible_once_a_target_is_validated():
    ctx = _make_ctx()
    ctx.state["infosec_target"] = "192.168.1.0/24"
    screen = infosec.build_menu(ctx)
    assert len(screen.batch_eligible()) == 2
    assert screen.batch_visible() is True


def test_infosec_lan_scan_is_skipped_without_a_validated_target():
    ctx = _make_ctx()
    screen = infosec.build_menu(ctx)
    scan_action = next(a for a in screen.actions if a.id == "infosec_scan")
    outcome = scan_action.handler()
    assert outcome.status == StatusLevel.SKIPPED


def test_infosec_batch_excludes_scan_when_no_target_selected():
    ctx = _make_ctx()
    screen = infosec.build_menu(ctx)
    eligible_ids = {a.id for a in screen.batch_eligible()}
    assert "infosec_scan" not in eligible_ids


def test_infosec_packet_capture_never_fabricates_evidence():
    """Confirmed truthfulness gap: PacketCapture.capture_packets() invents
    a fixed protocol split even on failure. This module must never call
    it or present its output as real."""
    ctx = _make_ctx()
    screen = infosec.build_menu(ctx)
    capture_action = next(a for a in screen.actions if a.id == "infosec_capture")
    assert capture_action.safe_for_batch is False
    outcome = capture_action.handler()
    assert outcome.status == StatusLevel.LIMITED
    assert "TCP" not in " ".join(outcome.fields[0]) if outcome.fields else True


def test_infosec_security_report_skipped_without_prior_scan():
    ctx = _make_ctx()
    screen = infosec.build_menu(ctx)
    report_action = next(a for a in screen.actions if a.id == "infosec_report")
    outcome = report_action.handler()
    assert outcome.status == StatusLevel.SKIPPED


# -- Smart Home: side-effecting actions excluded from [A] ---------------------

def test_smart_home_control_actions_excluded_from_batch():
    ctx = _make_ctx()
    screen = smart_home.build_menu(ctx)
    eligible_ids = {a.id for a in screen.batch_eligible()}
    for side_effecting in ("sh_on", "sh_off", "sh_toggle", "sh_temp"):
        assert side_effecting not in eligible_ids


def test_smart_home_control_actions_are_unavailable_no_authoritative_path():
    """No ActionDispatcher route and no backend-native safety contract
    exists for Smart Home control anywhere in this codebase -- a
    terminal-side Y/N prompt alone is not authorization, so these actions
    must not execute a real device-control call. They report UNAVAILABLE/
    LIMITED truthfully instead (see smart_home.py's module docstring for
    the full architecture audit that led to this)."""
    ctx = _make_ctx()
    screen = smart_home.build_menu(ctx)
    for aid in ("sh_on", "sh_off", "sh_toggle", "sh_temp"):
        action = next(a for a in screen.actions if a.id == aid)
        assert action.available is False
        outcome = action.handler()
        assert outcome.status == StatusLevel.LIMITED
        assert outcome.status != StatusLevel.PASS


def test_smart_home_control_never_calls_the_real_ha_client():
    """Regression guard for the exact defect this was hardened against:
    ensure no code path in these handlers reaches HomeAssistantClient's
    turn_on/turn_off/toggle/set_temperature methods."""
    ctx = _make_ctx()
    ctx.state["ha_client"] = None  # would raise/misbehave if ever touched without a real client
    screen = smart_home.build_menu(ctx)
    for aid in ("sh_on", "sh_off", "sh_toggle", "sh_temp"):
        action = next(a for a in screen.actions if a.id == aid)
        outcome = action.handler()  # must not raise, must not need ctx.state["ha_client"]
        assert outcome.status == StatusLevel.LIMITED


def test_smart_home_connection_status_offline_when_not_configured():
    ctx = _make_ctx()
    screen = smart_home.build_menu(ctx)
    status_action = next(a for a in screen.actions if a.id == "sh_status")
    outcome = status_action.handler()
    # default_config.yaml ships smart_home.home_assistant.enabled: false
    assert outcome.status == StatusLevel.OFFLINE


# -- Communications: send actions never fabricate delivery, never batch ------

def test_comms_send_actions_excluded_from_top_level_batch():
    ctx = _make_ctx()
    screen = comms.build_menu(ctx)
    eligible_ids = {a.id for a in screen.batch_eligible()}
    assert eligible_ids.issubset({"comms_channel_status", "comms_ratelimit", "comms_whitelist"})


def test_telegram_send_actions_never_fabricate_delivery():
    ctx = _make_ctx()
    screen = comms.build_telegram_menu(ctx)
    for aid in ("tg_send_msg", "tg_send_photo"):
        action = next(a for a in screen.actions if a.id == aid)
        assert action.safe_for_batch is False
        outcome = action.handler()
        assert outcome.status != StatusLevel.PASS  # never claims "sent"


def test_discord_send_actions_never_fabricate_delivery():
    ctx = _make_ctx()
    screen = comms.build_discord_menu(ctx)
    for aid in ("dc_send_msg", "dc_send_embed"):
        action = next(a for a in screen.actions if a.id == aid)
        assert action.safe_for_batch is False
        outcome = action.handler()
        assert outcome.status != StatusLevel.PASS


def test_email_status_is_truthful_about_no_real_imap_connection():
    ctx = _make_ctx()
    screen = comms.build_email_menu(ctx)
    status_action = next(a for a in screen.actions if a.id == "em_status")
    outcome = status_action.handler()
    assert any("IMAP" in line or "imap" in line for line in outcome.detail_lines)


# -- Biometrics: no enrollment/verification via [A], no raw embeddings --------

def test_biometrics_enroll_and_verify_excluded_from_batch():
    ctx = _make_ctx()
    screen = biometrics.build_menu(ctx)
    eligible_ids = {a.id for a in screen.batch_eligible()}
    assert "bio_enroll" not in eligible_ids
    assert "bio_verify" not in eligible_ids


def test_biometrics_enrolled_profiles_never_exposes_raw_embeddings():
    ctx = _make_ctx()
    screen = biometrics.build_menu(ctx)
    action = next(a for a in screen.actions if a.id == "bio_profiles")
    outcome = action.handler()
    # No field value should look like a raw float-vector embedding.
    for _, value in outcome.fields:
        assert not value.strip().startswith("[")


def test_biometrics_enroll_never_fabricates_success_without_camera():
    ctx = _make_ctx()
    screen = biometrics.build_menu(ctx)
    action = next(a for a in screen.actions if a.id == "bio_enroll")
    outcome = action.handler()
    assert outcome.status != StatusLevel.PASS


# -- Gesture: no camera loop from [A], recognition vs OS-wiring distinction ---

def test_gesture_batch_never_starts_a_camera_loop():
    ctx = _make_ctx()
    screen = gesture.build_menu(ctx)
    eligible_ids = {a.id for a in screen.batch_eligible()}
    assert "ges_test" not in eligible_ids  # the only action that could imply live capture


def test_gesture_distinguishes_hand_action_wiring_from_acoustic():
    ctx = _make_ctx()
    screen = gesture.build_menu(ctx)
    action = next(a for a in screen.actions if a.id == "ges_os")
    outcome = action.handler()
    fields = dict(outcome.fields)
    assert "AVAILABLE" in fields["Acoustic Clap - OS Action Wiring"]
    assert "LIMITED" in fields["Hand Gesture - OS Action Wiring"]


# -- Self-Healing: process termination excluded from [A] ----------------------

def test_healing_run_action_excluded_from_batch():
    ctx = _make_ctx()
    screen = healing.build_menu(ctx)
    eligible_ids = {a.id for a in screen.batch_eligible()}
    assert "heal_run" not in eligible_ids


def test_healing_run_action_requires_confirmation():
    ctx = _make_ctx()
    screen = healing.build_menu(ctx)
    action = next(a for a in screen.actions if a.id == "heal_run")
    assert action.requires_confirmation is True
    assert action.side_effect_level == "destructive"


def test_healing_run_action_calls_real_engine_directly_no_private_dispatcher():
    """Architecture guard: 'Run Healing Action' must call HealingEngine
    directly, relying on its own internal protected-process whitelist
    check as the authoritative gate -- NOT a terminal-owned ActionDispatcher
    (removed after audit; see jarvis/ui/terminal/modules/healing.py's
    module docstring). Uses a real HealingEngine and a real protected name
    ("python.exe", in PROTECTED_PROCESS_WHITELIST) so this is safe: the
    protection check runs BEFORE any OS-level process interaction is
    attempted, confirmed by source inspection."""
    ctx = _make_ctx(line_source=None)
    # Feed pid then name via a small queue so both read_line() calls work.
    values = iter([str(os.getpid()), "python.exe"])
    ctx.console._line_source = lambda: next(values)
    screen = healing.build_menu(ctx)
    action = next(a for a in screen.actions if a.id == "heal_run")
    outcome = action.handler()
    assert outcome.status == StatusLevel.FAILED
    assert outcome.error_reason == "PROTECTED_PROCESS"


def test_healing_telemetry_never_fabricates_reclaimed_ram():
    ctx = _make_ctx()
    screen = healing.build_menu(ctx)
    action = next(a for a in screen.actions if a.id == "heal_telemetry")
    outcome = action.handler()
    # No healing action has run this session -- telemetry must say so, not
    # invent a number.
    assert outcome.status == StatusLevel.LIMITED


# -- Data: [A] never guesses a dataset, requires >= 2 eligible ---------------

def test_data_batch_not_visible_before_a_dataset_is_selected():
    """Only 'Visualization' (backend availability, no data needed) is
    eligible before a file is selected -- one action alone must not offer
    [A]."""
    ctx = _make_ctx()
    screen = data.build_menu(ctx)
    assert len(screen.batch_eligible()) == 1
    assert screen.batch_visible() is False


def test_data_batch_visible_once_a_dataset_is_selected(tmp_path):
    ctx = _make_ctx()
    dataset = tmp_path / "sample.csv"
    dataset.write_text("a,b\n1,2\n", encoding="utf-8")
    ctx.state["data_selected_file"] = str(dataset)
    screen = data.build_menu(ctx)
    assert len(screen.batch_eligible()) >= 2
    assert screen.batch_visible() is True
