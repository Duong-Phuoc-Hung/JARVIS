# Reviewer P0-2 Handoff Report

## 1. Observation

### A. Test Suite & Benchmark Executions
1. **Command**: `pytest tests/unit/test_wake_word_p0.py tests/unit/test_proactive_engine_p0.py tests/unit/test_router_p0.py -v`
   - **Result**: `174 passed, 2 warnings in 3.07s` (Exit Code 0).
   - **Details**:
     - `tests/unit/test_wake_word_p0.py`: 20/20 passed.
     - `tests/unit/test_proactive_engine_p0.py`: 14/14 passed.
     - `tests/unit/test_router_p0.py`: 140/140 passed.
2. **Command**: `pytest tests/e2e/test_v460_e2e.py -v`
   - **Result**: `57 passed, 2 warnings in 1.22s` (Exit Code 0).
3. **Command**: `python -X utf8 tests/eval/routing_eval_n150.py`
   - **Result**:
     ```
     ============================================================
     Text-Routing Eval — N=143 utterances
     ============================================================
       CORRECT           : 143/143 = 100.0%  Wilson 95% CI [97.4%–100.0%]
       SILENT_FAILURE    :   0/143 =   0.0%  Wilson 95% CI [0.0%–2.6%]
       MISROUTED         :   0/143 =   0.0%  Wilson 95% CI [0.0%–2.6%]
     ```
4. **Command**: `pytest tests/unit/test_llm_engine.py -v`
   - **Result**: `FAILED tests/unit/test_llm_engine.py::test_intent_router_tier1_parametric_regex` (Exit Code 1).
   - **Verbatim Error**:
     ```
     __________________ test_intent_router_tier1_parametric_regex __________________
     tests\unit\test_llm_engine.py:263: in test_intent_router_tier1_parametric_regex
         assert res_scan.action_name == "security_nmap_scan"
     E   AssertionError: assert 'generic_llm_response' == 'security_nmap_scan'
     E     
     E     - security_nmap_scan
     E     + generic_llm_response
     ```
5. **Command**: `python tests/eval/routing_eval_n150.py` (without utf-8 flag on Windows cp1252):
   - **Verbatim Error**:
     ```
     UnicodeEncodeError: 'charmap' codec can't encode character '\u0394' in position 4: character maps to <undefined>
     ```

### B. Subsystem Code Inspections
1. **P0-A Wake Word (`jarvis/audio/wake_word.py`)**:
   - Lines 34–62: Graceful conditional imports for `vosk`, `openwakeword`, `pvporcupine`, `faster_whisper`.
   - Lines 527–573: Model discovery hierarchy checking `vosk_model_path`, `JARVIS_VOSK_MODEL`, `VOSK_MODEL_PATH`, and local/user directories.
   - Lines 812–850: Streaming recognition handling `AcceptWaveform()`, `PartialResult()` instant matching, malformed JSON recovery, and `Reset()`.
   - Lines 270–409: `AcousticSpectralDetector` implementing multi-band STFT spectral energy ratios, ZCR, and SFM pure-tone (<0.03) and white-noise (>0.65) rejection.
   - Lines 638–663, 790–800: Thread-safe locking, live enable/disable toggle, and 1.5s refractory cooldown.
2. **P0-B ProactiveEngine (`jarvis/workers/proactive.py`, `jarvis/workers/__init__.py`, `jarvis/core/app.py`)**:
   - `jarvis/workers/__init__.py` lines 15–50: Cleanly imports and re-exports `ProactiveEngine`, `ProactiveConfig`, `ReminderScheduler`, `SystemHealthMonitor`, `PomodoroTimer`, etc.
   - `jarvis/workers/proactive.py` lines 41–76: Subclasses `BaseProactiveEngine`, integrates with `ActionDispatcher` and hooks `health_monitor._dispatch_alert` to publish `hardware.alert` on `EventBus`.
   - Lines 93–157: Registers actions `proactive_reminder`, `proactive_pomodoro_start`, `proactive_pomodoro_stop`.
   - `jarvis/core/app.py` lines 72, 144–145, 301–303, 671, 1896–1902: Wires `ProactiveEngine` into app lifecycle without crash.
3. **P0-C Tier-2 LLM Routing (`jarvis/llm/router.py`, `jarvis/llm/client.py`)**:
   - Lines 67–148: `generate_tool_schema_from_dispatcher()` dynamically inspects registered action definitions and builds OpenAI function schemas.
   - Lines 2225–2286: Logs Tier-1 miss (`logger.info("Tier-1 fast-path miss for query %r...")`), invokes `LLMClient.generate()`, extracts tool calls to structured `IntentResult`, and returns natural responses.
   - Lines 2287–2324: Tier-3 exception fallback catches network/auth/timeout errors, falling back safely to regex/static rules.
