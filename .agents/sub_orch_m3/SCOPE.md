# Scope: Milestone 3 — Voice AI, LLM Semantic Intent & UI Dashboard

## Architecture
Milestone 3 equips JARVIS with bidirectional voice conversation, multi-provider LLM reasoning with tool-calling schema generation, Windows taskbar system tray controller, and an interactive real-time Web/WebSocket dashboard.

```
Voice AI & UI Dashboard Architecture (Milestone 3)
========================================================================================
[AudioEngine / Mic] ──> [VAD / Buffer Slice] ──> [STTEngine] (Local/Whisper REST/Windows)
                                                        │ (Transcript)
                                                        ▼
                                             [LLMIntentRouter]
                                             ├── Fast Rule Engine (Regex/Lookup)
                                             └── [LLMClient] (OpenAI / Gemini / Claude / Ollama)
                                                        │ (Tool Calls / Natural Response)
                                                        ▼
                                             [ActionDispatcher]
                                             ├── Execute Plugin Actions (Spotify, Chrome, etc.)
                                             └── Send Speech Text ──> [TTSManager] (ElevenLabs/SAPI5)

[SystemTrayController] (pystray / Win32 fallback) <──> [JarvisApp Core]
                                                               │ (Status & Telemetry)
                                                               ▼
                                                  [DashboardServer] (http.server + ws)
                                                  ├── REST API (/api/status, /api/telemetry, etc.)
                                                  └── WebSocket Live Telemetry & Event Stream
```

## Feature Inventory
| # | Feature | Target Modules | Status |
|---|---------|----------------|--------|
| F-14 | Speech-to-Text (STT) Engine | `jarvis/stt/engine.py`, `jarvis/stt/__init__.py` | IN_PROGRESS |
| F-15 | LLM Semantic Intent Engine | `jarvis/llm/client.py`, `jarvis/llm/router.py`, `jarvis/llm/__init__.py` | IN_PROGRESS |
| F-16 | System Tray Controller | `jarvis/ui/tray.py`, `jarvis/ui/__init__.py` | IN_PROGRESS |
| F-17 | Real-Time Dashboard | `jarvis/ui/dashboard.py`, `jarvis/ui/static/*` | IN_PROGRESS |
| Integration | Core App Lifecycle Wiring | `jarvis/core/app.py`, `jarvis/__main__.py`, `tests/test_llm_router.py` | IN_PROGRESS |

## Interface Contracts

### `jarvis.stt.engine.STTEngine`
- `transcribe(audio: Union[np.ndarray, bytes, Path], language: str = "vi") -> str`
- `transcribe_stream(audio_generator: Iterator[np.ndarray]) -> str`
- `is_speech_present(audio_buffer: np.ndarray) -> bool`

### `jarvis.llm.client.LLMClient`
- `generate(prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict]] = None) -> LLMResponse`
- `chat(messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None) -> LLMResponse`
- `generate_tool_schema(plugins: List[BasePlugin]) -> List[Dict[str, Any]]`

### `jarvis.llm.router.LLMIntentRouter`
- `parse_intent(user_input: str, available_actions: Optional[List[str]] = None) -> IntentResult`
- `execute_intent(intent: IntentResult) -> ActionResult`

### `jarvis.ui.tray.SystemTrayController`
- `start(in_thread: bool = True) -> None`
- `stop() -> None`
- `update_status(status: str) -> None`  # Active, Muted, Listening, Error

### `jarvis.ui.dashboard.DashboardServer`
- `start(host: str = "127.0.0.1", port: int = 8080) -> None`
- `stop() -> None`
- `broadcast_event(event: Dict[str, Any]) -> None`
- `broadcast_telemetry(metrics: Dict[str, Any]) -> None`

## Verification Strategy
- Comprehensive unit tests covering all features across Tiers 1-4.
- Deterministic synthetic mocking for speech audio, cloud LLM REST responses, tray callbacks, and WebSocket push.
- Adversarial challenger stress testing (concurrent requests, timeout recovery, malformed payloads, rate limiting).
- Forensic auditor verification against hardcoded strings, fake facades, and shortcuts.
