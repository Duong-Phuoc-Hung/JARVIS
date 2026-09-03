"""
tests/test_adversarial_m1_diacritic_homophones.py
=================================================
Empirical Adversarial Test Suite for Milestone 1 (Safe Preprocessing Diacritic Normalization v4.8.1).
Conducted by Challenger M1-1.

Challenge Dimensions:
1. Full Vietnamese diacritic stripping across all 134+ vowel forms in NFC & NFD + đ/Đ.
2. Homophone collision prevention:
   - 'nhạc' (spotify) vs 'nhắc' (reminder)
   - 'dừng' (system_power lock) vs 'dụng' (app_open / generic)
   - 'dán' (skill_clipboard paste) vs 'dẫn' (guide / unrouted)
   - 'báo' (news/briefing/alarm) vs 'bảo' (protect/unrouted)
   - 'tắt' (system_power shutdown) vs 'tắc' (traffic/unrouted)
3. Word boundary isolation: Subword non-matching for single-word rules.
4. Single-word diacritic preservation vs unaccented inputs.
5. Polysyllabic phrase diacritic folding (mixed case, punctuation, partial diacritics, NFD).
6. Single-word NFD behavior documentation and verification.
7. predict_intent contract synchronization in tests/eval/stt_intent_eval.py.
8. Stress & ReDoS latency SLA (< 20ms on long and 50KB strings).
"""
from __future__ import annotations

import time
import unicodedata
import pytest

from jarvis.llm.router import (
    IntentResult,
    LLMIntentRouter,
    strip_vietnamese_diacritics,
)
from tests.eval.stt_intent_eval import predict_intent


@pytest.fixture(scope="module")
def router() -> LLMIntentRouter:
    """Provides an offline LLMIntentRouter with fast_path enabled and no LLM client."""
    return LLMIntentRouter(llm_client=None, fast_path_enabled=True)


# ============================================================================
# 1. VIETNAMESE DIACRITIC STRIPPING EMPIRICAL COVERAGE
# ============================================================================

