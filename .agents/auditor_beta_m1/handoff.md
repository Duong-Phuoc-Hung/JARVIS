# Forensic Audit Report — Milestone 1 (JARVIS Beta v1)

**Work Product**: Milestone 1 code changes (`jarvis/core/app.py`, `jarvis/comms/zalo.py`, `tests/unit/test_voice_pipeline_fixes.py`, `tests/unit/test_zalo_bot.py`)  
**Profile**: General Project  
**Auditor**: Forensic Auditor Beta M1 (`.agents/auditor_beta_m1`)  
**Verdict**: **INTEGRITY VIOLATION** 🔴

---

## Phase Results

| Check Name | Status | Details |
|---|:---:|---|
| **1. Hardcoded Output Detection** | **PASS** | No hardcoded test assertions, expected output literals, or self-certifying stubs found in `jarvis/core/app.py` or tests. |
| **2. Facade & Ghost Success Detection** | 🔴 **FAIL** | `jarvis/comms/zalo.py:349` returns `ZaloSendResult(success=True, message_id="img_not_implemented")`. When `is_mock=False` and a token is present, it claims `success=True` without performing any image upload or API call. |
| **3. Pre-populated Artifact Detection** | **PASS** | No pre-existing fake test logs or result artifacts detected in the workspace for M1. |
| **4. Build and Runtime Test Execution** | **PASS** | `pytest tests/unit/test_voice_pipeline_fixes.py tests/unit/test_zalo_bot.py -v` executes 29 tests, all 29 passing in 3.22s. |
| **5. Fail-Closed Invariant Check** | 🔴 **FAIL** | `jarvis/comms/zalo.py:346` checks `if not self.config.access_token:` without `.strip()`. Passing whitespace tokens (`"   "`, `"\t\n  "`) bypasses the guard and returns `success=True`. |
| **6. Hardware Fail-Closed Semantics** | **PASS** | `_handle_system_volume()` and `_handle_system_brightness()` strictly return `success=False` and explicit error codes (`VOLUME_SET_FAILED`, `VOLUME_CHANGE_FAILED`, `BRIGHTNESS_SET_FAILED`, `BRIGHTNESS_CHANGE_FAILED`) when hardware controller returns `None`. |
| **7. Dependency Audit** | **PASS** | Standard library and pre-approved project libraries used; no prohibited external delegation. |

---

## 1. Observation

### Observation 1: Facade Implementation & Ghost Success in `jarvis/comms/zalo.py:349`
In `jarvis/comms/zalo.py` (lines 340–350):
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
When `is_mock=False` and `self.config.access_token` is provided (or contains whitespace), line 349 executes:
`return ZaloSendResult(success=True, message_id="img_not_implemented")`.
No HTTP request is constructed, no media is uploaded to Zalo OA, and no network interaction occurs. The method returns `success=True` while simultaneously acknowledging that image transmission is not implemented (`"img_not_implemented"`).

Direct empirical runtime probe command:
```powershell
python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; bot = ZaloBotController(config=ZaloConfig(access_token='valid_test_token'), is_mock=False); res = bot.send_image('user_123', 'photo.jpg'); print('RESULT:', res)"
```
Verbatim stdout:
```
RESULT: ZaloSendResult(success=True, error='', message_id='img_not_implemented')
```

### Observation 2: Whitespace Token Bypass in `jarvis/comms/zalo.py:346`
Line 346 performs:
`if not self.config.access_token:`
In Python, strings containing whitespace evaluate to `bool("   ") == True`. Consequently:
- Unconfigured empty string `""` returns `ZaloSendResult(success=False, error='NOT_CONFIGURED')`.
- Whitespace strings `"   "`, `"\t\n  "` evaluate as truthy, bypass line 346, and fall through to line 349, returning `success=True`.

Direct empirical runtime probe command:
```powershell
python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; bot = ZaloBotController(config=ZaloConfig(access_token='   '), is_mock=False); res = bot.send_image('user_123', 'photo.jpg'); print('RESULT:', res)"
```
Verbatim stdout:
```
RESULT: ZaloSendResult(success=True, error='', message_id='img_not_implemented')
```

### Observation 3: Incomplete Test Coverage in `tests/unit/test_zalo_bot.py`
In `tests/unit/test_zalo_bot.py`, Worker M1 added two tests:
- `test_mock_send_image_returns_success` (verifies `is_mock=True`)
- `test_send_image_not_configured_when_token_empty` (verifies `access_token=""`)

