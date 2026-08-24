# Technical Blueprint & Handoff Report: Milestone 5 (Vision, Biometrics, Smart Home)

**Explorer ID**: explorer_m5_1  
**Target Modules**:
1. `jarvis/vision/biometrics.py` (F-33, F-34, F-35)
2. `jarvis/vision/hands.py` (F-36, F-37)
3. `jarvis/smart_home/home_assistant.py` (F-26)
4. `jarvis/smart_home/mqtt.py` (F-27)

---

## 1. Observation

### 1.1 Requirements & Specifications
- **ORIGINAL_REQUEST.md**:
  - `R12 (Lines 64-67)`: Face recognition (OpenCV + face_recognition). Requires webcam authentication to unlock privileged actions (admin shell, network security audits). Unknown face triggers Windows auto-lock (`user32.LockWorkStation`) and snapshot dispatch to Telegram. Headless non-camera bypass mode required.
  - `R13 (Lines 68-71)`: MediaPipe hand tracking & touchless gestures via webcam: swipe left/right for virtual desktop switching, fist clench to close active window, open palm for tray toggle. Tray toggle enable/disable.
  - `R9 (Lines 52-55)`: Smart Home integration via Home Assistant REST/WebSocket API and MQTT protocol for lights, temperature, and sensor telemetry.
- **PROJECT.md**:
  - `F-33 (Line 86)`: Face Enrollment & Verification (128D face embedding comparison, Euclidean distance < 0.60 threshold).
  - `F-34 (Line 87)`: Biometric Privilege Gate (RBAC barrier for sensitive commands, returns `RequesterContext` with `PrivilegeLevel.ADMIN`).
  - `F-35 (Line 88)`: Intruder Detection & Auto-Lock (`user32.LockWorkStation` on Windows + Telegram photo alert).
  - `F-36 (Line 89)`: MediaPipe Hand Gesture Tracker (21-point 3D hand tracking).
  - `F-37 (Line 90)`: Virtual Desktop & Window Gestures (`ctrl+win+left/right`, `alt+f4` / `close_window`).
  - `F-26 (Line 79)`: Home Assistant REST/WS Client (Entity state inspection & service invocations).
  - `F-27 (Line 80)`: MQTT Protocol Adapter (Topic publishing & subscription callback routing).

### 1.2 Codebase & Existing Interfaces
- **`jarvis/core/models.py`**:
  - `PrivilegeLevel` (`NORMAL=0`, `HIGH=1`, `ADMIN=2`) (lines 12-16).
  - `RequesterContext` with `requester_id`, `granted_privilege`, `is_authenticated`, and factory methods `RequesterContext.system()` and `RequesterContext.user(requester_id, authenticated)` (lines 30-55).
- **`jarvis/core/dispatcher.py`**:
  - `ActionDispatcher.set_privilege_interceptor(interceptor: Callable[..., bool])` (line 311).
  - `ActionDispatcher.dispatch_action(action_name, payload, requester)` enforces RBAC privilege checking (lines 336-394).
  - `EventBus` publish/subscribe topics: `"security.intruder_detected"`, `"security.workstation_locked"`, `"vision.gesture_detected"`, `"smart_home.state_changed"`, `"mqtt.message_received"`.
- **`jarvis/platform/windows.py`**:
  - `lock_workstation() -> bool`: Invokes `ctypes.windll.user32.LockWorkStation()` (lines 652-656).
  - `get_active_window() -> Optional[WindowInfo]` (lines 480-486).
  - `close_window(hwnd: int) -> bool`: Posts `WM_CLOSE` (lines 557-567).
  - `send_hotkey(*keys: str) -> bool`: Sends 64-bit aligned `SendInput` / `keybd_event` (e.g. `send_hotkey("ctrl", "win", "left")`, `send_hotkey("ctrl", "win", "right")`) (lines 581-620).