class TestDiacriticStrippingCoverage:
    """Exhaustively tests strip_vietnamese_diacritics on all Vietnamese phonemes."""

    VOWEL_FAMILIES = [
        ("a", "aàáảãạăằắẳẵặâầấẩẫậ"),
        ("e", "eèéẻẽẹêềếểễệ"),
        ("i", "iìíỉĩị"),
        ("o", "oòóỏõọôồốổỗộơờớởỡợ"),
        ("u", "uùúủũụưừứửữự"),
        ("y", "yỳýỷỹỵ"),
    ]

    def test_all_precomposed_vowels_lowercase(self):
        """All lowercase vowels in NFC form must reduce to ASCII base character."""
        for base, family in self.VOWEL_FAMILIES:
            for ch in family:
                assert strip_vietnamese_diacritics(ch) == base, (
                    f"Failed on NFC char '{ch}' (U+{ord(ch):04X}) -> expected '{base}'"
                )

    def test_all_precomposed_vowels_uppercase(self):
        """All uppercase vowels in NFC form must reduce to uppercase ASCII base."""
        for base, family in self.VOWEL_FAMILIES:
            for ch in family:
                ch_up = ch.upper()
                expected = base.upper()
                assert strip_vietnamese_diacritics(ch_up) == expected, (
                    f"Failed on uppercase NFC char '{ch_up}' (U+{ord(ch_up):04X}) -> expected '{expected}'"
                )

    def test_all_decomposed_vowels_nfd(self):
        """All vowels in decomposed NFD form must reduce to ASCII base character."""
        for base, family in self.VOWEL_FAMILIES:
            for ch in family:
                ch_nfd = unicodedata.normalize("NFD", ch)
                assert strip_vietnamese_diacritics(ch_nfd) == base, (
                    f"Failed on NFD char '{ch}' -> expected '{base}'"
                )
                ch_nfd_up = unicodedata.normalize("NFD", ch.upper())
                assert strip_vietnamese_diacritics(ch_nfd_up) == base.upper(), (
                    f"Failed on uppercase NFD char '{ch.upper()}' -> expected '{base.upper()}'"
                )

    def test_d_with_stroke_normalization(self):
        """'đ' and 'Đ' must normalize to 'd' and 'D' in both NFC and NFD."""
        assert strip_vietnamese_diacritics("đ") == "d"
        assert strip_vietnamese_diacritics("Đ") == "D"
        assert strip_vietnamese_diacritics(unicodedata.normalize("NFD", "đ")) == "d"
        assert strip_vietnamese_diacritics(unicodedata.normalize("NFD", "Đ")) == "D"

    def test_complex_multisyllabic_words(self):
        """Real-world complex Vietnamese words with dipthongs and tone marks."""
        samples = [
            ("nghiêng ngả", "nghieng nga"),
            ("khuấy động", "khuay dong"),
            ("thuyền buồm", "thuyen buom"),
            ("nguyễn huệ", "nguyen hue"),
            ("quốc lộ", "quoc lo"),
            ("đường sá", "duong sa"),
            ("hoàng hôn", "hoang hon"),
            ("luyện tập", "luyen tap"),
            ("phượng hoàng", "phuong hoang"),
            ("thuở nhỏ", "thuo nho"),
        ]
        for vn, expected in samples:
            assert strip_vietnamese_diacritics(vn) == expected
            assert strip_vietnamese_diacritics(unicodedata.normalize("NFD", vn)) == expected
            assert strip_vietnamese_diacritics(vn.upper()) == expected.upper()

    def test_ascii_and_symbol_invariance(self):
        """ASCII letters, digits, punctuation, and whitespace must remain unchanged."""
        text = "JARVIS Pro v4.8.1: CPU 50%, RAM 8GB! URL: https://jarvis.ai?q=test_123"
        assert strip_vietnamese_diacritics(text) == text

    def test_edge_cases_empty_whitespace(self):
        """Empty, whitespace, and null string edge cases."""
        assert strip_vietnamese_diacritics("") == ""
        assert strip_vietnamese_diacritics("   ") == "   "
        assert strip_vietnamese_diacritics("\t\n\r") == "\t\n\r"


# ============================================================================
# 2. HOMOPHONE COLLISION PREVENTION
# ============================================================================

