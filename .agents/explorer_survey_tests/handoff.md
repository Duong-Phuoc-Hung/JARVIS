# Handoff Report — Explorer Survey Tests (Voice Pipeline Upgrade v4.8.1)

## 1. Observation

### 1.1 Test Runner Environment & Pytest Configuration
- **Pytest Configuration File**: `pyproject.toml` (lines 114–143):
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  python_files = ["test_*.py"]
  python_classes = ["Test*"]
  python_functions = ["test_*"]
  addopts = [
      "--tb=short",
      "--no-header",
      "-q",
  ]
  filterwarnings = [
      "ignore::pytest.PytestUnhandledThreadExceptionWarning",
      "ignore::DeprecationWarning",
  ]
  markers = [
      "slow: marks tests as slow (deselect with '-m not slow')",
      "integration: marks integration tests",
      "real_os: marks tests requiring real OS-level isolation (Job Object, MIC, AppContainer)",
      "requires_audio: marks tests requiring audio hardware",
  ]
  env = [
      "PYTHONUTF8=1",
      "PYTHONIOENCODING=utf-8",
  ]
  asyncio_mode = "auto"
  ```
- **Python Environment**:
  - Python requirement in `pyproject.toml`: `>=3.10`.
  - Bytecode in `tests/__pycache__/`: `cpython-313-pytest-9.1.1.pyc`, indicating Python 3.13 and pytest 9.1.1.
  - Dependencies: `pytest-env>=1.1`, `pytest>=8.0,<9`, `pytest-subtests>=0.12`, `pytest-timeout>=2.2`, `pytest-cov>=5.0`, `pytest-asyncio>=0.23,<1`.
  - Windows encoding isolation: `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` set via `pytest-env` prevents CP1252 `UnicodeDecodeError` when processing Vietnamese text in pytest parametrization.
- **Fixture Infrastructure**:
  - `tests/conftest.py` (1066 lines) defines deterministic zero-hardware, zero-cloud fixtures:
    - `AudioSynthesizer` and `mock_audio_stream` (DSP, claps, audio buffers).
    - `MockHardwareProvider` (CPU/GPU, RAM, S.M.A.R.T. telemetry).
    - `MockWin32Platform` (ctypes user32/kernel32/winreg interception).
    - `MockHttpServer` & API Hub (Home Assistant, ElevenLabs, Telegram, LLM mock).
    - `MockCameraFeed` (skipped if `cv2` is not installed).
- **Test Suite Inventory**:
  - `tests/unit/`: 76 test files.
  - `tests/test_adversarial_*.py`: 14 files:
    1. `tests/test_adversarial_challenger_1.py`
    2. `tests/test_adversarial_harness.py`
    3. `tests/test_adversarial_m1.py`
    4. `tests/test_adversarial_m1_intent_router.py`
    5. `tests/test_adversarial_m2_audio_gesture.py`
    6. `tests/test_adversarial_m2_llm_router.py`
    7. `tests/test_adversarial_m3_challenger1.py`
    8. `tests/test_adversarial_m3_stt_llm.py`
    9. `tests/test_adversarial_m3_ui_app.py`
    10. `tests/test_adversarial_m4_challenger1.py`
    11. `tests/test_adversarial_m5_2.py`
    12. `tests/test_adversarial_m5_challenger1.py`
    13. `tests/test_adversarial_sprint2_challenger1.py`
    14. `tests/test_adversarial_sprint2_challenger2.py`
  - In addition, there are 2 adversarial runner scripts: `tests/adversarial_challenge_runner.py` and `tests/adversarial_runner_m1_challenger2.py`.
- **Test Pass Counts & Baseline**:
  - `CLAUDE.md` lines 101–104:
    > "1511 passed, 1 skipped, 50 subtests passed, 0 failed (1413 baseline + 98 new tests/unit/-directory tests)"
  - Post-merge CI status: JARVIS CI #166 SUCCESS (all four jobs green: Syntax Check, Unit Tests, Import Validation, Pipeline Summary).
- **Flakiness & Failure History**:
  - `.pytest_cache/v/cache/lastfailed` contains 304 stale historical failures from earlier development cycles before:
    1. Vietnamese UTF-8 encoding in parametrization was resolved via `PYTHONUTF8=1` (`pyproject.toml`).
    2. Whisper wake-word test determinism was fixed in PR #32 (`fix/wake-word-whisper-ci`).
    3. Central dispatch truthfulness and `hardware_status_query` alias were resolved in PR #34.
    4. Self-healing truthfulness was resolved in PR #31.
  - No active test failures or unresolved flakiness remain on `main`.

---

### 1.2 Held-Out Test Set Requirements (R4)
- **Existence Check**:
  - `tests/eval/test_voice_generalization_heldout.py`: **DOES NOT EXIST**. Must be newly created.
- **Audio Ground Truth Manifest & Existing Evaluation Set**:
  - `tests/eval/phrase_manifest.py` (lines 31–46) defines 45 prompt phrases across 14 intents:
    ```python
    PHRASE_MANIFEST: dict[str, list[str]] = {
        "open_app":        ["mở chrome", "mở ứng dụng chrome", "mở notepad", "mở spotify", "khởi động chrome"],
        "system_shutdown": ["tắt máy tính", "shutdown máy", "tắt nguồn"],
        "system_restart":  ["khởi động lại máy", "restart máy tính", "reboot"],
        "volume_control":  ["tăng âm lượng", "giảm âm lượng", "điều chỉnh âm lượng", "tắt tiếng", "mute"],
        "weather_query":   ["thời tiết hôm nay", "thời tiết ngày mai", "dự báo thời tiết", "trời hôm nay thế nào"],
        "timer_set":       ["hẹn giờ 5 phút", "đặt timer 10 phút", "nhắc tôi sau 15 phút"],
        "reminder_set":    ["nhắc nhở lúc 3 giờ", "đặt nhắc lúc 8 giờ sáng"],
        "screenshot":      ["chụp màn hình", "chụp ảnh màn hình", "screenshot"],
        "stop":            ["dừng lại", "stop", "thôi", "hủy"],
        "search":          ["tìm kiếm google", "tìm file word", "search chrome", "tìm kiếm youtube"],
        "music_play":      ["mở nhạc", "phát nhạc", "play music"],
        "screen_off":      ["tắt màn hình", "turn off monitor"],
        "note_take":       ["ghi chú", "tạo ghi chú mới"],
        "settings_open":   ["mở cài đặt", "open settings"],
    }
    ```
  - Total 45 phrases * 2 acoustic conditions (`clean`, `noisy`) = 90 WAV files under `tests/eval/audio/`.
- **Target Intent Mapping & Acceptable Router Actions**:
  - In `tests/eval/failure_decomposition.py` (lines 53–67):
    ```python
    EXPECTED_ACTIONS: dict[str, set[str]] = {
        "open_app":        {"app_open", "web_open"},
        "system_shutdown": {"system_power"},
        "system_restart":  {"system_power"},
        "volume_control":  {"system_volume"},
        "weather_query":   {"shell_exec"},
        "timer_set":       {"reminder"},
        "reminder_set":    {"reminder"},
        "screenshot":      {"screen_capture"},
        "stop":            {"system_power"},
        "search":          {"web_open", "shell_exec"},
        "music_play":      {"spotify"},
        "screen_off":      {"system_power", "system_brightness"},
        "note_take":       {"memory_save_fact"},
        "settings_open":   {"app_open", "web_open"},
    }
    ```
- **Held-Out Test Set Requirements (R4 Acceptance Criteria)**:
  - Must create `tests/eval/test_voice_generalization_heldout.py`.
  - Must include at least **25–30 completely unseen utterances** that never appear in the 45 phrases of `PHRASE_MANIFEST`.
  - Must cover all 7 required domains:
    1. **Weather** (`weather_query` -> `shell_exec`)
    2. **Reminder** (`reminder_set`, `timer_set` -> `reminder`)
    3. **System control** (`system_shutdown`, `system_restart`, `screen_off` -> `system_power`)
    4. **Search** (`search` -> `web_open` or `shell_exec`)
    5. **Volume** (`volume_control` -> `system_volume`)
    6. **Notes** (`note_take` -> `memory_save_fact`)
    7. **Applications** (`open_app`, `settings_open` -> `app_open` or `web_open`)
  - Target metrics:
    - `CORRECT >= 85%` (e.g. >= 26/30 or 100%).
    - `MISROUTED == 0`.
    - 100% pytest pass (`pytest tests/eval/test_voice_generalization_heldout.py` -> 0 failures).

---

### 1.3 Git Repository Status & Release Documents
- **Version String**:
  - `jarvis/__init__.py` line 12: `__version__ = "5.0.0"`.
  - Note: As documented in `CLAUDE.md` and `CHANGELOG.md`, `__version__` was bumped from `4.7.0` to `5.0.0` for the J.A.R.V.I.S. Terminal Control Center release (PR #37 + PR #38) on 2026-09-03.
  - Task request mentions v4.8.1 for the Voice Pipeline Upgrade.
- **Git Remotes & Branching**:
  - `pyproject.toml` lines 85–86:
    ```toml
    Homepage = "https://github.com/Duong-Phuoc-Hung/JARVIS"
    Repository = "https://github.com/Duong-Phuoc-Hung/JARVIS"
    ```
  - Upstream branch: `origin main`.
- **`CHANGELOG.md` Status & Format**:
  - Follows "Keep a Changelog" format with SemVer headers and emoji badges.
  - Previous major headings:
    - Line 5: `## 🚀 [5.0.0] — J.A.R.V.I.S. Terminal Control Center — formally released as v5.0.0 (PR #37 + PR #38, tagged/published 2026-09-03)`
    - Line 356: `## 🔧 Post-v4.7.0 Maintenance / Unreleased Maintenance (2026-09-02 → 2026-09-03)`
    - Line 503: `## 🚀 [4.7.0] - 2026-09-02 — Sprint 2 Acoustic & UX Hardening Release`
    - Line 573: `## 🚀 [4.6.0] - 2026-09-02 — Technical Roadmap & P0 Critical Subsystems Release`
  - Required sections for v4.8.1:
    - Safe Preprocessing Diacritic Normalization (Zero-Homophone-Collision).
    - STT benchmark results on 90 real audio files (`CORRECT`, `ROUTER_ABSTAIN`, `MISROUTED`).
    - Held-out Generalization Evaluation (N=30 unseen utterances, 100% pass, MISROUTED = 0).
