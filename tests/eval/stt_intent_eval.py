"""
tests/eval/stt_intent_eval.py
==============================
Intent Misrouting Rate evaluation framework for JARVIS STT architecture decision.

Design (audit 2026-08-31, corrected 2026-09-02):
  - Domain-closed metric: Intent Misrouting Rate, NOT absolute WER
  - Two acoustic conditions: clean (quiet room) + noisy (fan/TV background)
  - Four outcome classes (corrected taxonomy — see tests/eval/failure_decomposition.py):
      CORRECT        = correct intent recognized              (no problem)
      MISROUTED      = wrong intent recognized                (safety risk)
      STT_EMPTY      = STT produced no transcript at all       (pure recognition failure)
      ROUTER_ABSTAIN = STT produced text, router found no match (routing/keyword-match gap)
    The historical 3-way taxonomy (CORRECT/MISROUTED/SILENT_FAILURE) collapsed
    STT_EMPTY and ROUTER_ABSTAIN into one bucket — see
    docs/eval/stt_eval_failure_decomposition.md for the corrected breakdown of
    already-committed historical results. This file's *own* live evaluation
    runs now use the 4-way taxonomy directly.
  - Confidence threshold CURVE 0.3-0.9 -> Pareto-optimal operating point
    (direct backend only — see --backend below)

IMPORTANT: Each model runs in a SEPARATE SUBPROCESS to guarantee VRAM is
fully released between models. del + torch.cuda.empty_cache() does NOT
reliably free CTranslate2 VRAM on GTX 1650 4GB; subprocess exit does.

NOTE on "confidence" value:
  confidence = exp(avg_logprob) where avg_logprob is faster-whisper's per-token
  log-probability mean. This is a RELATIVE PROXY for comparison across thresholds,
  NOT a calibrated probability ("confidence=0.6" does NOT mean "60% chance correct"
  in the statistical sense). Use only to rank segments against each other.
  Only the --backend direct path can compute this (see BACKENDS below); the
  production backend's FasterWhisperSTT.transcribe() does not return per-segment
  log-probabilities to the caller, so confidence is None/absent for those rows.

BACKENDS (--backend):
  direct     = historical raw faster_whisper.WhisperModel path, beam_size=3,
               unchanged from the original 2026-08-31 framework — preserved so
               already-committed historical results stay reproducible.
  production = calls jarvis.stt.engine.FasterWhisperSTT.transcribe() directly
               (production default beam_size=5, production hallucination
               filtering). Does NOT reimplement production filtering logic —
               it is the same class production code uses.

Beam size: direct backend uses beam_size=3 (same as latency benchmarks) so
latency numbers are directly comparable to prior benchmark tables. The
production backend uses whatever FasterWhisperSTT's own default is (5); do not
compare direct-backend and production-backend latency numbers as if they used
the same beam_size.

Output files default to a backend-suffixed name (e.g.
docs/eval/stt_eval_results_direct.json) so a new run never silently overwrites
the historical, already-committed docs/eval/stt_eval_results.json /
stt_eval_summaries.json evidence. Pass --out-results-name/--out-summaries-name
explicitly if you deliberately want different filenames.
"""
from __future__ import annotations
import argparse, json, math, os, site, statistics, subprocess, sys, time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

if sys.platform == "win32":
    for _sp in site.getsitepackages():
        _nr = os.path.join(_sp, "nvidia")
        if not os.path.isdir(_nr): continue
        for _p in os.listdir(_nr):
            _bd = os.path.join(_nr, _p, "bin")
            if os.path.isdir(_bd):
                if hasattr(os, "add_dll_directory"): os.add_dll_directory(_bd)
                if _bd not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = _bd + os.pathsep + os.environ["PATH"]

from tests.eval.failure_decomposition import EXPECTED_ACTIONS, Outcome, classify_outcome
from tests.eval.phrase_manifest import PHRASE_MANIFEST as INTENT_TEST_SET
from tests.eval.phrase_manifest import resolve_phrase_for_wav
from tests.eval.text_normalize import token_similarity

BACKENDS = ("direct", "production")