class TestHomophoneCollisionPrevention:
    """Stress-tests the router against subtle Vietnamese homophone and minimal-pair collisions."""

    def test_homophone_nhac_vs_nhac(self, router: LLMIntentRouter):
        """'nhạc' (music -> spotify) must NEVER collide with 'nhắc' (remind -> reminder)."""
        # Utterances with 'nhạc' -> MUST route to spotify
        nhac_cases = [
            "nhạc",
            "bật nhạc",
            "mở nhạc",
            "phát nhạc",
            "nghe nhạc",
            "dừng nhạc",
        ]
        for u in nhac_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name == "spotify", f"'{u}' should route to spotify, got {res.action_name}"

        # Utterances with 'nhắc' -> MUST NOT route to spotify
        nhac_remind_cases = [
            "nhắc tôi uống nước",
            "nhắc nhở lúc 8 giờ",
            "nhắc tôi họp sáng mai",
            "tạo lời nhắc mới",
            "nhắc việc",
        ]
        for u in nhac_remind_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name != "spotify", f"COLLISION: '{u}' routed to spotify!"
            assert res.action_name in ("reminder", "unknown_intent")

    def test_homophone_dung_vs_dung(self, router: LLMIntentRouter):
        """'dừng' (stop/lock -> system_power) must NEVER collide with 'dụng' (app / use)."""
        # Utterances with 'dừng' -> system_power
        dung_stop_cases = [
            "dừng",
            "dừng lại",
        ]
        for u in dung_stop_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name == "system_power", f"'{u}' should route to system_power, got {res.action_name}"

        # Utterances with 'dụng' -> MUST NOT route to system_power via 'dừng'
        dung_app_cases = [
            ("mở ứng dụng chrome", "app_open"),
            ("mở ứng dụng notepad", "app_open"),
            ("ứng dụng máy tính", None),
            ("hướng dẫn sử dụng", None),
            ("tác dụng phụ", None),
            ("sử dụng tài nguyên", None),
            ("nội dung clipboard", None),
        ]
        for u, expected in dung_app_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name != "system_power", f"COLLISION: '{u}' misrouted to system_power via 'dừng'!"
            if expected:
                assert res.action_name == expected

    def test_homophone_dan_vs_dan(self, router: LLMIntentRouter):
        """'dán' (paste -> skill_clipboard) must NEVER collide with 'dẫn' (guide/lead)."""
        # Utterances with 'dán' -> skill_clipboard
        dan_paste_cases = [
            "dán",
            "dán clipboard",
            "dán vào đây",
        ]
        for u in dan_paste_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name == "skill_clipboard", f"'{u}' should route to skill_clipboard, got {res.action_name}"

        # Utterances with 'dẫn' -> MUST NOT route to skill_clipboard via 'dán'
        dan_guide_cases = [
            "hướng dẫn sử dụng",
            "dẫn đường đến sân bay",
            "chỉ dẫn chi tiết",
            "bài hát này hấp dẫn quá",
            "dẫn xuất hàm số",
            "lãnh đạo dẫn dắt đội ngũ",
        ]
        for u in dan_guide_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name != "skill_clipboard", f"COLLISION: '{u}' misrouted to skill_clipboard via 'dán'!"

    def test_homophone_bao_vs_bao(self, router: LLMIntentRouter):
        """'báo' (alarm/news/briefing) must NEVER collide with 'bảo' (protect/assure/tell)."""
        # Utterances with 'báo'
        bao_alarm_cases = [
            ("đặt báo thức lúc 7 giờ", "reminder"),
            ("đọc báo", "news_headlines"),
            ("báo cáo buổi sáng", "morning_briefing"),
        ]
        for u, expected in bao_alarm_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name == expected, f"'{u}' should route to {expected}, got {res.action_name}"

        # Utterances with 'bảo' -> MUST NOT trigger news/briefing/reminder
        bao_protect_cases = [
            "bảo vệ màn hình",
            "bảo hiểm y tế",
            "bảo mật thông tin",
            "bảo đảm chất lượng",
            "ai bảo thế",
            "bảo tôi làm gì",
        ]
        for u in bao_protect_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name not in ("news_headlines", "morning_briefing", "reminder"), (
                f"COLLISION: '{u}' misrouted to news/briefing/reminder via 'báo'!"
            )

    def test_homophone_tat_vs_tac(self, router: LLMIntentRouter):
        """'tắt' (power/volume mute) must NEVER collide with 'tắc' (traffic/jam)."""
        # Utterances with 'tắt'
        tat_cases = [
            ("tắt máy", "system_power"),
            ("tắt tiếng", "system_volume"),
            ("tắt", "system_power"),
        ]
        for u, expected in tat_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name == expected, f"'{u}' should route to {expected}, got {res.action_name}"

        # Utterances with 'tắc' -> MUST NOT trigger system_power shutdown
        tac_cases = [
            "tắc đường",
            "kẹt xe tắc đường quá",
            "ùn tắc giao thông nghiêm trọng",
            "nghẽn tắc mạng nội bộ",
            "tắc cống",
        ]
        for u in tac_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name != "system_power", (
                f"CRITICAL COLLISION: Traffic utterance '{u}' triggered system_power shutdown via 'tắt'!"
            )


# ============================================================================
# 3. SINGLE-WORD BOUNDARY & DIACRITIC PRESERVATION
# ============================================================================

