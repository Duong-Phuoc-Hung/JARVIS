"""
rebuilt/tests/broken/broken_nlp_v2.py
====================================
BROKEN VERSION 8: Violates Rule NLP-03.
Omits training sample count and distinct class validation, proceeding without throwing ValueError.
Target test that MUST FAIL: test_ntest_04_training_validation_insufficient_samples.
"""
from __future__ import annotations

import logging
from typing import Any
from nlp_classifier import VietnameseNLPClassifier as BaseClassifier

log = logging.getLogger("broken.nlp_v2")


class VietnameseNLPClassifier(BaseClassifier):
    def train(
        self,
        samples: list[str],
        labels: list[str],
        cv_folds: int = 5,
    ) -> dict[str, Any]:
        # BUG: Deliberately omits sample length and unique class checks!
        # Does not raise ValueError when len(samples) < 10
        return {
            "num_samples": len(samples),
            "num_classes": len(set(labels)),
            "classes": sorted(list(set(labels))),
            "cv_accuracy_mean": 0.0,
            "cv_accuracy_std": 0.0,
            "train_duration_s": 0.0,
        }


__all__ = ["VietnameseNLPClassifier"]
