## 2026-08-22T02:07:13Z
You are Worker 1 for Milestone 3 (Voice AI, LLM Semantic Intent & UI Dashboard).
Working directory: d:/Software GitCode/JARVIS/.agents/worker_m3_1
Project Root: d:/Software GitCode/JARVIS
Virtualenv: d:/Software GitCode/JARVIS/.venv

Read these blueprint files before writing any code:
- d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md
- d:/Software GitCode/JARVIS/PROJECT.md
- d:/Software GitCode/JARVIS/.agents/sub_orch_m3/SCOPE.md
- d:/Software GitCode/JARVIS/.agents/explorer_m3_1/handoff.md (STT Engine blueprint)
- d:/Software GitCode/JARVIS/.agents/explorer_m3_2/handoff.md (LLM Engine & Router blueprint)
- d:/Software GitCode/JARVIS/.agents/explorer_m3_3/handoff.md (UI Tray, Dashboard & JarvisApp integration blueprint)

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Exclusive Write Ownership:
- jarvis/stt/__init__.py
- jarvis/stt/engine.py
- jarvis/llm/__init__.py
- jarvis/llm/client.py
- jarvis/llm/router.py
- jarvis/ui/__init__.py
- jarvis/ui/tray.py
- jarvis/ui/dashboard.py
- jarvis/core/app.py
- tests/test_llm_router.py
- tests/unit/test_stt_engine.py
- tests/unit/test_llm_engine.py
- tests/unit/test_ui_dashboard.py

Your Tasks:
1. Implement `jarvis/stt/__init__.py` and `jarvis/stt/engine.py` per explorer 1 blueprint:
   - `BaseSTTEngine`, `OpenAIWhisperSTT` (direct HTTP REST multipart), `FasterWhisperSTT` (local model with lazy load), `WindowsSpeechSTT` (PowerShell SAPI fallback), `MockSTTEngine` (deterministic test provider).
   - Universal audio conversion (`audio_to_float32`, `float32_to_pcm16_wav_bytes`, `resample_audio`) with pure NumPy linear interpolation.
   - `VADSegmenter` with pre-speech circular ring buffer (300ms), RMS threshold detection, silence trailing (800ms) cutoff, min/max speech limits.
   - Unified `STTEngine` coordinator supporting dynamic provider selection, fallback chains, `transcribe()`, `transcribe_stream()`, `is_speech_present()`, and `feed_audio_block()`.

2. Implement `jarvis/llm/__init__.py`, `jarvis/llm/client.py`, and `jarvis/llm/router.py` per explorer 2 blueprint:
   - `LLMClient`: Multi-provider REST client (`requests.Session`) for OpenAI, Gemini, Claude, Ollama, and Mock. Clean JSON normalization, rate limit/timeout retries, token usage estimation.
   - `generate_tool_schema_from_dispatcher()`: Inspects `ActionDispatcher` / `PluginRegistry` to generate OpenAI/Gemini/Claude function calling schemas.
   - `LLMIntentRouter`: Fast-path regex / keyword rule table for Vietnamese and English commands ("kiểm tra nhiệt độ cpu", "bật đèn phòng khách", "tình trạng hệ thống", "quét mạng nội bộ", "spotify", etc.), LLM semantic reasoning, graceful rule fallback on network/API failure, returning `IntentResult`.

3. Implement `jarvis/ui/__init__.py`, `jarvis/ui/tray.py`, and `jarvis/ui/dashboard.py` per explorer 3 blueprint:
   - `SystemTrayController`: Dynamic status icon creation (Pillow/ctypes), 3-tier fallback (pystray -> pure Win32 -> headless mock), context menu handlers (mute mic, toggle gestures, open dashboard, reload config, view logs, quit), `update_status()`.
   - `DashboardServer` & `DashboardMetricsServer`: stdlib `http.server.ThreadingHTTPServer` serving embedded HTML5/CSS3/JS dark HUD UI, optional `websockets` broadcast with HTTP polling fallback, REST endpoints (`/api/status`, `/api/telemetry`, `/api/actions`, `/api/config`, `/api/command`, `/api/logs`).

4. Update `jarvis/core/app.py`:
   - Wire STTEngine, LLMIntentRouter, SystemTrayController, DashboardServer into `JarvisApp`.
   - Implement the complete end-to-end voice loop: acoustic gesture / wake trigger -> listen audio -> STT transcribe -> LLM intent parse -> ActionDispatcher execute -> TTS vocalize response.
   - Ensure clean daemon startup and graceful teardown of all threads and servers.

5. Implement Comprehensive Unit & Integration Tests:
   - Update `tests/test_llm_router.py` to maintain compatibility with existing test contract while verifying full multi-provider functionality.
   - Add `tests/unit/test_stt_engine.py` testing audio conversions, VAD segmentation, multi-provider fallbacks, and error resilience.
   - Add `tests/unit/test_llm_engine.py` testing OpenAI, Gemini, Claude, Ollama request formatting, mock behaviors, tool schema generation, and two-tier intent routing.
   - Add `tests/unit/test_ui_dashboard.py` testing tray controller status transitions, dashboard HTTP server endpoints, telemetry broadcast, and command dispatch.

6. Verification:
   - Execute: `& "d:\Software GitCode\JARVIS\.venv\Scripts\python.exe" -m pytest tests/ tests/unit/ -v`
   - Ensure 100% test pass across the entire suite (including existing M1 and M2 tests) with 0 failures, 0 errors.

Write your completion report to `d:/Software GitCode/JARVIS/.agents/worker_m3_1/handoff.md` and send a message when complete.
