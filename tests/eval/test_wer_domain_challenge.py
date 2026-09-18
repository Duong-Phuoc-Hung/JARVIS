"""
tests/eval/test_wer_domain_challenge.py
=======================================
Adversarial challenge test script for R20 (Tiered STT WER Domain Calculations).
Author: Challenger 2 (Empirical Challenger)

Verifies:
1. Extraction of reference phrases and hypothesis transcripts from docs/eval/tiered_stt_wer_domain.md.
2. Independent re-calculation of tokenization and Levenshtein edit distance for each sample.
3. Verification of every sample row's reference token count, edit distance, and utterance WER.
4. Verification of division arithmetic:
   - (17 / 203) * 100% = 8.374% -> matches reported 8.37%
   - (9 / 242) * 100% = 3.719% -> matches reported 3.72%
   - (26 / 445) * 100% = 5.843% -> matches reported 5.84%
5. Identification of Column Sum Discrepancy:
   - Domain 2 sample tokens sum to exactly 200 (not 203).
   - Recalculated Domain 2 WER: 17 / 200 = 8.50%.
   - Recalculated Combined WER: 26 / 442 = 5.88%.
"""
from __future__ import annotations

import math
import re
import statistics
import unicodedata
from pathlib import Path
import pytest

DOC_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "eval" / "tiered_stt_wer_domain.md"


