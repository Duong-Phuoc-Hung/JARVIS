"""
tests/eval/stt_intent_eval.py
==============================
Intent Misrouting Rate evaluation framework for JARVIS STT architecture decision.

Design (audit 2026-08-31):
  - Domain-closed metric: Intent Misrouting Rate, NOT absolute WER
  - Two acoustic conditions: clean (quiet room) + noisy (fan/TV background)
  - Three outcome classes:
      CORRECT        = correct intent recognized          (no problem)
      MISROUTED      = wrong intent recognized            (safety risk)
      SILENT_FAILURE = no intent, system abstained        (UX issue only, safer)
  - Confidence threshold CURVE 0.3-0.9 -> Pareto-optimal operating point

IMPORTANT: Each model runs in a SEPARATE SUBPROCESS to guarantee VRAM is
fully released between models. del + torch.cuda.empty_cache() does NOT
reliably free CTranslate2 VRAM on GTX 1650 4GB; subprocess exit does.

NOTE on "confidence" value:
  confidence = exp(avg_logprob) where avg_logprob is faster-whisper's per-token
  log-probability mean. This is a RELATIVE PROXY for comparison across thresholds,
  NOT a calibrated probability ("confidence=0.6" does NOT mean "60% chance correct"
  in the statistical sense). Use only to rank segments against each other.

Beam size: eval uses beam_size=3 (same as latency benchmarks) so latency numbers
are directly comparable. If you change beam_size, latency will differ from the
benchmark tables.
"""
from __future__ import annotations
import argparse, json, math, os, site, statistics, subprocess, sys, time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

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

INTENT_TEST_SET: dict[str, list[str]] = {
    "open_app":       ["mo chrome", "mo ung dung chrome", "mo notepad"],
    "system_shutdown":["tat may tinh", "shutdown may", "tat nguon"],
    "system_restart": ["khoi dong lai may", "restart may tinh", "reboot"],
    "volume_control": ["tang am luong", "giam am luong", "dieu chinh am luong", "tat tieng", "mute"],
    "weather_query":  ["thoi tiet hom nay", "thoi tiet ngay mai", "du bao thoi tiet", "troi hom nay"],
    "timer_set":      ["hen gio 5 phut", "dat timer 10 phut", "nhac toi sau 15 phut"],
    "reminder_set":   ["nhac nho luc 3 gio", "dat nhac luc 8 gio sang"],
    "screenshot":     ["chup man hinh", "chup anh man hinh", "screenshot"],
    "stop":           ["dung lai", "stop", "thoi", "huy"],
    "search":         ["tim kiem google", "tim file word", "search chrome", "tim kiem youtube"],
    "music_play":     ["mo nhac", "phat nhac", "play music", "mo spotify", "launch spotify"],  # Spotify moved here (taxonomy fix)
    "screen_off":     ["tat man hinh", "turn off monitor"],
    "note_take":      ["ghi chu", "tao ghi chu moi"],
    "settings_open":  ["mo cai dat", "open settings"],
}

Outcome = Literal["CORRECT","MISROUTED","SILENT_FAILURE"]

@dataclass
class TrialResult:
    condition: str; intent_gt: str; phrase: str; audio_file: str
    model: str; transcript: str; predicted_intent: str
    outcome: Outcome; confidence: float; latency_ms: float

@dataclass
class EvalSummary:
    model: str; condition: str; n_trials: int
    n_correct: int; n_misrouted: int; n_silent: int
    correct_rate: float; misrouting_rate: float; silent_failure_rate: float
    median_latency_ms: float
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

# Map eval intent category -> acceptable router action_name(s).
# system_power handles BOTH shutdown and restart; screen_capture handles screenshot.
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

_ROUTER = None  # initialised lazily inside subprocess

def predict_intent(transcript: str) -> str:
    """
    Route transcript through Tier-1 rule_engine (deterministic substring match).
    Returns router action_name (e.g. 'system_power') or 'NO_INTENT'.
    Use EXPECTED_ACTIONS to map action_name back to eval intent.
    """
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = _build_router()
    t = transcript.lower().strip()
    if not t: return "NO_INTENT"
    if _ROUTER is not None:
        for keyword, result in _ROUTER.rule_engine.items():
            if keyword in t:
                return result.action_name
    # Fallback: ASCII/English keyword match (stops, reboot, screenshot, etc.)
    simple = {
        "stop": "system_power", "shutdown": "system_power",
        "reboot": "system_power", "restart": "system_power",
        "screenshot": "screen_capture",
        "mute": "system_volume", "play music": "spotify",
        "open settings": "app_open",
    }
    for kw, action in simple.items():
        if kw in t: return action
    return "NO_INTENT"

