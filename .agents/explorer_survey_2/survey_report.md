# JARVIS Personal AI Expansion: Survey & Architecture Report (Part 2)

**Author**: Explorer 2 (System Architecture & Pipeline Mapping)  
**Date**: 2026-08-24  
**Scope**: LLM Router & Prompt Assembly, R2 (Memory & Context System), R3 (Screen Vision Architecture), R5 (Web Intelligence Architecture)  
**Workspace**: `d:/Software GitCode/JARVIS`  

---

## Executive Summary

JARVIS is currently a modular desktop assistant for Windows with 67 modules and 537+ tests. The core voice pipeline (STT → LLM Router → ActionDispatcher → TTS / Overlay UI) is stable. However, the system currently lacks stateful multi-turn memory, screen perception, and real-time live web access. 

This report provides:
1. **As-Is Pipeline Mapping**: Exact execution flow of LLM routing, tool calling, prompt assembly, and TTS/UI response dispatching in the current codebase.
2. **R2 Architecture (Memory & Context System)**: Two-layer memory combining a 10-turn sliding-window session buffer and SQLite persistent database (`logs/memory.db`) with tables for semantic facts, user preferences/habits/projects, episodic event logs, heuristic/LLM memory extractors, and direct memory commands.
3. **R3 Architecture (Screen Vision)**: Low-latency (<100ms capture, <3.0s end-to-end) multi-monitor screenshot pipeline using `mss`/`PIL.ImageGrab`, unified Vision LLM integration (Gemini 1.5 Flash/Pro with base64/inlineData and GPT-4o Vision), dual-tier OCR, Win32 modal error dialog detection (`#32770`), and graceful offline/no-key fallbacks.
4. **R5 Architecture (Web Intelligence)**: Real-time information pipeline with DuckDuckGo/SerpAPI search, OpenWeatherMap + wttr.in fallback, XML RSS feed aggregator (VNExpress/TechCrunch/CoinDesk), realtime Crypto (Binance/CoinGecko) and Currency rates (USD/VND), stock lookups (VNIndex/AAPL/TSLA), thread-safe 10-minute TTL caching layer, and morning briefing composer.

---

## Section 1: LLM Routing & Prompt Assembly in Current Codebase

### 1.1 Prompt Ingestion and Reception Flow

User inputs enter the JARVIS execution pipeline via three distinct entry points:

1. **Voice Input Flow (`JarvisApp._ai_voice_loop`)**:
   - Triggered by acoustic gesture (subsequent double clap) or Wake Word.
   - `JarvisApp.record_audio()` records `dur = stt.timeout_s` (5.0s) float32 audio array via `sounddevice.rec()` (or mock zero-buffer in headless mode).
   - `STTEngine.transcribe(audio_buffer)` converts audio to text (via `WhisperAPI`, `FasterWhisper`, or `WindowsSpeechSTT`).
   - Transcribed string is forwarded to `JarvisApp.process_text_command(transcript, requester="voice")`.

2. **Direct Text Command Flow (`JarvisApp.process_text_command`)**:
   - Invoked directly from CLI (`jarvis cli`), test suites, or automation scripts.
   - Cleans input string, validates non-empty payload, and passes to `self.llm_router.parse_intent(clean_text)`.

3. **Remote / Dashboard Ingestion (`DashboardServer`)**:
   - Ingested via WebSocket `/ws` or REST endpoint `/api/command` and forwarded to `JarvisApp.process_text_command(text, requester="web")`.

```
[User Speech] ──> sounddevice.rec() ──> STTEngine.transcribe() ──┐
[CLI / Tests] ───────────────────────────────────────────────────┼──> JarvisApp.process_text_command()
[Dashboard WS] ──────────────────────────────────────────────────┘           │
                                                                             ▼
                                                                LLMIntentRouter.parse_intent()
                                                                             │
                                              ┌──────────────────────────────┼──────────────────────────────┐
                                              ▼                              ▼                              ▼
                                     Tier 1: Regex & Key            Tier 2: LLM API             Tier 3: Fallback
                                     Fast Path (<1ms)             (Gemini/Claude/OpenAI)       (Rule-based recovery)
```

---

### 1.2 Multi-Tier Intent Routing Engine (`jarvis/llm/router.py`)

Routing operates across three resilient tiers:

