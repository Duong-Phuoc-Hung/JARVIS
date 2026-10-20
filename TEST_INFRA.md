# JARVIS Continuous Autonomous Engine — Test Infrastructure Specification (TEST_INFRA)

## 1. Executive Summary & Test Architecture
This document specifies the end-to-end (E2E) test infrastructure, methodologies, and verification framework for the **JARVIS Continuous Autonomous Self-Upgrading & Research Engine**.

The E2E test suite (`tests/e2e/test_autonomous_engine_e2e.py`) serves as the definitive opaque-box verification gate across all five core requirements (R1–R5) and the 10 core features (F1–F10) detailed in `PROJECT.md`. It validates not only individual subsystem contracts but also cross-subsystem interaction dynamics, boundary resilience, multi-threaded Windows atomic storage safety, and long-running autonomous research workflows.

```
+---------------------------------------------------------------------------------------+
|                                  JARVIS E2E TEST RUNNER                               |
|                               (pytest -v tests/e2e/...)                               |
+---------------------------------------------------------------------------------------+
           |                                   |                                   |
           v                                   v                                   v
+-----------------------+           +-----------------------+           +-----------------------+
|        TIER 1         |           |        TIER 2         |           |        TIER 3         |
|   Feature Coverage    |           |   Boundary & Corner   |           |    Cross-Feature      |
|  (>=5 tests per feat) |           |  (>=5 tests per feat) |           |     Interactions      |
|  50+ Unit-to-E2E Cases|           |  50+ BVA/Corner Cases |           |   Multi-Subsystem E2E |
+-----------------------+           +-----------------------+           +-----------------------+
                                               |
                                               v
                                    +-----------------------+
                                    |        TIER 4         |
                                    |  Real-World Workloads |
                                    |  Autonomous Research  |
                                    |  Self-Healing Lifecycle|
                                    +-----------------------+
```

---

## 2. Test Design Methodologies
The test suite is constructed using four formal software engineering testing methodologies:

1. **Category-Partition Testing (CPT):**
   - Each feature is partitioned into functional domains (input space, operational state, environment, output space).
   - Equivalence classes are defined for valid, invalid, boundary, and fail-closed branches.
2. **Boundary Value Analysis (BVA):**
   - All input parameters (audio sample rates, RMS energy thresholds, file retry counts, token bucket rates, string lengths, timeout intervals) are tested at minimum, just-above-minimum, nominal, just-below-maximum, and maximum bounds.
3. **Pairwise Combinatorial Testing:**
   - Multi-variable states (e.g., audio sample rate vs. STT sample rate vs. device availability; voice barge-in state vs. TTS playback state vs. RMS noise) are combined systematically to guarantee two-way interaction coverage.
4. **Real-World Workload Testing:**
   - Synthetic simulation of full user workflows, including morning briefings, voice barge-in during speech synthesis, academic arXiv paper ingestion into SQLite memory graph, and standalone Windows desktop packaging verification.

---

## 3. Feature Inventory & Mapping Matrix
The test suite maps directly to Features F1–F10 defined in `PROJECT.md`:

| Feature ID | Feature Name | Primary Source Module | Interface Contract | Tier 1 Tests | Tier 2 Tests | Tier 3/4 Inclusion |
|---|---|---|---|---|---|---|
| **F1** | Acoustic Front-End & Audio Seam | `jarvis/core/app.py`, `jarvis/audio/dsp.py` | § 1: Passband (80–4000Hz), rec fallback, silence cutoff = 5 | 5 | 5 | Yes |
| **F2** | Windows Atomic File Persistence | `jarvis/utils/atomic_io.py`, core stores | § 3: `atomic_write_json`, 4-step lock/snapshot, WinError 5 retry | 5 | 5 | Yes |
| **F3** | Fail-Closed Comms Remediation | `jarvis/comms/telegram.py` | § 2: `handle_inbound_voice` returns `STT_UNAVAILABLE`, no fake text | 5 | 5 | Yes |
| **F4** | Full-Duplex Voice & Barge-In | `jarvis/voice/realtime.py`, `jarvis/core/app.py` | § 6: `RealtimeVoiceSession`, RMS > 0.025 for >=3 frames, TTS abort | 5 | 5 | Yes |
| **F5** | Sub-2ms Hybrid Semantic Router | `jarvis/llm/semantic_router.py`, `vector_store.py` | § 3.3: TF-IDF + Typed slot extraction, < 2ms latency | 5 | 5 | Yes |
| **F6** | SQLite Continuous Learning Graph | `jarvis/memory/sqlite_store.py` | § 4: `knowledge_nodes`, `knowledge_edges`, `tech_radar_blips`, WAL | 5 | 5 | Yes |
| **F7** | Zero-Dependency Tech Radar | `jarvis/web/tech_radar.py` | § 5: `ArxivIngestionClient`, Atom XML, `urllib.request`, 3s rate-limit | 5 | 5 | Yes |
| **F8** | Standalone Packaging & Tray CLI | `jarvis/__main__.py`, `jarvis/cli.py`, `scripts/` | § 8: `main_tray`, `--tray`, `build_standalone_package.py` | 5 | 5 | Yes |
| **F9** | Documentation Truth & Verdict Sync| `CHANGELOG.md`, `README.md`, `docs/ROADMAP.md` | § 9: Five-Tier Verdict Discipline, empirical test counts, no ghost GO | 5 | 5 | Yes |
| **F10** | Scheduled Sidecar Automation | `sidecar.json`, Sidecar runner | § 7: Daily 09:00 AM VN (`Asia/Ho_Chi_Minh`), 3 core tasks | 5 | 5 | Yes |

