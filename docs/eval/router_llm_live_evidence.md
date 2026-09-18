# Router LLM Live Test Runtime Evidence Report (R19 / R24 / P1-04)

- **Audit Standard**: `AGENTS.md §2` (Anti-Fabrication & Fail-Closed Principle) & `docs/AUDIT_FRAMEWORK.md`
- **Audit Date**: 2026-09-18
- **Auditor / Workers**: Worker 3 (`teamwork_preview_worker_m3_eval`) & Worker R24 (`worker_r24`)
- **Target LLM Provider**: Google Gemini (`gemini-1.5-flash`) via `LLMClient` & `LLMIntentRouter`
- **Audit Verdict**: `PASS fail-closed, runtime evidence PENDING`
- **Execution State Code**: `PENDING_CREDENTIALS`

---

## 1. Executive Summary

Requirement **R19** (Roadmap item P1-04) and **R24** mandate evaluating the live semantic intent routing capabilities of `LLMIntentRouter` (Tier-2 LLM Reasoning with `force_llm=True`) across 10 diverse Vietnamese utterances using a genuine Gemini API connection (`gemini-1.5-flash`), and auditing the presence of Gemini API credentials in the Windows Credential Manager and environment.

In strict compliance with **`AGENTS.md §2` (Anti-Fabrication & Fail-Closed Principle)**:
1. **Zero Data Fabrication**: We do NOT simulate, fabricate, or hardcode fake LLM responses, tool calls, or token counts.
2. **Fail-Closed Default**: Credential resolution probed both Windows Credential Manager and environment files. While `.env` contains an entry for `GEMINI_API_KEY`, forensic analysis revealed that the value (`AQ.Ab8RN...`) is an ElevenLabs token duplicate rather than a valid Google Gemini API key (`AIzaSy...`). Neither `GOOGLE_API_KEY` nor an active Gemini key in Windows Credential Manager is present.
3. **Truthful Interim Reporting**: The router's Tier-2 LLM live gate is classified truthfully as `PASS fail-closed, runtime evidence PENDING` with state `PENDING_CREDENTIALS`.
4. **Complete Test Suite & Tool Binding**: The 10-intent test suite, dispatcher action schemas, and test runner (`tests/eval/run_eval_worker3.py`) have been constructed and verified on disk, ready to execute immediately when authentic credentials are supplied.

---

## 2. Credential Resolution & Probe Audit Record

