# Technical Architecture & Survey Report: Requirements R3, R4, and R6
## JARVIS Autonomous Agentic Superpower Upgrade

**Author**: Explorer Survey 3  
**Target Workspace**: `d:/Software GitCode/JARVIS`  
**Working Directory**: `d:/Software GitCode/JARVIS/.agents/explorer_survey_3`  
**Date**: 2026-08-24  
**Status**: Complete (Hard Handoff)

---

## 1. Observation

### 1.1 Existing Codebase Baseline Observations

Direct inspection of `jarvis/` revealed the following module capabilities, interfaces, and limitations:

1. **Web & Browser Automation Subsystem**:
   - `jarvis/web/search.py` (lines 51–254): Implements `WebSearcher` with a 3-tier search engine: Tier 1 DuckDuckGo SDK (`duckduckgo_search.DDGS`), Tier 2 direct DuckDuckGo HTML scraping regex, and Tier 3 SerpAPI REST endpoint. Results are cached in `TTLCache` with 600s TTL.
   - `jarvis/web/hub.py` (lines 26–170): `WebIntelligenceHub` coordinates search, OpenWeatherMap / wttr.in weather (`WeatherProvider`), RSS news parsing (`NewsAggregator`), and Binance/CoinGecko crypto/exchange rate tracker (`FinanceTracker`).
   - `jarvis/plugins/chrome.py` (lines 20–125): `ChromeMultiMonitorPlugin` launches Google Chrome instances across multiple displays via `subprocess.Popen([chrome_exe, "--new-window", f"--window-position={x},{y}", url])`.
   - *Direct Gap*: There is no interactive browser driver, no DOM manipulation, no form automation, no dynamic SPA waiting loop, no CDP (Chrome DevTools Protocol) websocket interface, and no session/cookie persistence mechanism.

2. **Screen Capture & Vision Subsystem**:
   - `jarvis/vision/screen.py` (lines 60–260): `ScreenVisionManager` captures desktop screenshots via `mss` (Tier 1), falling back to `PIL.ImageGrab` (Tier 2) or synthetic test frame (Tier 3). Images are compressed to JPEG q80 within a target budget (<80ms capture, <3.0s total inference).
   - `jarvis/vision/screen.py` (lines 263–380): Implements `analyze_screen()` querying Google Gemini 1.5 Flash or OpenAI GPT-4o Vision via direct HTTP REST (`requests.post`). Returns polite fallback `"Tôi chưa thể nhìn thấy màn hình do chưa cấu hình Vision API key, thưa Ngài."` if API keys are missing.
   - `jarvis/vision/ocr.py` (lines 35–142): `DesktopOCR` provides dual-tier text extraction: local `pytesseract` (Tier 1) and Vision LLM OCR (Tier 2).
   - `jarvis/vision/dialog_detector.py` (lines 20–110): `ErrorDialogDetector` scans for `#32770` modal dialogs and Windows error windows via Win32 ctypes.
   - *Direct Gap*: There is no computer-use coordinate grounding engine (e.g. Anthropic 1000x1000 normalized grid), no visual element bounding-box resolver, no visual verification diffing engine to confirm UI state transitions between before/after actions, and no self-healing GUI retry logic.

3. **Desktop Automation & OS Control Subsystem**:
   - `jarvis/automation/control.py` (lines 21–340): `ComputerController` provides window management (`get_active_window`, `focus_window_by_title`, `close_window`), mouse manipulation (`mouse_click`, `mouse_move`, `mouse_scroll`), keyboard injection (`type_text`, `send_hotkey`), clipboard read/write (`get_clipboard_text`, `set_clipboard_text`), volume, brightness, and fast file search (`search_files`).
   - `jarvis/platform/windows.py` (lines 1–690): Provides low-level Win32 ctypes wrappers (`user32.dll`, `kernel32.dll`, `gdi32.dll`) for DPI awareness, window rect enumeration, and unicode text injection.
   - *Direct Gap*: Actions are executed blindly without verifying visual outcomes; mouse operations lack coordinate bounds verification against active display geometry, and there is no unified `GUIActor` combining vision grounding and verification.