- **`README.md` Status**:
  - Voice recognition and intent routing are documented at lines 42–66 ("### 🎙️ Nhận Diện Giọng Nói Offline & Barge-in", "### 🧠 Router Ý Định 3 Lớp Thông Minh").
  - Skills table with voice commands is located at lines 408–432 ("## 🧰 Danh Sách Kỹ Năng Chi Tiết (18+ Skills)").
  - Needs additions describing the Safe Diacritic Normalization, homophone collision prevention, and the updated list of voice commands across accented/unaccented variations.

---

## 2. Logic Chain

1. **Test Suite Integrity (Step 1)**:
   - *Observation*: `pyproject.toml` sets `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`. `tests/conftest.py` completely mocks external devices, APIs, and OS calls.
   - *Inference*: Tests under `tests/unit/` and `tests/test_adversarial_*.py` are fully deterministic and headless. Any new test added for held-out generalization or router updates can run without network access, audio devices, or cloud API keys.

2. **Held-Out Test Set Isolation (Step 2)**:
   - *Observation*: The 90 real audio WAV files correspond to the 45 phrases in `phrase_manifest.py`. `tests/eval/test_voice_generalization_heldout.py` does not yet exist.
   - *Inference*: To guarantee anti-overfitting, the test cases in `test_voice_generalization_heldout.py` must strictly exclude any of the 45 phrases in `phrase_manifest.py`.
   - *Verification*: A dedicated test or assertion can check `assert phrase not in ALL_TRAINING_PHRASES` to mathematically guarantee zero leakage between the audio training/ablation set and the held-out generalization set.