#### Tier 1: Fast-Path Rule Engine (Sub-millisecond, < 1ms)
- Checks compiled parametric regex patterns in `self._regex_rules` (e.g., light switches, fan speeds, climate temperature targets `(\d{1,2}) độ`, hardware metrics, Spotify track names, weather cities, reminders).
- If no regex matches, executes greedy substring matching against `self._sorted_rule_keys` (sorted descending by length).
- Returns `IntentResult` with `source="rule_fallback"` or `"rule_fast_path"`.

#### Tier 2: Multi-Provider LLM Semantic Reasoning (`LLMClient` + Dynamic Tool Calling)
- Invoked when fast path fails or when `force_llm=True`.
- Dynamically introspects registered actions in `ActionDispatcher` via `generate_tool_schema_from_dispatcher(self.dispatcher)` to produce OpenAI/Gemini-compliant JSON schemas.
- Assembles system prompt via `build_jarvis_system_prompt(context_info=context)`:
  - Injects Iron Man JARVIS persona (courteous, razor-sharp, Vietnamese/English auto-switching).
  - Supplies few-shot examples for tool calling.
- Dispatches payload via `LLMClient.generate(prompt=text, system_prompt=system_prompt, tools=tools)`.
  - **Gemini (`_call_gemini`)**: Converts `ChatMessage` list into `contents: [{"role": "user"/"model", "parts": [{"text": ...}]}]`, system instruction into `systemInstruction`, and tools into `{"functionDeclarations": [...]}`. POSTs to `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}`.
  - **OpenAI (`_call_openai`)**: Uses standard `tools` parameter and Bearer Authorization.
  - **Claude (`_call_claude`)**: Translates tools to `tools` block and system prompt to `system` parameter.
  - **Ollama (`_call_ollama`)**: Sends JSON payload to local REST endpoint `http://localhost:11434/api/chat`.
- If LLM generates a function call (`ToolCall`), router packages it as:
  `IntentResult(action_name=top_tool.name, parameters=top_tool.arguments, source="llm")`.
- If LLM generates a natural conversational text response, router packages it as:
  `IntentResult(action_name="generic_llm_response", parameters={"reply": reply}, source="llm")`.

#### Tier 3: Graceful Rule Fallback on Error
- Catches network timeouts (`LLMTimeoutError`), rate limits (`LLMRateLimitError`, HTTP 429), authentication errors (missing key, HTTP 401), or connection resets.
- Re-evaluates regex and rule key matchers with confidence `0.85`.
- If completely unrecognized, returns `IntentResult(action_name="unknown_intent", response_text="Tôi chưa hiểu lệnh này, vui lòng thử cách khác")`.

---

### 1.3 Response Processing & TTS/UI Fanout

Once `IntentResult` is produced in `JarvisApp.process_text_command()`:

1. **Action Execution**:
   - If `intent.action_name != "unknown_intent"` and `intent.action_name != "generic_llm_response"`, executes `self.dispatcher.dispatch_action(intent.action_name, payload=intent.parameters)`.
   - If `ActionResult.data` contains a pre-formatted `"message"`, it becomes `response_text`.
   - Otherwise, `self.llm_router.get_natural_response(...)` generates natural Vietnamese phrasing based on entity parameters.
2. **Audio Vocalization (`TTSManager`)**:
   - `self.tts_manager.speak(response_text, wait=False)` synthesizes voice.
   - Primary: ElevenLabs REST API with local WAV disk caching (`.cache/jarvis_welcome/`).
   - Secondary: Windows SAPI5 / `pyttsx3` native voice synthesis.
3. **UI HUD Feedback (`JarvisOverlay`)**:
   - Transitions HUD: `show_listening()` → `show_thinking(transcript)` → `show_response(transcript, response_text)`.
   - Shows cycling typing dots `.` `..` `...` during thinking.
   - Displays auto-hide countdown tooltip `"💡 Double clap để hỏi tiếp"`.
4. **Telemetry & Audit Logging**:
   - Emits WebSocket broadcast via `self.dashboard_server.broadcast_event(...)`.
   - Writes atomic log entry to `logs/jarvis.log` via `_global_log_interaction(...)`:
     `[INTERACTION] 2026-08-24 08:15:00 | TRIGGER: VOICE | INPUT: thời tiết hà nội | ACTION: shell_exec | RESPONSE: Đang kiểm tra thông tin thời tiết tại Hà Nội cho Ngài. | STATUS: success`

---

## Section 2: R2 — Memory & Context System Architecture

### 2.1 Architectural Overview

Currently, JARVIS is completely stateless: each command is processed without prior conversational turns, user preferences, or past interactions.

