"""
tests/eval/no_diacritic_regression.py
======================================
H-05 companion regression layer: Vietnamese WITHOUT diacritics.

Audit finding (H-05 acceptance review): `tests/eval/independent_test_manifest.py`
(the 210-utterance, 14-domain corpus behind `docs/eval/stt_eval_independent_summary.md`'s
420-trial acoustic benchmark) uses full Vietnamese diacritics in every single
phrase. It has zero no-diacritic coverage. The H-05 contract explicitly
requires both "Vietnamese with diacritics" and "Vietnamese without
diacritics" to be represented.

This module deliberately does NOT try to make an audio waveform "without
accents" -- spoken Vietnamese audio, played back, always carries the true
tonal/diacritic pronunciation regardless of how the ground-truth text is
spelled. Audio-based STT ground truth is inherently the WITH-diacritics
case. No-diacritic coverage is a genuinely different concern: it tests
whether TEXT that a user might type without accents (or that STT/an
upstream normalizer might produce in unaccented form) still routes
correctly through the production Tier-1 rule engine
(jarvis.llm.router.LLMIntentRouter). That is a text/router regression
question, not an acoustic one -- so it lives here, as a separate,
explicitly-labeled layer, rather than pretending to extend the audio corpus.

NO_DIACRITIC_MANIFEST covers the SAME 14 workflow domains as
INDEPENDENT_MANIFEST (matching keys exactly, for direct traceability) with
naturally-typed unaccented Vietnamese phrasing (e.g. "tat may tinh", not a
strict character-by-character diacritic strip of an existing manifest
phrase -- this is meant to represent how a real user types without an
accent-enabled keyboard, or how some STT/normalization pipelines emit
output).

Ground-truth expected actions are the SAME `EXPECTED_ACTIONS` mapping
`tests/eval/failure_decomposition.py` already uses for the audio corpus --
single-sourced, not a second parallel taxonomy.

This module reports genuine measured results, not a curated "always passes"
list: some phrases legitimately abstain (ROUTER_ABSTAIN) under the real
production router, exactly as the audio corpus shows real abstention rates.
Nothing here is cherry-picked to inflate a pass rate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.eval.failure_decomposition import EXPECTED_ACTIONS, Outcome, classify_outcome

ROOT = Path(__file__).resolve().parent.parent.parent

# Keys MUST exactly match tests/eval/independent_test_manifest.py's
# INDEPENDENT_MANIFEST domain keys -- enforced by test_h05_vietnamese_regression_contract.py.
NO_DIACRITIC_MANIFEST: dict[str, list[str]] = {
    "open_app": [
        "mo chrome",
        "mo word",
        "khoi dong discord",
        "mo may tinh calculator",
    ],
    "system_shutdown": [
        "tat may tinh",
        "tat nguon may",
        "shutdown may tinh",
    ],
    "system_restart": [
        "khoi dong lai may",
        "restart lai may tinh",
        "reboot may tinh",
    ],
    "volume_control": [
        "tang am luong len",
        "giam am luong xuong",
        "tat tieng loa",
    ],
    "weather_query": [
        "thoi tiet hom nay the nao",
        "du bao thoi tiet ngay mai",
        "nhiet do hien tai la bao nhieu",
    ],
    "timer_set": [
        "dat hen gio muoi phut",
        "cai dong ho dem nguoc",
        "hen gio nau an",
    ],
    "reminder_set": [
        "nhac toi uong nuoc",
        "dat loi nhac hop chieu nay",
        "nho nhac toi goi dien",
    ],
    "screenshot": [
        "chup man hinh",
        "chup anh man hinh lai",
        "luu anh man hinh",
    ],
    "stop": [
        "dung lai",
        "huy thao tac nay",
        "ngung lam viec",
    ],
    "search": [
        "tim kiem tren google",
        "tra cuu thong tin",
        "tim video tren youtube",
    ],
    "music_play": [
        "mo spotify len",
        "phat nhac di",
        "bat bai hat",
    ],
    "screen_off": [
        "tat man hinh",
        "khoa man hinh lai",
        "man hinh nghi ngoi",
    ],
    "note_take": [
        "ghi chu lai",
        "tao ghi chep moi",
        "luu y tuong nay",
    ],
    "settings_open": [
        "mo cai dat",
        "vao phan cau hinh he thong",
        "mo bang dieu khien",
    ],
}


def _build_router():
    """Construct the real Tier-1 production router, no LLM/network calls.
    Mirrors tests/eval/stt_intent_eval.py::_build_router() exactly."""
    from jarvis.llm.router import LLMIntentRouter

    class _FakeDispatcher:
        def get_available_actions(self):
            return []

        def get_action(self, name):
            return None

    return LLMIntentRouter(llm_client=None, dispatcher=_FakeDispatcher(), fast_path_enabled=True)


def route_phrase(router: Any, text: str) -> str:
    """Route a single phrase through the real Tier-1 router. Returns the
    action_name, or 'NO_INTENT' if the router found no match (unknown_intent/
    generic_llm_response are both folded into NO_INTENT, matching
    stt_intent_eval.py::predict_intent()'s convention)."""
    res = router.parse_intent(text, force_llm=False)
    if res and res.action_name and res.action_name not in ("unknown_intent", "generic_llm_response"):
        return res.action_name
    return "NO_INTENT"


def run_no_diacritic_regression() -> dict:
    """
    Route every phrase in NO_DIACRITIC_MANIFEST through the real production
    router and classify each with the SAME 4-way taxonomy used for the
    audio corpus. Since these are literal text strings (not STT output),
    STT_EMPTY is definitionally always 0 here -- this layer measures router
    behavior on unaccented text, not transcription.
    """
    router = _build_router()
    rows: list[dict] = []
    outcome_counts: dict[Outcome, int] = {"CORRECT": 0, "MISROUTED": 0, "STT_EMPTY": 0, "ROUTER_ABSTAIN": 0}

    for domain, phrases in NO_DIACRITIC_MANIFEST.items():
        for idx, phrase in enumerate(phrases):
            action = route_phrase(router, phrase)
            outcome: Outcome = classify_outcome(phrase, action, domain, EXPECTED_ACTIONS)
            outcome_counts[outcome] += 1
            rows.append({
                "domain": domain,
                "variant": idx,
                "phrase": phrase,
                "predicted_action": action,
                "outcome": outcome,
            })

    n = len(rows)
    denom = n if n else 1
    summary = {
        "n_trials": n,
        "n_domains": len(NO_DIACRITIC_MANIFEST),
        "n_correct": outcome_counts["CORRECT"],
        "n_misrouted": outcome_counts["MISROUTED"],
        "n_stt_empty": outcome_counts["STT_EMPTY"],
        "n_router_abstain": outcome_counts["ROUTER_ABSTAIN"],
        "correct_rate": outcome_counts["CORRECT"] / denom,
        "misrouting_rate": outcome_counts["MISROUTED"] / denom,
        "router_abstain_rate": outcome_counts["ROUTER_ABSTAIN"] / denom,
        # Official H-05 terminology aliases -- see docs/eval/h05_metric_terminology.md.
        "intent_success_rate": outcome_counts["CORRECT"] / denom,
        "misroute_rate": outcome_counts["MISROUTED"] / denom,
        "abstain_rate": outcome_counts["ROUTER_ABSTAIN"] / denom,
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    result = run_no_diacritic_regression()
    summary = result["summary"]
    print(f"No-diacritic text/router regression: {summary['n_trials']} phrases across {summary['n_domains']} domains")
    print(f"  CORRECT:        {summary['n_correct']:3d} ({summary['correct_rate']:.1%})")
    print(f"  MISROUTED:      {summary['n_misrouted']:3d} ({summary['misrouting_rate']:.1%})")
    print(f"  STT_EMPTY:      {summary['n_stt_empty']:3d} (definitionally 0 -- text input, not audio)")
    print(f"  ROUTER_ABSTAIN: {summary['n_router_abstain']:3d} ({summary['router_abstain_rate']:.1%})")

    out_path = ROOT / "docs" / "eval" / "no_diacritic_regression_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
