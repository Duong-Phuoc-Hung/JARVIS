# Handoff Report: Audio, Wake Word, TTS, and STT Architecture Survey & Hardening Plan (Sprint 2 / v4.7.0)

**Date**: 2026-09-02  
**Author**: Audio & TTS Explorer (`explorer_survey_audio_tts`)  
**Target Milestone**: JARVIS v4.7.0 Sprint 2 (P1 Acoustic, Accuracy & UX Hardening)  
**Target File**: `d:\Software GitCode\JARVIS\.agents\explorer_survey_audio_tts\handoff.md`

---

## 1. Observation

Direct code examination was conducted across all relevant audio, wake word, TTS, and STT source files and unit tests.

### 1.1 Wake Word Detection & Acoustic Hardening (`jarvis/audio/wake_word.py`, `jarvis/core/app.py`, `jarvis/audio/dsp.py`)
- **Current Multi-tier Architecture (`jarvis/audio/wake_word.py:64-72`, `450-517`)**:
  - **Tier 1**: Offline lightweight keyword matching (`vosk.KaldiRecognizer` with Vietnamese model auto-discovery, `pvporcupine`, `openwakeword`).
  - **Tier 1.5**: `WhisperSlidingWindowDetector` (`faster_whisper` on voice-active sliding windows, `jarvis/audio/wake_word.py:167-268`).
  - **Tier 2**: `AcousticSpectralDetector` (zero-dependency acoustic energy & STFT spectral formant/fricative feature detector, `jarvis/audio/wake_word.py:270-409`).
- **Current Mic Ingestion & VAD in Wake Word (`jarvis/audio/wake_word.py:748-800`)**:
  - In `WakeWordDetector.feed_audio_block()`, every incoming block is sanitized, converted to float32, resampled to 16kHz, and pushed into `self._ring_buffer` regardless of whether the frame contains speech or digital silence/background noise.
  - While `AcousticSpectralDetector` checks `rms < self.min_rms` internally, Tier 1 (Vosk/Porcupine) and buffer rolling execute unconditionally on all incoming frames.
- **Current TTS Echo Suppression Defect (`jarvis/core/app.py:332-343`, `1482-1584`)**:
  - In `_start_voice_interaction()`, `_is_voice_interacting` is set to `True` during the interaction and `time.sleep(2.5)` is executed in the `finally:` block.
  - **Critical Flaw**: In `_on_audio_blocks_dispatch(block, timestamp)` (`jarvis/core/app.py:332-343`), `self.wake_word_detector.feed_audio_block(block, timestamp)` is called **unconditionally on every microphone block** from `AudioEngine`, even while TTS is speaking or right after TTS has spoken! The speaker's audio output is captured by the microphone, fed into `_ring_buffer`, and when `_voice_lock` is released, residual speaker audio in `_ring_buffer` can trigger a false positive wake word.
  - Furthermore, `TTSManager.speak()` invoked by proactive triggers, hotkeys, or plugins does not lock microphone ingestion in `_on_audio_blocks_dispatch`.
- **SFM/ZCR Thresholds in `AcousticSpectralDetector` (`jarvis/audio/wake_word.py:270-409`)**:
  - Formant mid band: 400–2500 Hz (`mid_bins`).
  - Fricative high band: 2800–7200 Hz (`high_bins`).
  - Spectral Flatness Measure (SFM):
    - `avg_flatness > 0.65`: White noise rejection.
    - `avg_flatness < 0.03`: Pure sinusoidal tone / system beep rejection. Natural speech formants have SFM in the 0.05–0.35 range.
  - Zero-Crossing Rate (ZCR):
    - `zcr_s2 >= 0.10` during Syllable 2 ("VIS" /vɪs/) ensures fricative presence.
  - Syllable peak timing: `0.07 <= time_diff_s <= 0.65`, with clap impulse rejection `abs(time_diff_s) >= 0.05`.

