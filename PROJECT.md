# Project: JARVIS Continuous Autonomous Self-Upgrading & Research Engine

## Architecture
The system architecture integrates five core subsystems to transition JARVIS into an autonomous, self-upgrading, commercial-grade personal AI assistant on Windows 10/11:
1. **Continuous Academic & Industry Tech Radar (`jarvis/web/tech_radar.py` & `jarvis/memory/sqlite_store.py`):**
   - Autonomous ingestion client querying ArXiv Atom 1.0 (`cs.AI`, `cs.CL`, `cs.SD`, `eess.AS`), IEEE, and GitHub Trending feeds via zero-dependency `urllib.request` and `xml.etree.ElementTree`.
   - SQLite Continuous Learning Memory Graph (`knowledge_nodes`, `knowledge_edges`, `tech_radar_blips`) in WAL mode with relational indexing.
2. **Windows Atomic Persistence Layer (`jarvis/utils/atomic_io.py` & core stores):**
   - Strict 4-step Windows atomic persistence: thread serialization via `_save_lock = threading.Lock()`, fast RAM snapshot under `with self._lock:`, collision-proof temporary file `.tmp.<thread_id>.<timestamp_ns>`, and 5-retry loop for `WinError 5: Access is denied` with exponential backoff (`time.sleep(0.02 * attempt)`) and cleanup in `finally:`.
3. **Low-Latency Voice & Hybrid Routing Subsystem (`jarvis/voice/`, `jarvis/audio/`, `jarvis/llm/`):**
   - Full-duplex `RealtimeVoiceSession` bridged to `AudioEngine` in `jarvis/core/app.py`.
   - Continuous barge-in via Acoustic Front-End (AFE) bandpass filter and RMS voice activity detection, eliminating blocking half-duplex turn-taking and reducing E2E turn latency to < 500ms.
   - Sub-2ms on-device Hybrid Semantic Router combining TF-IDF cosine similarity and typed slot extraction to bypass cloud LLMs for 90%+ local commands.
4. **Test-Time Compute (TTC) Sandbox & Self-Healing Loop (`tests/unit/`, `jarvis/core/`):**
   - Clean-machine unit test execution across all 156 test suites (3,072 tests) with 100% pass rate.
   - Seam-first TDD patch for unmocked hardware calls and acoustic DC attenuation.
   - Fail-closed error signaling across all communications and hardware adapters.
5. **Commercial Standalone Packaging & Automation Sidecar (`installer/`, `scripts/`, `sidecar.json`):**
   - Windows standalone application bundle (`--onedir` with Inno Setup) eliminating `%TEMP%` extraction overhead.
   - Fixed entrypoints: `main_tray` in `jarvis/__main__.py` and `--tray` in `jarvis/cli.py`.
   - Scheduled Automation Sidecar (`sidecar.json`) running daily at 09:00 AM VN (`Asia/Ho_Chi_Minh`).
   - Truthful documentation synchronization under Five-Tier Verdict Discipline.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Unit Test Suite Blocker Fix | Patch `tests/unit/test_adversarial_challenger_m1_sample_rate.py` (mock `sounddevice.rec`, synthesize active sine wave, align silence chunks to 5) so all 156 test suites pass 100%. | M1 | Survey (Codebase) |