4. **Always-On HUD Overlay Subsystem**:
   - `jarvis/ui/overlay.py` (lines 188–700): `AlwaysOnOverlay` implements an Iron Man Arc Reactor style HUD in Tkinter running in a background thread. Features: 380px Sidebar Docking, collapsible 40px ribbon, 5-turn conversation history queue (`TurnRecord`), quick action buttons, top 3 persistent memory facts preview, 5s realtime CPU/RAM/Battery status bar, and 11-bar audio spectrum visualizer.
   - *Direct Gap*: The HUD lacks visual rendering for multi-step agent plans (Task DAG / execution step graph), real-time code execution logs/stream, and visual artifact display (screenshots, scraped comparison tables).

5. **Voice & Memory Subsystems**:
   - `jarvis/audio/wake_word.py` (lines 56–200): `WakeWordDetector` detects "Hey JARVIS" / "JARVIS" using Vosk / OpenWakeWord / Porcupine with a zero-dependency acoustic formant energy fallback.
   - `jarvis/memory/sqlite_store.py` (lines 23–220): `SQLiteMemoryStore` operates on `logs/memory.db` with SQLite WAL mode, managing `facts` (key-value profile/preferences), `episodes` (command history), and `user_habits`.
   - *Direct Gap*: Memory store does not contain a dedicated schema for agent task DAG history (`task_history`), browser sessions / cookies storage, or reusable workflow graphs.

### 1.2 Environment Probe Observations

Runtime Python package availability probed via `python -c`:
```
playwright: NOT AVAILABLE (No module named 'playwright')
pyautogui: NOT AVAILABLE (No module named 'pyautogui')
pywin32: NOT AVAILABLE (No module named 'pywin32')
win32gui: AVAILABLE
mss: NOT AVAILABLE (No module named 'mss')
PIL: AVAILABLE (Pillow 10.x+)
cv2: NOT AVAILABLE (No module named 'cv2')
sqlite3: AVAILABLE (Python Standard Library, WAL supported)
pydantic: AVAILABLE
requests: AVAILABLE
pytesseract: NOT AVAILABLE (No module named 'pytesseract')
```

**Critical Invariant**: All new components for R3, R4, and R6 MUST follow a strict multi-tier fallback architecture:
- Primary Tier: Advanced third-party packages (`playwright`, `pyautogui`, `cv2`, `mss`, `pytesseract`) if installed.
- Secondary Tier: Built-in standard library / native Win32 ctypes (`win32gui`, `ctypes.windll`, `PIL.ImageGrab`, `urllib`, `requests`, `html.parser`, `sqlite3`).
- Tertiary Tier: Deterministic in-memory Mock drivers for 100% headless CI/CD test isolation without network or display.

---

## 2. Logic Chain

From the observations above, we establish the step-by-step reasoning for the architecture of R3, R4, and R6:

```
[Observation 1.1.1 & 1.2: No Playwright installed by default; WebSearcher has HTTP scraping]
  ==> Logic Step 1: Design R3 Browser Agent with a Driver Abstraction Layer:
      PlaywrightDriver (Tier 1) -> CDPDriver (Tier 2) -> HttpScrapingDriver (Tier 3) -> MockBrowserDriver (Tier 4).
  ==> Logic Step 2: Implement dynamic SPA support via DOM state polling, wait_for_selector, accessibility snapshots, and JSON-LD extraction.
  ==> Logic Step 3: Implement BrowserSessionManager to persist cookies and local storage in SQLite/JSON for zero-friction re-authentication.

[Observation 1.1.2 & 1.1.3: ScreenVisionManager has capture/Gemini; ComputerController has mouse/keyboard]
  ==> Logic Step 4: Design R4 Computer-Use Vision with Normalized Coordinate Space (0-1000 grid).
  ==> Logic Step 5: Multi-Tier Element Detection: Vision LLM Grounding -> OCR Text Bounding Box -> Win32 UIAutomation / EnumChildWindows -> Template Match.
  ==> Logic Step 6: Visual Verification Loop: S_before -> Execute Action -> S_after -> Delta Diffing (SSIM / Pixel Delta / ROI state change).
  ==> Logic Step 7: Self-Healing GUI Retry: If visual state does not change, retry with adjusted coordinates or alternative hotkey.

[Observation 1.1.4 & 1.1.5: AlwaysOnOverlay has sidebar/5-turn history; SQLiteMemoryStore has WAL mode]
  ==> Logic Step 8: Upgrade R6 HUD Overlay to render Task DAG (Nodes, Status, Progress bars), Live Code Logs, and Visual Result Cards.
  ==> Logic Step 9: Integrate Wake Word -> STT -> Autonomous Planner -> TTS multi-modal voice loop.
  ==> Logic Step 10: Upgrade SQLite Memory Layer with `task_history`, `browser_sessions`, and `reusable_workflows` tables.
```