class TestSingleWordBoundaryAndPreservation:
    """Verifies that single-word rules preserve diacritics and enforce word boundaries."""

    def test_single_word_unaccented_non_match(self, router: LLMIntentRouter):
        """Unaccented single words ('nhac', 'dan') MUST NOT match accented rules ('nhạc', 'dán')."""
        res_nhac = router.parse_intent("nhac", force_llm=False)
        assert res_nhac.action_name != "spotify", (
            f"Single-word unaccented 'nhac' matched 'nhạc' -> spotify! Must preserve diacritics."
        )

        res_dan = router.parse_intent("dan", force_llm=False)
        assert res_dan.action_name != "skill_clipboard", (
            f"Single-word unaccented 'dan' matched 'dán' -> skill_clipboard! Must preserve diacritics."
        )

    def test_single_word_subword_non_match(self, router: LLMIntentRouter):
        """Single words with diacritics must not match when they appear as subwords."""
        subword_cases = [
            ("kinh doanh", "skill_clipboard"),   # contains 'd' but not 'dán'
            ("giàn giáo", "skill_clipboard"),
            ("mạt chược", "spotify"),           # contains 'nh' but not 'nhạc'
            ("lập tức", "system_power"),         # contains 't' but not 'tắt'
        ]
        for u, forbidden_action in subword_cases:
            res = router.parse_intent(u, force_llm=False)
            assert res.action_name != forbidden_action, (
                f"Subword collision: '{u}' matched {forbidden_action}!"
            )


# ============================================================================
# 4. POLYSYLLABIC PHRASE DIACRITIC FOLDING & PERMUTATIONS
# ============================================================================

class TestPolysyllabicPhraseVariations:
    """Verifies diacritic folding for multi-word phrases (len(words) >= 2)."""

    MULTIWORD_CASES = [
        # (original accented, unaccented, expected_action)
        ("Điều chỉnh âm lượng", "dieu chinh am luong", "system_volume"),
        ("Tìm kiếm Google.", "tim kiem google", "web_open"),
        ("Trời hôm nay thế nào?", "troi hom nay the nao", "shell_exec"),
        ("mở ứng dụng chrome", "mo ung dung chrome", "app_open"),
        ("nhắc nhở lúc 8 giờ", "nhac nho luc 8 gio", "reminder"),
        ("báo cáo buổi sáng", "bao cao buoi sang", "morning_briefing"),
        ("đọc báo", "doc bao", "news_headlines"),
        ("tắt máy tính", "tat may tinh", "system_power"),
    ]

    def test_exact_accented_phrases(self, router: LLMIntentRouter):
        """Exact accented utterances match intended action."""
        for accented, _, expected in self.MULTIWORD_CASES:
            res = router.parse_intent(accented, force_llm=False)
            assert res.action_name == expected, (
                f"Accented '{accented}' expected {expected}, got {res.action_name}"
            )

    def test_unaccented_folded_phrases(self, router: LLMIntentRouter):
        """Unaccented variants match identically to accented ones."""
        for _, unaccented, expected in self.MULTIWORD_CASES:
            res = router.parse_intent(unaccented, force_llm=False)
            assert res.action_name == expected, (
                f"Unaccented '{unaccented}' expected {expected}, got {res.action_name}"
            )

    def test_mixed_casing_and_punctuation(self, router: LLMIntentRouter):
        """Mixed casing and noisy punctuation match cleanly."""
        noisy_samples = [
            ("...ĐIỀU CHỈNH ÂM LƯỢNG???", "system_volume"),
            ("  [Tìm kiếm Google]!  ", "web_open"),
            ("Trời Hôm Nay Thế Nào...", "shell_exec"),
            ("MỞ ỨNG DỤNG CHROME!!!", "app_open"),
            ("nhắc Nhở Lúc 8 Giờ.", "reminder"),
        ]
        for noisy, expected in noisy_samples:
            res = router.parse_intent(noisy, force_llm=False)
            assert res.action_name == expected, (
                f"Noisy '{noisy}' expected {expected}, got {res.action_name}"
            )

    def test_nfd_polysyllabic_phrases(self, router: LLMIntentRouter):
        """Decomposed Unicode (NFD) polysyllabic phrases must fold and match correctly."""
        for accented, _, expected in self.MULTIWORD_CASES:
            nfd_text = unicodedata.normalize("NFD", accented)
            res = router.parse_intent(nfd_text, force_llm=False)
            assert res.action_name == expected, (
                f"NFD normalized '{accented}' expected {expected}, got {res.action_name}"
            )