R2 introduces a **Unified Two-Layer Memory Engine**:
1. **Layer 1: Short-Term Session Buffer (`SessionContextManager`)** — In-memory 10-turn sliding FIFO queue tracking ongoing multi-turn dialogue.
2. **Layer 2: Persistent Long-Term Memory (`SQLiteMemoryStore`)** — SQLite database located at `logs/memory.db` managing:
   - **Semantic Facts & User Profile** (name, email, role, preferences, projects, habits).
   - **Episodic Interaction Log** (historical timestamps, triggers, commands, tool execution parameters, outcomes, execution duration).
   - **Preference / Habit Statistics** (time-of-day query frequency, preferred music/apps).

```
                   ┌────────────────────────────────────────────────────────┐
                   │                     JarvisApp                          │
                   └───────────────────────────┬────────────────────────────┘
                                               │
                                  ┌────────────┴────────────┐
                                  ▼                         ▼
                    ┌───────────────────────────┐ ┌───────────────────┐
                    │   SessionContextManager   │ │   MemoryManager   │
                    │    (10-Turn FIFO Buffer)  │ │ (SQLite Engine)   │
                    └─────────────┬─────────────┘ └─────────┬─────────┘
                                  │                         │
                                  │                         │ logs/memory.db
                                  ▼                         ▼
                    ┌───────────────────────────┐ ┌───────────────────┐
                    │  Prompt Injection Layer   │ │ • facts           │
                    │  (Relevant Facts + Turns) │ │ • episodes        │
                    └─────────────┬─────────────┘ │ • habits          │
                                  │               └───────────────────┘
                                  ▼
                    ┌───────────────────────────┐
                    │    LLM / Router Engine    │
                    └───────────────────────────┘
```

---

### 2.2 Database Schema Design (`logs/memory.db`)

The SQLite database must be thread-safe, use WAL (Write-Ahead Logging) mode for concurrent access, and enforce schema integrity.

```sql
-- Enable WAL mode for high-concurrency read/write
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- 1. Table: facts (User profile, preferences, habits, projects, explicit memories)
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK(category IN ('profile', 'preference', 'habit', 'project', 'system', 'general')),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL DEFAULT 'user_explicit', -- 'user_explicit', 'llm_inferred', 'system_detected'
    created_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
    updated_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at DATETIME,
    UNIQUE(category, key)
);

CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);

-- 2. Table: episodes (Full interaction history and execution telemetry)
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
    trigger_type TEXT NOT NULL,            -- 'VOICE', 'GESTURE', 'CLI', 'WEB', 'PROACTIVE'
    user_input TEXT NOT NULL,
    action_name TEXT NOT NULL DEFAULT 'none',
    action_params TEXT,                    -- JSON string of parameters
    action_result TEXT,                    -- JSON string of action outcome
    response_text TEXT NOT NULL,
    execution_status TEXT NOT NULL CHECK(execution_status IN ('success', 'failed', 'cancelled')),
    latency_ms REAL NOT NULL DEFAULT 0.0,
    error_message TEXT,
    metadata TEXT                          -- JSON string of extra context (e.g. active window, cpu)
);

CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp);
CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_episodes_action ON episodes(action_name);

-- 3. Table: user_habits (Aggregated usage pattern analytics)
CREATE TABLE IF NOT EXISTS user_habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_type TEXT NOT NULL,              -- 'command_frequency', 'time_preference', 'app_usage'
    identifier TEXT NOT NULL,              -- e.g. 'morning_briefing', 'spotify_lofi'
    frequency_count INTEGER NOT NULL DEFAULT 1,
    typical_hour INTEGER CHECK(typical_hour BETWEEN 0 AND 23),
    last_observed_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
    UNIQUE(habit_type, identifier)
);
```

---

### 2.3 Short-Term Session Context Manager Contract

```python
@dataclass
class ConversationTurn:
    turn_id: str
    timestamp: float
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    action_name: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    confidence: float = 1.0


class SessionContextManager:
    """Thread-safe FIFO sliding window of conversation turns."""

    def __init__(self, max_turns: int = 10, session_id: Optional[str] = None) -> None:
        self.max_turns = max_turns
        self.session_id = session_id or str(uuid.uuid4())
        self._history: collections.deque[ConversationTurn] = collections.deque(maxlen=max_turns * 2)
        self._lock = threading.RLock()

    def add_user_turn(self, text: str) -> ConversationTurn:
        turn = ConversationTurn(
            turn_id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            role="user",
            content=text,
        )
        with self._lock:
            self._history.append(turn)
        return turn

    def add_assistant_turn(
        self,
        response_text: str,
        action_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            turn_id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            role="assistant",
            content=response_text,
            action_name=action_name,
            parameters=parameters,
        )
        with self._lock:
            self._history.append(turn)
        return turn

    def get_context_turns(self, limit: int = 10) -> List[ChatMessage]:
        """Formats turns as LLM ChatMessage objects for multi-turn chat."""
        with self._lock:
            recent = list(self._history)[-(limit * 2):]
            return [ChatMessage(role=t.role, content=t.content) for t in recent]

    def clear(self) -> None:
        with self._lock:
            self._history.clear()
            self.session_id = str(uuid.uuid4())
```

