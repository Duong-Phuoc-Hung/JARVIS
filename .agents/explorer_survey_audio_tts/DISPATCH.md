## 2026-09-02T07:31:41Z
You are the Audio & TTS Explorer for JARVIS Sprint 2 (v4.7.0).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\explorer_survey_audio_tts`
Please read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (mandatory source of truth).

Your objective is to investigate the existing audio, wake word, TTS, and STT components:
1. Examine `jarvis/audio/wake_word.py` and `jarvis/core/app.py`:
   - How is wake word detection currently implemented (Vosk, Faster-Whisper, energy/SFM/ZCR)?
   - How to implement energy-based or WebRTC VAD filter to discard silent/noise frames before wake word detection?
   - How is TTS echo suppression currently implemented? How to implement disabling/ignoring microphone frames for exactly 2.5s after TTS playback completes?
   - Review SFM/ZCR thresholds.
2. Examine `jarvis/tts/manager.py`:
   - How does `TTSManager` and `_worker_thread` handle SAPI5 and COM calls?
   - Where and how to add `pythoncom.CoInitialize()` and `pythoncom.CoUninitialize()` in finally blocks to ensure COM safety across daemon threads?
3. Examine `jarvis/stt/engine.py`:
   - How does `FasterWhisperSTT` initialize and transcribe?
   - How to implement background thread pre-loading on `__init__()`?
   - How to configure `vad_filter=True` and `vad_parameters={"min_silence_duration_ms": 500}`?
4. Check existing unit tests in `tests/unit/` for audio, TTS, and STT.
5. Provide precise implementation strategy and architectural recommendations.

Write your comprehensive report to:
`d:\Software GitCode\JARVIS\.agents\explorer_survey_audio_tts\handoff.md`
Maintain `progress.md` in your working directory.
When done, send a message back to the parent orchestrator with a summary and path to your handoff report.
