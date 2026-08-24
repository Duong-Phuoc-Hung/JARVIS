# Handoff Report: Milestone 3 Startup Intro, Randomized Greetings & Structured Interaction Logging Blueprint

**Agent**: Explorer M3.2 (`explorer_m3_2`)  
**Target Milestone**: Milestone 3 (UX Polish, Animations & Interaction Logging)  
**Deliverable**: Comprehensive Technical Investigation & Implementation Blueprint for:
1. **Vocal Startup Introduction** in `jarvis/core/app.py` (`JarvisApp.start()`)
2. **Randomized Greeting Pool** in `jarvis/tts/manager.py` (`TTSManager.speak_welcome()`)
3. **Structured `[INTERACTION]` Logging** in `jarvis/core/app.py`, `jarvis/core/logger.py`, and `logs/jarvis.log`

---

## 1. Observation

Direct examination of the repository source code and configuration files revealed the following exact observations:

### 1.1 `JarvisApp.start()` Lifecycle & Startup Introduction (`jarvis/core/app.py`)
- In `jarvis/core/app.py` (lines 629–633):
  ```python
  # Startup self-introduction speech
  if self.tts_manager:
      startup_greeting = self.config.get("welcome.startup_greeting") or "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."
      self.tts_manager.speak(startup_greeting, wait=False)
  ```
- **Observation 1.1a (Config Key Mismatch)**: `self.config.get("welcome.startup_greeting")` queries the root level `welcome` section, whereas `config/default_config.yaml` places welcome settings under `tts.welcome`. If a user configures `tts.welcome.startup_phrase` or `welcome.startup_greeting`, key resolution must check both hierarchy levels before falling back to the hardcoded default `"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."`.
- **Observation 1.1b (Exception Isolation)**: `self.tts_manager.speak()` is not enclosed in a `try...except` block in `start()`. If audio device initialization fails or TTS encounters a system error in headless CI runners, `JarvisApp.start()` could throw an unhandled exception and abort startup.
- **Observation 1.1c (Non-Blocking Guarantee)**: In `TTSManager.speak(text, wait=False)` (lines 99–101), asynchronous speech calls `self._queue.put(...)` and returns immediately (`True`), which fulfills the non-blocking constraint.

### 1.2 Welcome Greeting Pool & Precedence Bug (`jarvis/tts/manager.py`)
- In `jarvis/tts/manager.py` (lines 24–29 and 150–169):
  ```python
  WELCOME_PHRASES: List[str] = [
      "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.",
      "Chào mừng Ngài trở lại. Mọi hệ thống đang hoạt động tối ưu.",
      "Xin chào sếp, JARVIS đã sẵn sàng phục vụ.",
      "Welcome home sir. Tất cả các kết nối và cảm biến đã hoàn tất khởi động.",
  ]
  ```
  ```python
  def speak_welcome(self, delay_s: float = 1.0, phrase: Optional[str] = None) -> None:
      """Plays a randomized Tony Stark-style welcome phrase in a detached daemon thread."""
      import random
      if phrase:
          welcome_phrase = phrase
      elif self.config.get("welcome", {}).get("phrase"):
          welcome_phrase = self.config.get("welcome", {}).get("phrase")
      else:
          phrases = self.config.get("welcome", {}).get("phrases") or WELCOME_PHRASES
          available = [p for p in phrases if p != self._last_welcome_phrase] or list(phrases)
          welcome_phrase = random.choice(available)
          self._last_welcome_phrase = welcome_phrase
  ```
- **Observation 1.2a (Config Key Precedence Defect)**: In `config/default_config.yaml` (lines 80–86):
  ```yaml
  tts:
    welcome:
      enabled: true
      phrase: "Welcome home sir. Congratulations on the new client for your SaaS app—make sure to follow up..."
      phrases:
        - "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."
        - "Chào mừng Ngài trở lại. Mọi hệ thống đang hoạt động tối ưu."
        - "Xin chào sếp, JARVIS đã sẵn sàng phục vụ."
        - "Welcome home sir. Tất cả các kết nối và cảm biến đã hoàn tất khởi động."
  ```
  Because `self.config.get("welcome", {}).get("phrase")` exists in `default_config.yaml`, the `elif` branch is **always** taken. As a result, the randomized greeting pool in `phrases` is completely shadowed and never reached.
