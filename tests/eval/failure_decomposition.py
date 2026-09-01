"""
tests/eval/failure_decomposition.py
==============================
Deterministic outcome classification (Phase 1 taxonomy) and offline failure
decomposition for the JARVIS STT real-microphone eval.

Historical evaluator taxonomy (tests/eval/stt_intent_eval.py, still used for its
own live per-run reporting) collapses two distinct outcomes into one label:

    SILENT_FAILURE = STT produced an empty transcript
                      OR STT produced text but the router returned NO_INTENT

This module defines the corrected 4-way taxonomy and recomputes it directly
from each trial's own (transcript, predicted_intent, intent_gt) fields —
it does not just relabel the legacy 'outcome' field, so the classification is
independently reproducible from raw data:

    CORRECT         = router action matches an expected action for intent_gt
    MISROUTED       = transcript non-empty AND router chose a wrong action
    STT_EMPTY       = transcript.strip() == ""
    ROUTER_ABSTAIN  = transcript non-empty AND router returned NO_INTENT

Do NOT edit historical committed evidence (docs/eval/stt_eval_results.json) to
fit this taxonomy — this module reads it as-is and produces new, separate
analysis artifacts.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent.parent

Outcome = Literal["CORRECT", "MISROUTED", "STT_EMPTY", "ROUTER_ABSTAIN"]

# Map eval intent category -> acceptable router action_name(s). Single-sourced
# here; tests/eval/stt_intent_eval.py imports this instead of keeping its own
# copy, so the two can no longer drift apart.
EXPECTED_ACTIONS: dict[str, set[str]] = {
    "open_app":        {"app_open", "web_open"},
    "system_shutdown": {"system_power"},
    "system_restart":  {"system_power"},
    "volume_control":  {"system_volume"},
    "weather_query":   {"shell_exec"},
    "timer_set":       {"reminder"},
    "reminder_set":    {"reminder"},
    "screenshot":      {"screen_capture"},
    "stop":            {"system_power"},
    "search":          {"web_open", "shell_exec"},
    "music_play":      {"spotify"},
    "screen_off":      {"system_power", "system_brightness"},
    "note_take":       {"memory_save_fact"},
    "settings_open":   {"app_open", "web_open"},
}


def classify_outcome(
    transcript: str,
    predicted_action: str,
    intent_gt: str,
    expected_actions: dict[str, set[str]] | None = None,
) -> Outcome:
    """
    Deterministic 4-way classification. Order matters:
    an empty transcript is always STT_EMPTY, even if predicted_action happens
    to also be 'NO_INTENT' for that row (which it always is, for empty input,
    per predict_intent()'s own early-return — checking transcript emptiness
    first keeps this classifier correct independent of that implementation
    detail).
    """
    expected_actions = expected_actions if expected_actions is not None else EXPECTED_ACTIONS
    if transcript.strip() == "":
        return "STT_EMPTY"
    if predicted_action == "NO_INTENT":
        return "ROUTER_ABSTAIN"
    if predicted_action in expected_actions.get(intent_gt, set()):
        return "CORRECT"
    return "MISROUTED"


def _bucket_stats(counter: Counter, n_sub: int) -> dict:
    correct = counter.get("CORRECT", 0)
    misrouted = counter.get("MISROUTED", 0)
    stt_empty = counter.get("STT_EMPTY", 0)
    router_abstain = counter.get("ROUTER_ABSTAIN", 0)
    denom = n_sub if n_sub else 1
    return {
        "n_trials": n_sub,
        "n_correct": correct,
        "n_misrouted": misrouted,
        "n_stt_empty": stt_empty,
        "n_router_abstain": router_abstain,
        "correct_rate": correct / denom,
        "misrouting_rate": misrouted / denom,
        "stt_empty_rate": stt_empty / denom,
        "router_abstain_rate": router_abstain / denom,
        "end_to_end_abstention_rate": (stt_empty + router_abstain) / denom,
    }


def decompose_results(results: list[dict]) -> dict:
    """
    Recompute the 4-way taxonomy for every row in `results` (as loaded from
    stt_eval_results.json) and aggregate by (model, condition) and total.
    Also cross-tabulates against each row's pre-existing legacy 'outcome'
    field (CORRECT/MISROUTED/SILENT_FAILURE) to show exactly how many legacy
    SILENT_FAILURE rows were actually STT_EMPTY vs ROUTER_ABSTAIN.
    """
    by_model_condition: dict[tuple[str, str], Counter] = defaultdict(Counter)
    total: Counter = Counter()
    crosswalk: Counter = Counter()
    audio_files: set[str] = set()

    for row in results:
        transcript = row.get("transcript", "") or ""
        predicted = row.get("predicted_intent", "NO_INTENT")
        intent_gt = row.get("intent_gt", "")
        new_outcome = classify_outcome(transcript, predicted, intent_gt)

        model = row.get("model", "unknown")
        condition = row.get("condition", "unknown")
        by_model_condition[(model, condition)][new_outcome] += 1
        total[new_outcome] += 1

        legacy_outcome = row.get("outcome", "UNKNOWN")
        crosswalk[(legacy_outcome, new_outcome)] += 1

        audio_file = row.get("audio_file")
        if audio_file:
            audio_files.add(audio_file)

    n_rows = len(results)

    by_model_condition_out = {}
    for (model, condition), counter in sorted(by_model_condition.items()):
        n_sub = sum(counter.values())
        by_model_condition_out[f"{model}/{condition}"] = {
            "model": model,
            "condition": condition,
            **_bucket_stats(counter, n_sub),
        }

    legacy_silent_total = sum(
        c for (legacy, _new), c in crosswalk.items() if legacy == "SILENT_FAILURE"
    )
    legacy_silent_to_stt_empty = crosswalk.get(("SILENT_FAILURE", "STT_EMPTY"), 0)
    legacy_silent_to_router_abstain = crosswalk.get(("SILENT_FAILURE", "ROUTER_ABSTAIN"), 0)

    return {
        "n_rows": n_rows,
        "n_distinct_audio_files": len(audio_files) if audio_files else None,
        "by_model_condition": by_model_condition_out,
        "total": _bucket_stats(total, n_rows),
        "legacy_silent_failure_decomposition": {
            "legacy_silent_failure_total": legacy_silent_total,
            "of_which_stt_empty": legacy_silent_to_stt_empty,
            "of_which_router_abstain": legacy_silent_to_router_abstain,
        },
        "crosswalk_legacy_to_new": {
            f"{legacy}->{new}": c for (legacy, new), c in sorted(crosswalk.items())
        },
    }


def compute_text_similarity_stats(results: list[dict]) -> dict:
    """
    Phase 3 (auxiliary only): aggregate token_similarity() between each row's
    transcript and the phrase actually spoken, resolved via
    phrase_manifest.resolve_phrase_by_stem(row["intent_gt"], row["phrase"]) —
    the row's own portable metadata, deliberately NOT the row's `audio_file`
    absolute path. Historical rows in docs/eval/stt_eval_results.json store
    whatever machine-specific absolute path (e.g. a Windows path from the
    original recording machine) happened to be current when the eval ran;
    parsing that path as a filesystem path to recover the intent/variant is
    fragile and host-dependent. `intent_gt` and `phrase` (e.g. "variant_4")
    are plain strings already present on every row and need no path parsing
    at all.

    This is descriptive of transcription quality, NOT a safety/outcome metric.
    It is computed and reported here specifically to prevent the mistaken
    inference "STT_EMPTY is only 3/180, therefore transcription is largely
    accurate" — a non-empty transcript can still be almost entirely wrong.
    """
    from tests.eval.phrase_manifest import resolve_phrase_by_stem
    from tests.eval.text_normalize import token_similarity

    by_model_condition: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_outcome: dict[str, list[float]] = defaultdict(list)
    all_sims: list[float] = []
    n_unresolved = 0

    for row in results:
        intent_gt = row.get("intent_gt")
        variant_stem = row.get("phrase")
        if not intent_gt or not variant_stem:
            n_unresolved += 1
            continue
        expected_phrase = resolve_phrase_by_stem(intent_gt, variant_stem)
        if expected_phrase is None:
            n_unresolved += 1
            continue
        transcript = row.get("transcript", "") or ""
        sim = token_similarity(expected_phrase, transcript)
        all_sims.append(sim)

        model = row.get("model", "unknown")
        condition = row.get("condition", "unknown")
        by_model_condition[(model, condition)].append(sim)

        predicted = row.get("predicted_intent", "NO_INTENT")
        outcome = classify_outcome(transcript, predicted, intent_gt)
        by_outcome[outcome].append(sim)

    def _stats(values: list[float]) -> dict:
        if not values:
            return {"n": 0, "mean": None, "median": None, "stdev": None}
        return {
            "n": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        }

    distribution = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0, "1.0": 0}
    for s in all_sims:
        if s >= 1.0:
            distribution["1.0"] += 1
        elif s >= 0.8:
            distribution["0.8-1.0"] += 1
        elif s >= 0.6:
            distribution["0.6-0.8"] += 1
        elif s >= 0.4:
            distribution["0.4-0.6"] += 1
        elif s >= 0.2:
            distribution["0.2-0.4"] += 1
        else:
            distribution["0.0-0.2"] += 1

    return {
        "n_resolved": len(all_sims),
        "n_unresolved": n_unresolved,
        "overall": _stats(all_sims),
        "by_model_condition": {
            f"{model}/{condition}": _stats(values)
            for (model, condition), values in sorted(by_model_condition.items())
        },
        "by_outcome": {outcome: _stats(values) for outcome, values in sorted(by_outcome.items())},
        "distribution": distribution,
    }


EVALUATOR_VS_PRODUCTION_DIFFERENCES = """\
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
"""


def _fmt_stat(s: dict) -> str:
    if not s or s.get("n", 0) == 0:
        return "n=0"
    return f"n={s['n']} mean={s['mean']:.3f} median={s['median']:.3f} stdev={s['stdev']:.3f}"


PRODUCTION_RERUN_STATUS_NOT_ASSESSED = (
    "Not supplied to this report generator — the production-backend rerun's real-hardware/"
    "dependency status was not assessed for this invocation. This is a placeholder, not a "
    "claim about any specific machine: pass an explicit `production_rerun_status` string "
    "(or `--production-rerun-status` on the CLI) describing what was actually checked on the "
    "machine generating this report, per AUDIT_METHODOLOGY.md's rule against unverified claims."
)


def render_markdown_report(
    decomposition: dict,
    phrase_manifest_problems: list[str] | None = None,
    text_similarity_stats: dict | None = None,
    production_rerun_status: str = PRODUCTION_RERUN_STATUS_NOT_ASSESSED,
) -> str:
    total = decomposition["total"]
    n_rows = decomposition["n_rows"]
    n_audio = decomposition.get("n_distinct_audio_files")
    legacy = decomposition["legacy_silent_failure_decomposition"]

    lines: list[str] = []
    lines.append("# STT Real-Microphone Eval — Failure Decomposition\n")
    lines.append(
        "Corrects the historical `SILENT_FAILURE` bucket in "
        "`docs/eval/stt_eval_results.json` / `docs/eval/stt_eval_summaries.json` by "
        "separating pure STT recognition failure (empty transcript) from router "
        "abstention (non-empty transcript, no matching intent). This document does "
        "not modify or overwrite either historical file.\n"
    )
    lines.append("## Dataset size\n")
    lines.append(f"- Real microphone recordings (distinct audio files): **{n_audio}**")
    lines.append(f"- Historical model-evaluation rows (recordings × models): **{n_rows}**\n")

    lines.append("## Historical `SILENT_FAILURE` — what it actually was\n")
    lines.append(
        "`SILENT_FAILURE` in the historical taxonomy was an **end-to-end abstention "
        "bucket**, not a pure STT-empty-transcript rate. It fired whenever the router "
        "returned `NO_INTENT`, regardless of whether that was because STT produced no "
        "text at all, or because STT produced a non-empty (often garbled/mis-recognized) "
        "transcript that simply didn't match any Tier-1 rule-engine keyword.\n"
    )
    lines.append(
        f"- Legacy `SILENT_FAILURE` rows, total: **{legacy['legacy_silent_failure_total']}**"
    )
    lines.append(f"  - of which `STT_EMPTY` (transcript was truly empty): **{legacy['of_which_stt_empty']}**")
    lines.append(
        f"  - of which `ROUTER_ABSTAIN` (transcript non-empty, router found no match): "
        f"**{legacy['of_which_router_abstain']}**\n"
    )
    lines.append(
        "This means the historical 66–82% \"silent_failure_rate\" figures quoted "
        "elsewhere (CLAUDE.md, docs/PROJECT_STATE.md) were overwhelmingly driven by "
        "ROUTER_ABSTAIN, not STT_EMPTY. Per AUDIT_METHODOLOGY.md's causal-attribution "
        "rule, this does **not** by itself prove the root cause is \"the router is too "
        "strict\" versus \"STT mis-transcribes words badly enough that no keyword "
        "matches\" — both are consistent with a non-empty-but-wrong transcript, and "
        "distinguishing them needs the per-trial transcript quality metric (Phase 3, "
        "auxiliary only) or a manual transcript review, not this decomposition alone.\n"
    )

    lines.append("## Decomposition by model / condition\n")
    lines.append(
        "| Model | Condition | N | Correct | Misrouted | STT_EMPTY | ROUTER_ABSTAIN | "
        "End-to-end abstention |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for _key, s in sorted(decomposition["by_model_condition"].items()):
        lines.append(
            f"| {s['model']} | {s['condition']} | {s['n_trials']} | "
            f"{s['n_correct']} ({s['correct_rate']:.1%}) | "
            f"{s['n_misrouted']} ({s['misrouting_rate']:.1%}) | "
            f"{s['n_stt_empty']} ({s['stt_empty_rate']:.1%}) | "
            f"{s['n_router_abstain']} ({s['router_abstain_rate']:.1%}) | "
            f"{s['end_to_end_abstention_rate']:.1%} |"
        )
    lines.append(
        f"| **TOTAL** | — | {total['n_trials']} | "
        f"{total['n_correct']} ({total['correct_rate']:.1%}) | "
        f"{total['n_misrouted']} ({total['misrouting_rate']:.1%}) | "
        f"{total['n_stt_empty']} ({total['stt_empty_rate']:.1%}) | "
        f"{total['n_router_abstain']} ({total['router_abstain_rate']:.1%}) | "
        f"{total['end_to_end_abstention_rate']:.1%} |\n"
    )

    if text_similarity_stats:
        ts = text_similarity_stats
        lines.append("## Phase 3 (auxiliary) — Transcript text-quality metric\n")
        lines.append(
            "**AUXILIARY ONLY.** `token_similarity()` (`tests/eval/text_normalize.py`) scores "
            "each row's transcript against the phrase actually spoken for that WAV file "
            "(resolved from `tests/eval/phrase_manifest.py`), via normalized token-level Word "
            "Error Rate (1.0 = identical token sequence after lowercasing/punctuation-stripping/"
            "NFC normalization; 0.0 = fully divergent). It does **not** strip Vietnamese "
            "diacritics, so a transcript that is semantically right but drops/changes accents "
            "scores as a token mismatch — this metric is sensitive to that, not just to "
            "meaning. **It is never used to decide CORRECT/MISROUTED/STT_EMPTY/ROUTER_ABSTAIN "
            "and does not measure router safety.**\n"
        )
        lines.append(
            f"- Rows scored: **{ts['n_resolved']}** / rows unresolved (missing/unknown "
            f"`intent_gt` or `phrase`): {ts['n_unresolved']}"
        )
        lines.append(f"- Overall: {_fmt_stat(ts['overall'])}\n")
        lines.append("| Model | Condition | N | Mean | Median | Stdev |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for key, s in sorted(ts["by_model_condition"].items()):
            model, condition = key.split("/")
            if s["n"] == 0:
                lines.append(f"| {model} | {condition} | 0 | — | — | — |")
            else:
                lines.append(
                    f"| {model} | {condition} | {s['n']} | {s['mean']:.3f} | "
                    f"{s['median']:.3f} | {s['stdev']:.3f} |"
                )
        lines.append("")
        lines.append("By new-taxonomy outcome bucket:\n")
        lines.append("| Outcome | N | Mean | Median | Stdev |")
        lines.append("|---|---:|---:|---:|---:|")
        for outcome, s in sorted(ts["by_outcome"].items()):
            if s["n"] == 0:
                lines.append(f"| {outcome} | 0 | — | — | — |")
            else:
                lines.append(
                    f"| {outcome} | {s['n']} | {s['mean']:.3f} | {s['median']:.3f} | "
                    f"{s['stdev']:.3f} |"
                )
        lines.append("")
        dist = ts["distribution"]
        lines.append(
            "Distribution of scores across all resolved rows: "
            + ", ".join(f"{k}: {v}" for k, v in dist.items()) + "\n"
        )
        lines.append(
            "**What this does and does not prove**: the median similarity across all 180 rows "
            "is 0.0 and the mean is low (~0.17) — most transcripts share zero exact normalized "
            "tokens with the phrase actually spoken, including the majority of `ROUTER_ABSTAIN` "
            "rows (mean ≈ 0.115). This is evidence AGAINST the naive inference \"only 3/180 rows "
            "are STT_EMPTY, so transcription is mostly accurate and abstention is purely a "
            "router-matching problem\" — a non-empty transcript in this dataset is frequently "
            "also a substantially wrong one. It does **not**, by itself, prove the reverse "
            "either (that STT quality alone explains ROUTER_ABSTAIN) — the Tier-1 rule-engine's "
            "substring matching could still fail even on a perfectly transcribed sentence that "
            "phrases the same intent differently than its fixed keyword list expects. Distinguishing "
            "\"bad transcription\" from \"rigid keyword matching\" conclusively would require manual "
            "per-row review, which was not performed here.\n"
        )

    lines.append("## Phase 2 — Phrase manifest drift found and fixed\n")
    lines.append(
        "`tests/eval/stt_intent_eval.py` carried a stale, ASCII/unaccented copy of the "
        "phrase list (e.g. `\"mo chrome\"`), while `tests/eval/record_test_set.py` — the "
        "script that actually drove the committed microphone recordings under "
        "`tests/eval/audio/` — used the real accented Vietnamese prompts "
        "(e.g. `\"mở chrome\"`). Beyond accenting, one entry had drifted in content: "
        "`stt_intent_eval.py` claimed `open_app` variant 4 was `\"launch spotify\"`, but "
        "`record_test_set.py` (the actually-executed recorder) used `\"khởi động chrome\"` "
        "for that slot — that phrase was never recorded.\n"
    )
    lines.append(
        "Fixed by introducing `tests/eval/phrase_manifest.py` as the single source of "
        "truth (preserving `record_test_set.py`'s real prompts verbatim, since those are "
        "what was actually spoken into the microphone). Both `record_test_set.py` and "
        "`stt_intent_eval.py` now import from it instead of keeping local copies. No WAV "
        "file was renamed.\n"
    )
    if phrase_manifest_problems:
        lines.append(f"**Validation found {len(phrase_manifest_problems)} unresolved WAV file(s):**\n")
        for p in phrase_manifest_problems:
            lines.append(f"- {p}")
        lines.append("")
    else:
        lines.append(
            "**Validation**: every committed WAV file under `tests/eval/audio/` resolves "
            "to a manifest phrase (see `tests/eval/phrase_manifest.py::validate_audio_root()` "
            "and its regression test).\n"
        )

    lines.append(EVALUATOR_VS_PRODUCTION_DIFFERENCES)

    lines.append("## Phase 8 — Real production-backend rerun status\n")
    lines.append(production_rerun_status + "\n")

    lines.append("## What this document does NOT do\n")
    lines.append(
        "- Does not edit or overwrite `docs/eval/stt_eval_results.json` or "
        "`docs/eval/stt_eval_summaries.json` — both remain the original committed evidence.\n"
        "- Does not tune `no_speech_threshold`, `log_prob_threshold`, "
        "`compression_ratio_threshold`, production `beam_size`, the hallucination "
        "post-filter, or router behavior.\n"
        "- Does not claim Tier 1 status for STT recognition quality — see "
        "AUDIT_METHODOLOGY.md's criteria; this is a re-classification of existing "
        "evidence, not new acoustic evidence.\n"
    )
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="STT eval failure decomposition (Phase 1/2/4/6)")
    ap.add_argument("--results", default="docs/eval/stt_eval_results.json")
    ap.add_argument("--out-json", default="docs/eval/stt_eval_failure_decomposition.json")
    ap.add_argument("--out-md", default="docs/eval/stt_eval_failure_decomposition.md")
    ap.add_argument("--audio-dir", default="tests/eval/audio")
    ap.add_argument(
        "--production-rerun-status",
        default=None,
        help=(
            "Explicit, human-written description of whether/why a real production-backend "
            "(Phase 8) rerun was executed on THIS machine for THIS invocation. There is "
            "deliberately no machine-specific default — omitting this flag reports a neutral "
            "'not assessed' placeholder rather than silently reusing any prior session's "
            "hardware/dependency findings."
        ),
    )
    args = ap.parse_args()

    results_path = ROOT / args.results
    if not results_path.exists():
        print(f"Results file not found: {results_path}")
        return 1

    results = json.loads(results_path.read_text(encoding="utf-8"))
    decomposition = decompose_results(results)
    text_similarity_stats = compute_text_similarity_stats(results)

    from tests.eval.phrase_manifest import validate_audio_root

    audio_root = ROOT / args.audio_dir
    problems = validate_audio_root(audio_root) if audio_root.exists() else []

    out_json_path = ROOT / args.out_json
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(
        json.dumps(
            {
                **decomposition,
                "phrase_manifest_validation_problems": problems,
                "text_similarity_aux": text_similarity_stats,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    md = render_markdown_report(
        decomposition,
        phrase_manifest_problems=problems,
        text_similarity_stats=text_similarity_stats,
        production_rerun_status=(
            args.production_rerun_status
            if args.production_rerun_status is not None
            else PRODUCTION_RERUN_STATUS_NOT_ASSESSED
        ),
    )
    out_md_path = ROOT / args.out_md
    out_md_path.write_text(md, encoding="utf-8")

    print(f"Wrote {out_json_path}")
    print(f"Wrote {out_md_path}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
