"""
tests/test_data_analytics.py
============================
Test Suite for Data Ingestion, Descriptive Statistics, Monte Carlo Simulation, and Export.
Covering:
  - F-28: Data Ingestion & Stats Engine (CSV/XLSX parsing, descriptive statistics & anomalies)
  - F-29: Monte Carlo Simulation Module (Normal, Lognormal, Uniform, Triangular distributions & VaR)
  - F-30: Multi-Format Document Exporter (Pure OpenXML DOCX, PDF export & voice summary)
"""

import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
import zipfile
import numpy as np
import pytest

from jarvis.data.document import (
    DocxReportBuilder,
    DocumentExporter,
    PdfReportBuilder,
    VoiceSummaryGenerator,
)
from jarvis.data.stats import (
    AnomalyItem,
    AnomalyReport,
    CorrelationResult,
    DataAnalyticsEngine,
    DataStatsReport,
    DescriptiveStats,
    DistributionType,
    MonteCarloConfig,
    MonteCarloEngine,
    MonteCarloResult,
    TabularDataset,
    TrendResult,
)


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_data_analytics_csv_ingestion_and_stats_tier1(tmp_path):
    """
    [F-28] Validate ingestion of CSV dataset and accurate calculation of descriptive statistics.
    """
    csv_file = tmp_path / "sample_data.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "value"])
        for v in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]:
            writer.writerow([1, v])

    engine = DataAnalyticsEngine()
    stats = engine.compute_statistics_from_csv(csv_file, column="value")

    assert stats.count == 10
    assert stats.mean == 55.0
    assert stats.median == 55.0
    assert math.isclose(stats.p25, 32.5, abs_tol=1.0)


def test_data_analytics_comprehensive_stats_and_anomalies_tier1(tmp_path):
    """
    [F-28] Validate full descriptive statistics (std, skewness, kurtosis), correlation, and anomaly detection.
    """
    csv_file = tmp_path / "multi_col.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sales", "advertising"])
        for i in range(1, 21):
            writer.writerow([i * 10.0, i * 2.5])
        # Add outlier
        writer.writerow([1000.0, 50.0])

    engine = DataAnalyticsEngine()
    dataset = engine.load_csv(csv_file)

    stats = engine.compute_statistics(dataset, "sales")
    assert stats.count == 21
    assert stats.mean > 100.0
    assert stats.max == 1000.0

    corr = engine.compute_correlation_matrix(dataset)
    assert len(corr.columns) == 2
    assert corr.pearson_matrix[0][0] == 1.0
    assert corr.spearman_matrix[0][1] > 0.90

    anomalies = engine.detect_anomalies(dataset, "sales", method="zscore", threshold=2.5)
    assert anomalies.total_anomalies >= 1
    assert any(a.value == 1000.0 for a in anomalies.anomalies)

    trend = engine.analyze_trend(dataset, "advertising")
    assert trend.direction == "INCREASING"
    assert trend.slope > 0.0


def test_data_analytics_monte_carlo_simulation_tier1():
    """
    [F-29] Validate Monte Carlo simulation executes parameterized iterations and produces P5/P95 bounds.
    """
    engine = MonteCarloEngine()
    result = engine.run_simulation(initial_value=100.0, iterations=5000, mean_return=0.08, volatility=0.12)

    assert result.iterations == 5000
    assert result.p5 < result.p50 < result.p95
    assert 0.0 <= result.prob_target <= 100.0
    assert result.var_95 >= 0.0


def test_data_analytics_monte_carlo_distributions_tier1():
    """
    [F-29] Validate Monte Carlo simulations across Normal, Lognormal, Uniform, and Triangular distributions.
    """
    engine = MonteCarloEngine()
    
    # Lognormal
    res_log = engine.run_simulation(initial_value=100.0, iterations=2000, distribution="lognormal")
    assert res_log.iterations == 2000
    assert res_log.mean > 0

    # Uniform
    res_uni = engine.run_simulation(initial_value=100.0, iterations=2000, distribution="uniform")
    assert res_uni.iterations == 2000

    # Triangular
    res_tri = engine.run_simulation(initial_value=100.0, iterations=2000, distribution="triangular")
    assert res_tri.iterations == 2000


def test_data_analytics_document_export_and_voice_summary_tier1(tmp_path):
    """
    [F-30] Validate exporting analytics summary into structured DOCX report and voice summary.
    """
    stats = DataStatsReport(count=100, mean=52.4, std=12.1, median=50.0, p25=42.0, p75=61.0)
    sim = MonteCarloResult(iterations=10000, mean=108.5, std_err=0.15, p5=85.0, p50=107.0, p95=132.0, prob_target=78.5)

    exporter = DocumentExporter()
    out_file = tmp_path / "reports" / "summary.docx"
    exported_path = exporter.export_report(stats, sim, out_file)

    assert exported_path.exists()
    assert exported_path.stat().st_size > 0

    # Validate that generated docx is a valid zip containing OpenXML standard files
    with zipfile.ZipFile(exported_path, "r") as z:
        assert "[Content_Types].xml" in z.namelist()
        assert "word/document.xml" in z.namelist()

    voice_summary = exporter.get_voice_summary("survey.csv", stats, sim)
    assert "Đã hoàn thành phân tích" in voice_summary
    assert "78.5%" in voice_summary


def test_data_analytics_pdf_export_tier1(tmp_path):
    """
    [F-30] Validate PDF generation creates a valid PDF 1.4 binary file.
    """
    stats = DataStatsReport(count=50, mean=30.0, std=5.0, median=30.0, p25=25.0, p75=35.0)
    sim = MonteCarloResult(iterations=1000, mean=32.0, std_err=0.2, p5=28.0, p50=32.0, p95=36.0, prob_target=65.0)

    exporter = DocumentExporter()
    out_pdf = tmp_path / "reports" / "summary.pdf"
    exported_path = exporter.export_report(stats, sim, out_pdf)

    assert exported_path.exists()
    content = exported_path.read_bytes()
    assert content.startswith(b"%PDF-1.4")


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_data_analytics_corrupted_or_empty_csv_tier2(tmp_path):
    """
    [F-28] Validate handling 0-byte or corrupted non-CSV file raises ValueError with clear error.
    """
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("", encoding="utf-8")

    engine = DataAnalyticsEngine()
    with pytest.raises(ValueError):
        engine.compute_statistics_from_csv(empty_file)


def test_data_analytics_invalid_simulation_params_tier2():
    """
    [F-29] Validate that invalid simulation iterations (<1000) or negative volatility raises ValueError.
    """
    engine = MonteCarloEngine()
    with pytest.raises(ValueError):
        engine.run_simulation(iterations=50)  # Below 1000 limit

    with pytest.raises(ValueError):
        engine.run_simulation(volatility=-0.05)  # Invalid negative volatility
