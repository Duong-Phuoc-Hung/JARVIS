# Rebuilding JARVIS Orchestration Plan

## 1. Survey & Discovery Phase
- Dispatch 3 parallel explorers/spec miners:
  - Explorer 1 (`.agents/explorer_survey_1`): Deep-dive into existing `jarvis-main/jarvis.py` to extract all active logic, .env dependencies, thread handling, audio thresholds, subprocess calls, and edge cases.
  - Explorer 2 (`.agents/explorer_survey_2`): Investigate environment dependencies, installed packages in `.venv`, Windows APIs (pywin32, ctypes, registry, subprocess, psutil, pycaw), and hardware/camera capabilities.
  - Spec Miner 3 (`.agents/spec_miner_survey_3`): Map out exhaustive requirements R1-R15, acceptance criteria, and create the detailed Feature Inventory for `PROJECT.md` and `TEST_INFRA.md`.

## 2. Decomposition & Architecture Setup Phase
- Synthesize survey reports into `PROJECT.md` and `TEST_INFRA.md`.
- Define module boundaries, interfaces, and directory layout (`jarvis/core`, `jarvis/audio`, `jarvis/vision`, `jarvis/security`, `jarvis/hardware`, `jarvis/smart_home`, `jarvis/comms`, `jarvis/automation`, `jarvis/data_analysis`, `jarvis/ui`, `jarvis/plugins`, etc.).
- Establish Dual Tracks:
  - Track A: Implementation Track (Milestone Sub-orchestrators / Worker cycles)
  - Track B: E2E Testing Track (Test Suite Runner & Tiers 1-4 Test Cases)

## 3. Execution Phase
- Milestone 1: Core Framework (Config Manager with hot-reload, Logging, Plugin Architecture, Event/Action Dispatcher, CLI/Tray Entry).
- Milestone 2: Audio & Voice Engine (PyAudio stream, Clap/Pattern Detector, Speech-to-Text, LLM Client [OpenAI/Gemini/Claude], ElevenLabs/Fallback TTS).
- Milestone 3: Hardware Monitor & Healing Protocol (CPU/GPU temp, fan, RAM/VRAM, disk S.M.A.R.T., auto-kill unresponsive processes, voice alert).
- Milestone 4: Vision & Biometrics (Face recognition + bypass mode + lockdown, MediaPipe Hand tracking & gestures).
- Milestone 5: Communications Hub & Workspace Automation & Smart Home & Security Wrapper & Data Analysis (Telegram/Discord/IMAP, Home Assistant, Nmap/Wireshark subprocess wrapper, Workspaces VM/IDE launch, CSV analysis & doc report).
- Track B: E2E Test Suite Creation (Tiers 1-4 Test cases with >=15 passing unit & integration tests).

## 4. Verification & Hardening Phase
- Run full test suite (`python -m pytest`).
- Execute all review/challenge/forensic audit gates.
- Phase 2: Tier 5 Adversarial Coverage Hardening.
- Report completion to Sentinel with full evidence.
