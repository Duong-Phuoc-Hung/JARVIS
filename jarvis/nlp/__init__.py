"""
jarvis.nlp
==========
Natural Language Understanding and Acoustic Processing Subsystem for JARVIS.
Includes:
  - Joint Intent & Token-Level Slot Tagging Engine (JointIntentSlotTagger).
  - Compound Multi-Intent Decomposer & Sequential Pipeline.
  - Vietnamese Acoustic & Phonetic STT Normalizer.
  - High-performance ONNX Runtime Classifier.
  - Continuous Learning & Automated Feedback Loop.
"""
from __future__ import annotations

from jarvis.nlp.joint_tagger import (
    JointIntentSlotResult,
    JointIntentSlotTagger,
    build_default_joint_dataset,
)
from jarvis.nlp.phonetic_normalizer import normalize_phonetic_stt

__all__ = [
    "JointIntentSlotResult",
    "JointIntentSlotTagger",
    "build_default_joint_dataset",
    "normalize_phonetic_stt",
]
