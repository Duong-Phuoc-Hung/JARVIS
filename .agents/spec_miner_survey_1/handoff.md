# Handoff Report: Specification Mining for JARVIS Sprint 2 (v4.7.0)

- **Agent**: `spec_miner_survey_1` (Specification Miner)
- **Target Version**: `v4.7.0` (Sprint 2: Accuracy, Acoustic & UX Hardening)
- **Working Directory**: `d:\Software GitCode\JARVIS\.agents\spec_miner_survey_1`
- **Timestamp**: 2026-09-02T07:35:00Z
- **Authoritative Sources**:
  1. `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (Mandatory Source of Truth)
  2. `docs/ROADMAP.md` (Sprint 2 Plan § lines 652–672, Technical Backlog P1-6 to P1-11 § lines 285–401, Traceability Matrix § lines 720–748)
  3. `CHANGELOG.md` (v4.6.0 Baseline Reference)
  4. `AUDIT_METHODOLOGY.md` (Evaluation Tiers, Wilson Confidence Intervals, 7 Acceptance Criteria)
  5. Codebase implementations: `jarvis/audio/wake_word.py`, `jarvis/audio/vad.py`, `jarvis/audio/dsp.py`, `jarvis/tts/manager.py`, `jarvis/tts/fallback.py`, `jarvis/stt/engine.py`, `jarvis/ui/overlay.py`, `jarvis/ui/tray.py`, `jarvis/hardware/reporter.py`, `jarvis/hardware/monitor.py`, `jarvis/llm/router.py`, `jarvis/core/app.py`.

---

## 1. Observation

### 1.1 Baseline System State (v4.6.0)
- **Test Suite Status**: 0 failures across unit and adversarial suites (`pytest tests/ -q --ignore=tests/e2e`).
- **Router Text Intent Accuracy**: CORRECT = 100.0% (143/143), SILENT_FAILURE = 0.0%, MISROUTED = 0.0% on `tests/eval/routing_eval_n150.py`.
- **STT Acoustic Accuracy**: ~22% on real microphone acoustic trials (small model baseline, latency 853ms).
- **Installed / Missing Dependencies**:
  - Available: `faster_whisper` (CTranslate2), `requests`, `numpy`, `win32com`, `psutil`.
  - Missing / Optional: `vosk` (model not bundled in models/), `cv2`, `mediapipe`, `playwright`, `webrtcvad`.
- **Active Environment Variables**: `OPENAI_API_KEY`, `GOOGLE_API_KEY`. Unset: `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `TELEGRAM_BOT_TOKEN`.

### 1.2 Code-Level Direct Observations by Feature Group

#### R1: P1-8 DSP Acoustic Hardening & Echo Suppression
- **File**: `jarvis/audio/wake_word.py` (L750–L902)
  - `WakeWordDetector.feed_audio_block()` processes every non-empty audio block directly into the sliding ring buffer `self._ring_buffer` and immediately executes spectral analysis `AcousticSpectralDetector.analyze_window()` or Whisper sliding window if Tier 1 is not active.
  - Silent/low-energy frames are checked only inside `AcousticSpectralDetector.analyze_window()` (L307: `rms < self.min_rms`) or `WhisperSlidingWindowDetector` (L231), meaning compute is spent feeding ring buffers and no unified Voice Activity Detection (VAD) gate runs upfront before the wake word cascade.
- **File**: `jarvis/core/app.py` (L332–L343, L1480–L1570)
  - `_on_audio_blocks_dispatch(block, timestamp)` dispatches audio blocks unconditionally to `gesture_detector` and `wake_word_detector`.
  - While `app.py` has a cooldown of 2.5s on trigger re-activation, there is **no implementation-level microphone suppression window during TTS playback or for 2.5s immediately following TTS output**. Audio blocks continue to flow into the detector during and directly after TTS speech, creating risk of self-trigger acoustic feedback loops.
