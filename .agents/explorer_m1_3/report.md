# Technical Investigation & Implementation Blueprint: TTS Pipeline & Voice Loop De-duplication

**Author**: Explorer M1_3 (Milestone M1: Voice AI Pipeline Bug Fixes & Stabilization)  
**Target Files**:
- `jarvis/tts/manager.py` (High-level TTS coordinator & async worker)
- `jarvis/tts/fallback.py` (Offline SAPI5 / PowerShell / pyttsx3 / Mock synthesis)
- `jarvis/tts/elevenlabs.py` (Cloud neural TTS & HTTP error translation)
- `jarvis/tts/cache.py` (SHA-256 WAV disk cache & atomic persistence)
- `jarvis/tts/engine.py` (Unified backward-compatible coordinator)
- `jarvis/core/app.py` (`_ai_voice_loop` and `process_text_command` speech de-duplication)
- `tests/test_tts_engine.py`, `tests/unit/test_tts_cache.py`, `tests/unit/test_tts_engines.py` (Regression verification)

---

## 1. Executive Summary

This report delivers the verified architectural analysis, root cause diagnosis, and concrete code-level implementation blueprint for:
1. **TTS Fault-Tolerance & Seamless SAPI5 Fallback**: Ensuring that missing API keys, invalid credentials, HTTP 401/403/429/500 errors, network timeouts, or COM thread marshalling errors trigger instantaneous, non-blocking, non-crashing fallback to Windows SAPI5 (`win32com` / PowerShell `System.Speech` / `pyttsx3` / mock).
2. **Elimination of Duplicate TTS Vocalization in `jarvis/core/app.py`**: Refactoring `_ai_voice_loop` and `process_text_command` to establish a single authoritative vocalization pathway, preventing redundant speech queueing.
3. **UX Polish & Tony Stark Persona (R4)**: Adding startup self-introduction (`"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."`) and non-repeating randomized welcome greetings.
4. **Zero-Regression Verification**: Comprehensive audit of all test fixtures and assertions across `tests/test_tts_engine.py`, `tests/unit/test_tts_cache.py`, and `tests/unit/test_tts_engines.py` to ensure 100% test compatibility.

---

## 2. Deep Dive: TTS Manager & Offline SAPI5 Fallback Architecture

### 2.1 Component Architecture Map

```
                     ┌─────────────────────────────┐
                     │   Caller (App / Plugin /    │
                     │    User Voice Loop)         │
                     └──────────────┬──────────────┘
                                    │ speak(text, wait=False/True)
                                    ▼
                     ┌─────────────────────────────┐
                     │         TTSManager          │
                     │  (Thread-Safe Coordinator)  │
                     └──────┬───────────────┬──────┘
             [Cache Hit]    │               │  [Cache Miss]
                   ┌────────┴───────┐       ▼
                   │  TTSAudioCache │ ┌───────────────────────────┐
                   │ (SHA-256 WAV)  │ │  ElevenLabsTTS (Primary)  │
                   └────────────────┘ └─────────────┬─────────────┘
                                                    │ [Failure / No Key / 401/429/500]
                                                    ▼
                                      ┌───────────────────────────┐
                                      │ SAPI5FallbackTTS (Offline)│
                                      ├───────────────────────────┤
                                      │ 1. win32com (SAPI.SpVoice)│
                                      │ 2. PowerShell Synth       │
                                      │ 3. pyttsx3                │
                                      │ 4. Mock Logger & History  │
                                      └───────────────────────────┘
```

### 2.2 Detailed Failure Mode Analysis & Fallback Tracing

