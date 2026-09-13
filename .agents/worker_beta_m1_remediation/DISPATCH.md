## 2026-09-13T10:58:13Z
You are Worker M1 Remediation for the JARVIS Beta v1 project.

Your working directory is: d:\Software GitCode\JARVIS\.agents\worker_beta_m1_remediation
Your parent is: fcbdbddb-159a-4432-af21-f3ef3e4e8c4e (Project Orchestrator)

Authoritative User Request: d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md (You MUST read this file first).
Scope Document: d:\Software GitCode\JARVIS\PROJECT.md
Remediation Blueprint: d:\Software GitCode\JARVIS\.agents\explorer_beta_m1_remediation\remediation_blueprint.md (Follow this blueprint exactly).

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Write Ownership:
- d:\Software GitCode\JARVIS\jarvis\comms\zalo.py
- d:\Software GitCode\JARVIS\tests\unit\test_zalo_bot.py
- d:\Software GitCode\JARVIS\tests\test_adversarial_beta_m1_comms_failclosed.py

Objectives:
1. Apply the exact code changes specified in `remediation_blueprint.md` to `jarvis/comms/zalo.py`:
   - `verify_webhook_signature`: Strip whitespace from `webhook_secret`:
     `secret = (self.config.webhook_secret or "").strip()`
     `if not secret: return False`
   - `send_message`: Strip whitespace from `access_token`:
     `token = (self.config.access_token or "").strip()`
     `if not token: return ZaloSendResult(success=False, error="NOT_CONFIGURED")`
     and use `token` in the authorization header.
   - `send_image`:
     * If `self.is_mock`: return `ZaloSendResult(success=True, message_id="mock_img_id")`.
     * `token = (self.config.access_token or "").strip()`
     * `if not token:` return `ZaloSendResult(success=False, error="NOT_CONFIGURED")`
     * When token is present but image upload API is not implemented:
       `log.warning("Zalo send_image rejected: image upload API is not implemented")`
       `return ZaloSendResult(success=False, error="IMAGE_SEND_NOT_IMPLEMENTED")`
       (Eliminating ghost success and facade `success=True`).

2. Update `tests/unit/test_zalo_bot.py` and `tests/test_adversarial_beta_m1_comms_failclosed.py`:
   - Add tests verifying whitespace tokens (`"   "`, `"\t\n  "`) return `success=False, error="NOT_CONFIGURED"`.
   - Add test verifying that calling `send_image()` with a token under `is_mock=False` returns `success=False, error="IMAGE_SEND_NOT_IMPLEMENTED"`.

3. Verify:
   - Run: `pytest tests/unit/test_zalo_bot.py tests/test_adversarial_beta_m1_comms_failclosed.py tests/unit/test_voice_pipeline_fixes.py tests/test_comms_hub.py -v`
   - All tests must pass 100% with zero failures.

4. Output:
   - Write handoff report with test logs to `d:\Software GitCode\JARVIS\.agents\worker_beta_m1_remediation\handoff.md`.
   - Send completion message to parent.
