"""
tests/unit/test_h05_vietnamese_regression_contract.py
=======================================================
Strict, automated H-05 acceptance contract test. Fails if future edits
break any officially required property of the Vietnamese voice regression
corpus/evaluator. Validates actual data/content, not comments or filenames.

Official H-05 contract:
  - Vietnamese voice regression corpus >= 200 utterances.
  - Covers >= 10 core workflows.
  - Includes: Vietnamese with diacritics; Vietnamese without diacritics;
    colloquial/natural phrasing; English app names embedded in Vietnamese
    commands; clean and noisy acoustic conditions.
  - Evaluation is repeatable (deterministic ground-truth mapping).
  - Evaluator reports STT success, intent success, misroute, abstain.
  - Baseline evidence is persisted under docs/eval.

Assets under test:
  - tests/eval/independent_test_manifest.py (INDEPENDENT_MANIFEST) -- the
    210-utterance, 14-domain, WITH-diacritics acoustic corpus.
  - tests/eval/audio_independent/{clean,noisy}/ -- the 420 paired WAV files.
  - tests/eval/no_diacritic_regression.py (NO_DIACRITIC_MANIFEST) -- the
    companion WITHOUT-diacritics text/router regression layer added to
    close a real, confirmed gap: the acoustic manifest has zero no-diacritic
    coverage (audio ground truth is inherently spoken/accented Vietnamese,
    so no-diacritic coverage is deliberately a text/router concern, not an
    acoustic one -- see that module's docstring for the full rationale).
  - tests/eval/failure_decomposition.py (classify_outcome, EXPECTED_ACTIONS,
    _bucket_stats) -- the 4-way taxonomy and its official-terminology
    aliases.
  - docs/eval/stt_eval_independent_summary.md -- persisted baseline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.llm.router import strip_vietnamese_diacritics
from tests.eval.independent_test_manifest import INDEPENDENT_MANIFEST
from tests.eval.no_diacritic_regression import NO_DIACRITIC_MANIFEST, run_no_diacritic_regression
from tests.eval import failure_decomposition as fd

ROOT = Path(__file__).resolve().parent.parent.parent
AUDIO_ROOT = ROOT / "tests" / "eval" / "audio_independent"

MIN_TOTAL_UTTERANCES = 200
MIN_WORKFLOW_DOMAINS = 10

# Known English/Latin-script app or service names deliberately embedded in
# Vietnamese commands across the manifest (see open_app/search/music_play).
KNOWN_ENGLISH_APP_NAMES = [
    "Chrome", "Word", "Excel", "Spotify", "Discord", "Zalo", "Telegram",
    "Firefox", "Notepad", "Calculator", "Terminal", "Cursor", "Task Manager",
    "Paint", "Visual Studio Code", "Google", "YouTube", "Bluetooth", "Windows",
]

# Colloquial/natural Vietnamese particles and softeners that would not
# appear in a stiff, formal command-only corpus.
COLLOQUIAL_MARKERS = [
    "giùm", "giúp", "nhé", " đi ", "xíu", "nha", "hen", "ơi", "nhỉ", "đấy", "với", "nè",
]


def _all_manifest_phrases() -> list[str]:
    return [p for phrases in INDEPENDENT_MANIFEST.values() for p in phrases]


# ============================================================================
# Corpus size / domain coverage
# ============================================================================

def test_corpus_has_at_least_200_utterances():
    phrases = _all_manifest_phrases()
    assert len(phrases) >= MIN_TOTAL_UTTERANCES, (
        f"H-05 requires >= {MIN_TOTAL_UTTERANCES} utterances, found {len(phrases)}"
    )
    # No duplicate/empty phrases silently inflating the count.
    assert len(set(phrases)) == len(phrases), "Manifest contains duplicate phrases"
    assert all(p.strip() for p in phrases), "Manifest contains an empty/whitespace-only phrase"


def test_corpus_covers_at_least_10_workflow_domains():
    assert len(INDEPENDENT_MANIFEST) >= MIN_WORKFLOW_DOMAINS, (
        f"H-05 requires >= {MIN_WORKFLOW_DOMAINS} workflow domains, "
        f"found {len(INDEPENDENT_MANIFEST)}: {sorted(INDEPENDENT_MANIFEST.keys())}"
    )
    # Every domain must genuinely contribute utterances, not be an empty stub.
    for domain, phrases in INDEPENDENT_MANIFEST.items():
        assert len(phrases) > 0, f"Domain '{domain}' has zero phrases"


# ============================================================================
# Vietnamese WITH diacritics
# ============================================================================

def test_manifest_phrases_genuinely_carry_diacritics():
    """
    Assert actual content, not a claim: for the overwhelming majority of
    manifest phrases, stripping Vietnamese diacritics must actually change
    the string (i.e. real tone marks/diacritics are present), not just that
    the phrase LOOKS Vietnamese.
    """
    phrases = _all_manifest_phrases()
    with_diacritics = [p for p in phrases if strip_vietnamese_diacritics(p) != p]
    rate = len(with_diacritics) / len(phrases)
    assert rate >= 0.95, (
        f"Only {rate:.1%} of manifest phrases actually carry diacritics "
        f"(stripping changed the string) -- expected the corpus to be "
        f"overwhelmingly WITH-diacritics Vietnamese."
    )


# ============================================================================
# Vietnamese WITHOUT diacritics (the confirmed gap this audit closes)
# ============================================================================

def test_no_diacritic_companion_layer_exists_and_is_genuinely_unaccented():
    """
    The audio manifest has zero no-diacritic phrases (spoken audio cannot
    honestly be "without accents") -- so no-diacritic coverage must exist as
    a companion text/router regression layer, and every phrase in it must be
    genuinely diacritic-free (idempotent under strip_vietnamese_diacritics),
    not merely claimed to be.
    """
    assert len(NO_DIACRITIC_MANIFEST) >= MIN_WORKFLOW_DOMAINS, (
        f"No-diacritic layer must cover >= {MIN_WORKFLOW_DOMAINS} domains, "
        f"found {len(NO_DIACRITIC_MANIFEST)}"
    )
    all_no_diacritic_phrases = [p for phrases in NO_DIACRITIC_MANIFEST.values() for p in phrases]
    assert len(all_no_diacritic_phrases) >= 30, (
        f"No-diacritic layer must have a meaningful number of phrases, "
        f"found {len(all_no_diacritic_phrases)}"
    )

    not_actually_unaccented = [
        p for p in all_no_diacritic_phrases if strip_vietnamese_diacritics(p) != p
    ]
    assert not not_actually_unaccented, (
        f"These 'no-diacritic' phrases still contain diacritics: {not_actually_unaccented}"
    )


def test_no_diacritic_domains_align_with_acoustic_manifest_domains():
    """
    The no-diacritic layer's domain keys must be real subsets of the SAME
    14 workflow domains the acoustic manifest covers -- not an unrelated,
    untraceable taxonomy.
    """
    acoustic_domains = set(INDEPENDENT_MANIFEST.keys())
    no_diacritic_domains = set(NO_DIACRITIC_MANIFEST.keys())
    unknown = no_diacritic_domains - acoustic_domains
    assert not unknown, f"No-diacritic layer references unknown domains: {unknown}"


def test_no_diacritic_regression_routes_with_zero_misroutes_and_a_real_floor():
    """
    Actually run the no-diacritic phrases through the real Tier-1 router
    (not a mocked/fabricated result) and check genuine measured behavior:
    zero MISROUTED (fail-closed -- unmatched phrases must abstain, never
    route to a wrong action) and a non-trivial CORRECT floor. The floor is
    set below the currently-measured 72.1% (31/43) to avoid a brittle test
    that fails on minor future router tuning, while still catching a real
    regression (e.g. the no-diacritic rule table being accidentally gutted).
    """
    result = run_no_diacritic_regression()
    summary = result["summary"]

    assert summary["n_trials"] == sum(len(v) for v in NO_DIACRITIC_MANIFEST.values())
    assert summary["n_misrouted"] == 0, (
        f"No-diacritic phrases must never MISROUTE (wrong action) -- found "
        f"{summary['n_misrouted']}: "
        f"{[r for r in result['rows'] if r['outcome'] == 'MISROUTED']}"
    )
    assert summary["correct_rate"] >= 0.5, (
        f"No-diacritic CORRECT rate dropped to {summary['correct_rate']:.1%} "
        f"(floor is 50%, last measured 72.1%) -- investigate a real router regression."
    )
    # Every trial must land in exactly one of the 4 buckets.
    assert (
        summary["n_correct"] + summary["n_misrouted"]
        + summary["n_stt_empty"] + summary["n_router_abstain"]
    ) == summary["n_trials"]
    # Text input, never audio -- STT_EMPTY must be definitionally zero here.
    assert summary["n_stt_empty"] == 0


# ============================================================================
# Colloquial / natural phrasing
# ============================================================================

def test_manifest_includes_colloquial_phrasing():
    phrases = _all_manifest_phrases()
    hits = [p for p in phrases if any(marker in p for marker in COLLOQUIAL_MARKERS)]
    assert len(hits) >= 15, (
        f"Expected >= 15 colloquial-marker phrases, found {len(hits)}"
    )


# ============================================================================
# English app names embedded in Vietnamese commands
# ============================================================================

def test_manifest_includes_english_app_names_embedded_in_vietnamese():
    phrases = _all_manifest_phrases()
    hits = [p for p in phrases if any(name in p for name in KNOWN_ENGLISH_APP_NAMES)]
    assert len(hits) >= 10, (
        f"Expected >= 10 phrases with an embedded English app/service name, found {len(hits)}"
    )
    # Sanity: at least 5 distinct app names actually appear (not one name repeated).
    distinct_names_seen = {name for name in KNOWN_ENGLISH_APP_NAMES if any(name in p for p in phrases)}
    assert len(distinct_names_seen) >= 5, (
        f"Expected >= 5 distinct English app names represented, found {distinct_names_seen}"
    )


# ============================================================================
# Clean / noisy acoustic conditions, correctly paired
# ============================================================================

def test_clean_and_noisy_audio_paths_exist_and_are_paired_1to1():
    clean_dir = AUDIO_ROOT / "clean"
    noisy_dir = AUDIO_ROOT / "noisy"
    assert clean_dir.is_dir(), f"Missing clean audio directory: {clean_dir}"
    assert noisy_dir.is_dir(), f"Missing noisy audio directory: {noisy_dir}"

    for domain, phrases in INDEPENDENT_MANIFEST.items():
        clean_domain_dir = clean_dir / domain
        noisy_domain_dir = noisy_dir / domain
        assert clean_domain_dir.is_dir(), f"Missing clean/{domain}/"
        assert noisy_domain_dir.is_dir(), f"Missing noisy/{domain}/"

        clean_files = {p.name for p in clean_domain_dir.glob("*.wav")}
        noisy_files = {p.name for p in noisy_domain_dir.glob("*.wav")}

        assert len(clean_files) == len(phrases), (
            f"clean/{domain}/ has {len(clean_files)} WAV files, expected {len(phrases)}"
        )
        assert clean_files == noisy_files, (
            f"clean/{domain}/ and noisy/{domain}/ file sets differ: "
            f"clean-only={clean_files - noisy_files}, noisy-only={noisy_files - clean_files}"
        )


def test_total_audio_corpus_is_420_files():
    clean_count = sum(1 for _ in (AUDIO_ROOT / "clean").rglob("*.wav"))
    noisy_count = sum(1 for _ in (AUDIO_ROOT / "noisy").rglob("*.wav"))
    assert clean_count == 210, f"Expected 210 clean WAV files, found {clean_count}"
    assert noisy_count == 210, f"Expected 210 noisy WAV files, found {noisy_count}"


# ============================================================================
# Every audio file resolves to exactly one ground-truth phrase
# ============================================================================

def test_every_audio_file_resolves_to_exactly_one_ground_truth_phrase():
    for condition_dir in (AUDIO_ROOT / "clean", AUDIO_ROOT / "noisy"):
        for domain_dir in condition_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            domain = domain_dir.name
            assert domain in INDEPENDENT_MANIFEST, (
                f"{domain_dir} has no corresponding manifest domain"
            )
            for wav in domain_dir.glob("*.wav"):
                stem = wav.stem
                assert stem.startswith("variant_") and stem[len("variant_"):].isdigit(), (
                    f"Unexpected filename shape: {wav}"
                )
                idx = int(stem[len("variant_"):])
                assert 0 <= idx < len(INDEPENDENT_MANIFEST[domain]), (
                    f"{wav} has out-of-range index {idx} for domain '{domain}' "
                    f"(manifest has {len(INDEPENDENT_MANIFEST[domain])} phrases)"
                )
                # Resolves to a real, non-empty ground-truth phrase.
                phrase = INDEPENDENT_MANIFEST[domain][idx]
                assert isinstance(phrase, str) and phrase.strip()


# ============================================================================
# Evaluator taxonomy exposes the official 4 reporting concepts
# ============================================================================

def test_classify_outcome_only_produces_the_4_official_outcomes():
    valid_outcomes = {"CORRECT", "MISROUTED", "STT_EMPTY", "ROUTER_ABSTAIN"}

    assert fd.classify_outcome("", "NO_INTENT", "open_app") == "STT_EMPTY"
    assert fd.classify_outcome("mo chrome", "NO_INTENT", "open_app") == "ROUTER_ABSTAIN"
    assert fd.classify_outcome("mo chrome", "app_open", "open_app") == "CORRECT"
    assert fd.classify_outcome("mo chrome", "system_power", "open_app") == "MISROUTED"

    # Exhaustive: every (transcript-empty?, action) combination we can construct
    # must still land in the 4-set.
    for transcript in ("", "  ", "mo chrome"):
        for action in ("NO_INTENT", "app_open", "system_power", "unknown_intent"):
            outcome = fd.classify_outcome(transcript, action, "open_app")
            assert outcome in valid_outcomes


def test_bucket_stats_exposes_official_h05_terminology_aliases():
    """
    Ensure evaluator terminology maps clearly to the official H-05 metrics:
    STT success, intent success, misroute, abstain -- as explicit,
    machine-readable fields, additive on top of the historical field names
    (which must remain present and correctly valued, unchanged).
    """
    from collections import Counter

    counter = Counter({"CORRECT": 6, "MISROUTED": 1, "STT_EMPTY": 2, "ROUTER_ABSTAIN": 3})
    n = sum(counter.values())
    stats = fd._bucket_stats(counter, n)

    # Historical fields untouched.
    assert stats["n_correct"] == 6
    assert stats["n_misrouted"] == 1
    assert stats["n_stt_empty"] == 2
    assert stats["n_router_abstain"] == 3
    assert stats["correct_rate"] == pytest.approx(6 / 12)
    assert stats["misrouting_rate"] == pytest.approx(1 / 12)
    assert stats["stt_empty_rate"] == pytest.approx(2 / 12)
    assert stats["router_abstain_rate"] == pytest.approx(3 / 12)

    # Official H-05 terminology aliases, present and correctly derived.
    for key in (
        "stt_success_count", "stt_success_rate",
        "intent_success_count", "intent_success_rate",
        "misroute_count", "misroute_rate",
        "abstain_count", "abstain_rate",
    ):
        assert key in stats, f"Missing official H-05 metric alias field: {key}"

    # STT success = non-empty transcript rate = n_trials - STT_EMPTY.
    assert stats["stt_success_count"] == n - 2
    assert stats["stt_success_rate"] == pytest.approx((n - 2) / n)
    # intent success is an alias of CORRECT.
    assert stats["intent_success_count"] == stats["n_correct"]
    assert stats["intent_success_rate"] == pytest.approx(stats["correct_rate"])
    # misroute is an alias of MISROUTED.
    assert stats["misroute_count"] == stats["n_misrouted"]
    assert stats["misroute_rate"] == pytest.approx(stats["misrouting_rate"])
    # abstain is an alias of ROUTER_ABSTAIN, explicitly NOT STT_EMPTY.
    assert stats["abstain_count"] == stats["n_router_abstain"]
    assert stats["abstain_rate"] == pytest.approx(stats["router_abstain_rate"])
    assert stats["abstain_count"] != stats["n_stt_empty"]

    # Invariant: every trial lands in exactly one bucket.
    assert (
        stats["intent_success_count"] + stats["misroute_count"]
        + stats["n_stt_empty"] + stats["abstain_count"]
    ) == n
    # Invariant: STT success = intent_success + misroute + abstain (every
    # non-empty-transcript trial is exactly one of those three).
    assert stats["stt_success_count"] == (
        stats["intent_success_count"] + stats["misroute_count"] + stats["abstain_count"]
    )


def test_expected_actions_covers_every_manifest_domain():
    """The taxonomy's ground-truth action mapping must cover every domain
    the acoustic manifest actually uses -- no domain silently unclassifiable."""
    missing = set(INDEPENDENT_MANIFEST.keys()) - set(fd.EXPECTED_ACTIONS.keys())
    assert not missing, f"EXPECTED_ACTIONS is missing domains used by the manifest: {missing}"
    for domain, actions in fd.EXPECTED_ACTIONS.items():
        assert actions, f"EXPECTED_ACTIONS['{domain}'] is empty"


# ============================================================================
# Baseline evidence persisted under docs/eval
# ============================================================================

def test_baseline_summary_doc_exists_with_real_evidence_content():
    summary_path = ROOT / "docs" / "eval" / "stt_eval_independent_summary.md"
    assert summary_path.is_file(), f"Missing H-05 baseline summary: {summary_path}"
    text = summary_path.read_text(encoding="utf-8")

    # Validate actual content markers, not just file existence.
    for marker in ("CORRECT", "MISROUTED", "STT_EMPTY", "ROUTER_ABSTAIN", "420", "210"):
        assert marker in text, f"Baseline summary is missing expected evidence marker: {marker!r}"


def test_no_diacritic_layer_evidence_persisted_under_docs_eval():
    results_path = ROOT / "docs" / "eval" / "no_diacritic_regression_results.json"
    summary_path = ROOT / "docs" / "eval" / "no_diacritic_regression_summary.md"
    assert results_path.is_file(), f"Missing no-diacritic results JSON: {results_path}"
    assert summary_path.is_file(), f"Missing no-diacritic summary doc: {summary_path}"

    import json
    data = json.loads(results_path.read_text(encoding="utf-8"))
    assert "summary" in data and "rows" in data
    assert data["summary"]["n_trials"] == sum(len(v) for v in NO_DIACRITIC_MANIFEST.values())
