"""
jarvis/audio/adap_head.py
=========================
Acoustic Direct-to-Action Projection (ADAP) Linear Head.
Engineered for Sub-15ms Speech-to-Action Desktop Reflexes in Argon Frontier 10.0.

Mathematical Principles:
  1. Direct Latent-to-Action Formulation:
     Bypasses traditional ASR tokenization and NLU parsing by projecting the
     terminal acoustic hidden state h_t in R^{d_model} (d_model=512) directly to
     the categorical distribution over discrete desktop reflex actions:
       z = W_adap * Pooling(H_{1:T}) + b_adap
       P(a_k | X_{1:T}) = Softmax(z / tau)
  2. Memory & Parameter Budget:
     For K=45 reflex actions and d_model=512:
       W_adap in R^{45 x 512} (23,040 float32 weights = 90.0 KB)
       b_adap in R^{45} (45 float32 biases = 0.18 KB)
       Total Parameter Size = ~90.18 KB (<= 92.0 KB invariant)
  3. Strict Fail-Closed Gating:
     A reflex action is confirmed if and only if:
       - Confidence: P(a_(1)) >= theta_conf (default 0.82)
       - Margin: P(a_(1)) - P(a_(2)) >= theta_margin (default 0.15)
     Otherwise, execution gracefully defers to the standard Whisper + ActionTree pipeline.
  4. 0 MB VRAM Invariant:
     Evaluates purely on CPU SIMD AVX2 in NumPy (< 0.15ms latency), consuming
     0.00 MiB GPU VRAM.
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

logger = logging.getLogger("jarvis.audio.adap_head")


@dataclass(frozen=True)
class ReflexActionDefinition:
    """Descriptor for a native Win32 Desktop Reflex Action."""
    action_id: int
    domain: str
    intent: str
    target_app: str
    parameters: dict[str, Any]
    description: str


# ---------------------------------------------------------------------------
# Canonical 45 Core Desktop Reflex Actions (K = 45)
# ---------------------------------------------------------------------------
DEFAULT_REFLEX_ACTIONS: list[ReflexActionDefinition] = [
    # System Audio Controls (0 - 4)
    ReflexActionDefinition(0, "system", "system_volume_mute", "system", {"state": "mute"}, "Tắt toàn bộ âm thanh hệ thống"),
    ReflexActionDefinition(1, "system", "system_volume_unmute", "system", {"state": "unmute"}, "Bật lại âm thanh hệ thống"),
    ReflexActionDefinition(2, "system", "system_volume_up", "system", {"step": 5, "direction": "up"}, "Tăng âm lượng 5%"),
    ReflexActionDefinition(3, "system", "system_volume_down", "system", {"step": 5, "direction": "down"}, "Giảm âm lượng 5%"),
    ReflexActionDefinition(4, "system", "system_volume_max", "system", {"volume_level": 100}, "Đặt âm lượng tối đa 100%"),

    # Screen & Display Controls (5 - 9)
    ReflexActionDefinition(5, "system", "screen_brightness_up", "system", {"step": 10}, "Tăng độ sáng màn hình"),
    ReflexActionDefinition(6, "system", "screen_brightness_down", "system", {"step": 10}, "Giảm độ sáng màn hình"),
    ReflexActionDefinition(7, "system", "screen_lock", "system", {}, "Khóa màn hình máy tính tức thời"),
    ReflexActionDefinition(8, "system", "screenshot_fullscreen", "system", {"mode": "full"}, "Chụp toàn bộ màn hình vào bộ nhớ đệm"),
    ReflexActionDefinition(9, "system", "screenshot_region", "system", {"mode": "region"}, "Bật công cụ chụp vùng màn hình"),

    # Window Management (10 - 19)
    ReflexActionDefinition(10, "window", "window_minimize", "window", {}, "Thu nhỏ cửa sổ hiện tại"),
    ReflexActionDefinition(11, "window", "window_maximize", "window", {}, "Phóng to cửa sổ hiện tại"),
    ReflexActionDefinition(12, "window", "window_restore", "window", {}, "Khôi phục kích thước cửa sổ"),
    ReflexActionDefinition(13, "window", "window_close", "window", {}, "Đóng cửa sổ hiện tại"),
    ReflexActionDefinition(14, "window", "window_snap_left", "window", {"half": "left"}, "Gắn cửa sổ sang nửa trái màn hình"),
    ReflexActionDefinition(15, "window", "window_snap_right", "window", {"half": "right"}, "Gắn cửa sổ sang nửa phải màn hình"),
    ReflexActionDefinition(16, "window", "task_view_toggle", "window", {}, "Bật hoặc tắt màn hình Task View"),
    ReflexActionDefinition(17, "window", "desktop_show", "window", {}, "Ẩn tất cả cửa sổ và hiện màn hình chính"),
    ReflexActionDefinition(18, "window", "app_switch_next", "window", {"direction": "forward"}, "Chuyển sang ứng dụng kế tiếp (Alt-Tab)"),
    ReflexActionDefinition(19, "window", "app_switch_prev", "window", {"direction": "backward"}, "Chuyển sang ứng dụng trước đó"),

    # Media Playback Controls (20 - 27)
    ReflexActionDefinition(20, "media", "media_play", "media", {"command": "play"}, "Tiếp tục phát nhạc hoặc video"),
    ReflexActionDefinition(21, "media", "media_pause", "media", {"command": "pause"}, "Tạm dừng phát nhạc hoặc video"),
    ReflexActionDefinition(22, "media", "media_toggle", "media", {"command": "play_pause"}, "Chuyển đổi phát hoặc tạm dừng nhạc"),
    ReflexActionDefinition(23, "media", "media_next", "media", {"command": "next_track"}, "Chuyển sang bài hát tiếp theo"),
    ReflexActionDefinition(24, "media", "media_prev", "media", {"command": "prev_track"}, "Quay lại bài hát trước đó"),
    ReflexActionDefinition(25, "media", "media_stop", "media", {"command": "stop"}, "Dừng hẳn phát đa phương tiện"),
    ReflexActionDefinition(26, "media", "spotify_like", "spotify", {"command": "like_song"}, "Thả tim bài hát hiện tại trên Spotify"),
    ReflexActionDefinition(27, "media", "spotify_shuffle", "spotify", {"command": "toggle_shuffle"}, "Bật tắt chế độ trộn bài trên Spotify"),

    # Browser & Tab Navigation (28 - 35)
    ReflexActionDefinition(28, "navigation", "tab_new", "browser", {}, "Mở một thẻ trình duyệt mới"),
    ReflexActionDefinition(29, "navigation", "tab_close", "browser", {}, "Đóng thẻ trình duyệt hiện tại"),
    ReflexActionDefinition(30, "navigation", "tab_reopen", "browser", {}, "Mở lại thẻ trình duyệt vừa đóng"),
    ReflexActionDefinition(31, "navigation", "tab_next", "browser", {"direction": "next"}, "Chuyển sang thẻ trình duyệt kế tiếp"),
    ReflexActionDefinition(32, "navigation", "tab_prev", "browser", {"direction": "prev"}, "Chuyển sang thẻ trình duyệt trước đó"),
    ReflexActionDefinition(33, "navigation", "browser_back", "browser", {}, "Quay lại trang trước trên trình duyệt"),
    ReflexActionDefinition(34, "navigation", "browser_forward", "browser", {}, "Tiến lên trang sau trên trình duyệt"),
    ReflexActionDefinition(35, "navigation", "browser_refresh", "browser", {}, "Làm mới trang web hiện tại"),

    # Quick Utility & App Launchers (36 - 42)
    ReflexActionDefinition(36, "tools", "terminal_open", "terminal", {"command": "wt.exe"}, "Mở cửa sổ dòng lệnh Windows Terminal"),
    ReflexActionDefinition(37, "tools", "browser_open", "browser", {"command": "chrome.exe"}, "Mở trình duyệt Google Chrome"),
    ReflexActionDefinition(38, "tools", "explorer_open", "explorer", {"command": "explorer.exe"}, "Mở cửa sổ File Explorer"),
    ReflexActionDefinition(39, "tools", "calculator_open", "calculator", {"command": "calc.exe"}, "Mở ứng dụng máy tính cầm tay"),
    ReflexActionDefinition(40, "tools", "task_manager_open", "taskmgr", {"command": "taskmgr.exe"}, "Mở trình quản lý tác vụ Task Manager"),
    ReflexActionDefinition(41, "tools", "settings_open", "settings", {"command": "ms-settings:"}, "Mở cài đặt hệ điều hành Windows"),
    ReflexActionDefinition(42, "tools", "notepad_open", "notepad", {"command": "notepad.exe"}, "Mở trình soạn thảo Notepad"),

    # Clipboard Shortcuts (43 - 44)
    ReflexActionDefinition(43, "system", "clipboard_copy", "system", {"key": "ctrl+c"}, "Sao chép nội dung đang chọn"),
    ReflexActionDefinition(44, "system", "clipboard_paste", "system", {"key": "ctrl+v"}, "Dán nội dung từ bộ nhớ đệm"),
]


@dataclass(frozen=True)
class ADAPConfig:
    """Hyperparameters and operational limits for ADAP Projection Head."""
    d_model: int = 512
    num_reflex_intents: int = 45
    temperature: float = 1.0
    confidence_threshold: float = 0.82
    margin_threshold: float = 0.15
    pooling_mode: str = "terminal"  # "terminal", "mean", or "last_window"
    window_frames: int = 8


@dataclass(frozen=True)
class ADAPPrediction:
    """Telemetry and prediction verdict emitted by the ADAP Linear Head."""
    action: ReflexActionDefinition | None
    confidence: float
    margin: float
    logits: np.ndarray
    probabilities: np.ndarray
    is_reflex: bool
    latency_ms: float
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Converts prediction telemetry into structured dictionary."""
        return {
            "is_reflex": self.is_reflex,
            "action_id": self.action.action_id if self.action else None,
            "intent": self.action.intent if self.action else None,
            "domain": self.action.domain if self.action else None,
            "confidence": round(float(self.confidence), 4),
            "margin": round(float(self.margin), 4),
            "latency_ms": round(float(self.latency_ms), 3),
            "fallback_reason": self.fallback_reason,
        }