---

### 2.4 Persistent Memory Manager API Contract

```python
class MemoryManager:
    """Coordinates SQLite persistence, semantic extraction, and episodic logging."""

    def __init__(self, db_path: str = "logs/memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    # Facts & Preferences
    def save_fact(
        self,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        source: str = "user_explicit",
    ) -> bool: ...

    def get_fact(self, category: str, key: str) -> Optional[str]: ...

    def list_facts(self, category: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]: ...

    def delete_fact(self, category: str, key: str) -> bool: ...

    # Episodic Logs
    def record_episode(
        self,
        session_id: str,
        trigger_type: str,
        user_input: str,
        action_name: str,
        action_params: Dict[str, Any],
        response_text: str,
        status: str,
        latency_ms: float = 0.0,
        error_msg: Optional[str] = None,
    ) -> int: ...

    def query_daily_episodes(self, target_date: Optional[datetime.date] = None) -> List[Dict[str, Any]]: ...

    def summarize_day(self, target_date: Optional[datetime.date] = None) -> str: ...
```

---

### 2.5 Dynamic Memory Injection into System Prompt

`build_jarvis_system_prompt()` in `jarvis/llm/router.py` will query `MemoryManager` to inject active facts and preferences:

```markdown
### User Profile & Long-Term Memories:
- Name: Hưng (xưng hô: 'Ngài' hoặc 'anh Hưng')
- Preferences: Thích nghe nhạc lo-fi khi làm việc, ưu tiên nhiệt độ Celsius
- Projects: Dự án JARVIS Desktop Assistant (Path: d:/Software GitCode/JARVIS)
- Habits: Thường yêu cầu briefing thời tiết và tin tức vào khoảng 08:00 sáng

### Recent Session History:
- User: Mở Spotify bài Lofi Chill
- JARVIS: Đang mở Spotify và phát nhạc cho Ngài.
```

---

### 2.6 Direct Memory Commands Handling

1. **Instant Fact Storage ("JARVIS, nhớ rằng..." / "JARVIS, hãy nhớ là...")**:
   - Fast Regex: `r"(?:nhớ\s*rằng|ghi\s*nhớ|nhớ\s*là|remember\s*that)\s+(.+)"`
   - Extracts payload (e.g. `"tôi tên là Hưng"`, `"tôi thích uống cafe đen"`).
   - If entity parser detects key/value (e.g. `user_name` = `"Hưng"`), saves to `facts` table under `category='profile'` or `'preference'`.
   - Action Name: `memory_save_fact`.
   - Spoken Response: `"Tôi đã ghi nhớ thông tin này, thưa Ngài."`

2. **Daily Activity Summary ("JARVIS, hôm nay tôi đã làm gì?" / "tổng kết hôm nay")**:
   - Fast Regex: `r"(?:hôm\s*nay\s*tôi\s*(?:đã\s*)?làm\s*gì|tóm\s*tắt\s*(?:hoạt\s*động\s*)?hôm\s*nay|lịch\s*sử\s*hôm\s*nay)"`
   - Action Name: `memory_summarize_daily`.
   - Executes `MemoryManager.summarize_day()`.
   - Aggregates:
     - Total commands executed (e.g. 14 commands).
     - Breakdown by categories: 5 smart home commands, 3 music playback, 4 code/workspace executions, 2 web searches.
     - Spoken Response: `"Hôm nay Ngài đã thực hiện 14 tác vụ, bao gồm 4 phiên làm việc với dự án JARVIS và 5 thao tác điều khiển thiết bị thông minh, thưa Ngài."`
     - Displays full itemized timeline in Overlay UI.

---

## Section 3: R3 — Screen Vision Architecture

### 3.1 Architecture Overview

JARVIS Screen Vision gives the assistant visual understanding of the Windows desktop, active application windows, error dialogs, and onscreen documents.