---

## 3. Detailed Architectural Specifications

### 3.1 Requirement R3: Full Browser Automation Agent (`jarvis/browser/`)

#### 3.1.1 Module Structure & Boundaries
```
jarvis/browser/
├── __init__.py          # Exports: BrowserAgent, BrowserDriver, BrowserSessionManager, etc.
├── models.py            # Data classes: BrowserConfig, PageElement, ActionResult, ScrapeResult
├── driver.py            # BaseBrowserDriver, PlaywrightDriver, CDPDriver, HttpDriver, MockDriver
├── session.py           # BrowserSessionManager (cookies, storage, auth state)
├── actions.py           # BrowserActions (navigate, click, type, select, evaluate, download)
├── scraper.py           # WebScraper (Markdown converter, structured data, price comparator)
└── agent.py             # BrowserAgent (High-level autonomous browser controller)
```

#### 3.1.2 Data Schemas & Models (`jarvis/browser/models.py`)
```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class BrowserDriverType(str, Enum):
    PLAYWRIGHT = "playwright"
    CDP = "cdp"
    HTTP_SCRAPER = "http_scraper"
    MOCK = "mock"

@dataclass
class BrowserConfig:
    driver_type: BrowserDriverType = BrowserDriverType.PLAYWRIGHT
    headless: bool = True
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    viewport_width: int = 1280
    viewport_height: int = 800
    timeout_ms: int = 30000
    downloads_dir: str = "downloads"
    session_storage_dir: str = "logs/browser_sessions"

@dataclass
class PageElement:
    selector: str
    tag_name: str
    text: str
    role: Optional[str] = None
    aria_label: Optional[str] = None
    bounding_box: Optional[Dict[str, float]] = None  # x, y, width, height
    is_visible: bool = True
    is_enabled: bool = True

@dataclass
class BrowserActionResult:
    success: bool
    action: str
    url: str
    title: str = ""
    extracted_data: Any = None
    downloaded_file: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_b64: Optional[str] = None
    execution_time_ms: float = 0.0

@dataclass
class PriceComparisonItem:
    store_name: str
    product_title: str
    price: float
    currency: str = "VND"
    product_url: str = ""
    rating: Optional[float] = None
    in_stock: bool = True

@dataclass
class ScrapeResult:
    url: str
    title: str
    markdown_content: str
    text_content: str
    structured_data: Dict[str, Any] = field(default_factory=dict)
    links: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    tables: List[List[Dict[str, str]]] = field(default_factory=list)
```

#### 3.1.3 Driver Hierarchy & 4-Tier Fallback (`jarvis/browser/driver.py`)
```python
class BaseBrowserDriver:
    """Abstract Browser Driver contract."""
    def launch(self, config: BrowserConfig) -> bool: ...
    def close(self) -> None: ...
    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool: ...
    def click(self, selector: str, timeout_ms: int = 5000) -> bool: ...
    def type_text(self, selector: str, text: str, delay_ms: int = 50) -> bool: ...
    def select_option(self, selector: str, value: str) -> bool: ...
    def wait_for_selector(self, selector: str, state: str = "visible", timeout_ms: int = 10000) -> bool: ...
    def evaluate_script(self, script: str, *args: Any) -> Any: ...
    def get_html(self) -> str: ...
    def get_text(self, selector: Optional[str] = None) -> str: ...
    def capture_page_screenshot(self, full_page: bool = False) -> bytes: ...
    def get_cookies(self) -> List[Dict[str, Any]]: ...
    def set_cookies(self, cookies: List[Dict[str, Any]]) -> None: ...
```