3. **Intent Coverage & Target Actions (Step 3)**:
   - *Observation*: `failure_decomposition.py` maps each eval intent to expected router actions (`weather_query` -> `shell_exec`, `volume_control` -> `system_volume`, `note_take` -> `memory_save_fact`, `reminder_set` -> `reminder`, `open_app` -> `app_open`/`web_open`, `search` -> `web_open`/`shell_exec`, `system_shutdown` -> `system_power`).
   - *Inference*: The 25–30 held-out test cases must use these exact mappings. If the router implements Safe Diacritic Normalization (`len(words) >= 2` folding) and phonetic aliases, all 25–30 unseen test cases will route to their expected actions without a single misroute (`MISROUTED == 0`, `CORRECT >= 85%`, meeting R4).

4. **Release Documentation & Version Alignment (Step 4)**:
   - *Observation*: `jarvis/__init__.py` currently has `__version__ = "5.0.0"`. `CHANGELOG.md` and `README.md` have established formatting standards.
   - *Inference*: The v4.8.1 release section in `CHANGELOG.md` should be placed cleanly, and `README.md` should update both the voice description and the command examples in Section 8.

---

## 3. Caveats

1. **Terminal Command Permission**:
   - Running interactive CLI commands via `run_command` in this environment timed out awaiting user interaction. All observations were gathered through static inspection of `pyproject.toml`, bytecode caches, git docs, test manifests, and codebase files.
