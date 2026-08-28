"""
jarvis/data/stats.py
====================
Tabular Dataset Ingestion (CSV, Pure XML XLSX), Descriptive Statistics,
Correlation Matrices, Anomaly Detection, OLS Regression, and 4-Distribution Monte Carlo Engine.
Covers Features:
  - F-28: Data Ingestion & Stats Engine (CSV/XLSX parsing, descriptive statistics & anomalies)
  - F-29: Monte Carlo Simulation Module (Normal, Lognormal, Uniform, Triangular distributions & VaR)
"""
from __future__ import annotations

import csv
import io
import math
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np


class DistributionType(str, Enum):
    NORMAL = "normal"
    LOGNORMAL = "lognormal"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"
    EXPONENTIAL = "exponential"


@dataclass
class DataStatsReport:
    """Backward-compatible lightweight stats report."""
    count: int
    mean: float
    std: float
    median: float
    p25: float
    p75: float


@dataclass
class DescriptiveStats:
    """Comprehensive descriptive statistics for a single numeric column."""
    column_name: str
    count: int
    missing_count: int
    mean: float
    std: float
    variance: float
    std_err: float
    min: float
    max: float
    range: float
    median: float
    p25: float
    p75: float
    iqr: float
    skewness: float
    kurtosis: float


@dataclass
class CorrelationResult:
    """Pearson and Spearman correlation matrices across tabular columns."""
    columns: list[str]
    pearson_matrix: list[list[float]]
    spearman_matrix: list[list[float]]


@dataclass
class AnomalyItem:
    """Single flagged anomalous data point."""
    index: int
    value: float
    score: float
    reason: str


@dataclass
class AnomalyReport:
    """Detailed anomaly report for a column."""
    column_name: str
    method: str
    total_anomalies: int
    anomalies: list[AnomalyItem]


@dataclass
class TrendResult:
    """Ordinary Least Squares trend analysis and compound growth rate."""
    column_name: str
    slope: float
    intercept: float
    r_squared: float
    direction: str  # INCREASING, DECREASING, STABLE
    cagr_percent: float | None


@dataclass
class MonteCarloConfig:
    """Configuration for Monte Carlo probabilistic simulation."""
    distribution: DistributionType = DistributionType.NORMAL
    initial_value: float = 100.0
    iterations: int = 5000
    mean_return: float = 0.05
    volatility: float = 0.15
    target_value: float | None = 110.0
    triangular_low: float | None = None
    triangular_high: float | None = None
    triangular_mode: float | None = None
    uniform_low: float | None = None
    uniform_high: float | None = None
    random_seed: int | None = 42


@dataclass
class MonteCarloResult:
    """Simulation outcomes, confidence percentiles, and Value-at-Risk metrics."""
    iterations: int
    mean: float
    std_err: float
    p5: float
    p50: float
    p95: float
    prob_target: float
    distribution: str = "normal"
    std_dev: float = 0.0
    min: float = 0.0
    max: float = 0.0
    p1: float = 0.0
    p10: float = 0.0
    p25: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p99: float = 0.0
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0


class TabularDataset:
    """Represents a structured 2D tabular dataset."""

    def __init__(self, headers: list[str], rows: list[list[Any]]):
        self.headers: list[str] = headers
        self.rows: list[list[Any]] = rows
        self.numeric_columns: dict[str, np.ndarray] = {}
        self._extract_numeric_columns()

    def _extract_numeric_columns(self) -> None:
        """Identifies columns containing numeric values and stores as float64 ndarrays."""
        if not self.headers or not self.rows:
            return

        for col_idx, col_name in enumerate(self.headers):
            values = []
            for row in self.rows:
                if col_idx < len(row):
                    raw_val = row[col_idx]
                    if raw_val is not None and raw_val != "":
                        try:
                            # Strip commas/currency symbols if present
                            clean_str = str(raw_val).strip().replace(",", "").replace("$", "").replace("%", "")
                            val = float(clean_str)
                            if not math.isnan(val) and not math.isinf(val):
                                values.append(val)
                        except (ValueError, TypeError):
                            pass
            if len(values) > 0 and len(values) >= len(self.rows) * 0.4:
                self.numeric_columns[col_name] = np.array(values, dtype=np.float64)