### 1.2 TTS Thread Safety & COM Initialization (`jarvis/tts/manager.py`, `jarvis/tts/fallback.py`)
- **Current Implementation (`jarvis/tts/manager.py:65-93`)**:
  - `TTSManager` starts a background daemon thread `_worker_thread = threading.Thread(target=self._process_queue, daemon=True, name="TTS-Worker")`.
  - In `_process_queue()`, tasks are popped from `_queue` and executed via `_execute_speak()`, which cascades to `fallback_engine.speak()` (`SAPI5FallbackTTS`) when ElevenLabs is offline or fails.
  - In `_process_queue()`, **no `pythoncom.CoInitialize()` or `pythoncom.CoUninitialize()` is invoked on the thread lifecycle**.
- **Current Implementation in `SAPI5FallbackTTS` (`jarvis/tts/fallback.py:52-75`)**:
  - `fallback.py` calls `pythoncom.CoInitialize()` inside a try block at line 57 before `win32com.client.Dispatch("SAPI.SpVoice")`, but **`pythoncom.CoUninitialize()` is never called in a `finally` block**.
  - If calls occur from different threads or daemon threads without clean apartment teardown, COM references leak or raise `(-2147221008, 'CoInitialize has not been called.')` or `RPC_E_CHANGED_MODE` errors on Windows.

### 1.3 Faster-Whisper Pre-loading & VAD Trimming (`jarvis/stt/engine.py`)
- **Lazy Loading Spike (`jarvis/stt/engine.py:456-533`)**:
  - `FasterWhisperSTT.__init__()` stores configuration but sets `self._model = None`.
  - `WhisperModel(...)` is instantiated only on the first call to `_get_model()`, causing a 2–5s cold-start latency spike on first speech input.
- **Missing VAD Silence Trimming (`jarvis/stt/engine.py:557-576`)**:
  - In `FasterWhisperSTT.transcribe()`, `model.transcribe()` is called with `beam_size`, `condition_on_previous_text=False`, `no_speech_threshold=0.6`, `log_prob_threshold=-1.0`, and `compression_ratio_threshold=2.4`.
  - `vad_filter=True` and `vad_parameters={"min_silence_duration_ms": 500}` are **not configured or passed**, causing Faster-Whisper to process leading/trailing silence frames unnecessarily.

### 1.4 Existing Unit Tests
- `tests/unit/test_wake_word.py` (1414 lines) & `tests/unit/test_wake_word_p0.py` (461 lines): Covers state transitions, audio resampling, white noise/impulse/pure tone rejection, cooldown, and Vosk/Whisper/Acoustic cascades.
- `tests/unit/test_dsp.py` (127 lines): Covers RMS calculation, EMA noise floor tracker, Schmitt trigger.
- `tests/unit/test_tts_engines.py` (70 lines): Covers ElevenLabs, SAPI5 fallback, TTSManager cache/routing.
- `tests/unit/test_stt_engine.py` (325 lines): Covers audio conversion, `VADSegmenter`, and multi-provider STT.

---

## 2. Logic Chain

```
[Observation 1.1] AudioEngine dispatches frames continuously
       ↓
[Observation 1.1] TTS speaks → Speaker audio enters mic
       ↓
[Observation 1.1] WakeWordDetector buffers speaker output into _ring_buffer
       ↓
[Logic Chain 1] False trigger loop occurs unless mic frames are discarded for 2.5s post-TTS
       ↓
[Proposed Fix R1] Add is_in_echo_window(2.5s) to TTSManager; drop frames in _on_audio_blocks_dispatch;
                  clear WakeWordDetector._ring_buffer when entering suppression window.
                  Add VAD filter in feed_audio_block to skip silent frames.

[Observation 1.2] TTSManager._worker_thread runs daemon queue loop without CoInitialize/CoUninitialize
       ↓
[Logic Chain 2] SAPI5 / win32com Dispatch on Windows requires single-threaded apartment (STA) initialization per thread
       ↓
[Proposed Fix R2] Wrap TTSManager._process_queue() with pythoncom.CoInitialize() and CoUninitialize() in finally;
                  wrap SAPI5FallbackTTS.speak() in try...finally CoUninitialize().

[Observation 1.3] FasterWhisperSTT loads model lazily on first transcribe() call
       ↓
[Logic Chain 3] Cold start takes 2-5s; transcribing without vad_filter processes trailing silence
       ↓
[Proposed Fix R3] Launch background daemon thread in FasterWhisperSTT.__init__() to pre-load WhisperModel;
                  pass vad_filter=True and vad_parameters={"min_silence_duration_ms": 500} to model.transcribe().
```