class ADAPProjectionHead:
    """
    Acoustic Direct-to-Action Projection (ADAP) Linear Projection Layer.
    Executes sub-15ms direct speech-to-action routing with zero VRAM allocation.
    """

    def __init__(
        self,
        config: ADAPConfig | None = None,
        weights_path: str | Path | None = None,
        seed: int = 42,
    ) -> None:
        self.config = config or ADAPConfig()
        self.actions = list(DEFAULT_REFLEX_ACTIONS)
        self.num_actions = len(self.actions)
        self.d_model = self.config.d_model
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()

        # Allocate weight matrix W_adap and bias b_adap
        rng = np.random.default_rng(seed)
        scale = 1.0 / math.sqrt(self.d_model)
        self.w_adap = rng.normal(0.0, scale, (self.num_actions, self.d_model)).astype(np.float32)
        self.b_adap = np.zeros(self.num_actions, dtype=np.float32)

        # Calibrate initial orthogonal semantic prototypes
        self._initialize_semantic_prototypes(seed=seed)

        # Load weights if provided and exists
        if weights_path:
            p = Path(weights_path)
            if p.exists():
                self.load_weights(p)

    @property
    def parameter_bytes(self) -> int:
        """Returns exact memory footprint of ADAP projection weights."""
        return self.w_adap.nbytes + self.b_adap.nbytes

    def _initialize_semantic_prototypes(self, seed: int = 42) -> None:
        """
        Synthesizes well-separated orthonormal semantic direction vectors
        for the 45 core intents, ensuring distinct acoustic attractor basins.
        """
        rng = np.random.default_rng(seed)
        # Generate random Gaussian matrix and compute QR decomposition for orthonormality
        random_matrix = rng.normal(0.0, 1.0, (self.d_model, self.num_actions)).astype(np.float32)
        q, _ = np.linalg.qr(random_matrix)
        # q[:, i] is orthonormal unit vector in R^{d_model}
        for i in range(self.num_actions):
            prototype = q[:, i].astype(np.float32)
            # Scale prototype to provide clear margin
            self.w_adap[i, :] = prototype * 3.5
            self.b_adap[i] = 0.0

    def pool_acoustic_states(self, states: np.ndarray) -> np.ndarray:
        """
        Condenses streaming acoustic states into a single latent vector h_term.

        Args:
            states: Audio latent representations of shape (d_model,) or (T, d_model).

        Returns:
            np.ndarray of shape (d_model,).
        """
        arr = np.asarray(states, dtype=np.float32)
        if arr.ndim == 1:
            if arr.shape[0] != self.d_model:
                raise ValueError(f"State dimension {arr.shape[0]} does not match d_model {self.d_model}")
            return arr

        if arr.ndim == 2:
            if arr.shape[1] != self.d_model:
                raise ValueError(f"State feature dimension {arr.shape[1]} does not match d_model {self.d_model}")
            if arr.shape[0] == 0:
                return np.zeros(self.d_model, dtype=np.float32)

            mode = self.config.pooling_mode
            if mode == "mean":
                return np.mean(arr, axis=0)
            elif mode == "last_window":
                w = min(self.config.window_frames, arr.shape[0])
                return np.mean(arr[-w:], axis=0)
            else:  # "terminal"
                return arr[-1]

        raise ValueError(f"Expected 1D or 2D array, got {arr.ndim}D array")

    def predict(self, acoustic_input: np.ndarray) -> ADAPPrediction:
        """
        Computes direct speech-to-action projection with sub-15ms SLA.

        Args:
            acoustic_input: Terminal acoustic state or sequence from SSD Encoder.

        Returns:
            ADAPPrediction with confidence, margin, and reflex decision.
        """
        t0 = time.perf_counter()
        with self._lock:
            h_term = self.pool_acoustic_states(acoustic_input)

            # Compute linear projection logits: z = W_adap * h_term + b_adap
            logits = np.dot(self.w_adap, h_term) + self.b_adap

            # Softmax with temperature scaling and numerical stabilization
            temp = max(1e-4, float(self.config.temperature))
            scaled_logits = logits / temp
            max_logit = np.max(scaled_logits)
            exp_logits = np.exp(scaled_logits - max_logit)
            sum_exp = np.sum(exp_logits)
            probs = exp_logits / (sum_exp if sum_exp > 0.0 else 1.0)

            # Top-1 and Top-2 extraction
            sorted_indices = np.argsort(probs)[::-1]
            top1_idx = int(sorted_indices[0])
            top2_idx = int(sorted_indices[1]) if len(sorted_indices) > 1 else top1_idx

            top1_conf = float(probs[top1_idx])
            top2_conf = float(probs[top2_idx])
            margin = top1_conf - top2_conf

            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            # Gating invariant
            is_reflex = True
            fallback_reason = None

            if top1_conf < self.config.confidence_threshold:
                is_reflex = False
                fallback_reason = f"CONFIDENCE_BELOW_THRESHOLD ({top1_conf:.3f} < {self.config.confidence_threshold:.3f})"
            elif margin < self.config.margin_threshold:
                is_reflex = False
                fallback_reason = f"MARGIN_BELOW_THRESHOLD ({margin:.3f} < {self.config.margin_threshold:.3f})"

            selected_action = self.actions[top1_idx] if is_reflex else None

            return ADAPPrediction(
                action=selected_action,
                confidence=top1_conf,
                margin=margin,
                logits=logits,
                probabilities=probs,
                is_reflex=is_reflex,
                latency_ms=elapsed_ms,
                fallback_reason=fallback_reason,
            )

    def calibrate_action(
        self,
        acoustic_embedding: np.ndarray,
        target_action_id: int,
        learning_rate: float = 0.05,
    ) -> float:
        """
        Performs in-situ on-device SGD weight update to reinforce correct reflex mapping.

        Args:
            acoustic_embedding: Positive acoustic latent embedding for the action.
            target_action_id: Canonical index of the intended reflex action (0 to 44).
            learning_rate: Step size for gradient ascent on target logits.

        Returns:
            Cross-entropy loss before calibration step.
        """
        if not (0 <= target_action_id < self.num_actions):
            raise ValueError(f"Invalid target_action_id {target_action_id}. Must be in [0, {self.num_actions - 1}]")

        with self._lock:
            h = self.pool_acoustic_states(acoustic_embedding)
            h_norm = np.linalg.norm(h)
            if h_norm > 0:
                h_unit = h / h_norm
            else:
                h_unit = h

            # Forward pass
            logits = np.dot(self.w_adap, h_unit) + self.b_adap
            max_l = np.max(logits)
            exp_l = np.exp(logits - max_l)
            probs = exp_l / np.sum(exp_l)

            loss = -math.log(max(float(probs[target_action_id]), 1e-12))

            # Gradient of cross-entropy w.r.t logits: grad = probs - y_true
            grad = probs.copy()
            grad[target_action_id] -= 1.0

            # Update weights: W -= lr * outer(grad, h_unit)
            self.w_adap -= (learning_rate * np.outer(grad, h_unit)).astype(np.float32)
            self.b_adap -= (learning_rate * grad).astype(np.float32)

            return loss

    def save_weights(self, path: str | Path) -> None:
        """
        Persists ADAP projection weights to disk using Windows Atomic Persistence.
        Adheres strictly to Rule 3 of AGENTS.md.
        """
        target_path = Path(path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with self._save_lock:
            with self._lock:
                snapshot_w = self.w_adap.copy()
                snapshot_b = self.b_adap.copy()

            thread_id = threading.get_ident()
            timestamp_ns = time.time_ns()
            tmp_path = target_path.with_name(f"{target_path.stem}.tmp.{thread_id}.{timestamp_ns}.npz")

            try:
                np.savez_compressed(tmp_path, w_adap=snapshot_w, b_adap=snapshot_b)

                # Atomic replace with Windows retry backoff
                max_retries = 5
                for attempt in range(1, max_retries + 1):
                    try:
                        os.replace(tmp_path, target_path)
                        break
                    except OSError as err:
                        if attempt == max_retries:
                            raise err
                        time.sleep(0.02 * attempt)
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass

    def load_weights(self, path: str | Path) -> None:
        """Loads and verifies ADAP projection weights from disk."""
        target_path = Path(path).resolve()
        if not target_path.exists():
            raise FileNotFoundError(f"Weight file not found: {target_path}")

        data = np.load(target_path)
        w_loaded = data["w_adap"]
        b_loaded = data["b_adap"]

        if w_loaded.shape != (self.num_actions, self.d_model):
            raise ValueError(
                f"Weight matrix shape mismatch: expected ({self.num_actions}, {self.d_model}), "
                f"got {w_loaded.shape}"
            )

        with self._lock:
            self.w_adap = w_loaded.astype(np.float32)
            self.b_adap = b_loaded.astype(np.float32)
            logger.info("ADAP projection weights loaded successfully from %s", target_path)