1. **Tier 1: `PlaywrightBrowserDriver`**:
   - Uses `playwright.sync_api` with `chromium.launch(headless=config.headless)`.
   - Handles file download events via `page.expect_download()`.
   - Generates accessibility tree via `page.accessibility.snapshot()`.
2. **Tier 2: `CDPBrowserDriver`**:
   - Connects to existing Chrome debugging port (`http://127.0.0.1:9222/json`) via WebSocket.
   - Dispatches CDP commands: `Page.navigate`, `Runtime.evaluate`, `DOM.querySelector`, `Input.dispatchMouseEvent`.
3. **Tier 3: `HttpScrapingDriver`**:
   - Zero-browser fallback using `requests.Session` + `html.parser` / regex.
   - Extracts page titles, metadata, tables, text, and downloads files via HTTP GET/POST.
4. **Tier 4: `MockBrowserDriver`**:
   - In-memory mock driver with simulated DOM nodes for unit testing and CI verification without network.

#### 3.1.4 Browser Agent Controller (`jarvis/browser/agent.py`)
- **Key Methods**:
  - `open_and_search(query: str, search_engine: str = "duckduckgo") -> ScrapeResult`
  - `scrape_url(url: str, extract_tables: bool = True) -> ScrapeResult`
  - `compare_prices(product_name: str, stores: List[str]) -> List[PriceComparisonItem]`
  - `fill_form(url: str, form_fields: Dict[str, str], submit_selector: Optional[str]) -> BrowserActionResult`
  - `download_resource(url: str, target_path: Optional[str] = None) -> str`
  - `execute_workflow(steps: List[Dict[str, Any]]) -> BrowserActionResult`

---

### 3.2 Requirement R4: Computer-Use Vision & Desktop GUI Interaction (`jarvis/vision/` & `jarvis/automation/`)

#### 3.2.1 Module Structure & Boundaries
```
jarvis/vision/
├── screen.py            # Existing: High-speed capture & Vision LLM client
├── ocr.py               # Existing: Dual-tier Desktop OCR
├── dialog_detector.py   # Existing: Win32 modal dialog detector
├── computer_use.py      # NEW: Coordinate normalization, UI grounding, element detection
└── visual_verifier.py   # NEW: Before/After screenshot diffing & state transition validation

jarvis/automation/
├── control.py           # Existing: Low-level Win32/pyautogui automation
└── gui_actor.py         # NEW: High-level vision-driven actor with verification & self-healing
```

#### 3.2.2 Normalized Coordinate Space & Models (`jarvis/vision/computer_use.py`)
Anthropic Computer-Use specification (1000x1000 normalized grid):
$$x_{pixel} = \mathrm{round}\left(\frac{x_{norm}}{1000} \times W_{screen}\right), \quad y_{pixel} = \mathrm{round}\left(\frac{y_{norm}}{1000} \times H_{screen}\right)$$
$$x_{norm} = \mathrm{round}\left(\frac{x_{pixel}}{W_{screen}} \times 1000\right), \quad y_{norm} = \mathrm{round}\left(\frac{y_{pixel}}{H_{screen}} \times 1000\right)$$

```python
@dataclass
class BoundingBox:
    ymin: int  # 0 - 1000
    xmin: int  # 0 - 1000
    ymax: int  # 0 - 1000
    xmax: int  # 0 - 1000

    @property
    def center_norm(self) -> Tuple[int, int]:
        return (self.xmin + self.xmax) // 2, (self.ymin + self.ymax) // 2

    def to_pixel_coords(self, screen_w: int, screen_h: int) -> Tuple[int, int, int, int]:
        left = int(self.xmin * screen_w / 1000.0)
        top = int(self.ymin * screen_h / 1000.0)
        right = int(self.xmax * screen_w / 1000.0)
        bottom = int(self.ymax * screen_h / 1000.0)
        return left, top, right, bottom

@dataclass
class UIElement:
    name: str
    element_type: str  # button, text_box, menu_item, checkbox, link, icon
    bbox: BoundingBox
    text: Optional[str] = None
    confidence: float = 1.0
    source: str = "vision_llm"  # vision_llm | ocr | win32_uia | template_match
```