- **File**: `jarvis/audio/wake_word.py` (L350–L408)
  - SFM (Spectral Flatness Measure) thresholds: white noise rejection at `avg_flatness > 0.65`, pure tone / narrow-band rejection at `avg_flatness < 0.03`.
  - ZCR (Zero-Crossing Rate) during Syllable 2 ("VIS") required $\ge 0.10$.
  - Inter-syllable timing gap between "JAR" and "VIS" required between $0.07\text{s}$ and $0.65\text{s}$, with impulse clap rejection at $|t_{\text{diff}}| < 0.05\text{s}$.

#### R2: P1-9 SAPI5 TTS Thread Safety — COM Initialization
- **File**: `jarvis/tts/manager.py` (L70–L93)
  - `TTSManager._start_worker()` spawns `_worker_thread = threading.Thread(target=self._process_queue, daemon=True, name="TTS-Worker")`.
  - `_process_queue()` dequeues tasks and calls `self._execute_speak(text, ...)` which invokes `self.fallback_engine.speak(text, ...)` on offline fallback (`SAPI5FallbackTTS`).
  - Neither `_worker_thread` entry point nor `_process_queue` calls `pythoncom.CoInitialize()`. On Windows OS threads where COM objects are created/invoked without initialization in that thread's Single-Threaded Apartment (STA) or Multi-Threaded Apartment (MTA), calls to `win32com.client.Dispatch("SAPI.SpVoice")` crash with `pywintypes.com_error: (-2147221008, 'CoInitialize has not been called.', None, None)`.
- **File**: `jarvis/tts/fallback.py` (L54–L75)
  - `SAPI5FallbackTTS.speak()` attempts a local `pythoncom.CoInitialize()` inside a nested try-block, but lacks corresponding `pythoncom.CoUninitialize()` in a `finally` block, violating COM apartment lifecycle discipline and causing leak/lockup or thread apartment mismatch across consecutive daemon thread invocations.

#### R3: P1-10 Faster-Whisper Pre-loading & VAD Trimming
- **File**: `jarvis/stt/engine.py` (L458–L533)
  - `FasterWhisperSTT.__init__()` initializes `self._model = None` and defers model instantiation until `_get_model()` is called during the first `transcribe()` invocation.
  - This lazy loading strategy induces a severe cold-start latency spike ($2.0\text{s} - 5.0\text{s}$) on the user's first spoken command.
- **File**: `jarvis/stt/engine.py` (L557–L576)
  - In `FasterWhisperSTT.transcribe()`, `model.transcribe()` is called with `condition_on_previous_text=False`, `no_speech_threshold=0.6`, `log_prob_threshold=-1.0`, `compression_ratio_threshold=2.4`, but does **not** specify `vad_filter=True` or `vad_parameters={"min_silence_duration_ms": 500}`.
  - Leading and trailing silence frames are currently passed into the CTranslate2 neural network, wasting computation and increasing transcription latency.

#### R4: P1-6 & P1-7 HUD Overlay Non-Blocking & System Tray Controls
- **File**: `jarvis/ui/overlay.py` (L448–L500, L1820–L1837)
  - `AlwaysOnOverlay.start()` launches a dedicated daemon thread (`JARVIS-AlwaysOnOverlay`) executing `_run_tk()`.
  - `_schedule(fn)` routes all mutations through `self._root.after(0, fn)` (or direct execution in headless mode).
- **File**: `jarvis/ui/tray.py` (L204–L230)
  - `SystemTrayController._start_pystray()` constructs a menu with 13 items (`Toggle HUD Overlay`, `Morning Briefing`, `Focus Mode`, `System Health Status`, `Mute Microphone`, `Toggle Hand Gestures`, `Toggle Wake Word`, `Open Dashboard`, `Settings`, `View Logs`, `Reload Config`, `Exit`).
  - However, R4 specifies a dedicated **"Status"** menu item displaying a concise system summary: version (v4.7.0), TTS engine state, STT model state, and RAM usage.