Worker M1 omitted tests for:
1. Whitespace tokens (`access_token="   "`).
2. Non-empty tokens under `is_mock=False` (`access_token="configured_token"`).

Because neither test was written, the test suite showed 21/21 passing, masking the ghost success in line 349.

### Observation 4: Verified Authentic Fixes in `jarvis/core/app.py`
1. **H-01 Sample Rate Decoupling (`jarvis/core/app.py:1738`)**:
   ```python
   sr = int(sample_rate or self.config.get("stt.sample_rate", 16000))
   ```
   Direct empirical probe command:
   ```powershell
   python -c "from jarvis.core.app import JarvisApp; app = JarvisApp(headless=True); app.initialize(); arr = app.record_audio(duration_s=1.0); print('Buffer length:', len(arr))"
   ```
   Verbatim output: `Buffer length: 1600`. Decoupled from `audio.sample_rate: 44100`.
2. **H-02 Microphone Device Sync (`jarvis/core/app.py:1747-1755`)**:
   Correctly passes `target_device` from `AudioEngine._active_device_index` to sounddevice.
3. **H-03 Acoustic Settling Guard (`jarvis/core/app.py:1759-1763, 1831-1832`)**:
   Waits on `tts_manager.is_playing` loop (up to 1.0s) and applies 150ms post-speech settling sleep.
4. **H-04 Zero-Crash Hotkey (`jarvis/core/app.py:588-592`)**:
   `Ctrl+Shift+L` spawns thread executing `_start_voice_interaction(trigger_name="HOTKEY_PTT")`.
5. **H-08 Hardware Fail-Closed (`jarvis/core/app.py:1297-1325`)**:
   Direct empirical probe command:
   ```powershell
   python -c "from unittest.mock import MagicMock; from jarvis.core.app import JarvisApp; app = JarvisApp.__new__(JarvisApp); app.computer_controller = MagicMock(); app.computer_controller.set_volume.return_value = None; r = app._handle_system_volume(level=50); print('vol_set:', r['status'], r['success'], r['error']); app.computer_controller.change_volume.return_value = None; r = app._handle_system_volume(delta=10); print('vol_change:', r['status'], r['success'], r['error']); app.computer_controller.set_brightness.return_value = None; r = app._handle_system_brightness(level=50); print('bri_set:', r['status'], r['success'], r['error']); app.computer_controller.change_brightness.return_value = None; r = app._handle_system_brightness(delta=10); print('bri_change:', r['status'], r['success'], r['error']); app.computer_controller = None; r = app._handle_system_volume(level=50); print('vol_no_ctrl:', r['status'], r['success']); r = app._handle_system_brightness(level=50); print('bri_no_ctrl:', r['status'], r['success'])"
   ```
   Verbatim stdout:
   ```
   vol_set: failed False VOLUME_SET_FAILED
   vol_change: failed False VOLUME_CHANGE_FAILED
   bri_set: failed False BRIGHTNESS_SET_FAILED
   bri_change: failed False BRIGHTNESS_CHANGE_FAILED
   vol_no_ctrl: failed False
   bri_no_ctrl: failed False
   ```

---

## 2. Logic Chain

1. **Anti-Fabrication & Fail-Closed Normative Invariants**:
   - `AGENTS.md` Rule 2 (Fail-Closed Default):
     *"Nếu một dịch vụ thiếu cấu hình (API key, bot token)... hàm PHẢI trả về trạng thái thất bại thực chất (`False`, `None`, hoặc error code cụ thể như `NOT_CONFIGURED`... Tuyệt đối không trả `{'ok': True}` hoặc `{'success': True}` ngầm định (Silent Fallback) khi hành động chưa thực sự diễn ra thành công."*
   - `docs/AUDIT_FRAMEWORK.md` Axis 2 (Truthfulness) & Trap 15:
     *"Một hàm có thể có Tier bằng chứng cao nhưng vẫn fabrication nếu nó trả `success=True`/`ok=True` mà không có bằng chứng thật đứng sau. Trap 15: Fabrication: `success=True` làm fallback mặc định."*
   - General Integrity Profile Prohibited Pattern #2:
     *"Facade implementations: Correct-looking interfaces with no genuine logic (e.g., `return <constant>`)."*

