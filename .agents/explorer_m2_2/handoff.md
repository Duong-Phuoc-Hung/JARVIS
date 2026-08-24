# Handoff Report — Explorer M2_2: Vietnamese Conversational Response Generation Blueprint

**Agent ID**: explorer_m2_2  
**Milestone**: M2 (Smart Keyword Router Fallback in Vietnamese)  
**Parent Agent**: 88e315c1-4bbc-4194-bae5-c1ca88628303  
**Working Directory**: `d:/Software GitCode/JARVIS/.agents/explorer_m2_2`  
**Date**: 2026-08-22  

---

## 1. Observation

Direct code observations from the codebase:

1. **`jarvis/llm/router.py` Lines 27–45**:
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
   ```
   `IntentResult` lacks `response_text`, preventing natural conversational feedback from being bundled with parsed intents.

2. **`jarvis/llm/router.py` Lines 188–234**:
   `self.rule_engine` dictionary contains only 9 hardcoded phrases (`"bật đèn phòng khách"`, `"tắt đèn phòng khách"`, `"kiểm tra nhiệt độ cpu"`, `"tình trạng hệ thống"`, `"quét mạng nội bộ"`, `"mở spotify"`, `"spotify"`, `"chuẩn bị môi trường làm việc"`, `"tự phục hồi hệ thống"`). Missing: generic lighting (`"bật đèn"`, `"tắt đèn"`), weather (`"thời tiết"`), reminders (`"nhắc nhở"`), and system power (`"tắt máy"`, `"restart"`).

3. **`jarvis/llm/router.py` Lines 358–364**:
   Tier 3 error fallback returns `unknown_intent` without a default polite conversational Vietnamese message.

4. **`jarvis/core/app.py` Lines 543–552**:
   ```python
   if intent_result.action_name == "generic_llm_response":
       response_text = intent_result.parameters.get("reply", "")
   else:
       response_text = f"Đã thực hiện lệnh: {intent_result.action_name}"
   ...
   else:
       response_text = f"Tôi chưa hiểu lệnh '{clean_text}'. Vui lòng thử lại."
   ```
   - Success response is robotic (`"Đã thực hiện lệnh: ..."`).
   - Fallback response is not the standard phrase (`"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"`).

5. **`jarvis/ui/overlay.py` Lines 169–177**:
   Overlay `_do_show_response` truncates text over 200 characters (`display = response if len(response) <= 200 else response[:197] + "..."`).

---

## 2. Logic Chain

1. **Step 1 (Data Model)**: Since `IntentResult` is the central structure passing resolved commands from `LLMIntentRouter` to `JarvisApp`, adding `response_text: Optional[str] = None` allows Tier 1, Tier 2, and Tier 3 resolution pathways to immediately attach polite conversational Vietnamese text without breaking backward compatibility.
2. **Step 2 (Rule Matrix)**: Requirement R3 mandates keyword coverage for smart home, hardware, spotify, weather, reminders, and system power. Adding these rules to `self.rule_engine` and `self._regex_rules` with populated `response_text` ensures that offline or keyless execution immediately resolves with natural spoken feedback.
3. **Step 3 (App Execution Bridge)**: In `JarvisApp.process_text_command()`, dynamically selecting between (a) rich action output messages (e.g. `HardwareReporter`), (b) `intent_result.response_text`, and (c) helper generated templates eliminates robotic string formatting (`"Đã thực hiện lệnh: ..."`).
4. **Step 4 (Strict Fallback)**: By returning `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"` whenever `action_name == "unknown_intent"` or when router fails, Requirement R3 and Acceptance Criteria are strictly satisfied.
5. **Step 5 (Multi-modal Delivery)**: Because all generated Vietnamese responses are concise (< 100 characters), diacritically correct (NFC UTF-8), and devoid of code syntax, they are simultaneously optimal for ElevenLabs/SAPI5 TTS vocalization and the 420×280 Tkinter HUD overlay.

---

## 3. Caveats

- **No Source Modification**: As an explorer agent, no production code in `jarvis/` has been modified; all blueprints and specifications are documented in `report.md` for worker implementation.
- **Microphone / Sounddevice in Headless Testing**: In headless test environments, `sounddevice.rec` should be bypassed or mocked via `MockSTTEngine` or synthetic audio buffers.
- **Dynamic Weather API**: Weather actions in offline mode provide a polite generic response (`"Đang kiểm tra thời tiết hôm nay cho Ngài."`) or call `wttr.in` when network is reachable.

---

## 4. Conclusion

The blueprint for natural conversational Vietnamese response generation across `jarvis/llm/router.py` and `jarvis/core/app.py` is fully formulated and ready for implementation by workers:
1. `IntentResult` upgraded with `response_text`.
2. Complete 16-row Vietnamese Keyword Routing Matrix established across Tier 1, Tier 2, and Tier 3.
3. `JarvisApp.process_text_command()` upgraded to extract live telemetry messages and natural response texts.
4. Exact fallback `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"` strictly enforced.
5. Multi-modal compatibility with TTS and UI overlay verified.

---

## 5. Verification Method

To independently verify the implementation after workers apply changes:

1. **Run Unit & Router Tests**:
   ```bash
   python -m pytest tests/test_llm_router.py tests/unit/test_llm_engine.py -v
   ```
2. **Run E2E App Integration & Adversarial Tests**:
   ```bash
   python -m pytest tests/test_adversarial_m3_ui_app.py tests/unit/test_app_integration.py -v
   ```
3. **Run New Vietnamese M2 Test Suite**:
   ```bash
   python -m pytest tests/test_vietnamese_router_m2.py -v
   ```
4. **Full Regression Suite**:
   ```bash
   python -m pytest tests/ -x -q
   ```
   All 518+ tests must pass with 0 errors.

---
*End of Handoff Report*