# --- Merge note (origin/main v4.4.0, 2026-09-02) -----------------------------
# origin/main independently edited this file's old hardcoded INTENT_TEST_SET
# dict, moving "mo spotify"/"launch spotify" from the "open_app" category to
# "music_play" (see CHANGELOG.md's v4.4.0 "Eval Taxonomy Fix" entry). That
# dict no longer exists here: PHRASE_MANIFEST (tests/eval/phrase_manifest.py)
# replaced it as the single source of truth, preserving the phrases actually
# spoken for the 90 committed WAV recordings -- including "mở spotify" filed
# under open_app/variant_3, which is real recorded ground truth and is not
# renamed or moved just because a routing taxonomy elsewhere changed.
#
# origin/main's underlying observation is still correct and independently
# reproducible against the real dataset: EXPECTED_ACTIONS["open_app"] below
# does not include "spotify", and the Tier-1 router now (as of v4.4.0)
# consistently routes "mở spotify" to action_name="spotify" -- so all 4
# historical MISROUTED rows in docs/eval/stt_eval_results.json are exactly
# this one case (open_app/variant_3, all 4 model/condition combinations).
# EXPECTED_ACTIONS is deliberately NOT widened to also accept "spotify" under
# "open_app" here, because doing so would silently reclassify those 4
# historical MISROUTED rows to CORRECT without any new acoustic evidence --
# see AUDIT_METHODOLOGY.md's rule against editing historical evidence to fit
# a taxonomy change. This is a real, documented ambiguity in the original
# eval design (a phrase that could reasonably belong to either open_app or
# music_play), not a router defect and not evaluator error -- left as a known
# open question for future evaluation-taxonomy revision, not resolved here.


@dataclass
class TrialResult:
    condition: str; intent_gt: str; phrase: str; audio_file: str
    model: str; backend: str; transcript: str; predicted_intent: str
    outcome: Outcome; confidence: float | None; latency_ms: float
    text_similarity: float | None = None  # auxiliary only — see text_normalize.py

@dataclass
class EvalSummary:
    model: str; condition: str; backend: str; n_trials: int
    n_correct: int; n_misrouted: int; n_stt_empty: int; n_router_abstain: int
    correct_rate: float; misrouting_rate: float
    stt_empty_rate: float; router_abstain_rate: float
    end_to_end_abstention_rate: float
    median_latency_ms: float
    mean_text_similarity: float | None = None
    threshold_curve: dict[str, dict[str, float]] = field(default_factory=dict)

def _build_router():
    """Build LLMIntentRouter using only Tier-1 rule_engine (no LLM calls needed)."""
    try:
        from jarvis.llm.router import LLMIntentRouter

        class _FakeDispatcher:
            def get_available_actions(self): return []
            def get_action(self, name): return None

        return LLMIntentRouter(llm_client=None, dispatcher=_FakeDispatcher(),
                               fast_path_enabled=True)
    except Exception as e:
        print(f"  WARNING: could not build router ({e}) — using keyword fallback")
        return None

_ROUTER = None  # initialised lazily inside subprocess

def predict_intent(transcript: str) -> str:
    """
    Route transcript through Tier-1 production router with safe diacritic normalization.
    Returns router action_name (e.g. 'system_power') or 'NO_INTENT'.
    Use EXPECTED_ACTIONS to map action_name back to eval intent.
    """
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = _build_router()
    t = transcript.strip()
    if not t:
        return "NO_INTENT"
    if _ROUTER is not None:
        try:
            res = _ROUTER.parse_intent(t, force_llm=False)
            if res and res.action_name and res.action_name not in ("unknown_intent", "generic_llm_response"):
                return res.action_name
        except Exception:
            pass
    # Fallback: ASCII/English keyword match (stops, reboot, screenshot, etc.)
    simple = {
        "stop": "system_power", "shutdown": "system_power",
        "reboot": "system_power", "restart": "system_power",
        "screenshot": "screen_capture",
        "mute": "system_volume", "play music": "spotify",
        "open settings": "app_open",
    }
    t_lower = t.lower()
    for kw, action in simple.items():
        if kw in t_lower:
            return action
    return "NO_INTENT"

def avg_logprob_to_confidence(avg_lp: float) -> float:
    """
    PROXY mapping: avg_logprob -> [0,1] via exp().
    Suitable for RELATIVE comparison across thresholds only.
    NOT a calibrated probability — 0.6 does not mean '60% likely correct'.
    Typical range: avg_lp in [-0.3, -1.5], conf in [0.22, 0.74].
    """
    return max(0.0, min(1.0, math.exp(max(avg_lp, -10.0))))