- **Observation 1.2b (Config Nesting Normalization)**: `TTSManager` receives `self.config = config or {}`. When instantiated via `TTSManager(config=self.config.get("tts", {}))`, `self.config` has `welcome` as a top-level key in that sub-dict. However, if `TTSManager` is passed the root configuration dictionary, `welcome` is nested under `config["tts"]["welcome"]`. A robust resolver must inspect both locations.
- **Observation 1.2c (Thread-Safe Non-Repeating Random Selection)**: `self._last_welcome_phrase` tracking is not guarded by `self._lock` in `speak_welcome()`. While `random.choice` is safe, atomic exclusion of the immediately preceding phrase across concurrent invocations requires synchronized state update.

### 1.3 Interaction Logging Format & Persistence (`jarvis/core/app.py` & `jarvis/core/logger.py`)
- In `ORIGINAL_REQUEST.md` (R4, R6) and `PROJECT.md` (Feature 14):
  - Structured format requirement:
    `[INTERACTION] <timestamp> | TRIGGER: <trigger_type> | INPUT: <transcript/input> | ACTION: <action_name> | RESPONSE: <response_text> | STATUS: <success/failed>`
  - File target: `logs/jarvis.log` with directory creation guarantee (`logs/` directory auto-created if missing).
  - Target interactions:
    1. Voice commands (`_ai_voice_loop` and `process_voice_command`)
    2. Text commands (`process_text_command`)
    3. Acoustic gesture triggers (`_on_gesture_event`)
- In `jarvis/core/logger.py` (lines 100–178):
  `setup_logging` configures a `RotatingFileHandler` writing to `logs/jarvis.log` with max 10MB and 5 backups. `JarvisLoggerAdapter` currently provides `log_trigger` and `log_action`, but lacks a dedicated `log_interaction` helper that guarantees formatted dual output (to both the standard logger stream and direct thread-safe file append).
- In `jarvis/core/app.py` (lines 516–591):
  `process_text_command` executes intent routing and action dispatch, but currently emits only general debug logs and dashboard broadcasts without writing the structured `[INTERACTION]` line.

---

## 2. Logic Chain

### 2.1 Logic Chain 1: Vocal Startup Introduction in `app.py`
1. **Trigger Condition**: When `JarvisApp.start()` completes subsystem initialization and spins up background listeners (audio stream, dashboard server, tray icon, overlay HUD), the assistant must vocalize its operational readiness.
2. **Phrase Invariance**: The prompt mandates the exact phrase:
   `"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."`
3. **Hierarchy Fallback**:
   - First check: `self.config.get("tts.welcome.startup_phrase")`
   - Second check: `self.config.get("welcome.startup_greeting")`
   - Fallback: `"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."`
4. **Execution & Non-blocking Guarantee**:
   Calling `self.tts_manager.speak(startup_greeting, wait=False)` enqueues the speech request into `self.tts_manager._queue`. The queue is drained by the dedicated `TTS-Worker` background thread, ensuring `app.start()` returns in under $10\text{ ms}$ without blocking the main event loop.
5. **Fault Isolation**:
   If audio hardware is missing (headless CI/CD environment), `tts_manager` is `None`, or an internal TTS synthesis error occurs, wrapping the call in a `try...except Exception as e` block ensures `app.start()` logs a warning and continues running uninterrupted.

### 2.2 Logic Chain 2: Randomized Welcome Greeting Pool in `manager.py`
1. **Fixing the Config Precedence Inversion**:
   - When `phrases` (a list of 2 or more strings) is configured under `welcome.phrases` (or default `WELCOME_PHRASES`), the pool must take precedence over a static `phrase` string.
   - If only a single string is configured under `welcome.phrase` and `phrases` is not provided or empty, use that single phrase.
   - If an explicit `phrase` argument is passed directly to `speak_welcome(phrase="...")`, use the explicit argument.
