# Blueprint: Natural Conversational Vietnamese Response Generation for JARVIS

**Agent**: Explorer M2_2  
**Milestone**: M2 — Smart Keyword Router Fallback in Vietnamese  
**Target Subsystems**: `jarvis/llm/router.py`, `jarvis/core/app.py`, `jarvis/ui/overlay.py`, `jarvis/tts/`  
**Working Directory**: `d:/Software GitCode/JARVIS/.agents/explorer_m2_2`  
**Date**: 2026-08-22  

---

## 1. Executive Summary & Objective

This blueprint specifies the exact design, data structures, routing tables, and implementation details for **Natural Conversational Vietnamese Response Generation** across `jarvis/llm/router.py` and `jarvis/core/app.py`.

### Key Deliverables:
1. **`IntentResult.response_text` Integration**: Refactor `IntentResult` to include `response_text: Optional[str] = None` containing natural, polite conversational Vietnamese (e.g., *"Đang bật đèn phòng khách cho Ngài."*, *"Đang mở Spotify."*, *"Nhiệt độ CPU hiện tại là..."*, *"Đang kiểm tra thời tiết..."*, *"Đã ghi nhận lời nhắc của Ngài."*).
2. **Exact Fallback Guarantee**: Ensure the fallback phrase for unrecognized commands across all tiers is strictly:
   ```text
   "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"
   ```
3. **Multi-Modal Output Compatibility**: Validate that all generated responses are 100% compliant with both:
   - **TTS Vocalization**: High phoneme clarity, natural cadence, no unpronounceable code identifiers/symbols in both ElevenLabs Neural and Windows SAPI5 offline fallback.
   - **UI Overlay Display**: Clean text formatting fitting within the 420×280 Iron Man HUD overlay without clipping or text overflow.

---

## 2. Architecture & Data Flow Analysis

### 2.1 Current State & Identified Gaps

1. **Missing `response_text` on `IntentResult` (`jarvis/llm/router.py:27-45`)**:
   Currently, `IntentResult` only contains `action_name`, `parameters`, `confidence`, `source`, `reasoning`, `raw_text`, and `llm_response`. It lacks a dedicated `response_text` field. As a result, the router passes intent to `app.py` without semantic conversational feedback.

2. **Robotic String Formatting in `JarvisApp.process_text_command` (`jarvis/core/app.py:546`)**:
   When an action succeeds, `app.py` formats responses robotically:
   ```python
   # CURRENT ROBOTIC IMPLEMENTATION:
   response_text = f"Đã thực hiện lệnh: {intent_result.action_name}"
   ```
   For example, it outputs `"Đã thực hiện lệnh: home_assistant_call"` or `"Đã thực hiện lệnh: spotify"`. This violates Requirement R3 for natural conversational responses.

3. **Inconsistent Fallback Phrase (`jarvis/core/app.py:551`)**:
   Currently, `app.py` outputs:
   ```python
   # CURRENT INCONSISTENT FALLBACK:
   response_text = f"Tôi chưa hiểu lệnh '{clean_text}'. Vui lòng thử lại."
   ```
   Requirement R3 strictly mandates:
   `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"`

4. **Missing Rich Action Spoken Output Extraction**:
   Certain actions (like `hardware_status_query` / `system_status` via `HardwareReporter`) produce rich, live telemetry sentences (e.g., *"Tình trạng hệ thống: CPU đang sử dụng 15 phần trăm. Nhiệt độ CPU là 45 độ C. RAM đang sử dụng 38 phần trăm."*). The command processing pipeline must dynamically adopt this live telemetry text when available.

---

## 3. Data Model Refactoring: `IntentResult`

In `jarvis/llm/router.py`, `IntentResult` is updated with `response_text: Optional[str] = None` and exported in `to_dict()`:

```python
@dataclass
class IntentResult:
    action_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "llm"  # "llm", "rule_fallback", "rule_fast_path"
    reasoning: Optional[str] = None
    raw_text: str = ""
    llm_response: Optional[LLMResponse] = None
    response_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_name": self.action_name,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "source": self.source,
            "reasoning": self.reasoning,
            "raw_text": self.raw_text,
            "response_text": self.response_text,
        }
```

---

## 4. Vietnamese Smart Keyword Routing & Response Matrix (R3)

The following comprehensive routing table defines keyword patterns, extracted parameters, mapped action names, and corresponding polite Vietnamese responses:

| # | Category | Keyword Triggers (Clean Lower) | Action Name | Parameters | Conversational Vietnamese Response (`response_text`) |
|---|---|---|---|---|---|
| **1** | **Smart Home (Lights On)** | `"bật đèn"`, `"mở đèn"`, `"bật đèn phòng khách"`, `"bật điện"`, `"turn on light"` | `home_assistant_call` | `{"domain": "light", "service": "turn_on", "entity_id": "light.living_room"}` | `"Đang bật đèn phòng khách cho Ngài."` |
| **2** | **Smart Home (Lights Off)** | `"tắt đèn"`, `"tắt đèn phòng khách"`, `"tắt điện"`, `"turn off light"` | `home_assistant_call` | `{"domain": "light", "service": "turn_off", "entity_id": "light.living_room"}` | `"Đang tắt đèn phòng khách cho Ngài."` |
| **3** | **Smart Home (Desk Lamp)** | `"bật đèn bàn"`, `"đèn làm việc"`, `"đèn desk"` | `home_assistant_call` | `{"domain": "light", "service": "turn_on", "entity_id": "light.desk_lamp"}` | `"Đang bật đèn bàn làm việc cho Ngài."` |
| **4** | **Hardware (CPU)** | `"nhiệt độ cpu"`, `"kiểm tra nhiệt độ cpu"`, `"cpu nóng không"`, `"cpu"`, `"nhiệt độ máy"` | `hardware_telemetry_check` | `{"component": "cpu"}` | `"Đang kiểm tra nhiệt độ CPU của hệ thống."` |
| **5** | **Hardware (RAM)** | `"ram"`, `"bộ nhớ"`, `"bộ nhớ ram"`, `"kiểm tra ram"`, `"dung lượng ram"` | `hardware_telemetry_check` | `{"component": "ram"}` | `"Đang kiểm tra dung lượng RAM của hệ thống."` |
| **6** | **Hardware (GPU)** | `"gpu"`, `"nhiệt độ gpu"`, `"card màn hình"`, `"card đồ họa"` | `hardware_telemetry_check` | `{"component": "gpu"}` | `"Đang kiểm tra trạng thái GPU của hệ thống."` |
| **7** | **Hardware (Overall)** | `"tình trạng hệ thống"`, `"trạng thái máy tính"`, `"kiểm tra hệ thống"`, `"hệ thống"` | `hardware_status_query` | `{}` | `"Đang kiểm tra tình trạng tổng thể hệ thống cho Ngài."` |
| **8** | **Music / Spotify** | `"mở spotify"`, `"bật spotify"`, `"bật nhạc"`, `"mở nhạc"`, `"phát nhạc"`, `"nhạc"`, `"nghe nhạc"`, `"spotify"` | `spotify` | `{}` | `"Đang mở Spotify và phát nhạc cho Ngài."` |
| **9** | **Weather** | `"thời tiết"`, `"dự báo thời tiết"`, `"thời tiết hôm nay"`, `"nhiệt độ ngoài trời"`, `"weather"` | `weather` | `{"location": "default"}` | `"Đang kiểm tra thời tiết hôm nay cho Ngài."` |
| **10** | **Reminder** | `"nhắc nhở"`, `"reminder"`, `"nhắc tôi"`, `"đặt lịch"`, `"tạo nhắc nhở"` | `reminder` | `{"content": "<raw_text>"}` | `"Đã ghi nhận lời nhắc của Ngài."` |
| **11** | **System Power (Shutdown)** | `"tắt máy"`, `"shutdown"`, `"tắt máy tính"`, `"tắt nguồn"` | `system_power` | `{"action": "shutdown"}` | `"Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi."` |
| **12** | **System Power (Restart)** | `"restart"`, `"khởi động lại"`, `"reboot"` | `system_power` | `{"action": "restart"}` | `"Lệnh khởi động lại máy đã được ghi nhận. Vui lòng xác nhận để thực thi."` |
| **13** | **Workspace Prep** | `"chuẩn bị môi trường làm việc"`, `"mở không gian làm việc"`, `"prepare workspace"` | `workspace_prepare` | `{"recipe": "ai_development"}` | `"Đang chuẩn bị môi trường làm việc cho Ngài."` |
| **14** | **Self Healing** | `"tự phục hồi hệ thống"`, `"dọn dẹp ram"`, `"giải phóng bộ nhớ"` | `healing_watchdog_heal` | `{}` | `"Đang tiến hành tối ưu hóa bộ nhớ và kiểm tra tiến trình hệ thống."` |
| **15** | **Security Scan** | `"quét mạng nội bộ"`, `"quét mạng"`, `"security scan"` | `security_nmap_scan` | `{"target": "192.168.1.0/24"}` | `"Đang thực hiện quét an ninh mạng nội bộ cho Ngài."` |
| **16** | **Default Fallback** | *(Any unrecognized query)* | `unknown_intent` | `{"raw_text": "<raw_text>"}` | `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"` |

