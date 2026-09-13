# Technical Survey & Backlog Audit: Voice Pipeline (H-01 to H-13)
**Project**: JARVIS Beta v1 Voice Pipeline & Core Integration  
**Date**: 2026-09-13  
**Explorer**: Voice Pipeline Explorer (`explorer_beta_survey_1`)  
**Parent Orchestrator**: `fcbdbddb-159a-4432-af21-f3ef3e4e8c4e`  
**Working Directory**: `d:\Software GitCode\JARVIS\.agents\explorer_beta_survey_1`  

---

## 1. Executive Summary

An exhaustive audit of the JARVIS Voice Pipeline was conducted against the requirements established in `ORIGINAL_REQUEST.md` (2026-09-13T10:25:05Z), focusing on:
1. **R1: Audio Capture & Hardware Synchronization** (H-01, H-02, H-03)
2. **R2: Core Controls & Hardware Fail-Closed Semantics** (H-04, H-08)
3. **Complete Backlog Audit of Tasks H-01 through H-13**

### Overall Assessment
- **Unit Test Suite**: `tests/unit/test_voice_pipeline_fixes.py` passes **100% (6/6 tests)** in 1.63s.
- **Wider Voice Test Suite**: Across 8 test modules comprising 88 unit and integration tests (`test_voice_pipeline_fixes.py`, `test_app_web_dedupe_stress.py`, `test_hotkeys.py`, `test_tiered_stt.py`, `test_stt_preload.py`, `test_acoustic_hardening.py`, `test_tts_com_safety.py`, `test_voice_generalization_heldout.py`), the suite passes **100% (88/88 tests)** in 4.74s.
- **Acoustic & Wake Word Suites**: `tests/unit/test_wake_word.py`, `test_wake_word_p0.py`, `test_wake_word_real_audio_e8.py` pass **100% (76/76 tests)** in 7.68s.
- **Critical Architectural Finding (H-01 Config Precedence Gap)**:
  While commit `637fc76` implemented `sr = int(sample_rate or self.config.get("audio.sample_rate", 16000))` in `jarvis/core/app.py:1738`, `config/default_config.yaml:31` explicitly defines `audio: sample_rate: 44100`. In real production runs where `self.config.load()` executes, `self.config.get("audio.sample_rate")` evaluates to `44100`. As a result, the default parameter `16000` is **never reached in production runtime**, and `record_audio()` continues to capture at 44100 Hz unless decoupled. This is an active latent defect directly contributing to STT distortion.

---

## 2. Deep Dive: R1 — Audio Capture & Hardware Synchronization

### 2.1 H-01: 16 kHz Direct Capture for Whisper
- **Target File**: `jarvis/core/app.py:1727-1804`
- **Objective**: Ensure microphone audio for STT models (Whisper) is captured natively at 16000 Hz, eliminating 44.1kHz/48kHz linear interpolation artifacts and latency.
- **Source Inspection (`jarvis/core/app.py:1735-1742`)**:
  ```python
  # H-01 fix: Whisper requires 16kHz input. Record at 16000 Hz directly to
  # avoid the silent 44100→16000 resample mismatch that caused ROUTER_ABSTAIN.
  # (audio_to_float32 does NOT resample np.ndarray input — it returns as-is.)
  sr = int(sample_rate or self.config.get("audio.sample_rate", 16000))
  max_dur = float(duration_s or self.config.get("stt.timeout_s", 4.0))

  if self.headless:
      return np.zeros(int(sr * min(max_dur, 0.1)), dtype=np.float32)
  ```
- **Stream Invocations**:
  - `with _sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=chunk_size, device=target_device) as stream:` (line 1774)
  - Fallback: `audio_data = _sd.rec(int(dur * sr), samplerate=sr, channels=1, dtype="float32", device=target_device)` (line 1799)
- **Unit Test**: `test_h01_record_audio_default_16khz` in `tests/unit/test_voice_pipeline_fixes.py`:
  - Passes because `mock_app` fixture defines `app.config = {"audio.sample_rate": 16000, ...}`.
- **Latent Defect / Production Vulnerability**:
  - In `config/default_config.yaml:31`:
    ```yaml
    audio:
      sample_rate: 44100          # 44.1 kHz
    ```
  - Verification on genuine initialized `JarvisApp`:
    ```powershell
    python -c "from jarvis.core.app import JarvisApp; app = JarvisApp(headless=True); app.initialize(); print('App audio.sample_rate:', app.config.get('audio.sample_rate'))"
    # Output: App audio.sample_rate: 44100
    python -c "from jarvis.core.app import JarvisApp; app = JarvisApp(headless=True); app.initialize(); arr = app.record_audio(duration_s=1.0); print('Length:', len(arr), 'Expected at 16k:', 1600)"
    # Output: Length: 4410 Expected at 16k: 1600 (4410 samples in 0.1s headless = 44100 Hz!)
    ```