2. **Non-Repeating Random Selection Algorithm**:
   - Given a candidate list $P = [p_1, p_2, \dots, p_n]$:
     - If $|P| > 1$, define available set $A = \{p \in P \mid p \ne \text{last\_phrase}\}$. If $A = \emptyset$, reset $A = P$.
     - Select $p_{\text{chosen}} = \text{random.choice}(A)$.
     - Update $\text{last\_phrase} \leftarrow p_{\text{chosen}}$ within `with self._lock:` block.
   - Return $p_{\text{chosen}}$.
3. **Thread Safety & Delay Dispatch**:
   `speak_welcome(delay_s=1.0)` spawns a detached daemon thread `WelcomeTTS` that sleeps for `delay_s` (to allow background audio/music like Spotify to start first) and then calls `self.speak(chosen_phrase, wait=False)`.

### 2.3 Logic Chain 3: Structured Interaction Logging Architecture
1. **Unified Schema Compliance**:
   Every user-initiated or acoustic event triggers an interaction log line formatted exactly as:
   ```text
   [INTERACTION] <YYYY-MM-DD HH:MM:SS> | TRIGGER: <trigger_type> | INPUT: <input_text> | ACTION: <action_name> | RESPONSE: <response_text> | STATUS: <status>
   ```
2. **Interaction Event Taxonomy**:
   | Trigger Type | Source Context | Input Value | Action Value | Response Value | Status |
   |---|---|---|---|---|---|
   | `VOICE` | `_ai_voice_loop` / `process_voice_command` | Transcribed user speech (e.g., `"bật nhạc"`) | Dispatched action name (e.g., `"spotify"`) | Natural response text | `success` or `failed` |
   | `VOICE` | Silence / STT failure in voice loop | `"(silence)"` | `"none"` | `"Tôi không nghe thấy gì cả. Vui lòng thử lại."` | `failed` |
   | `TEXT` / `USER` / `CLI` / `DASHBOARD` | `process_text_command` | Clean input command text | Dispatched action name | Natural response text | `success` or `failed` |
   | `GESTURE:double_clap` | `_on_gesture_event` (1st double clap) | `"double_clap"` | `"welcome_sequence"` | `"Welcome sequence dispatched"` | `success` |
   | `GESTURE:triple_clap` | `_on_gesture_event` (triple clap) | `"triple_clap"` | `"system_status"` | Live CPU/RAM vocal summary | `success` |
   | `GESTURE:clap_pause_clap` | `_on_gesture_event` (clap-pause-clap) | `"clap_pause_clap"` | `"show_overlay"` | `"Chat overlay displayed"` | `success` |
   | `GESTURE:<custom>` | `_on_gesture_event` (other patterns) | Pattern identifier | Configured action list string | Execution summary | `success` or `failed` |
3. **Dual Persistence & Thread Safety**:
   - Primary: Logged through `logging.getLogger("jarvis.interaction")` at `INFO` level.
   - Secondary: Direct atomic UTF-8 append to `logs/jarvis.log`.
   - File Creation: Parent directory `logs/` is auto-created with `parents=True, exist_ok=True`.
   - Thread Lock: Class-level `_INTERACTION_LOCK = threading.Lock()` guarantees no line tearing under high concurrency (e.g., 20+ worker threads).

---

## 3. Caveats & Edge Cases

1. **Test Environment Headless Execution**:
   In automated unit test environments (e.g., `tests/test_user_simulation.py` or headless pytest runs), sound hardware may be completely absent. `TTSManager.speak(..., wait=False)` and `fallback_engine.speak()` must execute in mock/silent mode without throwing COM/SAPI5 Windows exceptions.
2. **Log File Rotation & File Locking on Windows**:
   On Windows, opening files with `open(path, "a")` concurrently across multiple threads is safe if guarded by a Python `threading.Lock`. However, if `RotatingFileHandler` is actively rotating `logs/jarvis.log` at 10MB threshold, transient `PermissionError` on rename could occur if another handle is open. The direct append implementation must catch `OSError`/`PermissionError` gracefully so logging never crashes the application.