---

## 5. Multi-Tier Resolution Pipeline in `LLMIntentRouter`

```
 User Input Query
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ TIER 1: Fast-Path Rule Engine & Parametric Regex Matching   │
│ - Exact & Substring match against Vietnamese rule dictionary │
│ - Parametric regex with capture groups                      │
│ - Response time: < 0.5 ms                                   │
│ - Returns: IntentResult with populated response_text        │
└──────────────────────────────┬──────────────────────────────┘
                               │ (If no Tier 1 match or force_llm)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ TIER 2: LLM Semantic Reasoning & Tool Calling               │
│ - Multi-provider (OpenAI / Gemini / Claude / Ollama)        │
│ - Tool call -> IntentResult(action, params, response_text)   │
│ - Conversational -> generic_llm_response(reply)             │
└──────────────────────────────┬──────────────────────────────┘
                               │ (On LLM Exception / Missing Key / 429)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ TIER 3: Deterministic Rule Fallback                         │
│ - Evaluates rule dictionary & regex                         │
│ - If matched -> IntentResult(action, response_text)         │
│ - If unmatched -> unknown_intent + Exact Fallback:          │
│   "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"          │
└─────────────────────────────────────────────────────────────┘
```

### 5.1 Helper Method: `LLMIntentRouter.get_natural_response()`

A dedicated helper generates polite Vietnamese responses dynamically based on action name, parameters, and execution results:

```python
def get_natural_response(
    self,
    action_name: str,
    parameters: Optional[Dict[str, Any]] = None,
    action_result: Optional[ActionResult] = None,
) -> str:
    """Generates natural conversational Vietnamese text for any action result."""
    params = parameters or {}
    
    # 1. If action result contains an explicit human-like spoken message (e.g. Hardware telemetry)
    if action_result and action_result.data and isinstance(action_result.data, dict):
        if "message" in action_result.data and action_result.data["message"]:
            return str(action_result.data["message"])

    # 2. Action-specific mapping
    if action_name == "generic_llm_response":
        return params.get("reply", "")

    if action_name == "home_assistant_call":
        svc = params.get("service", "")
        entity = params.get("entity_id", "")
        target = "phòng khách" if "living_room" in entity else ("bàn làm việc" if "desk" in entity else "")
        target_str = f" {target}" if target else ""
        if svc in ("turn_on", "toggle"):
            return f"Đang bật đèn{target_str} cho Ngài."
        elif svc == "turn_off":
            return f"Đang tắt đèn{target_str} cho Ngài."
        return "Đã thực hiện điều khiển thiết bị thông minh cho Ngài."

    if action_name in ("spotify", "spotify_play", "play_song"):
        return "Đang mở Spotify và phát nhạc cho Ngài."

    if action_name == "hardware_telemetry_check":
        comp = params.get("component", "cpu").upper()
        return f"Đang kiểm tra thông số {comp} của hệ thống."

    if action_name in ("hardware_status_query", "system_status"):
        return "Đang kiểm tra tình trạng tổng thể hệ thống cho Ngài."

    if action_name in ("weather", "weather_query"):
        return "Đang kiểm tra thời tiết hôm nay cho Ngài."

    if action_name in ("reminder", "reminder_create"):
        return "Đã ghi nhận lời nhắc của Ngài."

    if action_name == "system_power":
        act = params.get("action", "shutdown")
        act_vn = "khởi động lại" if "restart" in act else "tắt máy"
        return f"Lệnh {act_vn} đã được ghi nhận. Vui lòng xác nhận để thực thi."

    if action_name == "workspace_prepare":
        return "Đang chuẩn bị môi trường làm việc cho Ngài."

    if action_name == "healing_watchdog_heal":
        return "Đang tiến hành tối ưu hóa bộ nhớ và kiểm tra tiến trình hệ thống."

    if action_name == "security_nmap_scan":
        return "Đang thực hiện quét an ninh mạng nội bộ cho Ngài."

    if action_name == "unknown_intent":
        return "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"

    # Default clean fallback
    return f"Đã thực hiện lệnh {action_name} cho Ngài."
```