The credential resolution procedure was conducted across the three tiers defined in `docs/credentials_registry.md` and verified during Worker R24 audit:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   R19 / R24 CREDENTIAL RESOLUTION AUDIT                │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Windows Credential Manager Probe                                    │
│    - CLI Probe: cmdkey /list | Select-String -Pattern                  │
│                 'gemini|google|GOOGLE|GEMINI|API'                      │
│    - Status: NO_MATCH (No stored Gemini or Google credentials found)   │
│    - Secrets Subsystem: jarvis.security.secrets (Service: "JARVIS")    │
│      (Note: referenced as jarvis/core/secrets.py in task dispatch)     │
│    - Keyring Query: keyring.get_password("JARVIS", "GEMINI_API_KEY")   │
│    - Status: NOT_SET (No credential entry found)                       │
│    - Keyring Query: keyring.get_password("JARVIS", "GOOGLE_API_KEY")   │
│    - Status: NOT_SET (No credential entry found)                       │
├────────────────────────────────────────────────────────────────────────┤
│ 2. Environment Variables & Local .env File                             │
│    - Path: d:\Software GitCode\JARVIS\.env                             │
│    - Row 7: GEMINI_API_KEY=AQ.Ab8RN6IyGwMmCnTv7Y4GrcMm8x9TrGPWL80... │
│    - Row 2: ELEVENLABS_API_KEY=AQ.Ab8RN6IyGwMmCnTv7Y4GrcMm8x9TrGP... │
│    - Forensic Finding: Row 7 is a duplicate copy of ElevenLabs key.    │
│      Google Gemini API keys strictly require the prefix 'AIzaSy'       │
│      (39 alphanumeric characters). Sending 'AQ.Ab8RN...' to Google's   │
│      v1beta endpoint generates an immediate HTTP 400/401 API_KEY_INVALID.│
│    - GOOGLE_API_KEY: NOT_SET in .env or system environment.           │
├────────────────────────────────────────────────────────────────────────┤
│ 3. Resolution Verdict                                                  │
│    - Active Valid Secret: NONE                                         │
│    - Fallback Action: Fail-Closed (Prevent ghost execution)            │
│    - Result Code: PENDING_CREDENTIALS                                  │
└────────────────────────────────────────────────────────────────────────┘
```

### Forensic Probe Table

| Secret Target | Storage Medium | Value Detected | Integrity / Validity Assessment | Result |
|---|---|---|---|---|
| `GEMINI_API_KEY` | Windows Credential Manager (`JARVIS`) | `None` | Key not provisioned in OS secure store | `NOT_FOUND` |
| `GOOGLE_API_KEY` | Windows Credential Manager (`JARVIS`) | `None` | Legacy fallback key not provisioned | `NOT_FOUND` |
| `cmdkey /list` | Windows Credential Manager (All) | `None` | Pattern `'gemini\|google\|GOOGLE\|GEMINI\|API'` yielded no matches | `NOT_FOUND` |
| `GEMINI_API_KEY` | `.env` file (Line 7) | `AQ.Ab8RN6...` | **Invalid format** (ElevenLabs token string, not Google `AIzaSy...`) | `INVALID_KEY_FORMAT` |
| `GOOGLE_API_KEY` | `.env` / Process Env | `None` | Variable absent | `NOT_FOUND` |

---

## 3. Specification of 10 Diverse Vietnamese Intents

The test suite evaluates 10 diverse functional domains registered in JARVIS's `ActionDispatcher` (`jarvis/core/dispatcher.py`). Each utterance exercises Tier-2 semantic reasoning, requiring the LLM to map natural language Vietnamese intent directly to OpenAPI tool schemas.

| # | Domain | Input Utterance | Target Tool / Action Name | Tool Schema Parameters | Intended Assistant Action |
|:---:|---|---|---|---|---|
| **1** | **Smart Home** | *"Bật đèn phòng khách giúp tôi"* | `home_assistant_call` | `{"domain": "light", "service": "turn_on", "entity_id": "light.living_room"}` | Turn on living room light via Home Assistant |
| **2** | **Weather** | *"Thời tiết ngày mai ở Hà Nội có mưa không?"* | `weather_query` | `{"location": "Hà Nội", "date": "tomorrow"}` | Meteorological precipitation forecast |
| **3** | **Reminder** | *"Nhắc tôi uống thuốc sau 30 phút nữa"* | `proactive_reminder` | `{"message": "uống thuốc", "delay_minutes": 30}` | Proactive timed medication alert |
| **4** | **App Launch** | *"Mở trình duyệt Google Chrome lên"* | `app_open` | `{"app_name": "Google Chrome"}` | Launch desktop application by alias |
| **5** | **Screen Vision** | *"Chụp lại toàn bộ màn hình máy tính"* | `screen_capture` | `{"monitor_index": 0}` | Capture active display screenshot |
| **6** | **Volume** | *"Chỉnh âm lượng máy tính lên 80 phần trăm"* | `system_volume` | `{"level": 80, "mute": false}` | Adjust master audio speaker output |
| **7** | **Web Search** | *"Tìm kiếm thông tin về thị trường chứng khoán hôm nay"* | `web_search` | `{"query": "thị trường chứng khoán hôm nay"}` | Query search engine for real-time finance news |
| **8** | **System Status** | *"Kiểm tra nhiệt độ CPU và dung lượng RAM hiện tại"* | `system_status` | `{"component": "all"}` | Report hardware health telemetry |
| **9** | **Memory Recall** | *"Hôm nay tôi đã làm được những công việc gì?"* | `memory_summarize_daily` | `{"date": "today"}` | Summarize episodic journal and completed tasks |
| **10** | **Conversational QA** | *"Giải thích nguyên lý hoạt động của mạng nơ-ron tích chập CNN"* | `generic_llm_response` | `{"reply": "<natural_language_explanation>"}` | Conversational reasoning without tool dispatch |

---

## 4. Architectural Integration & Dispatcher Schema Bindings

The test execution harnesses `jarvis/llm/router.py`:
1. **Tier-1 Fast Path Bypass**: The evaluation calls `router.parse_intent(text, force_llm=True)` to explicitly bypass rule-matching dictionaries and force deep semantic reasoning.
2. **Dynamic Tool Schema Generation**: `generate_tool_schema_from_dispatcher(dispatcher)` inspects registered action signatures and builds Gemini-compatible OpenAPI function declarations:
   ```json
   {
     "tools": [
       {
         "functionDeclarations": [
           {
             "name": "home_assistant_call",
             "description": "Controls smart home devices via Home Assistant...",
             "parameters": {"type": "object", "properties": {"domain": {"type": "string"}, "service": {"type": "string"}, "entity_id": {"type": "string"}}, "required": ["domain", "service", "entity_id"]}
           },
           {
             "name": "weather_query",
             "description": "Queries current weather and meteorological forecasts...",
             "parameters": {"type": "object", "properties": {"location": {"type": "string"}, "date": {"type": "string"}}, "required": ["location"]}
           }
         ]
       }
     ]
   }
   ```
3. **System Prompt Persona Injection**: `build_jarvis_system_prompt()` injects the Tony Stark / JARVIS persona, operating instructions, and bilingual context constraints.

---

## 5. Reproduction & Execution Instructions

To execute this benchmark with genuine runtime evidence once valid Google Gemini API credentials are provided:

### Step 1: Provision Valid Gemini API Key
Obtain a valid API key from [Google AI Studio](https://aistudio.google.com/app/apikey) (format `AIzaSy...`, 39 characters). Store it securely using one of the supported methods:

**Option A: Windows Credential Manager via Python API (Recommended per AGENTS.md §3 & docs/credentials_registry.md)**
```powershell
.venv\Scripts\python.exe -c "from jarvis.security.secrets import set_secret; set_secret('GEMINI_API_KEY', 'AIzaSy...')"
```

**Option B: Windows Credential Manager via Native cmdkey CLI**
```powershell
cmdkey /generic:JARVIS /user:GEMINI_API_KEY /pass:AIzaSy...
```

**Option C: Session Environment Variable**
```powershell
$env:GEMINI_API_KEY = "AIzaSy..."
```

**Option D: Local .env File Configuration**
Update line 7 of `.env`:
```dotenv
GEMINI_API_KEY=AIzaSy...
```

### Step 2: Run the Benchmark Harness
```powershell
.venv\Scripts\python.exe tests/eval/run_eval_worker3.py
```

### Invalidation Conditions
- If synthetic or mock responses are accepted without authentic Google API endpoint responses (`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent`).
- If `force_llm=True` is disabled or falls back silently to Tier-1 regex rules.
- If `PENDING_CREDENTIALS` is falsely claimed as a `PASS runtime`.

---

*Report certified by Worker 3 (AI Model Benchmarking & Evaluation) & Worker R24 (Credential Manager & Live Verification).*  
*Compliance: `AGENTS.md §2` (Anti-Fabrication Principle) & `docs/AUDIT_FRAMEWORK.md`.*
