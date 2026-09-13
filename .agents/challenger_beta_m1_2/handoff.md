# Challenger 2 Handoff Report — Milestone 1 (JARVIS Beta v1)

**Date**: 2026-09-13T10:51:00Z  
**Author**: Challenger 2 (`challenger_beta_m1_2`)  
**Target Milestone**: M1 (Voice Pipeline & Comms Core Hardening)  
**Parent Agent**: `fcbdbddb-159a-4432-af21-f3ef3e4e8c4e`  
**Verdict**: **REQUEST_CHANGES** ❌

---

## 1. Observation

### Observation 1: `ZaloBotController.send_image()` Whitespace Bypass & Ghost Success
In `jarvis/comms/zalo.py`:
Lines 340-350:
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
When `self.config.access_token` contains whitespace (e.g. `"   "` or `"\t\n  "`), `bool(self.config.access_token)` evaluates to `True`.
The check `if not self.config.access_token:` is bypassed, and line 349 executes:
`return ZaloSendResult(success=True, message_id="img_not_implemented")`.

Direct empirical probe output:
Command:
```powershell
python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; c = ZaloBotController(config=ZaloConfig(access_token='   '), is_mock=False); res = c.send_image('u1', 'img.png'); print('RESULT:', res)"
```
Output:
```
RESULT: ZaloSendResult(success=True, error='', message_id='img_not_implemented')
```

Empirical pytest run on `tests/test_adversarial_beta_m1_comms_failclosed.py`:
Command:
```powershell
pytest tests/test_adversarial_beta_m1_comms_failclosed.py -v
```
Output snippet:
```
FAILED tests/test_adversarial_beta_m1_comms_failclosed.py::TestZaloSendImageFailClosed::test_zalo_send_image_whitespace_token - AssertionError: FABRICATION/GHOST SUCCESS: send_image returned success=True on whitespace token! result=ZaloSendResult(success=True, error='', message_id='img_not_implemented')
FAILED tests/test_adversarial_beta_m1_comms_failclosed.py::TestZaloSendImageFailClosed::test_zalo_send_image_tab_newline_whitespace - AssertionError: FABRICATION/GHOST SUCCESS: send_image returned success=True on tab/newline token! result=ZaloSendResult(success=True, error='', message_id='img_not_implemented')
======================== 2 failed, 15 passed in 2.59s =========================
```

### Observation 2: `ZaloBotController.send_image()` Mock Mode & Empty Token
- With default / unconfigured token (`access_token=""`): `send_image()` returns `ZaloSendResult(success=False, error="NOT_CONFIGURED", message_id="")`.
- With `is_mock=True`: `send_image()` returns `ZaloSendResult(success=True, error="", message_id="mock_img_id")`.

### Observation 3: Telegram, Discord, and IMAP Fail-Closed Semantics
- `TelegramBotController`:
  - `send_message()` without `http_client` returns `{"ok": False, "error_code": "NOT_CONFIGURED", "description": "No HTTP client configured. Message was NOT sent to Telegram."}`
  - `send_photo()` without `http_client` returns `{"ok": False, "error_code": "NOT_CONFIGURED", "description": "No HTTP client configured. Photo was NOT sent to Telegram."}`
- `DiscordBotController`:
  - `send_message()` without `bot_token` / `_http` returns `{"success": False, "error_code": "NOT_CONFIGURED", "description": "No bot_token configured. Message was NOT sent to Discord.", ...}`
  - `send_file()` without `bot_token` / `_http` returns `{"success": False, "error_code": "NOT_CONFIGURED", "description": "No bot_token configured. File '...' was NOT sent to Discord.", ...}`
  - `send_embed()` without `bot_token` / `_http` returns `{"success": False, "error_code": "NOT_CONFIGURED", "description": "No bot_token configured. Embed was NOT sent to Discord.", ...}`
- `IMAPEmailReader`:
  - `connect()` with unconfigured credentials raises `IMAPNotConfiguredError("IMAPEmailReader: host, username, and password are all required. ... Status: NOT_CONFIGURED")`
  - `fetch_and_summarize()` with unconfigured credentials raises `IMAPNotConfiguredError`

### Observation 4: Hardware Volume & Brightness Fail-Closed Semantics
In `jarvis/core/app.py`:
- `_handle_system_volume(level=80)` when `computer_controller.set_volume()` returns `None`:
  Returns: `{"status": "failed", "success": False, "volume": None, "error": "VOLUME_SET_FAILED", "message": "Không thể đặt âm lượng phần cứng, thưa Ngài."}`
- `_handle_system_volume(delta=10)` when `computer_controller.change_volume()` returns `None`:
  Returns: `{"status": "failed", "success": False, "volume": None, "error": "VOLUME_CHANGE_FAILED", "message": "Không thể điều chỉnh âm lượng phần cứng, thưa Ngài."}`