Key Performance Budget:
- Screenshot capture + image compression: **< 80ms**
- OCR / Vision LLM inference: **< 2.5s**
- Total end-to-end latency: **< 3.0s**

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                           ScreenVisionEngine                                │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
 ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
 │ ScreenCaptureManager │   │  Win32DialogDetector │   │   Dual-Tier OCR      │
 │ • mss (Primary)      │   │ • EnumWindows        │   │ • Pytesseract (Local)│
 │ • PIL.ImageGrab      │   │ • #32770 class check │   │ • Vision LLM (Cloud) │
 │ • Multi-Monitor / ROI│   │ • Error / Warning box│   │                      │
 └──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       │
                                       ▼
                     ┌──────────────────────────────────┐
                     │         VisionLLMClient          │
                     │  • Gemini 1.5 Flash (Primary)    │
                     │  • OpenAI GPT-4o Vision          │
                     │  • Graceful No-Key Fallback      │
                     └──────────────────────────────────┘
```

---

### 3.2 Screen Capture Subsystem (`jarvis/vision/screen.py`)

- **Capture Mechanism**:
  - Primary: `mss.mss()` — direct DirectX/GDI memory capture. Latency: 15-35ms.
  - Secondary fallback: `PIL.ImageGrab.grab()` or `win32gui` / `ctypes.windll.gdi32.BitBlt`.
- **Target Selection**:
  - Full Desktop (all virtual monitors combined).
  - Primary Monitor (default).
  - Active Foreground Window ROI (using `GetForegroundWindow()` + `GetWindowRect()`).
- **Compression & Optimization**:
  - Converts image buffer to RGB JPEG format (`quality=80`, `subsampling=1`).
  - Resizes if dimension exceeds max 1920x1080 (reduces upload size to 150-280 KB).
  - Encodes to Base64 string or in-memory byte buffer.

```python
class ScreenCaptureManager:
    """Captures and compresses display buffers with sub-50ms latency."""

    def __init__(self) -> None:
        self._has_mss = False
        try:
            import mss
            self._has_mss = True
        except ImportError:
            pass

    def capture_screenshot(
        self,
        monitor_index: int = 1,
        roi: Optional[Tuple[int, int, int, int]] = None,
        max_width: int = 1920,
        quality: int = 80,
    ) -> Tuple[bytes, str, Tuple[int, int]]:
        """
        Captures screenshot. Returns:
        - raw_jpeg_bytes: bytes
        - base64_jpeg: str
        - (width, height): Tuple[int, int]
        """
        ...
```

---

### 3.3 Vision LLM Integration (`jarvis/vision/vision_client.py`)

Supports Google Gemini Vision and OpenAI GPT-4o with unified error recovery:

1. **Gemini Vision (`gemini-1.5-flash` / `gemini-1.5-pro`)**:
   - Payload uses `inlineData` with `mimeType="image/jpeg"` and base64 data.
   - Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}`.
   - Typical latency on Gemini 1.5 Flash: 1.2s - 1.8s.

```json
{
  "contents": [
    {
      "parts": [
        {"text": "Mô tả ngắn gọn nội dung màn hình và giải thích các cửa sổ đang mở bằng tiếng Việt."},
        {
          "inlineData": {
            "mimeType": "image/jpeg",
            "data": "<BASE64_IMAGE_DATA>"
          }
        }
      ]
    }
  ],
  "generationConfig": {"temperature": 0.3, "maxOutputTokens": 512}
}
```

2. **OpenAI GPT-4o (`gpt-4o` / `gpt-4o-mini`)**:
   - Uses standard chat completion messages with `image_url` data URL:
     `{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}", "detail": "low"}}`.

3. **Offline / Missing Key Fallback**:
   - If no API key is set for Gemini or OpenAI:
     - Returns: `ActionResult(success=False, error="NO_VISION_API_KEY", data={"message": "Tôi chưa thể nhìn thấy màn hình do chưa cấu hình Vision API key, thưa Ngài."})`.

---

### 3.4 Win32 Error Popup & Modal Dialog Detection (`jarvis/vision/dialog_detector.py`)

Combines native Win32 window tree inspection and Vision analysis:

1. **Win32 Window Inspection**:
   - Uses `win32gui.EnumWindows` to detect dialog windows with class name `#32770` (standard Windows MessageBox / Dialog), or windows with titles containing `"Error"`, `"Warning"`, `"Exception"`, `"Crash"`, `"Lỗi"`, `"Cảnh báo"`.
   - Reads dialog static text controls via `win32gui.GetWindowText` and `EnumChildWindows`.