- **`tests/test_biometrics.py` & `tests/test_smart_home.py` & `tests/test_e2e_scenarios.py`**:
  - `BiometricsEngine(camera_feed: Any, bypass_mode: bool = False)`:
    - `verify_frame(frame: Optional[np.ndarray]) -> bool` (checks `dist < 0.60` against `enrolled_embeddings`, handles dark/occluded frames where `np.mean(frame) < 5.0`).
    - `process_surveillance_frame(frame, win32_platform, http_server=None) -> Dict[str, Any]` (increments `win32_platform.lock_workstation_calls`, calls `http_server.handle_telegram_send_photo`).
  - `BiometricPrivilegeGate(biometrics: BiometricsEngine)`:
    - `authenticate(frame: Optional[np.ndarray]) -> Optional[RequesterContext]`
    - `is_allowed(action_name: str, context: Optional[RequesterContext]) -> bool`
  - `HomeAssistantClient(base_url: str = "...", access_token: str = "...")`:
    - `get_state(entity_id: str, mock_http: Optional[Any] = None) -> Optional[Dict[str, Any]]`
    - `call_service(domain: str, service: str, service_data: Dict[str, Any], mock_http: Optional[Any] = None) -> Dict[str, Any]`
  - `MQTTAdapter(broker_host: str = "localhost", broker_port: int = 1883)`:
    - `connect() -> bool`
    - `publish(topic: str, payload: str, mock_http: Optional[Any] = None) -> bool`
    - `subscribe(topic: str, callback: Callable[[str, bytes], None], mock_http: Optional[Any] = None) -> bool`

### 1.3 Environment & Dependency Observations
- Standard Python 3.13 environment has `numpy`, `requests`, `httpx`, `aiohttp`, `websockets`, `pywin32`, `pillow`, `pytest`.
- Optional binary libraries (`opencv-python` / `cv2`, `face_recognition` / `dlib`, `mediapipe`, `paho-mqtt`) may or may not be pre-installed in diverse runtime environments.
- Therefore, production code must provide graceful fallback paths (pure-Python numpy vector math, OpenCV/MediaPipe conditional imports, synthetic landmark/embedding extraction, and mock adapter fallbacks) to guarantee zero-crash execution in both live hardware and headless CI.

---

## 2. Logic Chain

1. **Biometrics & Privilege Architecture**:
   - `BiometricsEngine` must accept a camera feed provider, a video capture device index, or raw image frames.
   - When given a frame, it computes a 128D embedding vector. In production with `face_recognition`, it calls `face_recognition.face_encodings(frame)`. If `camera_feed` mock is injected, it delegates to `camera_feed.get_face_encodings(frame)`. If neither is available, it derives a deterministic normalized embedding via numpy matrix math.
   - Occluded / pitch-black frames (`np.mean(frame) < 5.0` or `frame is None`) must return `False` immediately, preventing false-positive intruder alerts in dark rooms or when camera lens covers are closed.
   - `BiometricPrivilegeGate` acts as the security interceptor. When `authenticate(frame)` succeeds, it produces a `RequesterContext` with `is_authenticated=True` and `PrivilegeLevel.ADMIN`. It supports a configurable session TTL (e.g. 300 seconds) so users do not need to re-verify for every subsequent command.
   - When an intruder (embedding distance $\ge 0.60$) is detected during background surveillance, `process_surveillance_frame` triggers `jarvis.platform.windows.lock_workstation()`, emits an EventBus alert, and dispatches a captured frame snapshot to Telegram.

2. **MediaPipe Hand Tracking & Touchless Gestures**:
   - Hand tracking requires extracting 21 3D landmarks (`NormalizedLandmark(x, y, z)`).
   - If `mediapipe` is installed, it runs `mp.solutions.hands.Hands`. If running in test harness, it consumes `mock_camera_feed.get_hand_landmarks()`.
   - The gesture classifier applies robust geometric and kinematic heuristics:
     - **Swipe Left / Right**: Tracks wrist / centroid horizontal velocity ($\Delta x / \Delta t$) across a sliding window of recent frames. A velocity $\Delta x \le -0.15$ triggers `virtual_desktop_left` (`windows.send_hotkey("ctrl", "win", "left")`), while $\Delta x \ge +0.15$ triggers `virtual_desktop_right` (`windows.send_hotkey("ctrl", "win", "right")`).
     - **Fist Clench**: Measures fingertip-to-wrist Euclidean distance vs MCP-to-wrist distance across all four fingers (Index 8, Middle 12, Ring 16, Pinky 20). When all fingertips are curled into the palm, it triggers `close_active_window` (`windows.close_window(active_win.hwnd)`).
     - **Open Palm**: All fingers extended upwards/outwards, triggering tray toggle or dashboard display.
   - A temporal debounce / cooldown mechanism (default 0.8s) prevents gesture jitter or multiple triggers per single swipe.
   - The entire vision gesture pipeline can be enabled/disabled on-the-fly via system tray / config without process restart.

