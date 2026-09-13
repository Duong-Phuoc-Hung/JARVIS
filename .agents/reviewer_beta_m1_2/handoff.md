# Handoff Report — Reviewer 2 (Milestone 1: JARVIS Beta v1)

**Date**: 2026-09-13T10:53:00Z  
**Agent**: Reviewer 2 & Critic (`reviewer_beta_m1_2`)  
**Parent**: `fcbdbddb-159a-4432-af21-f3ef3e4e8c4e`  
**Target Milestone**: Milestone 1 (M1 — Voice Pipeline & Comms Core Hardening)  
**Verdict**: **REQUEST_CHANGES** ❌  

---

## Review Summary

**Verdict**: **REQUEST_CHANGES**  
While the fixes for sample rate precedence (`H-01`), device index synchronization (`H-02`), settling delay / playback lockout (`H-03`), hotkey registration (`H-04`), and volume/brightness fail-closed semantics (`H-08`) in `jarvis/core/app.py` are correct and fully verified by unit tests, the implementation in `jarvis/comms/zalo.py` contains a critical **INTEGRITY VIOLATION / GHOST SUCCESS** defect in `send_image()`:
1. When `self.config.access_token` contains whitespace (e.g. `"   "`), it bypasses `if not self.config.access_token:` and returns `success=True`.
2. Even when a non-empty token is provided, `send_image()` does not implement image upload to Zalo OA, yet returns `ZaloSendResult(success=True, message_id="img_not_implemented")`. This dummy/facade return violates `AGENTS.md` Rule 2 (Anti-Fabrication Principle) and the fail-closed security contract.

---

## 1. Observation

### Observation 1: Integrity Violation & Ghost Success in `jarvis/comms/zalo.py:send_image`
In `jarvis/comms/zalo.py` at lines 340–350:
```python
    def send_image(self, user_id: str, image_path: str, caption: str = "") -> ZaloSendResult:
        """Send image file to user (mock: just logs)."""
        log.info("Send image to %s: %s (%s)", user_id, image_path, caption)
        self.sent_messages.append({"user_id": user_id, "image": image_path, "caption": caption})
        if self.is_mock:
            return ZaloSendResult(success=True, message_id="mock_img_id")
        if not self.config.access_token:
            log.warning("Zalo send_image rejected: access_token not configured")
            return ZaloSendResult(success=False, error="NOT_CONFIGURED")
        return ZaloSendResult(success=True, message_id="img_not_implemented")
```
- Line 346: `if not self.config.access_token:` checks truthiness without `.strip()`. Any whitespace string (`"   "`, `"\t\n"`) bypasses the guard.
- Line 349: If `self.config.access_token` is present or bypassed, the method unconditionally returns `ZaloSendResult(success=True, message_id="img_not_implemented")` without performing any network call to Zalo's media upload API.
- Contrast with `jarvis/comms/discord.py` lines 351–361, where un-implemented file upload correctly fails closed:
  ```python
  return {
      "success": False,
      "error_code": "FILE_SEND_NOT_IMPLEMENTED",
      "description": f"File '{filename}' was NOT uploaded — Discord multipart file upload is not yet implemented.",
      "data": record,
  }
  ```

### Observation 2: Audio Capture & Hardware Synchronization in `jarvis/core/app.py`
In `jarvis/core/app.py` at lines 1735–1763:
- Line 1738:
  ```python
  sr = int(sample_rate or self.config.get("stt.sample_rate", 16000))
  ```
  Decoupled from `audio.sample_rate: 44100` (which defines playback rate in `config/default_config.yaml`).
- Line 1741–1742:
  ```python
  if self.headless:
      return np.zeros(int(sr * min(max_dur, 0.1)), dtype=np.float32)
  ```
  In headless mode, yields `int(16000 * 0.1) = 1600` samples.
- Lines 1746–1755:
  ```python
  target_device = None
  if self.audio_engine and getattr(self.audio_engine, "_active_device_index", None) is not None:
      target_device = self.audio_engine._active_device_index
  if target_device is None:
      cfg_dev = self.config.get("audio.input_device")
      if cfg_dev is not None:
          try:
              target_device = int(cfg_dev)
          except (ValueError, TypeError):
              target_device = None
  ```
  `target_device` is passed into both `_sd.InputStream(..., device=target_device)` (line 1774) and fallback `_sd.rec(..., device=target_device)` (line 1799).