| Scenario | Primary State | Exception Raised / Caught | Manager Handling | Fallback Execution |
|---|---|---|---|---|
| **Missing API Key** (`api_key=""` or None) | `ElevenLabsTTS.is_available() == False` | None (bypassed before HTTP) | `if is_available(): ...` evaluates to False | Direct jump to Step 3: `self.fallback_engine.speak(text)` |
| **Invalid API Key (HTTP 401 / 403)** | `is_available() == True` | `TTSError: ElevenLabs HTTP Error 401: Unauthorized` | `_execute_speak()` catches `Exception as e`, logs `WARNING`, proceeds to Step 3 | `self.fallback_engine.speak(text)` executes seamlessly |
| **Rate Limit / Quota (HTTP 429)** | `is_available() == True` | `TTSError: ElevenLabs HTTP Error 429: Too Many Requests` | Caught by `_execute_speak()`, logs warning, proceeds to Step 3 | `self.fallback_engine.speak(text)` executes seamlessly |
| **Server Error (HTTP 500 / 502 / 503)** | `is_available() == True` | `TTSError: ElevenLabs HTTP Error 500: Server Error` | Caught by `_execute_speak()`, logs warning, proceeds to Step 3 | `self.fallback_engine.speak(text)` executes seamlessly |
| **Network Timeout / Connection Refused** | `is_available() == True` | `requests.exceptions.Timeout` wrapped in `TTSError` | Caught by `_execute_speak()`, logs warning, proceeds to Step 3 | `self.fallback_engine.speak(text)` executes seamlessly |
| **Corrupted Cached WAV (< 44 bytes / 0-byte)** | Cache Hit check detects `st_size < 44` | Invalidation logs warning, deletes file, returns `None` | Cache miss detected -> proceeds to ElevenLabs or SAPI5 | Fresh synthesis executed, atomic overwrite |
| **Non-Windows / Headless Environment** | win32com / PowerShell unavailable | `ImportError` / `FileNotFoundError` | Cascades through pyttsx3 to Mock Logger | Records to `spoken_history` and `offline_calls`, returns `True` |

### 2.3 Hardening `jarvis/tts/fallback.py`

