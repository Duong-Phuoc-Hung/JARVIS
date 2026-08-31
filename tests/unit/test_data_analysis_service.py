"""
tests/unit/test_data_analysis_service.py
==========================================
Unit tests for the DataAnalysisService facade (jarvis.data.analysis_service).

Deterministic: uses small CSV fixtures written to tmp_path, a fixed random
seed for Monte Carlo, and never depends on matplotlib being installed
(render_chart() is tested for both the "matplotlib present" and
"matplotlib absent" cases via monkeypatched import failure).
"""
import builtins

import pytest

from jarvis.data.analysis_service import (
    AnalysisOperation,
    ChartSeries,
    DataAnalysisRequest,
    DataAnalysisService,
    FileTooLargeError,
    UnsupportedOperationError,
)
from jarvis.data.stats import DistributionType, MonteCarloConfig


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "sample.csv"
    p.write_text(
        "day,revenue,cost\n"
        "1,100,50\n"
        "2,110,52\n"
        "3,105,51\n"
        "4,120,53\n"
        "5,900,54\n"  # anomalous revenue spike
        "6,130,55\n"
        "7,135,56\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def service():
    return DataAnalysisService()


# --- describe -------------------------------------------------------------

def test_describe_single_column(service, csv_path):
    result = service.describe(csv_path, column="revenue")
    assert result.success is True
    assert result.operation == AnalysisOperation.DESCRIBE
    assert result.data.count == 7
    assert result.data.column_name == "revenue"


def test_describe_all_columns(service, csv_path):
    result = service.describe(csv_path)
    assert result.success is True
    assert set(result.data.keys()) == {"day", "revenue", "cost"}


def test_describe_missing_column_reports_failure(service, csv_path):
    result = service.describe(csv_path, column="does_not_exist")
    assert result.success is False
    assert result.error is not None


def test_describe_missing_file_reports_failure(service, tmp_path):
    result = service.describe(tmp_path / "nope.csv")
    assert result.success is False


# --- correlation ------------------------------------------------------------

def test_correlation_returns_matrix(service, csv_path):
    result = service.correlation(csv_path)
    assert result.success is True
    assert "revenue" in result.data.columns
    assert "cost" in result.data.columns
    n = len(result.data.columns)
    assert len(result.data.pearson_matrix) == n


# --- anomaly detection --------------------------------------------------

def test_detect_anomalies_zscore_flags_spike(service, csv_path):
    result = service.detect_anomalies(csv_path, column="revenue", method="zscore", threshold=1.5)
    assert result.success is True
    assert result.data.total_anomalies >= 1


def test_detect_anomalies_unknown_column_fails(service, csv_path):
    result = service.detect_anomalies(csv_path, column="ghost", method="zscore")
    assert result.success is False


# --- trend ---------------------------------------------------------------

def test_trend_detects_increasing_direction(service, csv_path):
    result = service.trend(csv_path, column="cost")
    assert result.success is True
    assert result.data.direction == "INCREASING"


# --- monte carlo -----------------------------------------------------------

def test_monte_carlo_deterministic_with_seed(service):
    config = MonteCarloConfig(
        distribution=DistributionType.NORMAL,
        initial_value=100.0,
        iterations=2000,
        mean_return=0.05,
        volatility=0.1,
        target_value=110.0,
        random_seed=7,
    )
    r1 = service.monte_carlo(config)
    r2 = service.monte_carlo(config)
    assert r1.success is True
    assert r2.success is True
    assert r1.data.mean == pytest.approx(r2.data.mean)
    assert r1.data.p50 == pytest.approx(r2.data.p50)


def test_monte_carlo_invalid_config_reports_failure(service):
    config = MonteCarloConfig(iterations=10)  # below the engine's minimum of 1000
    result = service.monte_carlo(config)
    assert result.success is False


# --- bounded file handling -------------------------------------------------

def test_file_over_size_limit_is_rejected(tmp_path):
    p = tmp_path / "big.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    tiny_limit_service = DataAnalysisService(max_file_size_bytes=1)  # smaller than the file itself
    result = tiny_limit_service.describe(p)
    assert result.success is False
    assert "exceeding" in result.error or "limit" in result.error


def test_check_file_bounds_raises_file_too_large_error(tmp_path):
    p = tmp_path / "big.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    tiny_limit_service = DataAnalysisService(max_file_size_bytes=1)
    with pytest.raises(FileTooLargeError):
        tiny_limit_service._check_file_bounds(p)


def test_unsupported_file_extension_is_rejected(service, tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("not tabular", encoding="utf-8")
    result = service.describe(p)
    assert result.success is False


# --- chart spec / rendering -------------------------------------------------

def test_build_chart_spec_valid_type(service):
    spec = service.build_chart_spec(
        chart_type="line",
        title="Revenue",
        x_label="Day",
        y_label="USD",
        series=[ChartSeries(name="revenue", x=[1, 2, 3], y=[100.0, 110.0, 105.0])],
    )
    assert spec.chart_type == "line"
    assert spec.series[0].name == "revenue"


def test_build_chart_spec_unsupported_type_raises(service):
    with pytest.raises(UnsupportedOperationError):
        service.build_chart_spec("pie", "T", "X", "Y", [])


def test_render_chart_without_matplotlib_is_graceful(service, monkeypatch):
    spec = service.build_chart_spec("line", "T", "X", "Y", [ChartSeries(name="s", x=[1, 2], y=[1.0, 2.0])])

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "matplotlib":
            raise ImportError("simulated missing matplotlib")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = service.render_chart(spec)
    assert result.rendered is False
    assert result.image_bytes is None
    assert result.error is not None


def test_render_chart_with_matplotlib_produces_png_bytes(service):
    pytest.importorskip("matplotlib")
    spec = service.build_chart_spec(
        "bar", "Revenue", "Day", "USD", [ChartSeries(name="revenue", x=[1, 2, 3], y=[10.0, 20.0, 15.0])]
    )
    result = service.render_chart(spec)
    assert result.rendered is True
    assert result.image_format == "png"
    assert result.image_bytes is not None
    assert result.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_chart_error_path_does_not_leak_figure(service):
    """A rendering error (mismatched series lengths) must still close the figure it opened."""
    plt = pytest.importorskip("matplotlib.pyplot")
    before = len(plt.get_fignums())

    # x has 3 points, y has 2 -> matplotlib raises ValueError inside ax.bar().
    spec = service.build_chart_spec(
        "bar", "Bad", "X", "Y", [ChartSeries(name="broken", x=[1, 2, 3], y=[1.0, 2.0])]
    )
    result = service.render_chart(spec)

    assert result.rendered is False
    assert result.error is not None
    assert len(plt.get_fignums()) == before  # no leaked figure


# --- execute() structured dispatch ------------------------------------------

def test_execute_describe(service, csv_path):
    request = DataAnalysisRequest(operation=AnalysisOperation.DESCRIBE, file_path=csv_path, column="revenue")
    result = service.execute(request)
    assert result.success is True


def test_execute_monte_carlo(service):
    request = DataAnalysisRequest(
        operation=AnalysisOperation.MONTE_CARLO,
        monte_carlo_config=MonteCarloConfig(iterations=1000, random_seed=1),
    )
    result = service.execute(request)
    assert result.success is True


def test_execute_missing_required_field_raises_value_error(service, csv_path):
    request = DataAnalysisRequest(operation=AnalysisOperation.ANOMALY, file_path=csv_path, column=None)
    with pytest.raises(ValueError):
        service.execute(request)


def test_execute_unsupported_operation_raises(service):
    request = DataAnalysisRequest(operation="not_a_real_operation")  # type: ignore[arg-type]
    with pytest.raises(UnsupportedOperationError):
        service.execute(request)


def test_execute_chart_success_reflects_actual_render_outcome(service):
    pytest.importorskip("matplotlib")
    spec = service.build_chart_spec(
        "line", "T", "X", "Y", [ChartSeries(name="s", x=[1, 2], y=[1.0, 2.0])]
    )
    request = DataAnalysisRequest(operation=AnalysisOperation.CHART, chart_spec=spec)
    result = service.execute(request)
    assert result.success is True
    assert result.data.rendered is True


def test_execute_chart_failure_is_not_reported_as_success(service, monkeypatch):
    """A chart render that fails (e.g. matplotlib missing) must surface success=False from execute()."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "matplotlib":
            raise ImportError("simulated missing matplotlib")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    spec = service.build_chart_spec("line", "T", "X", "Y", [ChartSeries(name="s", x=[1, 2], y=[1.0, 2.0])])
    request = DataAnalysisRequest(operation=AnalysisOperation.CHART, chart_spec=spec)
    result = service.execute(request)

    assert result.success is False
    assert result.error is not None
    assert result.data.rendered is False


# --- safety: no eval/exec/shell usage in this module ------------------------

def test_module_source_contains_no_eval_exec_or_shell_calls():
    import inspect

    import jarvis.data.analysis_service as mod

    source = inspect.getsource(mod)
    assert "eval(" not in source
    assert "exec(" not in source
    assert "subprocess" not in source
    assert "os.system" not in source