#### 3.2.3 4-Tier UI Element Grounding Engine (`UIElementDetector`)
1. **Tier 1: Vision LLM Grounding**: Prompts Gemini 1.5 Flash / GPT-4o Vision with annotated coordinate prompt. Extracts JSON `[{"name": "Save", "bbox": [ymin, xmin, ymax, xmax]}]`.
2. **Tier 2: Local Desktop OCR Bounding Boxes**: Uses `DesktopOCR` / `pytesseract.image_to_data()` to locate bounding boxes of exact text labels instantly without network overhead.
3. **Tier 3: Win32 UI Automation / Child Window Scanner**: Uses `win32gui.EnumChildWindows` & `GetWindowRect` to identify OS-native controls (buttons, edit boxes, list views).
4. **Tier 4: OpenCV / PIL Template Matching**: Detects common UI icons (close X, minimize, search magnifier, reload, folder).

#### 3.2.4 Visual Verification Loop (`jarvis/vision/visual_verifier.py`)
```python
@dataclass
class VisualDiffResult:
    state_changed: bool
    diff_ratio: float           # 0.0 to 1.0 (fraction of pixels changed)
    changed_roi: Optional[Tuple[int, int, int, int]] = None
    expected_change_detected: bool = False
    semantic_verification: str = ""
    before_img_bytes: bytes = b""
    after_img_bytes: bytes = b""

class VisualVerifier:
    """
    Compares before/after screenshots to ensure UI actions executed successfully.
    """
    def __init__(self, diff_threshold: float = 0.005, vision_manager: Optional[ScreenVisionManager] = None):
        self.diff_threshold = diff_threshold
        self.vision_manager = vision_manager or ScreenVisionManager()

    def verify_action(
        self,
        before_bytes: bytes,
        after_bytes: bytes,
        action_type: str,
        target_roi: Optional[Tuple[int, int, int, int]] = None,
        expected_effect: Optional[str] = None,
    ) -> VisualDiffResult:
        """
        1. Fast Pixel Delta: Compute Mean Squared Error (MSE) or Pixel Difference.
        2. ROI check: Did the target click/type area change?
        3. Semantic validation via Vision LLM if expected_effect is specified.
        """
```

#### 3.2.5 Vision-Driven GUI Actor (`jarvis/automation/gui_actor.py`)
- **Key Methods**:
  - `click_element(element_query: str, double_click: bool = False, verify: bool = True) -> bool`
  - `type_into_element(element_query: str, text: str, clear_first: bool = True, verify: bool = True) -> bool`
  - `drag_element(source_query: str, target_query: str, verify: bool = True) -> bool`
  - `perform_verified_action(action_fn: Callable[[], Any], expected_effect: str, max_retries: int = 2) -> bool`

---

### 3.3 Requirement R6: Unified Multi-Modal Integration & HUD Telemetry (`jarvis/audio/`, `jarvis/ui/`, `jarvis/memory/`)

#### 3.3.1 Multi-Modal Voice & Wake Word Integration
- **Flow**:
  1. `WakeWordDetector` receives audio stream from `AudioEngine`.
  2. "Hey JARVIS" detected -> Triggers `app.on_wake_word_detected()`.
  3. `AlwaysOnOverlay.show_listening()` displays glowing Arc Reactor badge + audio waveform.
  4. TTS speaks prompt *"Vâng thưa Ngài, tôi đang lắng nghe."*
  5. `STTEngine` captures user command in Vietnamese.
  6. `LLMIntentRouter` resolves intent:
     - Simple command -> Immediate plugin dispatch.
     - Multi-step complex task -> Dispatches to ReAct Planner (R1) / Browser Agent (R3) / GUI Actor (R4).
  7. Results vocalized via `TTSManager` and rendered on HUD.