2. **Vision-Assisted Visual Analysis**:
   - If dialog text is custom-rendered (e.g. Electron / Chromium modal, VS Code red squiggle tooltip), captures foreground window screenshot and prompts Vision LLM:
     `"Phát hiện xem có hộp thoại lỗi hoặc cảnh báo nào trên ảnh không. Nếu có, trích xuất mã lỗi, thông báo lỗi và hướng dẫn 1 câu khắc phục."`
3. **Dispatcher Actions**:
   - `screen_inspect`: "JARVIS, màn hình tôi đang hiện gì?"
   - `screen_explain_error`: "JARVIS, lỗi này là gì?"
   - `screen_summarize_doc`: "JARVIS, tóm tắt tài liệu này"

---

## Section 4: R5 — Web Intelligence Architecture

### 4.1 Architecture Overview

JARVIS Web Intelligence provides live, external world awareness while strictly safeguarding performance and preventing API rate-limiting through a thread-safe caching layer.

```
                      ┌────────────────────────────────────────────────────────┐
                      │                 WebIntelligenceHub                     │
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                      ┌───────────────────────────┼───────────────────────────┐
                      │                           │                           │
                      ▼                           ▼                           ▼
        ┌───────────────────────────┐ ┌───────────────────────┐ ┌───────────────────────────┐
        │       SearchEngine        │ │    WeatherProvider    │ │    FinanceExchangeHub     │
        │ • DuckDuckGo (Free)       │ │ • OpenWeatherMap      │ │ • Crypto (Binance/Coingecko)│
        │ • SerpAPI (Fallback)      │ │ • wttr.in (Fallback)  │ │ • Forex (USD/VND, EUR/VND)  │
        │ • Live Web Summarizer     │ │ • Hanoi/HCM default   │ │ • Stocks (VNIndex, AAPL)    │
        └─────────────┬─────────────┘ └───────────┬───────────┘ └─────────────┬─────────────┘
                      │                           │                           │
                      └───────────────────────────┼───────────────────────────┘
                                                  │
                                                  ▼
                                    ┌───────────────────────────┐
                                    │    RSS News Aggregator    │
                                    │ • VNExpress / TuoiTre     │
                                    │ • TechCrunch / CoinDesk   │
                                    └─────────────┬─────────────┘
                                                  │
                                                  ▼
                                    ┌───────────────────────────┐
                                    │  10-Minute TTL Cache      │
                                    │  (In-Memory Thread-Safe)  │
                                    └───────────────────────────┘
```

---

### 4.2 Module Breakdown & API Specifications

#### 1. Web Search (`jarvis/web/search.py`)
- **Engine Priority**:
  1. `duckduckgo_search` (`DDGS().text(query, max_results=5)`) — zero cost, zero API keys.
  2. Direct HTML DuckDuckGo scraper (`https://html.duckduckgo.com/html/?q={query}`).
  3. SerpAPI (`https://serpapi.com/search.json?q={query}&api_key={SERPAPI_KEY}`).
- **Summarizer**:
  - Compiles top 3-5 snippet snippets into prompt for `LLMClient`.
  - Output: 2-3 sentence factual Vietnamese summary with source URLs.

#### 2. Live Weather Provider (`jarvis/web/weather.py`)
- **Location Configuration**:
  - Default configurable in `config/default_config.yaml`: `web.weather.default_city: "Hà Nội"`.
  - Normalizes aliases: `"Hà Nội"`, `"Hanoi"`, `"Sài Gòn"`, `"TP.HCM"`, `"Hồ Chí Minh"`, `"Đà Nẵng"`.
- **API Endpoints**:
  1. Primary: OpenWeatherMap API v2.5 / v3.0 (`api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric&lang=vi`).
  2. Fallback: `wttr.in/{city}?format=j1` or `wttr.in/{city}?format=3` (pure HTTP JSON, 100% free, zero configuration).
- **Data Model**:
  `WeatherData(city="Hà Nội", temp_c=28.5, feels_like_c=31.0, condition="Nhiều mây, có mưa rào", humidity=78, wind_kph=14.5, uv_index=4)`
- **Vocal Output**:
  `"Thời tiết tại Hà Nội hiện tại 28.5 độ C, nhiều mây và có thể có mưa rào rải rác. Độ ẩm 78%, thưa Ngài."`