class DataAnalyticsEngine:
    """Statistical analytics engine for CSV and XLSX files."""

    def load_csv(self, file_path: str | Path) -> TabularDataset:
        """Parses CSV with delimiter sniffing, comment stripping, and type inference."""
        p = Path(file_path)
        if not p.exists() or p.stat().st_size == 0:
            raise ValueError(f"CSV file is empty or missing: {p}")

        content = p.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            raise ValueError(f"CSV file is empty: {p}")

        # Sniff delimiter
        sample = content[:4096]
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
        except Exception:
            for d in [",", "\t", ";", "|"]:
                if d in sample:
                    delimiter = d
                    break

        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]
        if not rows:
            raise ValueError(f"No valid data rows found in {p}")

        headers = [h.strip() for h in rows[0]]
        data_rows = rows[1:] if len(rows) > 1 else []
        return TabularDataset(headers=headers, rows=data_rows)

    def load_xlsx(self, file_path: str | Path, sheet_index: int = 0) -> TabularDataset:
        """Pure-Python standard-library XLSX reader using zipfile + xml.etree.ElementTree."""
        p = Path(file_path)
        if not p.exists() or p.stat().st_size == 0:
            raise ValueError(f"XLSX file is empty or missing: {p}")

        with zipfile.ZipFile(p, "r") as z:
            # 1. Read shared strings
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                xml_content = z.read("xl/sharedStrings.xml")
                root = ET.fromstring(xml_content)
                ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for si in root.findall(".//main:si", ns) or root.findall(".//si"):
                    texts = [t.text or "" for t in (si.findall(".//main:t", ns) or si.findall(".//t"))]
                    shared_strings.append("".join(texts))

            # 2. Find sheet
            sheet_name = f"xl/worksheets/sheet{sheet_index + 1}.xml"
            if sheet_name not in z.namelist():
                # Find any sheet
                sheets = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
                if not sheets:
                    raise ValueError(f"No worksheets found in {p}")
                sheet_name = sheets[0]

            sheet_xml = z.read(sheet_name)
            sheet_root = ET.fromstring(sheet_xml)
            ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

            rows_data: list[list[Any]] = []
            row_elements = sheet_root.findall(".//main:row", ns) or sheet_root.findall(".//row")

            for r in row_elements:
                c_elements = r.findall(".//main:c", ns) or r.findall(".//c")
                row_vals: dict[int, Any] = {}
                max_col = 0
                for c in c_elements:
                    r_attr = c.attrib.get("r", "A1")
                    # Parse column index from e.g. "B3" -> col 1
                    col_letters = "".join(filter(str.isalpha, r_attr)).upper()
                    col_idx = 0
                    for char in col_letters:
                        col_idx = col_idx * 26 + (ord(char) - ord("A") + 1)
                    col_idx -= 1  # 0-indexed
                    max_col = max(max_col, col_idx)

                    t_attr = c.attrib.get("t", "")
                    v_elem = c.find(".//main:v", ns) or c.find(".//v")
                    raw_val = v_elem.text if v_elem is not None else ""

                    if t_attr == "s" and raw_val.isdigit():
                        idx = int(raw_val)
                        val = shared_strings[idx] if idx < len(shared_strings) else ""
                    else:
                        val = raw_val

                    row_vals[col_idx] = val

                row_list = [row_vals.get(i, "") for i in range(max_col + 1)]
                if any(str(x).strip() for x in row_list):
                    rows_data.append(row_list)

        if not rows_data:
            raise ValueError(f"No rows could be read from sheet in {p}")

        headers = [str(h).strip() for h in rows_data[0]]
        data_rows = rows_data[1:] if len(rows_data) > 1 else []
        return TabularDataset(headers=headers, rows=data_rows)

    def compute_statistics_from_csv(
        self,
        file_path: Path,
        column: str = "value",
    ) -> DataStatsReport:
        """Backward-compatible descriptive statistics calculator."""
        dataset = self.load_csv(file_path)
        if column not in dataset.numeric_columns:
            # Fallback search case-insensitive
            match = next((k for k in dataset.numeric_columns if k.lower() == column.lower()), None)
            if not match:
                raise ValueError(f"No numeric values found for column '{column}'")
            column = match

        arr = dataset.numeric_columns[column]
        if len(arr) == 0:
            raise ValueError(f"No numeric values found for column '{column}'")

        return DataStatsReport(
            count=len(arr),
            mean=float(np.mean(arr)),
            std=float(np.std(arr)),
            median=float(np.median(arr)),
            p25=float(np.percentile(arr, 25)),
            p75=float(np.percentile(arr, 75)),
        )

    def compute_statistics(self, dataset: TabularDataset, column: str) -> DescriptiveStats:
        """Computes comprehensive descriptive statistics with Bessel's correction, skewness, and kurtosis."""
        if column not in dataset.numeric_columns:
            raise ValueError(f"Numeric column '{column}' not found in dataset")

        arr = dataset.numeric_columns[column]
        n = len(arr)
        if n == 0:
            raise ValueError(f"Column '{column}' has zero valid numeric samples")

        mean_val = float(np.mean(arr))
        var_val = float(np.var(arr, ddof=1)) if n > 1 else 0.0
        std_val = float(np.std(arr, ddof=1)) if n > 1 else 0.0
        std_err = float(std_val / math.sqrt(n)) if n > 0 else 0.0

        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        range_val = max_val - min_val

        median_val = float(np.median(arr))
        p25 = float(np.percentile(arr, 25))
        p75 = float(np.percentile(arr, 75))
        iqr_val = p75 - p25

        # Moments for skewness and kurtosis
        diff = arr - mean_val
        m2 = float(np.mean(diff**2))
        m3 = float(np.mean(diff**3))
        m4 = float(np.mean(diff**4))

        if m2 > 1e-12 and n >= 3:
            g1 = m3 / (m2**1.5)
            skew_val = float((math.sqrt(n * (n - 1)) / (n - 2)) * g1)
        else:
            skew_val = 0.0

        if m2 > 1e-12 and n >= 4:
            g2 = (m4 / (m2**2)) - 3.0
            kurt_val = float(((n - 1) / ((n - 2) * (n - 3))) * ((n + 1) * g2 + 6.0))
        else:
            kurt_val = 0.0

        total_rows = len(dataset.rows)
        missing_count = max(0, total_rows - n)

        return DescriptiveStats(
            column_name=column,
            count=n,
            missing_count=missing_count,
            mean=mean_val,
            std=std_val,
            variance=var_val,
            std_err=std_err,
            min=min_val,
            max=max_val,
            range=range_val,
            median=median_val,
            p25=p25,
            p75=p75,
            iqr=iqr_val,
            skewness=skew_val,
            kurtosis=kurt_val,
        )

    def compute_all_statistics(self, dataset: TabularDataset) -> dict[str, DescriptiveStats]:
        """Computes descriptive stats across all numeric columns."""
        res = {}
        for col in dataset.numeric_columns.keys():
            res[col] = self.compute_statistics(dataset, col)
        return res

    def compute_correlation_matrix(self, dataset: TabularDataset) -> CorrelationResult:
        """Calculates Pearson and Spearman rank correlation matrices across all numeric columns."""
        cols = list(dataset.numeric_columns.keys())
        k = len(cols)
        if k == 0:
            return CorrelationResult(columns=[], pearson_matrix=[], spearman_matrix=[])

        # Align series to common length
        min_len = min(len(dataset.numeric_columns[c]) for c in cols)
        matrix_data = np.column_stack([dataset.numeric_columns[c][:min_len] for c in cols])

        # Pearson correlation
        pearson_mat = np.zeros((k, k), dtype=np.float64)
        for i in range(k):
            for j in range(k):
                if i == j:
                    pearson_mat[i, j] = 1.0
                else:
                    x, y = matrix_data[:, i], matrix_data[:, j]
                    std_x, std_y = np.std(x), np.std(y)
                    if std_x > 1e-9 and std_y > 1e-9:
                        r = float(np.corrcoef(x, y)[0, 1])
                        pearson_mat[i, j] = float(np.clip(r, -1.0, 1.0))
                    else:
                        pearson_mat[i, j] = 0.0

        # Spearman rank correlation
        spearman_mat = np.zeros((k, k), dtype=np.float64)
        # Convert matrix to ranks
        rank_data = np.zeros_like(matrix_data)
        for c_idx in range(k):
            col_v = matrix_data[:, c_idx]
            order = col_v.argsort()
            ranks = order.argsort().astype(np.float64) + 1.0
            rank_data[:, c_idx] = ranks

        for i in range(k):
            for j in range(k):
                if i == j:
                    spearman_mat[i, j] = 1.0
                else:
                    rx, ry = rank_data[:, i], rank_data[:, j]
                    std_rx, std_ry = np.std(rx), np.std(ry)
                    if std_rx > 1e-9 and std_ry > 1e-9:
                        rs = float(np.corrcoef(rx, ry)[0, 1])
                        spearman_mat[i, j] = float(np.clip(rs, -1.0, 1.0))
                    else:
                        spearman_mat[i, j] = 0.0

        return CorrelationResult(
            columns=cols,
            pearson_matrix=pearson_mat.tolist(),
            spearman_matrix=spearman_mat.tolist(),
        )

    def detect_anomalies(
        self,
        dataset: TabularDataset,
        column: str,
        method: str = "zscore",
        threshold: float = 3.0,
    ) -> AnomalyReport:
        """Detects outliers using Z-score or Tukey IQR fences."""
        if column not in dataset.numeric_columns:
            raise ValueError(f"Numeric column '{column}' not found")

        arr = dataset.numeric_columns[column]
        anomalies: list[AnomalyItem] = []

        if method.lower() == "iqr":
            q25 = float(np.percentile(arr, 25))
            q75 = float(np.percentile(arr, 75))
            iqr = q75 - q25
            lower_fence = q25 - threshold * iqr
            upper_fence = q75 + threshold * iqr

            for idx, val in enumerate(arr):
                if val < lower_fence or val > upper_fence:
                    diff = abs(val - (q75 if val > upper_fence else q25)) / max(iqr, 1e-6)
                    anomalies.append(
                        AnomalyItem(
                            index=idx,
                            value=float(val),
                            score=float(diff),
                            reason=f"Exceeded Tukey IQR fence [{lower_fence:.2f}, {upper_fence:.2f}]",
                        )
                    )
        else:  # zscore
            mean = float(np.mean(arr))
            std = float(np.std(arr))
            if std > 1e-9:
                z_scores = np.abs((arr - mean) / std)
                for idx, (val, z) in enumerate(zip(arr, z_scores)):
                    if z > threshold:
                        anomalies.append(
                            AnomalyItem(
                                index=idx,
                                value=float(val),
                                score=float(z),
                                reason=f"Z-Score {z:.2f} > threshold {threshold:.2f}",
                            )
                        )

        return AnomalyReport(
            column_name=column,
            method=method,
            total_anomalies=len(anomalies),
            anomalies=anomalies,
        )

    def analyze_trend(self, dataset: TabularDataset, column: str) -> TrendResult:
        """Computes OLS linear regression and CAGR trend direction."""
        if column not in dataset.numeric_columns:
            raise ValueError(f"Numeric column '{column}' not found")

        y = dataset.numeric_columns[column]
        n = len(y)
        if n < 2:
            return TrendResult(column_name=column, slope=0.0, intercept=float(y[0]) if n == 1 else 0.0, r_squared=0.0, direction="STABLE", cagr_percent=None)

        x = np.arange(n, dtype=np.float64)
        mean_x = float(np.mean(x))
        mean_y = float(np.mean(y))

        cov_xy = float(np.sum((x - mean_x) * (y - mean_y)))
        var_x = float(np.sum((x - mean_x) ** 2))

        slope = cov_xy / var_x if var_x > 1e-9 else 0.0
        intercept = mean_y - slope * mean_x

        y_pred = slope * x + intercept
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - mean_y) ** 2))
        r_squared = float(1.0 - (ss_res / ss_tot)) if ss_tot > 1e-9 else 0.0

        # CAGR
        cagr = None
        if y[0] > 0 and y[-1] > 0 and n > 1:
            try:
                cagr = float(((y[-1] / y[0]) ** (1.0 / (n - 1)) - 1.0) * 100.0)
            except Exception:
                cagr = None

        if slope > 0.001 and r_squared >= 0.10:
            direction = "INCREASING"
        elif slope < -0.001 and r_squared >= 0.10:
            direction = "DECREASING"
        else:
            direction = "STABLE"

        return TrendResult(
            column_name=column,
            slope=slope,
            intercept=intercept,
            r_squared=float(np.clip(r_squared, 0.0, 1.0)),
            direction=direction,
            cagr_percent=cagr,
        )