def _text_similarity_for_wav(wav_path: Path, transcript: str) -> float | None:
    """Auxiliary only (Phase 3) — None if the wav doesn't resolve to a manifest phrase."""
    expected_phrase = resolve_phrase_for_wav(wav_path)
    if expected_phrase is None:
        return None
    return token_similarity(expected_phrase, transcript)


def _transcribe_direct(model: Any, wav_path: Path, language: str, beam_size: int) -> tuple[str, float | None, float]:
    """Historical direct backend — unchanged raw WhisperModel call. Returns (transcript, confidence, latency_ms)."""
    t0 = time.perf_counter()
    segs, _ = model.transcribe(str(wav_path), language=language,
        beam_size=beam_size, condition_on_previous_text=False,
        no_speech_threshold=0.6, log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4)
    texts, lps = [], []
    for s in segs:
        texts.append(s.text.strip())
        if hasattr(s, "avg_logprob"): lps.append(s.avg_logprob)
    lat_ms = (time.perf_counter() - t0) * 1000
    transcript = " ".join(texts).strip()
    conf = avg_logprob_to_confidence(statistics.mean(lps) if lps else -99.0)
    return transcript, conf, lat_ms


def _transcribe_production(engine: Any, wav_path: Path, language: str) -> tuple[str, float | None, float]:
    """
    Production backend — calls FasterWhisperSTT.transcribe() directly, no
    reimplementation of its filtering. Confidence is not available: the
    abstraction returns only the final string, not per-segment log-probs.
    """
    t0 = time.perf_counter()
    transcript = engine.transcribe(str(wav_path), language=language)
    lat_ms = (time.perf_counter() - t0) * 1000
    return transcript.strip(), None, lat_ms


def run_single_model(model_name: str, audio_root: Path, conditions: list[str],
                     language: str, out_path: Path, backend: str) -> None:
    """
    Inner worker — called in a fresh subprocess so VRAM is fully released
    between models. Writes results as JSON to out_path.
    """
    import numpy as np

    CACHE = os.path.join(os.environ.get("LOCALAPPDATA",""), "JARVIS","cache","whisper")
    compute = "int8" if model_name == "small" else "int8_float16"
    BEAM_SIZE = 3  # direct backend only — must match latency benchmarks for comparable numbers

    device = "cuda"
    try:
        import torch
        if not torch.cuda.is_available():
            device = "cpu"
    except Exception:
        device = "cpu"

    print(f"\n{'='*60}\nModel: {model_name}  backend={backend}  compute={compute}  device={device}")
    if backend == "direct":
        print(f"beam_size={BEAM_SIZE} (NOTE: latency comparable to prior benchmark, also beam_size=3)")
    else:
        print("beam_size=production default (5); confidence unavailable for this backend")
    print("=" * 60)

    if backend == "direct":
        from faster_whisper import WhisperModel
        compute_mode = "int8" if device == "cpu" else compute
        try:
            model = WhisperModel(model_name, device=device, compute_type=compute_mode, download_root=CACHE)
        except Exception as e:
            if device == "cuda":
                print(f"  CUDA init failed ({e}), falling back to CPU")
                device = "cpu"
                compute_mode = "int8"
                model = WhisperModel(model_name, device=device, compute_type=compute_mode, download_root=CACHE)
            else:
                raise
        aw = (np.random.randn(int(16000 * 2)) * 0.05).astype("float32")
        model.transcribe(aw, language=language, beam_size=BEAM_SIZE, condition_on_previous_text=False)
    else:
        from jarvis.stt.engine import FasterWhisperSTT
        compute_mode = "int8" if device == "cpu" else compute
        try:
            model = FasterWhisperSTT({
                "model_size": model_name, "compute_type": compute_mode,
                "device": device, "download_root": CACHE,
            })
        except Exception as e:
            if device == "cuda":
                print(f"  CUDA init failed ({e}), falling back to CPU")
                device = "cpu"
                compute_mode = "int8"
                model = FasterWhisperSTT({
                    "model_size": model_name, "compute_type": compute_mode,
                    "device": device, "download_root": CACHE,
                })
            else:
                raise
        aw = (np.random.randn(int(16000 * 2)) * 0.05).astype("float32")
        model.transcribe(aw, language=language)
    print("  Warmup done")

    results = []
    for condition in conditions:
        cond_dir = audio_root / condition
        if not cond_dir.exists():
            print(f"  WARNING: {cond_dir} not found — skipping"); continue
        print(f"\n  Condition: {condition}")
        for intent_dir in sorted(cond_dir.iterdir()):
            if not intent_dir.is_dir(): continue
            intent_gt = intent_dir.name
            for wav_path in sorted(intent_dir.glob("*.wav")):
                if backend == "direct":
                    transcript, conf, lat_ms = _transcribe_direct(model, wav_path, language, BEAM_SIZE)
                else:
                    transcript, conf, lat_ms = _transcribe_production(model, wav_path, language)

                pred_action = predict_intent(transcript)
                outcome: Outcome = classify_outcome(transcript, pred_action, intent_gt, EXPECTED_ACTIONS)
                sim = _text_similarity_for_wav(wav_path, transcript)

                icon = {"CORRECT": "✓", "MISROUTED": "✗",
                        "STT_EMPTY": "○", "ROUTER_ABSTAIN": "○"}[outcome]
                conf_str = f"c={conf:.2f}" if conf is not None else "c=n/a"
                print(f"    {icon} [{lat_ms:>5.0f}ms {conf_str}] "
                      f"{intent_gt} -> '{transcript[:35]}' -> {pred_action} ({outcome})")
                results.append(asdict(TrialResult(condition=condition,
                    intent_gt=intent_gt, phrase=wav_path.stem,
                    audio_file=str(wav_path), model=model_name, backend=backend,
                    transcript=transcript, predicted_intent=pred_action,
                    outcome=outcome, confidence=conf, latency_ms=lat_ms,
                    text_similarity=sim)))

    # Write results; subprocess exit releases all VRAM cleanly
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Saved {len(results)} trials -> {out_path}")