#### 3. RSS News Aggregator (`jarvis/web/news.py`)
- **Feed Sources**:
  - Tech / IT: `https://vnexpress.net/rss/so-hoa.rss` (VnExpress Số Hóa), `https://techcrunch.com/feed/`
  - World / Business: `https://vnexpress.net/rss/the-gioi.rss`, `https://vnexpress.net/rss/kinh-doanh.rss`
  - Crypto: `https://www.coindesk.com/arc/outboundfeeds/rss/`
- **Parsing**:
  - Uses standard library `xml.etree.ElementTree` to parse RSS 2.0 `<channel><item>` and Atom `<entry>` feeds without requiring third-party C-extensions.
  - Sanitizes HTML tags in `<description>` via regex.
  - Selects top 3 headlines published within the last 24 hours.

#### 4. Real-time Crypto, Currency & Stock Financial Rates (`jarvis/web/finance.py`)
- **Crypto Rates**:
  - Public Binance Ticker API: `https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT` and `ETHUSDT`.
  - Public CoinGecko API: `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd,vnd&include_24hr_change=true`.
- **Currency Exchange (USD/VND, EUR/VND)**:
  - Free ExchangeRate-API: `https://open.er-api.com/v6/latest/USD` -> extracts `rates["VND"]`.
  - Fallback: Static fallback with warning tag.
- **Stock Ticker Lookups**:
  - VN-Index & Vietnamese Stocks: Public TCBS / CafeF endpoints (`https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term?ticker=VNINDEX`).
  - US Stocks (AAPL, MSFT, TSLA, NVDA): Yahoo Finance public chart API (`https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d`).

#### 5. Thread-Safe 10-Minute Caching Layer (`jarvis/web/cache.py`)
- **Specification**:
  - In-memory `TTLCache` with TTL = 600.0s (10 minutes).
  - Cache keys formed deterministically: `hash_key = f"{domain}:{hashlib.sha256(json.dumps(params).encode()).hexdigest()}"`.
  - Thread safety enforced via `threading.RLock`.
  - Periodic background eviction of expired entries.

#### 6. Morning Briefing Workflow ("JARVIS, briefing sáng nay")
- Aggregates:
  1. Weather forecast for default city (e.g. Hà Nội).
  2. Top 3 technology & world headlines.
  3. BTC / ETH price snapshot with 24h change %.
  4. USD/VND exchange rate.
  5. Active projects / reminders from R2 Memory.
- Generates:
  - Spoken summary for TTS vocalization (under 4 sentences).
  - Multi-bullet structured text for Overlay UI display.

#### 7. Graceful Offline Detection
- Before making external network calls, probes network status via lightweight DNS socket probe (`socket.create_connection(("1.1.1.1", 53), timeout=1.0)`).
- If offline:
  - Immediately returns cached data if available (with `" [Dữ liệu lưu đệm]"` notice).
  - If no cache exists, returns polite Vietnamese fallback: `"Xin lỗi Ngài, tôi không có kết nối mạng để tải thông tin này."` without hanging or throwing exceptions.

---

## Section 5: Integration Map & ActionDispatcher Schemas

The following actions will be registered into `ActionDispatcher`:

| Action Name | Module | Parameters | Description | Natural Response Format |
|---|---|---|---|---|
| `memory_save_fact` | R2 Memory | `category: str`, `key: str`, `value: str` | Saves a long-term fact or preference | "Tôi đã ghi nhớ thông tin này, thưa Ngài." |
| `memory_query_fact` | R2 Memory | `category: Optional[str]`, `key: str` | Retrieves stored fact from memory.db | "Theo những gì tôi nhớ, [value], thưa Ngài." |
| `memory_summarize_daily`| R2 Memory | `date: Optional[str]` | Summarizes episodic interactions for the day | "Hôm nay Ngài đã thực hiện [N] tác vụ..." |
| `screen_capture` | R3 Vision | `monitor: int = 1`, `save_path: Optional[str]` | Takes screenshot and saves/returns path | "Đã chụp ảnh màn hình của Ngài." |
| `screen_inspect` | R3 Vision | `query: Optional[str]` | Analyzes current screen with Vision LLM | "Trên màn hình của Ngài hiện có..." |
| `screen_explain_error` | R3 Vision | `target: Optional[str]` | Explains error dialog/trace on screen | "Lỗi này xảy ra do [cause]. Ngài có thể..." |
| `screen_summarize_doc` | R3 Vision | `window_name: Optional[str]` | OCR + Vision summary of open document | "Tài liệu này nói về [summary]..." |
| `web_search` | R5 Web | `query: str`, `num_results: int = 5` | DuckDuckGo search and LLM summary | "Theo tìm kiếm: [summary]..." |
| `web_weather` | R5 Web | `location: Optional[str]` | OpenWeatherMap / wttr.in weather query | "Thời tiết tại [city] là [temp] độ C..." |
| `web_news_briefing` | R5 Web | `topic: str = "tech"`, `limit: int = 3` | Top RSS news headlines | "Tin tức công nghệ mới nhất..." |
| `web_crypto_rate` | R5 Web | `symbol: str = "BTC"`, `currency: str = "USD"`| Realtime crypto rate and 24h change | "Giá Bitcoin hiện tại là [price] USD..." |
| `web_currency_rate` | R5 Web | `base: str = "USD"`, `target: str = "VND"` | Currency exchange rate | "Tỷ giá USD trên VND hiện là [rate]..." |
| `web_morning_briefing` | R5 Web | `city: Optional[str]` | Full morning briefing synthesis | "Chào buổi sáng thưa Ngài. Hôm nay..." |

