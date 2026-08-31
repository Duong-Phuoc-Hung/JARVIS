# Dead Ends Log

| Iteration | Approach Tried | Why It Failed | Files Touched |
|-----------|---------------|---------------|---------------|
| 1 | Top-level globals purge loop deleting `_written`, `_MAX`, `_original`, `_capped` in sandbox preamble | `_capped_stdout_write` still relied on those globals, causing immediate `NameError` crash upon `sys.stdout.write` | `jarvis/sandbox/security.py` |
| 1 | Blocking `_winapi` in `_BLOCKED_SANDBOX_MODULES` | Windows Python 3.13 standard library `ntpath.abspath` imports `_winapi` during normal path normalization, breaking sandbox initialization | `jarvis/sandbox/security.py` |
| 1 | Fallback in-test assertion when `docs/night_shift_audit.md` is absent | Test facade violated integrity; the document must exist on disk | `tests/e2e/test_r2_night_shift_e2e.py` |
| 1 | Returning `SanitizationResult` object without string interface from `PromptGuard.sanitize()` | Violated interface contract in `PROJECT.md`, breaking downstream string consumers and E2E tests | `jarvis/security/prompt_guard.py` |
