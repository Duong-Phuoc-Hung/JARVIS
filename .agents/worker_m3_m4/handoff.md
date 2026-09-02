# Handoff Report: Faster-Whisper Model Preloading & VAD Trimming (R3) and HUD Thread Isolation & System Tray Status (R4)

**Worker**: Worker M3 & M4 (`worker_m3_m4`)  
**Roles**: implementer, qa, specialist  
**Date**: 2026-09-02  
**Target Milestone**: JARVIS v4.7.0 Sprint 2  

---

## 1. Observation

1. **FasterWhisperSTT Lazy Loading & Missing VAD Trimming (`jarvis/stt/engine.py:455-580`)**:
   - Previously, `FasterWhisperSTT.__init__()` set `self._model = None` without eager instantiation, causing a 2–5s cold-start latency spike on the first call to `transcribe()`.
   - In `FasterWhisperSTT.transcribe()`, `model.transcribe()` did not configure or pass `vad_filter` or `vad_parameters`, causing Faster-Whisper to transcribe unnecessary silence frames.
2. **System Tray Missing Path Import & Dynamic Status Item (`jarvis/ui/tray.py:8-16, 113-128, 343-351`)**:
   - `tray.py:344` used `Path(_apd2) / "JARVIS" / "logs" / "jarvis.log"`, but `from pathlib import Path` was missing from module imports, causing `NameError: name 'Path' is not defined` whenever `_on_view_logs` was invoked on Windows with `%LOCALAPPDATA%` set.
   - `SystemTrayController` lacked a dynamic "Status" menu item displaying current version (`v4.7.0`), TTS status, STT model readiness, and RAM usage.
3. **HUD Overlay Thread Isolation (`jarvis/ui/overlay.py:448-469, 1820-1837`)**:
   - Verified `AlwaysOnOverlay.start()` runs on dedicated background daemon thread `"JARVIS-AlwaysOnOverlay"`.
   - Public UI mutation methods (`show_listening`, `show_thinking`, `show_response`, `show`, `hide`, `update_task_dag`, `append_code_log`, `display_visual_result`, `toggle_sidebar`, etc.) strictly marshal via `self._schedule(callable)` calling `self._root.after(0, fn)` or direct execution in headless mode, maintaining complete isolation from the real-time audio loop.

---

## 2. Logic Chain

1. **R3 (Faster-Whisper Preloading & VAD Trimming)**:
   - In `FasterWhisperSTT.__init__()`, when `self.config.get("preload", True)` and `FASTER_WHISPER_AVAILABLE` are True, spawned background daemon thread `_preload_thread = threading.Thread(target=self._get_model, name="FasterWhisper-Preload", daemon=True)`.
   - In `_get_model()`, wrapped model instantiation within `with self._lock:` and a try-except block so concurrent callers block safely and receive the cached `self._model` instance.
   - Added property `is_model_loaded -> bool` returning `self._model is not None`.
   - In `FasterWhisperSTT.transcribe()`, extracted `vad_filter` (default: `True`) and `vad_parameters` (default: `{"min_silence_duration_ms": 500}`) and passed them to `model.transcribe()`.
2. **R4 (HUD Overlay & System Tray Controls)**:
   - Added `from pathlib import Path` to imports in `jarvis/ui/tray.py`, fixing `_on_view_logs`.
   - Implemented `SystemTrayController.get_status_text(item=None) -> str` dynamically formatting `f"Status: v{ver} | TTS: {tts_st} | STT: {stt_st} | RAM: {ram_str}"`.
   - Added `"Status"` to `self.menu_items` (menu length >= 4) and wired `pystray.MenuItem(self.get_status_text, None, enabled=False)` as the primary header in `pystray.Menu`.
   - Verified `AlwaysOnOverlay` thread safety and Tkinter dispatch mechanics.

---

## 3. Caveats

- **GPU vs CPU Whisper**: On systems without CUDA 12.x or `nvidia-cublas-cu12`, `FasterWhisperSTT._resolve_device()` automatically falls back to CPU `int8`. The preload thread functions identically across CPU and GPU configurations.
- **Headless CI Environments**: In headless Linux / CI environments where GUI displays are absent, both `AlwaysOnOverlay` and `SystemTrayController` gracefully detect headless mode and execute callbacks without display errors.

---

## 4. Conclusion

- **R3 & R4 are fully implemented and verified**:
  - `jarvis/stt/engine.py`: Eager daemon preloading active, VAD filtering active.
  - `jarvis/ui/tray.py`: `Path` imported, dynamic status item active, menu length >= 4.
  - `jarvis/ui/overlay.py`: Thread isolation verified.
  - Unit tests in `tests/unit/test_stt_engine.py`, `tests/unit/test_stt_preload.py`, `tests/unit/test_ui_dashboard.py`, and `tests/unit/test_tray_menu.py` pass 100% (32 passed, 0 failures).
  - Extended UI and STT test suite (84 tests) passes 100% (84 passed, 0 failures).

---

## 5. Verification Method

To independently verify the implementation:

```powershell
pytest tests/unit/test_stt_engine.py tests/unit/test_stt_preload.py tests/unit/test_ui_dashboard.py tests/unit/test_tray_menu.py -v
```

Extended verification across UI and STT subsystems:
```powershell
pytest tests/unit/test_always_on_overlay.py tests/unit/test_hud_telemetry_and_memory.py tests/unit/test_stt_engine.py tests/unit/test_stt_preload.py tests/unit/test_ui_dashboard.py tests/unit/test_tray_menu.py -v
```

### Invalidation Conditions
- `FasterWhisperSTT.__init__()` fails to start daemon thread when `preload=True`.
- `model.transcribe()` is called without `vad_filter=True` or `vad_parameters={"min_silence_duration_ms": 500}`.
- `SystemTrayController.get_status_text()` raises exception or omits version, TTS, STT, or RAM status.
- `_on_view_logs` triggers `NameError` on `Path`.