---

## Section 6: Configuration Schema Expansion (`config/default_config.yaml`)

```yaml
# ── R2: Memory & Context System ──────────────────────────────────────────
memory:
  enabled: true
  db_path: "logs/memory.db"
  session_max_turns: 10
  auto_inject_facts: true
  max_injected_facts: 5
  episodic_retention_days: 90

# ── R3: Screen Vision ───────────────────────────────────────────────────
vision:
  camera_index: 0
  screen:
    enabled: true
    capture_engine: "mss"          # "mss", "pil", "win32"
    primary_monitor_only: true
    max_resolution: [1920, 1080]
    jpeg_quality: 80
    vision_provider: "gemini"      # "gemini", "openai", "fallback"
    ocr_engine: "pytesseract"      # "pytesseract", "vision"
    dialog_detection:
      enabled: true
      poll_interval_s: 5.0
      auto_notify_errors: false   # Advisory only

# ── R5: Web Intelligence ────────────────────────────────────────────────
web:
  cache_ttl_seconds: 600           # 10 minutes cache
  offline_timeout_s: 2.0
  weather:
    enabled: true
    provider: "openweathermap"    # "openweathermap", "wttr_in"
    api_key: ""                   # Read from OPENWEATHER_API_KEY
    default_city: "Hà Nội"
  search:
    enabled: true
    provider: "duckduckgo"        # "duckduckgo", "serpapi"
    max_results: 5
  news:
    enabled: true
    feeds:
      tech: "https://vnexpress.net/rss/so-hoa.rss"
      crypto: "https://www.coindesk.com/arc/outboundfeeds/rss/"
      world: "https://vnexpress.net/rss/the-gioi.rss"
  finance:
    enabled: true
    default_crypto: ["BTC", "ETH"]
    default_currency_pair: "USD/VND"
    default_stocks: ["VNINDEX", "AAPL"]
```

---

## Section 7: Verification & Testing Strategy

To ensure zero regressions across the existing 537+ tests and guarantee high reliability for R2, R3, and R5:

1. **Unit Test Matrix**:
   - `tests/unit/test_memory_system.py`: SQLite initialization, WAL mode, CRUD on `facts`, `episodes` recording, sliding window turn eviction at turn 11, auto-summary of daily interactions.
   - `tests/unit/test_screen_vision.py`: Screenshot capture latency mock, Gemini/OpenAI vision payload formatting, base64 encoding, dialog detection heuristics, missing key fallback string validation.
   - `tests/unit/test_web_intelligence.py`: 10-minute cache hit/miss behavior, DuckDuckGo search parser, RSS XML element extraction, weather converter, offline network probe fallback.
2. **Adversarial & Stress Tests**:
   - Multi-threaded SQLite stress: 30 concurrent threads writing episodes and reading facts simultaneously without `database is locked` error.
   - Cache expiry and thread safety under high throughput.
   - Vision and Web timeout resilience: simulated 10s slow HTTP requests gracefully falling back within 2.0s timeout.
3. **Health-Check Integration**:
   - Extend `jarvis/cli.py` `run_health_check()` to diagnose:
     - SQLite `logs/memory.db` write permissions and schema status.
     - Screen capture availability (`mss` / `PIL`).
     - Vision API key presence (`GEMINI_API_KEY` / `OPENAI_API_KEY`).
     - Internet connectivity and weather/crypto endpoint reachability.