3. **Newline Sanitization in Inputs and Responses**:
   Multi-line inputs or LLM responses containing newline characters (`\n`) must be sanitized (e.g. replacing `\n` with ` ` or stripping excess whitespace) so each `[INTERACTION]` record occupies strictly one single log line for reliable grep/parsing.

---

## 4. Conclusion & Precise Code Blueprints

Below are the exact code modifications required for the worker to implement.

### 4.1 Blueprint 1: `jarvis/core/app.py` Modifications

#### A. Add `log_interaction` Helper to `JarvisApp`
```python
    def log_interaction(
        self,
        trigger: str,
        input_text: str,
        action: str,
        response: str,
        status: str = "success",
    ) -> str:
        """
        Structured interaction logger compliant with R6, R4, and M3 specification.
        Format:
        [INTERACTION] <timestamp> | TRIGGER: <trigger_type> | INPUT: <transcript/input> | ACTION: <action_name> | RESPONSE: <response_text> | STATUS: <success/failed>
        """
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clean_trigger = str(trigger or "UNKNOWN").strip()
        # Sanitize newlines to maintain single-line log structure
        clean_input = " ".join(str(input_text or "").split())
        clean_action = str(action or "none").strip()
        clean_response = " ".join(str(response or "").split())
        clean_status = "success" if str(status).lower() in ("success", "ok", "true", "1") else "failed"

        log_line = (
            f"[INTERACTION] {timestamp} | TRIGGER: {clean_trigger} | "
            f"INPUT: {clean_input} | ACTION: {clean_action} | "
            f"RESPONSE: {clean_response} | STATUS: {clean_status}"
        )

        # 1. Output to standard logger
        log.info(log_line)

        # 2. Append directly to dedicated logs/jarvis.log
        try:
            log_file_cfg = self.config.get("logging.file", "logs/jarvis.log") if self.config else "logs/jarvis.log"
            log_path = Path(log_file_cfg)
            if not log_path.is_absolute():
                workspace_root = Path(__file__).resolve().parent.parent.parent
                log_path = workspace_root / log_path

            log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(log_line + "\n")
        except Exception as e:
            log.warning("Failed to append interaction log to %s: %s", log_file_cfg, e)

        return log_line
```

#### B. Update `JarvisApp.start()` Startup Intro (Lines 629–634)
```python
        # Startup self-introduction speech (F-13 / R4)
        if self.tts_manager:
            try:
                startup_greeting = (
                    self.config.get("tts.welcome.startup_phrase")
                    or self.config.get("welcome.startup_greeting")
                    or "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."
                )
                self.tts_manager.speak(startup_greeting, wait=False)
                log.info("Startup vocal introduction queued: '%s'", startup_greeting)
            except Exception as e:
                log.warning("Startup vocal introduction failed to queue: %s", e)
```