| F2 | Windows Atomic Persistence Standardization | Refactor 9 non-compliant/partial modules (`vision/biometrics.py`, `skills/telemetry.py`, `skills/macro_recorder/`, `smart_home/discovery.py`, `skills/registry.py`, `workers/night_shift.py`, `comms/mobile_bridge.py`, `ui/setup_wizard.py`, `tts/cache.py`) to strict 4-step Section 3 AGENTS.md pattern. | M2 | Survey (Codebase) |
| F3 | Fail-Closed Comms Remediation | Fix `jarvis/comms/telegram.py` `handle_inbound_voice` to return `STT_UNAVAILABLE` on transcription error instead of hardcoded fake text `"Lệnh thoại đã nhận"`. | M1 | Survey (Codebase) |
| F4 | Full-Duplex Real-Time Voice Bridge & Barge-In | Bridge `RealtimeVoiceSession` to `jarvis/core/app.py`, remove unconditional mic frame dropping at lines 448-455, enable live barge-in during TTS playback, cutting E2E turn latency to < 500ms. | M4 | Survey (Tech Radar) |
| F5 | Sub-2ms On-Device Hybrid Semantic Router | Combine TF-IDF cosine similarity from `SemanticVectorStore` with typed slot extraction from `LocalSemanticRouter` in `jarvis/llm/semantic_router.py` to route local actions in < 2ms without cloud LLM roundtrip. | M4 | Survey (Tech Radar) |
| F6 | SQLite Continuous Learning Memory Graph | Add tables `knowledge_nodes`, `knowledge_edges`, and `tech_radar_blips` with foreign-key cascades, WAL mode, and typed search queries in `jarvis/memory/sqlite_store.py`. | M3 | Survey (Tech Radar) |
| F7 | Zero-Dependency Tech Radar Ingestion Client | Implement `ArxivIngestionClient` and GitHub Trending scraper in `jarvis/web/tech_radar.py` using `urllib.request` and `xml.etree.ElementTree` without third-party C-dependencies. | M3 | Survey (Tech Radar) |
| F8 | Packaging Entrypoints & Standalone Installer Script | Add missing `main_tray` to `jarvis/__main__.py` and `--tray` flag to `jarvis/cli.py`. Build standalone `--onedir` packaging script (`scripts/build_standalone_package.py`) with clean-machine compatibility. | M5 | Survey (Spec Miner) |
| F9 | Documentation Truth & Three-Tier Verdict Sync | Synchronize `CHANGELOG.md`, `README.md`, and `docs/ROADMAP.md` with true empirical numbers (156 test files, 3,072 tests, 0 security findings) and strict verdict tiers. | M5 | Survey (Spec Miner) |
| F10 | Scheduled Automation Sidecar Integration | Create `sidecar.json` configured for daily 09:00 AM VN (`Asia/Ho_Chi_Minh`) to autonomously execute radar scans, health checks, and continuous learning updates. | M5 | Survey (Spec Miner) |
| F11 | Comprehensive E2E Testing Suite (Tiers 1-4) & Adversarial Hardening (Tier 5) | Independent opaque-box test suite verifying all R1-R5 features across 4 tiers (55+ test cases) followed by Tier 5 adversarial stress testing and coverage audit. | M6 | Survey & Dual Track |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Test Suite Self-Healing & Fail-Closed Remediation | Fix test hang in `test_adversarial_challenger_m1_sample_rate.py`; fix Telegram `handle_inbound_voice` fail-closed flaw; achieve 100% unit test suite pass rate (156 files, 3,072 tests). | none | DONE |
| M2 | Windows Atomic Persistence Standardization | Implement shared helper or standardize 9 modules (`vision/biometrics`, `skills/telemetry`, `skills/macro_recorder`, `smart_home/discovery`, `skills/registry`, `workers/night_shift`, `comms/mobile_bridge`, `ui/setup_wizard`, `tts/cache`) to strict Section 3 AGENTS.md pattern. | M1 | DONE |
| M3 | Continuous Learning Vault & Tech Radar Ingestion | Implement `knowledge_nodes`, `knowledge_edges`, and `tech_radar_blips` in `jarvis/memory/sqlite_store.py`; implement `ArxivIngestionClient` in `jarvis/web/tech_radar.py` and verify paper ingestion into memory graph. | M1 | DONE |
| M4 | Low-Latency Voice Pipeline & Fast Semantic Router | Connect `RealtimeVoiceSession` to `jarvis/core/app.py`, remove mic drop on echo window, integrate continuous barge-in, implement Sub-2ms On-Device Hybrid Semantic Router in `jarvis/llm/semantic_router.py`. | M1 | DONE |
| M5 | Commercial Packaging, Sidecar Automation & Documentation Truth | Fix `main_tray` and `--tray`; create `scripts/build_standalone_package.py`; create `sidecar.json` (daily 09:00 AM VN); sync `CHANGELOG.md`, `README.md`, `docs/ROADMAP.md` under Five-Tier Verdict Discipline. | M1, M2, M3, M4 | IN_PROGRESS |
| M6 | E2E Test Suite Pass (100%) & Adversarial Coverage Hardening | Run opaque-box E2E test suite (Tiers 1-4) until 100% pass; execute Tier 5 adversarial stress testing, gap analysis, and coverage verification. | M1, M2, M3, M4, M5, TEST_READY.md | PLANNED |

---

## Interface Contracts

### 1. Acoustic Front-End & App Seam (`jarvis.audio.dsp` ↔ `jarvis.core.app`)
- Function: `app.record_audio(duration_s: float = 4.0, target_device: Optional[int] = None) -> np.ndarray`
- Contract:
  - Synthetic test audio must contain frequency content within passband ($80\text{ Hz} - 4000\text{ Hz}$).
  - Audio recording fallback block must check `sounddevice.rec` mock before calling real host device.
  - Silence cutoff triggers when `silence_chunks_after_speech >= 5`.

### 2. Comms Fail-Closed Contract (`jarvis.comms.telegram`)
- Function: `telegram.handle_inbound_voice(voice_file_path: Path) -> dict`
- Contract:
  - If STT is unconfigured, missing, or throws an exception, MUST return `{"ok": False, "error_code": "STT_UNAVAILABLE", "message": "Voice transcription service offline or not configured."}`.
  - MUST NEVER return hardcoded synthetic text `"Lệnh thoại đã nhận"`.

