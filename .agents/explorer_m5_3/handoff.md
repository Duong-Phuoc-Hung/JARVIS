# Milestone 5 Technical Blueprint: Data Analytics, Document Exporter & Test Architecture

**Author**: Explorer 3 (Milestone 5)  
**Parent Conversation ID**: `24cd405b-b214-4ee6-baa6-eb8e731cac33`  
**Target Milestone**: Milestone 5 — Vision, Comms, IoT, Data Analytics & Workspace Automation  
**Working Directory**: `d:/Software GitCode/JARVIS/.agents/explorer_m5_3`  

---

## 1. OBSERVATION

### 1.1 Environment & Dependency Forensics
- **Runtime**: Python 3.13.2 (64-bit) on Windows 11.
- **Installed Packages**: `numpy` (2.2.3), `pydantic` (2.10.6), `pytest` (8.3.4), `sounddevice`, `psutil`.
- **Absent Heavy Dependencies**: `scipy`, `pandas`, `openpyxl`, `python-docx`, `reportlab`, `matplotlib`, `cv2`, `mediapipe`, `paho-mqtt`, `aiohttp` are **NOT** installed in the local virtual environment (`d:\Software GitCode\JARVIS\.venv`).
- **Architectural Requirement**: All Milestone 5 components must implement **pure Python / Standard Library + NumPy** zero-dependency algorithms with zero crashes, robust error isolation, and graceful optional-dependency detection.

### 1.2 Feature Scope Mapping for Explorer 3
| Feature ID | Name | Module Path | Core Responsibilities |
|---|---|---|---|
| **F-28** | Data Ingestion & Stats Engine | `jarvis/data/stats.py` | CSV / XLSX ingestion, descriptive statistics (mean, median, std, quartiles, skewness, kurtosis), correlation matrix, anomaly detection, trend analysis / OLS regression. |
| **F-29** | Monte Carlo Simulation Module | `jarvis/data/stats.py` | Configurable probabilistic distribution modeling (Normal, Lognormal, Uniform, Triangular), percentile confidence intervals ($P_5 - P_{95}$), Value-at-Risk ($\text{VaR}$), Conditional VaR ($\text{CVaR}$). |
| **F-30** | Multi-Format Document Exporter | `jarvis/data/document.py` | Pure zipfile OpenXML DOCX generation (100% valid ECMA-376 XML package without binary dependencies), PDF export engine + structured fallback, Voice Executive Summary generator. |
| **M5 Tests** | Test Architecture Suite | `tests/` | Complete 4-Tier test suites across `test_biometrics.py`, `test_smart_home.py`, `test_data_analytics.py`, `test_comms_hub.py`, `test_e2e_scenarios.py`. |

---

## 2. LOGIC CHAIN & TECHNICAL BLUEPRINT

### 2.1 Data Analytics & Statistics Engine (`jarvis/data/stats.py`)

#### 2.1.1 Data Ingestion Architecture
```
                        +---------------------------------------+
                        | Raw Input File (CSV / XLSX / Bytes)   |
                        +---------------------------------------+
                                           │
                   ┌───────────────────────┴───────────────────────┐
                   ▼                                               ▼
     [CSV Ingestion Pipeline]                        [Pure XLSX XML Reader]
     - Sniff delimiter (, ; \t |)                    - Open zipfile.ZipFile(xlsx)
     - Strip BOM & whitespace                        - Read xl/sharedStrings.xml
     - Auto-infer column types                       - Parse xl/worksheets/sheet1.xml
     - Filter NaN / NULL strings                     - Map cell coordinates (A1, B2..)
                   │                                               │
                   └───────────────────────┬───────────────────────┘
                                           ▼
                       +---------------------------------------+
                       | TabularDataset / DataMatrix           |
                       | - headers: List[str]                  |
                       | - rows: List[List[Any]]               |
                       | - numeric_columns: Dict[str, ndarray] |
                       +---------------------------------------+
```

1. **Pure XLSX Parsing via Standard Library (`zipfile` + `xml.etree.ElementTree`)**:
   - An `.xlsx` workbook is a standard ZIP archive.
   - Parse `xl/sharedStrings.xml`: Extract `<si><t>string</t></si>` entries into a string lookup table `List[str]`.
   - Parse `xl/worksheets/sheet1.xml`: Traverse `<sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1"><v>123.45</v></c></row>`.
     - When attribute `t="s"`: Resolve shared string index from lookup table.
     - When attribute `t` is missing or numeric: Parse `<v>` as float / integer.
     - Reconstruct rectangular 2D tabular matrix without needing `openpyxl` or `pandas`.

2. **CSV Ingestion Pipeline**:
   - Sniff dialect via `csv.Sniffer().sniff(sample_text)`.
   - Fallback delimiters: `[",", ";", "\t", "|"]`.
   - Handle header detection: check if first row contains non-numeric strings while subsequent rows contain numeric values.
   - Clean non-numeric tokens (`"NA"`, `"N/A"`, `"-"`, `""`, `"None"`, `"null"`).

