# Handoff Report — Reviewer 1 (M1): Voice Pipeline & Comms Core Hardening

## 1. Observation

### Observation 1: Code Modification in `jarvis/core/app.py`
In `jarvis/core/app.py` at line 1738:
```python
1735:         # H-01 fix: Whisper requires 16kHz input. Record at 16000 Hz directly to
1736:         # avoid the silent 44100→16000 resample mismatch that caused ROUTER_ABSTAIN.
1737:         # Decouple STT capture sample rate (default 16000) from system playback audio.sample_rate (44100).
1738:         sr = int(sample_rate or self.config.get("stt.sample_rate", 16000))
1739:         max_dur = float(duration_s or self.config.get("stt.timeout_s", 4.0))
1740: 
1741:         if self.headless:
1742:             return np.zeros(int(sr * min(max_dur, 0.1)), dtype=np.float32)
```
- In `config/default_config.yaml` lines 30-31:
  ```yaml
  audio:
    sample_rate: 44100          # 44.1 kHz
  ```
- Prior code inspected from git diff / history:
  ```python
  sr = int(sample_rate or self.config.get("audio.sample_rate", 16000))
  ```
  which evaluated to `44100` under default configuration.
- The new code decouples STT capture rate via `self.config.get("stt.sample_rate", 16000)`. When unconfigured, it defaults to 16000 Hz, completely independent of `audio.sample_rate: 44100`.

### Observation 2: Runtime Probe Output
Executing the runtime probe independently:
```powershell
python -c "from jarvis.core.app import JarvisApp; app = JarvisApp(headless=True); app.initialize(); arr = app.record_audio(duration_s=1.0); print(len(arr))"
```
Verbatim stdout output:
```
1600
```
This confirms that with `headless=True`, `min(1.0, 0.1) * 16000 = 1600` samples are generated (a 100ms slice at 16kHz), down from the erroneous 4410 samples at 44.1kHz.

### Observation 3: Code Modification in `jarvis/comms/zalo.py`
In `jarvis/comms/zalo.py` at lines 340-350:
```python
340:     def send_image(self, user_id: str, image_path: str, caption: str = "") -> ZaloSendResult:
341:         """Send image file to user (mock: just logs)."""
342:         log.info("Send image to %s: %s (%s)", user_id, image_path, caption)
343:         self.sent_messages.append({"user_id": user_id, "image": image_path, "caption": caption})
344:         if self.is_mock:
345:             return ZaloSendResult(success=True, message_id="mock_img_id")
346:         if not self.config.access_token:
347:             log.warning("Zalo send_image rejected: access_token not configured")
348:             return ZaloSendResult(success=False, error="NOT_CONFIGURED")
349:         return ZaloSendResult(success=True, message_id="img_not_implemented")
```
- Lines 346-348 were added. When `self.is_mock` is False and `self.config.access_token` is empty or None, it returns `ZaloSendResult(success=False, error="NOT_CONFIGURED")`.
- Line 349 returns `ZaloSendResult(success=True, message_id="img_not_implemented")` when `access_token` is provided.

### Observation 4: Affected Test Suite Execution
Running the target test command:
```powershell
pytest tests/unit/test_voice_pipeline_fixes.py tests/unit/test_zalo_bot.py tests/test_comms_hub.py -v
```
Verbatim test output:
```
============================= test session starts =============================
collected 34 items

tests\unit\test_voice_pipeline_fixes.py ........                         [ 23%]
tests\unit\test_zalo_bot.py .....................                        [ 85%]
tests\test_comms_hub.py .....                                            [100%]

============================= 34 passed in 4.48s ==============================
```
All 34 tests passed with 0 failures in 4.48s.

---

## 2. Logic Chain

1. **Decoupling Validation (H-01 / F-01)**:
   - *From Observation 1*: Whisper models require 16000 Hz float32 PCM input.
   - The query `self.config.get("stt.sample_rate", 16000)` prevents `record_audio()` from inheriting `audio.sample_rate: 44100` from `config/default_config.yaml`.
   - *From Observation 2*: The empirical probe produced exactly 1600 samples, proving that 16000 Hz is selected in runtime environments when no override is given.
   - *From Observation 4*: `test_h01_record_audio_default_16khz`, `test_h01_record_audio_sample_rate_precedence`, and `test_h01_record_audio_headless_16khz_buffer_length` all passed, demonstrating that explicit parameter overrides (`sample_rate=22050`), configuration overrides (`stt.sample_rate: 8000`), and default settings (`16000`) adhere strictly to precedence rules.