#### R5: P1-11 Hardware Voice Reporting & Intent Routing
- **File**: `jarvis/hardware/reporter.py` (L41–L110)
  - `HardwareReporter.format_voice_summary(metrics, lang="vi")` formats: CPU usage %, CPU temperature, RAM usage %, Storage SMART status.
  - `HardwareReporter.format_component_summary(component, ...)` supports targeted inquiries (`cpu`, `ram`, `gpu`, `disk`).
- **File**: `jarvis/llm/router.py` (L470–L505, L1075–L1085, L1245–L1250)
  - Router maps general queries (`"tình trạng hệ thống"`, `"tình trạng máy"`, `"trạng thái máy tính"`, `"kiểm tra hệ thống"`) to `hardware_status_query` / `system_status`.
  - However, explicit queries requested in R5:
    1. `"cpu mấy phần trăm"`
    2. `"ram còn bao nhiêu"`
    3. `"nhiệt độ máy"`
    4. `"pin còn bao nhiêu"`
    5. `"tốc độ cpu"`
    need comprehensive rule and regex mappings to `system_status` (covering both Vietnamese diacritics and no-diacritics variants).

#### R6: Test Suite Integrity & Release
- **File**: `jarvis/__init__.py` (L12)
  - Currently `__version__ = "4.6.0"`. Must be bumped to `"4.7.0"`.
- **File**: `CHANGELOG.md`
  - Needs comprehensive `[4.7.0] - 2026-09-02` release notes section detailing all Sprint 2 deliverables.
- **Evaluation**:
  - `tests/eval/routing_eval_n150.py` must maintain `SILENT_FAILURE <= 5.0%` (target 0%) and `MISROUTED == 0`.

---

## 2. Logic Chain

1. **Acoustic Hardening & Echo Elimination (R1)**:
   - *Observation*: During and after TTS speech output, speaker audio radiates into the microphone. An energy-based acoustic fallback or Vosk detector can trigger on JARVIS's own synthesized voice.
   - *Logic*: By adding a hardware/application-level gate in `app.py` and `wake_word.py`:
     1. Whenever `TTSManager` is actively speaking (`is_speaking == True`), and for **exactly 2.5s cooldown** after speech completion (`time.monotonic() - last_tts_finish_time < 2.5`), drop or bypass incoming audio blocks completely before they reach the detector.
     2. Integrate `VoiceActivityDetector` (`jarvis.audio.vad`) into `WakeWordDetector.feed_audio_block()` to reject non-speech frames immediately with minimal compute ($<0.1\text{ms}$ per 40ms frame).
     3. Verify SFM thresholds ($[0.03, 0.65]$) and ZCR ($\ge 0.10$) against synthetic and natural speech formants to prevent regression on real Vietnamese voices while blocking claps and tones.

2. **COM Apartment Concurrency Safety (R2)**:
   - *Observation*: Windows SAPI5 COM calls require the calling thread to be registered in a COM apartment via `CoInitialize()`. Background daemon threads created by Python `threading.Thread` do not have COM initialized by default.
   - *Logic*: Placing `pythoncom.CoInitialize()` at the entry of the TTS worker loop and wrapping the execution block in `try ... finally: pythoncom.CoUninitialize()` guarantees that COM is initialized once per worker thread and properly torn down upon shutdown. Safeguarding inside `SAPI5FallbackTTS.speak()` handles ad-hoc thread invocations.

3. **STT Cold-Start & Latency Optimization (R3)**:
   - *Observation*: Initializing CTranslate2 `WhisperModel` involves reading multi-megabyte model weights into CPU/GPU RAM, taking 2–5 seconds. If done synchronously on the first voice utterance, the user perceives the assistant as frozen or dead.
   - *Logic*:
     1. In `FasterWhisperSTT.__init__()`, spawn a background daemon thread (`WhisperPreloadWorker`) to initialize and warm up `WhisperModel`.
     2. `_get_model()` coordinates via `threading.Lock` / `threading.Event`, waiting for preload if called while loading. Subsequent calls return the cached warm model instantly ($\le 1\text{ms}$).
     3. Enabling `vad_filter=True` with `vad_parameters={"min_silence_duration_ms": 500}` inside `model.transcribe()` strips leading and trailing silence before audio enters the transformer layers, reducing compute and lowering 3-second audio transcription latency to $\le 1.5\text{s}$ on CPU ($\le 800\text{ms}$ on GPU).

