# Remediation Blueprint — Milestone 1 (M1 Iteration 2)

**Author**: Remediation Explorer (`explorer_beta_m1_remediation`)  
**Target Milestone**: Milestone 1 (JARVIS Beta v1 Voice Pipeline & Comms Core Hardening)  
**Parent Agent**: `fcbdbddb-159a-4432-af21-f3ef3e4e8c4e`  
**Date**: 2026-09-13T11:00:00Z  
**Status**: APPROVED BLUEPRINT FOR IMPLEMENTATION  

---

## 1. Executive Summary

Milestone 1 work product was audited and rejected by the Forensic Auditor, Challenger 2, and Reviewer 2 due to an **INTEGRITY VIOLATION / GHOST SUCCESS** in `jarvis/comms/zalo.py`:
1. **Ghost Success in `send_image()` (`jarvis/comms/zalo.py:349`)**: Returned `ZaloSendResult(success=True, message_id="img_not_implemented")` when `is_mock=False` and a token is present, simulating successful message delivery without performing any API call.
2. **Whitespace Bypass (`jarvis/comms/zalo.py:315, 346`)**: `if not self.config.access_token:` did not strip whitespace, allowing whitespace tokens (`"   "`, `"\t\n  "`) to bypass unconfigured guards.
3. **Test Masking (`tests/unit/test_zalo_bot.py`)**: Unit tests only asserted against empty token `""` and `is_mock=True`, failing to assert on whitespace tokens or non-mock token-configured calls.

This blueprint provides exact line-by-line remediation for `Worker M1 Remediation` to eliminate all facade implementations and ghost successes, achieve 100% fail-closed compliance across all comms boundaries, and provide complete test coverage.

---

## 2. Root Cause Analysis & Forensic Breakdown

### Defect 1: Facade Implementation & Ghost Success in `jarvis/comms/zalo.py:349`
- **Location**: `jarvis/comms/zalo.py:344-354`
- **Existing Code**:
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
- **Violation**: `AGENTS.md` Rule 2 and `docs/AUDIT_FRAMEWORK.md` Axis 2 (Truthfulness & Trap 15: Silent Fallback). Line 349 returned `success=True` for an unimplemented operation.
- **Remediation**: In non-mock mode when token is present, return `ZaloSendResult(success=False, error="IMAGE_SEND_NOT_IMPLEMENTED")`.

### Defect 2: Whitespace Token Fail-Closed Bypass
- **Location**: `jarvis/comms/zalo.py:315` (`send_message`) and `jarvis/comms/zalo.py:350` (`send_image`)
- **Existing Code**: `if not self.config.access_token:`
- **Violation**: In Python, `bool("   ") == True`. Whitespace strings evaluate to truthy, bypassing the guard. In `send_image()`, it triggered ghost success at line 349. In `send_message()`, it dispatched an unauthenticated HTTP POST with whitespace credentials instead of immediately failing closed.
- **Remediation**: Sanitize with `token = (self.config.access_token or "").strip()`. If `not token: return ZaloSendResult(success=False, error="NOT_CONFIGURED")`. Use sanitized `token` in request headers. Also sanitize `webhook_secret` in `verify_webhook_signature()`.

### Defect 3: Incomplete Test Coverage in Unit Suite
- **Location**: `tests/unit/test_zalo_bot.py:124-177`
- **Gap**: Tests in `TestFailClosed` only checked `access_token=""` and `is_mock=True`. No tests checked whitespace tokens or non-mock token-provided image calls.
- **Remediation**: Expand `TestFailClosed` with whitespace tests for both `send_message` and `send_image`, and explicit verification of `IMAGE_SEND_NOT_IMPLEMENTED` when token is configured under `is_mock=False`.

---

## 3. Exact Code Changes

### A. Production Code: `jarvis/comms/zalo.py`

#### Change 1: Sanitize `webhook_secret` in `verify_webhook_signature`
**File**: `jarvis/comms/zalo.py`  
**Lines 120–135**:
```python
<<<< ORIGINAL
        if self.is_mock:
            return True
        if not self.config.webhook_secret:
            log.error("Zalo webhook rejection: webhook_secret is not configured.")
            return False
        if not signature:
            return False

        clean_sig = signature.strip()
        try:
            raw_hmac = hmac.new(
                self.config.webhook_secret.encode("utf-8"),
                payload,
                hashlib.sha256,
            )
==== REPLACEMENT
        if self.is_mock:
            return True
        secret = (self.config.webhook_secret or "").strip()
        if not secret:
            log.error("Zalo webhook rejection: webhook_secret is not configured.")
            return False
        if not signature:
            return False

        clean_sig = signature.strip()
        try:
            raw_hmac = hmac.new(
                secret.encode("utf-8"),
                payload,
                hashlib.sha256,
            )
>>>>
```

