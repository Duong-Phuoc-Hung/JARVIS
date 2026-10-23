"""
jarvis/nlp/automation/evaluator_gate.py
======================================
Automated Quality and Regression Gate for NLP Model Retraining.
Enforces:
  - Minimum Cross-Validation Accuracy Threshold (default >= 97.5%).
  - Minimum F1-Macro Score Threshold (default >= 96.0%).
  - Golden Regression Suite Zero-Tolerance Test (100% pass on core canonical commands).
  - Fail-closed refusal to deploy any model that regresses performance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from jarvis.llm.local_classifier import VietnameseNLPClassifier

logger = logging.getLogger("jarvis.nlp.automation.evaluator_gate")

# Golden regression queries that must ALWAYS classify correctly
GOLDEN_REGRESSION_TESTS: list[tuple[str, str]] = [
    ("tăng âm lượng lên 80%", "system_volume"),
    ("tắt tiếng máy tính", "system_volume"),
    ("chỉnh độ sáng lên 90%", "system_brightness"),
    ("giảm độ sáng màn hình", "system_brightness"),
    ("mở visual studio code", "app_launch"),
    ("đóng trình duyệt chrome", "app_close"),
    ("tắt nhạc spotify đi", "media_control"),
    ("tiếp tục phát nhạc", "media_control"),
    ("nhiệt độ cpu là bao nhiêu", "system_status"),
    ("bật đèn phòng khách", "smart_home"),
    ("bật điều hòa 24 độ", "smart_home"),
    ("nhắc tôi uống thuốc sau 1 tiếng", "timer_reminder"),
    ("hẹn giờ 15 phút", "timer_reminder"),
    ("tìm kiếm thời tiết hôm nay", "web_search"),
    ("chào buổi sáng jarvis ơi", "greeting_chat"),
    ("chia đôi màn hình sang trái", "window_management"),
    ("phóng to cửa sổ", "window_management"),
    ("mở thư mục tải về", "file_management"),
    ("dọn dẹp thùng rác", "file_management"),
    ("sao chép đoạn này", "clipboard_action"),
    ("kiểm tra kết nối mạng wifi", "network_control"),
    ("khóa màn hình máy tính", "system_power"),
    ("hẹn giờ tắt máy tính sau 30 phút", "system_power"),
    ("công thức nấu món phở bò truyền thống", "unknown"),
]


@dataclass
class GateEvaluationResult:
    """Outcome of an automated quality gate evaluation."""
    passed: bool
    cv_accuracy: float
    cv_f1_macro: float
    golden_accuracy: float
    failed_golden_queries: list[tuple[str, str, str]]  # (query, expected, actual)
    rejection_reasons: list[str]


class AutomatedEvaluatorGate:
    """
    Evaluates new candidate models against statistical thresholds and golden regression cases.
    """

    def __init__(
        self,
        min_cv_accuracy: float = 0.975,
        min_cv_f1: float = 0.960,
        golden_tests: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        self.min_cv_accuracy = float(min_cv_accuracy)
        self.min_cv_f1 = float(min_cv_f1)
        self.golden_tests = list(golden_tests) if golden_tests is not None else GOLDEN_REGRESSION_TESTS

    def evaluate(
        self,
        classifier: VietnameseNLPClassifier,
        training_report: dict[str, Any],
    ) -> GateEvaluationResult:
        """
        Validates model quality. Returns GateEvaluationResult.
        """
        rejection_reasons: list[str] = []

        cv_acc = float(training_report.get("cv_accuracy_mean", 0.0))
        cv_f1 = float(training_report.get("cv_f1_macro_mean", 0.0))

        import math
        if math.isnan(cv_acc) or cv_acc < self.min_cv_accuracy:
            rejection_reasons.append(
                f"CV Accuracy {cv_acc * 100:.2f}% below threshold {self.min_cv_accuracy * 100:.2f}%"
            )

        if math.isnan(cv_f1) or cv_f1 < self.min_cv_f1:
            rejection_reasons.append(
                f"CV F1-Macro {cv_f1 * 100:.2f}% below threshold {self.min_cv_f1 * 100:.2f}%"
            )

        # Run golden regression suite
        failed_golden: list[tuple[str, str, str]] = []
        for query, expected_intent in self.golden_tests:
            pred = classifier.predict(query)
            if pred.intent != expected_intent:
                failed_golden.append((query, expected_intent, pred.intent))

        golden_acc = (
            (len(self.golden_tests) - len(failed_golden)) / len(self.golden_tests)
            if self.golden_tests
            else 1.0
        )

        if failed_golden:
            rejection_reasons.append(
                f"Failed {len(failed_golden)}/{len(self.golden_tests)} golden regression queries ({golden_acc * 100:.1f}%)"
            )

        passed = len(rejection_reasons) == 0

        if passed:
            logger.info("Automated quality gate PASSED (CV Acc=%.2f%%, Golden=%.1f%%)", cv_acc * 100, golden_acc * 100)
        else:
            logger.warning("Automated quality gate REJECTED: %s", rejection_reasons)

        return GateEvaluationResult(
            passed=passed,
            cv_accuracy=cv_acc,
            cv_f1_macro=cv_f1,
            golden_accuracy=golden_acc,
            failed_golden_queries=failed_golden,
            rejection_reasons=rejection_reasons,
        )