def compute_threshold_curve(results, thresholds=None):
    """Direct-backend only — needs a numeric confidence per trial. Rows with
    confidence=None (production backend) are excluded; returns {} if none qualify."""
    thresholds = thresholds or [0.3,0.4,0.5,0.6,0.7,0.8,0.9]
    scored = [r for r in results if r.get("confidence") is not None]
    n = len(scored); curve = {}
    if not n: return curve
    for t in thresholds:
        c=m=s=0
        for r in scored:
            if r["confidence"] < t: s += 1
            elif r["outcome"]=="CORRECT": c += 1
            elif r["outcome"]=="MISROUTED": m += 1
            else: s += 1
        curve[str(t)] = {"correct":c/n,"misrouting":m/n,"end_to_end_abstention":s/n}
    return curve

def summarize(results, model, condition, backend):
    sub = [r for r in results if r["model"]==model and r["condition"]==condition and r["backend"]==backend]
    n = len(sub)
    if not n:
        return EvalSummary(model=model, condition=condition, backend=backend, n_trials=0,
            n_correct=0, n_misrouted=0, n_stt_empty=0, n_router_abstain=0,
            correct_rate=0, misrouting_rate=0, stt_empty_rate=0, router_abstain_rate=0,
            end_to_end_abstention_rate=0, median_latency_ms=0)
    nc = sum(1 for r in sub if r["outcome"] == "CORRECT")
    nm = sum(1 for r in sub if r["outcome"] == "MISROUTED")
    ne = sum(1 for r in sub if r["outcome"] == "STT_EMPTY")
    na = sum(1 for r in sub if r["outcome"] == "ROUTER_ABSTAIN")
    sims = [r["text_similarity"] for r in sub if r.get("text_similarity") is not None]
    return EvalSummary(model=model, condition=condition, backend=backend, n_trials=n,
        n_correct=nc, n_misrouted=nm, n_stt_empty=ne, n_router_abstain=na,
        correct_rate=nc/n, misrouting_rate=nm/n,
        stt_empty_rate=ne/n, router_abstain_rate=na/n,
        end_to_end_abstention_rate=(ne+na)/n,
        median_latency_ms=statistics.median(r["latency_ms"] for r in sub),
        mean_text_similarity=(statistics.mean(sims) if sims else None),
        threshold_curve=compute_threshold_curve(sub))