#### Change 2: Fail-closed whitespace check in `send_message`
**File**: `jarvis/comms/zalo.py`  
**Lines 311–333**:
```python
<<<< ORIGINAL
        if self.is_mock:
            log.info("Mock send to %s: %s", user_id, text[:60])
            return ZaloSendResult(success=True, message_id="mock_msg_id")

        if not self.config.access_token:
            log.warning("Zalo send rejected: access_token not configured")
            return ZaloSendResult(success=False, error="NOT_CONFIGURED")

        try:
            payload = json.dumps({
                "recipient": {"user_id": user_id},
                "message": {"text": text[:2000]},
            }).encode("utf-8")
            req = Request(
                _ZALO_MSG_URL,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "access_token": self.config.access_token,
                },
            )
==== REPLACEMENT
        if self.is_mock:
            log.info("Mock send to %s: %s", user_id, text[:60])
            return ZaloSendResult(success=True, message_id="mock_msg_id")

        token = (self.config.access_token or "").strip()
        if not token:
            log.warning("Zalo send rejected: access_token not configured")
            return ZaloSendResult(success=False, error="NOT_CONFIGURED")

        try:
            payload = json.dumps({
                "recipient": {"user_id": user_id},
                "message": {"text": text[:2000]},
            }).encode("utf-8")
            req = Request(
                _ZALO_MSG_URL,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "access_token": token,
                },
            )
>>>>
```

#### Change 3: Fail-closed whitespace check & eliminate ghost success in `send_image`
**File**: `jarvis/comms/zalo.py`  
**Lines 344–354**:
```python
<<<< ORIGINAL
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
==== REPLACEMENT
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
        log.warning("Zalo send_image rejected: image upload API is not implemented")
        return ZaloSendResult(success=False, error="IMAGE_SEND_NOT_IMPLEMENTED")
>>>>
```

---

### B. Unit Test Suite: `tests/unit/test_zalo_bot.py`

Add the following tests to class `TestFailClosed` in `tests/unit/test_zalo_bot.py`:

```python
    def test_send_message_not_configured_when_token_whitespace(self):
        """send_message() must return NOT_CONFIGURED error when access_token is whitespace."""
        bot = ZaloBotController(config=ZaloConfig(access_token="   \t\n  "), is_mock=False)
        result = bot.send_message("user_123", "Hello JARVIS")
        assert isinstance(result, ZaloSendResult), "Expected ZaloSendResult dataclass"
        assert result.success is False, (
            "FABRICATION: send_message returned success=True on whitespace token"
        )
        assert result.error == "NOT_CONFIGURED", (
            f"Expected error='NOT_CONFIGURED', got: {result.error!r}"
        )

    def test_send_image_not_configured_when_token_whitespace(self):
        """send_image() must return NOT_CONFIGURED error when access_token is whitespace."""
        bot = ZaloBotController(config=ZaloConfig(access_token="   \t\n  "), is_mock=False)
        result = bot.send_image("user_123", "path/to/image.jpg")
        assert isinstance(result, ZaloSendResult), "Expected ZaloSendResult dataclass"
        assert result.success is False, (
            "FABRICATION: send_image returned success=True on whitespace token"
        )
        assert result.error == "NOT_CONFIGURED", (
            f"Expected error='NOT_CONFIGURED', got: {result.error!r}"
        )

    def test_send_image_not_implemented_when_token_provided(self):
        """send_image() must fail-closed with IMAGE_SEND_NOT_IMPLEMENTED when token is configured (no ghost success)."""
        bot = ZaloBotController(config=ZaloConfig(access_token="valid_test_token_123"), is_mock=False)
        result = bot.send_image("user_123", "path/to/image.jpg", caption="Test image")
        assert isinstance(result, ZaloSendResult), "Expected ZaloSendResult dataclass"
        assert result.success is False, (
            "FABRICATION/GHOST SUCCESS: send_image returned success=True without upload implementation"
        )
        assert result.error == "IMAGE_SEND_NOT_IMPLEMENTED", (
            f"Expected error='IMAGE_SEND_NOT_IMPLEMENTED', got: {result.error!r}"
        )

    def test_webhook_secret_whitespace_fails_closed(self):
        """verify_webhook_signature must fail-closed when webhook_secret is only whitespace."""
        bot = ZaloBotController(config=ZaloConfig(webhook_secret="   \t\n "), is_mock=False)
        assert bot.verify_webhook_signature(b"payload", "any_signature") is False
```