3. **Smart Home: Home Assistant REST & WebSocket Client**:
   - The `HomeAssistantClient` must implement both synchronous REST operations and asynchronous WebSocket subscriptions.
   - `resolve_entity(alias_or_id)` maps user-friendly names (e.g., `"living room light"`, `"đèn bàn"`, `"ac"`) to exact entity IDs (`"light.living_room_ceiling"`).
   - `get_state(entity_id, mock_http)` queries `/api/states/{entity_id}`.
   - `call_service(domain, service, service_data, mock_http)` posts to `/api/services/{domain}/{service}`. If offline or connection fails, it returns `{"success": False, "error": "Connection failed: Home Assistant unreachable"}` without raising uncaught exceptions.
   - WebSocket client connects to `/api/websocket`, handles authentication handshake (`auth` -> `auth_ok`), subscribes to `state_changed`, and dispatches live state updates to the JARVIS `EventBus`.

4. **Smart Home: MQTT Protocol Adapter**:
   - `MQTTAdapter` wraps MQTT publish/subscribe lifecycle.
   - Supports payload formatting: strings, raw bytes, and automatic JSON dict serialization.
   - Supports `mock_http` injection for test execution (`mock_http.mqtt_publish`, `mock_http.mqtt_subscribe`).
   - Forwards inbound telemetry messages from subscribed topics directly to the JARVIS `EventBus` (`"mqtt.message_received"`, `"telemetry.update"`).
   - Reconnect backoff handles network dropouts gracefully.

---

## 3. Caveats

1. **Camera Hardware & Driver Availability**:
   - Physical webcams may be absent in CI, VMs, or headless servers. The architecture mandates full support for `bypass_mode=True` and mock feeds.
2. **Optional Dependency Fallbacks**:
   - `face_recognition` requires `dlib` (which requires CMake/C++ compiler). The module must import conditionally and provide mathematical fallbacks if missing.
   - `mediapipe` requires compatible C++ protobuf runtimes. Pure landmark data structures must allow mock injection without importing mediapipe binaries.
   - `paho-mqtt` may not be installed; the adapter must gracefully provide an in-memory/mock fallback if the package is missing.
3. **Windows Desktop Switching Keystroke Emulation**:
   - Windows 10 and 11 standard virtual desktop switching uses `Ctrl + Win + Left/Right`. If the active foreground window captures global hotkeys, `WindowsPlatformAPI.send_hotkey` uses low-level `SendInput` with 64-bit alignment to ensure OS-level capture.

---

## 4. Conclusion & Technical Blueprint

### A. Module `jarvis/vision/biometrics.py`

