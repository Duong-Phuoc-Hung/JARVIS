"""
tests/eval/stt_intent_eval.py
==============================
Intent Misrouting Rate evaluation framework for JARVIS STT architecture decision.

Design (from audit 2026-08-31):
  - Domain-closed system metric: Intent Misrouting Rate, NOT absolute WER
  - Two acoustic conditions: CLEAN (quiet room) and NOISY (fan/TV background)
  - Three outcome classes: CORRECT / MISROUTED / SILENT_FAILURE
    (misrouted=safety risk, silent=UX issue only — very different implications)
  - Confidence threshold CURVE across 0.3-0.9 to find Pareto-optimal threshold,
    not a single binary test at 0.6

Usage:
  python tests/eval/stt_intent_eval.py --models small large-v3
  Results -> docs/eval/stt_eval_results.json + stt_eval_summaries.json

Audio structure:
  tests/eval/audio/
    clean/open_app/variant_0.wav  ...
    noisy/open_app/variant_0.wav  ...
"""
from __future__ import annotations
import argparse, json, math, os, site, statistics, sys, time
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

# Ground-truth intent test set (from intent_router.py rules)
INTENT_TEST_SET: dict[str, list[str]] = {
    "open_app":       ["mo chrome","mo ung dung chrome","mo notepad","mo spotify","launch spotify"],
    "system_shutdown":["tat may tinh","shutdown may","tat nguon"],
    "system_restart": ["khoi dong lai may","restart may tinh","reboot"],
    "volume_control": ["tang am luong","giam am luong","dieu chinh am luong","tat tieng","mute"],
    "weather_query":  ["thoi tiet hom nay","thoi tiet ngay mai","du bao thoi tiet","troi hom nay"],
    "timer_set":      ["hen gio 5 phut","dat timer 10 phut","nhac toi sau 15 phut"],
    "reminder_set":   ["nhac nho luc 3 gio","dat nhac luc 8 gio sang"],
    "screenshot":     ["chup man hinh","chup anh man hinh","screenshot"],
    "stop":           ["dung lai","stop","thoi","huy"],
    "search":         ["tim kiem google","tim file word","search chrome"],
    "music_play":     ["mo nhac","phat nhac","play music"],
    "screen_off":     ["tat man hinh","turn off monitor"],
    "note_take":      ["ghi chu","tao ghi chu moi"],
    "settings_open":  ["mo cai dat","open settings"],
}

Outcome = Literal["CORRECT", "MISROUTED", "SILENT_FAILURE"]

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

def predict_intent(transcript: str) -> str:
    if not transcript.strip(): return "NO_INTENT"
    try:
        from jarvis.llm.router import IntentRouter
        r = IntentRouter().route(transcript)
        return r.intent if r and getattr(r, "intent", None) else "NO_INTENT"
    except Exception:
        t = transcript.lower()
        for intent, phrases in INTENT_TEST_SET.items():
            for ph in phrases:
                if all(w in t for w in ph.split()[:2]): return intent
        return "NO_INTENT"

def transcribe_with_confidence(model, audio_path: str, language="vi", beam_size=5):
    segs, _ = model.transcribe(audio_path, language=language, beam_size=beam_size,
        condition_on_previous_text=False, no_speech_threshold=0.6,
        logprob_threshold=-1.0, compression_ratio_threshold=2.4)
    texts, lps = [], []
    for s in segs:
        texts.append(s.text.strip())
        if hasattr(s, "avg_logprob"): lps.append(s.avg_logprob)
    avg_lp = statistics.mean(lps) if lps else -99.0
    return " ".join(texts).strip(), max(0.0, min(1.0, math.exp(max(avg_lp, -10.0))))