---

### C. Adversarial Test Suite: `tests/test_adversarial_beta_m1_comms_failclosed.py`

Add a test case to `TestZaloSendImageFailClosed` in `tests/test_adversarial_beta_m1_comms_failclosed.py`:

```python
    def test_zalo_send_image_configured_token_not_implemented(self):
        """Configured token under is_mock=False must return success=False and error='IMAGE_SEND_NOT_IMPLEMENTED' (no ghost success)."""
        bot = ZaloBotController(config=ZaloConfig(access_token="configured_token_123"), is_mock=False)
        result = bot.send_image(user_id="user_123", image_path="test.png", caption="Test")
        assert isinstance(result, ZaloSendResult)
        assert result.success is False, (
            f"FABRICATION/GHOST SUCCESS: send_image returned success=True on configured token! result={result}"
        )
        assert result.error == "IMAGE_SEND_NOT_IMPLEMENTED", (
            f"Expected error='IMAGE_SEND_NOT_IMPLEMENTED', got: {result.error}"
        )
```

---

### D. Project Documentation: `PROJECT.md`

Update lines 49–52 in `PROJECT.md`:

```markdown
### Zalo OA Fail-Closed Contract (`jarvis/comms/zalo.py`)
- `ZaloBotController.send_message(user_id, text) -> ZaloSendResult`:
  Must strip whitespace `token = (self.config.access_token or "").strip()` and return `ZaloSendResult(success=False, error="NOT_CONFIGURED")` when missing or whitespace-only.
- `ZaloBotController.send_image(user_id, image_path, caption) -> ZaloSendResult`:
  Must strip whitespace `token = (self.config.access_token or "").strip()` and return `ZaloSendResult(success=False, error="NOT_CONFIGURED")` when missing or whitespace-only. When configured but OA image API is not implemented, must return `ZaloSendResult(success=False, error="IMAGE_SEND_NOT_IMPLEMENTED")` (never ghost `success=True`).
```

---

## 4. Verification Protocol

The Worker agent must execute the following commands in order and verify 100% pass:

### Command 1: Pytest Unit Tests
```powershell
pytest tests/unit/test_voice_pipeline_fixes.py tests/unit/test_zalo_bot.py -v
```
**Expected Output**: 33 passed (8 voice pipeline + 25 Zalo unit tests), 0 failures.

### Command 2: Pytest Adversarial Fail-Closed Tests
```powershell
pytest tests/test_adversarial_beta_m1_comms_failclosed.py -v
```
**Expected Output**: 18 passed (all 6 Zalo tests + 5 Comms tests + 5 Hardware tests + 2 helper tests), 0 failures.

### Command 3: Direct Runtime Verification One-Liners

**Probe A: Whitespace token handling**:
```powershell
python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; b = ZaloBotController(config=ZaloConfig(access_token='   '), is_mock=False); r = b.send_image('u1', 'img.png'); assert r.success is False and r.error == 'NOT_CONFIGURED', f'Failed: {r}'; print('Whitespace Probe: PASS')"
```

**Probe B: Configured token non-implemented handling**:
```powershell
python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; b = ZaloBotController(config=ZaloConfig(access_token='token123'), is_mock=False); r = b.send_image('u1', 'img.png'); assert r.success is False and r.error == 'IMAGE_SEND_NOT_IMPLEMENTED', f'Failed: {r}'; print('Configured Probe: PASS')"
```

**Probe C: Mock mode preservation**:
```powershell
python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; b = ZaloBotController(config=ZaloConfig(), is_mock=True); r = b.send_image('u1', 'img.png'); assert r.success is True and r.message_id == 'mock_img_id', f'Failed: {r}'; print('Mock Probe: PASS')"
```

---

## 5. Invalidation Conditions

The remediation is considered **INVALID** if any of the following occur:
1. `send_image()` returns `success=True` when `is_mock=False` under any token state (empty, whitespace, or non-empty string).
2. `send_message()` attempts an HTTP call when `access_token` contains only whitespace characters.
3. Any unit test or adversarial test fails in the test suite.
