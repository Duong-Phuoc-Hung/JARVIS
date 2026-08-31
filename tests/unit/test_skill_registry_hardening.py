"""
tests/unit/test_skill_registry_hardening.py
==============================================
Regression tests for the skill manifest/telemetry hardening sprint:

  - SkillMetadata.to_dict()/from_dict() round-trip fidelity (category/author)
  - deterministic manifest validation (jarvis.skills.validation)
  - runtime telemetry separated from packaged metadata.json
    (jarvis.skills.telemetry.SkillTelemetryStore)
  - deterministic discovery ordering / duplicate-name resolution

All tests use temporary directories for skills_dir and telemetry storage;
the one test that discovers the real packaged jarvis/skills/ tree still
uses an isolated temporary telemetry store, and explicitly asserts that no
tracked metadata.json file is touched.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.skills.models import SkillDefinition, SkillMetadata
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.telemetry import SkillTelemetryStore
from jarvis.skills.validation import is_safe_skill_identifier

EXECUTE_OK = "def execute(**kw):\n    return {'output': 'ok'}\n"


def _write_skill(skills_dir: Path, dir_name: str, declared_name: str | None = None, code: str = EXECUTE_OK) -> Path:
    """Create a minimal on-disk skill directory with __init__.py and metadata.json."""
    skill_dir = skills_dir / dir_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "__init__.py").write_text(code, encoding="utf-8")
    meta = {"name": declared_name if declared_name is not None else dir_name}
    (skill_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return skill_dir


@pytest.fixture
def telemetry_store(tmp_path) -> SkillTelemetryStore:
    return SkillTelemetryStore(tmp_path / "telemetry.json")


# --- 1. Metadata round-trip fidelity ---------------------------------------

def test_metadata_round_trip_preserves_category_and_author():
    original = SkillMetadata(
        name="demo_skill",
        version="2.1.0",
        description="A demo skill",
        category="finance",
        author="Alice",
        tags=["a", "b"],
        synthesized_by="tester",
        parameters_schema={"type": "object", "properties": {}},
        return_schema={"type": "object"},
    )

    round_tripped = SkillMetadata.from_dict(json.loads(json.dumps(original.to_dict())))

    assert round_tripped.name == "demo_skill"
    assert round_tripped.version == "2.1.0"
    assert round_tripped.description == "A demo skill"
    assert round_tripped.category == "finance"
    assert round_tripped.author == "Alice"
    assert round_tripped.tags == ["a", "b"]
    assert round_tripped.synthesized_by == "tester"
    assert round_tripped.parameters_schema == {"type": "object", "properties": {}}
    assert round_tripped.return_schema == {"type": "object"}
    assert round_tripped.created_at == original.created_at


def test_to_manifest_dict_excludes_telemetry_but_keeps_identity_fields():
    metadata = SkillMetadata(name="demo", category="finance", author="Alice")
    metadata.record_invocation(success=True, latency_ms=5.0)

    full = metadata.to_dict()
    manifest = metadata.to_manifest_dict()

    for telemetry_key in (
        "invocation_count", "success_count", "failure_count",
        "total_latency_ms", "success_rate", "avg_latency_ms",
    ):
        assert telemetry_key in full  # to_dict() unchanged, still includes telemetry
        assert telemetry_key not in manifest  # to_manifest_dict() excludes it

    assert manifest["name"] == "demo"
    assert manifest["category"] == "finance"
    assert manifest["author"] == "Alice"


# --- 2. Legacy metadata missing optional fields -----------------------------

def test_legacy_metadata_missing_fields_loads_with_safe_defaults():
    legacy = {"name": "old_skill", "version": "1.0.0", "description": "old"}
    restored = SkillMetadata.from_dict(legacy)

    assert restored.name == "old_skill"
    assert restored.category == "general"
    assert restored.author == "jarvis_agentic_synthesizer"
    assert restored.tags == []
    assert restored.parameters_schema == {}
    assert restored.return_schema is None
    assert restored.invocation_count == 0


# --- 3. Invalid metadata types rejected deterministically -------------------

def test_invalid_metadata_types_fall_back_to_safe_defaults():
    bad = {
        "name": 12345,
        "tags": "not-a-list",
        "parameters_schema": "not-a-dict",
        "return_schema": "not-a-dict-either",
        "invocation_count": "not-an-int",
        "total_latency_ms": "not-a-float",
        "category": 999,
        "author": None,
    }
    restored = SkillMetadata.from_dict(bad)

    assert restored.name == "unnamed_skill"
    assert restored.tags == []
    assert restored.parameters_schema == {}
    assert restored.return_schema is None
    assert restored.invocation_count == 0
    assert restored.total_latency_ms == 0.0
    assert restored.category == "general"
    assert restored.author == "jarvis_agentic_synthesizer"


def test_from_dict_handles_non_dict_input_gracefully():
    restored = SkillMetadata.from_dict(None)  # type: ignore[arg-type]
    assert restored.name == "unnamed_skill"


# --- 4. Invalid/unsafe skill identifier rejected ----------------------------

def test_is_safe_skill_identifier_rejects_path_traversal_and_separators():
    assert is_safe_skill_identifier("normal_skill") is True
    assert is_safe_skill_identifier("../evil") is False
    assert is_safe_skill_identifier("a/b") is False
    assert is_safe_skill_identifier("a\\b") is False
    assert is_safe_skill_identifier("") is False
    assert is_safe_skill_identifier(None) is False
    assert is_safe_skill_identifier("x" * 200) is False


def test_registry_overrides_unsafe_declared_name_with_directory_name(tmp_path, telemetry_store):
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "safe_dir_name", declared_name="../../evil")

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    discovered = registry.discover_skills()

    assert "../../evil" not in discovered
    assert "safe_dir_name" in discovered
    assert discovered["safe_dir_name"].metadata.name == "safe_dir_name"


def test_register_skill_writes_manifest_without_telemetry_fields(tmp_path, telemetry_store):
    """
    register_skill(save_to_disk=True) writes a NEW packaged metadata.json.
    That file must describe the static manifest only -- it must not bake in
    runtime telemetry fields, even though SkillMetadata.to_dict() (used
    elsewhere for API/introspection responses) still includes them.
    """
    skills_dir = tmp_path / "skills"
    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)

    skill_def = SkillDefinition(
        metadata=SkillMetadata(name="fresh_skill", description="brand new"),
        entrypoint_code=EXECUTE_OK,
    )
    assert registry.register_skill(skill_def) is True

    written = json.loads((skills_dir / "fresh_skill" / "metadata.json").read_text(encoding="utf-8"))
    for telemetry_key in (
        "invocation_count", "success_count", "failure_count",
        "total_latency_ms", "success_rate", "avg_latency_ms",
    ):
        assert telemetry_key not in written
    assert written["name"] == "fresh_skill"
    assert written["description"] == "brand new"


def test_register_skill_rejects_unsafe_identifier(tmp_path, telemetry_store):
    registry = SkillRegistry(skills_dir=tmp_path / "skills", auto_discover=False, telemetry_store=telemetry_store)
    bad_def = SkillDefinition(metadata=SkillMetadata(name="../evil"), entrypoint_code=EXECUTE_OK)
    assert registry.register_skill(bad_def) is False


def test_wrong_typed_declared_name_falls_back_to_directory_name_not_generic_placeholder(tmp_path, telemetry_store):
    """
    A declared "name" of the wrong TYPE (not just an unsafe string) must
    still resolve to THIS skill's own safe directory name -- never to the
    fixed generic placeholder SkillMetadata.from_dict() uses when called
    standalone ("unnamed_skill"), which would let two different
    wrong-typed-name skills collide under one shared, incorrect identity.
    """
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "real_calculator"
    skill_dir.mkdir(parents=True)
    (skill_dir / "__init__.py").write_text(EXECUTE_OK, encoding="utf-8")
    (skill_dir / "metadata.json").write_text(json.dumps({"name": 12345, "version": "1.0.0"}), encoding="utf-8")

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    discovered = registry.discover_skills()

    assert "unnamed_skill" not in discovered
    assert "real_calculator" in discovered
    assert discovered["real_calculator"].metadata.name == "real_calculator"


def test_two_wrong_typed_names_do_not_collide_under_shared_placeholder(tmp_path, telemetry_store):
    """Two independent skills with equally-wrong-typed declared names must
    resolve to their own distinct directory-derived identities, not merge
    into one shared "unnamed_skill" entry."""
    skills_dir = tmp_path / "skills"
    for dir_name in ["skill_one", "skill_two"]:
        d = skills_dir / dir_name
        d.mkdir(parents=True)
        (d / "__init__.py").write_text(EXECUTE_OK, encoding="utf-8")
        (d / "metadata.json").write_text(json.dumps({"name": None}), encoding="utf-8")

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    discovered = registry.discover_skills()

    assert "unnamed_skill" not in discovered
    assert "skill_one" in discovered
    assert "skill_two" in discovered


# --- 5. Malformed metadata JSON does not crash discovery --------------------

def test_malformed_json_does_not_crash_discovery(tmp_path, telemetry_store):
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "good_skill")

    bad_dir = skills_dir / "bad_skill"
    bad_dir.mkdir(parents=True)
    (bad_dir / "__init__.py").write_text(EXECUTE_OK, encoding="utf-8")
    (bad_dir / "metadata.json").write_text("{ this is not valid json !!!", encoding="utf-8")

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    discovered = registry.discover_skills()

    assert "good_skill" in discovered
    assert "bad_skill" in discovered
    assert discovered["bad_skill"].metadata.name == "bad_skill"


# --- 6/7. Duplicate names and discovery order determinism -------------------

def test_duplicate_declared_names_resolve_deterministically(tmp_path, telemetry_store):
    skills_dir = tmp_path / "skills"
    # Created out of alphabetical order to prove sorted-name resolution, not
    # filesystem creation order, decides the winner.
    _write_skill(skills_dir, "zzz_dir", declared_name="shared_name")
    _write_skill(skills_dir, "aaa_dir", declared_name="shared_name")

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    discovered = registry.discover_skills()

    assert "shared_name" in discovered
    assert "aaa_dir" in discovered["shared_name"].file_path


def test_discovery_order_is_deterministic_across_repeated_calls(tmp_path, telemetry_store):
    skills_dir = tmp_path / "skills"
    for name in ["charlie", "alpha", "bravo"]:
        _write_skill(skills_dir, name)

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    first = list(registry.discover_skills().keys())
    second = list(registry.discover_skills().keys())

    assert first == second == ["alpha", "bravo", "charlie"]


def test_directory_wins_over_identically_named_standalone_file(tmp_path, telemetry_store):
    """A packaged directory skill and a standalone .py file sharing the same
    name must resolve deterministically to the directory (pre-existing
    behavior, verified rather than assumed)."""
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "shared_stem")
    (skills_dir / "shared_stem.py").write_text(
        "def execute(**kw):\n    return {'output': 'from standalone file'}\n", encoding="utf-8"
    )

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    discovered = registry.discover_skills()

    assert "shared_stem" in discovered
    assert discovered["shared_stem"].file_path.endswith("__init__.py")


# --- 8/9. Telemetry updates on success/failure ------------------------------

def test_successful_invocation_updates_runtime_telemetry(tmp_path, telemetry_store):
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "ok_skill")

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    registry.discover_skills()

    result = registry.invoke_skill("ok_skill")
    assert result.success is True

    metrics = registry.get_metrics("ok_skill")
    assert metrics["invocations"] == 1
    assert metrics["success_count"] == 1
    assert metrics["failure_count"] == 0

    stored = telemetry_store.get("ok_skill")
    assert stored["invocation_count"] == 1
    assert stored["success_count"] == 1


def test_failed_invocation_updates_failure_telemetry(tmp_path, telemetry_store):
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "fail_skill", code="def execute(**kw):\n    raise ValueError('boom')\n")

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    registry.discover_skills()

    result = registry.invoke_skill("fail_skill")
    assert result.success is False

    metrics = registry.get_metrics("fail_skill")
    assert metrics["invocations"] == 1
    assert metrics["failure_count"] == 1
    assert metrics["success_count"] == 0

    stored = telemetry_store.get("fail_skill")
    assert stored["failure_count"] == 1


# --- 10. Invocation never modifies packaged metadata.json -------------------

def test_invocation_does_not_modify_packaged_metadata_json(tmp_path, telemetry_store):
    skills_dir = tmp_path / "skills"
    skill_dir = _write_skill(skills_dir, "tracked_like_skill")
    meta_path = skill_dir / "metadata.json"
    before_content = meta_path.read_text(encoding="utf-8")
    before_mtime = meta_path.stat().st_mtime

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    registry.discover_skills()
    for _ in range(5):
        registry.invoke_skill("tracked_like_skill")

    assert meta_path.read_text(encoding="utf-8") == before_content
    assert meta_path.stat().st_mtime == before_mtime


# --- 11. Telemetry survives a new registry instance with the same store ----

def test_telemetry_survives_new_registry_instance_with_same_store(tmp_path, telemetry_store):
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "persistent_skill")

    reg1 = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    reg1.discover_skills()
    reg1.invoke_skill("persistent_skill")
    reg1.invoke_skill("persistent_skill")

    reg2 = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    reg2.discover_skills()

    metrics = reg2.get_metrics("persistent_skill")
    assert metrics["invocations"] == 2


# --- 12. Corrupt telemetry file recovers gracefully -------------------------

def test_corrupt_telemetry_file_recovers_gracefully(tmp_path):
    store_path = tmp_path / "telemetry.json"
    store_path.write_text("{ not valid json at all ][", encoding="utf-8")

    store = SkillTelemetryStore(store_path)
    assert store.load_all() == {}
    assert store.get("anything") is None

    result = store.record_invocation("some_skill", success=True, latency_ms=5.0)
    assert result["invocation_count"] == 1
    assert store.get("some_skill")["invocation_count"] == 1


# --- 13. Concurrent telemetry updates do not lose counts --------------------

def test_concurrent_telemetry_updates_do_not_lose_counts(tmp_path):
    store = SkillTelemetryStore(tmp_path / "telemetry.json")
    n_threads = 20

    def worker():
        store.record_invocation("concurrent_skill", success=True, latency_ms=1.0)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = store.get("concurrent_skill")
    assert final["invocation_count"] == n_threads
    assert final["success_count"] == n_threads


def test_concurrent_invoke_skill_preserves_success_failure_invariant(tmp_path, telemetry_store):
    """
    End-to-end (not just the isolated store): concurrent invoke_skill()
    calls for the SAME skill, a mix of successes and failures, must never
    lose an update in either the in-memory SkillMetadata (get_metrics()) or
    the on-disk telemetry store -- invocation_count must always equal
    success_count + failure_count in both views.
    """
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir,
        "flaky_skill",
        code=(
            "def execute(should_fail=False, **kw):\n"
            "    if should_fail:\n"
            "        raise ValueError('simulated failure')\n"
            "    return {'output': 'ok'}\n"
        ),
    )

    registry = SkillRegistry(skills_dir=skills_dir, auto_discover=False, telemetry_store=telemetry_store)
    registry.discover_skills()

    n_threads = 40  # even, so exactly half fail / half succeed deterministically

    def worker(i: int) -> None:
        registry.invoke_skill("flaky_skill", should_fail=(i % 2 == 0))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    metrics = registry.get_metrics("flaky_skill")
    assert metrics["invocations"] == n_threads
    assert metrics["success_count"] + metrics["failure_count"] == n_threads
    assert metrics["success_count"] == n_threads // 2
    assert metrics["failure_count"] == n_threads // 2

    stored = telemetry_store.get("flaky_skill")
    assert stored["invocation_count"] == n_threads
    assert stored["success_count"] + stored["failure_count"] == n_threads
    assert stored["invocation_count"] == metrics["invocations"]


# --- 14. Dispatcher registration still works --------------------------------

def test_dispatcher_registration_still_works(tmp_path, telemetry_store):
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir,
        "dispatched_skill",
        code="def execute(x: int = 0, **kw):\n    return {'output': x * 2}\n",
    )

    event_bus = EventBus()
    dispatcher = ActionDispatcher(event_bus=event_bus)
    registry = SkillRegistry(
        skills_dir=skills_dir, dispatcher=dispatcher, auto_discover=False, telemetry_store=telemetry_store
    )
    registry.discover_skills()

    result = dispatcher.dispatch_action(action_name="skill_dispatched_skill", payload={"x": 21})
    assert result.success is True
    assert result.data == 42


# --- 15/16. Real built-in skills still discover; tracked metadata untouched -

def test_real_builtin_skills_still_discover_and_load(tmp_path):
    real_skills_dir = Path("jarvis/skills").resolve()
    isolated_store = SkillTelemetryStore(tmp_path / "telemetry.json")

    registry = SkillRegistry(skills_dir=real_skills_dir, auto_discover=True, telemetry_store=isolated_store)
    names = [s.name for s in registry.list_skills()]

    for expected in [
        "calculator", "briefing", "file_manager", "note_taker",
        "pomodoro", "system_control", "git_assistant", "clipboard", "app_launcher",
    ]:
        assert expected in names


def test_running_against_real_skills_dir_leaves_tracked_metadata_unchanged(tmp_path):
    real_skills_dir = Path("jarvis/skills").resolve()
    metadata_files = list(real_skills_dir.glob("*/metadata.json"))
    before = {p: p.read_text(encoding="utf-8") for p in metadata_files}

    isolated_store = SkillTelemetryStore(tmp_path / "telemetry.json")
    registry = SkillRegistry(skills_dir=real_skills_dir, auto_discover=True, telemetry_store=isolated_store)
    registry.invoke_skill("calculator", expression="1+1")
    registry.invoke_skill("briefing", city="Hanoi")

    after = {p: p.read_text(encoding="utf-8") for p in metadata_files}
    assert before == after
