"""
tests/test_adversarial_v481_m1_challenger2.py
=============================================
Adversarial Verification Suite for Milestone 1 (v4.8.1):
Empirical Challenge of Safe Preprocessing Diacritic Normalization,
predict_intent Contract, 10,000 Query Latency Benchmark, and 50KB ReDoS Stress Testing.
"""
from __future__ import annotations

import random
import re
import string
import time
import unicodedata
import pytest

from jarvis.llm.router import strip_vietnamese_diacritics, LLMIntentRouter
from tests.eval.stt_intent_eval import predict_intent


# ============================================================================
# 1. EXHAUSTIVE DIACRITIC STRIPPING VERIFICATION (144 VOWELS + đ/Đ)
# ============================================================================

def test_strip_vietnamese_diacritics_exhaustive():
    """Verify all 134+ Vietnamese vowel tone forms in NFC and NFD, plus d/D."""
    vowel_groups = [
        ("a", "aàáảãạăằắẳẵặâầấẩẫậ"),
        ("e", "eèéẻẽẹêềếểễệ"),
        ("i", "iìíỉĩị"),
        ("o", "oòóỏõọôồốổỗộơờớởỡợ"),
        ("u", "uùúủũụưừứửữự"),
        ("y", "yỳýỷỹỵ"),
    ]
    for base, chars in vowel_groups:
        for ch in chars:
            # NFC
            assert strip_vietnamese_diacritics(ch) == base, f"Failed NFC lowercase: {ch} -> {base}"
            assert strip_vietnamese_diacritics(ch.upper()) == base.upper(), f"Failed NFC uppercase: {ch.upper()} -> {base.upper()}"
            # NFD
            nfd_ch = unicodedata.normalize("NFD", ch)
            assert strip_vietnamese_diacritics(nfd_ch) == base, f"Failed NFD lowercase: {ch} -> {base}"
            assert strip_vietnamese_diacritics(nfd_ch.upper()) == base.upper(), f"Failed NFD uppercase: {ch.upper()} -> {base.upper()}"

    # đ / Đ
    assert strip_vietnamese_diacritics("đ") == "d"
    assert strip_vietnamese_diacritics("Đ") == "D"
    assert strip_vietnamese_diacritics(unicodedata.normalize("NFD", "đ")) == "d"
    assert strip_vietnamese_diacritics(unicodedata.normalize("NFD", "Đ")) == "D"

    # Preserves punctuation, whitespace, and numbers
    sample = "Chào bạn! 123 @#$ \t\n"
    expected = "Chao ban! 123 @#$ \t\n"
    assert strip_vietnamese_diacritics(sample) == expected

    # Pure ASCII early return
    ascii_sample = "Hello world! 12345"
    assert strip_vietnamese_diacritics(ascii_sample) is ascii_sample or strip_vietnamese_diacritics(ascii_sample) == ascii_sample


# ============================================================================
# 2. CONTRACT INTEGRITY: PREDICT_INTENT CONTRACT VERIFICATION
# ============================================================================

def test_predict_intent_empty_whitespace_and_noise():
    """Empty, whitespace, emoji-only, number-only must return 'NO_INTENT'."""
    empties = ["", "   ", "\t", "\n", " \t \r\n  "]
    for s in empties:
        res = predict_intent(s)
        assert res == "NO_INTENT", f"Expected 'NO_INTENT' for whitespace '{repr(s)}', got '{res}'"

    noise_cases = [
        "???", "!!!", ".,:;!?",
        "123456", "999 888 777", "3.14159",
        "🔥🔥🔥", "😂😂", "🚀🚀🚀", "👍👍👍",
    ]
    for s in noise_cases:
        res = predict_intent(s)
        assert res == "NO_INTENT", f"Expected 'NO_INTENT' for noise '{s}', got '{res}'"