### 3. Windows Atomic File Persistence Contract (`jarvis.utils.atomic_io`)
- Helper: `atomic_write_json(path: Path, data: Any, lock: Optional[threading.Lock] = None, indent: int = 2) -> None`
- Contract:
  - Acquire `lock` if provided.
  - Snapshot data into JSON string in RAM.
  - Write to unique temporary file `.tmp.<thread_id>.<timestamp_ns>` in same directory.
  - Execute `tmp_path.replace(path)` with up to 5 retries on `PermissionError` / `WinError 5` with `time.sleep(0.02 * attempt)`.
  - In `finally:`, unlink `tmp_path` if it still exists.

### 4. Continuous Learning Memory Graph (`jarvis.memory.sqlite_store`)
- Methods:
  - `add_knowledge_node(node_id: str, label: str, node_type: str, properties: dict) -> None`
  - `add_knowledge_edge(source_id: str, target_id: str, relation: str, weight: float = 1.0, properties: dict = None) -> None`
  - `record_tech_radar_blip(blip_id: str, title: str, ring: str, quadrant: str, summary: str, url: str, source: str) -> None`
  - `query_tech_radar(quadrant: Optional[str] = None, ring: Optional[str] = None) -> List[dict]`

### 5. ArXiv Tech Radar Ingestion (`jarvis.web.tech_radar`)
- Class: `ArxivIngestionClient`
- Method: `fetch_latest_papers(categories: List[str] = ["cs.AI", "cs.CL", "cs.SD", "eess.AS"], max_results: int = 10) -> List[dict]`
- Contract:
  - Returns structured list of dicts: `[{"id": str, "title": str, "authors": List[str], "summary": str, "category": str, "published": str, "pdf_url": str}]`.
  - Zero third-party dependencies (pure `urllib.request` + `xml.etree.ElementTree`).
  - Rate limited to 1 request per 3 seconds.

### 6. Full-Duplex Real-Time Voice Bridge (`jarvis.voice.realtime` ↔ `jarvis.core.app`)
- Class: `RealtimeVoiceSession`
- Contract:
  - In `jarvis/core/app.py`, microphone frames arriving during TTS playback are passed to `RealtimeVoiceSession.on_audio_chunk()`.
  - If RMS of bandpassed speech exceeds barge-in threshold ($> 0.025$) for $\ge 3$ consecutive frames, TTS playback is immediately aborted via `tts_manager.stop()`, state transitions from `SPEAKING` to `LISTENING`, and speech stream begins buffer accumulation.

### 7. Scheduled Automation Sidecar (`sidecar.json`)
- Schema:
  ```json
  {
    "version": "1.0",
    "enabled": true,
    "schedule": {
      "cron": "0 9 * * *",
      "timezone": "Asia/Ho_Chi_Minh",
      "description": "Daily 09:00 AM VN automated radar scan and self-upgrade check"
    },
    "tasks": [
      {
        "id": "tech_radar_scan",
        "action": "run_radar_ingestion",
        "params": {"sources": ["arxiv", "github_trending"], "max_papers": 10}
      },
      {
        "id": "system_health_self_check",
        "action": "run_unit_health_check",
        "params": {"test_target": "tests/unit/", "timeout_s": 120}
      },
      {
        "id": "continuous_learning_upgrade",
        "action": "update_knowledge_graph",
        "params": {"auto_link": true}
      }
    ]
  }
  ```

---

## Code Layout & Ownership Boundaries
To ensure clean isolation and avoid write contention across workers:
- **Milestone 1 Worker**: Owns `tests/unit/test_adversarial_challenger_m1_sample_rate.py`, `jarvis/comms/telegram.py`.
- **Milestone 2 Worker**: Owns `jarvis/utils/atomic_io.py`, `jarvis/vision/biometrics.py`, `jarvis/skills/telemetry.py`, `jarvis/skills/macro_recorder/__init__.py`, `jarvis/smart_home/discovery.py`, `jarvis/skills/registry.py`, `jarvis/workers/night_shift.py`, `jarvis/comms/mobile_bridge.py`, `jarvis/ui/setup_wizard.py`, `jarvis/tts/cache.py`, and unit tests `tests/unit/test_windows_atomic_persistence.py`.
- **Milestone 3 Worker**: Owns `jarvis/memory/sqlite_store.py`, `jarvis/web/tech_radar.py`, and unit tests `tests/unit/test_tech_radar_and_knowledge_graph.py`.
- **Milestone 4 Worker**: Owns `jarvis/core/app.py` (voice barge-in bridge), `jarvis/llm/semantic_router.py`, and unit tests `tests/unit/test_realtime_voice_bridge.py`.
- **Milestone 5 Worker**: Owns `jarvis/__main__.py`, `jarvis/cli.py`, `scripts/build_standalone_package.py`, `sidecar.json`, `CHANGELOG.md`, `README.md`, `docs/ROADMAP.md`.
- **E2E Testing Track**: Owns `tests/e2e/test_autonomous_engine_e2e.py`, `TEST_INFRA.md`, and `TEST_READY.md`.