#### C. Update `JarvisApp.process_text_command()` to Emit Interaction Logs
```python
    def process_text_command(self, text: str, requester: str = "user") -> Dict[str, Any]:
        """
        Executes text command:
        Intent Parsing -> Tool Execution -> Spoken TTS Response -> Dashboard Broadcast -> Structured Interaction Log.
        """
        clean_text = text.strip()
        trigger_name = requester.upper() if requester else "USER"
        if not clean_text:
            self.log_interaction(
                trigger=trigger_name,
                input_text="",
                action="none",
                response="Empty command",
                status="failed",
            )
            return {"success": False, "error": "Empty command"}

        intent_result = None
        if self.llm_router:
            try:
                intent_result = self.llm_router.parse_intent(clean_text)
            except Exception as e:
                log.error("LLM Intent Router failed: %s", e)

        # Execute matched action
        response_text = ""
        action_result = None
        status_flag = "success"

        if intent_result and intent_result.action_name != "unknown_intent":
            try:
                action_result = self.dispatcher.dispatch_action(
                    action_name=intent_result.action_name,
                    payload=intent_result.parameters,
                    requester=RequesterContext.user(requester_id=requester, authenticated=True),
                )
                if (
                    action_result
                    and action_result.data
                    and isinstance(action_result.data, dict)
                    and action_result.data.get("message")
                ):
                    response_text = str(action_result.data["message"])
                elif intent_result.action_name == "generic_llm_response":
                    response_text = intent_result.parameters.get("reply", "")
                elif intent_result.response_text:
                    response_text = intent_result.response_text
                else:
                    if self.llm_router and hasattr(self.llm_router, "get_natural_response"):
                        response_text = self.llm_router.get_natural_response(
                            intent_result.action_name,
                            params=intent_result.parameters,
                            text=clean_text,
                            action_result=action_result,
                        )
                    else:
                        response_text = f"Đã thực hiện lệnh: {intent_result.action_name}"
            except Exception as e:
                log.error("Action execution failed: %s", e)
                response_text = f"Lỗi thực thi: {e}"
                status_flag = "failed"
        else:
            response_text = "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"
            status_flag = "failed"

        # Vocalize response via TTS
        if self.tts_manager and response_text:
            self.tts_manager.speak(response_text, wait=False)

        if self.tray_controller:
            self.tray_controller.update_status(TrayStatus.ACTIVE)

        if self.dashboard_server:
            self.dashboard_server.broadcast_event({
                "type": "command",
                "input": clean_text,
                "response": response_text,
                "action": intent_result.action_name if intent_result else "none",
            })

        # Emit structured interaction log
        self.log_interaction(
            trigger=trigger_name,
            input_text=clean_text,
            action=intent_result.action_name if intent_result else "none",
            response=response_text,
            status=status_flag,
        )

        return {
            "success": status_flag == "success",
            "transcript": clean_text,
            "intent": intent_result.to_dict() if hasattr(intent_result, "to_dict") else None,
            "result": action_result.to_dict() if action_result else None,
            "response_text": response_text,
        }
```

#### D. Update `JarvisApp._on_gesture_event()` to Emit Interaction Logs
```python
        # 1. DOUBLE CLAP - First activation:
        if pattern_name == "double_clap":
            if not self.welcome_executed:
                self.welcome_executed = True
                log.info("First activation — running welcome sequence.")
                self.log_interaction(
                    trigger="GESTURE:double_clap",
                    input_text="double_clap",
                    action="welcome_sequence",
                    response="Khởi chạy chuỗi hành động chào mừng và ứng dụng làm việc",
                    status="success",
                )
                ...
            else:
                # Subsequent double claps handled inside _ai_voice_loop
                ...

        # 2. TRIPLE CLAP:
        if pattern_name == "triple_clap":
            action_names = self.config.get("gesture.patterns.triple_clap.actions", ["system_status"])
            for act in action_names:
                try:
                    self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                except Exception as e:
                    log.error("Action [%s] failed for pattern [triple_clap]: %s", act, e)
            self.log_interaction(
                trigger="GESTURE:triple_clap",
                input_text="triple_clap",
                action=",".join(action_names),
                response="Báo cáo tình trạng hệ thống và phần cứng",
                status="success",
            )
            return

        # 3. CLAP-PAUSE-CLAP:
        if pattern_name == "clap_pause_clap":
            action_names = self.config.get("gesture.patterns.clap_pause_clap.actions", ["show_overlay"])
            for act in action_names:
                try:
                    self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                except Exception as e:
                    log.error("Action [%s] failed for pattern [clap_pause_clap]: %s", act, e)
            self.log_interaction(
                trigger="GESTURE:clap_pause_clap",
                input_text="clap_pause_clap",
                action=",".join(action_names),
                response="Hiển thị cửa sổ giao diện JARVIS Overlay HUD",
                status="success",
            )
            return
```

#### E. Update `_ai_voice_loop` for Silence Interaction Logging
```python
                    if not transcript or not transcript.strip():
                        if self.overlay:
                            self.overlay.show_response("(không nghe thấy)", "Tôi không nghe thấy gì. Vui lòng thử lại.")
                        if self.tts_manager:
                            self.tts_manager.speak("Tôi không nghe thấy gì cả. Vui lòng thử lại.", wait=False)
                        if self.tray_controller:
                            self.tray_controller.update_status(TrayStatus.ACTIVE)
                        self.log_interaction(
                            trigger="VOICE",
                            input_text="(silence)",
                            action="none",
                            response="Tôi không nghe thấy gì cả. Vui lòng thử lại.",
                            status="failed",
                        )
                        return
```

