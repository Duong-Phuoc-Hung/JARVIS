# STT Real-Microphone Eval — Failure Decomposition

Corrects the historical `SILENT_FAILURE` bucket in `docs/eval/stt_eval_results.json` / `docs/eval/stt_eval_summaries.json` by separating pure STT recognition failure (empty transcript) from router abstention (non-empty transcript, no matching intent). This document does not modify or overwrite either historical file.

## Dataset size

- Real microphone recordings (distinct audio files): **90**
- Historical model-evaluation rows (recordings × models): **180**

## Historical `SILENT_FAILURE` — what it actually was

`SILENT_FAILURE` in the historical taxonomy was an **end-to-end abstention bucket**, not a pure STT-empty-transcript rate. It fired whenever the router returned `NO_INTENT`, regardless of whether that was because STT produced no text at all, or because STT produced a non-empty (often garbled/mis-recognized) transcript that simply didn't match any Tier-1 rule-engine keyword.

- Legacy `SILENT_FAILURE` rows, total: **134**
  - of which `STT_EMPTY` (transcript was truly empty): **3**
  - of which `ROUTER_ABSTAIN` (transcript non-empty, router found no match): **131**

This means the historical 66–82% "silent_failure_rate" figures quoted elsewhere (CLAUDE.md, docs/PROJECT_STATE.md) were overwhelmingly driven by ROUTER_ABSTAIN, not STT_EMPTY. Per AUDIT_METHODOLOGY.md's causal-attribution rule, this does **not** by itself prove the root cause is "the router is too strict" versus "STT mis-transcribes words badly enough that no keyword matches" — both are consistent with a non-empty-but-wrong transcript, and distinguishing them needs the per-trial transcript quality metric (Phase 3, auxiliary only) or a manual transcript review, not this decomposition alone.

## Decomposition by model / condition

| Model | Condition | N | Correct | Misrouted | STT_EMPTY | ROUTER_ABSTAIN | End-to-end abstention |
|---|---|---:|---:|---:|---:|---:|---:|
| large-v3 | clean | 45 | 13 (28.9%) | 1 (2.2%) | 0 (0.0%) | 31 (68.9%) | 68.9% |
| large-v3 | noisy | 45 | 14 (31.1%) | 1 (2.2%) | 0 (0.0%) | 30 (66.7%) | 66.7% |
| small | clean | 45 | 7 (15.6%) | 1 (2.2%) | 1 (2.2%) | 36 (80.0%) | 82.2% |
| small | noisy | 45 | 8 (17.8%) | 1 (2.2%) | 2 (4.4%) | 34 (75.6%) | 80.0% |
| **TOTAL** | — | 180 | 42 (23.3%) | 4 (2.2%) | 3 (1.7%) | 131 (72.8%) | 74.4% |

## Phase 3 (auxiliary) — Transcript text-quality metric

**AUXILIARY ONLY.** `token_similarity()` (`tests/eval/text_normalize.py`) scores each row's transcript against the phrase actually spoken for that WAV file (resolved from `tests/eval/phrase_manifest.py`), via normalized token-level Word Error Rate (1.0 = identical token sequence after lowercasing/punctuation-stripping/NFC normalization; 0.0 = fully divergent). It does **not** strip Vietnamese diacritics, so a transcript that is semantically right but drops/changes accents scores as a token mismatch — this metric is sensitive to that, not just to meaning. **It is never used to decide CORRECT/MISROUTED/STT_EMPTY/ROUTER_ABSTAIN and does not measure router safety.**

- Rows scored: **180** / rows unresolved (no manifest match or missing audio_file): 0
- Overall: n=180 mean=0.170 median=0.000 stdev=0.336

| Model | Condition | N | Mean | Median | Stdev |
|---|---|---:|---:|---:|---:|
| large-v3 | clean | 45 | 0.235 | 0.000 | 0.382 |
| large-v3 | noisy | 45 | 0.302 | 0.000 | 0.425 |
| small | clean | 45 | 0.037 | 0.000 | 0.177 |
| small | noisy | 45 | 0.106 | 0.000 | 0.238 |

By new-taxonomy outcome bucket:

| Outcome | N | Mean | Median | Stdev |
|---|---:|---:|---:|---:|
| CORRECT | 42 | 0.333 | 0.000 | 0.466 |
| MISROUTED | 4 | 0.375 | 0.250 | 0.479 |
| ROUTER_ABSTAIN | 131 | 0.115 | 0.000 | 0.261 |
| STT_EMPTY | 3 | 0.000 | 0.000 | 0.000 |

Distribution of scores across all resolved rows: 0.0-0.2: 138, 0.2-0.4: 7, 0.4-0.6: 9, 0.6-0.8: 7, 0.8-1.0: 0, 1.0: 19

**What this does and does not prove**: the median similarity across all 180 rows is 0.0 and the mean is low (~0.17) — most transcripts share zero exact normalized tokens with the phrase actually spoken, including the majority of `ROUTER_ABSTAIN` rows (mean ≈ 0.115). This is evidence AGAINST the naive inference "only 3/180 rows are STT_EMPTY, so transcription is mostly accurate and abstention is purely a router-matching problem" — a non-empty transcript in this dataset is frequently also a substantially wrong one. It does **not**, by itself, prove the reverse either (that STT quality alone explains ROUTER_ABSTAIN) — the Tier-1 rule-engine's substring matching could still fail even on a perfectly transcribed sentence that phrases the same intent differently than its fixed keyword list expects. Distinguishing "bad transcription" from "rigid keyword matching" conclusively would require manual per-row review, which was not performed here.

## Phase 2 — Phrase manifest drift found and fixed

