"""
rebuilt/nlp_classifier.py
=========================
Clean-room implementation of On-Device Machine Learning Vietnamese NLP Intent Classifier.
Implements rules NLP-01 to NLP-11 from SPEC-JARVIS-001.

Contracts:
- NLP-01: 4-step text normalization pipeline (lowercase, strip, unicode regex, collapse spaces).
- NLP-02: Untrained model returns intent="unknown", confidence=0.0 without exception.
- NLP-03: Two distinct ValueError guard paths on insufficient/single-class training data.
- NLP-04: Dual TF-IDF FeatureUnion (word 1-2 n-grams + char 2-5 n-grams with char_wb).
- NLP-05: Calibrated Logistic Regression pipeline with sigmoid calibration.
- NLP-06: Configurable min_confidence threshold falling back to "unknown".
- NLP-07: Probability scores sum to approx 1.0.
- NLP-08: Atomic save with joblib and 5-attempt retry loop on OS file lock.
- NLP-09: Versioned joblib payload schema with pipeline and classes.
- NLP-10: Sub-50ms CPU prediction latency measurement.
- NLP-11: Thread-safe predict and train with fine-grained lock release.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import FeatureUnion, Pipeline

log = logging.getLogger("rebuilt.nlp_classifier")

DEFAULT_MODEL_DIR = Path("data/models")
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "vietnamese_nlp_intent.joblib"


def normalize_vietnamese_text(text: str) -> str:
    """
    Rule NLP-01: 4-step Vietnamese text normalization:
    1. Empty / whitespace-only -> return ""
    2. Lowercase and strip
    3. Strip punctuation and non-alphanumeric characters
    4. Collapse consecutive whitespace into single space
    """
    if not text:
        return ""
    cleaned = text.lower().strip()
    cleaned = re.sub(r"[^\w\s\d]", " ", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# Alias for clean-room caller flexibility
normalize_text = normalize_vietnamese_text


@dataclass
class ClassificationResult:
    """Outcome of intent classification."""
    intent: str
    confidence: float
    all_scores: dict[str, float]
    latency_ms: float


class VietnameseNLPClassifier:
    """
    On-device NLP Intent Classifier using Dual FeatureUnion TF-IDF & Calibrated Logistic Regression.
    Rules NLP-01 through NLP-11.
    """

    def __init__(
        self,
        model_path: Path | str = DEFAULT_MODEL_PATH,
        min_confidence: float = 0.35,
    ) -> None:
        self.model_path = Path(model_path)
        self.min_confidence = float(min_confidence)
        self.pipeline: Pipeline | None = None
        self.classes_: list[str] = []
        # Rule NLP-11: Standard threading.Lock
        self._lock = threading.Lock()
        self._load_if_exists()

    @property
    def is_trained(self) -> bool:
        """Returns True if a valid pipeline is fitted and ready."""
        with self._lock:
            return self.pipeline is not None and len(self.classes_) > 0

    def _load_if_exists(self) -> bool:
        """Rule NLP-09: Load joblib model payload from disk if present."""
        if not self.model_path.exists():
            return False
        try:
            with self._lock:
                data = joblib.load(self.model_path)
                self.pipeline = data["pipeline"]
                self.classes_ = list(data["classes"])
            log.info("Loaded NLP classifier model from %s", self.model_path)
            return True
        except Exception as exc:
            log.warning("Failed loading model from %s: %s", self.model_path, exc)
            return False

    def train(
        self,
        samples: list[str],
        labels: list[str],
        cv_folds: int = 5,
    ) -> dict[str, Any]:
        """
        Train classifier on training samples and labels.
        Rules NLP-03, NLP-04, NLP-05, NLP-11.
        """
        # Rule NLP-03: Training validation - insufficient / mismatched
        if len(samples) != len(labels) or len(samples) < 10:
            raise ValueError(
                f"Insufficient or mismatched training data: {len(samples)} samples, {len(labels)} labels"
            )

        clean_texts = [normalize_vietnamese_text(t) for t in samples]
        unique_labels = sorted(list(set(labels)))

        # Rule NLP-03: Training validation - distinct classes
        if len(unique_labels) < 2:
            raise ValueError("Training requires at least 2 distinct intent classes.")

        # Rule NLP-04: Dual TF-IDF FeatureUnion
        features = FeatureUnion([
            ("word_ngram", TfidfVectorizer(
                ngram_range=(1, 2),
                sublinear_tf=True,
                min_df=1,
            )),
            ("char_ngram", TfidfVectorizer(
                ngram_range=(2, 5),
                analyzer="char_wb",
                sublinear_tf=True,
                min_df=1,
            )),
        ])

        # Rule NLP-05: Calibrated Logistic Regression
        base_clf = LogisticRegression(
            C=10.0,
            max_iter=1000,
            class_weight="balanced",
            solver="lbfgs",
            random_state=42,
        )

        calibrated = CalibratedClassifierCV(
            estimator=base_clf,
            method="sigmoid",
            cv=min(3, len(samples) // len(unique_labels)),
        )

        pipeline = Pipeline([
            ("features", features),
            ("classifier", calibrated),
        ])

        t0 = time.monotonic()
        actual_cv_folds = min(cv_folds, min([labels.count(c) for c in unique_labels]))
        if actual_cv_folds >= 2:
            skf = StratifiedKFold(n_splits=actual_cv_folds, shuffle=True, random_state=42)
            cv_scores = cross_val_score(pipeline, clean_texts, labels, cv=skf, scoring="accuracy")
            cv_acc_mean = float(np.mean(cv_scores))
            cv_acc_std = float(np.std(cv_scores))
        else:
            cv_acc_mean = 1.0
            cv_acc_std = 0.0

        # Fit on 100% of data
        pipeline.fit(clean_texts, labels)
        train_duration = time.monotonic() - t0

        # Rule NLP-11: Acquire lock when assigning trained pipeline
        with self._lock:
            self.pipeline = pipeline
            self.classes_ = list(pipeline.classes_)

        return {
            "num_samples": len(samples),
            "num_classes": len(unique_labels),
            "classes": unique_labels,
            "cv_accuracy_mean": cv_acc_mean,
            "cv_accuracy_std": cv_acc_std,
            "train_duration_s": round(train_duration, 3),
        }

    def save(self, target_path: Path | str | None = None) -> bool:
        """
        Rule NLP-08 & NLP-09: Atomically persist trained model using joblib and retry loop.
        """
        out_path = Path(target_path) if target_path else self.model_path
        with self._lock:
            if self.pipeline is None:
                log.error("Cannot save: model is not trained.")
                return False
            payload = {
                "version": 1,
                "trained_at": time.time(),
                "pipeline": self.pipeline,
                "classes": self.classes_,
            }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        tid = threading.get_ident()
        now_ns = time.time_ns()
        tmp_path = out_path.with_name(f"{out_path.name}.tmp.{tid}.{now_ns}")

        try:
            joblib.dump(payload, tmp_path, compress=3)
            # Rule NLP-08: 5-retry loop on OSError / Windows lock
            for attempt in range(5):
                try:
                    tmp_path.replace(out_path)
                    log.info("Saved NLP model to %s", out_path)
                    return True
                except OSError:
                    time.sleep(0.02 * (attempt + 1))
            return False
        except Exception as exc:
            log.error("Failed saving model to %s: %s", out_path, exc)
            return False
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def predict(self, raw_text: str) -> ClassificationResult:
        """
        Classify input query into an intent category.
        Rules NLP-02, NLP-06, NLP-07, NLP-10, NLP-11.
        """
        t0 = time.monotonic()
        clean = normalize_vietnamese_text(raw_text)

        # Rule NLP-11: Thread-safe predict with fine-grained lock
        with self._lock:
            # Rule NLP-02: Untrained model or empty text returns intent="unknown" without error
            if self.pipeline is None or not clean:
                dur_ms = (time.monotonic() - t0) * 1000.0
                return ClassificationResult(
                    intent="unknown",
                    confidence=0.0,
                    all_scores={},
                    latency_ms=dur_ms,
                )

            # Rule NLP-11: Predict probabilities inside lock
            probs = self.pipeline.predict_proba([clean])[0]
            classes = self.classes_

        # Lock is released before top selection and dict formatting (Rule NLP-11)
        top_idx = int(np.argmax(probs))
        top_confidence = float(probs[top_idx])

        # Rule NLP-06: Min confidence fallback
        top_intent = classes[top_idx] if top_confidence >= self.min_confidence else "unknown"

        # Rule NLP-07: Dict mapping summing to ~1.0
        scores_dict = {cls_name: float(p) for cls_name, p in zip(classes, probs)}

        # Rule NLP-10: Sub-50ms latency calculation
        dur_ms = (time.monotonic() - t0) * 1000.0

        return ClassificationResult(
            intent=top_intent,
            confidence=top_confidence,
            all_scores=scores_dict,
            latency_ms=dur_ms,
        )


# Aliases for clean-room interoperability
NLPClassifier = VietnameseNLPClassifier

__all__ = [
    "VietnameseNLPClassifier",
    "NLPClassifier",
    "ClassificationResult",
    "normalize_vietnamese_text",
    "normalize_text",
]