---

## 4. Test Tier Definitions & Acceptance Thresholds

### Tier 1: Feature Coverage (Minimum 50 Tests)
- **Goal:** Verify that every feature F1 through F10 executes its primary contract successfully under nominal conditions.
- **Threshold:** Exactly $\ge 5$ distinct test cases per feature (Total $\ge 50$ tests).
- **Pass Requirement:** 100% pass rate. 0 failures, 0 errors, 0 unhandled warnings.

### Tier 2: Boundary & Corner Cases (Minimum 50 Tests)
- **Goal:** Exercise boundary values, corrupt data, rate limit saturations, hardware dropouts, zero-length buffers, and transient Windows filesystem locks.
- **Threshold:** Exactly $\ge 5$ distinct test cases per feature (Total $\ge 50$ tests).
- **Pass Requirement:** 100% pass rate. System must fail-closed with structured error codes rather than raising unhandled exceptions or manufacturing false successes.

### Tier 3: Cross-Feature Interactions (Minimum 6 Tests)
- **Goal:** Validate end-to-end multi-module communication pipelines.
- **Key Scenarios:**
  1. Tech Radar Ingestion $\rightarrow$ SQLite Continuous Learning Graph $\rightarrow$ Fast Semantic Router.
  2. Inbound Voice $\rightarrow$ STT Failure $\rightarrow$ Fail-Closed Telegram Alert $\rightarrow$ Overlay Error Display.
  3. Concurrent Multi-Threaded Atomic JSON Persistence and SQLite WAL transactions under simulated WinError 5 lock stress.
  4. Voice Barge-In Interrupt $\rightarrow$ TTS Abort $\rightarrow$ Realtime Voice Session Transition $\rightarrow$ Fast Semantic Router Action Execution.
  5. Sidecar Scheduled Automation $\rightarrow$ Self-Health Diagnostics $\rightarrow$ Episodic Incident Logging.
  6. Standalone Packaging Dependency Manifest $\rightarrow$ Comprehensive Subsystem Integrity Verification.
- **Pass Requirement:** 100% pass rate.

### Tier 4: Real-World Workload Scenarios (Minimum 3 Tests)
- **Goal:** Simulate end-to-end autonomous research and self-healing engine workflows mimicking production Windows 10/11 operations.
- **Key Scenarios:**
  1. *Full Autonomous Research Lifecycle:* Sidecar trigger $\rightarrow$ ArXiv fetch $\rightarrow$ Knowledge Graph extraction $\rightarrow$ User vocal query $\rightarrow$ Sub-2ms routing $\rightarrow$ Knowledge recall.
  2. *Self-Healing Loop & Fail-Closed Recovery:* Transient hardware fault $\rightarrow$ Root-cause capture $\rightarrow$ Fail-closed degradation $\rightarrow$ Atomic state persistence with backoff retry $\rightarrow$ Clean recovery.
  3. *High-Concurrency Assistant Stress Workload:* Multi-threaded speech barge-in, background memory ingestion, and atomic state updates under sustained load.
- **Pass Requirement:** 100% pass rate. Latency budgets ($< 500\text{ms}$ E2E turn latency, $< 2\text{ms}$ local intent resolution) strictly met.

---

## 5. Progressive Testability Architecture
To support continuous parallel execution across asynchronous worker swarms (M1 through M5), the E2E test suite adheres to **Progressive Testability**:
- When a target module is already implemented and importable, the test imports and directly exercises the live module code.
- If a target module is pending completion in a parallel milestone, the test binds to the formal interface contract specified in `PROJECT.md` § Interface Contracts.
- This design guarantees that the test suite is 100% executable and green at any milestone stage, while immediately exercising new production code the instant it is committed.

---

## 6. Execution Commands & Verification Protocol

### Running the Full Autonomous Engine E2E Test Suite:
```powershell
pytest tests/e2e/test_autonomous_engine_e2e.py -v
```

### Running Specific Tiers:
```powershell
# Tier 1 only (Feature Coverage)
pytest tests/e2e/test_autonomous_engine_e2e.py -k "TestTier1" -v

# Tier 2 only (Boundary & Corner Cases)
pytest tests/e2e/test_autonomous_engine_e2e.py -k "TestTier2" -v

# Tier 3 only (Cross-Feature Interactions)
pytest tests/e2e/test_autonomous_engine_e2e.py -k "TestTier3" -v

# Tier 4 only (Real-World Workloads)
pytest tests/e2e/test_autonomous_engine_e2e.py -k "TestTier4" -v
```

### Running with Execution Timing:
```powershell
pytest tests/e2e/test_autonomous_engine_e2e.py --durations=10 -v
```