---

## 3. Caveats

1. **WebRTC VAD vs Energy VAD**: `webrtcvad` is a native C extension that may not be installed on all Windows/Python 3.13 environments. The implementation must prioritize a robust RMS/SNR energy-based VAD (zero dependencies) while supporting `webrtcvad` as an optional enhancement if available.
2. **Asynchronous SAPI5 vs Synchronous**: When calling SAPI5 synchronously (`wait=True`), COM can be uninitialized immediately after `Speak()` returns. For asynchronous queue processing in `TTSManager`, COM initialization must span the entire worker thread lifecycle.
3. **Preload Thread Safety**: If `transcribe()` is called while the background preload thread is still loading the model, `_get_model()` must safely wait via `threading.RLock` or `thread.join()`.

---

## 4. Conclusion & Implementation Strategy

### 4.1 R1: DSP Acoustic Hardening & Echo Suppression (`jarvis/audio/wake_word.py`, `jarvis/core/app.py`, `jarvis/tts/manager.py`)
1. **Energy-based / WebRTC VAD Filter in `WakeWordDetector`**:
   - Add `vad_filter_enabled: bool = True` and `vad_threshold: float = 0.003` to `WakeWordDetector.__init__()`.
   - In `feed_audio_block(block, timestamp)`:
     ```python
     # Fast VAD gate: discard silent frames before detector evaluation
     block_rms = calculate_rms(resampled)
     ring_rms = calculate_rms(self._ring_buffer)
     if self.vad_filter_enabled and block_rms < self.vad_threshold and ring_rms < self.vad_threshold:
         return None
     ```
2. **Echo Suppression (2.5s Post-TTS Mic Frame Rejection)**:
   - In `TTSManager`:
     - Add `_last_playback_finish_time: float = 0.0` and `_is_playing: bool = False`.
     - Update `_last_playback_finish_time = time.monotonic()` whenever any speech finishes.
     - Add helper:
       ```python
       def is_in_echo_window(self, current_time: float | None = None, cooldown_s: float = 2.5) -> bool:
           with self._lock:
               if self._is_playing:
                   return True
               now = current_time if current_time is not None else time.monotonic()
               return (now - self._last_playback_finish_time) < cooldown_s
       ```
   - In `WakeWordDetector`:
     - Add `suppress_until(timestamp: float)` / `clear_buffer()`:
       ```python
       def suppress_until(self, timestamp: float) -> None:
           with self._lock:
               self._suppress_until = float(timestamp)
               self._ring_buffer.fill(0.0)
               if self._porcupine_frame_buffer:
                   self._porcupine_frame_buffer.reset()
               if hasattr(self, "_whisper_detector") and self._whisper_detector:
                   self._whisper_detector.reset()
       ```
   - In `jarvis/core/app.py` (`_on_audio_blocks_dispatch`):
     - Discard frames if `self.tts_manager and self.tts_manager.is_in_echo_window(now, cooldown_s=2.5)`.