#### Observations & Identified Risks in Existing Code:
1. **COM Multi-threading Initialization**: In secondary threads (e.g. `TTS-Worker`, `AI-Voice-Loop`), calling `win32com.client.Dispatch("SAPI.SpVoice")` can fail with `CoInitialize has not been called (0x800401F0)` if COM apartment threading is not initialized.
2. **PowerShell Special Character Escaping**: `ps_script` constructed using simple single-quote replacement (`clean_text = text.replace("'", "''")`) may encounter syntax parsing errors when `text` contains multiline newlines (`\n`), backticks (`` ` ``), or control characters.
3. **Subprocess Hanging Guard**: PowerShell child processes must be invoked with strict timeout, `stdin=subprocess.DEVNULL`, `stdout=subprocess.DEVNULL`, `stderr=subprocess.DEVNULL`, and `creationflags=subprocess.CREATE_NO_WINDOW` on Windows.

#### Proposed Hardened Implementation for `SAPI5FallbackTTS.speak()`:
```python
def speak(self, text: str, voice_id: Optional[str] = None, wait: bool = False, **kwargs) -> bool:
    """Speak via Windows SAPI5 or PowerShell System.Speech with cross-platform fallback."""
    if not text or not text.strip():
        return False

    clean_text = text.strip()
    self._spoken_history.append(clean_text)

    if sys.platform == "win32":
        # Priority 1: win32com.client SAPI.SpVoice with defensive CoInitialize
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            if self.voice_name:
                try:
                    for v in speaker.GetVoices():
                        if self.voice_name.lower() in v.GetDescription().lower():
                            speaker.Voice = v
                            break
                except Exception:
                    pass
            speaker.Rate = self.rate
            speaker.Volume = self.volume
            flags = 0 if wait else 1  # 1 = SVSFlagsAsync
            speaker.Speak(clean_text, flags)
            return True
        except Exception as e:
            log.debug("win32com SAPI speak failed (%s), trying PowerShell fallback", e)

        # Priority 2: PowerShell System.Speech.Synthesis
        try:
            import base64
            # Use Base64 encoding to eliminate any shell quoting or character escaping issues
            b64_script = base64.b64encode(
                f"""
                Add-Type -AssemblyName System.Speech;
                $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;
                $synth.Rate = {self.rate};
                $synth.Volume = {self.volume};
                $bytes = [System.Convert]::FromBase64String('{base64.b64encode(clean_text.encode("utf-8")).decode("ascii")}');
                $text = [System.Text.Encoding]::UTF8.GetString($bytes);
                $synth.Speak($text);
                """.encode("utf-16le")
            ).decode("ascii")

            cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", b64_script]
            kw: dict = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW

            if wait:
                subprocess.run(cmd, check=True, timeout=15.0, **kw)
            else:
                subprocess.Popen(cmd, **kw)
            return True
        except Exception as e:
            log.warning("PowerShell speech synthesis failed: %s", e)

    # Priority 3: pyttsx3 fallback (Cross-platform)
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(clean_text)
        if wait:
            engine.runAndWait()
        return True
    except Exception:
        pass

    # Priority 4: Mock logger for CI/Headless
    log.info("[SAPI5 Mock TTS Spoke]: %s", clean_text)
    return True
```

---

## 3. Deep Dive: Eliminating Duplicate TTS Vocalization in `jarvis/core/app.py`

### 3.1 Root Cause of Duplicate Speech
In `jarvis/core/app.py`, speech vocalization was split across two distinct locations:
1. `process_text_command(text)`:
   ```python
   # Line 491-492:
   if self.tts_manager and response_text:
       self.tts_manager.speak(response_text, wait=False)
   ```
2. `_ai_voice_loop()`:
   ```python
   # Lines 373-389:
   if self.llm_router:
       try:
           result = self.process_text_command(transcript, requester="voice")
           response_text = result.get("response_text", "")
       except Exception as e:
           log.error("LLM processing failed: %s", e)
           response_text = f"Xin lỗi, tôi gặp lỗi khi xử lý lệnh: {e}"
   else:
       response_text = f"Tôi nghe thấy: {transcript}. Nhưng LLM chưa được cấu hình."

   if self.overlay:
       self.overlay.show_response(transcript, response_text)

   # Redundant duplicate speak guard:
   if response_text and self.tts_manager and not self.llm_router:
       self.tts_manager.speak(response_text, wait=False)
   ```

### 3.2 Key Defects in Previous Flow:
1. **Asymmetric Responsibility**: When `llm_router` was present, `process_text_command` spoke the response. When `llm_router` was None, `process_text_command` was bypassed, and `_ai_voice_loop` manually set `response_text` and spoke it via a negative guard `not self.llm_router`.
2. **Double Queuing Hazard**: If any future refactoring triggered `process_text_command` inside `_ai_voice_loop` without `llm_router`, or if `process_text_command` was modified, speech commands could be queued twice to `TTSManager`.
3. **Inconsistent Dashboard & Action Telemetry**: Bypassing `process_text_command` when `llm_router` is None meant the dashboard never received the interaction event.

### 3.3 Proposed Refactored Architecture for `_ai_voice_loop` & `process_text_command`

#### 1. Single Centralized Authority in `process_text_command()`:
`process_text_command()` is responsible for:
- Intent parsing (Tier 1 fast regex -> Tier 2 LLM tool calling -> Tier 3 rule fallback).
- Fallback handling if `llm_router` is `None` or raises an unhandled exception.
- Natural Vietnamese response formatting.
- Spoken vocalization via `self.tts_manager.speak(response_text, wait=False)` (single point of vocalization).
- Dashboard event broadcast via `self.dashboard_server.broadcast_event()`.
- Returning structured dictionary with `response_text`.

#### 2. Cleaned `_ai_voice_loop()` in `jarvis/core/app.py`:
```python
def _ai_voice_loop():
    # 1. Show overlay listening state + vocal prompt
    if self.overlay:
        self.overlay.show_listening()
    if self.tts_manager:
        self.tts_manager.speak("Vâng thưa Ngài, tôi đang lắng nghe.", wait=True)

    if self.tray_controller:
        self.tray_controller.update_status(TrayStatus.LISTENING)

    # 2. Record and transcribe audio
    transcript = ""
    if self.stt_engine:
        try:
            import sounddevice as _sd
            sample_rate = int(self.config.get("audio.sample_rate", 44100))
            record_s = float(self.config.get("stt.timeout_s", 5.0))
            log.info("Recording voice command for %.1fs...", record_s)
            audio_data = _sd.rec(
                int(record_s * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
            _sd.wait()
            audio_flat = audio_data.flatten()
            transcript = self.stt_engine.transcribe(audio_flat)
            log.info("Transcribed: '%s'", transcript)
        except Exception as e:
            log.error("STT recording/transcription failed: %s", e)

    # 3. Handle silence / empty transcription
    if not transcript or not transcript.strip():
        silence_msg = "Tôi không nghe thấy gì. Vui lòng thử lại."
        if self.overlay:
            self.overlay.show_response("(không nghe thấy)", silence_msg)
        if self.tts_manager:
            self.tts_manager.speak(silence_msg, wait=False)
        if self.tray_controller:
            self.tray_controller.update_status(TrayStatus.ACTIVE)
        return

    # 4. Show thinking state on overlay
    if self.overlay:
        self.overlay.show_thinking(transcript)

    # 5. Process command (Central authority handles dispatch, speech, dashboard)
    response_text = ""
    try:
        result = self.process_text_command(transcript, requester="voice")
        response_text = result.get("response_text", "")
    except Exception as e:
        log.error("Voice command processing failed: %s", e)
        response_text = f"Xin lỗi, tôi gặp lỗi khi xử lý lệnh: {e}"
        if self.tts_manager:
            self.tts_manager.speak(response_text, wait=False)

    # 6. Update overlay with final response
    if self.overlay:
        self.overlay.show_response(transcript, response_text)

    if self.tray_controller:
        self.tray_controller.update_status(TrayStatus.ACTIVE)
```

---

## 4. UX Polish & Persona Requirements (R4)

### 4.1 Startup Self-Introduction
Requirement R4 mandates:
`"JARVIS tự giới thiệu khi khởi động: 'Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.'"`

In `JarvisApp.start()`:
```python
# Startup self-introduction speech
if self.tts_manager:
    startup_greeting = self.config.get("welcome.startup_greeting") or "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."
    self.tts_manager.speak(startup_greeting, wait=False)
```

### 4.2 Randomized Non-Repeating Welcome Pool in `TTSManager.speak_welcome`
In `jarvis/tts/manager.py`:
```python
WELCOME_PHRASES = [
    "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.",
    "Chào mừng Ngài trở lại. Mọi hệ thống đang hoạt động tối ưu.",
    "Xin chào sếp, JARVIS đã sẵn sàng phục vụ.",
    "Welcome home sir. Tất cả các kết nối và cảm biến đã hoàn tất khởi động.",
]

class TTSManager:
    ...
    def speak_welcome(self, delay_s: float = 1.0, phrase: Optional[str] = None) -> None:
        """Plays a randomized Tony Stark-style welcome phrase in a detached daemon thread."""
        import random
        if phrase:
            welcome_phrase = phrase
        elif self.config.get("welcome", {}).get("phrase"):
            welcome_phrase = self.config.get("welcome", {}).get("phrase")
        else:
            welcome_phrase = random.choice(WELCOME_PHRASES)

        def _runner():
            if delay_s > 0:
                time.sleep(delay_s)
            self.speak(welcome_phrase, wait=False)

        threading.Thread(target=_runner, daemon=True, name="WelcomeTTS").start()
```

---

## 5. Test Suite Analysis & Regression Verification

### 5.1 Verification Matrix across TTS Test Suites

| Test Function | File Location | Subsystem Tested | Key Assertions & Invariants |
|---|---|---|---|
| `test_tts_elevenlabs_stream_generation_tier1` | `tests/test_tts_engine.py` | `TTSEngine` (ElevenLabs + Mock) | `res is True`, `len(mock_http.elevenlabs_calls) == 1`, `played_audio_count == 1` |
| `test_tts_audio_cache_hit_and_replay_tier1` | `tests/test_tts_engine.py` | `TTSEngine` + `LocalTTSCache` | 1st call: Miss -> 1 API call; 2nd call: Hit -> 1 API call, `played_audio_count == 2` |
| `test_tts_audio_cache_write_on_miss_tier1` | `tests/test_tts_engine.py` | `LocalTTSCache` atomic WAV write | Cache directory has 1 `.wav` file with `stat().st_size > 44` |
| `test_tts_offline_sapi5_pyttsx3_fallback_tier1` | `tests/test_tts_engine.py` | `TTSEngine` with `api_key=""` | `res is True`, `"Offline notification alert" in offline_calls`, `played_audio_count == 1` |
| `test_tts_elevenlabs_http_500_and_rate_limit_fallback_tier2` | `tests/test_tts_engine.py` | `TTSEngine` HTTP error fallback | `elevenlabs_fail_mode = "429"`, `res is True`, `"Rate limited prompt" in offline_calls` |
| `test_tts_corrupted_cached_wav_file_tier2` | `tests/test_tts_engine.py` | `LocalTTSCache` 0-byte invalidation | Corrupt 0-byte file replaced with valid WAV `stat().st_size > 44` |
| `test_tts_empty_and_whitespace_phrase_tier2` | `tests/test_tts_engine.py` | `TTSEngine` empty input handling | `speak("") is False`, `speak("  ") is False`, `played_audio_count == 0` |
| `test_tts_cache_key_computation` | `tests/unit/test_tts_cache.py` | `TTSAudioCache.compute_key` | SHA-256 digest matches `{text}\|{voice_id}\|{model_id}\|{output_format}`[:24] |
| `test_tts_cache_put_and_get` | `tests/unit/test_tts_cache.py` | `TTSAudioCache.put_pcm` / `get` | 16-bit mono 24kHz WAV header verified, cache hit returns saved path |
| `test_tts_cache_corruption_handling` | `tests/unit/test_tts_cache.py` | `TTSAudioCache` corruption guard | Corrupt 0-byte file deleted, `get()` returns `None` |
| `test_local_tts_cache_bytes_interface` | `tests/unit/test_tts_cache.py` | `LocalTTSCache.get` | Returns raw `bytes` with length > 44 |
| `test_elevenlabs_engine_availability` | `tests/unit/test_tts_engines.py` | `ElevenLabsTTS.is_available` | Returns `False` for empty key, `True` for non-empty key |
| `test_elevenlabs_synthesize_mock_http` | `tests/unit/test_tts_engines.py` | `ElevenLabsTTS.synthesize_to_bytes` | Returns valid PCM bytes via mock HTTP handler |
| `test_sapi5_fallback_tts` | `tests/unit/test_tts_engines.py` | `SAPI5FallbackTTS` | `is_available() is True`, records to `spoken_history` |
| `test_tts_manager_cache_and_fallback_routing` | `tests/unit/test_tts_engines.py` | `TTSManager` routing | Call 1 (miss): API called; Call 2 (hit): API skipped; Call 3 (error): falls back to SAPI5 |
| `test_full_audio_gesture_dispatch_pipeline` | `tests/unit/test_app_integration.py` | Full App + GestureDetector + TTS | Double clap audio executes actions and invokes TTS fallback speak |
| `test_jarvis_app_full_voice_pipeline_dispatch` | `tests/test_adversarial_m3_ui_app.py` | `JarvisApp.process_voice_command` | Full pipeline executes action, updates dashboard, and triggers single TTS response |

### 5.2 Preservation of Public Interfaces & Signatures
The refactor strictly maintains:
1. `TTSManager(config, cache_dir, primary_engine, fallback_engine)`:
   - `speak(text, voice_id, wait, callback, mock_http) -> bool`
   - `speak_welcome(delay_s, phrase) -> None`
   - `stop() -> None`
2. `SAPI5FallbackTTS(config)`:
   - `speak(text, voice_id, wait, **kwargs) -> bool`
   - `offline_calls -> List[str]` property
   - `spoken_history -> List[str]` property
   - `synthesize_to_bytes(text, voice_id, **kwargs) -> bytes`
3. `TTSEngine(api_key, voice_id, model_id, cache_dir, config)`:
   - `speak(text, wait, mock_http) -> bool`
   - `offline_calls: List[str]`
   - `played_audio_count: int`
4. `TTSAudioCache` & `LocalTTSCache`:
   - `compute_key(text, voice_id, model_id, output_format) -> str`
   - `get(text, voice_id, model_id, output_format) -> Optional[Path / bytes]`
   - `put_pcm(...) -> Path`, `put(...) -> Path`

---

## 6. Actionable Implementation Checklist for Worker

- [ ] **Step 1 (`jarvis/tts/fallback.py`)**:
  - Add defensive `pythoncom.CoInitialize()` in `win32com` block.
  - Implement base64-encoded command execution for PowerShell `System.Speech.Synthesis` with `CREATE_NO_WINDOW` and strict 15.0s timeout.
  - Ensure `_spoken_history` is populated on every `speak()` call.
- [ ] **Step 2 (`jarvis/tts/manager.py`)**:
  - Implement Tony Stark polite randomized welcome greeting pool (`WELCOME_PHRASES`) in `speak_welcome()`.
  - Maintain thread safety with `_lock` and non-blocking queue processing.
- [ ] **Step 3 (`jarvis/core/app.py`)**:
  - In `_ai_voice_loop`: remove lines 388-389 (`self.tts_manager.speak` with `and not self.llm_router`).
  - In `_ai_voice_loop`: ensure `process_text_command` is called as the unified command handler, catching any unexpected exception and vocalizing once.
  - In `start()`: trigger startup self-introduction speech (`"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."`).
- [ ] **Step 4 (`tests/`)**:
  - Run regression check on `tests/test_tts_engine.py`, `tests/unit/test_tts_cache.py`, `tests/unit/test_tts_engines.py`, `tests/unit/test_app_integration.py`.