4. **UI Thread Confinement & Tray Telemetry (R4)**:
   - *Observation*: Tkinter is not thread-safe. Invoking Tk widget methods from worker threads causes intermittent segmentation faults or GUI freezes on Windows.
   - *Logic*:
     1. `AlwaysOnOverlay` must confine all Tkinter widget creation and manipulation to the dedicated GUI thread via `_schedule()` / `root.after(0, ...)`.
     2. Add a dynamic **"Status"** item to `SystemTrayController` that computes and formats version, TTS engine, STT model readiness, and RAM usage on demand without blocking the tray event loop.

5. **Hardware Intent Routing (R5)**:
   - *Observation*: Users formulate hardware inquiries in various natural forms (e.g. `"cpu mấy phần trăm"`, `"ram còn bao nhiêu"`, `"nhiệt độ máy"`, `"pin còn bao nhiêu"`, `"tốc độ cpu"`).
   - *Logic*: Adding regex rules with word boundaries (`\b`) and unaccented/accented variations in `jarvis/llm/router.py` maps these queries directly to `system_status` (or `hardware_status_query`) in Tier 1 Fast-Path with $O(1)$/$O(N)$ evaluation, achieving $\text{MISROUTED} = 0$ and $\text{SILENT} = 0$. Connecting `app._handle_system_status()` to `HardwareReporter.format_voice_summary()` ensures natural spoken output.

6. **Release & Quality Gate (R6)**:
   - *Observation*: Sprint 2 requires zero test failures and full backward compatibility.
   - *Logic*: Executing unit tests, adversarial tests, and `routing_eval_n150.py`, bumping version to `4.7.0`, and documenting changes in `CHANGELOG.md` fulfills the Sprint 2 release contract.

---

## 3. Caveats & Assumptions

1. **Optional Dependency Degradation**:
   - `vosk`: If `models/vosk-model-small-vn-0.4` is not present, `WakeWordDetector` gracefully cascades to `WhisperSlidingWindowDetector` (Tier 1.5) and `AcousticSpectralDetector` (Tier 2).
   - `webrtcvad`: If `webrtcvad` C-extension is not installed, `VoiceActivityDetector` transparently falls back to energy-based RMS thresholding (`silence_threshold=0.01`).
   - `pystray` / `PIL`: In headless CI or non-GUI environments, `SystemTrayController` and `AlwaysOnOverlay` operate in headless mock mode without crashing.
2. **Platform Specifics**:
   - Windows COM (`win32com.client`, `pythoncom`) is only available on `sys.platform == "win32"`. On Linux/macOS or CI environments without win32com, fallback to pyttsx3 or mock logger is invoked.
   - Hardware telemetry uses Win32 API ctypes (`GlobalMemoryStatusEx`, `GetSystemTimes`, `GetSystemPowerStatus`) with fallback to `psutil` or mock telemetry.
3. **GPU vs CPU STT**:
   - CUDA is auto-detected via `torch.cuda.is_available()` / `ctranslate2.get_cuda_device_count()`. If CUDA libraries (cublas64_12.dll) are missing, system falls back to `device="cpu"`, `compute_type="int8"` without crashing.

---

## 4. Conclusion: Structured Requirements & Specifications Matrix