def print_report(summaries):
    print(f"\n{'='*88}\nEVALUATION REPORT — Intent Misrouting Rate (corrected 4-way taxonomy)\n{'='*88}")
    print("Confidence note: proxy via exp(avg_logprob), direct backend only — relative")
    print("comparison only, NOT calibrated probability.\n")
    print(f"{'Model':<10}{'Cond':<7}{'Backend':<11}{'N':>4} | {'Correct':>8}{'Misroute':>9}"
          f"{'STT_empty':>10}{'RtrAbst':>9} | {'Lat(p50)':>10}")
    print("-"*88)
    for s in summaries:
        print(f"{s.model:<10}{s.condition:<7}{s.backend:<11}{s.n_trials:>4} | "
              f"{s.correct_rate:>7.1%} {s.misrouting_rate:>8.1%} "
              f"{s.stt_empty_rate:>9.1%} {s.router_abstain_rate:>8.1%} | {s.median_latency_ms:>9.0f}ms")
    print("\nOutcomes: CORRECT=ok | MISROUTED=safety risk | STT_EMPTY=pure recognition failure |")
    print("ROUTER_ABSTAIN=transcript non-empty but no keyword matched (UX issue, not proven safety risk)")
    first = next((s for s in summaries if s.threshold_curve and s.condition=="clean"), None)
    if first:
        print(f"\nConfidence threshold curve — {first.model}/{first.backend}, clean condition:")
        print(f"  (Each threshold: trials below it treated as abstained)")
        print(f"  {'t':>5} | {'Correct':>8} | {'Misrouted':>10} | {'Abstained':>9}")
        for t,v in sorted(first.threshold_curve.items(),key=lambda x:float(x[0])):
            mark = "  <-- Pareto candidate" if v["misrouting"]<0.05 and v["end_to_end_abstention"]<0.30 else ""
            print(f"  {float(t):>5.1f} | {v['correct']:>7.1%}  | {v['misrouting']:>9.1%}  | {v['end_to_end_abstention']:>8.1%}{mark}")
        print("\n  Goal: lowest misrouting_rate where abstention_rate stays < 30%")

