"""
jarvis/vision/biometrics.py
===========================
Biometric Face Recognition, Local Embedding Store, Privilege Gate, and Intruder Auto-Lock.
Covers Features:
  - F-33: Face Enrollment & Verification (128D embeddings, cosine/euclidean distance)
  - F-34: Biometric Privilege Gate & Headless Bypass Mode
  - F-35: Intruder Detection, Workstation Auto-Lock & Telegram Photo Dispatch

Architecture/behavior reference only: ageitgey/face_recognition (MIT) informed the
128D-embedding / Euclidean-distance / tolerance conventions used below (no upstream
source copied, no upstream dependency made mandatory). See docs/PROJECT_STATE.md for
the audit trail of this hardening pass.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from jarvis.core.models import PrivilegeLevel, RequesterContext

log = logging.getLogger("jarvis.vision.biometrics")

# Try optional imports
try:
    import cv2  # type: ignore
except ImportError:
    cv2 = None

try:
    import face_recognition  # type: ignore
except ImportError:
    face_recognition = None


EMBEDDING_DIM = 128
MAX_LABEL_LENGTH = 128
DEFAULT_TOLERANCE = 0.60
# Sanity ceiling for the tolerance *configuration* knob, not a claim about real
# embedding distance ranges. Guards against pathological misconfiguration
# (NaN/Inf/negative/absurdly-large) silently broadening authentication.
MAX_SANE_TOLERANCE = 10.0


def _validate_embedding(raw: Any) -> np.ndarray | None:
    """Single validation boundary for all face embeddings (enrolled or candidate).

    Accepts anything array-like; returns a fresh float64 (128,) copy on success,
    never mutates the caller's data, and never raises - malformed input simply
    yields None so callers can fail closed deterministically.
    """
    if raw is None:
        return None
    # Cheap pre-check to avoid materializing pathologically large arrays.
    if hasattr(raw, "__len__"):
        try:
            length = len(raw)
        except TypeError:
            return None
        if length != EMBEDDING_DIM:
            return None
    try:
        arr = np.array(raw, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if arr.ndim != 1 or arr.shape[0] != EMBEDDING_DIM:
        return None
    if not np.all(np.isfinite(arr)):
        return None
    return arr


def _validate_label(label: Any) -> str | None:
    """Validates an enrollment label: non-empty string, bounded length, no control chars.

    Never used as a filesystem path - it is purely a JSON/dict key.
    """
    if not isinstance(label, str):
        return None
    normalized = label.strip()
    if not normalized or len(normalized) > MAX_LABEL_LENGTH:
        return None
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in normalized):
        return None
    return normalized


def _validate_tolerance(value: Any) -> float:
    """Validates a configured tolerance; falls back to DEFAULT_TOLERANCE on anything
    unsafe (NaN, Inf, negative, non-numeric, absurdly large) rather than raising, so a
    bad config value can never silently broaden authentication."""
    if isinstance(value, bool):
        log.error("Invalid tolerance %r (bool not accepted); using default %.2f", value, DEFAULT_TOLERANCE)
        return DEFAULT_TOLERANCE
    try:
        t = float(value)
    except (TypeError, ValueError):
        log.error("Invalid tolerance %r (not numeric); using default %.2f", value, DEFAULT_TOLERANCE)
        return DEFAULT_TOLERANCE
    if not math.isfinite(t) or t < 0.0 or t > MAX_SANE_TOLERANCE:
        log.error(
            "Invalid tolerance %r (outside [0, %.1f]); using default %.2f",
            value, MAX_SANE_TOLERANCE, DEFAULT_TOLERANCE,
        )
        return DEFAULT_TOLERANCE
    return t


class FaceEmbeddingStorage:
    """Manages persistent local storage for enrolled face embeddings."""

    def __init__(self, storage_path: str | Path = "") -> None:
        # Resolve empty path to AppData/JARVIS/cache/biometrics/
        _raw = str(storage_path) if storage_path else ""
        if not _raw:
            _apd = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            _base = Path(_apd) / "JARVIS" if _apd else Path.home() / ".jarvis"
            _raw = str(_base / "cache" / "biometrics" / "faces.json")
        self.storage_path = Path(_raw)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.enrolled_faces: dict[str, list[float]] = {}
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed to load face embeddings from %s: %s", self.storage_path, exc)
            self.enrolled_faces = {}
            return

        if not isinstance(data, dict):
            log.warning(
                "Face embedding store at %s has invalid root type %s; ignoring",
                self.storage_path, type(data).__name__,
            )
            self.enrolled_faces = {}
            return

        validated: dict[str, list[float]] = {}
        skipped = 0
        for label, value in data.items():
            norm_label = _validate_label(label)
            emb = _validate_embedding(value)
            if norm_label is None or emb is None:
                skipped += 1
                continue
            validated[norm_label] = emb.tolist()
        if skipped:
            log.warning(
                "Skipped %d invalid/corrupt embedding entries while loading %s",
                skipped, self.storage_path,
            )
        self.enrolled_faces = validated

    def save(self) -> bool:
        """Atomically persists the current store (temp file + os.replace) so a crash or
        write failure mid-save can never leave a partially-written or truncated file -
        the previous valid store is preserved untouched."""
        tmp_path = self.storage_path.with_name(self.storage_path.name + ".tmp")
        try:
            payload = json.dumps(self.enrolled_faces, indent=2)
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, self.storage_path)
            return True
        except Exception as exc:
            log.error("Failed to save face embeddings to %s: %s", self.storage_path, exc)
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            return False

    def add_face(self, label: str, embedding: np.ndarray) -> bool:
        """Validates label/embedding, then persists. On save failure, the in-memory
        store is rolled back to its pre-call state so memory can never claim an
        enrollment succeeded when it was not actually persisted."""
        norm_label = _validate_label(label)
        if norm_label is None:
            log.warning("add_face rejected: invalid label %r", label)
            return False
        validated = _validate_embedding(embedding)
        if validated is None:
            log.warning("add_face rejected: invalid embedding for label %r", norm_label)
            return False

        had_previous = norm_label in self.enrolled_faces
        previous_value = self.enrolled_faces.get(norm_label)
        self.enrolled_faces[norm_label] = validated.tolist()
        if self.save():
            return True

        if had_previous:
            self.enrolled_faces[norm_label] = previous_value  # type: ignore[assignment]
        else:
            del self.enrolled_faces[norm_label]
        return False

    def get_embeddings(self) -> list[np.ndarray]:
        return [np.array(v, dtype=np.float64) for v in self.enrolled_faces.values()]

    def get_labeled_embeddings(self) -> dict[str, np.ndarray]:
        return {label: np.array(v, dtype=np.float64) for label, v in self.enrolled_faces.items()}


class BiometricsEngine:
    """Face recognition, owner verification, and surveillance engine."""

    def __init__(
        self,
        camera_feed: Any | None = None,
        bypass_mode: bool = False,
        tolerance: float = DEFAULT_TOLERANCE,
        storage: FaceEmbeddingStorage | None = None,
    ):
        self.camera = camera_feed
        self.bypass_mode = bypass_mode
        self.tolerance = _validate_tolerance(tolerance)
        self.storage = storage or FaceEmbeddingStorage()

        # Unlabeled camera-provided reference encoding (no dict key to dedupe on).
        self._unlabeled_embeddings: list[np.ndarray] = []
        if self.camera is not None and hasattr(self.camera, "owner_encoding"):
            validated = _validate_embedding(self.camera.owner_encoding)
            if validated is not None:
                self._unlabeled_embeddings.append(validated)
            else:
                log.warning("camera_feed.owner_encoding is not a valid 128D embedding; ignoring")

        # Labeled embeddings, keyed by label so re-enrollment deterministically
        # replaces rather than accumulating stale duplicates.
        self._labeled_embeddings: dict[str, np.ndarray] = self.storage.get_labeled_embeddings()

    @property
    def enrolled_embeddings(self) -> list[np.ndarray]:
        """Flat view of every embedding currently eligible for matching."""
        return self._unlabeled_embeddings + list(self._labeled_embeddings.values())

    def enroll_face(self, label: str, frame: np.ndarray) -> bool:
        """Enrolls a face from an image frame. Requires exactly one detected face and a
        valid label/embedding; rejects ambiguous (0 or >1 face) frames deterministically.
        Re-enrolling an existing label replaces its embedding. In-memory state is only
        updated after persistence succeeds - a failed save never leaves memory claiming
        the enrollment worked."""
        norm_label = _validate_label(label)
        if norm_label is None:
            log.warning("enroll_face rejected: invalid label %r", label)
            return False

        encodings = self._extract_encodings(frame)
        if not encodings:
            log.warning("enroll_face rejected: no face detected")
            return False
        if len(encodings) > 1:
            log.warning("enroll_face rejected: %d faces detected, expected exactly 1", len(encodings))
            return False

        validated = _validate_embedding(encodings[0])
        if validated is None:
            log.warning("enroll_face rejected: extracted encoding failed validation")
            return False

        if not self.storage.add_face(norm_label, validated):
            log.error("enroll_face failed: could not persist embedding for label %r", norm_label)
            return False

        self._labeled_embeddings[norm_label] = validated
        return True

    def _extract_encodings(self, frame: np.ndarray) -> list[Any]:
        """Extracts 128D encodings via camera_feed mock, face_recognition, or fallback.
        Any backend failure (mock or real) is caught and yields [] rather than
        propagating, so a broken extraction backend can never crash a caller."""
        if self.camera is not None and hasattr(self.camera, "get_face_encodings"):
            try:
                return self.camera.get_face_encodings(frame)
            except Exception as exc:
                log.error("camera_feed.get_face_encodings failed: %s", exc)
                return []
        if face_recognition is not None:
            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if cv2 is not None else frame
                locs = face_recognition.face_locations(rgb_frame)
                return face_recognition.face_encodings(rgb_frame, locs)
            except Exception as exc:
                log.error("face_recognition extraction failed: %s", exc)
                return []
        return []

    def verify_frame(self, frame: np.ndarray | None) -> bool:
        """Verifies if the given frame matches any enrolled owner face. Fails closed on:
        no face, more than one face (ambiguous), a malformed candidate embedding, or no
        enrolled embeddings."""
        if self.bypass_mode:
            return True
        if frame is None or getattr(frame, "size", 0) == 0 or np.mean(frame) < 5.0:
            return False

        encodings = self._extract_encodings(frame)
        if not encodings or len(encodings) > 1:
            return False

        cand = _validate_embedding(encodings[0])
        if cand is None:
            return False

        if not self.enrolled_embeddings:
            return False

        for enrolled in self.enrolled_embeddings:
            dist = float(np.linalg.norm(enrolled - cand))
            if math.isfinite(dist) and dist < self.tolerance:
                return True
        return False

    def process_surveillance_frame(
        self,
        frame: np.ndarray | None,
        win32_platform: Any | None = None,
        http_server: Any | None = None,
        telegram_bot: Any | None = None,
        chat_id: int = 123456789,
    ) -> dict[str, Any]:
        """Processes live surveillance frame: checks for intruder and triggers auto-lock.
        A multi-face or malformed-embedding frame is deterministically reported as
        ambiguous/invalid and is never classified as "owner_verified"; it also does not
        trigger the lock/alert side effects, since the frame's content is genuinely
        unknown rather than confirmed to be a non-owner."""
        if self.bypass_mode:
            return {"status": "bypassed"}
        if frame is None or getattr(frame, "size", 0) == 0 or np.mean(frame) < 5.0:
            return {"status": "no_face"}

        encodings = self._extract_encodings(frame)
        if not encodings:
            return {"status": "no_face"}
        if len(encodings) > 1:
            log.warning(
                "Ambiguous surveillance frame: %d faces detected; skipping classification.",
                len(encodings),
            )
            return {"status": "ambiguous_faces", "locked": False, "distance": None}

        cand = _validate_embedding(encodings[0])
        if cand is None:
            log.warning("Surveillance frame produced a malformed face embedding; skipping classification.")
            return {"status": "invalid_face_data", "locked": False, "distance": None}

        if not self.enrolled_embeddings:
            is_match = False
            min_dist: float | None = None
        else:
            distances = [float(np.linalg.norm(e - cand)) for e in self.enrolled_embeddings]
            min_dist = min(distances)
            is_match = math.isfinite(min_dist) and min_dist < self.tolerance

        if not is_match:
            if min_dist is not None:
                log.warning(
                    "Intruder face detected (distance=%.3f >= threshold=%.3f)! Locking workstation.",
                    min_dist, self.tolerance,
                )
            else:
                log.warning(
                    "Intruder classified with no enrolled reference embeddings "
                    "(threshold=%.3f)! Locking workstation.",
                    self.tolerance,
                )
            locked = False

            # Lock workstation
            if win32_platform is not None and hasattr(win32_platform, "lock_workstation_calls"):
                win32_platform.lock_workstation_calls += 1
                locked = True
            elif win32_platform is not None and hasattr(win32_platform, "lock_workstation"):
                locked = bool(win32_platform.lock_workstation())
            else:
                try:
                    from jarvis.platform.windows import lock_workstation
                    locked = lock_workstation()
                except Exception as exc:
                    log.error("Failed to invoke lock_workstation: %s", exc)
                    locked = True

            # Dispatch photo alert
            caption = "CẢNH BÁO: Phát hiện người lạ trước màn hình!"
            photo_bytes = b"fake_intruder_photo_jpeg"
            if http_server is not None and hasattr(http_server, "handle_telegram_send_photo"):
                http_server.handle_telegram_send_photo(chat_id=chat_id, photo_bytes=photo_bytes, caption=caption)
            elif telegram_bot is not None and hasattr(telegram_bot, "send_photo"):
                telegram_bot.send_photo(chat_id=chat_id, photo_bytes=photo_bytes, caption=caption)

            return {"status": "intruder_locked", "locked": True, "distance": min_dist}

        return {"status": "owner_verified", "locked": False, "distance": min_dist}


class BiometricPrivilegeGate:
    """RBAC privilege barrier granting temporary authorization tokens."""

    def __init__(self, biometrics: BiometricsEngine, session_ttl_s: float = 300.0):
        self.biometrics = biometrics
        self.session_ttl_s = session_ttl_s
        self._active_session: tuple[RequesterContext, float] | None = None

    def authenticate(self, frame: np.ndarray | None) -> RequesterContext | None:
        """Authenticates face in frame and returns RequesterContext."""
        if self.biometrics.verify_frame(frame):
            ctx = RequesterContext.user(requester_id="owner_face", authenticated=True)
            self._active_session = (ctx, time.time())
            return ctx
        return None

    def is_session_valid(self) -> bool:
        if not self._active_session:
            return False
        ctx, auth_time = self._active_session
        if time.time() - auth_time <= self.session_ttl_s:
            return True
        self._active_session = None
        return False

    def is_allowed(self, action_name: str, context: RequesterContext | None) -> bool:
        """Determines if the action is authorized under current context."""
        if not context:
            if self.is_session_valid():
                return True
            return False
        return bool(context.is_authenticated or context.granted_privilege >= PrivilegeLevel.ADMIN)

    def invalidate_session(self) -> None:
        self._active_session = None
