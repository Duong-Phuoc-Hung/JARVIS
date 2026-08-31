"""
jarvis/data/analysis_service.py
=================================
Thin, deterministic facade over jarvis.data.stats (DataAnalyticsEngine,
MonteCarloEngine) with structured request/result models and a bounded,
safe chart-specification/rendering path.

Deliberately independent of jarvis.llm.router — this module only maps a
structured DataAnalysisRequest to one of a fixed set of deterministic
operations. No dynamic code evaluation, no shell commands, no
LLM-generated code execution. A later phase may map natural language onto
these structured operations; that mapping does not live here.

matplotlib is an optional, lazily-imported dependency (see pyproject.toml
`charts` extra). When it isn't installed, render_chart() still returns a
ChartSpec (the deterministic, structured chart description) with
rendered=False rather than raising — headless-safe by construction.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from jarvis.data.stats import (
    AnomalyReport,
    CorrelationResult,
    DataAnalyticsEngine,
    DescriptiveStats,
    MonteCarloConfig,
    MonteCarloEngine,
    MonteCarloResult,
    TabularDataset,
    TrendResult,
)

DEFAULT_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class AnalysisOperation(str, Enum):
    """The fixed set of structured operations this service supports."""
    DESCRIBE = "describe"
    CORRELATION = "correlation"
    ANOMALY = "anomaly"
    TREND = "trend"
    MONTE_CARLO = "monte_carlo"
    CHART = "chart"


class UnsupportedOperationError(ValueError):
    """Raised when a DataAnalysisRequest names an operation this service does not implement."""


class FileTooLargeError(ValueError):
    """Raised when an input file exceeds the configured bound."""


@dataclass
class DataAnalysisRequest:
    """Structured request for one supported analysis operation."""
    operation: AnalysisOperation
    file_path: str | Path | None = None
    column: str | None = None
    method: str = "zscore"
    threshold: float = 3.0
    monte_carlo_config: MonteCarloConfig | None = None
    chart_spec: ChartSpec | None = None


@dataclass
class DataAnalysisResult:
    """Structured, uniform outcome for any supported operation."""
    operation: AnalysisOperation
    success: bool
    data: Any = None
    error: str | None = None


@dataclass
class ChartSeries:
    """One named data series for a chart (deterministic, plotting-library-agnostic)."""
    name: str
    x: list[Any]
    y: list[float]


@dataclass
class ChartSpec:
    """
    Deterministic, structured description of a chart. Independent of any
    plotting library — can be produced, inspected, and asserted on in tests
    even when matplotlib is not installed.
    """
    chart_type: str  # "line" | "bar" | "scatter" | "hist"
    title: str
    x_label: str
    y_label: str
    series: list[ChartSeries] = field(default_factory=list)


@dataclass
class ChartRenderResult:
    """Outcome of attempting to render a ChartSpec to an image."""
    spec: ChartSpec
    rendered: bool
    image_bytes: bytes | None = None
    image_format: str = "png"
    error: str | None = None


_SUPPORTED_CHART_TYPES = frozenset({"line", "bar", "scatter", "hist"})


class DataAnalysisService:
    """
    Facade exposing the existing DataAnalyticsEngine/MonteCarloEngine
    through structured request/result models, with bounded file handling
    and clear, typed errors for unsupported operations.
    """

    def __init__(
        self,
        engine: DataAnalyticsEngine | None = None,
        monte_carlo_engine: MonteCarloEngine | None = None,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> None:
        self.engine = engine or DataAnalyticsEngine()
        self.monte_carlo_engine = monte_carlo_engine or MonteCarloEngine()
        self.max_file_size_bytes = int(max_file_size_bytes)

    # -- Bounded file loading ---------------------------------------------

    def _check_file_bounds(self, file_path: str | Path) -> Path:
        p = Path(file_path)
        if not p.exists():
            raise ValueError(f"File does not exist: {p}")
        size = p.stat().st_size
        if size > self.max_file_size_bytes:
            raise FileTooLargeError(
                f"File {p} is {size} bytes, exceeding the {self.max_file_size_bytes}-byte limit"
            )
        return p

    def _load_dataset(self, file_path: str | Path) -> TabularDataset:
        p = self._check_file_bounds(file_path)
        suffix = p.suffix.lower()
        if suffix == ".csv":
            return self.engine.load_csv(p)
        if suffix in (".xlsx", ".xlsm"):
            return self.engine.load_xlsx(p)
        raise UnsupportedOperationError(f"Unsupported file type: {suffix}")

    # -- Structured operations ----------------------------------------------

    def describe(self, file_path: str | Path, column: str | None = None) -> DataAnalysisResult:
        try:
            dataset = self._load_dataset(file_path)
            data: DescriptiveStats | dict[str, DescriptiveStats]
            if column is not None:
                data = self.engine.compute_statistics(dataset, column)
            else:
                data = self.engine.compute_all_statistics(dataset)
            return DataAnalysisResult(operation=AnalysisOperation.DESCRIBE, success=True, data=data)
        except Exception as exc:
            return DataAnalysisResult(operation=AnalysisOperation.DESCRIBE, success=False, error=str(exc))

    def correlation(self, file_path: str | Path) -> DataAnalysisResult:
        try:
            dataset = self._load_dataset(file_path)
            data: CorrelationResult = self.engine.compute_correlation_matrix(dataset)
            return DataAnalysisResult(operation=AnalysisOperation.CORRELATION, success=True, data=data)
        except Exception as exc:
            return DataAnalysisResult(operation=AnalysisOperation.CORRELATION, success=False, error=str(exc))

    def detect_anomalies(
        self,
        file_path: str | Path,
        column: str,
        method: str = "zscore",
        threshold: float = 3.0,
    ) -> DataAnalysisResult:
        try:
            dataset = self._load_dataset(file_path)
            data: AnomalyReport = self.engine.detect_anomalies(dataset, column, method=method, threshold=threshold)
            return DataAnalysisResult(operation=AnalysisOperation.ANOMALY, success=True, data=data)
        except Exception as exc:
            return DataAnalysisResult(operation=AnalysisOperation.ANOMALY, success=False, error=str(exc))

    def trend(self, file_path: str | Path, column: str) -> DataAnalysisResult:
        try:
            dataset = self._load_dataset(file_path)
            data: TrendResult = self.engine.analyze_trend(dataset, column)
            return DataAnalysisResult(operation=AnalysisOperation.TREND, success=True, data=data)
        except Exception as exc:
            return DataAnalysisResult(operation=AnalysisOperation.TREND, success=False, error=str(exc))

    def monte_carlo(self, config: MonteCarloConfig) -> DataAnalysisResult:
        try:
            data: MonteCarloResult = self.monte_carlo_engine.run_simulation(
                initial_value=config.initial_value,
                iterations=config.iterations,
                mean_return=config.mean_return,
                volatility=config.volatility,
                target_value=config.target_value if config.target_value is not None else config.initial_value,
                distribution=config.distribution,
                triangular_low=config.triangular_low,
                triangular_high=config.triangular_high,
                triangular_mode=config.triangular_mode,
                uniform_low=config.uniform_low,
                uniform_high=config.uniform_high,
                random_seed=config.random_seed,
            )
            return DataAnalysisResult(operation=AnalysisOperation.MONTE_CARLO, success=True, data=data)
        except Exception as exc:
            return DataAnalysisResult(operation=AnalysisOperation.MONTE_CARLO, success=False, error=str(exc))

    # -- Chart specification / safe rendering --------------------------------

    def build_chart_spec(
        self,
        chart_type: str,
        title: str,
        x_label: str,
        y_label: str,
        series: list[ChartSeries],
    ) -> ChartSpec:
        """Build a deterministic ChartSpec. Raises UnsupportedOperationError for an unknown chart_type."""
        if chart_type not in _SUPPORTED_CHART_TYPES:
            raise UnsupportedOperationError(
                f"Unsupported chart_type '{chart_type}'; supported: {sorted(_SUPPORTED_CHART_TYPES)}"
            )
        return ChartSpec(chart_type=chart_type, title=title, x_label=x_label, y_label=y_label, series=list(series))

    def render_chart(self, spec: ChartSpec) -> ChartRenderResult:
        """
        Render a ChartSpec to a PNG image using matplotlib's headless Agg
        backend, if matplotlib is installed. Never raises: returns
        rendered=False with an explanatory error when matplotlib is
        unavailable or rendering fails.
        """
        try:
            import matplotlib
            matplotlib.use("Agg", force=True)
            import matplotlib.pyplot as plt
        except ImportError:
            return ChartRenderResult(
                spec=spec, rendered=False, error="matplotlib is not installed (optional 'charts' extra)"
            )

        fig = None
        try:
            fig, ax = plt.subplots()
            for s in spec.series:
                if spec.chart_type == "line":
                    ax.plot(s.x, s.y, label=s.name)
                elif spec.chart_type == "bar":
                    ax.bar(s.x, s.y, label=s.name)
                elif spec.chart_type == "scatter":
                    ax.scatter(s.x, s.y, label=s.name)
                elif spec.chart_type == "hist":
                    ax.hist(s.y, label=s.name)

            ax.set_title(spec.title)
            ax.set_xlabel(spec.x_label)
            ax.set_ylabel(spec.y_label)
            if spec.series:
                ax.legend()

            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            return ChartRenderResult(spec=spec, rendered=True, image_bytes=buf.getvalue(), image_format="png")
        except Exception as exc:
            return ChartRenderResult(spec=spec, rendered=False, error=str(exc))
        finally:
            # Guarantee the figure is released on every path (success or error) so a
            # malformed ChartSpec (e.g. mismatched series lengths) can never leak an
            # open matplotlib figure across repeated render_chart() calls.
            if fig is not None:
                plt.close(fig)

    # -- Single structured dispatch entry point ------------------------------

    def execute(self, request: DataAnalysisRequest) -> DataAnalysisResult:
        """Dispatch a DataAnalysisRequest to the matching operation."""
        if request.operation == AnalysisOperation.DESCRIBE:
            if request.file_path is None:
                raise ValueError("describe requires file_path")
            return self.describe(request.file_path, request.column)
        if request.operation == AnalysisOperation.CORRELATION:
            if request.file_path is None:
                raise ValueError("correlation requires file_path")
            return self.correlation(request.file_path)
        if request.operation == AnalysisOperation.ANOMALY:
            if request.file_path is None or request.column is None:
                raise ValueError("anomaly requires file_path and column")
            return self.detect_anomalies(request.file_path, request.column, request.method, request.threshold)
        if request.operation == AnalysisOperation.TREND:
            if request.file_path is None or request.column is None:
                raise ValueError("trend requires file_path and column")
            return self.trend(request.file_path, request.column)
        if request.operation == AnalysisOperation.MONTE_CARLO:
            if request.monte_carlo_config is None:
                raise ValueError("monte_carlo requires monte_carlo_config")
            return self.monte_carlo(request.monte_carlo_config)
        if request.operation == AnalysisOperation.CHART:
            if request.chart_spec is None:
                raise ValueError("chart requires chart_spec")
            render_result = self.render_chart(request.chart_spec)
            return DataAnalysisResult(
                operation=AnalysisOperation.CHART,
                success=render_result.rendered,
                data=render_result,
                error=render_result.error,
            )

        raise UnsupportedOperationError(f"Unsupported operation: {request.operation}")
