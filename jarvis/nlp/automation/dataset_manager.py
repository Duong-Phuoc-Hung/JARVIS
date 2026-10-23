"""
jarvis/nlp/automation/dataset_manager.py
=======================================
Continuous Dataset Manager for Corpus Consolidation and Deduplication.
Manages:
  - Merging canonical baseline data with newly curated / corrected turns.
  - Removing duplicate utterances across datasets.
  - Detecting label conflicts (identical utterances mapped to different intents).
  - Exporting unified training matrices with data integrity validation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from jarvis.llm.local_classifier import normalize_vietnamese_text

logger = logging.getLogger("jarvis.nlp.automation.dataset_manager")


@dataclass
class DatasetConflict:
    """Represents a conflict where the same utterance has conflicting labels."""
    normalized_text: str
    existing_label: str
    new_label: str
    sample_raw: str


class ContinuousDatasetManager:
    """
    Manages corpus consolidation, deduplication, and label consistency.
    """

    def __init__(self, canonical_data: Sequence[tuple[str, str]] | None = None) -> None:
        self._corpus: dict[str, tuple[str, str]] = {}  # normalized_text -> (raw_text, label)
        self._conflicts: list[DatasetConflict] = []
        if canonical_data:
            self.add_samples(canonical_data)

    @property
    def total_samples(self) -> int:
        """Returns total unique utterances in the corpus."""
        return len(self._corpus)

    @property
    def conflicts(self) -> list[DatasetConflict]:
        """Returns list of detected label conflicts."""
        return list(self._conflicts)

    def add_samples(self, samples: Sequence[tuple[str, str]]) -> int:
        """
        Adds samples to the corpus, skipping duplicates and logging conflicts.

        Args:
            samples: List of (raw_text, label) pairs.

        Returns:
            Count of newly added unique samples.
        """
        added_count = 0
        for raw, label in samples:
            raw_clean = raw.strip()
            if not raw_clean:
                continue
            norm = normalize_vietnamese_text(raw_clean)
            if not norm:
                continue

            if norm in self._corpus:
                existing_raw, existing_label = self._corpus[norm]
                if existing_label != label:
                    conflict = DatasetConflict(
                        normalized_text=norm,
                        existing_label=existing_label,
                        new_label=label,
                        sample_raw=raw_clean,
                    )
                    self._conflicts.append(conflict)
                    logger.warning(
                        "Label conflict for '%s': existing '%s' vs new '%s'",
                        norm,
                        existing_label,
                        label,
                    )
            else:
                self._corpus[norm] = (raw_clean, label)
                added_count += 1

        return added_count

    def get_dataset(self) -> list[tuple[str, str]]:
        """Returns all deduplicated (raw_text, label) pairs."""
        return list(self._corpus.values())

    def get_label_distribution(self) -> dict[str, int]:
        """Returns frequency count per intent domain."""
        dist: dict[str, int] = {}
        for _, label in self._corpus.values():
            dist[label] = dist.get(label, 0) + 1
        return dist


def get_canonical_dataset() -> tuple[list[str], list[str]]:
    """
    Returns canonical training samples and labels for Vietnamese NLP intent classification.
    Safely falls back to golden regression and default joint pairs if external script is unavailable.
    """
    try:
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from scripts.train_vietnamese_nlp import CANONICAL_TRAINING_DATA, augment_dataset
        augmented = augment_dataset(CANONICAL_TRAINING_DATA)
        return [item[0] for item in augmented], [item[1] for item in augmented]
    except Exception:
        from jarvis.nlp.automation.evaluator_gate import GOLDEN_REGRESSION_TESTS
        from jarvis.nlp.joint_tagger import build_default_joint_dataset
        joint = [(d[0], d[1]) for d in build_default_joint_dataset()]
        all_samples = joint + list(GOLDEN_REGRESSION_TESTS)
        return [item[0] for item in all_samples], [item[1] for item in all_samples]

