"""
rebuilt/tests/broken/broken_nlp_v3.py
====================================
BROKEN VERSION 9: Violates Rule NLP-02.
Raises uncaught AttributeError when predict() is called on an untrained model instance.
Target test that MUST FAIL: test_ntest_03_untrained_classifier_fallback.
"""
from __future__ import annotations

import logging
from nlp_classifier import (
    ClassificationResult,
    VietnameseNLPClassifier as BaseClassifier,
)

log = logging.getLogger("broken.nlp_v3")


class VietnameseNLPClassifier(BaseClassifier):
    def predict(self, raw_text: str) -> ClassificationResult:
        # BUG: Deliberately assumes pipeline is never None, raising AttributeError!
        return self.pipeline.predict_proba([raw_text])  # type: ignore[union-attr]


__all__ = ["VietnameseNLPClassifier"]