2. **Fail-Closed Validation (F-06)**:
   - *From Observation 3*: `ZaloBotController.send_image()` now intercepts missing or empty `access_token` when `is_mock=False` before any attempt to execute or report success.
   - It returns `ZaloSendResult(success=False, error="NOT_CONFIGURED")` and logs a warning.
   - *From Observation 4*: `test_send_image_not_configured_when_token_empty` in `tests/unit/test_zalo_bot.py` asserts `result.success is False` and `"NOT_CONFIGURED" in result.error`, which passed.
   - `test_mock_send_image_returns_success` verified that mock mode continues to return `success=True` and `mock_img_id` as expected for testing.

3. **Integrity & Anti-Fabrication Assessment**:
   - Actively checked for hardcoded test results: None found in production code.
   - Actively checked for facade/dummy implementations: The sample rate decoupling and access token validation are authentic runtime checks.
   - Actively checked for shortcuts or bypassed tests: Test fixtures in `tests/unit/test_voice_pipeline_fixes.py` were properly updated to use the production default `audio.sample_rate: 44100` rather than masking the defect with 16000.
   - No integrity violations or cheating detected.

---

## 3. Caveats

1. **Pre-existing Ghost Success in `ZaloBotController.send_image` (Adversarial Challenge 1)**:
   - In `jarvis/comms/zalo.py:349`: When `is_mock=False` and `self.config.access_token` IS set, `send_image()` returns `ZaloSendResult(success=True, message_id="img_not_implemented")`.
   - While Milestone 1 specifically required fixing the unconfigured token fail-closed behavior (`access_token="" -> NOT_CONFIGURED`), returning `success=True` when real image transmission is not implemented represents a lingering ghost success under AUDIT_FRAMEWORK.md (Pitfall #2).
2. **Type Coercion on Explicit `None` in Config (Adversarial Challenge 2)**:
   - In `jarvis/core/app.py:1738`: `sr = int(sample_rate or self.config.get("stt.sample_rate", 16000))`. If `stt.sample_rate` is explicitly present in config with value `None` (e.g. from a YAML `null` field), `self.config.get` returns `None`, resulting in `int(None)` which raises `TypeError`.
3. **E2E Acceptance Test Harness Limitations**:
   - Running `tests/e2e/test_beta_v1_acceptance.py` (slated for M5) revealed 2 test harness assertion/threading mismatches (`test_tier1_acoustic_settling_delay_and_playback_lockout` and `test_tier3_interaction_hotkey_ptt_to_settling_to_record_audio_pipeline`). These are issues in the acceptance test mock setup, not regressions in `record_audio()` or `send_image()`.

---

## 4. Conclusion

**Verdict: APPROVE**

The work product delivered by Worker Beta M1 completely satisfies all requirements assigned to Milestone 1:
1. `record_audio()` properly decouples STT recording from general `audio.sample_rate: 44100`, defaulting cleanly to 16000 Hz for Whisper models.
2. `ZaloBotController.send_image()` enforces strict fail-closed semantics (`success=False, error="NOT_CONFIGURED"`) when credentials are unconfigured.
3. All 34 affected unit tests across `test_voice_pipeline_fixes.py`, `test_zalo_bot.py`, and `test_comms_hub.py` pass 100%.
4. Zero integrity violations detected.

### Recommended Follow-up Actions (for Orchestrator / Subsequent Milestones)
- **Recommendation 1 (Anti-Fabrication Hardening in Zalo)**: Update `jarvis/comms/zalo.py:349` to return `ZaloSendResult(success=False, error="NOT_IMPLEMENTED")` when `is_mock=False` and `access_token` is present, eliminating the ghost success until the Zalo OA media upload API is fully wired.
- **Recommendation 2 (Defensive Sample Rate Resolution)**: Update `jarvis/core/app.py:1738` to `sr = int(sample_rate or self.config.get("stt.sample_rate") or 16000)` to guard against explicit `null`/`None` configuration values.

---

## 5. Verification Method

### Test Suite Execution Command
Run the affected test suites:
```powershell
pytest tests/unit/test_voice_pipeline_fixes.py tests/unit/test_zalo_bot.py tests/test_comms_hub.py -v
```
Expected result: `34 passed in < 5s`.

### Runtime Probe Verification Command
Execute headless audio record probe:
```powershell
python -c "from jarvis.core.app import JarvisApp; app = JarvisApp(headless=True); app.initialize(); arr = app.record_audio(duration_s=1.0); print(len(arr))"
```
Expected result: exactly `1600`.

### Files to Inspect
- `jarvis/core/app.py` (lines 1735–1742)
- `jarvis/comms/zalo.py` (lines 340–350)
- `tests/unit/test_voice_pipeline_fixes.py` (lines 26, 47–90)
- `tests/unit/test_zalo_bot.py` (lines 98–105, 142–152)

### Invalidation Conditions
- If `record_audio()` returns an array with length != 1600 under `duration_s=1.0` in headless mode when `audio.sample_rate: 44100`.
- If `ZaloBotController.send_image()` returns `success=True` when `is_mock=False` and `access_token=""`.
- If any test in `test_voice_pipeline_fixes.py` fails.