### 4.1 Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|---|---|---|---|---|---|---|
| **F-01** | Acoustic / DSP | Voice Activity Detection (VAD) Filter Gate | Pre-filters raw audio blocks using RMS energy or WebRTC VAD before feeding wake word detector | `np.ndarray` (16kHz/44.1kHz PCM) | `bool` (is_speech) | Silent/low-energy frames dropped immediately ($<0.1\text{ms}$) | `ORIGINAL_REQUEST.md` §R1, `ROADMAP.md` P1-8 |
| **F-02** | Acoustic / DSP | 2.5s Post-TTS Echo Lockout & Mic Suppression | Disables audio block ingestion during TTS output and for exactly 2.5s after TTS finishes | Audio block + TTS playback state / timestamp | Blocks suppressed / dropped | Audio dropped safely, timer resets on new TTS | `ORIGINAL_REQUEST.md` §R1, `ROADMAP.md` P1-8 |
| **F-03** | Acoustic / DSP | Spectral Formant & SFM Threshold Hardening | Multi-band STFT analysis with SFM $[0.03, 0.65]$ and ZCR $\ge 0.10$ for synthetic and real speech | Sliding ring buffer (1.0–1.5s float32) | `(detected, keyword, confidence)` | Rejects pure tones ($<0.03$), white noise ($>0.65$), claps ($<0.05\text{s}$) | `jarvis/audio/wake_word.py`, `ROADMAP.md` P1-8 |
| **F-04** | TTS / COM | Worker Thread COM Initialization | Calls `pythoncom.CoInitialize()` at start of TTS worker thread and `CoUninitialize()` in finally | Worker thread lifecycle | Initialized STA/MTA COM apartment | Falls back to PowerShell / pyttsx3 on error | `ORIGINAL_REQUEST.md` §R2, `ROADMAP.md` P1-9 |
| **F-05** | TTS / COM | SAPI5 Speech Synthesizer Invocation | Invokes `win32com.client.Dispatch("SAPI.SpVoice")` to speak Vietnamese / English phrases | `text: str`, `voice_id: str`, `wait: bool` | `bool` (success) | Falls back to PowerShell Base64 if COM dispatch fails | `jarvis/tts/fallback.py`, `ROADMAP.md` P1-9 |
| **F-06** | STT Engine | Background Eager Model Pre-loading | Spawns background thread on `FasterWhisperSTT.__init__()` to load CTranslate2 model into memory | Config (`model_size`, `device`, `compute_type`) | Warm `WhisperModel` instance | Synchronous fallback if preload thread still running | `ORIGINAL_REQUEST.md` §R3, `ROADMAP.md` P1-10 |
| **F-07** | STT Engine | VAD-based Silence Trimming in STT | Configures `vad_filter=True` and `min_silence_duration_ms=500` in Faster-Whisper transcription | Audio array (16kHz float32) | Transcribed text (`str`) | Returns empty string on complete silence | `ORIGINAL_REQUEST.md` §R3, `ROADMAP.md` P1-10 |
| **F-08** | UI / HUD | Thread-Safe Tkinter Overlay Mutation | Dispatches all UI updates through `_schedule()` / `root.after(0, fn)` without blocking audio loop | UI event / text update callable | Updated HUD graphics | Runs directly in headless mode if GUI unavailable | `ORIGINAL_REQUEST.md` §R4, `ROADMAP.md` P1-6 |
| **F-09** | UI / Tray | Dynamic Tray Context Menu & Status Item | Taskbar tray controller with toggles (Wake Word, Mic, Gestures) and new "Status" summary | Tray menu clicks / events | Status tooltip, icon update, action trigger | Graceful fallback to Win32 ctypes or headless | `ORIGINAL_REQUEST.md` §R4, `ROADMAP.md` P1-7 |
| **F-10** | Hardware | Vietnamese Hardware Voice Summary | Formats natural Vietnamese speech summary containing CPU%, RAM%, GPU temp, SMART status | `HardwareMetrics` or live probe | Formatted Vietnamese speech text | Returns fallback safe string on probe exception | `ORIGINAL_REQUEST.md` §R5, `ROADMAP.md` P1-11 |
| **F-11** | Router / LLM | Hardware Query Intent Rules (5 Utterances) | Maps 5 hardware query utterances and no-diacritic forms to `system_status` with $\text{MISROUTED}=0$ | User transcript string | `IntentResult(action="system_status")` | Falls back to Tier 2 LLM if no regex matches | `ORIGINAL_REQUEST.md` §R5, `ROADMAP.md` P1-11 |
| **F-12** | Release / QA | Test Suite & Benchmark Quality Gate | Verifies 0 test failures, routing eval SILENT $\le 5\%$, MISROUTED $= 0$, version bump to 4.7.0 | Test runner commands | Pytest test results & eval reports | Fails build if regressions detected | `ORIGINAL_REQUEST.md` §R6, `ROADMAP.md` P0-5 |

