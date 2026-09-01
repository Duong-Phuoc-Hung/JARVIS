"""
tests/unit/test_stt_eval_failure_decomposition.py
==================================================
CPU-only, deterministic unit tests for the STT real-microphone eval baseline
correction (tests/eval/failure_decomposition.py, phrase_manifest.py,
text_normalize.py). No CUDA, no faster-whisper model, no microphone, no
network required anywhere in this file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.failure_decomposition import (
    EXPECTED_ACTIONS,
    classify_outcome,
    compute_text_similarity_stats,
    decompose_results,
    render_markdown_report,
)
from tests.eval.phrase_manifest import (
    PHRASE_MANIFEST,
    resolve_phrase,
    resolve_phrase_by_stem,
    resolve_phrase_for_wav,
    validate_audio_root,
)
from tests.eval.text_normalize import (
    normalize_text,
    token_edit_distance,
    token_similarity,
    tokenize,
    word_error_rate,
)

# ============================================================================
# 1. Outcome classification (Phase 1 taxonomy)
# ============================================================================

class TestClassifyOutcome:
    def test_empty_transcript_is_stt_empty(self):
        assert classify_outcome("", "NO_INTENT", "open_app") == "STT_EMPTY"

    def test_whitespace_only_transcript_is_stt_empty(self):
        assert classify_outcome("   ", "NO_INTENT", "open_app") == "STT_EMPTY"

    def test_nonempty_transcript_no_intent_is_router_abstain(self):
        assert classify_outcome("gi cho gi cho", "NO_INTENT", "note_take") == "ROUTER_ABSTAIN"

    def test_matching_action_is_correct(self):
        assert classify_outcome("mo chrome", "app_open", "open_app") == "CORRECT"

    def test_wrong_action_is_misrouted(self):
        assert classify_outcome("tat may tinh", "app_open", "system_shutdown") == "MISROUTED"

    def test_stt_empty_takes_priority_over_no_intent(self):
        # Even though predicted_action for empty input is always NO_INTENT in
        # practice, the classifier must not depend on that — empty transcript
        # alone is sufficient for STT_EMPTY.
        assert classify_outcome("", "app_open", "open_app") == "STT_EMPTY"

    def test_unknown_intent_gt_with_matching_action_absent_is_misrouted(self):
        # intent_gt not in expected_actions map -> empty expected set -> any
        # non-NO_INTENT action is a mismatch -> MISROUTED, never a crash.
        assert classify_outcome("abc", "some_action", "totally_unknown_intent") == "MISROUTED"

    def test_custom_expected_actions_override(self):
        custom = {"foo": {"bar_action"}}
        assert classify_outcome("hello", "bar_action", "foo", custom) == "CORRECT"
        assert classify_outcome("hello", "baz_action", "foo", custom) == "MISROUTED"

    def test_every_expected_actions_entry_is_a_nonempty_set(self):
        for intent, actions in EXPECTED_ACTIONS.items():
            assert isinstance(actions, set) and actions, intent


# ============================================================================
# 2. Historical decomposition (Phase 1/6) — offline, from committed evidence
# ============================================================================

class TestDecomposeResults:
    def _row(self, model="small", condition="clean", transcript="", predicted="NO_INTENT",
              intent_gt="open_app", legacy_outcome="SILENT_FAILURE", audio_file=None):
        return {
            "model": model, "condition": condition, "transcript": transcript,
            "predicted_intent": predicted, "intent_gt": intent_gt,
            "outcome": legacy_outcome, "audio_file": audio_file,
        }

    def test_decompose_counts_all_four_buckets(self):
        rows = [
            self._row(transcript="", predicted="NO_INTENT", legacy_outcome="SILENT_FAILURE"),
            self._row(transcript="gi do gi do", predicted="NO_INTENT", legacy_outcome="SILENT_FAILURE"),
            self._row(transcript="mo chrome", predicted="app_open", legacy_outcome="CORRECT"),
            self._row(transcript="tat may", predicted="app_open", intent_gt="system_shutdown",
                      legacy_outcome="MISROUTED"),
        ]
        d = decompose_results(rows)
        assert d["n_rows"] == 4
        total = d["total"]
        assert total["n_stt_empty"] == 1
        assert total["n_router_abstain"] == 1
        assert total["n_correct"] == 1
        assert total["n_misrouted"] == 1
        assert total["end_to_end_abstention_rate"] == pytest.approx(2 / 4)

    def test_legacy_silent_failure_crosswalk(self):
        rows = [
            self._row(transcript="", legacy_outcome="SILENT_FAILURE"),
            self._row(transcript="abc def", legacy_outcome="SILENT_FAILURE"),
            self._row(transcript="abc def", legacy_outcome="SILENT_FAILURE"),
        ]
        d = decompose_results(rows)
        legacy = d["legacy_silent_failure_decomposition"]
        assert legacy["legacy_silent_failure_total"] == 3
        assert legacy["of_which_stt_empty"] == 1
        assert legacy["of_which_router_abstain"] == 2

    def test_by_model_condition_breakdown_keys(self):
        rows = [
            self._row(model="small", condition="clean", transcript=""),
            self._row(model="large-v3", condition="noisy", transcript="", legacy_outcome="SILENT_FAILURE"),
        ]
        d = decompose_results(rows)
        assert "small/clean" in d["by_model_condition"]
        assert "large-v3/noisy" in d["by_model_condition"]
        assert d["by_model_condition"]["small/clean"]["n_trials"] == 1

    def test_n_distinct_audio_files_counts_unique_paths(self):
        rows = [
            self._row(audio_file="a.wav"),
            self._row(audio_file="a.wav"),
            self._row(audio_file="b.wav"),
        ]
        d = decompose_results(rows)
        assert d["n_distinct_audio_files"] == 2

    def test_empty_results_does_not_crash(self):
        d = decompose_results([])
        assert d["n_rows"] == 0
        assert d["total"]["n_trials"] == 0
        assert d["total"]["end_to_end_abstention_rate"] == 0.0

    def test_decomposition_matches_committed_historical_evidence(self):
        """
        Locks in the exact real-microphone decomposition against the committed
        docs/eval/stt_eval_results.json evidence, so a future accidental edit
        to that file (or to classify_outcome) is caught by CI. Numbers below
        were computed once, directly from the committed file, and are not
        re-derived here from the legacy 'outcome' field.
        """
        results_path = Path(__file__).resolve().parent.parent.parent / "docs" / "eval" / "stt_eval_results.json"
        if not results_path.exists():
            pytest.skip("docs/eval/stt_eval_results.json not present in this checkout")
        rows = json.loads(results_path.read_text(encoding="utf-8"))
        d = decompose_results(rows)
        assert d["n_rows"] == 180
        assert d["n_distinct_audio_files"] == 90
        total = d["total"]
        assert total["n_correct"] == 42
        assert total["n_misrouted"] == 4
        assert total["n_stt_empty"] == 3
        assert total["n_router_abstain"] == 131
        legacy = d["legacy_silent_failure_decomposition"]
        assert legacy["legacy_silent_failure_total"] == 134
        assert legacy["of_which_stt_empty"] == 3
        assert legacy["of_which_router_abstain"] == 131


class TestRenderMarkdownReport:
    def test_render_produces_nonempty_markdown_with_key_sections(self):
        rows = [{"model": "small", "condition": "clean", "transcript": "", "predicted_intent": "NO_INTENT",
                 "intent_gt": "open_app", "outcome": "SILENT_FAILURE", "audio_file": "x.wav"}]
        d = decompose_results(rows)
        md = render_markdown_report(d, phrase_manifest_problems=[])
        assert "STT_EMPTY" in md
        assert "ROUTER_ABSTAIN" in md
        assert "Phase 4" in md
        assert "docs/eval/stt_eval_results.json" in md

    def test_render_lists_phrase_manifest_problems_when_present(self):
        rows = []
        d = decompose_results(rows)
        md = render_markdown_report(d, phrase_manifest_problems=["clean/foo/variant_9.wav: bad"])
        assert "1 unresolved WAV" in md
        assert "variant_9.wav" in md

    def test_render_omits_text_quality_section_when_stats_not_provided(self):
        d = decompose_results([])
        md = render_markdown_report(d, phrase_manifest_problems=[])
        assert "AUXILIARY ONLY" not in md

    def test_render_includes_text_quality_section_when_stats_provided(self):
        rows = [{"model": "small", "condition": "clean", "transcript": "mo chrome",
                 "predicted_intent": "app_open", "intent_gt": "open_app", "phrase": "variant_0",
                 "outcome": "CORRECT", "audio_file": "tests/eval/audio/clean/open_app/variant_0.wav"}]
        d = decompose_results(rows)
        stats = compute_text_similarity_stats(rows)
        md = render_markdown_report(d, phrase_manifest_problems=[], text_similarity_stats=stats)
        assert "AUXILIARY ONLY" in md
        assert "does not measure router safety" in md
        assert "small | clean" in md

    def test_render_default_production_status_is_machine_neutral(self):
        """
        Locks §3's fix: render_markdown_report()'s default production_rerun_status
        must be a generic "not assessed" placeholder, never a specific machine's
        GPU/dependency findings baked in as a reusable default.
        """
        d = decompose_results([])
        md = render_markdown_report(d, phrase_manifest_problems=[])
        assert "not assessed" in md.lower() or "not supplied" in md.lower()
        assert "nvidia-smi" not in md
        assert "RTX 3050" not in md and "GTX 1650" not in md

    def test_render_accepts_explicit_production_status(self):
        d = decompose_results([])
        md = render_markdown_report(
            d, phrase_manifest_problems=[],
            production_rerun_status="Executed successfully on host X with model cache Y.",
        )
        assert "Executed successfully on host X" in md
        assert "not assessed" not in md.lower()


class TestComputeTextSimilarityStats:
    def _row(self, transcript, phrase="variant_0", audio_file="tests/eval/audio/clean/open_app/variant_0.wav",
              model="small", condition="clean", predicted="app_open", intent_gt="open_app"):
        return {
            "model": model, "condition": condition, "transcript": transcript,
            "predicted_intent": predicted, "intent_gt": intent_gt, "phrase": phrase,
            "audio_file": audio_file,
        }

    def test_identical_transcript_scores_one(self):
        # variant_0 of open_app resolves to "mở chrome" in the manifest.
        rows = [self._row("mở chrome")]
        stats = compute_text_similarity_stats(rows)
        assert stats["n_resolved"] == 1
        assert stats["n_unresolved"] == 0
        assert stats["overall"]["mean"] == pytest.approx(1.0)

    def test_empty_transcript_scores_zero(self):
        rows = [self._row("")]
        stats = compute_text_similarity_stats(rows)
        assert stats["overall"]["mean"] == pytest.approx(0.0)

    def test_resolution_uses_intent_gt_and_phrase_not_audio_file(self):
        """
        Path independence (per the AUDIT_METHODOLOGY.md finding that historical
        rows carry machine-specific absolute paths): a row whose audio_file is
        a bogus/unresolvable/foreign-OS-style path must still resolve correctly
        purely from its portable intent_gt + phrase fields.
        """
        rows = [self._row(
            "mở chrome",
            intent_gt="open_app", phrase="variant_4",
            audio_file="/this/path/does/not/exist/anywhere.wav",
        )]
        stats = compute_text_similarity_stats(rows)
        assert stats["n_resolved"] == 1
        assert stats["n_unresolved"] == 0
        # variant_4 of open_app is "khởi động chrome", not "mở chrome" -> low similarity,
        # proving the *correct* (variant_4) phrase was actually used for scoring.
        assert stats["overall"]["mean"] < 1.0

    def test_historical_windows_absolute_path_row_resolves_via_metadata_fields(self):
        """
        Reproduces the exact shape of a real historical row from
        docs/eval/stt_eval_results.json: a Windows absolute path from the
        original recording machine (a different machine than this test runs
        on, and — if this suite ever runs on non-Windows — a different OS's
        path syntax entirely). Resolution must succeed via intent_gt/phrase
        alone; the audio_file string is never parsed as a path.
        """
        row = {
            "condition": "clean", "intent_gt": "music_play", "phrase": "variant_0",
            "audio_file": r"D:\Software GitCode\JARVIS\tests\eval\audio\clean\music_play\variant_0.wav",
            "model": "small", "transcript": "phát nhạc",
            "predicted_intent": "spotify", "outcome": "CORRECT",
        }
        stats = compute_text_similarity_stats([row])
        assert stats["n_resolved"] == 1
        assert stats["n_unresolved"] == 0
        # music_play variant_0 is "mở nhạc" in the manifest; "phát nhạc" shares
        # one of two tokens -> a mid-range, non-zero, non-one similarity score
        # (proves real manifest text was actually looked up, not a placeholder).
        assert 0.0 < stats["overall"]["mean"] < 1.0

    def test_missing_intent_gt_counted_as_unresolved(self):
        row = self._row("mở chrome")
        row["intent_gt"] = None
        stats = compute_text_similarity_stats([row])
        assert stats["n_unresolved"] == 1
        assert stats["n_resolved"] == 0

    def test_missing_phrase_counted_as_unresolved(self):
        row = self._row("mở chrome")
        row["phrase"] = None
        stats = compute_text_similarity_stats([row])
        assert stats["n_unresolved"] == 1
        assert stats["n_resolved"] == 0

    def test_unknown_intent_gt_counted_as_unresolved(self):
        rows = [self._row("mở chrome", intent_gt="totally_unknown_intent")]
        stats = compute_text_similarity_stats(rows)
        assert stats["n_resolved"] == 0
        assert stats["n_unresolved"] == 1

    def test_malformed_phrase_stem_counted_as_unresolved(self):
        rows = [self._row("mở chrome", phrase="not_a_variant_stem")]
        stats = compute_text_similarity_stats(rows)
        assert stats["n_resolved"] == 0
        assert stats["n_unresolved"] == 1

    def test_by_model_condition_and_by_outcome_populated(self):
        rows = [
            self._row("mở chrome", model="small", condition="clean"),
            self._row("", model="large-v3", condition="noisy", predicted="NO_INTENT"),
        ]
        stats = compute_text_similarity_stats(rows)
        assert "small/clean" in stats["by_model_condition"]
        assert "large-v3/noisy" in stats["by_model_condition"]
        assert "CORRECT" in stats["by_outcome"]
        assert "STT_EMPTY" in stats["by_outcome"]

    def test_distribution_buckets_sum_to_resolved_count(self):
        rows = [self._row("mở chrome"), self._row(""), self._row("hoan toan khac")]
        stats = compute_text_similarity_stats(rows)
        assert sum(stats["distribution"].values()) == stats["n_resolved"]

    def test_empty_results_does_not_crash(self):
        stats = compute_text_similarity_stats([])
        assert stats["n_resolved"] == 0
        assert stats["overall"]["n"] == 0
        assert stats["overall"]["mean"] is None

    def test_matches_real_dataset_aggregate_direction(self):
        """
        Locks in the qualitative finding (not exact floats, which would make
        this test brittle to normalization tweaks): most transcripts in the
        real dataset are far from the spoken phrase, even though only 3/180
        rows are STT_EMPTY. Guards against silently regressing this into a
        metric that would let a future reader wrongly conclude "STT quality
        is fine" just because STT_EMPTY is rare.
        """
        results_path = Path(__file__).resolve().parent.parent.parent / "docs" / "eval" / "stt_eval_results.json"
        if not results_path.exists():
            pytest.skip("docs/eval/stt_eval_results.json not present in this checkout")
        rows = json.loads(results_path.read_text(encoding="utf-8"))
        stats = compute_text_similarity_stats(rows)
        assert stats["n_resolved"] == 180
        assert stats["n_unresolved"] == 0
        assert stats["overall"]["median"] == pytest.approx(0.0)
        assert stats["overall"]["mean"] < 0.3
        assert stats["by_outcome"]["ROUTER_ABSTAIN"]["mean"] < 0.3


# ============================================================================
# 3. Phrase manifest (Phase 2)
# ============================================================================

class TestPhraseManifest:
    def test_resolve_phrase_known_intent_and_index(self):
        assert resolve_phrase("open_app", 0) == "mở chrome"
        assert resolve_phrase("open_app", 4) == "khởi động chrome"

    def test_resolve_phrase_unknown_intent_returns_none(self):
        assert resolve_phrase("does_not_exist", 0) is None

    def test_resolve_phrase_out_of_range_index_returns_none(self):
        assert resolve_phrase("open_app", 99) is None
        assert resolve_phrase("open_app", -1) is None

    def test_resolve_phrase_for_wav_standard_path(self):
        p = Path("tests/eval/audio/clean/open_app/variant_2.wav")
        assert resolve_phrase_for_wav(p) == "mở notepad"

    def test_resolve_phrase_for_wav_bad_filename_returns_none(self):
        p = Path("tests/eval/audio/clean/open_app/not_a_variant.wav")
        assert resolve_phrase_for_wav(p) is None

    def test_resolve_phrase_for_wav_nonnumeric_suffix_returns_none(self):
        p = Path("tests/eval/audio/clean/open_app/variant_abc.wav")
        assert resolve_phrase_for_wav(p) is None

    def test_resolve_phrase_by_stem_matches_resolve_phrase_for_wav(self):
        # Same result as the path-based resolver, but with zero path parsing.
        assert resolve_phrase_by_stem("open_app", "variant_2") == "mở notepad"
        assert resolve_phrase_by_stem("open_app", "variant_2") == resolve_phrase_for_wav(
            Path("tests/eval/audio/clean/open_app/variant_2.wav")
        )

    def test_resolve_phrase_by_stem_unknown_intent_returns_none(self):
        assert resolve_phrase_by_stem("does_not_exist", "variant_0") is None

    def test_resolve_phrase_by_stem_malformed_stem_returns_none(self):
        assert resolve_phrase_by_stem("open_app", "not_a_variant") is None
        assert resolve_phrase_by_stem("open_app", "variant_abc") is None

    def test_resolve_phrase_by_stem_out_of_range_index_returns_none(self):
        assert resolve_phrase_by_stem("open_app", "variant_99") is None

    def test_resolve_phrase_by_stem_ignores_path_like_intent_string(self):
        # Even a garbage/path-like "intent" string is treated as a plain key
        # lookup, never parsed as a path — it simply won't match any manifest
        # entry, which is the correct (fail-closed) behavior.
        assert resolve_phrase_by_stem(r"D:\some\path\open_app", "variant_0") is None

    def test_every_manifest_intent_has_at_least_one_phrase(self):
        for intent, phrases in PHRASE_MANIFEST.items():
            assert isinstance(phrases, list) and len(phrases) > 0, intent

    def test_validate_audio_root_on_committed_wav_files(self):
        audio_root = Path(__file__).resolve().parent.parent.parent / "tests" / "eval" / "audio"
        if not audio_root.exists():
            pytest.skip("tests/eval/audio not present in this checkout")
        problems = validate_audio_root(audio_root)
        assert problems == []

    def test_validate_audio_root_flags_unresolvable_file(self, tmp_path):
        bad_dir = tmp_path / "clean" / "totally_unknown_intent"
        bad_dir.mkdir(parents=True)
        (bad_dir / "variant_0.wav").write_bytes(b"RIFF")
        problems = validate_audio_root(tmp_path)
        assert len(problems) == 1
        assert "totally_unknown_intent" in problems[0]

    def test_validate_audio_root_missing_condition_dir_is_silently_skipped(self, tmp_path):
        # Only 'clean' exists; 'noisy' does not — must not raise.
        (tmp_path / "clean").mkdir()
        problems = validate_audio_root(tmp_path)
        assert problems == []


# ============================================================================
# 4. Text normalization & auxiliary quality metric (Phase 3)
# ============================================================================

class TestNormalizeText:
    def test_lowercases(self):
        assert normalize_text("MỞ CHROME") == "mở chrome"

    def test_strips_punctuation(self):
        assert normalize_text("mở, chrome!!") == "mở chrome"

    def test_collapses_whitespace(self):
        assert normalize_text("mở    chrome\t\nnhé") == "mở chrome nhé"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_unicode_nfc_stability(self):
        # NFD-decomposed vs NFC-composed forms of the same visible text must
        # normalize identically.
        import unicodedata
        composed = "mở chrome"
        decomposed = unicodedata.normalize("NFD", composed)
        assert normalize_text(composed) == normalize_text(decomposed)

    def test_tokenize_splits_on_normalized_whitespace(self):
        assert tokenize("  Mở   Chrome  ") == ["mở", "chrome"]

    def test_tokenize_empty_returns_empty_list(self):
        assert tokenize("") == []
        assert tokenize("   ") == []


class TestWordErrorRate:
    def test_identical_text_zero_wer(self):
        assert word_error_rate("mở chrome", "mở chrome") == 0.0

    def test_case_and_punctuation_insensitive(self):
        assert word_error_rate("Mở Chrome!", "mở chrome") == 0.0

    def test_completely_different_text_full_wer(self):
        assert word_error_rate("mở chrome", "abc") == pytest.approx(2 / 2)

    def test_both_empty_is_zero_error(self):
        assert word_error_rate("", "") == 0.0

    def test_empty_reference_nonempty_hypothesis_is_one(self):
        assert word_error_rate("", "mo chrome") == 1.0

    def test_nonempty_reference_empty_hypothesis_is_full_error(self):
        assert word_error_rate("mo chrome", "") == 1.0

    def test_partial_overlap_between_zero_and_one(self):
        wer = word_error_rate("mo chrome ngay bay gio", "mo chrome")
        assert 0.0 < wer < 1.0

    def test_token_edit_distance_matches_expected_substitution_count(self):
        assert token_edit_distance(["a", "b", "c"], ["a", "x", "c"]) == 1
        assert token_edit_distance(["a", "b"], ["a", "b", "c"]) == 1
        assert token_edit_distance([], []) == 0
        assert token_edit_distance(["a"], []) == 1


class TestTokenSimilarity:
    def test_identical_is_one(self):
        assert token_similarity("mo chrome", "mo chrome") == 1.0

    def test_completely_different_is_zero(self):
        assert token_similarity("mo chrome", "abc def") == 0.0

    def test_clamped_to_unit_interval(self):
        sim = token_similarity("a", "a b c d e f")
        assert 0.0 <= sim <= 1.0

    def test_auxiliary_metric_does_not_imply_intent_outcome(self):
        # A transcript can be textually close to the expected phrase yet still
        # not match the router keyword (e.g. a determiner/synonym swap) —
        # this metric is descriptive only, never used to decide CORRECT vs
        # ROUTER_ABSTAIN. Sanity check: high similarity does not equal "CORRECT".
        sim = token_similarity("mo chrome", "mo chromee")
        assert sim > 0.0
        outcome = classify_outcome("mo chromee", "NO_INTENT", "open_app")
        assert outcome == "ROUTER_ABSTAIN"
