"""
jarvis.nlp.automation
=====================
Automated Continuous Learning Loop for JARVIS NLP Engine.
Includes:
  - UnrecognizedTurnCollector: Real-time collection of low-confidence / unknown queries with PII scrubbing.
  - ContinuousDatasetManager: Automated corpus deduplication, dataset merging, and label conflict resolution.
  - AutomatedEvaluatorGate: Deterministic K-fold CV & regression gating before atomic model deployment.
"""
from __future__ import annotations

__all__ = [
    "UnrecognizedTurnCollector",
    "ContinuousDatasetManager",
    "AutomatedEvaluatorGate",
]