def main():
    ap = argparse.ArgumentParser(description="JARVIS STT Intent Misrouting Rate Evaluator")
    ap.add_argument("--models", nargs="+", default=["small","large-v3"])
    ap.add_argument("--conditions", nargs="+", default=["clean","noisy"])
    ap.add_argument("--audio-dir", default="tests/eval/audio")
    ap.add_argument("--out-dir", default="docs/eval")
    ap.add_argument("--language", default="vi")
    ap.add_argument("--backend", choices=BACKENDS, default="direct",
                     help="'direct' = historical raw WhisperModel path (reproduces old results). "
                          "'production' = calls jarvis.stt.engine.FasterWhisperSTT directly.")
    ap.add_argument("--out-results-name", default=None,
                     help="Override output results filename. Default is backend-suffixed "
                          "(e.g. stt_eval_results_direct.json) so historical committed "
                          "evidence is never overwritten by default.")
    ap.add_argument("--out-summaries-name", default=None,
                     help="Override output summaries filename (see --out-results-name).")
    ap.add_argument("--cached-transcripts", action="store_true",
                     help="Evaluate routing accuracy using cached transcripts from previous runs without re-running STT audio inference.")
    # Internal flag: run as subprocess worker for one model
    ap.add_argument("--_worker-model", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--_worker-out", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--_worker-backend", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    audio_root = ROOT / args.audio_dir
    out_dir = ROOT / args.out_dir
    results_name = args.out_results_name or f"stt_eval_results_{args.backend}.json"
    summaries_name = args.out_summaries_name or f"stt_eval_summaries_{args.backend}.json"
    cached_source = out_dir / results_name
    if not cached_source.exists():
        cached_source = out_dir / f"stt_eval_results_{args.backend}.json"

    # ── CACHED TRANSCRIPTS EVALUATION ─────────────────────────────────────────
    def _evaluate_cached(source_path: Path):
        print(f"Re-evaluating routing accuracy on cached transcripts: {source_path}")
        raw_entries = json.loads(source_path.read_text(encoding="utf-8"))
        evaluated = []
        for r in raw_entries:
            if r.get("model") not in args.models or r.get("condition") not in args.conditions:
                continue
            transcript = r.get("transcript", "")
            intent_gt = r.get("intent_gt", "")
            wav_path = Path(r.get("audio_file", ""))
            pred_action = predict_intent(transcript)
            outcome: Outcome = classify_outcome(transcript, pred_action, intent_gt, EXPECTED_ACTIONS)
            sim = _text_similarity_for_wav(wav_path, transcript) if wav_path.exists() else r.get("text_similarity")
            r_copy = dict(r)
            r_copy["predicted_intent"] = pred_action
            r_copy["outcome"] = outcome
            r_copy["text_similarity"] = sim
            evaluated.append(r_copy)

        summaries = []
        for m in args.models:
            for c in args.conditions:
                s = summarize(evaluated, m, c, args.backend)
                if s.n_trials > 0:
                    summaries.append(s)

        print_report(summaries)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / results_name).write_text(
            json.dumps(evaluated, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / summaries_name).write_text(
            json.dumps([asdict(s) for s in summaries], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nFull results: {out_dir}/{results_name}")
        print(f"Summaries:    {out_dir}/{summaries_name}")
        return 0

    if args.cached_transcripts:
        if not cached_source.exists():
            print(f"Cached results file not found: {cached_source}")
            return 1
        return _evaluate_cached(cached_source)

    # ── SUBPROCESS WORKER MODE (called internally) ────────────────────────────
    if args._worker_model:
        run_single_model(
            model_name=args._worker_model,
            audio_root=audio_root,
            conditions=args.conditions,
            language=args.language,
            out_path=Path(args._worker_out),
            backend=args._worker_backend or args.backend,
        )
        return 0

    # ── ORCHESTRATOR MODE ─────────────────────────────────────────────────────
    if not audio_root.exists():
        print(f"Audio directory not found: {audio_root}")
        print("\nExpected structure:")
        print("  tests/eval/audio/{clean,noisy}/{intent_name}/variant_N.wav")
        print("\nRecord with: python tests/eval/record_test_set.py")
        return 1

    all_results = []
    tmp_files = []

    for model_name in args.models:
        tmp_path = out_dir / f"_tmp_{model_name.replace('-','_')}_{args.backend}.json"
        tmp_files.append(tmp_path)
        print(f"\nLaunching subprocess for model: {model_name} (backend={args.backend})")
        print("(Subprocess ensures VRAM fully released before next model loads)")
        cmd = [sys.executable, str(Path(__file__)), "--_worker-model", model_name,
               "--_worker-out", str(tmp_path), "--_worker-backend", args.backend,
               "--audio-dir", args.audio_dir,
               "--out-dir", args.out_dir,
               "--conditions"] + args.conditions + ["--language", args.language]
        r = subprocess.run(cmd, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if r.returncode != 0:
            print(f"  ERROR: subprocess for {model_name} failed (exit {r.returncode})")
            continue
        if tmp_path.exists():
            all_results.extend(json.loads(tmp_path.read_text(encoding="utf-8")))

    # Cleanup tmp files
    for f in tmp_files:
        if f.exists(): f.unlink()

    if not all_results:
        if cached_source.exists():
            print(f"No results from live audio transcription. Falling back to cached transcripts from {cached_source}...")
            return _evaluate_cached(cached_source)
        print("No results collected."); return 1

    summaries = []
    for m in args.models:
        for c in args.conditions:
            s = summarize(all_results, m, c, args.backend)
            if s.n_trials > 0: summaries.append(s)

    print_report(summaries)

    out_dir.mkdir(parents=True, exist_ok=True)
    results_name = args.out_results_name or f"stt_eval_results_{args.backend}.json"
    summaries_name = args.out_summaries_name or f"stt_eval_summaries_{args.backend}.json"
    (out_dir/results_name).write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir/summaries_name).write_text(
        json.dumps([asdict(s) for s in summaries], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFull results: {out_dir}/{results_name}")
    print(f"Summaries:    {out_dir}/{summaries_name}")
    print("\n(Historical docs/eval/stt_eval_results.json and stt_eval_summaries.json were NOT touched.)")
    return 0

if __name__ == "__main__": sys.exit(main())