def compute_threshold_curve(results, thresholds=None):
    thresholds = thresholds or [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    n = len(results)
    if not n: return {}
    curve = {}
    for t in thresholds:
        c = m = s = 0
        for r in results:
            if r.confidence < t: s += 1
            elif r.outcome == "CORRECT": c += 1
            elif r.outcome == "MISROUTED": m += 1
            else: s += 1
        curve[str(t)] = {"correct": c/n, "misrouting": m/n, "silent": s/n}
    return curve

def evaluate_model(model_name, audio_root, conditions, language="vi"):
    from faster_whisper import WhisperModel
    import numpy as np
    CACHE = os.path.join(os.environ.get("LOCALAPPDATA",""), "JARVIS","cache","whisper")
    compute = "int8" if model_name == "small" else "int8_float16"
    print(f"\n{'='*60}\nModel: {model_name}  compute={compute}\n{'='*60}")
    model = WhisperModel(model_name, device="cuda", compute_type=compute, download_root=CACHE)
    aw = (np.random.randn(int(16000*2))*0.05).astype("float32")
    model.transcribe(aw, language=language, beam_size=3, condition_on_previous_text=False)
    print("  Warmup done")
    results = []
    for condition in conditions:
        cond_dir = audio_root / condition
        if not cond_dir.exists():
            print(f"  WARNING: {cond_dir} not found"); continue
        print(f"\n  Condition: {condition}")
        for intent_dir in sorted(cond_dir.iterdir()):
            if not intent_dir.is_dir(): continue
            intent_gt = intent_dir.name
            for wav_path in sorted(intent_dir.glob("*.wav")):
                t0 = time.perf_counter()
                transcript, conf = transcribe_with_confidence(model, str(wav_path), language)
                lat_ms = (time.perf_counter()-t0)*1000
                pred = predict_intent(transcript)
                outcome: Outcome = ("NO_INTENT" == pred and "SILENT_FAILURE") or \
                                   (pred == intent_gt and "CORRECT") or "MISROUTED"
                icon = {"CORRECT":"✓","MISROUTED":"✗","SILENT_FAILURE":"○"}[outcome]
                print(f"    {icon} [{lat_ms:>5.0f}ms c={conf:.2f}] {intent_gt} → '{transcript[:35]}' → {pred}")
                results.append(TrialResult(condition=condition, intent_gt=intent_gt,
                    phrase=wav_path.stem, audio_file=str(wav_path), model=model_name,
                    transcript=transcript, predicted_intent=pred, outcome=outcome,
                    confidence=conf, latency_ms=lat_ms))
    del model
    return results

def summarize(results, model, condition):
    sub = [r for r in results if r.model==model and r.condition==condition]
    n = len(sub)
    if not n: return EvalSummary(model=model,condition=condition,n_trials=0,n_correct=0,
        n_misrouted=0,n_silent=0,correct_rate=0,misrouting_rate=0,
        silent_failure_rate=0,median_latency_ms=0)
    nc=sum(1 for r in sub if r.outcome=="CORRECT")
    nm=sum(1 for r in sub if r.outcome=="MISROUTED")
    ns=sum(1 for r in sub if r.outcome=="SILENT_FAILURE")
    return EvalSummary(model=model,condition=condition,n_trials=n,
        n_correct=nc,n_misrouted=nm,n_silent=ns,
        correct_rate=nc/n,misrouting_rate=nm/n,silent_failure_rate=ns/n,
        median_latency_ms=statistics.median(r.latency_ms for r in sub),
        threshold_curve=compute_threshold_curve(sub))

def print_report(summaries):
    print(f"\n{'='*72}\nEVALUATION REPORT — Intent Misrouting Rate\n{'='*72}")
    print(f"\n{'Model':<12}{'Cond':<8}{'N':>4} | {'Correct':>8}{'Misrouted':>11}{'Silent':>8} | {'Lat(p50)':>10}")
    print("-"*72)
    for s in summaries:
        print(f"{s.model:<12}{s.condition:<8}{s.n_trials:>4} | "
              f"{s.correct_rate:>7.1%}  {s.misrouting_rate:>9.1%}  "
              f"{s.silent_failure_rate:>7.1%} | {s.median_latency_ms:>9.0f}ms")
    print("\nOutcomes: CORRECT=ok | MISROUTED=safety risk | SILENT_FAILURE=UX issue only")
    first = next((s for s in summaries if s.threshold_curve and s.condition=="clean"), None)
    if first:
        print(f"\nConfidence curve — {first.model}, clean:")
        print(f"  {'t':>5} | {'Correct':>8} | {'Misrouted':>10} | {'Silent':>8}")
        for t,v in sorted(first.threshold_curve.items(),key=lambda x:float(x[0])):
            marker = " <-- Pareto candidate" if v["misrouting"]<0.05 and v["silent"]<0.30 else ""
            print(f"  {float(t):>5.1f} | {v['correct']:>7.1%}  | {v['misrouting']:>9.1%}  | {v['silent']:>7.1%}{marker}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["small","large-v3"])
    ap.add_argument("--conditions", nargs="+", default=["clean","noisy"])
    ap.add_argument("--audio-dir", default="tests/eval/audio")
    ap.add_argument("--out-dir", default="docs/eval")
    ap.add_argument("--language", default="vi")
    args = ap.parse_args()
    audio_root = ROOT / args.audio_dir
    if not audio_root.exists():
        print(f"Audio dir not found: {audio_root}")
        print("Record with: python tests/eval/record_test_set.py")
        print("Structure:   tests/eval/audio/{clean,noisy}/{intent_name}/variant_N.wav")
        return 1
    all_results = []
    for m in args.models:
        all_results.extend(evaluate_model(m, audio_root, args.conditions, args.language))
    summaries = []
    for m in args.models:
        for c in args.conditions:
            s = summarize(all_results, m, c)
            if s.n_trials > 0: summaries.append(s)
    print_report(summaries)
    out = ROOT / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out/"stt_eval_results.json").write_text(
        json.dumps([asdict(r) for r in all_results], ensure_ascii=False, indent=2), encoding="utf-8")
    (out/"stt_eval_summaries.json").write_text(
        json.dumps([asdict(s) for s in summaries], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved to {out}/")
    return 0

if __name__ == "__main__": sys.exit(main())