---

## 6. Detailed Implementation Blueprint for Workers

### 6.1 Target File: `jarvis/llm/router.py`

#### Changes:
1. **Line 27**: Add `response_text: Optional[str] = None` to `IntentResult` dataclass.
2. **Line 36**: Update `to_dict()` to include `"response_text": self.response_text`.
3. **Lines 188–234 (`self.rule_engine`)**:
   Populate all entries with Vietnamese `response_text` and add the new R3 categories (`weather`, `reminder`, `system_power`).
4. **Lines 237–262 (`self._regex_rules`)**:
   Add comprehensive regex rules for:
   - Lighting variations: `(?:bật|mở|tắt)\s+(?:đèn|điện|light)`
   - Hardware telemetry variations: `(?:kiểm tra\s+)?(?:nhiệt độ|cpu|gpu|ram|bộ nhớ|ổ cứng|hệ thống)`
   - Spotify variations: `(?:mở|bật|phát|nghe)\s*(?:spotify|nhạc|bài hát)`
   - Weather variations: `(?:thời tiết|dự báo thời tiết|weather)`
   - Reminder variations: `(?:nhắc nhở|nhắc tôi|reminder|đặt lịch)`
   - Power variations: `(?:tắt máy|khởi động lại|restart|shutdown|reboot)`
5. **Tier 2 (LLM Generation)**:
   When `LLMResponse` contains `tool_calls`, populate `response_text = self.get_natural_response(top_tool.name, top_tool.arguments)`.
6. **Tier 3 (Error Fallback)**:
   When unrecognized, return:
   ```python
   return IntentResult(
       action_name="unknown_intent",
       parameters={"raw_text": text, "error": str(exc)},
       confidence=0.0,
       source="rule_fallback",
       raw_text=text,
       response_text="Tôi chưa hiểu lệnh này, vui lòng thử cách khác",
   )
   ```
7. **Add `get_natural_response()` method** to `LLMIntentRouter`.

---

### 6.2 Target File: `jarvis/core/app.py`

#### Changes:
1. **In `process_text_command(self, text: str, requester: str = "user")`**:
   - Refactor response text selection logic:
     ```python
     response_text = ""
     action_result = None

     if intent_result and intent_result.action_name != "unknown_intent":
         try:
             action_result = self.dispatcher.dispatch_action(
                 action_name=intent_result.action_name,
                 payload=intent_result.parameters,
                 requester=RequesterContext.user(requester_id=requester, authenticated=True),
             )

             if intent_result.action_name == "generic_llm_response":
                 response_text = intent_result.parameters.get("reply", "")
             elif (
                 action_result
                 and action_result.data
                 and isinstance(action_result.data, dict)
                 and "message" in action_result.data
                 and action_result.data["message"]
             ):
                 # Use rich live telemetry message (e.g. system_status / HardwareReporter)
                 response_text = action_result.data["message"]
             elif intent_result.response_text:
                 response_text = intent_result.response_text
             elif self.llm_router:
                 response_text = self.llm_router.get_natural_response(
                     intent_result.action_name, intent_result.parameters, action_result
                 )
             else:
                 response_text = f"Đã thực hiện xong lệnh cho Ngài."
         except Exception as e:
             log.error("Action execution failed: %s", e)
             response_text = f"Xin lỗi Ngài, đã xảy ra lỗi khi thực thi lệnh: {e}"
     else:
         if intent_result and intent_result.response_text:
             response_text = intent_result.response_text
         else:
             response_text = "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"
     ```
   - Ensure `self.tts_manager.speak(response_text, wait=False)` vocalizes the single unified response.
   - Broadcast `response_text` to Dashboard Server.

2. **In `_ai_voice_loop()`**:
   - Verify that when STT returns empty/silence, it uses:
     `"Tôi không nghe thấy gì cả. Vui lòng thử lại."`
   - During processing:
     - `self.overlay.show_thinking(transcript)`
     - Executes `process_text_command(transcript, requester="voice")`
     - Displays `self.overlay.show_response(transcript, response_text)`
   - No double vocalization.

