# Task T-03: Telegram real transport

Implementation of Telegram real transport directly using `requests` without relying on injected `mock_http`.

Status: PARTIALLY DONE (Blocked for live certification due to missing credentials).

Completed requirements:
- Implemented real Bot API transport for `send_message`, `send_photo`, `getUpdates`.
- Fails closed safely if credentials missing or network fails.
- NotificationHub now checks `tg.send_message` result properly.
- Rate limits handled and retry_after processed.
- Enforced whitelist matching user requirements.
