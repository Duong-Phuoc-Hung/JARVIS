"""
tests/test_adversarial_m5_challenger1.py
=========================================
Adversarial Stress Test Suite for Milestone 5:
- Data Analytics Engine (jarvis/data/stats.py):
  1. Statistical edge cases (single-element, zero variance, extreme outliers, NaN/NULL tokens, non-numeric column filtration).
  2. Mathematical precision of skewness (G_1) and excess kurtosis (G_2) vs SciPy unbiased ground truth.
  3. Pearson and Spearman correlation matrices: bounds [-1.0, 1.0], symmetry, zero-variance handling, monotonic transforms.
  4. Monte Carlo engine: 4 distributions (Normal, Lognormal, Uniform, Triangular), VaR_95, VaR_99, CVaR_95 inequalities.
- Document Exporter (jarvis/data/document.py):
  1. OpenXML .docx ZIP structure and XML schema extraction & validation ([Content_Types].xml, _rels/.rels, word/document.xml, word/styles.xml).
  2. XML injection resistance and Unicode/Vietnamese handling.
  3. PDF 1.4 header (%PDF-1.4), xref, stream length, and boundary stress tests.
"""

import csv
import io
import math
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pytest

from jarvis.data.document import (
    DocumentExporter,
    DocxReportBuilder,
    PdfReportBuilder,
    VoiceSummaryGenerator,
)
from jarvis.data.stats import (
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
# SECTION 1: ADVERSARIAL DATA ANALYTICS & STATISTICAL EDGE CASES
# ============================================================================

def test_adversarial_single_element_dataset():
    """Test descriptive statistics on a single-element series (n=1)."""
    engine = DataAnalyticsEngine()
    dataset = TabularDataset(headers=["val"], rows=[["42.5"]])
    
    stats = engine.compute_statistics(dataset, "val")
    assert stats.count == 1
    assert stats.mean == 42.5
    assert stats.variance == 0.0
    assert stats.std == 0.0
    assert stats.std_err == 0.0
    assert stats.min == 42.5
    assert stats.max == 42.5
    assert stats.range == 0.0
    assert stats.median == 42.5
    assert stats.skewness == 0.0
    assert stats.kurtosis == 0.0
    assert stats.missing_count == 0


def test_adversarial_two_element_dataset():
    """Test sample variance with Bessel correction ddof=1 on n=2."""
    engine = DataAnalyticsEngine()
    dataset = TabularDataset(headers=["val"], rows=[["10.0"], ["20.0"]])
    
    stats = engine.compute_statistics(dataset, "val")
    assert stats.count == 2
    assert stats.mean == 15.0
    assert math.isclose(stats.variance, 50.0, rel_tol=1e-6)
    assert math.isclose(stats.std, math.sqrt(50.0), rel_tol=1e-6)
    assert stats.skewness == 0.0
    assert stats.kurtosis == 0.0


def test_adversarial_zero_variance_constant_series():
    """Test constant series: zero variance, zero std, no division by zero."""
    engine = DataAnalyticsEngine()
    rows = [["100.0"] for _ in range(50)]
    dataset = TabularDataset(headers=["constant_col"], rows=rows)

    stats = engine.compute_statistics(dataset, "constant_col")
    assert stats.count == 50
    assert stats.mean == 100.0
    assert stats.variance == 0.0
    assert stats.std == 0.0
    assert stats.std_err == 0.0
    assert stats.min == 100.0
    assert stats.max == 100.0
    assert stats.range == 0.0
    assert stats.skewness == 0.0
    assert stats.kurtosis == 0.0


def test_adversarial_extreme_magnitude_outliers_and_stability():
    """Test numerical stability with extreme numbers (1e14, -1e14, 1e-10)."""
    engine = DataAnalyticsEngine()
    rows = [["1e14"], ["-1e14"], ["1.0"], ["2.0"], ["3.0"]]
    dataset = TabularDataset(headers=["extreme"], rows=rows)

    stats = engine.compute_statistics(dataset, "extreme")
    assert stats.count == 5
    assert stats.min == -1e14
    assert stats.max == 1e14
    assert stats.range == 2e14
    assert not math.isnan(stats.mean)
    assert not math.isnan(stats.variance)
    assert not math.isnan(stats.std)


def test_adversarial_nan_null_and_corrupted_token_handling(tmp_path):
    """Test CSV containing NaN, null, None, N/A, currency, and percentages."""
    csv_file = tmp_path / "messy.csv"
    csv_content = (
        'id,amount,score,status\n'
        '1,"$1,250.50",95.5%,OK\n'
        '2,null,NaN,FAILED\n'
        '3,3500.00,N/A,OK\n'
        '4,None,70.0%,OK\n'
        '5,"$4,100.00",82.0%,OK\n'
        '6,invalid_num,#N/A,ERROR\n'
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    engine = DataAnalyticsEngine()
    dataset = engine.load_csv(csv_file)

    assert "amount" in dataset.numeric_columns
    amount_vals = dataset.numeric_columns["amount"]
    assert len(amount_vals) == 3
    assert list(amount_vals) == [1250.50, 3500.00, 4100.00]

    assert "score" in dataset.numeric_columns
    score_vals = dataset.numeric_columns["score"]
    assert len(score_vals) == 3
    assert list(score_vals) == [95.5, 70.0, 82.0]

    assert "status" not in dataset.numeric_columns


def test_adversarial_non_numeric_column_filtration(tmp_path):
    """Verify strict filtration of purely string/categorical columns."""
    csv_file = tmp_path / "catalog.csv"
    csv_content = (
        "product_name,category,sku_code,price,quantity\n"
        "Widget A,Hardware,SKU-001,29.99,100\n"
        "Widget B,Software,SKU-002,199.99,50\n"
        "Widget C,Hardware,SKU-003,49.50,200\n"
        "Widget D,Services,SKU-004,500.00,10\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    engine = DataAnalyticsEngine()
    dataset = engine.load_csv(csv_file)

    assert set(dataset.numeric_columns.keys()) == {"price", "quantity"}
    assert "product_name" not in dataset.numeric_columns
    assert "category" not in dataset.numeric_columns
    assert "sku_code" not in dataset.numeric_columns


# ============================================================================
# SECTION 2: SKEWNESS & EXCESS KURTOSIS MATHEMATICAL VERIFICATION
# ============================================================================

def test_adversarial_skewness_and_kurtosis_against_scipy_definitions():
    """
    Directly verify sample skewness G1 and sample excess kurtosis G2
    against exact analytical / SciPy formulas:
    G1 = [sqrt(n(n-1)) / (n-2)] * [m3 / m2^(3/2)]
    G2 = [(n-1) / ((n-2)(n-3))] * [(n+1)(m4 / m2^2 - 3) + 6]
    """
    engine = DataAnalyticsEngine()

    # Fixed deterministic sample: n=10
    raw_data = [12.0, 15.0, 14.0, 18.0, 19.0, 25.0, 32.0, 48.0, 55.0, 90.0]
    dataset = TabularDataset(headers=["x"], rows=[[str(v)] for v in raw_data])
    stats = engine.compute_statistics(dataset, "x")

    n = len(raw_data)
    arr = np.array(raw_data, dtype=np.float64)
    mean_v = np.mean(arr)
    diff = arr - mean_v
    m2 = np.mean(diff**2)
    m3 = np.mean(diff**3)
    m4 = np.mean(diff**4)

    g1 = m3 / (m2**1.5)
    expected_g1 = (math.sqrt(n * (n - 1)) / (n - 2)) * g1

    g2 = (m4 / (m2**2)) - 3.0
    expected_g2 = ((n - 1) / ((n - 2) * (n - 3))) * ((n + 1) * g2 + 6.0)

    assert math.isclose(stats.skewness, expected_g1, rel_tol=1e-7)
    assert math.isclose(stats.kurtosis, expected_g2, rel_tol=1e-7)
    assert stats.skewness > 0.0


def test_adversarial_symmetric_distribution_skewness_zero():
    """Verify perfectly symmetric data yields skewness == 0.0."""
    engine = DataAnalyticsEngine()
    symmetric_data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    dataset = TabularDataset(headers=["sym"], rows=[[str(v)] for v in symmetric_data])

    stats = engine.compute_statistics(dataset, "sym")
    assert math.isclose(stats.skewness, 0.0, abs_tol=1e-10)


def test_adversarial_platykurtic_vs_leptokurtic_kurtosis():
    """Verify heavy-tailed data has G2 > 0 and uniform-like data has G2 < 0."""
    engine = DataAnalyticsEngine()

    lepto_data = [-100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0]
    ds_lepto = TabularDataset(headers=["lepto"], rows=[[str(v)] for v in lepto_data])
    stats_lepto = engine.compute_statistics(ds_lepto, "lepto")
    assert stats_lepto.kurtosis > 0.0

    platy_data = [float(i) for i in range(1, 21)]
    ds_platy = TabularDataset(headers=["platy"], rows=[[str(v)] for v in platy_data])
    stats_platy = engine.compute_statistics(ds_platy, "platy")
    assert stats_platy.kurtosis < 0.0


# ============================================================================
# SECTION 3: PEARSON & SPEARMAN CORRELATION MATRICES & BOUNDS
# ============================================================================

def test_adversarial_correlation_bounds_and_symmetry():
    """Test that all correlation matrix entries strictly satisfy [-1.0, 1.0] and symmetry."""
    engine = DataAnalyticsEngine()
    np.random.seed(123)
    n = 100
    x = np.random.normal(0, 1, n)
    y = 2.5 * x + np.random.normal(0, 0.5, n)
    z = -3.0 * x + np.random.normal(0, 0.5, n)
    w = np.random.uniform(-10, 10, n)

    rows = [[str(x[i]), str(y[i]), str(z[i]), str(w[i])] for i in range(n)]
    dataset = TabularDataset(headers=["x", "y", "z", "w"], rows=rows)

    corr = engine.compute_correlation_matrix(dataset)
    k = len(corr.columns)
    assert k == 4

    for i in range(k):
        for j in range(k):
            p_val = corr.pearson_matrix[i][j]
            s_val = corr.spearman_matrix[i][j]

            assert -1.0 <= p_val <= 1.0, f"Pearson out of bounds at ({i}, {j}): {p_val}"
            assert -1.0 <= s_val <= 1.0, f"Spearman out of bounds at ({i}, {j}): {s_val}"

            assert math.isclose(p_val, corr.pearson_matrix[j][i], abs_tol=1e-7)
            assert math.isclose(s_val, corr.spearman_matrix[j][i], abs_tol=1e-7)

            if i == j:
                assert p_val == 1.0
                assert s_val == 1.0

    assert corr.pearson_matrix[0][1] > 0.90
    assert corr.pearson_matrix[0][2] < -0.90
    assert corr.spearman_matrix[0][1] > 0.90
    assert corr.spearman_matrix[0][2] < -0.90


def test_adversarial_zero_variance_spearman_and_pearson_behavior():
    """
    Adversarial Challenge: Verify that a zero-variance column in a dataset
    correctly yields 0.0 in Pearson and test its behavior in Spearman.
    """
    engine = DataAnalyticsEngine()
    n = 50
    x = np.linspace(1.0, 50.0, n)
    c = np.full(n, 100.0)  # constant zero-variance column

    rows = [[str(x[i]), str(c[i])] for i in range(n)]
    dataset = TabularDataset(headers=["x", "const"], rows=rows)

    corr = engine.compute_correlation_matrix(dataset)
    # Pearson correctly returns 0.0 for constant columns
    assert corr.pearson_matrix[0][1] == 0.0
    assert corr.pearson_matrix[1][0] == 0.0


def test_adversarial_monotonic_non_linear_spearman_vs_pearson():
    """For strictly monotonic non-linear y = x^5, Spearman must be exactly 1.0 while Pearson < 1.0."""
    engine = DataAnalyticsEngine()
    x_vals = np.linspace(1.0, 10.0, 20)
    y_vals = x_vals ** 5

    rows = [[str(x_vals[i]), str(y_vals[i])] for i in range(20)]
    dataset = TabularDataset(headers=["x", "y"], rows=rows)

    corr = engine.compute_correlation_matrix(dataset)
    spearman_xy = corr.spearman_matrix[0][1]
    pearson_xy = corr.pearson_matrix[0][1]

    assert math.isclose(spearman_xy, 1.0, abs_tol=1e-6)
    assert pearson_xy < 0.95


# ============================================================================
# SECTION 4: MONTE CARLO ENGINE & VaR / CVaR FORMULAS
# ============================================================================

def test_adversarial_monte_carlo_distributions_execution_and_percentiles():
    """Verify all 4 distributions generate valid ordered percentiles."""
    engine = MonteCarloEngine()
    for dist in [DistributionType.NORMAL, DistributionType.LOGNORMAL, DistributionType.UNIFORM, DistributionType.TRIANGULAR]:
        res = engine.run_simulation(
            initial_value=100.0,
            iterations=10000,
            mean_return=0.06,
            volatility=0.15,
            target_value=110.0,
            distribution=dist,
            random_seed=42,
        )

        assert res.iterations == 10000
        assert res.min <= res.p1 <= res.p5 <= res.p10 <= res.p25 <= res.p50 <= res.p75 <= res.p90 <= res.p95 <= res.p99 <= res.max
        assert 0.0 <= res.prob_target <= 100.0
        assert res.std_err > 0.0
        assert res.mean > 0.0


def test_adversarial_monte_carlo_lognormal_strictly_positive():
    """Lognormal distribution must generate strictly positive outcomes (no negative values)."""
    engine = MonteCarloEngine()
    res = engine.run_simulation(
        initial_value=50.0,
        iterations=5000,
        mean_return=-0.50,
        volatility=0.80,
        distribution="lognormal",
        random_seed=999,
    )
    assert res.min > 0.0
    assert res.p1 > 0.0


def test_adversarial_var_and_cvar_mathematical_inequalities():
    """
    Verify fundamental risk inequalities:
    1. VaR_99 >= VaR_95 >= 0
    2. CVaR_95 >= VaR_95
    """
    engine = MonteCarloEngine()
    res = engine.run_simulation(
        initial_value=100.0,
        iterations=10000,
        mean_return=0.02,
        volatility=0.20,
        distribution="normal",
        random_seed=777,
    )

    assert res.var_95 >= 0.0
    assert res.var_99 >= res.var_95, f"VaR_99 ({res.var_99}) must be >= VaR_95 ({res.var_95})"
    assert res.cvar_95 >= res.var_95, f"CVaR_95 ({res.cvar_95}) must be >= VaR_95 ({res.var_95})"


# ============================================================================
# SECTION 5: OPENXML DOCX ZIP STRUCTURE & XML SCHEMA VALIDATION
# ============================================================================

def test_adversarial_docx_zip_structure_and_xml_schemas(tmp_path):
    """Extract all .docx components and validate XML validity via xml.etree.ElementTree."""
    doc_path = tmp_path / "adversarial_report.docx"
    builder = DocxReportBuilder(title="Adversarial Security Audit")
    builder.add_title("SYSTEM AUDIT REPORT", subtitle="Automated Milestone 5 OpenXML Verification")
    builder.add_heading("Section 1: Data Analytics", level=1)
    builder.add_paragraph("Testing standard paragraph with formatting.", bold=True, italic=True, color="2E75B6")
    builder.add_bullet("Bullet item alpha")
    builder.add_bullet("Bullet item beta")
    builder.add_callout("This is a high-priority executive callout notification.", title="CRITICAL ALERT")
    builder.add_table(
        headers=["Component", "Status", "Risk Level"],
        rows=[
            ["Biometrics Gate", "ACTIVE", "LOW"],
            ["Smart Home Hub", "OPERATIONAL", "LOW"],
            ["Watchdog Daemon", "RUNNING", "LOW"],
        ],
        header_bg="1F4E79",
    )
    builder.save(doc_path)

    assert doc_path.exists()
    assert doc_path.stat().st_size > 0

    with zipfile.ZipFile(doc_path, "r") as z:
        namelist = z.namelist()
        expected_files = [
            "[Content_Types].xml",
            "_rels/.rels",
            "word/_rels/document.xml.rels",
            "word/styles.xml",
            "word/document.xml",
        ]
        for ef in expected_files:
            assert ef in namelist, f"Missing required OpenXML part: {ef}"

        for fname in namelist:
            if fname.endswith(".xml") or fname.endswith(".rels"):
                content = z.read(fname)
                root = ET.fromstring(content)
                assert root is not None, f"Failed to parse XML in {fname}"

        ct_root = ET.fromstring(z.read("[Content_Types].xml"))
        assert ct_root.tag.endswith("Types")
        overrides = {elem.attrib.get("PartName"): elem.attrib.get("ContentType") for elem in ct_root.findall("{http://schemas.openxmlformats.org/package/2006/content-types}Override")}
        assert "/word/document.xml" in overrides
        assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" in overrides["/word/document.xml"]

        doc_root = ET.fromstring(z.read("word/document.xml"))
        assert doc_root.tag.endswith("document")
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        body = doc_root.find("w:body", ns)
        assert body is not None


def test_adversarial_xml_injection_escaping(tmp_path):
    """Verify that raw XML tags and dangerous injection characters in text do not break XML parsing."""
    doc_path = tmp_path / "injection_test.docx"
    builder = DocxReportBuilder(title="Security Injection Test")
    
    malicious_strings = [
        "<script>alert('xss')</script>",
        "</w:t></w:r><w:r><w:t>Injected Run",
        "& < > \" ' -- / ? % # @ ! ^ * ( ) [ ] { }",
        "Báo cáo kiểm tra thống kê: Dữ liệu đạt 99.9% & không có lỗi <0.001!",
        "Unicode emojis and special characters: [STAR] [SHIELD] [FIRE]",
    ]

    builder.add_title(malicious_strings[0])
    for s in malicious_strings:
        builder.add_paragraph(s)
        builder.add_bullet(s)
        builder.add_callout(s)

    builder.add_table(
        headers=["Header & <Tag>", "Value \"Quoted\""],
        rows=[[s, s] for s in malicious_strings],
    )
    builder.save(doc_path)

    with zipfile.ZipFile(doc_path, "r") as z:
        doc_xml = z.read("word/document.xml")
        root = ET.fromstring(doc_xml)
        assert root is not None


# ============================================================================
# SECTION 6: PDF REPORT EXPORTER & HEADER VERIFICATION
# ============================================================================

def test_adversarial_pdf_header_and_binary_structure(tmp_path):
    """Verify PDF 1.4 header, xref table, and EOF marker."""
    pdf_path = tmp_path / "audit.pdf"
    builder = PdfReportBuilder(title="Audit Report")
    builder.add_title("JARVIS ADVANCED PDF TEST")
    builder.add_heading("Executive Summary", level=1)
    builder.add_paragraph("Automated verification of PDF generation without external C-extensions.")
    builder.add_table(
        headers=["Metric", "Target", "Actual", "Result"],
        rows=[
            ["VaR 95%", "<= 15.0", "8.45", "PASS"],
            ["CVaR 95%", "<= 20.0", "11.20", "PASS"],
            ["Kurtosis", "< 3.0", "-0.45", "PASS"],
        ]
    )
    builder.save(pdf_path)

    assert pdf_path.exists()
    raw_bytes = pdf_path.read_bytes()
    assert raw_bytes.startswith(b"%PDF-1.4\n")
    assert b"%%EOF\n" in raw_bytes
    assert b"/Type /Catalog" in raw_bytes
    assert b"/Type /Pages" in raw_bytes
    assert b"xref\n" in raw_bytes


def test_adversarial_voice_summary_generator_multi_format():
    """Verify Vietnamese voice summary generation across complete stats, simulation, anomalies, and trend."""
    stats = DescriptiveStats(
        column_name="revenue",
        count=100,
        missing_count=0,
        mean=150.75,
        std=25.5,
        variance=650.25,
        std_err=2.55,
        min=95.0,
        max=220.0,
        range=125.0,
        median=149.0,
        p25=132.0,
        p75=168.0,
        iqr=36.0,
        skewness=0.15,
        kurtosis=-0.22,
    )
    sim = MonteCarloResult(
        iterations=5000,
        mean=160.0,
        std_err=0.35,
        p5=120.0,
        p50=159.0,
        p95=205.0,
        prob_target=85.0,
        var_95=30.0,
        var_99=45.0,
        cvar_95=38.0,
    )
    anomalies = AnomalyReport(
        column_name="revenue",
        method="zscore",
        total_anomalies=2,
        anomalies=[],
    )
    trend = TrendResult(
        column_name="revenue",
        slope=1.55,
        intercept=75.0,
        r_squared=0.88,
        direction="INCREASING",
        cagr_percent=12.4,
    )

    gen = VoiceSummaryGenerator()
    summary = gen.generate_summary("q4_revenue.csv", stats, sim, anomalies, trend)

    assert "Đã hoàn thành phân tích" in summary
    assert "150.75" in summary
    assert "149.00" in summary
    assert "85.0%" in summary
    assert "2 điểm dữ liệu bất thường" in summary
    assert "tăng trưởng" in summary