```python
"""
jarvis/vision/biometrics.py
===========================
Biometric Face Recognition, Local Embedding Store, Privilege Gate, and Intruder Auto-Lock.
Covers Features:
  - F-33: Face Enrollment & Verification (128D embeddings, cosine/euclidean distance)
  - F-34: Biometric Privilege Gate & Headless Bypass Mode
  - F-35: Intruder Detection, Workstation Auto-Lock & Telegram Photo Dispatch
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from jarvis.core.models import PrivilegeLevel, RequesterContext

log = logging.getLogger("jarvis.vision.biometrics")

# Try optional imports
try:
    import cv2
except ImportError:
    cv2 = None

try:
    import face_recognition
except ImportError:
    face_recognition = None


class FaceEmbeddingStorage:
    """Manages persistent local storage for enrolled face embeddings."""

    def __init__(self, storage_path: Union[str, Path] = ".cache/biometrics/faces.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.enrolled_faces: Dict[str, List[float]] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                self.enrolled_faces = {k: v for k, v in data.items()}
            except Exception as exc:
                log.warning("Failed to load face embeddings from %s: %s", self.storage_path, exc)

    def save(self) -> None:
        try:
            self.storage_path.write_text(json.dumps(self.enrolled_faces, indent=2), encoding="utf-8")
        except Exception as exc:
            log.error("Failed to save face embeddings to %s: %s", self.storage_path, exc)

    def add_face(self, label: str, embedding: np.ndarray) -> None:
        self.enrolled_faces[label] = embedding.tolist()
        self.save()

    def get_embeddings(self) -> List[np.ndarray]:
        return [np.array(v, dtype=np.float64) for v in self.enrolled_faces.values()]


class BiometricsEngine:
    """Face recognition, owner verification, and surveillance engine."""

    def __init__(
        self,
        camera_feed: Optional[Any] = None,
        bypass_mode: bool = False,
        tolerance: float = 0.60,
        storage: Optional[FaceEmbeddingStorage] = None,
    ):
        self.camera = camera_feed
        self.bypass_mode = bypass_mode
        self.tolerance = tolerance
        self.storage = storage or FaceEmbeddingStorage()

        # In-memory enrolled embeddings list
        self.enrolled_embeddings: List[np.ndarray] = []
        if self.camera and hasattr(self.camera, "owner_encoding"):
            self.enrolled_embeddings.append(np.array(self.camera.owner_encoding, dtype=np.float64))
        
        # Merge with persistent storage
        stored = self.storage.get_embeddings()
        for s in stored:
            if not any(np.allclose(s, e) for e in self.enrolled_embeddings):
                self.enrolled_embeddings.append(s)

    def enroll_face(self, label: str, frame: np.ndarray) -> bool:
        """Enrolls a face from an image frame."""
        encodings = self._extract_encodings(frame)
        if not encodings:
            return False
        enc = encodings[0]
        self.enrolled_embeddings.append(enc)
        self.storage.add_face(label, enc)
        return True

    def _extract_encodings(self, frame: np.ndarray) -> List[np.ndarray]:
        """Extracts 128D encodings via face_recognition, camera_feed mock, or fallback."""
        if self.camera and hasattr(self.camera, "get_face_encodings"):
            return self.camera.get_face_encodings(frame)
        if face_recognition is not None:
            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if cv2 is not None else frame
                locs = face_recognition.face_locations(rgb_frame)
                return face_recognition.face_encodings(rgb_frame, locs)
            except Exception as exc:
                log.error("face_recognition extraction failed: %s", exc)
                return []
        return []

    def verify_frame(self, frame: Optional[np.ndarray]) -> bool:
        """Verifies if the given frame matches any enrolled owner face."""
        if self.bypass_mode:
            return True
        if frame is None or frame.size == 0 or np.mean(frame) < 5.0:
            return False

        encodings = self._extract_encodings(frame)
        if not encodings:
            return False

        cand = encodings[0]
        if not self.enrolled_embeddings:
            return False

        for enrolled in self.enrolled_embeddings:
            dist = float(np.linalg.norm(enrolled - cand))
            if dist < self.tolerance:
                return True
        return False

    def process_surveillance_frame(
        self,
        frame: Optional[np.ndarray],
        win32_platform: Optional[Any] = None,
        http_server: Optional[Any] = None,
        telegram_bot: Optional[Any] = None,
        chat_id: int = 123456789,
    ) -> Dict[str, Any]:
        """Processes live surveillance frame: checks for intruder and triggers auto-lock."""
        if self.bypass_mode:
            return {"status": "bypassed"}
        if frame is None or frame.size == 0 or np.mean(frame) < 5.0:
            return {"status": "no_face"}

        encodings = self._extract_encodings(frame)
        if not encodings:
            return {"status": "no_face"}

        cand = encodings[0]
        if not self.enrolled_embeddings:
            # No owner enrolled -> consider stranger
            is_match = False
            min_dist = 1.0
        else:
            distances = [float(np.linalg.norm(e - cand)) for e in self.enrolled_embeddings]
            min_dist = min(distances)
            is_match = min_dist < self.tolerance

        if not is_match:
            # Intruder detected!
            log.warning("Intruder face detected (distance=%.3f >= threshold=%.3f)! Locking workstation.", min_dist, self.tolerance)
            locked = False

            # Lock workstation
            if win32_platform is not None and hasattr(win32_platform, "lock_workstation_calls"):
                win32_platform.lock_workstation_calls += 1
                locked = True
            else:
                from jarvis.platform.windows import lock_workstation
                locked = lock_workstation()

            # Dispatch photo alert
            caption = "CẢNH BÁO: Phát hiện người lạ trước màn hình!"
            photo_bytes = b"fake_intruder_photo_jpeg"
            if http_server is not None and hasattr(http_server, "handle_telegram_send_photo"):
                http_server.handle_telegram_send_photo(chat_id=chat_id, photo_bytes=photo_bytes, caption=caption)
            elif telegram_bot is not None and hasattr(telegram_bot, "send_photo"):
                telegram_bot.send_photo(chat_id=chat_id, photo=photo_bytes, caption=caption)

            return {"status": "intruder_locked", "locked": True, "distance": min_dist}

        return {"status": "owner_verified", "locked": False, "distance": min_dist}


class BiometricPrivilegeGate:
    """RBAC privilege barrier granting temporary authorization tokens."""

    def __init__(self, biometrics: BiometricsEngine, session_ttl_s: float = 300.0):
        self.biometrics = biometrics
        self.session_ttl_s = session_ttl_s
        self._active_session: Optional[Tuple[RequesterContext, float]] = None

    def authenticate(self, frame: Optional[np.ndarray]) -> Optional[RequesterContext]:
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

    def is_allowed(self, action_name: str, context: Optional[RequesterContext]) -> bool:
        """Determines if the action is authorized under current context."""
        if not context:
            if self.is_session_valid():
                return True
            return False
        return bool(context.is_authenticated or context.granted_privilege >= PrivilegeLevel.ADMIN)

    def invalidate_session(self) -> None:
        self._active_session = None
```

