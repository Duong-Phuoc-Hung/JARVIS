# Scope: Milestone 2 — Audio Engine, Gestures & TTS Subsystems

## Objective
Implement and verify all components of Milestone 2:
1. Audio Engine & Acoustic DSP (`jarvis/audio/dsp.py`, `jarvis/audio/engine.py`):
   - RMS energy calculation over NumPy int16/float32 buffers.
   - Exponential Moving Average (EMA) dynamic noise floor tracking with configurable alpha/beta (rising vs falling).
   - Dual-threshold Schmitt trigger (high threshold to trigger clap, low threshold to reset) for robust transient detection without bouncing.
   - Quiet gate / minimum SNR ratio check.
   - Device enumeration, auto-probing active/loudest microphone with SoundDevice fallback / mock support for headless/CI environments.
2. Gesture Detection Engine (`jarvis/gesture/detector.py`, `jarvis/gesture/patterns.py`):
   - Multi-clap detector with precise timestamped event queue.
   - Double clap: 2 claps with interval within [0.05s, 0.35s], debounce, 0.45s cooldown.
   - Triple clap: 3 claps within calibrated consecutive windows.
   - Syncopated Clap-Pause-Clap pattern: Clap 1 -> Gap 1 -> Clap 2 -> Pause window -> Clap 3.
   - Extensible pattern matcher emitting gesture events to dispatcher / action handlers.
3. Text-to-Speech Subsystem (`jarvis/tts/`):
   - `jarvis/tts/base.py`: Abstract Base Class for TTS engines.
   - `jarvis/tts/cache.py`: SHA-256 local audio cache (`.cache/jarvis_welcome/` or configured cache dir), format conversion / playback helpers.
   - `jarvis/tts/elevenlabs.py`: ElevenLabs REST/WebSocket client, streaming audio chunk handling, API key from settings/.env, graceful error handling.
   - `jarvis/tts/fallback.py`: Offline fallback via Windows SAPI5 / pyttsx3 (or mock on non-Windows/CI), automatic fallback if ElevenLabs fails or lacks API key.
   - `jarvis/tts/manager.py`: TTSManager (orchestrating primary + fallback + cache).
4. Legacy & Modern Action Plugins (`jarvis/plugins/`):
   - `jarvis/plugins/spotify.py`: Launch Spotify track / URI via `os.startfile` / subprocess.
   - `jarvis/plugins/chrome.py`: Google Chrome multi-monitor placement (Claude on Monitor 1, Binance on Monitor 3, Win32 coordinate calculation, F11 fullscreen).
   - `jarvis/plugins/cursor.py`: Cursor IDE window enumeration, unminimize, focus, and F11 fullscreen.
   - Integration with M1 ActionDispatcher and Config registry.
5. Entry Point / Background Loop (`jarvis/__main__.py`, `jarvis/core/app.py`):
   - Wire audio stream -> DSP -> gesture detector -> dispatcher -> action execution -> TTS greeting / status feedback.
   - Graceful shutdown on SIGINT/Ctrl+C.

## Feature Inventory
| # | Feature | Scope / Component | Status |
|---|---------|-------------------|--------|
| F-02 | Monolith Legacy Compatibility | .env parsing, Spotify, Chrome multi-monitor placement, Cursor IDE focus/F11 | **DONE** |
| F-03 | Acoustic Signal Processor | `jarvis/audio/dsp.py` (RMS, EMA noise floor, Schmitt trigger, quiet gate) | **DONE** |
| F-04 | Microphone Auto-Probe | `jarvis/audio/engine.py` (SoundDevice capture, enumeration, probe loudest mic) | **DONE** |
| F-05 | Double Clap Detection | `jarvis/gesture/detector.py` (0.05s-0.35s window, 0.45s cooldown, debounce) | **DONE** |
| F-06 | Triple Clap Detection | `jarvis/gesture/detector.py` (3 consecutive claps within windows) | **DONE** |
| F-07 | Clap-Pause-Clap Detection | `jarvis/gesture/detector.py` (Syncopated rhythm pattern) | **DONE** |
| F-11 | ElevenLabs TTS Engine | `jarvis/tts/elevenlabs.py` (PCM conversion, API key integration) | **DONE** |
| F-12 | Local TTS Audio Cache | `jarvis/tts/cache.py` (SHA-256 caching under `.cache/jarvis_welcome/`) | **DONE** |
| F-13 | Offline Fallback TTS | `jarvis/tts/fallback.py` (Windows SAPI5 / pyttsx3 offline synthesis) | **DONE** |
| Built-in | Spotify Plugin | `jarvis/plugins/spotify.py` | **DONE** |
| Built-in | Chrome Multi-Monitor | `jarvis/plugins/chrome.py` | **DONE** |
| Built-in | Cursor IDE Action | `jarvis/plugins/cursor.py` | **DONE** |
| Built-in | Main Background Loop | `jarvis/__main__.py` & `jarvis/core/app.py` | **DONE** |

## Architecture & Code Layout
- `jarvis/audio/`:
  - `__init__.py`
  - `dsp.py`: RMS, EMA filter, SchmittTrigger, QuietGate, AudioDSPProcessor
  - `engine.py`: AudioEngine, MicrophoneProbeManager, feed_virtual_audio
- `jarvis/gesture/`:
  - `__init__.py`
  - `models.py`: GestureType, ClapEvent, GestureResult, DetectorState, GesturePatternConfig
  - `patterns.py`: Pattern definitions & registry
  - `detector.py`: GestureDetector (Double, Triple, Clap-Pause-Clap state machines with chatter suppression & float epsilon tolerance)
- `jarvis/tts/`:
  - `__init__.py`
  - `base.py`: BaseTTSEngine
  - `cache.py`: TTSAudioCache (SHA-256, atomic write)
  - `elevenlabs.py`: ElevenLabsTTS
  - `fallback.py`: SAPI5FallbackTTS / Pyttsx3TTS
  - `manager.py`: TTSManager (orchestrating primary + fallback + cache)
- `jarvis/plugins/`:
  - `spotify.py`: SpotifyPlugin
  - `chrome.py`: ChromeMultiMonitorPlugin
  - `cursor.py`: CursorFocusPlugin
  - `shell.py`: ShellPlugin
  - `webhook.py`: WebhookPlugin
- `jarvis/core/app.py` / `jarvis/__main__.py`:
  - Application lifecycle, event loop, wire-up of Audio -> Gesture -> Actions -> TTS.
- `tests/`:
  - `test_dsp.py`, `test_audio_engine.py`, `test_gesture_detector.py`, `test_tts_cache.py`, `test_tts_engines.py`, `test_plugins_m2.py`, `test_app_integration.py`, `test_adversarial_m2_audio_gesture.py`, `test_empirical_challenger_m2.py`, `test_empirical_challenger_m2_e2e_stress.py`, `test_empirical_challenger_m2_3.py`.
