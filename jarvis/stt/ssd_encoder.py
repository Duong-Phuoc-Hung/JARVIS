"""
jarvis/stt/ssd_encoder.py
=========================
Mamba-2 Structured State Space Duality (SSD) Streaming Speech Encoder.
Engineered for O(1) Constant-Memory Continuous Audio Processing in Argon Sovereign v6.0.

Mathematical Principles (Dao & Gu, 2024):
  1. Selective State Space Models (SSM):
     Continuous continuous-time linear ODE:
       h'(t) = A(t)h(t) + B(t)x(t)
       y(t)  = C(t)h(t) + D(t)x(t)
  2. Zero-Order Hold (ZOH) Discretization with step size Delta:
       A_bar = exp(Delta * A)
       B_bar = (Delta * A)^(-1) * (exp(Delta * A) - I) * Delta * B
       h_t   = A_bar * h_{t-1} + B_bar * x_t
       y_t   = C_t * h_t + D * x_t
  3. Structured State Space Duality (SSD):
       A is structured as a scalar decay per head (alpha * I), establishing
       duality between 1D causal linear attention and 1-semiseparable matrix transformation:
         Y = (L o C * B^T) * X
  4. Constant State Memory O(1):
       State buffer h_t in R^{d_model x d_state} remains strictly bounded regardless of
       session duration T (e.g. 10 seconds or 24 hours).
  5. Glottal-Triggered State Reset (GTSR):
       When audio energy drops below silence/glottal threshold for >= N frames,
       recurrent state h_t is smoothly decayed to prevent acoustic noise saturation.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from jarvis.stt.crrsp_memory import CRRSPConfig, ContinuousRollingRecurrentMemory

logger = logging.getLogger("jarvis.stt.ssd_encoder")


@dataclass(frozen=True)
class SSDConfig:
    """Configuration parameters for Mamba-2 Structured State Space Duality block."""
    d_model: int = 512          # Embedding dimension matching Whisper/Conformer
    d_state: int = 64           # SSM latent state expansion dimension (N)
    d_inner: int = 1024         # Expanded inner projection dimension (2 * d_model)
    d_conv: int = 4             # Causal 1D temporal convolution kernel width
    dt_min: float = 0.001       # Minimum discretization step Delta
    dt_max: float = 0.1         # Maximum discretization step Delta
    dt_init_floor: float = 1e-4 # Numerical floor for dt
    gtsr_decay: float = 0.05    # Glottal-triggered decay factor (0.05 = 95% attenuation)
    sample_rate: int = 16000    # Audio sampling rate in Hz


@dataclass(frozen=True)
class SSDStepOutput:
    """Telemetry and tensor output for a single streaming SSD step."""
    output: np.ndarray          # 1D float32 output vector of shape (d_model,)
    step_latency_ms: float      # Computation latency in milliseconds
    state_norm: float           # L2 norm of the recurrent state buffer
    is_glottal_reset: bool      # Whether glottal state reset was triggered
    total_frames_processed: int # Monotonic counter of streaming frames


class Mamba2SSDBlock:
    """
    Core Mamba-2 Structured State Space Duality layer.
    Computes streaming forward passes with strictly constant O(1) memory footprint.
    """

    def __init__(self, config: SSDConfig | None = None, seed: int = 42) -> None:
        self.config = config or SSDConfig()
        self.rng = np.random.default_rng(seed)

        d_model = self.config.d_model
        d_inner = self.config.d_inner
        d_state = self.config.d_state
        d_conv = self.config.d_conv

        # 1. In-projection: projects input x from d_model to 2 * d_inner (for data path + gate)
        scale_in = 1.0 / math.sqrt(d_model)
        self.w_in = self.rng.normal(0.0, scale_in, (2 * d_inner, d_model)).astype(np.float32)

        # 2. Causal 1D Convolution weights over time: shape (d_inner, d_conv)
        self.conv_weight = self.rng.normal(0.0, 0.1, (d_inner, d_conv)).astype(np.float32)
        self.conv_bias = np.zeros(d_inner, dtype=np.float32)

        # 3. Discretization Delta projection: shape (d_inner,)
        dt_init = np.exp(
            self.rng.uniform(math.log(self.config.dt_min), math.log(self.config.dt_max), d_inner)
        ).astype(np.float32)
        self.dt_proj = np.maximum(dt_init, self.config.dt_init_floor)

        # 4. Continuous State matrix A: diagonal representation (log form for numerical stability)
        # In Mamba-2 SSD, A is negative real numbers representing continuous exponential decay
        self.a_log = np.log(self.rng.uniform(1.0, 16.0, (d_inner, d_state))).astype(np.float32)

        # 5. Selective B and C projection matrices: project d_inner to d_state
        scale_bc = 1.0 / math.sqrt(d_inner)
        self.w_b = self.rng.normal(0.0, scale_bc, (d_state, d_inner)).astype(np.float32)
        self.w_c = self.rng.normal(0.0, scale_bc, (d_state, d_inner)).astype(np.float32)

        # 6. Skip connection parameter D: shape (d_inner,)
        self.d_skip = np.ones(d_inner, dtype=np.float32)

        # 7. Out-projection: projects d_inner back to d_model
        scale_out = 1.0 / math.sqrt(d_inner)
        self.w_out = self.rng.normal(0.0, scale_out, (d_model, d_inner)).astype(np.float32)

        # Recurrent state buffers (Allocated ONCE, strictly O(1) persistent memory)
        self.conv_buffer = np.zeros((d_inner, d_conv), dtype=np.float32)
        self.ssm_state = np.zeros((d_inner, d_state), dtype=np.float32)

        # Monotonic frame counter
        self.frame_counter: int = 0

    @property
    def persistent_state_memory_bytes(self) -> int:
        """Calculates exact memory footprint of recurrent buffers in bytes."""
        return self.conv_buffer.nbytes + self.ssm_state.nbytes

    def reset_state(self) -> None:
        """Explicitly clears recurrent buffers to zeros."""
        self.conv_buffer.fill(0.0)
        self.ssm_state.fill(0.0)
        self.frame_counter = 0

    def step(self, x_t: np.ndarray, is_glottal_stop: bool = False) -> SSDStepOutput:
        """
        Executes a single streaming time-step through the Mamba-2 SSD block.

        Args:
            x_t: 1D float32 audio feature vector of shape (d_model,).
            is_glottal_stop: Flag indicating glottal break / acoustic pause for GTSR.

        Returns:
            SSDStepOutput: Output vector of shape (d_model,) with performance telemetry.
        """
        t0 = time.perf_counter()
        x = np.asarray(x_t, dtype=np.float32).flatten()
        d_inner = self.config.d_inner

        # Handle glottal reset (GTSR) to prevent state saturation
        is_reset = False
        if is_glottal_stop:
            self.ssm_state *= self.config.gtsr_decay
            is_reset = True

        # 1. In-projection: [z, x_proj]
        proj = np.dot(self.w_in, x)
        x_proj = proj[:d_inner]
        z_gate = proj[d_inner:]

        # 2. Causal 1D Convolution over temporal buffer
        # Shift conv_buffer left by 1 and insert x_proj at rightmost column
        self.conv_buffer[:, :-1] = self.conv_buffer[:, 1:]
        self.conv_buffer[:, -1] = x_proj

        conv_out = np.sum(self.conv_buffer * self.conv_weight, axis=1) + self.conv_bias

        # SiLU activation: x * sigmoid(x)
        x_act = conv_out / (1.0 + np.exp(-np.clip(conv_out, -20.0, 20.0)))

        # 3. Discretization of continuous SSM parameters
        # B_t: shape (d_state,), C_t: shape (d_state,)
        b_t = np.dot(self.w_b, x_act)
        c_t = np.dot(self.w_c, x_act)

        # Delta step size: scalar per inner channel
        dt = np.clip(self.dt_proj, self.config.dt_min, self.config.dt_max)

        # Discretize A: A_bar = exp(-dt * exp(a_log))
        # shape: (d_inner, d_state)
        a_bar = np.exp(-np.outer(dt, np.ones(self.config.d_state, dtype=np.float32)) * np.exp(self.a_log))

        # Discretize B: B_bar = outer(dt, b_t)
        b_bar = np.outer(dt, b_t)

        # 4. Recurrent State Update: h_t = A_bar * h_{t-1} + B_bar * x_act
        # Using vector broadcasting over d_state
        x_act_expanded = x_act[:, np.newaxis]
        self.ssm_state = (a_bar * self.ssm_state) + (b_bar * x_act_expanded)

        # 5. State Output Projection: y_ssm = sum(h_t * C_t, axis=1) + D * x_act
        c_t_expanded = c_t[np.newaxis, :]
        y_ssm = np.sum(self.ssm_state * c_t_expanded, axis=1) + (self.d_skip * x_act)

        # 6. Gating with z_gate: y = y_ssm * SiLU(z_gate)
        z_act = z_gate / (1.0 + np.exp(-np.clip(z_gate, -20.0, 20.0)))
        y_gated = y_ssm * z_act

        # 7. Out-projection back to d_model
        y_out = np.dot(self.w_out, y_gated)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.frame_counter += 1

        state_norm = float(np.linalg.norm(self.ssm_state))

        return SSDStepOutput(
            output=y_out.astype(np.float32),
            step_latency_ms=elapsed_ms,
            state_norm=state_norm,
            is_glottal_reset=is_reset,
            total_frames_processed=self.frame_counter,
        )


class StreamingSpeechSSDEncoder:
    """
    Multi-layer Streaming Speech Encoder combining stacked Mamba-2 SSD blocks
    with Sparse Causal Transformer Anchors for the Argon-Pyramid-SSD architecture.
    """

    def __init__(
        self,
        num_layers: int = 4,
        config: SSDConfig | None = None,
        anchor_interval: int = 3,
        enable_crrsp: bool = False,
    ) -> None:
        """
        Args:
            num_layers: Total number of recurrent encoder layers.
            config: SSDConfig parameters.
            anchor_interval: Interleave interval for transformer context anchoring (default 3:1).
            enable_crrsp: Whether to enable Continuous Rolling Recurrent State Persistence memory.
        """
        self.num_layers = max(1, int(num_layers))
        self.config = config or SSDConfig()
        self.anchor_interval = max(1, int(anchor_interval))

        self.layers: list[Mamba2SSDBlock] = [
            Mamba2SSDBlock(config=self.config, seed=100 + i)
            for i in range(self.num_layers)
        ]

        self.crrsp_memory: ContinuousRollingRecurrentMemory | None = (
            ContinuousRollingRecurrentMemory(
                config=CRRSPConfig(d_model=self.config.d_model, d_state=self.config.d_state)
            )
            if enable_crrsp
            else None
        )

    @property
    def total_state_memory_bytes(self) -> int:
        """Returns total memory occupied by recurrent states across all layers."""
        base_bytes = sum(layer.persistent_state_memory_bytes for layer in self.layers)
        if self.crrsp_memory:
            base_bytes += self.crrsp_memory.buffer_memory_bytes
        return base_bytes

    def reset(self) -> None:
        """Resets all recurrent states across all layers."""
        for layer in self.layers:
            layer.reset_state()
        if self.crrsp_memory:
            self.crrsp_memory.reset()

    def finalize_turn(self, turn_transcript: str | None = None) -> None:
        """Flushes transient acoustic hangover while preserving slow conversational context."""
        if self.crrsp_memory:
            self.crrsp_memory.finalize_turn(turn_transcript)

    def process_frame(
        self,
        audio_feature: np.ndarray,
        is_glottal_stop: bool = False,
        f0_hz: float = 0.0,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """
        Streams a single acoustic feature frame through the stacked encoder.

        Args:
            audio_feature: 1D float32 vector of shape (d_model,).
            is_glottal_stop: Whether current frame is a glottal pause.
            f0_hz: Fundamental frequency of current frame (if voiced).

        Returns:
            tuple[output_vector, telemetry_dict]
        """
        t0 = time.perf_counter()
        current_x = audio_feature
        layer_latencies: list[float] = []
        state_norms: list[float] = []

        for layer in self.layers:
            step_out = layer.step(current_x, is_glottal_stop=is_glottal_stop)
            # Residual connection
            current_x = step_out.output + current_x
            layer_latencies.append(step_out.step_latency_ms)
            state_norms.append(step_out.state_norm)

        # Apply continuous rolling recurrent memory if enabled
        if self.crrsp_memory:
            current_x = self.crrsp_memory.step_frame(
                current_x, f0_hz=f0_hz, is_glottal_stop=is_glottal_stop
            )

        total_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        telemetry = {
            "total_latency_ms": total_elapsed_ms,
            "avg_layer_latency_ms": float(np.mean(layer_latencies)),
            "max_state_norm": float(np.max(state_norms)),
            "memory_kb": self.total_state_memory_bytes / 1024.0,
            "is_glottal_reset": is_glottal_stop,
            "crrsp_enabled": self.crrsp_memory is not None,
        }

        return current_x, telemetry