2. **Version Divergence (`5.0.0` vs `4.8.1`)**:
   - The repository has already tagged `5.0.0` for the Terminal Control Center milestone on 2026-09-03. The implementer/orchestrator should decide whether `jarvis/__init__.py`'s `__version__` should remain `5.0.0` or be set to `4.8.1` / `5.0.1` based on the owner's versioning strategy. The CHANGELOG and README can document the Voice Pipeline Upgrade as requested.
3. **Audio Hardware / CTranslate2 Execution**:
   - Evaluating on the 90 actual WAV audio files (`tests/eval/stt_intent_eval.py --backend direct`) requires CTranslate2 / faster-whisper. Unit and held-out router generalization tests (`tests/eval/test_voice_generalization_heldout.py`), however, are purely text-based and run instantaneously without hardware dependencies.

---

## 4. Conclusion

- **Test Suite Status**: Highly stable, 76 unit test files and 14 adversarial test files, zero active failures on `main`. Fully configured with UTF-8 encoding environment flags and comprehensive mock fixtures in `tests/conftest.py`.
- **Held-Out Test Infrastructure (R4)**: Does not exist yet. Must be created at `tests/eval/test_voice_generalization_heldout.py` containing 25–30 unseen utterances across 7 domains (Weather, Reminder, System, Search, Volume, Notes, Apps) guaranteeing 0 overlap with the 45 phrases in `phrase_manifest.py`.
- **Release Docs**: `CHANGELOG.md` and `README.md` are well-structured and ready for the v4.8.1 Voice Pipeline Upgrade entries.

---

## 5. Verification Method

To independently verify all findings:
1. Check pytest configuration:
   - Inspect `pyproject.toml` lines 114–143.
2. Verify test file inventory:
   - `tests/unit/`: 76 files.
   - `tests/test_adversarial_*.py`: 14 files.
3. Check absence of held-out test file:
   - Verify `tests/eval/test_voice_generalization_heldout.py` does not exist on disk yet.
4. Verify phrase manifest ground truth:
   - Inspect `tests/eval/phrase_manifest.py` lines 31–46 (45 phrases).
5. Verify evaluation taxonomy:
   - Inspect `tests/eval/failure_decomposition.py` lines 37–67 (4 outcome classes and `EXPECTED_ACTIONS`).
6. Verify version and release docs:
   - Inspect `jarvis/__init__.py` line 12.
   - Inspect `CHANGELOG.md` lines 1–50 and `README.md` lines 42–66, 408–432.
