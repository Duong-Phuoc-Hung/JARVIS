"""
rebuilt/tests/broken/broken_nlp_v1.py
====================================
BROKEN VERSION 7: Violates Rule NLP-06.
Omits minimum confidence threshold fallback, always returning top intent even when confidence is near zero.
Target test that MUST FAIL: test_ntest_08_confidence_threshold_fallback.
"""
from __future__ import annotations

import logging
import numpy as np
from nlp_classifier import (
    ClassificationResult,
    VietnameseNLPClassifier as BaseClassifier,
    normalize_vietnamese_text,
)

log = logging.getLogger("broken.nlp_v1")


class VietnameseNLPClassifier(BaseClassifier):
    def predict(self, raw_text: str) -> ClassificationResult:
        clean = normalize_vietnamese_text(raw_text)
        if self.pipeline is None or not clean:
            return ClassificationResult(intent="unknown", confidence=0.0, all_scores={}, latency_ms=0.0)

        with self._lock:
            probs = self.pipeline.predict_proba([clean])[0]
            classes = self.classes_

        top_idx = int(np.argmax(probs))
        top_confidence = float(probs[top_idx])

        # BUG: Deliberately bypasses min_confidence check!
        # Always returns classes[top_idx] even when top_confidence < min_confidence
        top_intent = classes[top_idx]

        scores_dict = {cls_name: float(p) for cls_name, p in zip(classes, probs)}
        return ClassificationResult(
            intent=top_intent,
            confidence=top_confidence,
            all_scores=scores_dict,
            latency_ms=1.0,
        )


__all__ = ["VietnameseNLPClassifier"]