---

### 4.2 Edge Cases Matrix

| # | Feature | Input / Condition | Observed / Required Behavior |
|---|---|---|---|
| **E-01** | VAD Pre-filter | Pure silence ($RMS < 0.001$) or low background hum ($RMS < 0.008$) | Frame dropped immediately; ring buffer not updated; 0 CPU STFT computed |
| **E-02** | Echo Suppression | User speaks immediately ($1.0\text{s}$) after JARVIS TTS output finishes | Block is suppressed by 2.5s lockout window to prevent false trigger from reverberation |
| **E-03** | Echo Suppression | User speaks after $2.6\text{s}$ following TTS completion | Block is processed normally through VAD and wake word detection pipeline |
| **E-04** | COM Safety | TTS worker thread spawned, 10 consecutive phrases spoken in rapid succession | All 10 phrases synthesize without `CoInitialize has not been called` com_error |
| **E-05** | COM Safety | Non-Windows (Linux/macOS) execution of `SAPI5FallbackTTS` | `pythoncom` import caught; falls back to `pyttsx3` or mock logger without exception |
| **E-06** | STT Preload | `FasterWhisperSTT.transcribe()` called before preload thread finishes | Thread lock/event waits for preload to complete or loads model safely under lock |
| **E-07** | STT Trimming | 3-second audio containing 2.5s silence + 0.5s speech | `vad_filter=True` strips silence; transcription finishes in $\le 500\text{ms}$ |
| **E-08** | Overlay Non-Blocking | Heavy animation (breathing glow + 11-bar waveform) active during voice record | `sounddevice` audio recording callback maintains regular 40ms intervals without audio buffer drop |
| **E-09** | Tray Menu Status | User clicks "Status" menu item on tray | Displays or logs: `JARVIS v4.7.0 | TTS: Ready | STT: Faster-Whisper (base) | RAM: X%` |
| **E-10** | Hardware Router | User speaks `"cpu mấy phần trăm"` or unaccented `"cpu may phan tram"` | Router returns `action_name="system_status"` (or `hardware_status_query`) with confidence $\ge 0.95$ |
| **E-11** | Hardware Router | User speaks `"ram còn bao nhiêu"` or `"ram con bao nhieu"` | Router returns `action_name="system_status"` with confidence $\ge 0.95$ |
| **E-12** | Hardware Router | User speaks `"nhiệt độ máy"` or `"nhiet do may"` | Router returns `action_name="system_status"` with confidence $\ge 0.95$ |
| **E-13** | Hardware Router | User speaks `"pin còn bao nhiêu"` or `"pin con bao nhieu"` | Router returns `action_name="system_status"` with confidence $\ge 0.95$ |
| **E-14** | Hardware Router | User speaks `"tốc độ cpu"` or `"toc do cpu"` | Router returns `action_name="system_status"` with confidence $\ge 0.95$ |

---

### 4.3 Interface & Contract Specifications

#### 1. Audio Engine & Wake Word Acoustic Gate
```python
class WakeWordDetector:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        callback: Callable[[], None] | None = None,
        on_wake_word: Callable[[str, float], None] | None = None,
        vad_detector: VoiceActivityDetector | None = None,
    ) -> None: ...

    def feed_audio_block(
        self,
        block: np.ndarray | None,
        timestamp: float | None = None,
        is_speech: bool | None = None,
    ) -> WakeWordResult | None: ...
```