def avg_logprob_to_confidence(avg_lp: float) -> float:
    """
    PROXY mapping: avg_logprob -> [0,1] via exp().
    Suitable for RELATIVE comparison across thresholds only.
    NOT a calibrated probability — 0.6 does not mean '60% likely correct'.
    Typical range: avg_lp in [-0.3, -1.5], conf in [0.22, 0.74].
    """
    return max(0.0, min(1.0, math.exp(max(avg_lp, -10.0))))

def run_single_model(model_name: str, audio_root: Path, conditions: list[str],
                     language: str, out_path: Path) -> None:
    """
    Inner worker — called in a fresh subprocess so VRAM is fully released
    between models. Writes results as JSON to out_path.
    """
    from faster_whisper import WhisperModel
    import numpy as np

    CACHE = os.path.join(os.environ.get("LOCALAPPDATA",""), "JARVIS","cache","whisper")
    compute = "int8" if model_name == "small" else "int8_float16"
    BEAM_SIZE = 3  # Must match latency benchmarks for comparable numbers

    print(f"\n{'='*60}\nModel: {model_name}  compute={compute}  beam_size={BEAM_SIZE}")
    print(f"NOTE: latency comparable to prior benchmark (also beam_size=3)\n{'='*60}")

    model = WhisperModel(model_name, device="cuda", compute_type=compute,
                         download_root=CACHE)
    aw = (np.random.randn(int(16000*2))*0.05).astype("float32")
    model.transcribe(aw, language=language, beam_size=BEAM_SIZE,
                     condition_on_previous_text=False)
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
                t0 = time.perf_counter()
                segs, _ = model.transcribe(str(wav_path), language=language,
                    beam_size=BEAM_SIZE, condition_on_previous_text=False,
                    no_speech_threshold=0.6, log_prob_threshold=-1.0,
                    compression_ratio_threshold=2.4)
                texts, lps = [], []
                for s in segs:
                    texts.append(s.text.strip())
                    if hasattr(s,"avg_logprob"): lps.append(s.avg_logprob)
                lat_ms = (time.perf_counter()-t0)*1000
                transcript = " ".join(texts).strip()
                conf = avg_logprob_to_confidence(
                    statistics.mean(lps) if lps else -99.0)
                # Route via real Tier-1 rule_engine; compare using EXPECTED_ACTIONS
                pred_action = predict_intent(transcript)
                expected = EXPECTED_ACTIONS.get(intent_gt, set())
                if pred_action == "NO_INTENT":    outcome: Outcome = "SILENT_FAILURE"
                elif pred_action in expected:      outcome = "CORRECT"
                else:                              outcome = "MISROUTED"
                icon = {"CORRECT":"✓","MISROUTED":"✗","SILENT_FAILURE":"○"}[outcome]
                print(f"    {icon} [{lat_ms:>5.0f}ms c={conf:.2f}] "
                      f"{intent_gt} -> '{transcript[:35]}' -> {pred_action}")
                results.append(asdict(TrialResult(condition=condition,
                    intent_gt=intent_gt, phrase=wav_path.stem,
                    audio_file=str(wav_path), model=model_name,
                    transcript=transcript, predicted_intent=pred_action,
                    outcome=outcome, confidence=conf, latency_ms=lat_ms)))

    # Write results; subprocess exit releases all VRAM cleanly
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Saved {len(results)} trials -> {out_path}")

def compute_threshold_curve(results, thresholds=None):
    thresholds = thresholds or [0.3,0.4,0.5,0.6,0.7,0.8,0.9]
    n = len(results); curve = {}
    if not n: return curve
    for t in thresholds:
        c=m=s=0
        for r in results:
            if r["confidence"] < t: s += 1
            elif r["outcome"]=="CORRECT": c += 1
            elif r["outcome"]=="MISROUTED": m += 1
            else: s += 1
        curve[str(t)] = {"correct":c/n,"misrouting":m/n,"silent":s/n}
    return curve

def summarize(results, model, condition):
    sub = [r for r in results if r["model"]==model and r["condition"]==condition]
    n = len(sub)
    if not n: return EvalSummary(model=model,condition=condition,n_trials=0,
        n_correct=0,n_misrouted=0,n_silent=0,correct_rate=0,
        misrouting_rate=0,silent_failure_rate=0,median_latency_ms=0)
    nc=sum(1 for r in sub if r["outcome"]=="CORRECT")
    nm=sum(1 for r in sub if r["outcome"]=="MISROUTED")
    ns=sum(1 for r in sub if r["outcome"]=="SILENT_FAILURE")
    return EvalSummary(model=model,condition=condition,n_trials=n,
        n_correct=nc,n_misrouted=nm,n_silent=ns,
        correct_rate=nc/n,misrouting_rate=nm/n,silent_failure_rate=ns/n,
        median_latency_ms=statistics.median(r["latency_ms"] for r in sub),
        threshold_curve=compute_threshold_curve(sub))