class MonteCarloEngine:
    """Probabilistic simulation coordinator supporting Normal, Lognormal, Uniform, and Triangular distributions."""

    def run_simulation(
        self,
        initial_value: float = 100.0,
        iterations: int = 5000,
        mean_return: float = 0.05,
        volatility: float = 0.15,
        target_value: float = 110.0,
        distribution: str | DistributionType = DistributionType.NORMAL,
        triangular_low: float | None = None,
        triangular_high: float | None = None,
        triangular_mode: float | None = None,
        uniform_low: float | None = None,
        uniform_high: float | None = None,
        random_seed: int | None = 42,
    ) -> MonteCarloResult:
        """Executes Monte Carlo simulation and computes risk percentiles."""
        if iterations < 1000:
            raise ValueError("Iterations must be >= 1000")
        if volatility <= 0:
            raise ValueError("Volatility must be > 0")

        if random_seed is not None:
            np.random.seed(random_seed)

        dist_str = distribution.value if isinstance(distribution, DistributionType) else str(distribution).lower()

        # Generate returns
        if dist_str == DistributionType.LOGNORMAL.value:
            sigma_ln = math.sqrt(math.log(1.0 + (volatility**2 / max(0.001, (1.0 + mean_return)**2))))
            mu_ln = math.log(max(0.001, 1.0 + mean_return)) - 0.5 * sigma_ln**2
            multipliers = np.random.lognormal(mu_ln, sigma_ln, iterations)
            final_values = initial_value * multipliers
        elif dist_str == DistributionType.UNIFORM.value:
            low_u = uniform_low if uniform_low is not None else (mean_return - math.sqrt(3) * volatility)
            high_u = uniform_high if uniform_high is not None else (mean_return + math.sqrt(3) * volatility)
            returns = np.random.uniform(low_u, high_u, iterations)
            final_values = initial_value * (1.0 + returns)
        elif dist_str == DistributionType.TRIANGULAR.value:
            t_low = triangular_low if triangular_low is not None else (mean_return - 2 * volatility)
            t_high = triangular_high if triangular_high is not None else (mean_return + 2 * volatility)
            t_mode = triangular_mode if triangular_mode is not None else mean_return
            returns = np.random.triangular(t_low, t_mode, t_high, iterations)
            final_values = initial_value * (1.0 + returns)
        else:  # Normal default
            returns = np.random.normal(mean_return, volatility, iterations)
            final_values = initial_value * (1.0 + returns)

        mean_val = float(np.mean(final_values))
        std_dev = float(np.std(final_values))
        std_err = float(std_dev / math.sqrt(iterations))

        p1 = float(np.percentile(final_values, 1))
        p5 = float(np.percentile(final_values, 5))
        p10 = float(np.percentile(final_values, 10))
        p25 = float(np.percentile(final_values, 25))
        p50 = float(np.percentile(final_values, 50))
        p75 = float(np.percentile(final_values, 75))
        p90 = float(np.percentile(final_values, 90))
        p95 = float(np.percentile(final_values, 95))
        p99 = float(np.percentile(final_values, 99))

        prob_target = float(np.mean(final_values >= target_value)) * 100.0

        # VaR and CVaR calculations
        var_95 = max(0.0, float(initial_value - p5))
        var_99 = max(0.0, float(initial_value - p1))

        tail_values = final_values[final_values <= p5]
        cvar_95 = max(0.0, float(initial_value - np.mean(tail_values))) if len(tail_values) > 0 else var_95

        return MonteCarloResult(
            iterations=iterations,
            distribution=dist_str,
            mean=mean_val,
            std_dev=std_dev,
            std_err=std_err,
            min=float(np.min(final_values)),
            max=float(np.max(final_values)),
            p1=p1,
            p5=p5,
            p10=p10,
            p25=p25,
            p50=p50,
            p75=p75,
            p90=p90,
            p95=p95,
            p99=p99,
            prob_target=prob_target,
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
        )