2. **Analysis of Observation 1 & 2**:
   - In `jarvis/comms/zalo.py:346`, unconfigured checks are incomplete because whitespace is not stripped.
   - In `jarvis/comms/zalo.py:349`, when a token is provided, `send_image()` returns `ZaloSendResult(success=True, message_id="img_not_implemented")`.
   - Returning `success=True` for an action that did not take place and is explicitly acknowledged as not implemented (`"img_not_implemented"`) is a direct violation of AGENTS.md Rule 2 and AUDIT_FRAMEWORK.md Axis 2.
   - Contrast this with `jarvis/comms/discord.py:356-361`, where unimplemented file upload correctly returns `success=False, error_code="FILE_SEND_NOT_IMPLEMENTED"`.

3. **Analysis of Observation 3**:
   - Worker M1's unit tests in `tests/unit/test_zalo_bot.py` self-certified compliance by only asserting on `access_token=""` and `is_mock=True`, failing to test whitespace or configured live paths.

4. **Conclusion of Logic Chain**:
   - Even though the core voice pipeline fixes in `jarvis/core/app.py` are genuine and robust, `jarvis/comms/zalo.py` contains an active integrity violation (ghost success / facade implementation).
   - Under the Integrity Forensics standard: *"If ANY check fails, your verdict is INTEGRITY VIOLATION and you MUST reject the work product."*

---

## 3. Caveats

- The voice pipeline fixes in `jarvis/core/app.py` (H-01, H-02, H-03, H-04, H-08) are completely clean, verified, and free of fabrication.
- The defect is strictly localized to `jarvis/comms/zalo.py:346-349` in the Zalo OA adapter.
- Fixing this defect requires updating `jarvis/comms/zalo.py` line 346 to check `if not self.config.access_token or not self.config.access_token.strip():` and updating line 349 to return `ZaloSendResult(success=False, error="IMAGE_SEND_NOT_IMPLEMENTED")`.

---

## 4. Conclusion

The work product submitted for Milestone 1 contains an **INTEGRITY VIOLATION** under `AGENTS.md` Rule 2 and `AUDIT_FRAMEWORK.md` Axis 2:
1. `jarvis/comms/zalo.py` line 349 returns `success=True` with `message_id="img_not_implemented"` when an access token is provided, simulating successful image delivery without real implementation (Silent Fallback / Ghost Success).
2. `jarvis/comms/zalo.py` line 346 fails to strip whitespace, permitting whitespace-only tokens to bypass the `NOT_CONFIGURED` guard and receive `success=True`.

**Verdict**: **INTEGRITY VIOLATION** 🔴 (Work Product Rejected until remediated).

---

## 5. Verification Method & Remediation Spec

### Remediation Required in `jarvis/comms/zalo.py` (lines 346–349):
```python
        token = (self.config.access_token or "").strip()
        if not token:
            log.warning("Zalo send_image rejected: access_token not configured")
            return ZaloSendResult(success=False, error="NOT_CONFIGURED")
        log.warning("Zalo send_image rejected: image upload API is not implemented")
        return ZaloSendResult(success=False, error="IMAGE_SEND_NOT_IMPLEMENTED")
```

### Verification Commands:
1. **Adversarial Whitespace & Token Probe**:
   ```powershell
   python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; b1 = ZaloBotController(config=ZaloConfig(access_token='   '), is_mock=False); r1 = b1.send_image('u1', 'img.png'); print('Whitespace:', r1); b2 = ZaloBotController(config=ZaloConfig(access_token='tok'), is_mock=False); r2 = b2.send_image('u1', 'img.png'); print('Configured:', r2)"
   ```
   Expected after fix:
   - `Whitespace: ZaloSendResult(success=False, error='NOT_CONFIGURED', message_id='')`
   - `Configured: ZaloSendResult(success=False, error='IMAGE_SEND_NOT_IMPLEMENTED', message_id='')`

2. **Unit Test Suite Execution**:
   ```powershell
   pytest tests/unit/test_voice_pipeline_fixes.py tests/unit/test_zalo_bot.py -v
   ```

### Invalidation Conditions:
- If `send_image()` returns `success=True` when `is_mock=False` for any token (empty, whitespace, or non-empty without actual API upload).