#### 2. TTS Manager COM Thread Safety Contract
```python
class TTSManager:
    def _process_queue(self) -> None:
        """
        Worker thread loop.
        Must call pythoncom.CoInitialize() on Windows before loop,
        and pythoncom.CoUninitialize() in finally block.
        """
        ...
```

#### 3. FasterWhisperSTT Eager Pre-load & VAD Contract
```python
class FasterWhisperSTT(BaseSTTEngine):
    def __init__(self, config: dict[str, Any] | None = None, preload: bool = True) -> None: ...

    def transcribe(
        self,
        audio: np.ndarray | bytes | Path | io.BytesIO | str,
        language: str = "vi",
        vad_filter: bool = True,
        vad_parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str: ...
```

#### 4. Hardware Voice Reporter Contract
```python
class HardwareReporter:
    def format_voice_summary(
        self,
        metrics: HardwareMetrics | None = None,
        lang: str = "vi",
    ) -> str:
        """
        Returns:
            str: e.g. "Tình trạng hệ thống: CPU đang sử dụng 15 phần trăm. RAM đang sử dụng 45 phần trăm. Ổ đĩa trạng thái Good."
        """
        ...
```

#### 5. Router Hardware Query Rules Contract
```python
# In jarvis/llm/router.py:
# Mapping table entries:
"cpu mấy phần trăm": IntentResult(action_name="system_status", parameters={"component": "cpu"}, source="rule_fallback")
"ram còn bao nhiêu": IntentResult(action_name="system_status", parameters={"component": "ram"}, source="rule_fallback")
"nhiệt độ máy": IntentResult(action_name="system_status", parameters={"component": "temperature"}, source="rule_fallback")
"pin còn bao nhiêu": IntentResult(action_name="system_status", parameters={"component": "battery"}, source="rule_fallback")
"tốc độ cpu": IntentResult(action_name="system_status", parameters={"component": "cpu_freq"}, source="rule_fallback")
```

---

### 4.4 Latency Budgets & Threshold Parameters

| Metric / Parameter | Value | Scope | Rationale |
|---|---|---|---|
| **VAD Frame Evaluation Latency** | $< 0.1\text{ms}$ | Per 40ms frame (16kHz) | Zero overhead on main audio streaming thread |
| **Post-TTS Echo Lockout Cooldown** | **Exactly 2.5s** | Post-playback window | Triangulated from room acoustic reverberation tests |
| **STT Model Cold-Start (Post-preload)** | $\le 200\text{ms}$ | First `transcribe()` call | Model already loaded into RAM/VRAM |
| **STT Warm Transcription Latency** | $\le 1.5\text{s}$ (CPU INT8), $\le 800\text{ms}$ (GPU FP16) | 3-second audio segment | CTranslate2 + VAD silence trim |
| **Total Voice Turnaround Latency** | $< 1.5\text{s}$ | End of speech to audio playback | Full pipeline: VAD + STT + Router + Local TTS |
| **Acoustic SFM Upper Threshold** | $0.65$ | `AcousticSpectralDetector` | Blocks wideband white noise |
| **Acoustic SFM Lower Threshold** | $0.03$ | `AcousticSpectralDetector` | Blocks pure sine tones & narrow-band noise ($<0.03$) |
| **Acoustic ZCR Lower Threshold** | $0.10$ | S2 ("VIS") fricative | Detects high-frequency consonant burst |
| **Inter-syllable Gap Window** | $0.07\text{s} - 0.65\text{s}$ | S1 ("JAR") to S2 ("VIS") | Rejects simultaneous clap impulses ($<0.05\text{s}$) |
| **Tray Status Menu Items** | $\ge 4$ items | `SystemTrayController` | Includes Wake Word, Mic, Gestures, Status, Exit |

---