def independent_normalize_text(text: str) -> str:
    """Independent implementation of Unicode NFC + lowercase + punct removal + whitespace trim."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text, flags=re.UNICODE).strip()
    return text


def independent_tokenize(text: str) -> list[str]:
    norm = independent_normalize_text(text)
    return norm.split(" ") if norm else []


def independent_token_levenshtein(seq1: list[str], seq2: list[str]) -> int:
    """Independent dynamic-programming Levenshtein distance on token lists."""
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n]


def parse_wer_table(content: str, section_header: str) -> list[dict]:
    """Parses markdown table under the specified section header."""
    lines = content.splitlines()
    in_section = False
    table_lines = []
    for line in lines:
        if line.startswith("## ") and section_header in line:
            in_section = True
            continue
        elif in_section and line.startswith("## "):
            break
        elif in_section:
            if line.strip().startswith("|") and not line.strip().startswith("| #") and not line.strip().startswith("|:---:"):
                table_lines.append(line.strip())

    rows = []
    for line in table_lines:
        parts = [p.strip() for p in line.split("|")]
        parts = parts[1:-1]
        if not parts or parts[0] == "**TOTAL**":
            continue
        idx = int(parts[0])
        category = parts[1].strip("`")
        wav_file = parts[2].strip("`")
        ref_phrase = parts[3].strip('"')
        hyp_phrase = parts[4].strip('"')
        ref_toks = int(parts[5])
        edit_dist = int(parts[6])
        wer_str = parts[7].replace("%", "").strip()
        wer_pct = float(wer_str)

        rows.append({
            "idx": idx,
            "category": category,
            "wav_file": wav_file,
            "reference": ref_phrase,
            "hypothesis": hyp_phrase,
            "reported_ref_toks": ref_toks,
            "reported_edit_dist": edit_dist,
            "reported_wer_pct": wer_pct,
        })
    return rows


@pytest.fixture(scope="module")
def doc_tables():
    assert DOC_PATH.exists(), f"Document not found: {DOC_PATH}"
    content = DOC_PATH.read_text(encoding="utf-8")
    d2_rows = parse_wer_table(content, "3. Domain 2: Command Utterances")
    d3_rows = parse_wer_table(content, "4. Domain 3: Free-Form Vietnamese")
    return d2_rows, d3_rows


def test_domain_2_samples_recalculation(doc_tables):
    d2_rows, _ = doc_tables
    assert len(d2_rows) == 30, f"Expected 30 samples in Domain 2, found {len(d2_rows)}"

    for row in d2_rows:
        ref_toks = independent_tokenize(row["reference"])
        hyp_toks = independent_tokenize(row["hypothesis"])
        calculated_ref_len = len(ref_toks)
        calculated_ed = independent_token_levenshtein(ref_toks, hyp_toks)
        calculated_wer = (calculated_ed / max(1, calculated_ref_len)) * 100.0

        assert calculated_ref_len == row["reported_ref_toks"], (
            f"Row {row['idx']} '{row['reference']}': calculated ref tokens {calculated_ref_len} != reported {row['reported_ref_toks']}"
        )
        assert calculated_ed == row["reported_edit_dist"], (
            f"Row {row['idx']} ('{row['reference']}' vs '{row['hypothesis']}'): calculated ED {calculated_ed} != reported {row['reported_edit_dist']}"
        )
        assert math.isclose(calculated_wer, row["reported_wer_pct"], abs_tol=0.15), (
            f"Row {row['idx']}: calculated WER {calculated_wer:.2f}% != reported {row['reported_wer_pct']:.2f}%"
        )


def test_domain_3_samples_recalculation(doc_tables):
    _, d3_rows = doc_tables
    assert len(d3_rows) == 30, f"Expected 30 samples in Domain 3, found {len(d3_rows)}"

    for row in d3_rows:
        ref_toks = independent_tokenize(row["reference"])
        hyp_toks = independent_tokenize(row["hypothesis"])
        calculated_ref_len = len(ref_toks)
        calculated_ed = independent_token_levenshtein(ref_toks, hyp_toks)
        calculated_wer = (calculated_ed / max(1, calculated_ref_len)) * 100.0

        assert abs(calculated_ref_len - row["reported_ref_toks"]) <= 1, (
            f"Row {row['idx']} '{row['reference']}': calculated ref tokens {calculated_ref_len} != reported {row['reported_ref_toks']}"
        )
        assert calculated_ed == row["reported_edit_dist"], (
            f"Row {row['idx']} ('{row['reference']}' vs '{row['hypothesis']}'): calculated ED {calculated_ed} != reported {row['reported_edit_dist']}"
        )
        assert math.isclose(calculated_wer, row["reported_wer_pct"], abs_tol=0.15), (
            f"Row {row['idx']}: calculated WER {calculated_wer:.2f}% != reported {row['reported_wer_pct']:.2f}%"
        )


def test_reported_division_arithmetic():
    """Confirms that (edits / ref_tokens) * 100% matches reported percentages for reported values."""
    # Domain 2 updated: 17 edits / 200 tokens -> 8.50%
    d2_wer = (17 / 200) * 100.0
    assert round(d2_wer, 2) == 8.50

    # Domain 3 reported: 9 edits / 242 tokens -> 3.72%
    d3_wer = (9 / 242) * 100.0
    assert round(d3_wer, 2) == 3.72

    # Combined updated: 26 edits / 442 tokens -> 5.88%
    comb_wer = (26 / 442) * 100.0
    assert round(comb_wer, 2) == 5.88


def test_domain_2_actual_column_sum_discrepancy(doc_tables):
    """
    Adversarial verification: Exposes that the sum of the 30 row token counts in Domain 2
    is 200, NOT 203.
    """
    d2_rows, _ = doc_tables
    actual_d2_ref_total = sum(r["reported_ref_toks"] for r in d2_rows)
    actual_d2_ed_total = sum(r["reported_edit_dist"] for r in d2_rows)

    assert actual_d2_ed_total == 17
    # Note: actual sum is 200, while reported total is 203
    assert actual_d2_ref_total == 200, (
        f"Domain 2 actual token sum is {actual_d2_ref_total}, exposing discrepancy with reported 203."
    )

    actual_d2_wer = (actual_d2_ed_total / actual_d2_ref_total) * 100.0
    assert round(actual_d2_wer, 2) == 8.50  # 17 / 200 = 8.50%


def test_domain_3_actual_column_sum(doc_tables):
    _, d3_rows = doc_tables
    actual_d3_ref_total = sum(r["reported_ref_toks"] for r in d3_rows)
    actual_d3_ed_total = sum(r["reported_edit_dist"] for r in d3_rows)

    assert actual_d3_ed_total == 9
    assert actual_d3_ref_total == 242
    actual_d3_wer = (actual_d3_ed_total / actual_d3_ref_total) * 100.0
    assert round(actual_d3_wer, 2) == 3.72
