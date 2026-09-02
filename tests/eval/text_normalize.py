"""
tests/eval/text_normalize.py
==============================
Deterministic text normalization + auxiliary token-level quality metric for
STT eval transcripts. No new dependency — stdlib only (re, unicodedata).

IMPORTANT (per AUDIT_METHODOLOGY.md — do not attribute causes without a
component breakdown): this metric is AUXILIARY. It describes how close a raw
transcript is to the phrase that was actually spoken (from phrase_manifest),
token-for-token. It does NOT measure router safety or end-to-end behavior —
a transcript can score low here and still route correctly (extra filler
words), or score high and still fail to route (a homophone substitution that
changes meaning but not token count). The authoritative end-to-end outcome
remains the CORRECT / MISROUTED / STT_EMPTY / ROUTER_ABSTAIN classification in
failure_decomposition.py.
"""
from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+", flags=re.UNICODE)


def normalize_text(text: str) -> str:
    """
    Unicode-safe normalization suitable for mixed Vietnamese/English commands:
      - Unicode NFC normalization (stable composed accented-character form)
      - lowercase
      - strip punctuation (Unicode-aware; keeps letters/digits/underscore/whitespace)
      - collapse and trim whitespace
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.lower()
    normalized = _PUNCT_RE.sub(" ", normalized)
    normalized = _WS_RE.sub(" ", normalized).strip()
    return normalized


def tokenize(text: str) -> list[str]:
    """Normalize then split on whitespace into tokens."""
    normalized = normalize_text(text)
    if not normalized:
        return []
    return normalized.split(" ")


def token_edit_distance(reference_tokens: list[str], hypothesis_tokens: list[str]) -> int:
    """
    Classic Levenshtein edit distance over token sequences (insert/delete/substitute,
    unit cost each). Deterministic dynamic-programming implementation.
    """
    n, m = len(reference_tokens), len(hypothesis_tokens)
    if n == 0:
        return m
    if m == 0:
        return n

    prev_row = list(range(m + 1))
    curr_row = [0] * (m + 1)
    for i in range(1, n + 1):
        curr_row[0] = i
        ref_tok = reference_tokens[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ref_tok == hypothesis_tokens[j - 1] else 1
            curr_row[j] = min(
                prev_row[j] + 1,       # deletion
                curr_row[j - 1] + 1,   # insertion
                prev_row[j - 1] + cost,  # substitution / match
            )
        prev_row, curr_row = curr_row, prev_row
    return prev_row[m]


def word_error_rate(reference: str, hypothesis: str) -> float:
    """
    Token-level Word Error Rate: edit_distance / max(1, len(reference_tokens)).
    reference="" and hypothesis="" -> 0.0 (nothing to say, nothing said, no error).
    reference="" and hypothesis!="" -> 1.0 (pure insertion error, normalized to 1.0
    since there is no reference length to divide by).
    """
    ref_tokens = tokenize(reference)
    hyp_tokens = tokenize(hypothesis)
    if not ref_tokens and not hyp_tokens:
        return 0.0
    if not ref_tokens:
        return 1.0
    distance = token_edit_distance(ref_tokens, hyp_tokens)
    return distance / len(ref_tokens)


def token_similarity(reference: str, hypothesis: str) -> float:
    """
    Auxiliary quality score in [0.0, 1.0]: 1.0 - WER, clamped.
    1.0 = identical token sequence after normalization. 0.0 = fully divergent.
    AUXILIARY ONLY — see module docstring.
    """
    wer = word_error_rate(reference, hypothesis)
    return max(0.0, min(1.0, 1.0 - wer))
