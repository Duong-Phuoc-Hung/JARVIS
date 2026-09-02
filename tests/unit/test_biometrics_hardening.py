"""
tests/test_biometrics_hardening.py
===================================
Focused regression suite for the biometrics hardening pass over
jarvis/vision/biometrics.py: embedding validation, storage corruption
resilience/atomicity, label validation, face-count ambiguity, matching/tolerance
semantics, optional-dependency graceful degradation, enrollment duplication, and
privilege-session correctness.

Architecture/behavior reference only: ageitgey/face_recognition (MIT) informed the
128D-embedding / Euclidean-distance / tolerance conventions exercised below. No
upstream source is used, no real biometric data is used - all embeddings here are
synthetic, deterministic 128D float arrays. This suite hardens software semantics;
it makes no claim about recognition accuracy, false-accept/reject rates, spoofing
resistance, or liveness detection.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from jarvis.vision.biometrics import (
    DEFAULT_TOLERANCE,
    EMBEDDING_DIM,
    BiometricPrivilegeGate,
    BiometricsEngine,
    FaceEmbeddingStorage,
    _validate_embedding,
    _validate_label,
    _validate_tolerance,
)


def _unit_vec(index: int, dim: int = EMBEDDING_DIM) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float64)
    v[index] = 1.0
    return v


class MockCam:
    """Deterministic mock camera: returns a configurable list of encodings per frame."""

    def __init__(self, encodings: list[Any] | None = None, owner_encoding: np.ndarray | None = None):
        self._encodings = encodings if encodings is not None else []
        if owner_encoding is not None:
            self.owner_encoding = owner_encoding

    def set_encodings(self, encodings: list[Any]) -> None:
        self._encodings = encodings

    def get_face_encodings(self, frame: np.ndarray) -> list[Any]:
        return self._encodings


class ThrowingCam:
    """Mock camera whose extraction backend raises - must never crash callers."""

    def get_face_encodings(self, frame: np.ndarray) -> list[Any]:
        raise RuntimeError("simulated backend failure")


BRIGHT_FRAME = np.full((64, 64, 3), 128, dtype=np.uint8)


# ============================================================================
# 1. EMBEDDING VALIDATION
# ============================================================================

def test_valid_128d_embedding_accepted():
    v = _unit_vec(0)
    result = _validate_embedding(v)
    assert result is not None
    assert result.shape == (EMBEDDING_DIM,)
    assert result.dtype == np.float64


def test_127d_rejected():
    assert _validate_embedding([0.0] * 127) is None


def test_129d_rejected():
    assert _validate_embedding([0.0] * 129) is None


def test_empty_embedding_rejected():
    assert _validate_embedding([]) is None
    assert _validate_embedding(np.array([])) is None


def test_nan_embedding_rejected():
    v = [0.0] * EMBEDDING_DIM
    v[5] = float("nan")
    assert _validate_embedding(v) is None


def test_infinity_embedding_rejected():
    v = [0.0] * EMBEDDING_DIM
    v[5] = float("inf")
    assert _validate_embedding(v) is None
    v[5] = float("-inf")
    assert _validate_embedding(v) is None


def test_non_numeric_embedding_rejected():
    assert _validate_embedding(["a"] * EMBEDDING_DIM) is None
    assert _validate_embedding("not a list") is None
    assert _validate_embedding(None) is None


def test_malformed_nested_structure_rejected():
    ragged = [0.0] * (EMBEDDING_DIM - 1) + [[1.0, 2.0]]
    assert _validate_embedding(ragged) is None
    assert _validate_embedding([[0.0] * EMBEDDING_DIM]) is None  # shape (1, 128)


def test_validate_embedding_does_not_mutate_caller_array():
    original = _unit_vec(3)
    snapshot = original.copy()
    result = _validate_embedding(original)
    assert result is not None
    result[0] = 999.0
    assert np.array_equal(original, snapshot), "validation must never mutate caller's array"


# ============================================================================
# 2. STORAGE CORRUPTION
# ============================================================================

def test_malformed_storage_json_fails_gracefully(tmp_path):
    store_path = tmp_path / "faces.json"
    store_path.write_text("{invalid json: broken", encoding="utf-8")
    storage = FaceEmbeddingStorage(storage_path=store_path)
    assert storage.enrolled_faces == {}


def test_storage_root_wrong_type_fails_gracefully(tmp_path):
    store_path = tmp_path / "faces.json"
    store_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    storage = FaceEmbeddingStorage(storage_path=store_path)
    assert storage.enrolled_faces == {}

    store_path.write_text(json.dumps("just a string"), encoding="utf-8")
    storage2 = FaceEmbeddingStorage(storage_path=store_path)
    assert storage2.enrolled_faces == {}


def test_mixed_valid_and_corrupt_storage_entries_retains_only_valid(tmp_path):
    store_path = tmp_path / "faces.json"
    valid_emb = _unit_vec(1).tolist()
    raw = {
        "good_owner": valid_emb,
        "bad_short": [0.0] * 50,
        "bad_nan": [float("nan")] * EMBEDDING_DIM,
        "bad_type": "not a list",
        "": valid_emb,  # invalid label
    }
    store_path.write_text(json.dumps(raw), encoding="utf-8")

    storage = FaceEmbeddingStorage(storage_path=store_path)
    assert list(storage.enrolled_faces.keys()) == ["good_owner"]
    assert storage.enrolled_faces["good_owner"] == valid_emb


def test_atomic_save_preserves_valid_file_if_write_fails(tmp_path, monkeypatch):
    store_path = tmp_path / "faces.json"
    storage = FaceEmbeddingStorage(storage_path=store_path)
    owner_emb = _unit_vec(2)
    assert storage.add_face("owner", owner_emb) is True
    original_bytes = store_path.read_bytes()

    def _boom(self, *a, **kw):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(Path, "write_text", _boom)
    ok = storage.add_face("owner2", _unit_vec(3))
    assert ok is False
    # Original file on disk must be untouched.
    assert store_path.read_bytes() == original_bytes
    # In-memory store must not claim the failed enrollment succeeded.
    assert "owner2" not in storage.enrolled_faces


def test_storage_survives_registry_restart(tmp_path):
    store_path = tmp_path / "faces.json"
    storage1 = FaceEmbeddingStorage(storage_path=store_path)
    assert storage1.add_face("owner", _unit_vec(4)) is True

    storage2 = FaceEmbeddingStorage(storage_path=store_path)
    assert "owner" in storage2.enrolled_faces
    assert np.allclose(np.array(storage2.enrolled_faces["owner"]), _unit_vec(4))


def test_no_biometric_files_written_into_repo_tree_by_default(tmp_path, monkeypatch):
    fake_appdata = tmp_path / "FakeAppData"
    fake_appdata.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(fake_appdata))
    monkeypatch.delenv("APPDATA", raising=False)

    storage = FaceEmbeddingStorage()  # default (empty) path
    repo_root = Path(__file__).resolve().parents[1]
    assert repo_root not in storage.storage_path.parents
    assert str(fake_appdata) in str(storage.storage_path)


# ============================================================================
# 3. LABEL VALIDATION
# ============================================================================

def test_label_empty_rejected():
    assert _validate_label("") is None
    assert _validate_label("   ") is None


def test_label_wrong_type_rejected():
    assert _validate_label(None) is None
    assert _validate_label(123) is None
    assert _validate_label(["owner"]) is None


def test_label_control_characters_rejected():
    assert _validate_label("owner\x00evil") is None
    assert _validate_label("owner\ntwo") is None


def test_label_too_long_rejected():
    assert _validate_label("x" * 129) is None
    assert _validate_label("x" * 128) == "x" * 128


def test_duplicate_label_replaces_deterministically(tmp_path):
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    emb1 = _unit_vec(1)
    emb2 = _unit_vec(2)
    assert storage.add_face("owner", emb1) is True
    assert storage.add_face("owner", emb2) is True
    assert list(storage.enrolled_faces.keys()) == ["owner"]
    assert np.allclose(np.array(storage.enrolled_faces["owner"]), emb2)


# ============================================================================
# 4. FACE COUNT AMBIGUITY - ENROLLMENT
# ============================================================================

def test_enrollment_zero_faces_fails(tmp_path):
    cam = MockCam(encodings=[])
    engine = BiometricsEngine(camera_feed=cam, storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    assert engine.enroll_face("owner", BRIGHT_FRAME) is False


def test_enrollment_multiple_faces_fails(tmp_path):
    cam = MockCam(encodings=[_unit_vec(1), _unit_vec(2)])
    engine = BiometricsEngine(camera_feed=cam, storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    assert engine.enroll_face("owner", BRIGHT_FRAME) is False
    assert "owner" not in engine.storage.enrolled_faces


def test_enrollment_exactly_one_valid_face_succeeds(tmp_path):
    cam = MockCam(encodings=[_unit_vec(1)])
    engine = BiometricsEngine(camera_feed=cam, storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    assert engine.enroll_face("owner", BRIGHT_FRAME) is True
    assert "owner" in engine.storage.enrolled_faces


def test_enrollment_rejects_malformed_encoding(tmp_path):
    cam = MockCam(encodings=[[0.0] * 50])  # wrong dimension
    engine = BiometricsEngine(camera_feed=cam, storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    assert engine.enroll_face("owner", BRIGHT_FRAME) is False


def test_enrollment_failed_persistence_does_not_create_inconsistent_state(tmp_path, monkeypatch):
    cam = MockCam(encodings=[_unit_vec(1)])
    engine = BiometricsEngine(camera_feed=cam, storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))

    monkeypatch.setattr(engine.storage, "add_face", lambda label, emb: False)
    assert engine.enroll_face("owner", BRIGHT_FRAME) is False
    assert "owner" not in engine._labeled_embeddings
    assert not any(np.allclose(e, _unit_vec(1)) for e in engine.enrolled_embeddings)


def test_enroll_face_replaces_stale_duplicate_in_memory(tmp_path):
    cam = MockCam(encodings=[_unit_vec(1)])
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    engine = BiometricsEngine(camera_feed=cam, storage=storage)
    assert engine.enroll_face("owner", BRIGHT_FRAME) is True

    cam.set_encodings([_unit_vec(9)])
    assert engine.enroll_face("owner", BRIGHT_FRAME) is True

    matches = [e for e in engine.enrolled_embeddings if np.allclose(e, _unit_vec(1)) or np.allclose(e, _unit_vec(9))]
    assert len(matches) == 1, "re-enrolling a label must replace, not accumulate, the in-memory embedding"
    assert np.allclose(matches[0], _unit_vec(9))


# ============================================================================
# 5. VERIFICATION AMBIGUITY
# ============================================================================

def test_verify_no_face_fails(tmp_path):
    engine = BiometricsEngine(storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    cam = MockCam(encodings=[])
    engine.camera = cam
    assert engine.verify_frame(BRIGHT_FRAME) is False


def test_verify_multiple_faces_fails_closed(tmp_path):
    owner = _unit_vec(1)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    cam = MockCam(encodings=[owner, owner])  # ambiguous even if both match
    engine = BiometricsEngine(camera_feed=cam, storage=storage)
    assert engine.verify_frame(BRIGHT_FRAME) is False


def test_verify_malformed_candidate_fails_closed(tmp_path):
    owner = _unit_vec(1)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    cam = MockCam(encodings=[[0.0] * 10])  # malformed dimension
    engine = BiometricsEngine(camera_feed=cam, storage=storage)
    assert engine.verify_frame(BRIGHT_FRAME) is False


def test_verify_no_enrolled_embeddings_fails(tmp_path):
    cam = MockCam(encodings=[_unit_vec(1)])
    engine = BiometricsEngine(camera_feed=cam, storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    assert engine.enrolled_embeddings == []
    assert engine.verify_frame(BRIGHT_FRAME) is False


def test_verify_malformed_stored_embedding_cannot_authenticate(tmp_path):
    store_path = tmp_path / "faces.json"
    store_path.write_text(json.dumps({"owner": [0.0] * 50}), encoding="utf-8")
    storage = FaceEmbeddingStorage(storage_path=store_path)
    assert storage.enrolled_faces == {}  # corrupt entry dropped at load
    cam = MockCam(encodings=[np.zeros(EMBEDDING_DIM)])
    engine = BiometricsEngine(camera_feed=cam, storage=storage)
    assert engine.verify_frame(BRIGHT_FRAME) is False


# ============================================================================
# 6. MATCHING SEMANTICS & TOLERANCE
# ============================================================================

def test_known_close_embedding_matches(tmp_path):
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    close = owner.copy()
    close[1] = 0.1  # distance = 0.1, well under default 0.60 tolerance
    cam = MockCam(encodings=[close])
    engine = BiometricsEngine(camera_feed=cam, storage=storage)
    assert engine.verify_frame(BRIGHT_FRAME) is True


def test_distant_embedding_does_not_match(tmp_path):
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    far = _unit_vec(50)  # distance = sqrt(2) ~= 1.414
    cam = MockCam(encodings=[far])
    engine = BiometricsEngine(camera_feed=cam, storage=storage)
    assert engine.verify_frame(BRIGHT_FRAME) is False


def test_exact_tolerance_boundary_is_strict_less_than(tmp_path):
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    cam = MockCam(encodings=[owner])
    engine = BiometricsEngine(camera_feed=cam, storage=storage, tolerance=0.5)

    at_boundary = owner.copy()
    at_boundary[1] = 0.5  # distance exactly == tolerance -> must NOT match
    cam.set_encodings([at_boundary])
    assert engine.verify_frame(BRIGHT_FRAME) is False

    just_under = owner.copy()
    just_under[1] = 0.4999
    cam.set_encodings([just_under])
    assert engine.verify_frame(BRIGHT_FRAME) is True


@pytest.mark.parametrize("bad_tolerance", [float("nan"), float("inf"), -1.0, "abc", 1e9, True])
def test_invalid_tolerance_cannot_broaden_authentication(tmp_path, bad_tolerance):
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    far = _unit_vec(70)  # far away; would only match under an absurdly broad tolerance
    cam = MockCam(encodings=[far])
    engine = BiometricsEngine(camera_feed=cam, storage=storage, tolerance=bad_tolerance)
    assert engine.tolerance == DEFAULT_TOLERANCE
    assert engine.verify_frame(BRIGHT_FRAME) is False


def test_validate_tolerance_accepts_sane_values():
    assert _validate_tolerance(0.6) == 0.6
    assert _validate_tolerance(0.0) == 0.0
    assert _validate_tolerance(2) == 2.0


# ============================================================================
# 7. OPTIONAL DEPENDENCY BEHAVIOR
# ============================================================================

def test_face_recognition_absent_does_not_crash(tmp_path, monkeypatch):
    import jarvis.vision.biometrics as biometrics_mod
    monkeypatch.setattr(biometrics_mod, "face_recognition", None)
    monkeypatch.setattr(biometrics_mod, "cv2", None)
    engine = BiometricsEngine(storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    assert engine.verify_frame(BRIGHT_FRAME) is False
    assert engine.process_surveillance_frame(BRIGHT_FRAME)["status"] == "no_face"
    assert engine.enroll_face("owner", BRIGHT_FRAME) is False


def test_camera_mock_extraction_still_works(tmp_path):
    cam = MockCam(encodings=[_unit_vec(3)])
    engine = BiometricsEngine(camera_feed=cam, storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    assert engine.enroll_face("owner", BRIGHT_FRAME) is True
    assert engine.verify_frame(BRIGHT_FRAME) is True


def test_camera_backend_throwing_does_not_crash(tmp_path):
    engine = BiometricsEngine(
        camera_feed=ThrowingCam(),
        storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"),
    )
    assert engine.verify_frame(BRIGHT_FRAME) is False
    assert engine.process_surveillance_frame(BRIGHT_FRAME)["status"] == "no_face"
    assert engine.enroll_face("owner", BRIGHT_FRAME) is False


# ============================================================================
# 8. PRIVILEGE SESSION
# ============================================================================

def test_privilege_session_only_begins_after_valid_verification(tmp_path):
    cam = MockCam(encodings=[])  # never matches
    engine = BiometricsEngine(camera_feed=cam, storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    gate = BiometricPrivilegeGate(engine)

    assert gate.authenticate(BRIGHT_FRAME) is None
    assert gate.is_session_valid() is False

    owner = _unit_vec(0)
    engine.storage.add_face("owner", owner)
    engine._labeled_embeddings["owner"] = owner
    cam.set_encodings([owner])
    ctx = gate.authenticate(BRIGHT_FRAME)
    assert ctx is not None
    assert gate.is_session_valid() is True


def test_expired_privilege_session_invalidates(tmp_path):
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    cam = MockCam(encodings=[owner])
    engine = BiometricsEngine(camera_feed=cam, storage=storage)
    gate = BiometricPrivilegeGate(engine, session_ttl_s=0.05)

    ctx = gate.authenticate(BRIGHT_FRAME)
    assert ctx is not None
    assert gate.is_session_valid() is True
    time.sleep(0.1)
    assert gate.is_session_valid() is False
    assert gate.is_allowed("any_action", None) is False


# ============================================================================
# 9. SURVEILLANCE SIDE EFFECTS
# ============================================================================

def test_surveillance_ambiguous_multiface_frame_not_owner_verified(tmp_path):
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    cam = MockCam(encodings=[owner, owner])
    engine = BiometricsEngine(camera_feed=cam, storage=storage)

    res = engine.process_surveillance_frame(BRIGHT_FRAME)
    assert res["status"] != "owner_verified"
    assert res["status"] == "ambiguous_faces"
    assert res["locked"] is False


def test_surveillance_malformed_embedding_not_owner_verified(tmp_path):
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    cam = MockCam(encodings=[[0.0] * 5])
    engine = BiometricsEngine(camera_feed=cam, storage=storage)

    res = engine.process_surveillance_frame(BRIGHT_FRAME)
    assert res["status"] != "owner_verified"
    assert res["status"] == "invalid_face_data"


# ============================================================================
# 9B. INTRUDER LOCK/EVIDENCE TRUTHFULNESS (v4.5.2 P0 hotfix)
# All frames/embeddings are synthetic. No real camera, network, or
# workstation lock is ever exercised by these tests.
# ============================================================================

class _FailIfLockCalled:
    """Test double proving lock_workstation() is never invoked in a given path."""

    def lock_workstation(self):
        raise AssertionError("lock_workstation() must not be called in this scenario")


class _FailIfAlertSent:
    """Test double proving no evidence/alert dispatch happens in a given path."""

    def handle_telegram_send_photo(self, **kwargs):
        raise AssertionError("no photo/alert should be dispatched in this scenario")


class _LockDouble:
    """Deterministic, synthetic lock backend: configurable result or exception,
    and a call counter proving the lock is attempted exactly once."""

    def __init__(self, result: bool | None = None, raise_exc: Exception | None = None):
        self.calls = 0
        self._result = result
        self._raise_exc = raise_exc

    def lock_workstation(self) -> bool:
        self.calls += 1
        if self._raise_exc is not None:
            raise self._raise_exc
        return bool(self._result)


class _CounterOnlyWin32:
    """Test double that only exposes a bookkeeping call-counter attribute,
    with NO real callable lock method -- the exact ambiguous shape the P0
    hotfix must not treat as proof of a successful lock."""

    def __init__(self):
        self.lock_workstation_calls = 0


def _intruder_engine(tmp_path):
    """Builds an engine with one enrolled owner and a candidate far enough
    away to be classified as a non-matching intruder."""
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    intruder = _unit_vec(50)  # distance = sqrt(2), well outside default tolerance
    cam = MockCam(encodings=[intruder])
    engine = BiometricsEngine(camera_feed=cam, storage=storage)
    return engine


def test_surveillance_no_enrolled_embeddings_is_not_classified_as_intruder(tmp_path):
    """[1] A valid face with zero enrolled references must never be reported
    as an intruder, must never attempt a lock, and must never dispatch
    evidence -- there is nothing to compare against."""
    cam = MockCam(encodings=[_unit_vec(1)])
    engine = BiometricsEngine(camera_feed=cam, storage=FaceEmbeddingStorage(storage_path=tmp_path / "faces.json"))
    assert engine.enrolled_embeddings == []

    res = engine.process_surveillance_frame(
        BRIGHT_FRAME, win32_platform=_FailIfLockCalled(), http_server=_FailIfAlertSent()
    )

    assert res["status"] == "no_enrolled_faces"
    assert res["status"] != "intruder_locked"
    assert res["locked"] is False
    assert res["distance"] is None


def test_surveillance_real_intruder_lock_success(tmp_path):
    """[2] A genuine intruder with a lock backend that reports True."""
    engine = _intruder_engine(tmp_path)
    win32 = _LockDouble(result=True)

    res = engine.process_surveillance_frame(BRIGHT_FRAME, win32_platform=win32)

    assert res["status"] == "intruder_locked"
    assert res["locked"] is True
    assert win32.calls == 1


def test_surveillance_real_intruder_lock_returns_false(tmp_path):
    """[3] A genuine intruder with a lock backend that reports False."""
    engine = _intruder_engine(tmp_path)
    win32 = _LockDouble(result=False)

    res = engine.process_surveillance_frame(BRIGHT_FRAME, win32_platform=win32)

    assert res["status"] != "intruder_locked"
    assert res["status"] == "intruder_lock_failed"
    assert res["locked"] is False
    assert win32.calls == 1


def test_surveillance_real_intruder_lock_raises(tmp_path):
    """[4] A genuine intruder whose lock backend raises: no exception escapes."""
    engine = _intruder_engine(tmp_path)
    win32 = _LockDouble(raise_exc=RuntimeError("simulated lock backend failure"))

    res = engine.process_surveillance_frame(BRIGHT_FRAME, win32_platform=win32)  # must not raise

    assert res["status"] == "intruder_lock_failed"
    assert res["locked"] is False
    assert win32.calls == 1


def test_surveillance_counter_only_win32_double_cannot_confirm_lock(tmp_path):
    """The mere presence/increment of a call-counter attribute must never be
    treated as proof of a successful lock -- only an actual callable result
    counts. A test double exposing only `.lock_workstation_calls` (no real
    `lock_workstation()` method) must resolve to a failed, unconfirmed lock."""
    engine = _intruder_engine(tmp_path)
    win32 = _CounterOnlyWin32()

    res = engine.process_surveillance_frame(BRIGHT_FRAME, win32_platform=win32)

    assert res["locked"] is False
    assert res["status"] == "intruder_lock_failed"
    # The counter must not have been silently incremented by production code
    # pretending a lock occurred.
    assert win32.lock_workstation_calls == 0


def test_surveillance_evidence_uses_real_encoder_output_not_fake_sentinel(tmp_path, monkeypatch):
    """[5] Evidence bytes delivered to the alert transport are the actual
    (mocked) encoder output for the real frame -- never a hardcoded sentinel."""
    engine = _intruder_engine(tmp_path)
    win32 = _LockDouble(result=True)

    real_encoder_bytes = b"\xff\xd8\xff\xe0REAL_JPEG_BYTES_FROM_ENCODER"
    monkeypatch.setattr(engine, "_encode_frame_as_jpeg", lambda frame: real_encoder_bytes)

    captured: dict[str, Any] = {}

    class CaptureHTTP:
        def handle_telegram_send_photo(self, chat_id, photo_bytes, caption):
            captured["photo_bytes"] = photo_bytes
            captured["caption"] = caption

    res = engine.process_surveillance_frame(BRIGHT_FRAME, win32_platform=win32, http_server=CaptureHTTP())

    assert res["locked"] is True
    assert captured["photo_bytes"] == real_encoder_bytes
    assert captured["photo_bytes"] != b"fake_intruder_photo_jpeg"


def test_surveillance_cv2_unavailable_no_photo_sent_lock_still_truthful(tmp_path, monkeypatch):
    """[6] With cv2 unavailable, no fake photo is sent, and the lock result
    remains truthful and independent of evidence dispatch."""
    import jarvis.vision.biometrics as biometrics_mod
    monkeypatch.setattr(biometrics_mod, "cv2", None)

    engine = _intruder_engine(tmp_path)
    win32 = _LockDouble(result=True)

    res = engine.process_surveillance_frame(BRIGHT_FRAME, win32_platform=win32, http_server=_FailIfAlertSent())

    assert res["status"] == "intruder_locked"
    assert res["locked"] is True


def test_surveillance_encoder_failure_no_photo_sent_lock_still_truthful(tmp_path, monkeypatch):
    """[7] When encoding fails (returns None), no fake photo is sent, and the
    lock result remains truthful."""
    engine = _intruder_engine(tmp_path)
    win32 = _LockDouble(result=True)
    monkeypatch.setattr(engine, "_encode_frame_as_jpeg", lambda frame: None)

    res = engine.process_surveillance_frame(BRIGHT_FRAME, win32_platform=win32, http_server=_FailIfAlertSent())

    assert res["status"] == "intruder_locked"
    assert res["locked"] is True


def test_surveillance_alert_transport_exception_does_not_affect_lock_truth(tmp_path, monkeypatch):
    """[8] An alert-transport exception must not flip a successful lock to
    failed, nor a failed lock to successful, and must not crash the call."""
    engine = _intruder_engine(tmp_path)
    monkeypatch.setattr(engine, "_encode_frame_as_jpeg", lambda frame: b"jpegbytes")

    class RaisingHTTP:
        def handle_telegram_send_photo(self, **kwargs):
            raise RuntimeError("simulated network failure")

    # Successful lock must remain locked=True despite the alert exception.
    win32_ok = _LockDouble(result=True)
    res_ok = engine.process_surveillance_frame(BRIGHT_FRAME, win32_platform=win32_ok, http_server=RaisingHTTP())
    assert res_ok["locked"] is True
    assert res_ok["status"] == "intruder_locked"

    # Failed lock must remain locked=False despite the alert exception.
    win32_fail = _LockDouble(result=False)
    res_fail = engine.process_surveillance_frame(BRIGHT_FRAME, win32_platform=win32_fail, http_server=RaisingHTTP())
    assert res_fail["locked"] is False
    assert res_fail["status"] == "intruder_lock_failed"


def test_surveillance_owner_match_still_no_lock_no_photo(tmp_path):
    """[9] An actual owner match remains owner_verified, with no lock attempt
    and no intruder evidence dispatch."""
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)
    cam = MockCam(encodings=[owner])  # exact match
    engine = BiometricsEngine(camera_feed=cam, storage=storage)

    res = engine.process_surveillance_frame(
        BRIGHT_FRAME, win32_platform=_FailIfLockCalled(), http_server=_FailIfAlertSent()
    )

    assert res["status"] == "owner_verified"
    assert res["locked"] is False


def test_surveillance_ambiguous_and_malformed_never_lock_or_dispatch(tmp_path):
    """[10] Ambiguous multi-face and malformed-embedding frames must never
    attempt a lock or dispatch intruder evidence."""
    owner = _unit_vec(0)
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    storage.add_face("owner", owner)

    # Ambiguous: two faces detected.
    cam_ambiguous = MockCam(encodings=[owner, owner])
    engine_ambiguous = BiometricsEngine(camera_feed=cam_ambiguous, storage=storage)
    res_ambiguous = engine_ambiguous.process_surveillance_frame(
        BRIGHT_FRAME, win32_platform=_FailIfLockCalled(), http_server=_FailIfAlertSent()
    )
    assert res_ambiguous["status"] == "ambiguous_faces"
    assert res_ambiguous["locked"] is False

    # Malformed embedding.
    cam_malformed = MockCam(encodings=[[0.0] * 5])
    engine_malformed = BiometricsEngine(camera_feed=cam_malformed, storage=storage)
    res_malformed = engine_malformed.process_surveillance_frame(
        BRIGHT_FRAME, win32_platform=_FailIfLockCalled(), http_server=_FailIfAlertSent()
    )
    assert res_malformed["status"] == "invalid_face_data"
    assert res_malformed["locked"] is False


# ============================================================================
# 10. PUBLIC API COMPATIBILITY
# ============================================================================

def test_public_api_compatibility(tmp_path):
    cam = MockCam(encodings=[_unit_vec(1)])
    storage = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    engine = BiometricsEngine(camera_feed=cam, storage=storage)

    assert isinstance(engine.enroll_face("owner", BRIGHT_FRAME), bool)
    assert isinstance(engine.verify_frame(BRIGHT_FRAME), bool)
    res = engine.process_surveillance_frame(BRIGHT_FRAME)
    assert isinstance(res, dict)
    assert "status" in res

    gate = BiometricPrivilegeGate(engine)
    assert isinstance(gate.is_allowed("x", None), bool)
    assert isinstance(storage.add_face("owner2", _unit_vec(2)), bool)