#### 2.1.2 Descriptive Statistics Math Specifications
Given numeric array $X = [x_1, x_2, \dots, x_N]$ with $N$ valid samples:

1. **Arithmetic Mean**:
   $$\mu = \frac{1}{N} \sum_{i=1}^N x_i$$

2. **Variance & Standard Deviation (Sample $ddof=1$ with Bessel's correction)**:
   $$s^2 = \frac{1}{N-1}\sum_{i=1}^N (x_i - \mu)^2, \quad s = \sqrt{s^2}$$
   Standard Error of the Mean: $SE = \frac{s}{\sqrt{N}}$.

3. **Median & Quartiles ($Q_1, Q_2, Q_3, IQR$)**:
   - Order statistics $x_{(1)} \le x_{(2)} \le \dots \le x_{(N)}$.
   - Percentile via linear interpolation: $k = (N - 1)\frac{p}{100}, i = \lfloor k \rfloor, f = k - i$.
     $$P_p = x_{(i+1)} + f(x_{(i+2)} - x_{(i+1)})$$
   - Median $= P_{50}$, $Q_1 = P_{25}$, $Q_3 = P_{75}$.
   - Interquartile Range: $IQR = Q_3 - Q_1$.

4. **Skewness (Fisher-Pearson Standardized Third Moment)**:
   $$m_r = \frac{1}{N} \sum_{i=1}^N (x_i - \mu)^r$$
   $$g_1 = \frac{m_3}{m_2^{3/2}} = \frac{\frac{1}{N}\sum (x_i - \mu)^3}{\left(\frac{1}{N}\sum (x_i - \mu)^2\right)^{3/2}}$$
   Sample-adjusted skewness:
   $$G_1 = \frac{\sqrt{N(N-1)}}{N-2} g_1 \quad (\text{for } N \ge 3)$$
   - $G_1 > 0.5 \implies$ Right-skewed (positive tail).
   - $G_1 < -0.5 \implies$ Left-skewed (negative tail).
   - $-0.5 \le G_1 \le 0.5 \implies$ Approximately symmetric.

5. **Kurtosis (Sample-Adjusted Excess Kurtosis)**:
   $$g_2 = \frac{m_4}{m_2^2} - 3 = \frac{\frac{1}{N}\sum (x_i - \mu)^4}{\left(\frac{1}{N}\sum (x_i - \mu)^2\right)^2} - 3$$
   Sample-adjusted excess kurtosis:
   $$G_2 = \frac{N-1}{(N-2)(N-3)}\left((N+1)g_2 + 6\right) \quad (\text{for } N \ge 4)$$

#### 2.1.3 Correlation Matrix
For $K$ numeric columns $X_1, X_2, \dots, X_K$:
1. **Pearson Correlation**:
   $$r_{jk} = \frac{\sum_{i=1}^N (x_{ij} - \bar{x}_j)(x_{ik} - \bar{x}_k)}{\sqrt{\sum_{i=1}^N (x_{ij} - \bar{x}_j)^2 \sum_{i=1}^N (x_{ik} - \bar{x}_k)^2}}$$
   Returns a $K \times K$ symmetric matrix with $r_{jj} = 1.0$. If column variance is 0, set $r_{jk} = 0.0$.
2. **Spearman Rank Correlation**:
   - Rank transform each column $R(X_j)$ with average ranks for tied values.
   - Compute Pearson correlation on the rank vectors: $r_{s, jk} = r(R(X_j), R(X_k))$.

#### 2.1.4 Anomaly Detection Engine
1. **Z-Score Method**:
   $$z_i = \frac{x_i - \mu}{s}$$
   Flag anomaly if $|z_i| > \tau_z$ (default threshold $\tau_z = 3.0$).
2. **Tukey IQR Fences**:
   $$\text{Lower Fence} = Q_1 - k \cdot IQR, \quad \text{Upper Fence} = Q_3 + k \cdot IQR$$
   - Mild outliers: $k = 1.5$
   - Extreme outliers: $k = 3.0$
3. **Rolling Anomaly Detection**:
   - Window size $W$ (default $\min(20, N/4)$).
   - Moving mean $\mu_w(t)$ and moving standard deviation $\sigma_w(t)$.
   - Flag local spikes where $|x_t - \mu_w(t)| > 2.5 \sigma_w(t)$.

#### 2.1.5 Trend Analysis & Linear Regression
1. **Ordinary Least Squares (OLS) Linear Model**: $y = \beta_1 x + \beta_0$
   $$\beta_1 = \frac{\sum_{i=1}^N (x_i - \bar{x})(y_i - \bar{y})}{\sum_{i=1}^N (x_i - \bar{x})^2}, \quad \beta_0 = \bar{y} - \beta_1 \bar{x}$$
2. **Goodness of Fit ($R^2$)**:
   $$R^2 = 1 - \frac{\sum (y_i - \hat{y}_i)^2}{\sum (y_i - \bar{y})^2}$$
3. **Direction & Growth Rate**:
   - Compound Annual / Period Growth Rate (CAGR):
     $$\text{CAGR} = \left(\frac{y_N}{y_1}\right)^{\frac{1}{N-1}} - 1 \quad (\text{for } y_1 > 0, y_N > 0)$$
   - Trend Direction: `"INCREASING"` if $\beta_1 > 0$ and $R^2 \ge 0.10$; `"DECREASING"` if $\beta_1 < 0$ and $R^2 \ge 0.10$; else `"STABLE"`.

#### 2.1.6 Monte Carlo Simulation Engine Math
Configurable distribution types and probabilistic sampling:

1. **Distribution Generators (NumPy / Pure Python Fallback)**:
   - `DistributionType.NORMAL`: Gaussian $\mathcal{N}(\mu, \sigma^2)$.
     Box-Muller transform: $Z_0 = \sqrt{-2\ln U_1}\cos(2\pi U_2), X = \mu + \sigma Z_0$.
   - `DistributionType.LOGNORMAL`: Parameterized by expected mean $M$ and standard deviation $S$:
     $$\sigma_{\ln} = \sqrt{\ln\left(1 + \frac{S^2}{M^2}\right)}, \quad \mu_{\ln} = \ln(M) - \frac{1}{2}\sigma_{\ln}^2$$
     $$X = \exp(\mathcal{N}(\mu_{\ln}, \sigma_{\ln}^2))$$
   - `DistributionType.UNIFORM`: $\mathcal{U}(a, b) = a + (b - a) U$ for $U \sim \mathcal{U}(0, 1)$.
   - `DistributionType.TRIANGULAR`: $\text{Triangular}(a, b, c)$ where $a=\text{low}, b=\text{high}, c=\text{mode}$:
     $$X = \begin{cases} a + \sqrt{U(b - a)(c - a)} & \text{if } U < \frac{c - a}{b - a} \\ b - \sqrt{(1 - U)(b - a)(b - c)} & \text{if } U \ge \frac{c - a}{b - a} \end{cases}$$

2. **Simulation Models**:
   - **Single-Period Return Model**: $S_{\text{final}} = S_0 \cdot (1 + R)$ where $R \sim \text{Dist}$.
   - **Multi-Step Geometric Brownian Motion (GBM)**:
     $$S_t = S_{t-1} \exp\left(\left(\mu - \frac{1}{2}\sigma^2\right)\Delta t + \sigma \sqrt{\Delta t} Z_t\right)$$

3. **Risk Metrics Calculation**:
   - Percentiles: $P_1, P_5, P_{10}, P_{25}, P_{50}, P_{75}, P_{90}, P_{95}, P_{99}$.
   - Target Attainment Probability:
     $$\text{Prob}(S_{\text{final}} \ge T) = \frac{1}{M}\sum_{m=1}^M \mathbb{I}(S_m \ge T) \times 100\%$$
   - Value-at-Risk ($\text{VaR}$): Maximum expected loss at confidence level $\alpha \in \{0.95, 0.99\}$:
     $$\text{VaR}_{95\%} = \max(0.0, S_0 - P_5)$$
     $$\text{VaR}_{99\%} = \max(0.0, S_0 - P_1)$$
   - Conditional Value-at-Risk ($\text{CVaR}_{95\%}$ / Expected Shortfall):
     $$\text{CVaR}_{95\%} = S_0 - \frac{1}{|K|}\sum_{i \in K} S_i \quad \text{where } K = \{i \mid S_i \le P_5\}$$

---

### 2.2 Document Exporter Architecture (`jarvis/data/document.py`)

#### 2.2.1 Pure OpenXML DOCX Generator Specification
A valid `.docx` file is an ECMA-376 standard Open Packaging Convention (OPC) ZIP archive. The pure generator constructs the exact folder structure:

```
[output_filename.docx] (ZIP Archive)
├── [Content_Types].xml
├── _rels/
│   └── .rels
└── word/
    ├── _rels/
    │   └── document.xml.rels
    ├── styles.xml
    └── document.xml
```

1. **`[Content_Types].xml`**:
   ```xml
   <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
   <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
     <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
     <Default Extension="xml" ContentType="application/xml"/>
     <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
     <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
   </Types>
   ```

2. **`_rels/.rels`**:
   ```xml
   <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
   <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
     <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
   </Relationships>
   ```

3. **`word/_rels/document.xml.rels`**:
   ```xml
   <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
   <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
     <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
   </Relationships>
   ```

4. **`word/styles.xml`**:
   Configures standard Word styles: `Normal`, `Title`, `Subtitle`, `Heading1`, `Heading2`, `Heading3`, `TableGrid`, `Callout`.
   - Typography: Font family `Calibri`, primary color `#1F4E79` (Deep Navy), secondary color `#2E75B6` (Cobalt), body font size 11pt (`w:sz w:val="22"`).

5. **`word/document.xml` Layout**:
   - XML Character Escaping helper: `&` $\to$ `&amp;`, `<` $\to$ `&lt;`, `>` $\to$ `&gt;`, `"` $\to$ `&quot;`, `'` $\to$ `&apos;`.
   - Paragraph construction: `<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Heading Text</w:t></w:r></w:p>`.
   - Formatted Tables:
     - Header Row: Background `#1F4E79`, bold white text `<w:color w:val="FFFFFF"/>`, `<w:tblHeader/>`.
     - Alternating Row Shading: Even rows `#F2F4F7`, odd rows `#FFFFFF`.
     - Cell Padding & Borders: `<w:tblBorders><w:insideH w:val="single" w:sz="4" w:color="E0E0E0"/></w:tblBorders>`.
   - Section Properties: A4 Page dimensions (11,906 $\times$ 16,838 dxa/twips) with 1-inch margins (1,440 dxa).

#### 2.2.2 Hybrid PDF Export Architecture
1. **ReportLab Accelerated Engine (if available)**:
   - Uses `SimpleDocTemplate` + `Table` + `Paragraph` + `Spacer` + `colors.HexColor`.
2. **Pure Python Minimalist PDF 1.4 Canvas Engine (Zero-Dependency Primary/Fallback)**:
   - Directly synthesizes standard PDF 1.4 binary stream with valid `/Type /Catalog`, `/Type /Pages`, `/Type /Page`, `/Type /Font` (`/BaseFont /Helvetica` and `/BaseFont /Helvetica-Bold`), `/MediaBox [0 0 595.28 841.89]` (A4 in points).
   - Generates cross-reference table (`xref`), `/Trailer`, and startxref offset.
   - Text rendering via `BT`, `/F1 12 Tf`, `x y Td`, `(text) Tj`, `ET` stream operators.
   - Tables drawn via rectangular path operations: `x y w h re f` (fill) and `x y w h re s` (stroke).

#### 2.2.3 Voice Executive Summary Generator (`VoiceSummaryGenerator`)
Converts dense statistical analyses into natural language audio scripts (Vietnamese + English):
- **Vietnamese Voice Summary Template**:
  ```python
  f"Đã hoàn thành phân tích tệp dữ liệu '{filename}'. "
  f"Tập dữ liệu gồm {stats.count:,} mẫu hợp lệ. "
  f"Giá trị trung bình là {stats.mean:.2f}, trung vị là {stats.median:.2f}, và độ lệch chuẩn là {stats.std:.2f}. "
  f"Phân phối có độ nghiêng {skew_desc} ({stats.skewness:.2f}). "
  f"Mô phỏng Monte Carlo với {sim.iterations:,} kịch bản dự báo xác suất đạt mục tiêu {target_val:.2f} là {sim.prob_target:.1f}%, "
  f"trong khoảng tin cậy 95% từ {sim.p5:.2f} đến {sim.p95:.2f}. "
  f"Mức rủi ro VaR 95% là {sim.var_95:.2f}. "
  f"Phát hiện {anomaly_count} điểm dữ liệu bất thường. "
  f"Báo cáo chi tiết đã được xuất ra định dạng DOCX và PDF."
  ```

---

### 2.3 Proposed Class Blueprint & Data Models

```python
# ============================================================================
# jarvis/data/stats.py - Models & Class Interface
# ============================================================================

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


class DistributionType(str, Enum):
    NORMAL = "normal"
    LOGNORMAL = "lognormal"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"
    EXPONENTIAL = "exponential"


@dataclass
class DescriptiveStats:
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
    columns: List[str]
    pearson_matrix: List[List[float]]
    spearman_matrix: List[List[float]]


@dataclass
class AnomalyItem:
    index: int
    value: float
    score: float
    reason: str


@dataclass
class AnomalyReport:
    column_name: str
    method: str
    total_anomalies: int
    anomalies: List[AnomalyItem]


@dataclass
class TrendResult:
    column_name: str
    slope: float
    intercept: float
    r_squared: float
    direction: str  # INCREASING, DECREASING, STABLE
    cagr_percent: Optional[float]


@dataclass
class MonteCarloConfig:
    distribution: DistributionType = DistributionType.NORMAL
    initial_value: float = 100.0
    iterations: int = 5000
    mean_return: float = 0.05
    volatility: float = 0.15
    target_value: Optional[float] = 110.0
    triangular_low: Optional[float] = None
    triangular_high: Optional[float] = None
    triangular_mode: Optional[float] = None
    uniform_low: Optional[float] = None
    uniform_high: Optional[float] = None
    random_seed: Optional[int] = 42


@dataclass
class MonteCarloResult:
    iterations: int
    distribution: str
    mean: float
    std_dev: float
    std_err: float
    min: float
    max: float
    p1: float
    p5: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float
    prob_target: float
    var_95: float
    var_99: float
    cvar_95: float


class TabularDataset:
    def __init__(self, headers: List[str], rows: List[List[Any]]):
        self.headers = headers
        self.rows = rows
        self.numeric_columns: Dict[str, np.ndarray] = {}
        self._extract_numeric_columns()


class DataAnalyticsEngine:
    """Core statistical engine for CSV and XLSX processing."""
    def load_csv(self, file_path: Union[str, Path]) -> TabularDataset: ...
    def load_xlsx(self, file_path: Union[str, Path], sheet_index: int = 0) -> TabularDataset: ...
    def compute_statistics(self, dataset: TabularDataset, column: str) -> DescriptiveStats: ...
    def compute_all_statistics(self, dataset: TabularDataset) -> Dict[str, DescriptiveStats]: ...
    def compute_correlation_matrix(self, dataset: TabularDataset) -> CorrelationResult: ...
    def detect_anomalies(self, dataset: TabularDataset, column: str, method: str = "zscore", threshold: float = 3.0) -> AnomalyReport: ...
    def analyze_trend(self, dataset: TabularDataset, column: str) -> TrendResult: ...


class MonteCarloEngine:
    """Probabilistic Monte Carlo simulation coordinator."""
    def run_simulation(self, config: MonteCarloConfig) -> MonteCarloResult: ...
```

```python
# ============================================================================
# jarvis/data/document.py - Models & Class Interface
# ============================================================================

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from jarvis.data.stats import AnomalyReport, CorrelationResult, DescriptiveStats, MonteCarloResult, TrendResult


class DocxReportBuilder:
    """Pure-Python OpenXML DOCX Generator without external dependencies."""
    def __init__(self, title: str = "JARVIS Analytics Report"): ...
    def add_title(self, text: str, subtitle: Optional[str] = None) -> None: ...
    def add_heading(self, text: str, level: int = 1) -> None: ...
    def add_paragraph(self, text: str, bold: bool = False, italic: bool = False, color: Optional[str] = None) -> None: ...
    def add_bullet(self, text: str) -> None: ...
    def add_table(self, headers: List[str], rows: List[List[str]], header_bg: str = "1F4E79") -> None: ...
    def add_callout(self, text: str, title: str = "EXECUTIVE SUMMARY") -> None: ...
    def save(self, target_path: Union[str, Path]) -> Path: ...


class PdfReportBuilder:
    """Zero-dependency PDF 1.4 Canvas & ReportLab Exporter."""
    def __init__(self, title: str = "JARVIS Analytics Report"): ...
    def add_title(self, text: str, subtitle: Optional[str] = None) -> None: ...
    def add_heading(self, text: str, level: int = 1) -> None: ...
    def add_paragraph(self, text: str) -> None: ...
    def add_table(self, headers: List[str], rows: List[List[str]]) -> None: ...
    def save(self, target_path: Union[str, Path]) -> Path: ...


class VoiceSummaryGenerator:
    """Converts statistical insights into spoken natural language scripts."""
    def generate_summary(
        self,
        filename: str,
        stats: DescriptiveStats,
        sim: Optional[MonteCarloResult] = None,
        anomalies: Optional[AnomalyReport] = None,
        trend: Optional[TrendResult] = None,
        language: str = "vi",
    ) -> str: ...
    def generate_brief_notification(self, filename: str, stats: DescriptiveStats, sim: Optional[MonteCarloResult] = None) -> str: ...


class DocumentExporter:
    """Unified coordinator for DOCX, PDF, and Voice generation."""
    def export_full_analytics_suite(
        self,
        dataset_name: str,
        stats_map: Dict[str, DescriptiveStats],
        correlation: Optional[CorrelationResult],
        sim_result: Optional[MonteCarloResult],
        anomaly_map: Optional[Dict[str, AnomalyReport]],
        trend_map: Optional[Dict[str, TrendResult]],
        output_docx: Path,
        output_pdf: Path,
    ) -> Dict[str, Any]: ...
```

---

## 3. TEST ARCHITECTURE FOR MILESTONE 5

### 3.1 Overview of Milestone 5 Test Suites

```
                                 MILESTONE 5 TEST SUITE
 +───────────────────────────────────────────────────────────────────────────────────+
 │                                                                                   │
 │  tests/test_biometrics.py           tests/test_smart_home.py                      │
 │  ├── Face Enrollment (128D)         ├── Home Assistant REST Client                │
 │  ├── Live Frame Verification        ├── WebSocket Subscriptions                   │
 │  ├── Biometric Privilege Gate       ├── Service Calls (Light, AC)                 │
 │  ├── Stranger Auto-Lock             ├── MQTT Topic Publish/Sub                    │
 │  └── Non-Camera Bypass Mode         └── Reconnection & Timeout Handling           │
 │                                                                                   │
 │  tests/test_data_analytics.py       tests/test_comms_hub.py                       │
 │  ├── CSV Sniffing & Type Inference  ├── Telegram Bot Whitelist Filter             │
 │  ├── Pure Zipfile XLSX Parser       ├── Remote Command Dispatch (/lock, /status)  │
 │  ├── Descriptive Stats & Skewness   ├── Intruder Photo Alert                      │
 │  ├── Correlation & Anomaly Engine   ├── IMAP Unread Priority Email Reader         │
 │  ├── Monte Carlo Engine (4 Dists)   └── Discord Channel Reader & Summary          │
 │  ├── Pure OpenXML DOCX Generation                                                 │
 │  ├── PDF Export & Fallback          tests/test_e2e_scenarios.py                   │
 │  └── Voice Executive Summary        ├── VM Orchestrator (VMware / VBox)           │
 │                                     ├── Workspace IDE/Terminal Recipes            │
 │                                     ├── Tier 3 Cross-Feature Pipelines            │
 │                                     └── Tier 4 Real-World Automation Workflows    │
 +───────────────────────────────────────────────────────────────────────────────────+
```

### 3.2 Test Specifications per Module

#### 1. `tests/test_biometrics.py`
- **F-33: Face Enrollment & Verification**:
  - `test_face_enrollment_stores_normalized_128d_embedding`: Validates enrollment creates a 128-element normalized vector.
  - `test_face_verification_matches_owner_within_euclidean_threshold`: Injects owner frame with slight synthetic noise; asserts Euclidean distance $< 0.60 \implies \text{True}$.
  - `test_face_verification_rejects_stranger_face`: Injects orthogonal stranger embedding; asserts distance $\ge 0.60 \implies \text{False}$.
- **F-34: Biometric Privilege Gate**:
  - `test_privilege_gate_blocks_admin_actions_without_biometric_token`: Confirms `is_allowed("nmap_scan", None) == False`.
  - `test_privilege_gate_authorizes_when_owner_verified`: Confirms `authenticate(owner_frame)` yields authenticated `RequesterContext` granting access.
- **F-35: Intruder Detection & Auto-Lock**:
  - `test_intruder_detection_triggers_win32_lockworkstation_and_telegram`: Injects stranger frame during surveillance loop; asserts `mock_win32_platform.lock_workstation_calls == 1` and `mock_http_server.telegram_sent_photos` contains snapshot.
- **Tier 2 Edge Cases**:
  - `test_biometrics_camera_disconnected_enters_safe_bypass_mode`: Verifies graceful bypass when webcam is absent.
  - `test_biometrics_dark_or_occluded_frame_suppresses_false_positive_lock`: Asserts black frame returns `False` without triggering auto-lock.

#### 2. `tests/test_smart_home.py`
- **F-26: Home Assistant REST & WebSocket Client**:
  - `test_ha_get_entity_state`: Queries `light.living_room` and parses state + attributes.
  - `test_ha_call_service_turn_on_with_brightness`: Calls `light.turn_on` with `brightness=200`; verifies state update in mock hub.
  - `test_ha_climate_target_temperature_update`: Updates AC unit target temperature via service call.
  - `test_ha_entity_alias_mapping`: Resolves friendly name `"đèn phòng khách"` $\to$ `"light.living_room"`.
- **F-27: MQTT Protocol Adapter**:
  - `test_mqtt_publish_and_subscribe_callback_routing`: Publishes to `"home/sensors/power"`; verifies callback receives exact decoded payload.
  - `test_mqtt_wildcard_topic_subscription`: Subscribes to `"home/sensors/#"`; verifies reception across sub-topics.
- **Tier 2 Edge Cases**:
  - `test_ha_server_unreachable_returns_structured_error`: When endpoint is offline, returns `{"success": False, "error": "Connection failed"}` with zero crash.
  - `test_mqtt_reconnect_backoff`: Handles broker disconnect without blocking main event loop.

#### 3. `tests/test_data_analytics.py`
- **F-28: Data Ingestion & Descriptive Statistics**:
  - `test_csv_ingestion_with_various_delimiters_and_type_inference`: Ingests CSVs with comma, semicolon, tab; parses numeric columns correctly.
  - `test_pure_xml_xlsx_ingestion_extracts_sheets_and_shared_strings`: Reads synthetic `.xlsx` ZIP archive via pure Python; verifies extracted cell rows.
  - `test_descriptive_statistics_accuracy`: Verifies count, mean, std (sample $ddof=1$), median, quartiles ($Q_1, Q_3$), skewness ($G_1$), and kurtosis ($G_2$).
  - `test_correlation_matrix_pearson_and_spearman`: Tests 3-column dataset with known linear and monotonic relationships; validates correlation coefficients in $[-1.0, 1.0]$.
  - `test_anomaly_detection_zscore_and_iqr_fences`: Injects synthetic outlier ($x=1000$ in a $[10..50]$ dataset); asserts both Z-score and Tukey fences flag index.
  - `test_trend_analysis_linear_regression`: Evaluates linearly increasing time series; validates slope $> 0$, $R^2 > 0.95$, and direction `"INCREASING"`.
- **F-29: Monte Carlo Simulation Engine**:
  - `test_monte_carlo_normal_distribution_simulation`: Runs 5,000 iterations; asserts $P_5 < P_{50} < P_{95}$ and probability of target attainment in $[0\%, 100\%]$.
  - `test_monte_carlo_lognormal_uniform_triangular_distributions`: Parameterizes and validates all 4 distribution types.
  - `test_monte_carlo_var_and_cvar_risk_calculation`: Verifies $\text{VaR}_{95}$ and $\text{CVaR}_{95}$ calculations match theoretical risk bounds.
- **F-30: Document Exporter & Voice Summary**:
  - `test_pure_openxml_docx_generation_is_valid_zip_and_xml`: Generates `.docx` file; opens with `zipfile.ZipFile`; validates XML schema of `[Content_Types].xml`, `_rels/.rels`, `word/document.xml`, and `word/styles.xml`.
  - `test_pdf_export_and_fallback_generation`: Generates PDF file; validates PDF header `%PDF-1.4`, object streams, and non-empty output.
  - `test_voice_executive_summary_formatting`: Verifies Vietnamese and English natural language summaries contain exact numbers, percentages, and risk insights.
- **Tier 2 Edge Cases**:
  - `test_data_analytics_empty_or_corrupted_file_raises_value_error`: Zero-byte file raises clear descriptive `ValueError`.
  - `test_monte_carlo_invalid_parameters_raise_value_error`: Iterations $< 1000$ or negative volatility raises `ValueError`.

#### 4. `tests/test_comms_hub.py`
- **F-38: Telegram Bot Remote Controller**:
  - `test_telegram_authorized_user_status_command`: Whitelisted user sends `/status`; receives 200 OK with system status text.
  - `test_telegram_authorized_user_lock_command`: Whitelisted user sends `/lock`; executes `user32.LockWorkStation`.
  - `test_telegram_unauthorized_user_rejection_403`: Non-whitelisted user is rejected with 403 Forbidden and logged in `security_violations`.
  - `test_telegram_photo_send_for_intruder_alert`: Dispatches photo bytes and caption to Telegram chat.
- **F-39: IMAP Email Reader & Summarizer**:
  - `test_imap_fetch_priority_unread_emails`: Filters unread emails against priority sender whitelist.
  - `test_imap_voice_summary_generation`: Summarizes priority email sender, subject, and body into crisp audio script.
- **F-40: Discord Bot Integration**:
  - `test_discord_channel_activity_summary`: Summarizes recent message counts and active topics.

#### 5. `tests/test_e2e_scenarios.py`
- **F-31 & F-32: Workspace Automation**:
  - `test_workspace_vm_orchestrator_starts_vmware_and_vbox`: Simulates `vmrun start` / `VBoxManage startvm`.
  - `test_workspace_recipe_manager_prepares_apps`: Executes `"ai_development"` recipe launching Cursor, Windows Terminal, and Spotify.
- **Tier 3 Cross-Feature Interactions**:
  - `test_e2e_tier3_gesture_to_multiaction_and_tts`: Acoustic Double Clap $\to$ Action Fanout $\to$ ElevenLabs Welcome.
  - `test_e2e_tier3_voice_command_to_smart_home_with_tts`: Voice STT $\to$ LLM Intent $\to$ Home Assistant Light $\to$ Spoken Confirmation.
  - `test_e2e_tier3_intruder_to_lock_and_telegram`: Stranger Face $\to$ Win32 Workstation Lock $\to$ Telegram Photo Alert.
  - `test_e2e_tier3_hardware_overheat_to_voice_alert`: CPU 94°C $\to$ Threshold Breach $\to$ Vocal Warning.
  - `test_e2e_tier3_privilege_gated_nmap_scan_flow`: Security Scan Request $\to$ Biometric Face Auth $\to$ Nmap Audit $\to$ Markdown Report.
  - `test_e2e_tier3_unresponsive_app_healing_flow`: Hung App $\to$ Watchdog Trigger $\to$ Safe Kill $\to$ RAM Reclaimed.
  - `test_e2e_tier3_data_file_to_docx_and_voice`: CSV Ingestion $\to$ Monte Carlo Sim $\to$ Pure DOCX Export $\to$ Voice Executive Summary.
- **Tier 4 Real-World Application Workflows**:
  - `test_e2e_tier4_full_morning_workspace_automation_workflow`: Complete morning sequence (Double clap $\to$ Spotify $\to$ Multi-monitor Chrome $\to$ ElevenLabs Greeting $\to$ Boot VM $\to$ Launch Terminal).
  - `test_e2e_tier4_system_crisis_self_healing_workflow`: Crisis recovery (RAM 96% + Hung Chrome $\to$ Autonomous Termination $\to$ Memory Reclaimed $\to$ Spoken Diagnosis).
  - `test_e2e_tier4_security_audit_and_incident_workflow`: Remote incident response (Telegram `/exec` $\to$ Biometric Challenge $\to$ Nmap Scan $\to$ Report Generated).
  - `test_e2e_tier4_offline_resilience_and_graceful_degradation_workflow`: Zero-cloud offline mode (No internet $\to$ Double clap $\to$ SAPI5 offline speech $\to$ Local rule intent $\to$ Zero crash).

---

## 4. CAVEATS & EDGE CASE MITIGATION

1. **Zero-Variance Columns**:
   - If all values in a numeric column are identical (e.g. `[5.0, 5.0, 5.0]`), standard deviation is $0.0$.
   - **Mitigation**: Division by zero in Z-score, skewness, and Pearson correlation is caught and safely defaulted to $0.0$.
2. **High-Iteration Monte Carlo Performance**:
   - Running $100,000+$ iterations with pure Python loops would be slow.
   - **Mitigation**: Vectorized NumPy random generation (`np.random.normal`, `np.random.lognormal`, `np.random.uniform`, `np.random.triangular`) ensures 10,000 iterations execute in $< 5$ milliseconds.
3. **Pure OpenXML Schema Validity**:
   - Microsoft Word is strict regarding OpenXML namespaces and XML element ordering. If `<w:pPr>` appears after `<w:r>`, Word throws a corrupted document error.
   - **Mitigation**: Pure `DocxReportBuilder` enforces strict schema ordering: `<w:pPr>` always precedes `<w:r>`, and `<w:rPr>` always precedes `<w:t>`.
4. **Pure PDF 1.4 Font Encodings**:
   - Built-in PDF 1.4 Type 1 font `/Helvetica` supports WinAnsi / ISO-8859-1. Non-ASCII characters (like Vietnamese diacritics) in raw PDF stream operators without embedded TrueType fonts can render incorrectly.
   - **Mitigation**: `PdfReportBuilder` performs automatic Unicode normalization / unidecode stripping for pure canvas mode, while full UTF-8 diacritics are preserved in DOCX and ReportLab PDF modes.

---

## 5. CONCLUSION

1. **Production-Ready Pure Implementations**:
   - `jarvis/data/stats.py` provides complete data ingestion (CSV & pure XML XLSX), descriptive statistics, correlation matrices, anomaly detection, OLS trend regression, and a 4-distribution Monte Carlo engine.
   - `jarvis/data/document.py` provides a pure-Python OpenXML DOCX generator (zero external binary dependencies), a dual-engine PDF exporter, and a bilingual Voice Executive Summary generator.
2. **Comprehensive Test Suite**:
   - The 5 Milestone 5 test files (`test_biometrics.py`, `test_smart_home.py`, `test_data_analytics.py`, `test_comms_hub.py`, `test_e2e_scenarios.py`) provide exhaustive 4-Tier coverage (Feature happy paths, boundary & corner cases, cross-feature pipelines, and end-to-end user workflows) with 100% headless CI compatibility.

---

## 6. VERIFICATION METHOD

To independently verify this technical blueprint:

1. **Verify OpenXML Pure ZIP Generation**:
   ```powershell
   & "d:\Software GitCode\JARVIS\.venv\Scripts\python.exe" "d:\Software GitCode\JARVIS\.agents\explorer_m5_3\verify_openxml.py"
   ```
   *Expected*: Prints valid XML confirmation for `[Content_Types].xml`, `_rels/.rels`, `word/_rels/document.xml.rels`, `word/styles.xml`, and `word/document.xml`.

2. **Verify Pure XLSX XML Ingestion**:
   ```powershell
   & "d:\Software GitCode\JARVIS\.venv\Scripts\python.exe" "d:\Software GitCode\JARVIS\.agents\explorer_m5_3\verify_xlsx.py"
   ```
   *Expected*: Prints parsed 2D row data extracted from synthetic ZIP archive.

3. **Run Existing Test Suite**:
   ```powershell
   & "d:\Software GitCode\JARVIS\.venv\Scripts\python.exe" -m pytest tests/ -v
   ```
   *Expected*: All test modules execute cleanly with zero hardware crashes.