`tests/eval/stt_intent_eval.py` carried a stale, ASCII/unaccented copy of the phrase list (e.g. `"mo chrome"`), while `tests/eval/record_test_set.py` — the script that actually drove the committed microphone recordings under `tests/eval/audio/` — used the real accented Vietnamese prompts (e.g. `"mở chrome"`). Beyond accenting, one entry had drifted in content: `stt_intent_eval.py` claimed `open_app` variant 4 was `"launch spotify"`, but `record_test_set.py` (the actually-executed recorder) used `"khởi động chrome"` for that slot — that phrase was never recorded.

Fixed by introducing `tests/eval/phrase_manifest.py` as the single source of truth (preserving `record_test_set.py`'s real prompts verbatim, since those are what was actually spoken into the microphone). Both `record_test_set.py` and `stt_intent_eval.py` now import from it instead of keeping local copies. No WAV file was renamed.

**Validation**: every committed WAV file under `tests/eval/audio/` resolves to a manifest phrase (see `tests/eval/phrase_manifest.py::validate_audio_root()` and its regression test).

## Phase 4 — Historical Direct Evaluator vs Production STT Path

Audited by direct source comparison of `tests/eval/stt_intent_eval.py::run_single_model()`
(historical "direct" backend) against `jarvis.stt.engine.FasterWhisperSTT.transcribe()`
(production). These are genuinely different code paths — do not describe historical
evaluator latency/behavior numbers as production STT numbers without this context.

| Aspect | Historical direct evaluator | Production (`FasterWhisperSTT`) |
|---|---|---|
| Model API surface | Raw `faster_whisper.WhisperModel` instantiated directly in the eval subprocess | `FasterWhisperSTT` abstraction (`jarvis/stt/engine.py`), lazy-loaded, thread-locked |
| `beam_size` | `3` (fixed, chosen to match latency benchmark tables) | `5` (production default; caller can override via kwargs) |
| Audio input path | `model.transcribe(str(wav_path), ...)` — faster-whisper reads the WAV file itself | `audio_to_float32()` first (resampling, channel-mixing, int16/float32/uint8 handling), then `model.transcribe(arr, ...)` |
| Pre-transcription RMS gate | None — every file is sent to the model | `calculate_rms(arr) < 0.001` short-circuits to `""` before the model ever runs |
| `condition_on_previous_text` | `False` | `False` (same) |
| `no_speech_threshold` | `0.6` (same) | `0.6` (same) |
| `log_prob_threshold` | `-1.0` (same) | `-1.0` (same) |
| `compression_ratio_threshold` | `2.4` (same) | `2.4` (same) |
| Post-filter hallucination gate | None | Low-RMS (`< 0.005`) + long-transcript (`> 3` words) segments are discarded with a logged warning |
| Confidence/segment metadata returned to caller | Yes — evaluator computes `confidence = exp(mean(avg_logprob))` per trial from the raw segment iterator | No — `transcribe()` returns only the final joined string; avg_logprob/no_speech_prob are consumed internally for the hallucination post-filter and never returned. The production backend in this evaluator therefore **cannot** report a confidence value or threshold curve — this is a real capability gap in the abstraction, not an evaluator oversight, and is left as `null`/absent rather than fabricated. |
| Compute type | `int8` (small) / `int8_float16` (large-v3), matching production's own default selection for those models | Configurable via `compute_type` (defaults to `int8`); this eval sets it explicitly to match the direct backend's values so latency stays comparable |
| Device selection | Hardcoded `device="cuda"` | `_resolve_device()` auto-detects CUDA availability (DLL smoke-test) and falls back to CPU; eval passes `device="cuda"` explicitly, same effective behavior when CUDA is present |
| Model loading/caching | New `WhisperModel` per subprocess (one model per run, VRAM released on subprocess exit) | Lazily constructed once per `FasterWhisperSTT` instance, cached on `self._model`, guarded by `self._lock` |
| `language` argument | Passed through as given (`--language`, default `"vi"`) | Passed through as given (same) |
| Router integration | Evaluator calls `predict_intent()` separately after transcription, using `LLMIntentRouter`'s Tier-1 `rule_engine` in isolation | N/A — `FasterWhisperSTT` has no router integration; routing is a downstream concern in the real pipeline (`jarvis/llm/router.py`), not part of the STT engine at all |

**Conclusion**: the historical direct-backend latency/behavior numbers in
`docs/eval/stt_eval_results.json` and `docs/eval/stt_eval_summaries.json` describe the
raw `WhisperModel` path at `beam_size=3` with no RMS pre-gate and no post-filter — they
are close to, but not identical to, what the production `FasterWhisperSTT` abstraction
would produce for the same audio. The evaluator's new `--backend production` mode
(Phase 5) calls the real `FasterWhisperSTT.transcribe()` directly (no reimplementation
of its filtering logic) so a real production-path comparison can be run without
conflating the two.

## Phase 8 — Real production-backend rerun status

Not executed this session — CUDA-capable GPU is present on the host (confirmed via `nvidia-smi`), but the `faster-whisper`/`ctranslate2` Python packages are not installed in any available interpreter and no project virtual environment with them was found. Per AUDIT_METHODOLOGY.md, no mock or fabricated results are substituted — this rerun remains an open follow-up.

## What this document does NOT do

- Does not edit or overwrite `docs/eval/stt_eval_results.json` or `docs/eval/stt_eval_summaries.json` — both remain the original committed evidence.
- Does not tune `no_speech_threshold`, `log_prob_threshold`, `compression_ratio_threshold`, production `beam_size`, the hallucination post-filter, or router behavior.
- Does not claim Tier 1 status for STT recognition quality — see AUDIT_METHODOLOGY.md's criteria; this is a re-classification of existing evidence, not new acoustic evidence.
