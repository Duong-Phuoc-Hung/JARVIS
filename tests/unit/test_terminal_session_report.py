"""
tests/unit/test_terminal_session_report.py
=============================================
Redaction, session history, and report-writer tests. No filesystem paths
outside jarvis.core.paths.data_path() (%LOCALAPPDATA%/JARVIS) are ever
touched -- reports write into an isolated temp dir via JARVIS_DATA_DIR.
"""
from __future__ import annotations

import time

import pytest

from jarvis.ui.terminal.models import ActionOutcome, BatchItemResult, BatchResult, MenuAction
from jarvis.ui.terminal.report import ReportWriter
from jarvis.ui.terminal.session import SessionHistory, redact_fields, redact_structured
from jarvis.ui.terminal.theme import StatusLevel


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    yield


# -- Redaction ---------------------------------------------------------------

def test_redact_structured_hides_secret_shaped_keys():
    data = {"bot_token": "123456:AAETrue-secret-value", "note": "hello"}
    redacted = redact_structured(data)
    assert redacted["bot_token"] == "<REDACTED>"
    assert redacted["note"] == "hello"


def test_redact_structured_recurses_into_nested_dicts_and_lists():
    data = {"outer": {"api_key": "sk-abc123"}, "items": [{"password": "hunter2"}]}
    redacted = redact_structured(data)
    assert redacted["outer"]["api_key"] == "<REDACTED>"
    assert redacted["items"][0]["password"] == "<REDACTED>"


def test_redact_structured_scrubs_inline_bearer_tokens_in_text():
    data = {"error": "Request failed: Authorization: Bearer abcdEFGH12345678901234"}
    redacted = redact_structured(data)
    assert "abcdEFGH12345678901234" not in redacted["error"]


def test_redact_fields_hides_secret_field_values():
    fields = [("access_token", "supersecret"), ("Target", "192.168.1.0/24")]
    redacted = redact_fields(fields)
    assert redacted[0] == ("access_token", "<REDACTED>")
    assert redacted[1] == ("Target", "192.168.1.0/24")


def test_no_biometric_embedding_leaks_through_redaction():
    data = {"face_encoding": [0.123, 0.456, 0.789]}
    redacted = redact_structured(data)
    assert redacted["face_encoding"] == "<REDACTED>"


# -- SessionHistory ------------------------------------------------------

def test_session_history_records_and_redacts():
    history = SessionHistory()
    outcome = ActionOutcome(status=StatusLevel.PASS, title="X", duration_s=0.1,
                             structured_data={"api_key": "leak-me"})
    history.record("HARDWARE", "System Snapshot", outcome)
    recs = history.all()
    assert len(recs) == 1
    assert recs[0].structured_data["api_key"] == "<REDACTED>"


def test_session_history_for_module_filters_correctly():
    history = SessionHistory()
    history.record("HARDWARE", "A", ActionOutcome(status=StatusLevel.PASS, title="A"))
    history.record("INFOSEC", "B", ActionOutcome(status=StatusLevel.PASS, title="B"))
    assert len(history.for_module("HARDWARE")) == 1
    assert len(history.for_module("INFOSEC")) == 1
    assert len(history.for_module("MISSING")) == 0


def test_session_history_is_bounded():
    history = SessionHistory()
    history.MAX_RECORDS = 5
    for i in range(10):
        history.record("HARDWARE", f"action_{i}", ActionOutcome(status=StatusLevel.PASS, title=str(i)))
    assert len(history.all()) == 5


# -- ReportWriter ----------------------------------------------------------

def _outcome(status=StatusLevel.PASS, fields=None) -> ActionOutcome:
    return ActionOutcome(status=status, title="System Snapshot", fields=fields or [("CPU", "10 %")],
                          duration_s=0.25, started_at=time.time())


def test_save_single_result_writes_a_verified_file():
    writer = ReportWriter()
    result = writer.save_single_result("HARDWARE", "System Snapshot", _outcome())
    assert result.saved is True
    assert result.path is not None
    assert result.path.exists()
    assert result.path.stat().st_size > 0


def test_saved_report_contains_truthful_fields_and_version():
    from jarvis import __version__
    writer = ReportWriter()
    result = writer.save_single_result("HARDWARE", "System Snapshot", _outcome())
    content = result.path.read_text(encoding="utf-8")
    assert __version__ in content
    assert "System Snapshot" in content
    assert "PASS" in content
    assert "CPU" in content


def test_save_never_overwrites_existing_file():
    writer = ReportWriter()
    r1 = writer.save_single_result("HARDWARE", "System Snapshot", _outcome())
    r2 = writer.save_single_result("HARDWARE", "System Snapshot", _outcome())
    assert r1.path != r2.path
    assert r1.path.exists() and r2.path.exists()


def test_save_generates_a_filesystem_safe_unique_filename():
    writer = ReportWriter()
    result = writer.save_single_result("HARDWARE", "System Snapshot", _outcome())
    assert result.path.name.startswith("jarvis_HARDWARE_result_")
    assert result.path.suffix == ".txt"


def test_save_redacts_secret_fields_before_writing():
    writer = ReportWriter()
    outcome = _outcome(fields=[("bot_token", "leak-me-12345")])
    result = writer.save_single_result("COMMS", "Send Message", outcome)
    content = result.path.read_text(encoding="utf-8")
    assert "leak-me-12345" not in content
    assert "<REDACTED>" in content


def test_save_write_failure_is_reported_truthfully(monkeypatch, tmp_path):
    writer = ReportWriter()

    def _boom(*a, **kw):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr("pathlib.Path.write_text", _boom)
    result = writer.save_single_result("HARDWARE", "System Snapshot", _outcome())
    assert result.saved is False
    assert result.error is not None


def test_save_batch_result_includes_truthful_summary_counts():
    writer = ReportWriter()
    items = [
        BatchItemResult(action=MenuAction(id="a", key="1", label="A"), outcome=_outcome(StatusLevel.PASS)),
        BatchItemResult(action=MenuAction(id="b", key="2", label="B"), outcome=_outcome(StatusLevel.LIMITED)),
        BatchItemResult(action=MenuAction(id="c", key="3", label="C"), outcome=_outcome(StatusLevel.FAILED)),
    ]
    batch = BatchResult(module="HARDWARE", operation="Run All Checks", items=items, duration_s=1.23)
    result = writer.save_batch_result(batch)
    content = result.path.read_text(encoding="utf-8")
    assert "PASS" in content and "LIMITED" in content and "FAILED" in content
    assert "1.23" in content


def test_save_full_session_handles_empty_history_gracefully():
    writer = ReportWriter()
    result = writer.save_full_session([])
    assert result.saved is True
    content = result.path.read_text(encoding="utf-8")
    assert "no records" in content.lower()