4. **P0-D Router Tier-1 Rules Expansion (`jarvis/llm/router.py`)**:
   - Lines 750–950, 1178–1400: Added 80+ fast-path regex rules and dictionary entries covering non-diacritic Vietnamese, English shortcuts, and system domains.
   - Lines 2141–2170: ReDoS protection clamping regex string length to 512 characters and fast-rejecting emoji-only/number-only inputs.
   - **Missing Pattern**: Lines 1178–1400 in `_regex_rules` lack a parametric regex pattern for `security_nmap_scan` (`r"^(?:jarvis[,\s]*)?(?:quét\s*mạng|scan\s*(?:network|subnet))(?:\s+(.+))?$"`), which is expected by existing unit test `tests/unit/test_llm_engine.py:262`.

---

## 2. Logic Chain

1. **Integrity & Implementation Logic**:
   - Observation B.1–B.4 reveals real, substantial implementations across all 4 P0 areas without dummy facades, mock bypasses in production code, or hardcoded test returns.
   - P0-A, P0-B, and P0-C fulfill all functional requirements and interface contracts defined in `PROJECT.md`.
2. **Acceptance Criteria & Test Pass Verification**:
   - Acceptance Criteria §R3 in `ORIGINAL_REQUEST.md` requires: `pytest tests/unit/ -q → 0 failures`.
   - While the new test suites (`test_wake_word_p0.py`, `test_proactive_engine_p0.py`, `test_router_p0.py`, `test_v460_e2e.py`) pass 100% (Observations A.1 & A.2), running the broader unit test suite revealed a failure in `tests/unit/test_llm_engine.py::test_intent_router_tier1_parametric_regex` (Observation A.4).
   - In `jarvis/llm/router.py`, `security_nmap_scan` is only defined as a static rule for `"quét mạng nội bộ"` (Observation B.4), so query `"scan network 10.0.0.0/24"` falls through to Tier 2 and fails when using a mock client with default behavior.
3. **Evaluation Script Portability**:
   - In `tests/eval/routing_eval_n150.py:305`, the literal `\u0394` causes `UnicodeEncodeError` on Windows consoles with default code pages (Observation A.5).

---

## 3. Caveats

- Hardware acoustic microphone testing was simulated using deterministic mathematical synthetic signals (`generate_wake_word_signal`) and mocked audio frames due to headless environment constraints.
- Optional heavy binary dependencies (`vosk`, `openwakeword`, `cv2`, `mediapipe`) were evaluated via fallback cascading and mock unit tests rather than local wheel installations.

---

## 4. Conclusion & Verdict

**Verdict**: `REQUEST_CHANGES`

### Required Changes:
1. **Fix missing `security_nmap_scan` parametric regex in `jarvis/llm/router.py`**:
   Add the following rule into `self._regex_rules` (around line 1400) in `jarvis/llm/router.py`:
   ```python
   (
       re.compile(
           r"^(?:jarvis[,\s]*)?(?:quét\s*mạng|quet\s*mang|scan\s*(?:network|subnet))(?:\s+(.+))?$",
           re.IGNORECASE,
       ),
       lambda m: IntentResult(
           action_name="security_nmap_scan",
           parameters={"target": m.group(1).strip() if (m.lastindex and m.group(1) and m.group(1).strip()) else "192.168.1.0/24"},
           source="rule_fallback",
           response_text="Đang thực hiện quét an ninh mạng cho Ngài.",
       ),
   ),
   ```
2. **Fix Unicode character in `tests/eval/routing_eval_n150.py:305`**:
   Replace `\u0394` with `Delta` or reconfigure stdout stream to UTF-8 to ensure clean out-of-the-box Windows console execution.

Once these two items are addressed, all unit test suites (`pytest tests/unit/ -q`), E2E suites (`pytest tests/e2e/test_v460_e2e.py -v`), and evaluation benchmarks will pass with 0 failures and 100% compliance.

---

## 5. Verification Method

To independently verify the fixes:
1. Run target unit suites:
   `pytest tests/unit/test_wake_word_p0.py tests/unit/test_proactive_engine_p0.py tests/unit/test_router_p0.py -v`
2. Run regression unit test:
   `pytest tests/unit/test_llm_engine.py -v`
3. Run full unit test suite:
   `pytest tests/unit/ -q`
4. Run E2E test suite:
   `pytest tests/e2e/test_v460_e2e.py -v`
5. Run routing benchmark:
   `python tests/eval/routing_eval_n150.py`