- Lines 1759–1763:
  ```python
  if self.tts_manager and getattr(self.tts_manager, "is_playing", False):
      t_wait_start = time.monotonic()
      while getattr(self.tts_manager, "is_playing", False) and (time.monotonic() - t_wait_start) < 1.0:
          time.sleep(0.05)
  ```
  Acoustic settling guard prevents microphone self-capture while TTS is actively playing.
- Line 1832:
  ```python
  time.sleep(0.15)
  ```
  150ms settling delay post-greeting before microphone recording commences.

### Observation 3: Zero-Crash Hotkey Registration in `jarvis/core/app.py`
In `jarvis/core/app.py` at lines 585–592 and line 608:
```python
        def _ptt_voice_cb():
            threading.Thread(
                target=self._start_voice_interaction,
                kwargs={"trigger_name": "HOTKEY_PTT", "greeting_phrase": "Vâng, tôi nghe."},
                daemon=True,
            ).start()
```
```python
        self.hotkey_manager.register("Ctrl+Shift+L", _ptt_voice_cb, "Ghi âm lệnh giọng nói tức thì (PTT)")
```
`_ptt_voice_cb` targets existing `self._start_voice_interaction` with `trigger_name="HOTKEY_PTT"`. No `AttributeError` can occur.

### Observation 4: Hardware Fail-Closed Semantics in `jarvis/core/app.py`
In `jarvis/core/app.py` at lines 1297–1325:
- Lines 1302–1303:
  ```python
  if vol is None:
      return {"status": "failed", "success": False, "volume": None, "error": "VOLUME_SET_FAILED", "message": "Không thể đặt âm lượng phần cứng, thưa Ngài."}
  ```
- Lines 1307–1308:
  ```python
  if vol is None:
      return {"status": "failed", "success": False, "volume": None, "error": "VOLUME_CHANGE_FAILED", "message": "Không thể điều chỉnh âm lượng phần cứng, thưa Ngài."}
  ```
- Lines 1317–1318:
  ```python
  if b is None:
      return {"status": "failed", "success": False, "brightness": None, "error": "BRIGHTNESS_SET_FAILED", "message": "Không thể đặt độ sáng màn hình, thưa Ngài."}
  ```
- Lines 1322–1323:
  ```python
  if b is None:
      return {"status": "failed", "success": False, "brightness": None, "error": "BRIGHTNESS_CHANGE_FAILED", "message": "Không thể điều chỉnh độ sáng màn hình, thưa Ngài."}
  ```
- Lines 1310 & 1325:
  When `self.computer_controller is None`, returns `{"status": "failed", "success": False, "message": "Computer controller unavailable"}`.

### Observation 5: Regression Test Suite Execution
Direct command:
`pytest tests/unit/test_voice_pipeline_fixes.py tests/unit/test_hotkeys.py tests/unit/test_zalo_bot.py -v`
Verbatim execution result:
```
============================= test session starts =============================
collected 37 items

tests\unit\test_voice_pipeline_fixes.py ........                         [ 21%]
tests\unit\test_hotkeys.py ........                                      [ 43%]
tests\unit\test_zalo_bot.py .....................                        [100%]

============================= 37 passed in 3.07s ==============================
```

---

## 2. Logic Chain

1. **Audio Pipeline & Hardware Controls Verification (Observations 2, 3, 4, 5)**:
   - `H-01`: Decoupling `stt.sample_rate` (16000) from `audio.sample_rate` (44100) ensures Whisper STT receives native 16kHz audio. Headless buffer length is confirmed at 1600 samples for 0.1s. Tests `test_h01_record_audio_default_16khz`, `test_h01_record_audio_sample_rate_precedence`, and `test_h01_record_audio_headless_16khz_buffer_length` pass.
   - `H-02`: AudioEngine device synchronization is wired into both stream and fallback recording calls. Test `test_h02_record_audio_uses_audio_engine_device` passes.
   - `H-03`: Post-greeting settling delay (150ms) and active TTS playback loop guard against acoustic self-echo. Test `test_h03_record_audio_waits_for_active_tts` passes.
   - `H-04`: Global shortcut `Ctrl+Shift+L` registers to valid callback `_ptt_voice_cb` invoking `_start_voice_interaction`. Test `test_h04_hotkey_registration_has_valid_target` passes.
   - `H-08`: Volume and brightness handlers fail closed with `success: False` and specific error codes when controllers return `None`. Tests `test_h08_volume_fail_closed_on_none` and `test_h08_brightness_fail_closed_on_none` pass.