#### 3.3.2 Enhanced HUD Sidebar Overlay Telemetry (`jarvis/ui/overlay.py`)
Enhance `AlwaysOnOverlay` with 4 new dedicated widgets:
1. **Task DAG Graph Widget (`TaskDAGFrame`)**:
   - Renders step-by-step progress cards for multi-step tasks.
   - Status indicators: `PENDING` (⚪), `RUNNING` (🟡 ⏳), `SUCCESS` (🟢 ✅), `FAILED` (🔴 ❌), `RETRYING` (🟣 🔄).
   - Step progress bar: Percentage of completed DAG nodes.
2. **Live Execution Log & Code Stream Widget (`CodeLogFrame`)**:
   - Displays running Python/PowerShell sandbox code snippets and live output logs in a syntax-highlighted dark console.
3. **Visual Results Card Widget (`VisualResultFrame`)**:
   - Renders thumbnails of captured screenshots, price comparison tables, or generated matplotlib charts.
4. **Autonomous Execution Control Buttons**:
   - Interactive Tkinter buttons: `⏸ Tạm dừng`, `▶ Tiếp tục`, `⏹ Hủy bỏ tác vụ`.

#### 3.3.3 SQLite Persistent Memory Layer Upgrade (`jarvis/memory/sqlite_store.py`)
Add 3 new tables to SQLite WAL schema:

```sql
-- 1. Agent Task History Table (Task DAG Execution Records)
CREATE TABLE IF NOT EXISTS task_history (
    task_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    goal TEXT NOT NULL,
    plan_dag_json TEXT NOT NULL,
    execution_trace_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    success BOOLEAN NOT NULL DEFAULT 1,
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    created_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
    completed_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_task_history_created ON task_history(created_at);
CREATE INDEX IF NOT EXISTS idx_task_history_status ON task_history(status);

-- 2. Browser Sessions & Cookies Cache Table
CREATE TABLE IF NOT EXISTS browser_sessions (
    domain TEXT PRIMARY KEY,
    cookies_json TEXT NOT NULL,
    local_storage_json TEXT NOT NULL DEFAULT '{}',
    user_agent TEXT NOT NULL DEFAULT '',
    updated_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime'))
);

-- 3. Reusable Agent Workflows / Learned Patterns Table
CREATE TABLE IF NOT EXISTS learned_workflows (
    workflow_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    trigger_pattern TEXT NOT NULL,
    steps_template_json TEXT NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 1,
    last_used_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime'))
);
```

---

## 4. Caveats & Fallback Matrix

| Requirement | Environment / Scenario | Primary Mechanism | Fallback Mechanism | Headless / CI Behavior |
|---|---|---|---|---|
| **R3 (Browser)** | No `playwright` installed | `PlaywrightBrowserDriver` | `CDPBrowserDriver` (port 9222) -> `HttpScrapingDriver` | Auto-uses `MockBrowserDriver` with DOM fixtures |
| **R3 (Browser)** | Cloudflare / Captcha Block | Interactive Headed Browser | Spawns user prompt on HUD for manual solve | Skips / Returns mock data |
| **R4 (Computer Use)** | Headless Linux / No Display | `mss` + `pyautogui` | `PIL.ImageGrab` + Win32 ctypes | Returns synthetic 1280x720 frame + mock click event |
| **R4 (Computer Use)** | No Vision API Key | Gemini 1.5 Flash Vision | Local OCR (`DesktopOCR`) + Win32 UIAutomation | Uses OCR text coordinate grounding |
| **R4 (Computer Use)** | Dead Click (No UI Change) | Visual Verification Diff | Increases click duration, retries with double-click | Logs warning and proceeds if non-critical |
| **R6 (HUD & Voice)** | Headless CI (No DISPLAY / X11) | Tkinter GUI (`root.mainloop()`) | Headless Event Queue (`_headless = True`) | In-memory state tracking, zero GUI errors |
| **R6 (Memory)** | High Concurrent Access | SQLite WAL Mode + Mutex | 10.0s Timeout Retry Queue | `check_same_thread=False` + `threading.RLock` |

