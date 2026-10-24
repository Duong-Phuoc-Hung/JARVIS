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

__all__ = [
    "LATENT_DIM",
    "CONTEXT_DIM",
    "SpeculativeActionStatus",
    "SpeculativeActionCandidate",
    "LatentPredictionResult",
    "LatentOSWorldModel",
    "NegativeLatencyExecutionManager",
]