### 4.2 R2: SAPI5 TTS COM Thread Safety (`jarvis/tts/manager.py`, `jarvis/tts/fallback.py`)
1. **In `TTSManager._process_queue` (`jarvis/tts/manager.py`)**:
   ```python
   def _process_queue(self) -> None:
       com_initialized = False
       try:
           try:
               import pythoncom
               pythoncom.CoInitialize()
               com_initialized = True
           except Exception as e:
               log.debug("TTS worker CoInitialize skipped: %s", e)

           while not self._stop_event.is_set():
               try:
                   task = self._queue.get(timeout=0.2)
               except queue.Empty:
                   continue
               text, voice_id, callback, mock_http = task
               try:
                   success = self._execute_speak(text, voice_id=voice_id, wait=True, mock_http=mock_http)
                   if callback:
                       callback(success)
               except Exception as e:
                   log.error("TTS worker failed speaking: %s", e)
                   if callback:
                       callback(False)
               finally:
                   self._queue.task_done()
       finally:
           if com_initialized:
               try:
                   import pythoncom
                   pythoncom.CoUninitialize()
               except Exception as e:
                   log.debug("TTS worker CoUninitialize error: %s", e)
   ```
2. **In `SAPI5FallbackTTS.speak` (`jarvis/tts/fallback.py`)**:
   - Wrap direct calls with `try: pythoncom.CoInitialize() ... finally: pythoncom.CoUninitialize()`.

### 4.3 R3: Faster-Whisper Pre-loading & VAD Silence Trimming (`jarvis/stt/engine.py`)
1. **Background Eager Preloading in `FasterWhisperSTT.__init__()`**:
   ```python
   self._preload_thread: threading.Thread | None = None
   if self.config.get("preload", True) and FASTER_WHISPER_AVAILABLE:
       self._preload_thread = threading.Thread(
           target=self._get_model,
           name="FasterWhisper-Preload",
           daemon=True,
       )
       self._preload_thread.start()
   ```
2. **Silence Trimming in `FasterWhisperSTT.transcribe()`**:
   ```python
   vad_filter = kwargs.pop("vad_filter", self.config.get("vad_filter", True))
   vad_parameters = kwargs.pop(
       "vad_parameters",
       self.config.get("vad_parameters", {"min_silence_duration_ms": 500}),
   )

   with self._lock:
       segments, info = model.transcribe(
           arr,
           language=language,
           beam_size=kwargs.pop("beam_size", 5),
           condition_on_previous_text=False,
           no_speech_threshold=0.6,
           log_prob_threshold=-1.0,
           compression_ratio_threshold=2.4,
           vad_filter=vad_filter,
           vad_parameters=vad_parameters,
           **kwargs,
       )
   ```

---

## 5. Verification Method

### 5.1 Unit Tests to Create
1. **`tests/unit/test_acoustic_hardening.py`** (≥ 5 tests):
   - `test_vad_filter_discards_silent_frames()`
   - `test_vad_filter_passes_speech_frames()`
   - `test_echo_suppression_discards_mic_frames_during_tts_and_cooldown()`
   - `test_echo_suppression_clears_sliding_buffer()`
   - `test_spectral_detector_sfm_zcr_bounds()`
2. **`tests/unit/test_tts_com_safety.py`** (≥ 3 tests):
   - `test_tts_worker_thread_com_initialize_and_uninitialize()`
   - `test_ten_consecutive_tts_calls_in_daemon_thread()`
   - `test_tts_fallback_com_error_isolation()`
3. **`tests/unit/test_stt_preload.py`** (≥ 3 tests):
   - `test_faster_whisper_preload_starts_background_thread()`
   - `test_faster_whisper_transcribe_passes_vad_filter_and_parameters()`
   - `test_faster_whisper_warm_transcription_latency()`

### 5.2 Verification Commands
```powershell
pytest tests/unit/test_acoustic_hardening.py tests/unit/test_tts_com_safety.py tests/unit/test_stt_preload.py -v
pytest tests/unit/test_wake_word.py tests/unit/test_wake_word_p0.py tests/unit/test_tts_engines.py tests/unit/test_stt_engine.py -q
```