### 4.5 Dependency Mapping & Cross-Module Interactions

```
                ┌─────────────────────────────────────────────────────────────┐
                │                         JarvisApp                           │
                │                  (jarvis/core/app.py)                       │
                └──┬────────────────────────┬───────────────────────────┬─────┘
                   │                        │                           │
          (Audio Stream)              (TTS Speech)              (Status Inquiries)
                   │                        │                           │
                   ▼                        ▼                           ▼
        ┌─────────────────────┐   ┌───────────────────┐    ┌────────────────────────┐
        │     AudioEngine     │   │    TTSManager     │    │   LLMIntentRouter      │
        │(suppressed for 2.5s)│   │  (SAPI5 COM Safe) │    │  (5 Hardware Rules)    │
        └──────────┬──────────┘   └─────────┬─────────┘    └───────────┬────────────┘
                   │                        │                          │
                   ▼                        │                          ▼
        ┌─────────────────────┐             │              ┌────────────────────────┐
        │  WakeWordDetector   │◄────────────┘              │    HardwareReporter    │
        │ (VAD pre-filter)    │   (TTS Cooldown signal)    │ (format_voice_summary) │
        └──────────┬──────────┘                            └───────────┬────────────┘
                   │                                                   │
                   ▼                                                   ▼
        ┌─────────────────────┐                            ┌────────────────────────┐
        │   FasterWhisperSTT  │                            │     AlwaysOnOverlay    │
        │(Preload + VAD trim) │                            │    & SystemTray (UI)   │
        └─────────────────────┘                            └────────────────────────┘
```

---

## 5. Verification Method

To independently verify all Sprint 2 requirements during and after implementation:

### 5.1 Automated Pytest Commands
1. **Acoustic Hardening & Echo Suppression (R1)**:
   ```powershell
   pytest tests/unit/test_acoustic_hardening.py -v
   pytest tests/test_audio_dsp.py -v
   ```
   *Expected*: $\ge 5$ tests passing; VAD rejection of silent frames verified; 2.5s post-TTS microphone suppression verified.

2. **TTS COM Apartment Thread Safety (R2)**:
   ```powershell
   pytest tests/unit/test_tts_com_safety.py -v
   pytest tests/test_tts_engine.py -v
   ```
   *Expected*: $\ge 3$ tests passing; 10 consecutive TTS calls in background daemon thread without `CoInitialize` errors.

3. **Faster-Whisper Pre-load & VAD Trimming (R3)**:
   ```powershell
   pytest tests/unit/test_stt_preload.py -v
   pytest tests/unit/test_stt_engine.py -v
   ```
   *Expected*: $\ge 3$ tests passing; eager background preload verified; warm transcription latency $\le 1.5\text{s}$ for 3s audio; `vad_filter=True` active.

4. **HUD Overlay & Tray Controls (R4)**:
   ```powershell
   pytest tests/unit/test_tray_menu.py -v
   pytest tests/test_m3_ux.py -v
   pytest tests/test_adversarial_m3_ui_app.py -v
   ```
   *Expected*: $\ge 3$ tests passing; tray menu has $\ge 4$ items including "Status"; UI mutations routed through `_schedule()`.

5. **Hardware Voice Reporting & Router Intent (R5)**:
   ```powershell
   pytest tests/test_hardware_monitor.py -v
   pytest tests/unit/test_router_hardware.py -v
   ```
   *Expected*: 5 hardware utterances route to `system_status` with $\text{MISROUTED} = 0$; `format_voice_summary()` outputs valid string with CPU% and RAM%.

6. **Regression Gate & Benchmark (R6)**:
   ```powershell
   pytest tests/unit/ tests/test_adversarial_*.py -q
   python tests/eval/routing_eval_n150.py
   ```
   *Expected*: 0 pytest failures; `SILENT_FAILURE <= 5.0%` (target 0%), `MISROUTED == 0`.

---
*Report completed by Spec Miner agent `spec_miner_survey_1`.*