---

### 4.2 Blueprint 2: `jarvis/tts/manager.py` Modifications

#### A. Enhanced Pool Resolution & Non-Repeating Random Selection
```python
WELCOME_PHRASES: List[str] = [
    "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.",
    "Chào mừng Ngài trở lại. Mọi hệ thống đang hoạt động tối ưu.",
    "Xin chào sếp, JARVIS đã sẵn sàng phục vụ.",
    "Welcome home sir. Tất cả các kết nối và cảm biến đã hoàn tất khởi động.",
    "Chào Ngài, tôi đã sẵn sàng phục vụ mọi yêu cầu.",
]
```

```python
    def get_welcome_phrase(self, explicit_phrase: Optional[str] = None) -> str:
        """
        Selects a welcome phrase. If a pool of phrases is configured or available,
        selects randomly without repeating the immediately previous phrase.
        """
        import random

        if explicit_phrase and explicit_phrase.strip():
            return explicit_phrase.strip()

        welcome_cfg = self.config.get("welcome")
        if not isinstance(welcome_cfg, dict) and "tts" in self.config:
            welcome_cfg = self.config.get("tts", {}).get("welcome", {})
        if not isinstance(welcome_cfg, dict):
            welcome_cfg = {}

        # 1. Prioritize phrases list if configured with 1+ items
        phrases = welcome_cfg.get("phrases")
        if isinstance(phrases, list) and len(phrases) > 0:
            candidate_pool = [str(p).strip() for p in phrases if str(p).strip()]
        else:
            # 2. Check if a single phrase string is configured
            single = welcome_cfg.get("phrase")
            if single and isinstance(single, str) and single.strip():
                candidate_pool = [single.strip()]
            else:
                # 3. Fallback to default pool
                candidate_pool = list(WELCOME_PHRASES)

        with self._lock:
            if len(candidate_pool) > 1:
                available = [p for p in candidate_pool if p != self._last_welcome_phrase]
                if not available:
                    available = candidate_pool
            else:
                available = candidate_pool

            chosen = random.choice(available)
            self._last_welcome_phrase = chosen
            return chosen

    def speak_welcome(self, delay_s: float = 1.0, phrase: Optional[str] = None) -> None:
        """Plays a randomized Tony Stark-style welcome phrase in a detached daemon thread."""
        welcome_phrase = self.get_welcome_phrase(explicit_phrase=phrase)

        def _runner():
            if delay_s > 0:
                time.sleep(delay_s)
            self.speak(welcome_phrase, wait=False)

        threading.Thread(target=_runner, daemon=True, name="WelcomeTTS").start()
```

---

### 4.3 Blueprint 3: `jarvis/core/logger.py` Additions

```python
_INTERACTION_LOCK = threading.Lock()


def log_interaction(
    trigger: str,
    input_text: str,
    action: str,
    response: str,
    status: str = "success",
    log_file: Optional[Union[str, Path]] = None,
) -> str:
    """
    Structured interaction logger for R6 & M3 compliance.
    Format:
    [INTERACTION] <timestamp> | TRIGGER: <trigger_type> | INPUT: <transcript/input> | ACTION: <action_name> | RESPONSE: <response_text> | STATUS: <success/failed>
    """
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_trigger = str(trigger or "UNKNOWN").strip()
    clean_input = " ".join(str(input_text or "").split())
    clean_action = str(action or "none").strip()
    clean_response = " ".join(str(response or "").split())
    clean_status = "success" if str(status).lower() in ("success", "ok", "true", "1") else "failed"

    entry = (
        f"[INTERACTION] {timestamp} | TRIGGER: {clean_trigger} | "
        f"INPUT: {clean_input} | ACTION: {clean_action} | "
        f"RESPONSE: {clean_response} | STATUS: {clean_status}"
    )

    # 1. Output to standard logger
    interaction_logger = logging.getLogger("jarvis.interaction")
    interaction_logger.info(entry)

    # 2. Append directly to log file
    target_path = Path(log_file) if log_file else Path(__file__).resolve().parent.parent.parent / "logs" / "jarvis.log"
    with _INTERACTION_LOCK:
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception as e:
            interaction_logger.warning("Failed to write to interaction log file %s: %s", target_path, e)

    return entry
```