- **Root Cause**: `self.config.get("audio.sample_rate", 16000)` reads the general audio config (intended for audio playback / AudioEngine) instead of dedicated STT input rate. Because `"audio.sample_rate"` exists in default configuration, default argument `16000` is bypassed.
- **Recommended Remediation**:
  In `jarvis/core/app.py:1738`:
  ```python
  # Decouple STT capture rate: Whisper strictly requires 16 kHz.
  sr = int(sample_rate or self.config.get("stt.sample_rate", 16000))
  ```
  Or override `sample_rate = sample_rate or 16000` for `record_audio()` to enforce 16 kHz by default regardless of general audio engine settings.

---

### 2.2 H-02: Microphone Device Synchronization
- **Target File**: `jarvis/core/app.py:1744-1756, 1774, 1799`
- **Objective**: Synchronize `record_audio()` with the active device index selected and probed by `AudioEngine`, guaranteeing wake-word detection and voice recording operate on the identical physical audio endpoint.
- **Source Inspection (`jarvis/core/app.py:1744-1756`)**:
  ```python
  # H-02 fix: Synchronize recording device with AudioEngine's selected active device
  # so wake-word detector and command capture always listen on the exact same microphone.
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
- **AudioEngine Seam Verification**:
  - `jarvis/audio/engine.py:262`: `self._active_device_index: int | None = None`
  - `jarvis/audio/engine.py:360`: Sets `self._active_device_index = self.probe_manager.select_best_device(...)`
  - `jarvis/audio/engine.py:387`: Passes `device_index=self._active_device_index` to PyAudio stream
- **Stream Invocations**:
  - Both `_sd.InputStream(..., device=target_device)` and `_sd.rec(..., device=target_device)` pass `device=target_device`.
- **Unit Test**: `test_h02_record_audio_uses_audio_engine_device` in `tests/unit/test_voice_pipeline_fixes.py` (PASS).
- **Verdict**: 🟢 **VERIFIED & COMPLIANT**.

---

### 2.3 H-03: Acoustic Echo & Self-Contamination Suppression
- **Target File**: `jarvis/core/app.py:1757-1763, 1814-1818, 1829-1831`
- **Objective**: Prevent the microphone from capturing synthesized JARVIS TTS audio (room echo/reverberation) by enforcing active playback lockout, settling delays, and single-flight execution.
- **Source Inspection**:
  1. **Defense Layer 1 (Continuous Audio Block Dispatch Gate)** — `jarvis/core/app.py:404-412`:
     ```python
     if self.tts_manager and self.tts_manager.is_in_echo_window(current_time=now, cooldown_s=2.5):
         if self.wake_word_detector:
             try:
                 self.wake_word_detector.suppress_until(now + 0.1)
             except Exception:
                 pass
         return  # Drop raw microphone frame
     ```
  2. **Defense Layer 2 (Active Playback Lockout in `record_audio()`)** — `jarvis/core/app.py:1757-1763`:
     ```python
     # H-03 fix: Acoustic Echo Guard — if TTS is still actively playing through speakers,
     # wait briefly for it to complete to prevent capturing self-audio into STT.
     if self.tts_manager and getattr(self.tts_manager, "is_playing", False):
         t_wait_start = time.monotonic()
         while getattr(self.tts_manager, "is_playing", False) and (time.monotonic() - t_wait_start) < 1.0:
             time.sleep(0.05)
     ```
  3. **Defense Layer 3 (Post-TTS Acoustic Settling Delay)** — `jarvis/core/app.py:1829-1831`:
     ```python
     if self.tts_manager and greeting_phrase:
         self.tts_manager.speak(greeting_phrase, wait=True)
         # H-03: Acoustic settling delay — allow 150ms for speaker reverberation to decay
         time.sleep(0.15)
     ```
  4. **Defense Layer 4 (Single-Flight Execution Lock)** — `jarvis/core/app.py:1814-1818`:
     ```python
     with self._voice_lock:
         if self._is_voice_interacting:
             log.debug("Voice interaction already in progress. Suppressing trigger [%s].", trigger_name)
             return
         self._is_voice_interacting = True
     ```
- **Unit Tests**:
  - `test_h03_record_audio_waits_for_active_tts` (PASS)
  - `test_tts_manager_is_in_echo_window` in `test_acoustic_hardening.py` (PASS)
  - `test_tts_manager_echo_window_lifecycle_during_and_after_playback` in `test_tts_com_safety.py` (PASS)
- **Verdict**: 🟢 **VERIFIED & COMPLIANT**.

---

## 3. Deep Dive: R2 — Core Controls & Hardware Fail-Closed Semantics

### 3.1 H-04: Zero-Crash Hotkeys (Ctrl+Shift+L PTT)
- **Target File**: `jarvis/core/app.py:585-593, 608`
- **Objective**: Ensure system-wide push-to-talk hotkey `Ctrl+Shift+L` triggers voice interaction without throwing `AttributeError`.
- **Source Inspection (`jarvis/core/app.py:585-593`)**:
  ```python
  def _ptt_voice_cb():
      # H-04 fix: _handle_voice_command did not exist → delegate to _start_voice_interaction.
      # PTT hotkey uses shorter greeting to minimize delay before recording starts.
      threading.Thread(
          target=self._start_voice_interaction,
          kwargs={"trigger_name": "HOTKEY_PTT", "greeting_phrase": "Vâng, tôi nghe."},
          daemon=True,
      ).start()

  self.hotkey_manager.register("Ctrl+Shift+L", _ptt_voice_cb, "Ghi âm lệnh giọng nói tức thì (PTT)")
  ```
- **Method Signature Match**:
  `jarvis/core/app.py:1805`:
  ```python
  def _start_voice_interaction(
      self,
      greeting_phrase: str = "Vâng thưa Ngài, tôi đang lắng nghe.",
      trigger_name: str = "VOICE",
  ) -> None:
  ```
- **Unit Tests**:
  - `test_h04_hotkey_registration_has_valid_target` in `tests/unit/test_voice_pipeline_fixes.py` (PASS)
  - `tests/unit/test_hotkeys.py` (8/8 PASS in 0.95s)
- **Verdict**: 🟢 **VERIFIED & COMPLIANT**.

---

### 3.2 H-08: Honest Hardware Status (Volume & Brightness Fail-Closed)
- **Target File**: `jarvis/core/app.py:1297-1326`
- **Objective**: When hardware controller methods return `None` (headless, missing display DDC/CI, pycaw COM error), handlers must return `success: False`, `status: failed`, and explicit error codes (`VOLUME_SET_FAILED`, `BRIGHTNESS_SET_FAILED`), never ghost successes.
- **Source Inspection**:
  - Master Volume (`jarvis/core/app.py:1297-1310`):
    ```python
    def _handle_system_volume(self, delta: int | None = None, level: int | None = None, **kwargs) -> dict[str, Any]:
        """Adjusts or sets master audio volume (fail-closed if endpoint unavailable)."""
        if self.computer_controller:
            if level is not None:
                vol = self.computer_controller.set_volume(level)
                if vol is None:
                    return {"status": "failed", "success": False, "volume": None, "error": "VOLUME_SET_FAILED", "message": "Không thể đặt âm lượng phần cứng, thưa Ngài."}
                return {"status": "success", "success": True, "volume": vol, "message": f"Đã đặt âm lượng hệ thống thành {vol}%, thưa Ngài."}
            delta_val = delta if delta is not None else 10
            vol = self.computer_controller.change_volume(delta_val)
            if vol is None:
                return {"status": "failed", "success": False, "volume": None, "error": "VOLUME_CHANGE_FAILED", "message": "Không thể điều chỉnh âm lượng phần cứng, thưa Ngài."}
            return {"status": "success", "success": True, "volume": vol, "message": f"Đã điều chỉnh âm lượng lên {vol}%, thưa Ngài."}
        return {"status": "failed", "success": False, "message": "Computer controller unavailable"}
    ```
  - Display Brightness (`jarvis/core/app.py:1312-1325`):
    ```python
    def _handle_system_brightness(self, delta: int | None = None, level: int | None = None, **kwargs) -> dict[str, Any]:
        """Adjusts or sets screen brightness (fail-closed if monitor unavailable)."""
        if self.computer_controller:
            if level is not None:
                b = self.computer_controller.set_brightness(level)
                if b is None:
                    return {"status": "failed", "success": False, "brightness": None, "error": "BRIGHTNESS_SET_FAILED", "message": "Không thể đặt độ sáng màn hình, thưa Ngài."}
                return {"status": "success", "success": True, "brightness": b, "message": f"Đã đặt độ sáng màn hình thành {b}%, thưa Ngài."}
            delta_val = delta if delta is not None else 10
            b = self.computer_controller.change_brightness(delta_val)
            if b is None:
                return {"status": "failed", "success": False, "brightness": None, "error": "BRIGHTNESS_CHANGE_FAILED", "message": "Không thể điều chỉnh độ sáng màn hình, thưa Ngài."}
            return {"status": "success", "success": True, "brightness": b, "message": f"Đã điều chỉnh độ sáng màn hình thành {b}%, thưa Ngài."}
        return {"status": "failed", "success": False, "message": "Computer controller unavailable"}
    ```
- **Unit Tests**:
  - `test_h08_volume_fail_closed_on_none` in `tests/unit/test_voice_pipeline_fixes.py` (PASS)
  - `test_h08_brightness_fail_closed_on_none` in `tests/unit/test_voice_pipeline_fixes.py` (PASS)
- **Verdict**: 🟢 **VERIFIED & COMPLIANT**.

---

## 4. Complete Backlog Audit: Voice Pipeline Tasks H-01 through H-13

The complete Voice Pipeline backlog comprises 13 architectural tasks covering capture, acoustic pre-filtering, STT inference, intent normalization, hardware controls, and speech synthesis:

| Task ID | Component & Description | Primary Files | Existing Tests | Status | Truthfulness / Fail-Closed |
|---|---|---|---|---|---|
| **H-01** | 16 kHz Direct Capture for Whisper | `jarvis/core/app.py:1735` | `tests/unit/test_voice_pipeline_fixes.py` | 🟡 Config Gap | Defect: `default_config.yaml` overrides fallback to 44100Hz |
| **H-02** | Mic Device Synchronization | `jarvis/core/app.py:1744`, `jarvis/audio/engine.py` | `tests/unit/test_voice_pipeline_fixes.py` | 🟢 Verified | Passes `target_device` to sounddevice stream |
| **H-03** | Acoustic Echo & Settling Guard | `jarvis/core/app.py:1757, 1830`, `jarvis/tts/manager.py` | `tests/unit/test_voice_pipeline_fixes.py`, `test_acoustic_hardening.py` | 🟢 Verified | 4-layer defense: lockout, 150ms settling, single-flight, echo window |
| **H-04** | Zero-Crash PTT Hotkey (Ctrl+Shift+L) | `jarvis/core/app.py:586` | `tests/unit/test_voice_pipeline_fixes.py`, `tests/unit/test_hotkeys.py` | 🟢 Verified | Delegated to `_start_voice_interaction` (8/8 tests pass) |
| **H-05** | Multi-Condition STT & Intent Eval (A1-A4) | `tests/eval/stt_intent_eval.py`, `tests/eval/independent_test_manifest.py` | `docs/eval/stt_eval_results_direct.json` | 🟡 Dataset Ready | 210 independent sentences created; P0-A benchmark recorded; eval pending execution |
| **H-06** | VAD Silence Gating & Energy Cutoff | `jarvis/stt/engine.py:1206`, `jarvis/core/app.py:1780` | `tests/unit/test_tiered_stt.py` (11 tests) | 🟢 Verified | RMS < 0.002 short-circuits with `is_silent=True` |
| **H-07** | App & Web Launch Anti-Runaway Deduplication | `jarvis/automation/control.py`, `jarvis/core/runaway_guard.py` | `tests/unit/test_app_web_dedupe_stress.py` (3 tests) | 🟢 Verified | 60 rapid calls -> 3 launches allowed, 57 suppressed `LAUNCH_RATE_LIMITED` |
| **H-08** | Master Volume & Brightness Fail-Closed | `jarvis/core/app.py:1297-1325` | `tests/unit/test_voice_pipeline_fixes.py` | 🟢 Verified | Returns `success=False` + `VOLUME_SET_FAILED` / `BRIGHTNESS_SET_FAILED` |
| **H-09** | SAPI5 TTS COM Thread Safety | `jarvis/tts/manager.py:78`, `jarvis/tts/fallback.py` | `tests/unit/test_tts_com_safety.py` (6 tests) | 🟢 Verified | `pythoncom.CoInitialize()` / `CoUninitialize()` in daemon worker |
| **H-10** | Faster-Whisper Eager Preload & Anti-Hallucination | `jarvis/stt/engine.py:474-675` | `tests/unit/test_stt_preload.py` (5 tests) | 🟢 Verified | Background thread load + 5-layer anti-hallucination filter |
| **H-11** | Safe Diacritic Normalization & Zero-Homophone Rule | `jarvis/llm/router.py:65, 1989` | `tests/eval/test_voice_generalization_heldout.py` (38 tests) | 🟢 Verified | Single-word exact match boundary; multi-word diacritic folding (38/38 pass) |
| **H-12** | Wake Word Spectral E8 & Clap Rejection | `jarvis/audio/wake_word.py:504`, `dsp.py` | `tests/unit/test_wake_word_real_audio_e8.py` (76 tests total) | 🟢 Verified | SFM [0.03, 0.65], formant delta [0.07s, 0.65s], 2.5s post-TTS suppression |
| **H-13** | TTS Fallback Priority 4 Fail-Closed | `jarvis/tts/fallback.py:134-141` | `tests/unit/test_tts_com_safety.py` | 🟢 Verified | Returns `False` when all TTS fail (no ghost `[SAPI5 Mock TTS Spoke]`) |

---

## 5. Test Suite Execution Matrix

The following test suites were executed on the active Windows test environment:

| Test Command | Items | Result | Duration | Notes |
|---|---|---|---|---|
| `pytest tests/unit/test_voice_pipeline_fixes.py -v` | 6 | **6 Passed (100%)** | 1.63s | Verifies H-01, H-02, H-03, H-04, H-08 |
| `pytest tests/unit/test_app_web_dedupe_stress.py -v` | 3 | **3 Passed (100%)** | 0.59s | Verifies H-07 stress dedupe (60 rapid calls) |
| `pytest tests/unit/test_hotkeys.py -v` | 8 | **8 Passed (100%)** | 0.95s | Verifies global hotkey registration and dispatch |
| `pytest tests/unit/test_tiered_stt.py -v` | 11 | **11 Passed (100%)** | 2.88s | Verifies H-06 VAD silence gating, SNR gating, cascade |
| `pytest tests/unit/test_stt_preload.py -v` | 5 | **5 Passed (100%)** | 1.00s | Verifies H-10 Faster-Whisper eager background loading |
| `pytest tests/unit/test_acoustic_hardening.py -v` | 11 | **11 Passed (100%)** | 2.40s | Verifies H-03 & H-12 VAD gate, echo window tracking |
| `pytest tests/unit/test_tts_com_safety.py -v` | 6 | **6 Passed (100%)** | 1.03s | Verifies H-09 & H-13 COM lifecycle and Priority 4 fail-closed |
| `pytest tests/eval/test_voice_generalization_heldout.py -v` | 38 | **38 Passed (100%)** | 2.31s | Verifies H-11 safe diacritics on unseen phrases |
| `pytest tests/unit/test_wake_word*.py -v` | 76 | **76 Passed (100%)** | 7.68s | Verifies H-12 wake word spectral and real audio E8 |
| `tests/eval/routing_eval_n150.py` | 148 + 284 | **100% Correct (148/148), 278 Tests Passed, 6 Skipped** | 129.93s | Text-routing N=148: 100.0% CORRECT, 0% MISROUTED, 0% SILENT. Pytest suite 0 failures. |
| **Combined Core Voice Suite** | **88** | **88 Passed (100%)** | **4.74s** | Zero regressions across all voice modules |

---

## 6. Recommendations & Actionable Remediation Steps

### Recommended Fix 1: Resolve H-01 Config Precedence (High Priority)
- **Problem**: `record_audio()` calls `self.config.get("audio.sample_rate", 16000)`. Because `config/default_config.yaml` has `audio: sample_rate: 44100`, runtime STT recording silently captures at 44.1 kHz, causing 2.75x slow audio into Whisper.
- **Remediation**:
  In `jarvis/core/app.py`:
  ```python
  # Change line 1738:
  # Before:
  sr = int(sample_rate or self.config.get("audio.sample_rate", 16000))
  # After:
  sr = int(sample_rate or self.config.get("stt.sample_rate", 16000))
  ```
  Update `test_h01_record_audio_default_16khz` to verify that when `app.config` contains `audio.sample_rate: 44100`, `record_audio()` still chooses 16000 Hz for STT.

### Recommended Fix 2: Execute Multi-Condition Independent STT Benchmark (H-05)
- With `tests/eval/independent_test_manifest.py` specifying 210 independent utterances across 14 intents, coordinate with Explorer 3 (`explorer_beta_survey_3`) to execute the benchmark against both `small` and `large-v3` models in `clean` and `noisy` acoustic conditions once H-01 sample rate decoupling is in place.