- `_handle_system_brightness(level=70)` when `computer_controller.set_brightness()` returns `None`:
  Returns: `{"status": "failed", "success": False, "brightness": None, "error": "BRIGHTNESS_SET_FAILED", "message": "Không thể đặt độ sáng màn hình, thưa Ngài."}`
- `_handle_system_brightness(delta=-10)` when `computer_controller.change_brightness()` returns `None`:
  Returns: `{"status": "failed", "success": False, "brightness": None, "error": "BRIGHTNESS_CHANGE_FAILED", "message": "Không thể điều chỉnh độ sáng màn hình, thưa Ngài."}`
- When `computer_controller` is `None`:
  Both return `{"status": "failed", "success": False, "message": "Computer controller unavailable"}`.

---

## 2. Logic Chain

1. **Requirement Check**:
   The authoritative user objective states:
   * "`ZaloBotController.send_image()` with missing token, empty token, whitespace token -> must return `success=False` and `error="NOT_CONFIGURED"`."
   * "Verify no silent fallback or ghost success occurs."
   * `AGENTS.md` Rule 2: "Fail-Closed Mặc Định: Nếu một dịch vụ thiếu cấu hình (API key, bot token)... hàm PHẢI trả về trạng thái thất bại thực chất (`False`, `None`, hoặc error code cụ thể như `NOT_CONFIGURED`... Tuyệt đối không trả `{'ok': True}` hoặc `{'success': True}` ngầm định (Silent Fallback) khi hành động chưa thực sự diễn ra thành công."
2. **Implementation Flaw in `jarvis/comms/zalo.py`**:
   Line 346 performs:
   `if not self.config.access_token:`
   It fails to strip whitespace (`self.config.access_token.strip()`).
   Therefore, any whitespace-only string (e.g. `"   "`, `"\t\n  "`) bypasses the `NOT_CONFIGURED` check.
3. **Ghost Success Consequence**:
   Because line 349 unconditionally executes:
   `return ZaloSendResult(success=True, message_id="img_not_implemented")`
   any caller passing a whitespace-only token receives `success=True`.
   This is a direct violation of the fail-closed invariant and represents an active ghost success.
4. **Scope of the Defect**:
   - `send_image()` missing token (`""`): PASSES fail-closed (`success=False, error="NOT_CONFIGURED"`).
   - `send_image()` whitespace token (`"   "`): FAILS (`success=True, error=""`).
   - `send_image()` tab/newline whitespace token (`"\t\n  "`): FAILS (`success=True, error=""`).
   - `send_image()` with unverified token and `is_mock=False`: returns `success=True, message_id="img_not_implemented"` without sending an image (stub pseudo-success).
   - All other tested comms (Telegram, Discord, IMAP) and hardware volume/brightness handlers strictly adhere to fail-closed semantics.

---

## 3. Caveats

- Live network endpoints for Zalo OA, Telegram, Discord, and IMAP were not contacted with valid credentials as credentials are unconfigured on this development workstation (`PENDING_CREDENTIALS`). All tests were performed against the unconfigured/missing/invalid credential boundary conditions.
- Per constraint "Review-only — do NOT modify implementation code", Challenger 2 did not patch `jarvis/comms/zalo.py`. The worker agent must apply the recommended fix.

---

## 4. Conclusion & Verdict

**Verdict**: **REQUEST_CHANGES** ❌

The implementation in `jarvis/comms/zalo.py` fails the M1 adversarial challenge on whitespace token handling for `send_image()`, returning `success=True` (ghost success) instead of `success=False, error="NOT_CONFIGURED"`.

### Recommended Mitigation for Worker Agent
In `jarvis/comms/zalo.py`, update `send_image()` (and optionally `send_message()`) to strip whitespace when checking `access_token`:
```python
    def send_image(self, user_id: str, image_path: str, caption: str = "") -> ZaloSendResult:
        """Send image file to user (mock: just logs)."""
        log.info("Send image to %s: %s (%s)", user_id, image_path, caption)
        self.sent_messages.append({"user_id": user_id, "image": image_path, "caption": caption})
        if self.is_mock:
            return ZaloSendResult(success=True, message_id="mock_img_id")
        token = (self.config.access_token or "").strip()
        if not token:
            log.warning("Zalo send_image rejected: access_token not configured")
            return ZaloSendResult(success=False, error="NOT_CONFIGURED")
        # In non-mock mode without real OA image API implementation, fail closed
        return ZaloSendResult(success=False, error="NOT_IMPLEMENTED", message_id="img_not_implemented")
```
Similarly in `send_message()`:
```python
        token = (self.config.access_token or "").strip()
        if not token:
            log.warning("Zalo send rejected: access_token not configured")
            return ZaloSendResult(success=False, error="NOT_CONFIGURED")
```

---

## 5. Verification Method

To independently verify this finding:

1. Run the empirical adversarial probe suite created by Challenger 2:
   ```powershell
   pytest tests/test_adversarial_beta_m1_comms_failclosed.py -v
   ```
2. Observe failures on:
   - `TestZaloSendImageFailClosed::test_zalo_send_image_whitespace_token`
   - `TestZaloSendImageFailClosed::test_zalo_send_image_tab_newline_whitespace`
3. Direct single-line Python verification:
   ```powershell
   python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; c = ZaloBotController(config=ZaloConfig(access_token='   '), is_mock=False); res = c.send_image('u1', 'img.png'); assert res.success is False, f'Ghost success observed: {res}'; print('PASSED')"
   ```
4. Once the worker agent applies `token = (self.config.access_token or "").strip()` in `jarvis/comms/zalo.py`, re-run `pytest tests/test_adversarial_beta_m1_comms_failclosed.py -v` to ensure all 17 tests pass 100%.

---

## Adversarial Challenge Summary Matrix

| Probe / Dimension | Target Component | Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|---|---|
| Zalo Missing Token | `ZaloBotController.send_image` | Default config (`access_token=""`) | `success=False, error="NOT_CONFIGURED"` | `success=False, error="NOT_CONFIGURED"` | ✅ PASS |
| Zalo Empty Token | `ZaloBotController.send_image` | `access_token=""` | `success=False, error="NOT_CONFIGURED"` | `success=False, error="NOT_CONFIGURED"` | ✅ PASS |
| Zalo Whitespace Token | `ZaloBotController.send_image` | `access_token="   "` | `success=False, error="NOT_CONFIGURED"` | `success=True, error="", message_id="img_not_implemented"` | ❌ **FAIL** (Ghost Success) |
| Zalo Tab/NL Token | `ZaloBotController.send_image` | `access_token="\t\n  "` | `success=False, error="NOT_CONFIGURED"` | `success=True, error="", message_id="img_not_implemented"` | ❌ **FAIL** (Ghost Success) |
| Zalo Mock Mode | `ZaloBotController.send_image` | `is_mock=True` | `success=True, message_id="mock_img_id"` | `success=True, message_id="mock_img_id"` | ✅ PASS |
| Telegram Send Msg | `TelegramBotController.send_message` | No HTTP client | `ok=False, error_code="NOT_CONFIGURED"` | `ok=False, error_code="NOT_CONFIGURED"` | ✅ PASS |
| Telegram Send Photo | `TelegramBotController.send_photo` | No HTTP client | `ok=False, error_code="NOT_CONFIGURED"` | `ok=False, error_code="NOT_CONFIGURED"` | ✅ PASS |
| Discord Send Msg | `DiscordBotController.send_message` | No bot token | `success=False, error_code="NOT_CONFIGURED"` | `success=False, error_code="NOT_CONFIGURED"` | ✅ PASS |
| Discord Send File | `DiscordBotController.send_file` | No bot token | `success=False, error_code="NOT_CONFIGURED"` | `success=False, error_code="NOT_CONFIGURED"` | ✅ PASS |
| Discord Send Embed | `DiscordBotController.send_embed` | No bot token | `success=False, error_code="NOT_CONFIGURED"` | `success=False, error_code="NOT_CONFIGURED"` | ✅ PASS |
| IMAP Connect | `IMAPEmailReader.connect` | Unconfigured creds | Raises `IMAPNotConfiguredError` | Raises `IMAPNotConfiguredError` | ✅ PASS |
| IMAP Summarize | `IMAPEmailReader.fetch_and_summarize` | Unconfigured creds | Raises `IMAPNotConfiguredError` | Raises `IMAPNotConfiguredError` | ✅ PASS |
| Hardware Volume Set | `JarvisApp._handle_system_volume` | `controller.set_volume() -> None` | `success=False, error="VOLUME_SET_FAILED"` | `success=False, error="VOLUME_SET_FAILED"` | ✅ PASS |
| Hardware Volume Change | `JarvisApp._handle_system_volume` | `controller.change_volume() -> None` | `success=False, error="VOLUME_CHANGE_FAILED"` | `success=False, error="VOLUME_CHANGE_FAILED"` | ✅ PASS |
| Hardware Brightness Set | `JarvisApp._handle_system_brightness` | `controller.set_brightness() -> None` | `success=False, error="BRIGHTNESS_SET_FAILED"` | `success=False, error="BRIGHTNESS_SET_FAILED"` | ✅ PASS |
| Hardware Brightness Change | `JarvisApp._handle_system_brightness` | `controller.change_brightness() -> None` | `success=False, error="BRIGHTNESS_CHANGE_FAILED"` | `success=False, error="BRIGHTNESS_CHANGE_FAILED"` | ✅ PASS |
| Hardware Controller None | `JarvisApp._handle_system_volume` | `computer_controller = None` | `status="failed", success=False` | `status="failed", success=False` | ✅ PASS |
