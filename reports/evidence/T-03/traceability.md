# Traceability Matrix

- Requirement: Implement Bot API transport thật.
  - Code path: `jarvis/comms/telegram.py` (uses `requests`)
  - Test case: `test_telegram_send_message_missing_token`
  - Evidence: `test-results.txt`

- Requirement: Missing token -> NOT_CONFIGURED.
  - Code path: `jarvis/comms/telegram.py:send_message`
  - Test case: `test_telegram_send_message_missing_token`
  - Evidence: `negative-tests.txt`

- Requirement: NotificationHub kiểm tra kết quả.
  - Code path: `jarvis/workers/notification_hub.py`
  - Test case: Manual code inspection (implemented).

- Requirement: Whitelist user/chat enforce.
  - Code path: `jarvis/comms/telegram.py:is_user_authorized`
  - Test case: `test_telegram_unauthorized_user`