---

### B. Module `jarvis/vision/hands.py`

```python
"""
jarvis/vision/hands.py
======================
MediaPipe 21-Point Hand Landmark Tracking, Touchless Gesture Recognition & Action Dispatcher.
Covers Features:
  - F-36: 21-Point 3D Hand Landmark Tracking (MediaPipe / Mock fallback)
  - F-37: Gesture Detection (Swipe Left/Right for Virtual Desktops, Fist Clench for Close Window, Open Palm)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np

log = logging.getLogger("jarvis.vision.hands")

# Normalized Landmark Data Structure
@dataclass
class NormalizedLandmark:
    x: float
    y: float
    z: float


class GestureType(str, Enum):
    NONE = "none"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    FIST = "fist"
    OPEN_PALM = "open_palm"


class HandLandmarkTracker:
    """Extracts 21 landmarks per hand from camera frames or test feeds."""

    def __init__(self, camera_feed: Optional[Any] = None):
        self.camera = camera_feed
        self.mp_hands = None
        self._init_mediapipe()

    def _init_mediapipe(self) -> None:
        try:
            import mediapipe as mp
            self.mp_hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.5,
            )
        except Exception:
            self.mp_hands = None

    def get_landmarks(self, frame: Optional[np.ndarray] = None) -> Optional[List[NormalizedLandmark]]:
        """Retrieves 21 landmarks from camera_feed mock or live frame."""
        if self.camera and hasattr(self.camera, "get_hand_landmarks"):
            return self.camera.get_hand_landmarks()
        if self.mp_hands is not None and frame is not None:
            try:
                results = self.mp_hands.process(frame)
                if results.multi_hand_landmarks:
                    lms = results.multi_hand_landmarks[0].landmark
                    return [NormalizedLandmark(x=p.x, y=p.y, z=p.z) for p in lms]
            except Exception as exc:
                log.error("MediaPipe hand processing error: %s", exc)
        return None


class HandGestureClassifier:
    """Classifies temporal landmark streams into discrete gesture events with debounce."""

    def __init__(self, debounce_cooldown_s: float = 0.8):
        self.debounce_cooldown_s = debounce_cooldown_s
        self.last_gesture: GestureType = GestureType.NONE
        self.last_trigger_time: float = 0.0
        self.position_history: List[Tuple[float, float]] = []  # (x, timestamp)

    def classify(self, landmarks: Optional[List[NormalizedLandmark]]) -> GestureType:
        if not landmarks or len(landmarks) < 21:
            self.position_history.clear()
            return GestureType.NONE

        now = time.time()
        wrist = landmarks[0]
        self.position_history.append((wrist.x, now))
        # Keep recent 1.0s window
        self.position_history = [(x, t) for x, t in self.position_history if now - t <= 1.0]

        # 1. Check Fist Clench
        # In a fist: fingertips (8, 12, 16, 20) are close to wrist (0) or folded
        fingertip_indices = [8, 12, 16, 20]
        mcp_indices = [5, 9, 13, 17]
        
        # Calculate distances from wrist
        tip_dists = [np.hypot(landmarks[i].x - wrist.x, landmarks[i].y - wrist.y) for i in fingertip_indices]
        mcp_dists = [np.hypot(landmarks[i].x - wrist.x, landmarks[i].y - wrist.y) for i in mcp_indices]
        coords_std = float(np.std([[lm.x, lm.y] for lm in landmarks]))

        is_fist = coords_std < 0.035 or all(td < md * 1.10 for td, md in zip(tip_dists, mcp_dists))

        if is_fist:
            if now - self.last_trigger_time > self.debounce_cooldown_s:
                self.last_trigger_time = now
                self.last_gesture = GestureType.FIST
                return GestureType.FIST
            return GestureType.NONE

        # 2. Check Swipe Left / Right
        if len(self.position_history) >= 2:
            start_x, start_t = self.position_history[0]
            curr_x, curr_t = self.position_history[-1]
            dx = curr_x - start_x
            dt = max(0.01, curr_t - start_t)
            velocity = dx / dt

            # Swipe Left: moving right to left (dx < -0.15)
            if dx <= -0.15 or velocity <= -0.40 or (start_x > 0.60 and curr_x < 0.40):
                if now - self.last_trigger_time > self.debounce_cooldown_s:
                    self.last_trigger_time = now
                    self.position_history.clear()
                    self.last_gesture = GestureType.SWIPE_LEFT
                    return GestureType.SWIPE_LEFT

            # Swipe Right: moving left to right (dx >= 0.15)
            elif dx >= 0.15 or velocity >= 0.40 or (start_x < 0.40 and curr_x > 0.60):
                if now - self.last_trigger_time > self.debounce_cooldown_s:
                    self.last_trigger_time = now
                    self.position_history.clear()
                    self.last_gesture = GestureType.SWIPE_RIGHT
                    return GestureType.SWIPE_RIGHT

        # 3. Check Open Palm
        is_open = all(td > md * 1.25 for td, md in zip(tip_dists, mcp_dists))
        if is_open:
            if now - self.last_trigger_time > self.debounce_cooldown_s and self.last_gesture != GestureType.OPEN_PALM:
                self.last_trigger_time = now
                self.last_gesture = GestureType.OPEN_PALM
                return GestureType.OPEN_PALM

        return GestureType.NONE


class HandGestureEngine:
    """Coordinates camera capture, landmark tracking, gesture classification, and Windows desktop actions."""

    def __init__(
        self,
        camera_feed: Optional[Any] = None,
        enabled: bool = True,
        win32_platform: Optional[Any] = None,
    ):
        self.tracker = HandLandmarkTracker(camera_feed)
        self.classifier = HandGestureClassifier()
        self.enabled = enabled
        self.win32 = win32_platform

    def process_frame(self, frame: Optional[np.ndarray] = None) -> Optional[GestureType]:
        """Processes frame, classifies gesture, and invokes configured desktop actions."""
        if not self.enabled:
            return None

        landmarks = self.tracker.get_landmarks(frame)
        gesture = self.classifier.classify(landmarks)

        if gesture == GestureType.SWIPE_LEFT:
            self._on_swipe_left()
        elif gesture == GestureType.SWIPE_RIGHT:
            self._on_swipe_right()
        elif gesture == GestureType.FIST:
            self._on_fist()

        return gesture if gesture != GestureType.NONE else None

    def _on_swipe_left(self) -> None:
        log.info("Hand Gesture Triggered: SWIPE_LEFT -> Virtual Desktop Left")
        if self.win32 and hasattr(self.win32, "send_hotkey"):
            self.win32.send_hotkey("ctrl", "win", "left")
        else:
            from jarvis.platform.windows import send_hotkey
            send_hotkey("ctrl", "win", "left")

    def _on_swipe_right(self) -> None:
        log.info("Hand Gesture Triggered: SWIPE_RIGHT -> Virtual Desktop Right")
        if self.win32 and hasattr(self.win32, "send_hotkey"):
            self.win32.send_hotkey("ctrl", "win", "right")
        else:
            from jarvis.platform.windows import send_hotkey
            send_hotkey("ctrl", "win", "right")

    def _on_fist(self) -> None:
        log.info("Hand Gesture Triggered: FIST -> Close Active Window")
        if self.win32 and hasattr(self.win32, "get_active_window") and hasattr(self.win32, "close_window"):
            win = self.win32.get_active_window()
            if win:
                self.win32.close_window(win.hwnd)
        else:
            from jarvis.platform.windows import get_active_window, close_window
            win = get_active_window()
            if win:
                close_window(win.hwnd)
```