def test_predict_intent_100_synthetic_and_adversarial_unknowns():
    """Verify 100+ synthetic and adversarial transcripts strictly return 'NO_INTENT'."""
    unrelated_vietnamese = [
        "con mèo trèo cây cau", "hỏi thăm chú chuột đi đâu vắng nhà",
        "bà ba béo bán bánh bò bên bờ biển", "bầu trời trong xanh và mây trắng lượn lờ",
        "anh ơi đi đâu thế qua cầu rung lắc lẻo", "con gà cục tác lá chanh",
        "bác đưa thư đến gõ cửa nhà em", "mùa xuân hoa nở rực rỡ bên hiên nhà",
        "chiếc thuyền ngoài xa lặng lẽ trôi", "hôm nay tôi cảm thấy rất vui vẻ",
        "quê hương là chùm khế ngọt", "cho con trèo hái mỗi ngày",
        "đường về quê ngoại quanh co uốn khúc", "tiếng chim hót líu lo đầu cành",
        "ngọn gió mùa thu lay bay nhè nhẹ", "bầu trời xanh ngắt không một bóng mây",
        "học hành chăm chỉ tương lai sáng lạn", "ly trà sữa thơm phức mùi hoa nhài",
        "bánh mì kẹp thịt pate ngon tuyệt", "chúc một ngày mới tràn đầy năng lượng",
    ]

    foreign_languages = [
        "hello how are you today", "bonjour comment ca va",
        "guten morgen wie geht es ihnen", "konnichiwa genki desu ka",
        "random english sentence without matched action keywords",
        "lorem ipsum dolor sit amet consectetur adipiscing elit",
        "duis aute irure dolor in reprehenderit in voluptate velit",
        "the quick brown fox jumps over the lazy dog",
        "sphynx of black quartz judge my vow",
        "pack my box with five dozen liquor jugs",
    ]

    gibberish = [
        "asdfghjklqwerty", "zxcvbnmasdfgh", "qwertyuiopasdfg",
        "zzzzzzzzzzzzzzz", "blablablablabla", "xyz123abc456",
        "foo bar baz qux quux", "corge grault garply waldo",
        "fred plugh xyzzy thud", "nananananananana batman",
    ]

    adversarial_templates = [
        "tôi muốn kể cho bạn nghe câu chuyện về {}",
        "hôm qua tôi thấy một con {} rất to",
        "đừng bao giờ nghĩ rằng {} là sự thật",
        "hãy giải thích ý nghĩa của từ {}",
        "tại sao chúng ta lại cần có {}",
    ]

    synthetic_pool = []
    for templ in adversarial_templates:
        for word in [
            "chiếc lá", "đám mây", "dòng sông", "hòn đá", "cơn gió",
            "bài thơ", "ngôi sao", "giọt sương", "bức tranh", "khung cửa",
            "con đường", "bến đò", "nắng sớm", "cánh đồng", "tiếng ve",
        ]:
            synthetic_pool.append(templ.format(word))

    all_unknowns = unrelated_vietnamese + foreign_languages + gibberish + synthetic_pool
    assert len(all_unknowns) >= 100, f"Expected >= 100 unknown cases, got {len(all_unknowns)}"

    for utterance in all_unknowns:
        res = predict_intent(utterance)
        assert res == "NO_INTENT", (
            f"Adversarial violation! Query: '{utterance}' resulted in '{res}' (must be 'NO_INTENT')"
        )
        assert res != "unknown_intent"
        assert res != "generic_llm_response"


# ============================================================================
# 3. PRODUCTION ROUTING ACCURACY & HOMOPHONE ISOLATION
# ============================================================================

def test_predict_intent_production_rules_and_diacritic_folding():
    """Verify production rules route accurately with both accented and unaccented multi-word phrases."""
    cases = [
        # Requirement R1 acceptance criteria:
        ("Điều chỉnh âm lượng", "system_volume"),
        ("dieu chinh am luong", "system_volume"),
        ("ĐIỀU CHỈNH ÂM LƯỢNG", "system_volume"),
        ("ĐiỀu ChỈnH Âm LưỢnG", "system_volume"),
        ("Tìm kiếm Google.", "web_open"),
        ("tim kiem google", "web_open"),
        ("Trời hôm nay thế nào?", "shell_exec"),
        ("troi hom nay the nao", "shell_exec"),
        # NFD decomposed versions
        (unicodedata.normalize("NFD", "Điều chỉnh âm lượng"), "system_volume"),
        (unicodedata.normalize("NFD", "Tìm kiếm Google."), "web_open"),
        (unicodedata.normalize("NFD", "Trời hôm nay thế nào?"), "shell_exec"),
        # English fallback keywords
        ("stop", "system_power"),
        ("shutdown", "system_power"),
        ("reboot", "system_power"),
        ("restart", "system_power"),
        ("screenshot", "screen_capture"),
        ("mute", "system_volume"),
        ("play music", "spotify"),
        ("open settings", "app_open"),
    ]

    for utterance, expected_intent in cases:
        res = predict_intent(utterance)
        assert res == expected_intent, (
            f"Routing mismatch! Input: '{utterance}' -> Expected '{expected_intent}', got '{res}'"
        )