---

### 4.4 Blueprint 4: `config/default_config.yaml` Alignment

Update lines 78–86 in `config/default_config.yaml` to ensure `welcome.phrases` and `startup_phrase` are clearly defined:

```yaml
tts:
  provider: "elevenlabs"      # "elevenlabs" or "sapi5"
  elevenlabs:
    api_key: ""               # Loaded from .env ELEVENLABS_API_KEY
    voice_id: ""              # Loaded from .env ELEVENLABS_VOICE_ID
    model_id: "eleven_multilingual_v2"
    output_format: "pcm_24000"
    sample_rate: 24000
  cache:
    enabled: true
    dir: ".cache/jarvis_welcome"
  welcome:
    enabled: true
    startup_phrase: "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."
    phrase: "Welcome home sir. Tất cả các kết nối và cảm biến đã hoàn tất khởi động."
    phrases:
      - "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."
      - "Chào mừng Ngài trở lại. Mọi hệ thống đang hoạt động tối ưu."
      - "Xin chào sếp, JARVIS đã sẵn sàng phục vụ."
      - "Welcome home sir. Tất cả các kết nối và cảm biến đã hoàn tất khởi động."
      - "Chào Ngài, tôi đã sẵn sàng phục vụ mọi yêu cầu."
    delay_after_song_s: 1.0
  fallback:
    engine: "sapi5"
    voice_name: "Microsoft David Desktop"
    rate: 190
    volume: 1.0
```

---

## 5. Verification Method

To independently verify the implementation after the worker completes the code changes:

### 5.1 Unit Tests for Startup Intro & Randomized Welcome Pool
```python
def test_tts_randomized_welcome_pool_non_repeating():
    """Verify TTSManager selects from pool without repeating immediate previous phrase."""
    config = {
        "welcome": {
            "phrases": ["Phrase A", "Phrase B", "Phrase C"]
        }
    }
    mgr = TTSManager(config=config)
    selected = []
    for _ in range(30):
        p = mgr.get_welcome_phrase()
        selected.append(p)
        assert p in ["Phrase A", "Phrase B", "Phrase C"]

    # Verify no two consecutive phrases are identical
    for i in range(len(selected) - 1):
        assert selected[i] != selected[i+1]

def test_startup_vocal_introduction(monkeypatch):
    """Verify JarvisApp.start() vocalizes the exact startup intro phrase."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    spoken = []
    app.initialize()
    if app.tts_manager:
        monkeypatch.setattr(app.tts_manager, "speak", lambda txt, wait=False: spoken.append((txt, wait)) or True)
    app.start()
    assert len(spoken) >= 1
    assert spoken[0][0] == "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."
    assert spoken[0][1] is False  # Non-blocking wait=False
    app.stop()
```

### 5.2 Unit Tests for Structured Interaction Logging
```python
def test_structured_interaction_logging(tmp_path):
    """Verify [INTERACTION] format in log file for voice, text, and gestures."""
    log_file = tmp_path / "jarvis.log"
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.config.set("logging.file", str(log_file))
    app.initialize()

    # 1. Text command
    app.process_text_command("nhiệt độ hệ thống", requester="user")

    # 2. Gesture trigger
    app._on_gesture_event("triple_clap")

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if "[INTERACTION]" in line]
    assert len(lines) >= 2

    # Verify schema regex / layout
    for line in lines:
        assert line.startswith("[INTERACTION]")
        assert " | TRIGGER: " in line
        assert " | INPUT: " in line
        assert " | ACTION: " in line
        assert " | RESPONSE: " in line
        assert " | STATUS: " in line
    app.stop()
```

### 5.3 Automated Full Regression Command
```bash
cd "d:/Software GitCode/JARVIS"
python -m pytest tests/ -q
```
All existing tests ($\ge 518$) plus newly added unit and simulation tests must pass with 100% green status.