# ============================================================================
# 5. PREDICT_INTENT CONTRACT SYNCHRONIZATION
# ============================================================================

class TestPredictIntentContract:
    """Verifies tests/eval/stt_intent_eval.py::predict_intent contract with router."""

    def test_predict_intent_recognized_actions(self):
        """Recognized intents return action_name string directly."""
        assert predict_intent("Điều chỉnh âm lượng") == "system_volume"
        assert predict_intent("mở ứng dụng chrome") == "app_open"
        assert predict_intent("tìm kiếm google") == "web_open"
        assert predict_intent("báo cáo buổi sáng") == "morning_briefing"
        assert predict_intent("dừng lại") == "system_power"

    def test_predict_intent_unknown_maps_to_no_intent(self):
        """Unrecognized / out-of-domain queries return 'NO_INTENT'."""
        unknown_queries = [
            "câu lệnh ngẫu nhiên không khớp bất kỳ rule nào 12345",
            "con mèo đang ngủ trên mái nhà",
            "hôm nay đi ăn phở hay bún bò",
            "tôi muốn mua một chiếc ô tô",
        ]
        for q in unknown_queries:
            result = predict_intent(q)
            assert result == "NO_INTENT", f"Query '{q}' expected 'NO_INTENT', got '{result}'"

    def test_predict_intent_empty_or_whitespace(self):
        """Empty, whitespace-only, or punctuation-only returns 'NO_INTENT'."""
        assert predict_intent("") == "NO_INTENT"
        assert predict_intent("   ") == "NO_INTENT"
        assert predict_intent("\t\n") == "NO_INTENT"


# ============================================================================
# 6. ADVERSARIAL STRESS & REDOS RESISTANCE
# ============================================================================

class TestAdversarialStressAndReDoS:
    """Ensures sub-millisecond execution and immunity to algorithmic complexity attacks."""

    def test_moderate_string_latency_sla(self, router: LLMIntentRouter):
        """A 1KB repetitive query (< 2048 chars) must match within 20ms SLA."""
        payload = "điều chỉnh âm lượng " * 50  # ~1000 characters
        start = time.perf_counter()
        res = router.parse_intent(payload, force_llm=False)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert res.action_name == "system_volume"
        assert elapsed_ms < 20.0, f"Latency SLA breached! Took {elapsed_ms:.2f} ms (> 20.0 ms SLA)"

    def test_massive_string_dos_rejection_sla(self, router: LLMIntentRouter):
        """A 50KB repetitive query must be rejected in under 20ms to prevent DoS."""
        long_payload = "điều chỉnh âm lượng " * 2500  # ~50,000 characters
        start = time.perf_counter()
        res = router.parse_intent(long_payload, force_llm=False)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        # Must reject (DoS guard at >2048 chars) and finish within 20ms SLA
        assert res.action_name == "unknown_intent"
        assert elapsed_ms < 20.0, f"ReDoS vulnerability! Took {elapsed_ms:.2f} ms (> 20.0 ms SLA)"

    def test_massive_unmatched_payload(self, router: LLMIntentRouter):
        """A 50KB unmatched noise payload must return unknown_intent under 20ms."""
        noise_payload = "a" * 50000
        start = time.perf_counter()
        res = router.parse_intent(noise_payload, force_llm=False)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert res.action_name == "unknown_intent"
        assert elapsed_ms < 20.0, f"Unmatched payload took {elapsed_ms:.2f} ms (> 20.0 ms SLA)"