def test_predict_intent_single_word_homophone_protection():
    """Verify single-word rules NEVER falsely collide into substring compound words."""
    homophone_isolation_cases = [
        # 'ứng dụng' must NOT trigger 'system_power' via single-word rule 'dừng'
        ("mở ứng dụng chrome", "app_open"),
        ("cài đặt ứng dụng mới", "app_open"),
        ("công dụng của máy tính", "NO_INTENT"),
        # 'nhắc nhở' must NOT trigger 'spotify' via single-word rule 'nhạc'
        ("nhắc nhở lúc 8 giờ", "reminder"),
        ("lời nhắc nhở hàng ngày", "reminder"),
        # 'hướng dẫn' / 'hấp dẫn' must NOT trigger 'skill_clipboard' via single-word rule 'dán'
        ("hướng dẫn sử dụng", "NO_INTENT"),
        ("hấp dẫn quá đi mất", "NO_INTENT"),
        # 'dừng lại' is a multi-word rule for system_power
        ("dừng lại", "system_power"),
        # Exact single-word matches with diacritics preserved
        ("nhạc", "spotify"),
        ("dừng", "system_power"),
        ("dán", "skill_clipboard"),
        ("tắt", "system_power"),
    ]

    for utterance, expected_intent in homophone_isolation_cases:
        res = predict_intent(utterance)
        if expected_intent == "NO_INTENT":
            assert res not in ("skill_clipboard", "system_power", "spotify"), (
                f"Homophone collision! '{utterance}' falsely triggered {res}"
            )
            assert res == "NO_INTENT"
        else:
            assert res == expected_intent, (
                f"Homophone test mismatch! Input: '{utterance}' -> Expected '{expected_intent}', got '{res}'"
            )


# ============================================================================
# 4. LATENCY BENCHMARK: 10,000 QUERIES (< 1.0 MS/UTTERANCE)
# ============================================================================

def test_latency_benchmark_10000_queries():
    """Benchmark latency across 10,000 queries with mixed Vietnamese diacritics. Mean latency must be < 1.0 ms."""
    pool = [
        "Điều chỉnh âm lượng", "dieu chinh am luong",
        "Tìm kiếm Google.", "tim kiem google",
        "Trời hôm nay thế nào?", "troi hom nay the nao",
        "mở ứng dụng chrome", "mo ung dung chrome",
        "nhắc nhở lúc 8 giờ", "nhac nho luc 8 gio",
        "dừng lại", "dung lai", "tắt máy", "tat may",
        "con mèo trèo cây cau", "thời tiết hôm nay thế nào",
        "chụp màn hình", "screenshot", "mute", "shutdown",
        "hướng dẫn sử dụng chi tiết", "chào jarvis bạn khỏe không",
    ]

    # Pre-generate 10,000 queries
    rng = random.Random(42)
    queries = [rng.choice(pool) for _ in range(10000)]

    # Warmup
    for q in pool:
        _ = predict_intent(q)

    # Benchmark run
    t0 = time.perf_counter()
    for q in queries:
        _ = predict_intent(q)
    total_time_s = time.perf_counter() - t0

    avg_latency_ms = (total_time_s / len(queries)) * 1000.0
    print(f"\n[BENCHMARK] 10,000 queries completed in {total_time_s:.4f}s. Avg latency: {avg_latency_ms:.4f} ms/query.")

    assert avg_latency_ms < 1.0, f"Latency SLA violated! Avg latency {avg_latency_ms:.4f} ms >= 1.0 ms"


# ============================================================================
# 5. REDOS AND 50KB MASSIVE PAYLOAD STRESS HARNESS (< 20.0 MS)
# ============================================================================

def test_redos_fuzzing_50kb_inputs():
    """Verify 50KB adversarial and fuzzing inputs complete safely in < 20.0 ms."""
    payloads = [
        # Payload 1: 50KB repeating Vietnamese multi-word phrases
        ("50KB Vietnamese Diacritics", ("Điều chỉnh âm lượng máy tính của tôi hôm nay " * 1150)[:50000]),
        # Payload 2: 50KB catastrophic regex backtracking trigger
        ("50KB Backtracking Pattern (a* b*)", ("a" * 25000 + "b" * 25000)),
        # Payload 3: 50KB unicode combining marks
        ("50KB Combining Diacritics", (("\u0300\u0301\u0302\u0303\u0309\u0323" * 9000) + " test")[:50000]),
        # Payload 4: 50KB random noise and special characters
        ("50KB Noise & Whitespace", "x" * 50000),
        # Payload 5: 50KB with target match buried at end
        ("50KB Prefix + Buried Match", ("padding text with no intent " * 1800) + "dieu chinh am luong"),
    ]

    for label, payload in payloads:
        assert len(payload) >= 50000, f"Payload {label} size too small: {len(payload)} bytes"
        # Warmup
        _ = predict_intent(payload)
        
        # Measure 3 trials to avoid OS scheduling / GC spikes
        trials = []
        for _ in range(3):
            t0 = time.perf_counter()
            res = predict_intent(payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            trials.append(elapsed_ms)
        
        avg_ms = sum(trials) / len(trials)
        min_ms = min(trials)
        print(f"[REDOS FUZZ] {label:<32} -> avg: {avg_ms:>6.2f} ms (min: {min_ms:>6.2f} ms, res: '{res}')")

        assert min_ms < 20.0, f"ReDoS SLA violated for {label}! Min elapsed: {min_ms:.2f} ms >= 20.0 ms"
        assert avg_ms < 20.0, f"ReDoS SLA violated for {label}! Avg elapsed: {avg_ms:.2f} ms >= 20.0 ms"
        assert res in ("NO_INTENT", "system_volume")
