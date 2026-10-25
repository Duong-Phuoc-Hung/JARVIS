"""
jarvis.learning
===============
Reinforcement learning, latent world modeling, and speculative execution subsystem.
"""
from __future__ import annotations

from jarvis.learning.latent_world_model import (
    LATENT_DIM,
    CONTEXT_DIM,
    SpeculativeActionStatus,
    SpeculativeActionCandidate,
    LatentPredictionResult,
    LatentOSWorldModel,
    NegativeLatencyExecutionManager,
)
from jarvis.learning.quantum_tensor_policy import (
    AnnealingScheduleResult,
    MatrixProductStatePolicy,
    MPSTelemetry,
    SimulatedQuantumAnnealer,
)

__all__ = [
    "AnnealingScheduleResult",
    "CONTEXT_DIM",
    "LATENT_DIM",
    "LatentOSWorldModel",
    "LatentPredictionResult",
    "MatrixProductStatePolicy",
    "MPSTelemetry",
    "NegativeLatencyExecutionManager",
    "SimulatedQuantumAnnealer",
    "SpeculativeActionCandidate",
    "SpeculativeActionStatus",
]