3. **In `_on_gesture_event()`**:
   - `clap_pause_clap` pattern dispatches `show_overlay` instead of `toggle_mute`.
   - Cooldown guard logs `"Gesture [%s] suppressed — cooldown %.1fs remaining."` at `INFO` level.

---

## 7. Multi-Modal Output Compatibility Specifications

### 7.1 TTS Vocalization Compatibility
- **Pronunciation & Diacritics**: All phrases use correct Vietnamese standard UTF-8 diacritics (NFC normalization).
- **Tone & Persona**: Polite, deferential tone (*"thưa Ngài"*, *"cho Ngài"*), matching Tony Stark's JARVIS.
- **Numbers & Units**:
  - `45°C` formatted as `"45 độ C"`.
  - `90%` formatted as `"90 phần trăm"`.
  - Avoid raw punctuation marks (like `_`, `->`, `{}`) that cause SAPI5 or ElevenLabs to pronounce symbols.

### 7.2 UI Overlay HUD Compatibility
- **Window Dimensions**: 420px width × 280px height, `wraplength=310`.
- **Character Budget**: Responses are 25–100 characters, well within the 200 character overlay limit (`response[:197] + "..."`).
- **Visual Typography**: Consolas font 9pt on `#0a0e1a` HUD background with `#c0f8ff` cyan text color.

---

## 8. Verification & Test Plan

A dedicated automated test file `tests/test_vietnamese_router_m2.py` must verify all acceptance criteria:

```python
"""
tests/test_vietnamese_router_m2.py
Test suite validating Vietnamese conversational response generation and fallback.
"""
import pytest
from jarvis.llm.client import LLMClient
from jarvis.llm.router import LLMIntentRouter, IntentResult
from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher

def test_intent_result_response_text_field():
    """Verify IntentResult dataclass has response_text field and to_dict includes it."""
    res = IntentResult(action_name="test_action", response_text="Đang xử lý cho Ngài.")
    assert res.response_text == "Đang xử lý cho Ngài."
    d = res.to_dict()
    assert d["response_text"] == "Đang xử lý cho Ngài."

@pytest.mark.parametrize("query,expected_action,expected_substr", [
    ("bật đèn phòng khách", "home_assistant_call", "Đang bật đèn phòng khách cho Ngài."),
    ("tắt đèn phòng khách", "home_assistant_call", "Đang tắt đèn phòng khách cho Ngài."),
    ("bật đèn", "home_assistant_call", "bật đèn"),
    ("kiểm tra nhiệt độ cpu", "hardware_telemetry_check", "nhiệt độ CPU"),
    ("nhiệt độ cpu", "hardware_telemetry_check", "nhiệt độ"),
    ("ram máy tính", "hardware_telemetry_check", "RAM"),
    ("tình trạng hệ thống", "hardware_status_query", "tình trạng tổng thể hệ thống"),
    ("mở spotify", "spotify", "Đang mở Spotify"),
    ("bật nhạc", "spotify", "Spotify"),
    ("thời tiết hôm nay", "weather", "thời tiết"),
    ("nhắc nhở tôi lúc 8h", "reminder", "lời nhắc"),
    ("tắt máy", "system_power", "tắt máy"),
    ("khởi động lại máy", "system_power", "khởi động lại"),
])
def test_vietnamese_keyword_categories_response_text(query, expected_action, expected_substr):
    """Verify all R3 keyword categories return matched intent with polite Vietnamese response."""
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(llm_client=client)
    intent = router.parse_intent(query)
    assert intent.action_name == expected_action
    assert expected_substr.lower() in (intent.response_text or "").lower()

def test_vietnamese_fallback_exact_phrase():
    """Verify unknown queries fall back strictly to 'Tôi chưa hiểu lệnh này, vui lòng thử cách khác'."""
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(llm_client=client)
    intent = router.parse_intent("lệnh hoàn toàn lạ lẫm không thể hiểu nổi 12345")
    assert intent.action_name == "unknown_intent"
    assert intent.response_text == "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"

def test_app_process_text_command_e2e():
    """Verify JarvisApp.process_text_command returns conversational response text."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    
    # 1. Spotify command
    res_spotify = app.process_text_command("mở spotify phát nhạc")
    assert res_spotify["success"] is True
    assert "Spotify" in res_spotify["response_text"]
    
    # 2. Fallback command
    res_unknown = app.process_text_command("câu lệnh vô nghĩa xyz")
    assert res_unknown["response_text"] == "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"
    
    app.stop()
```

---
*End of Blueprint Report*