def print_report(summaries):
    print(f"\n{'='*72}\nEVALUATION REPORT — Intent Misrouting Rate\n{'='*72}")
    print(f"Confidence note: proxy via exp(avg_logprob) — relative comparison only,")
    print(f"NOT calibrated probability. beam_size=3 (matches latency benchmark).\n")
    print(f"{'Model':<12}{'Cond':<8}{'N':>4} | {'Correct':>8}{'Misrouted':>11}{'Silent':>9} | {'Lat(p50)':>10}")
    print("-"*72)
    for s in summaries:
        print(f"{s.model:<12}{s.condition:<8}{s.n_trials:>4} | "
              f"{s.correct_rate:>7.1%}  {s.misrouting_rate:>9.1%}  "
              f"{s.silent_failure_rate:>8.1%} | {s.median_latency_ms:>9.0f}ms")
    print("\nOutcomes: CORRECT=ok | MISROUTED=safety risk | SILENT_FAILURE=UX issue, not safety risk")
    first = next((s for s in summaries if s.threshold_curve and s.condition=="clean"), None)
    if first:
        print(f"\nConfidence threshold curve — {first.model}, clean condition:")
        print(f"  (Each threshold: trials below it treated as SILENT_FAILURE)")
        print(f"  {'t':>5} | {'Correct':>8} | {'Misrouted':>10} | {'Silent':>8}")
        for t,v in sorted(first.threshold_curve.items(),key=lambda x:float(x[0])):
            mark = "  <-- Pareto candidate" if v["misrouting"]<0.05 and v["silent"]<0.30 else ""
            print(f"  {float(t):>5.1f} | {v['correct']:>7.1%}  | {v['misrouting']:>9.1%}  | {v['silent']:>7.1%}{mark}")
        print("\n  Goal: lowest misrouting_rate where silent_failure_rate stays < 30%")

def main():
    ap = argparse.ArgumentParser(description="JARVIS STT Intent Misrouting Rate Evaluator")
    ap.add_argument("--models", nargs="+", default=["small","large-v3"])
    ap.add_argument("--conditions", nargs="+", default=["clean","noisy"])
    ap.add_argument("--audio-dir", default="tests/eval/audio")
    ap.add_argument("--out-dir", default="docs/eval")
    ap.add_argument("--language", default="vi")
    # Internal flag: run as subprocess worker for one model
    ap.add_argument("--_worker-model", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--_worker-out", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    audio_root = ROOT / args.audio_dir
    out_dir = ROOT / args.out_dir

    # ── SUBPROCESS WORKER MODE (called internally) ────────────────────────────
    if args._worker_model:
        run_single_model(
            model_name=args._worker_model,
            audio_root=audio_root,
            conditions=args.conditions,
            language=args.language,
            out_path=Path(args._worker_out),
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
        tmp_path = out_dir / f"_tmp_{model_name.replace('-','_')}.json"
        tmp_files.append(tmp_path)
        print(f"\nLaunching subprocess for model: {model_name}")
        print("(Subprocess ensures VRAM fully released before next model loads)")
        cmd = [sys.executable, str(Path(__file__)), "--_worker-model", model_name,
               "--_worker-out", str(tmp_path),
               "--audio-dir", args.audio_dir,
               "--out-dir", args.out_dir,
               "--conditions"] + args.conditions + ["--language", args.language]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"  ERROR: subprocess for {model_name} failed (exit {r.returncode})")
            continue
        if tmp_path.exists():
            all_results.extend(json.loads(tmp_path.read_text(encoding="utf-8")))

    # Cleanup tmp files
    for f in tmp_files:
        if f.exists(): f.unlink()

    if not all_results:
        print("No results collected."); return 1

    summaries = []
    for m in args.models:
        for c in args.conditions:
            s = summarize(all_results, m, c)
            if s.n_trials > 0: summaries.append(s)

    print_report(summaries)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir/"stt_eval_results.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir/"stt_eval_summaries.json").write_text(
        json.dumps([asdict(s) for s in summaries], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFull results: {out_dir}/stt_eval_results.json")
    print(f"Summaries:    {out_dir}/stt_eval_summaries.json")
    return 0

if __name__ == "__main__": sys.exit(main())