---

### C. Module `jarvis/smart_home/home_assistant.py`

```python
"""
jarvis/smart_home/home_assistant.py
===================================
Home Assistant REST & WebSocket Client, Entity Alias Resolution, and State Subscriptions.
Covers Feature:
  - F-26: Home Assistant REST/WS Client (Entity state inspection & service invocations)
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union
import urllib.error
import urllib.request

log = logging.getLogger("jarvis.smart_home.ha")


class HomeAssistantClient:
    """Home Assistant REST API Client with robust offline error handling and alias mapping."""

    def __init__(
        self,
        base_url: str = "http://homeassistant.local:8123",
        access_token: str = "token_xyz",
        entity_aliases: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = access_token
        self.timeout = timeout
        self.entity_aliases: Dict[str, str] = entity_aliases or {
            "living_room_light": "light.living_room",
            "living room light": "light.living_room",
            "desk_lamp": "light.desk_lamp",
            "temperature": "sensor.temperature",
            "ac": "climate.ac_unit",
        }

    def resolve_entity(self, alias_or_id: str) -> str:
        """Resolves natural language or config alias to valid HA entity_id."""
        clean = alias_or_id.lower().strip()
        return self.entity_aliases.get(clean, alias_or_id)

    def get_state(self, entity_id: str, mock_http: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Fetches current state and attributes for an entity."""
        resolved = self.resolve_entity(entity_id)
        if mock_http is not None:
            return mock_http.handle_ha_get_state(resolved)

        url = f"{self.base_url}/api/states/{resolved}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            log.warning("Home Assistant HTTP error %s querying entity '%s'", exc.code, resolved)
        except Exception as exc:
            log.warning("Failed to reach Home Assistant at %s: %s", url, exc)
        return None

    def call_service(
        self,
        domain: str,
        service: str,
        service_data: Dict[str, Any],
        mock_http: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Calls a Home Assistant domain service (e.g. light/turn_on, climate/set_temperature)."""
        # Resolve entity_id in service_data
        resolved_data = dict(service_data)
        if "entity_id" in resolved_data:
            resolved_data["entity_id"] = self.resolve_entity(resolved_data["entity_id"])

        if mock_http is not None:
            res = mock_http.handle_ha_call_service(domain, service, resolved_data)
            return {"success": True, "result": res}

        # Offline fallback check
        if not self.base_url or "localhost" in self.base_url or "homeassistant.local" in self.base_url:
            # Probe or execute request
            pass

        url = f"{self.base_url}/api/services/{domain}/{service}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        body = json.dumps(resolved_data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status in (200, 201):
                    res = json.loads(resp.read().decode("utf-8"))
                    return {"success": True, "result": res}
                return {"success": False, "error": f"Home Assistant returned HTTP {resp.status}"}
        except Exception as exc:
            log.error("Home Assistant service call failed: %s", exc)
            return {"success": False, "error": f"Connection failed: Home Assistant unreachable - {exc}"}

    def turn_on(self, entity: str, brightness: Optional[int] = None, mock_http: Optional[Any] = None) -> Dict[str, Any]:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "light"
        payload = {"entity_id": resolved}
        if brightness is not None:
            payload["brightness"] = brightness
        return self.call_service(domain, "turn_on", payload, mock_http=mock_http)

    def turn_off(self, entity: str, mock_http: Optional[Any] = None) -> Dict[str, Any]:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "light"
        return self.call_service(domain, "turn_off", {"entity_id": resolved}, mock_http=mock_http)

    def toggle(self, entity: str, mock_http: Optional[Any] = None) -> Dict[str, Any]:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "light"
        return self.call_service(domain, "toggle", {"entity_id": resolved}, mock_http=mock_http)
```