---

## 5. Conclusion & Implementation Blueprint

### 5.1 Proposed File Additions & Modifications
1. **New Package `jarvis/browser/`**:
   - `jarvis/browser/__init__.py`
   - `jarvis/browser/models.py`
   - `jarvis/browser/driver.py`
   - `jarvis/browser/session.py`
   - `jarvis/browser/actions.py`
   - `jarvis/browser/scraper.py`
   - `jarvis/browser/agent.py`
2. **Vision & GUI Actor Enhancements**:
   - `jarvis/vision/computer_use.py` (New)
   - `jarvis/vision/visual_verifier.py` (New)
   - `jarvis/automation/gui_actor.py` (New)
3. **HUD & Memory Enhancements**:
   - `jarvis/ui/overlay.py` (Extend with `TaskDAGFrame`, `CodeLogFrame`, `VisualResultFrame`, `update_task_dag()`, `append_code_log()`)
   - `jarvis/memory/sqlite_store.py` (Extend with `task_history`, `browser_sessions`, `learned_workflows` tables and CRUD methods)
4. **Action Dispatcher Integration (`jarvis/core/dispatcher.py`)**:
   - Register actions: `browser_navigate`, `browser_scrape`, `browser_compare_prices`, `browser_fill_form`, `computer_use_click`, `computer_use_type`, `hud_update_dag`, `hud_log_code`.

---

## 6. Verification Method

### 6.1 Recommended Test Suites
Create comprehensive unit and integration tests under `tests/unit/`:

1. `tests/unit/test_browser_agent.py` (Coverage for R3):
   - `test_browser_config_defaults_and_custom()`
   - `test_mock_browser_driver_navigation_and_dom()`
   - `test_browser_session_cookie_serialization()`
   - `test_http_scraping_driver_table_extraction()`
   - `test_browser_scraper_markdown_conversion()`
   - `test_browser_price_comparison_synthesis()`
   - `test_browser_agent_form_filling_workflow()`
   - `test_browser_agent_driver_fallback_chain()`

2. `tests/unit/test_computer_use_vision.py` (Coverage for R4):
   - `test_coordinate_mapper_normalization_and_pixel_conversion()`
   - `test_bounding_box_center_and_clamping()`
   - `test_visual_verifier_pixel_diff_detection()`
   - `test_visual_verifier_roi_change_detection()`
   - `test_gui_actor_verified_click_success()`
   - `test_gui_actor_self_healing_retry_on_dead_click()`
   - `test_ui_element_detector_ocr_grounding_fallback()`

3. `tests/unit/test_hud_telemetry_and_memory.py` (Coverage for R6):
   - `test_overlay_task_dag_state_transitions()`
   - `test_overlay_code_log_streaming()`
   - `test_overlay_visual_result_rendering()`
   - `test_sqlite_memory_store_task_history_crud()`
   - `test_sqlite_memory_store_browser_sessions()`
   - `test_sqlite_memory_store_learned_workflows()`
   - `test_wake_word_to_voice_loop_routing()`

### 6.2 Verification Commands
```powershell
# Run unit tests for R3, R4, R6
pytest tests/unit/test_browser_agent.py tests/unit/test_computer_use_vision.py tests/unit/test_hud_telemetry_and_memory.py -v

# Run system health check
python -m jarvis health-check
```

### 6.3 Invalidation Conditions
- If `BrowserAgent` crashes when `playwright` is not installed (Invalidation test: Must fall back gracefully to `CDPBrowserDriver`, `HttpScrapingDriver`, or `MockBrowserDriver`).
- If `GUIActor` produces unhandled exceptions in headless CI (Invalidation test: Must simulate actions in-memory with logged telemetry).
- If `AlwaysOnOverlay` DAG updates cause Tkinter thread deadlocks (Invalidation test: All UI mutations MUST route through `root.after` thread-safe scheduler).