2. **Zalo Integrity Violation (Observation 1)**:
   - In accordance with `AGENTS.md` Rule 2:
     > "Nếu một dịch vụ thiếu cấu hình (API key, bot token)... hàm PHẢI trả về trạng thái thất bại thực chất (False, None, hoặc error code cụ thể như NOT_CONFIGURED)... Tuyệt đối không trả `{'ok': True}` hoặc `{'success': True}` ngầm định (Silent Fallback) khi hành động chưa thực sự diễn ra thành công."
   - In `jarvis/comms/zalo.py:send_image()`:
     - Step A: When `access_token` contains whitespace, `if not self.config.access_token:` evaluates to `False`. The check is bypassed.
     - Step B: Execution reaches line 349: `return ZaloSendResult(success=True, message_id="img_not_implemented")`.
     - Step C: This returns `success=True` for an action that was never executed or sent. It constitutes an **INTEGRITY VIOLATION / GHOST SUCCESS** as defined in the agent review and critic guidelines.
     - Step D: Furthermore, even when a non-whitespace `access_token` is provided, `send_image()` does not upload the image, yet still returns `success=True`.

---

## 3. Caveats

- Live external network calls to Zalo OA, Telegram, Discord, and IMAP servers were not executed with active credentials because production credentials are not configured on this workstation (`PENDING_CREDENTIALS`).
- Per strict constraint "Review-only — do NOT modify implementation code", Reviewer 2 did not modify `jarvis/comms/zalo.py`. Remediation must be performed by a Worker agent.

---

## 4. Conclusion & Findings

### Finding 1: [Critical] INTEGRITY VIOLATION — Ghost Success in `jarvis/comms/zalo.py:send_image`
- **What**: `send_image()` returns `success=True, message_id="img_not_implemented"` when `is_mock=False` and a token is present, even though no image was sent.
- **Where**: `jarvis/comms/zalo.py:349`.
- **Why**: Direct violation of `AGENTS.md` Rule 2 (Anti-Fabrication Principle). No service may report `success=True` when the underlying operation is not implemented.
- **Suggestion**:
  ```python
  token = (self.config.access_token or "").strip()
  if not token:
      log.warning("Zalo send_image rejected: access_token not configured")
      return ZaloSendResult(success=False, error="NOT_CONFIGURED")
  log.warning("Zalo send_image: OA image upload API is not yet implemented")
  return ZaloSendResult(success=False, error="NOT_IMPLEMENTED", message_id="img_not_implemented")
  ```

### Finding 2: [Major] Fail-Closed Bypass on Whitespace Token
- **What**: Whitespace-only tokens (`"   "`, `"\t\n"`) bypass `if not self.config.access_token:` in `send_image()` and `send_message()`.
- **Where**: `jarvis/comms/zalo.py:314` and `jarvis/comms/zalo.py:346`.
- **Why**: Non-empty whitespace string evaluates to truthy, bypassing the `NOT_CONFIGURED` fail-closed guard.
- **Suggestion**: Use `token = (self.config.access_token or "").strip()` in both methods.

### Finding 3: [Minor] Test Suite Completeness
- **What**: `tests/unit/test_zalo_bot.py` only tested empty string `""` and mock mode, masking the whitespace and `img_not_implemented` ghost success behavior.
- **Where**: `tests/unit/test_zalo_bot.py:142–152`.
- **Suggestion**: Add tests verifying that whitespace tokens return `NOT_CONFIGURED` and that non-mock mode returns `success=False` when upload is not implemented.

---

## 5. Verification Method

### Direct Test Commands
1. Run target regression suites:
   ```bash
   pytest tests/unit/test_voice_pipeline_fixes.py tests/unit/test_hotkeys.py tests/unit/test_zalo_bot.py -v
   ```
   (Expected: 37 passed).

2. Re-test whitespace & non-implemented image fail-closed probe:
   ```bash
   python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; c = ZaloBotController(config=ZaloConfig(access_token='   '), is_mock=False); res = c.send_image('u1', 'img.png'); assert res.success is False, f'Ghost success: {res}'; print('PASS')"
   ```
   (Currently fails with `AssertionError: Ghost success: ZaloSendResult(success=True, error='', message_id='img_not_implemented')`).

3. Verify fix once applied by Worker:
   ```bash
   python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; c = ZaloBotController(config=ZaloConfig(access_token='fake_token'), is_mock=False); res = c.send_image('u1', 'img.png'); assert res.success is False and res.error == 'NOT_IMPLEMENTED', f'Unexpected: {res}'; print('PASS')"
   ```

### Invalidation Conditions
- If `send_image()` continues to return `success=True` when `is_mock=False` and `access_token="   "`.
- If `send_image()` continues to return `success=True` when `is_mock=False` and `access_token="any_token"` while upload is not implemented.