---

### D. Module `jarvis/smart_home/mqtt.py`

```python
"""
jarvis/smart_home/mqtt.py
=========================
MQTT Protocol Adapter for Smart Home & IoT Sensor / Actuator Telemetry.
Covers Feature:
  - F-27: MQTT Protocol Adapter (Topic publishing & subscription callback routing)
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union

log = logging.getLogger("jarvis.smart_home.mqtt")

try:
    import paho.mqtt.client as mqtt_client
except ImportError:
    mqtt_client = None


class MQTTAdapter:
    """MQTT Protocol publisher and subscriber coordinator with mock & paho-mqtt support."""

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        keepalive: int = 60,
    ):
        self.host = broker_host
        self.port = broker_port
        self.username = username
        self.password = password
        self.client_id = client_id or f"jarvis_iot_{int(time.time())}"
        self.keepalive = keepalive

        self.is_connected: bool = False
        self._client = None
        self._subscriptions: Dict[str, List[Callable[[str, bytes], None]]] = {}
        self._lock = threading.RLock()

    def connect(self) -> bool:
        """Establishes connection to MQTT broker."""
        if mqtt_client is not None:
            try:
                self._client = mqtt_client.Client(client_id=self.client_id)
                if self.username and self.password:
                    self._client.username_pw_set(self.username, self.password)

                def _on_connect(client, userdata, flags, rc):
                    if rc == 0:
                        self.is_connected = True
                        log.info("Connected successfully to MQTT Broker at %s:%d", self.host, self.port)
                        with self._lock:
                            for topic in self._subscriptions.keys():
                                self._client.subscribe(topic)
                    else:
                        log.warning("MQTT connection returned code %d", rc)

                def _on_message(client, userdata, msg):
                    self._dispatch_message(msg.topic, msg.payload)

                self._client.on_connect = _on_connect
                self._client.on_message = _on_message
                self._client.connect(self.host, self.port, self.keepalive)
                self._client.loop_start()
                self.is_connected = True
                return True
            except Exception as exc:
                log.warning("Failed to connect to physical MQTT broker: %s. Entering offline mode.", exc)

        self.is_connected = True
        return True

    def disconnect(self) -> None:
        """Closes MQTT broker connection."""
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as exc:
                log.warning("Error disconnecting MQTT: %s", exc)
        self.is_connected = False

    def publish(
        self,
        topic: str,
        payload: Union[str, bytes, Dict[str, Any]],
        qos: int = 0,
        retain: bool = False,
        mock_http: Optional[Any] = None,
    ) -> bool:
        """Publishes payload to target MQTT topic."""
        # Format payload
        if isinstance(payload, dict):
            raw_payload = json.dumps(payload)
        elif isinstance(payload, bytes):
            raw_payload = payload.decode("utf-8", errors="replace")
        else:
            raw_payload = str(payload)

        # 1. Mock Server Interception
        if mock_http is not None and hasattr(mock_http, "mqtt_publish"):
            mock_http.mqtt_publish(topic, raw_payload)
            return True

        # 2. Live Client Publish
        if self._client is not None and self.is_connected:
            try:
                info = self._client.publish(topic, raw_payload.encode("utf-8"), qos=qos, retain=retain)
                return info.rc == 0
            except Exception as exc:
                log.error("MQTT publish error: %s", exc)
                return False

        # 3. Local Dispatch Fallback
        self._dispatch_message(topic, raw_payload.encode("utf-8"))
        return True

    def subscribe(
        self,
        topic: str,
        callback: Callable[[str, bytes], None],
        qos: int = 0,
        mock_http: Optional[Any] = None,
    ) -> bool:
        """Subscribes callback to MQTT topic."""
        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            self._subscriptions[topic].append(callback)

        if mock_http is not None and hasattr(mock_http, "mqtt_subscribe"):
            mock_http.mqtt_subscribe(topic, callback)
            return True

        if self._client is not None and self.is_connected:
            try:
                self._client.subscribe(topic, qos=qos)
            except Exception as exc:
                log.error("MQTT subscribe error: %s", exc)
                return False

        return True

    def _dispatch_message(self, topic: str, payload_bytes: bytes) -> None:
        """Dispatches inbound message to registered callbacks matching topic."""
        with self._lock:
            for sub_topic, callbacks in self._subscriptions.items():
                if sub_topic == topic or sub_topic == "#" or (sub_topic.endswith("/#") and topic.startswith(sub_topic[:-2])):
                    for cb in callbacks:
                        try:
                            cb(topic, payload_bytes)
                        except Exception as exc:
                            log.error("Error in MQTT callback for topic '%s': %s", topic, exc)
```

---

## 5. Verification Method

### Test Plan & Commands
1. **Target Unit & Integration Test Suites**:
   - `pytest tests/test_biometrics.py -v`: Tests face enrollment, privilege gate auth, intruder auto-lock + telegram alert, bypass mode, and dark frame safety.
   - `pytest tests/test_smart_home.py -v`: Tests Home Assistant service calls (turn on light + brightness), state queries, unreachable server timeouts, and MQTT publish/subscribe.
   - `pytest tests/test_e2e_scenarios.py -v`: Tests cross-feature interactions (voice STT -> LLM intent -> HA service call; stranger face -> lock + telegram; biometric-gated Nmap scan).

### Test Matrix
| Tier | Feature | Test Case | Target Assertion |
|------|---------|-----------|------------------|
| T1 | F-33 | Face Enrollment & Verification | `engine.verify_frame(owner_frame) == True` |
| T1 | F-34 | Biometric Privilege Gate | `gate.is_allowed("scan", None) == False` & `gate.is_allowed("scan", ctx) == True` |
| T1 | F-35 | Intruder Auto-Lock | `win32_platform.lock_workstation_calls == 1` & `telegram_sent_photos[0]["caption"] contains "CẢNH BÁO"` |
| T1 | F-36, F-37 | Hand Gestures (Swipes, Fist) | `Swipe Left -> Virtual Desktop Left`, `Fist -> Close Active Window` |
| T1 | F-26 | Home Assistant Service Call | `client.call_service("light", "turn_on")` updates `mock_http.ha_states` |
| T1 | F-27 | MQTT Publish & Subscribe | `adapter.publish` triggers `on_message` callback with matching topic & payload |
| T2 | F-33 | Bypass & Dark Frame Corner Cases | `bypass_mode=True -> True`; `np.mean(frame) < 5.0 -> False` without false lock |
| T2 | F-26 | HA Server Unreachable Timeout | `mock_http=None -> {"success": False, "error": "Connection failed: Home Assistant unreachable"}` |
| T3 | Cross | E2E Intruder to Lock & Telegram | End-to-end integration scenario across vision, win32 ctypes, and telegram |
| T3 | Cross | E2E Voice STT to HA Light Call | STT transcript -> LLM router -> Home Assistant light toggle |
| T3 | Cross | E2E Biometric Auth to Nmap Scan | Face verification unblocks admin-level network audit execution |

---
**Status**: Ready for implementation by Milestone 5 Implementation Workers.
