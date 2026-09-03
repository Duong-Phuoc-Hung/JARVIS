# Handoff Report: Router Architecture, Safe Diacritic Normalization, & Phonetic Drift Expansion (v4.8.1)

**Author:** Explorer Survey Router  
**Target:** Parent Agent / Implementer Agent  
**Working Directory:** `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\`  
**Date:** 2026-09-03  

---

## 1. Observation

### 1.1 Current Implementation of `_match_rule_key` in `jarvis/llm/router.py`
In `jarvis/llm/router.py` (lines 1803–1820), deterministic dictionary key matching is implemented as:

```python
1803:     def _match_rule_key(self, key: str, clean_lower: str) -> bool:
1804:         """Determines if clean_lower matches the deterministic key."""
1805:         if not key or not clean_lower:
1806:             return False
1807:         if key not in clean_lower:
1808:             return False
1809:         if len(key) <= 4:
1810:             if clean_lower == key:
1811:                 return True
1812:             pattern = getattr(self, "_short_key_regexes", {}).get(key)
1813:             if pattern is None:
1814:                 pattern = re.compile(r"(?:\b|^)" + re.escape(key) + r"(?:\b|$)", re.IGNORECASE)
1815:                 if not hasattr(self, "_short_key_regexes"):
1816:                     self._short_key_regexes = {}
1817:                 self._short_key_regexes[key] = pattern
1818:             return bool(pattern.search(clean_lower))
1819:         return True
```

**Key Code Observations:**
1. **No diacritic normalization exists:** Direct Python substring check `key in clean_lower` (line 1807) enforces strict character-by-character equality. If `key` is unaccented (e.g. `"dieu chinh am luong"`, line 1115), an accented user query such as `"Điều chỉnh âm lượng"` fails `key not in clean_lower` and yields `False`.
2. **Character-length boundary rather than word-token boundary:** Line 1809 tests `len(key) <= 4`. Single-word keys with length $> 4$ (e.g. `"reboot"`, `"cancel"`, `"chuông"`, `"settings"`) bypass regex boundary enforcement and fall through to line 1819 (`return True`), allowing arbitrary substring matches inside other words.
3. **No Unicode NFC/NFD decomposition handling:** Characters arriving in decomposed NFD (e.g. `e` + `\u0300` for `è`) fail to match precomposed NFC strings in `self.rule_engine`.
4. **Precompilation restriction:** In `IntentRouter.__init__` (lines 1287–1291), `self._short_key_regexes` only precompiles keys where `len(k) <= 4 and k.isascii()`. Accented short Vietnamese keys (e.g. `"tắt"`, `"dừng"`, `"mở"`) are compiled dynamically on first access.

### 1.2 Rule Dictionary State for Target Test Cases
- `"dieu chinh am luong"` exists at line 1115:
  ```python
  "dieu chinh am luong": IntentResult(action_name="system_volume", parameters={"delta": 0}, source="rule_fallback", response_text="Đang điều chỉnh âm lượng cho Ngài."),
  ```
  There is no accented `"điều chỉnh âm lượng"` entry in `self.rule_engine`.
- `"tim kiem google"` exists at line 1231:
  ```python
  "tim kiem google": IntentResult(action_name="web_open", parameters={"query": "google", "target": "https://www.google.com"}, source="rule_fallback", response_text="Đang tìm kiếm trên Google cho Ngài."),
  ```
  There is no accented `"tìm kiếm google"` entry in `self.rule_engine`.
- `"troi hom nay"` exists at line 1169:
  ```python
  "troi hom nay": IntentResult(action_name="shell_exec", parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"}, source="rule_fallback", response_text="Đang kiểm tra tình hình thời tiết hôm nay cho Ngài."),
  ```
  In addition, parametric regex pattern at line 1416:
  ```python
  re.compile(r"^(?:jarvis[,\s]*)?(?:dự\s*báo|du\s*bao|xem|kiểm\s*tra|kiem\s*tra)?\s*(?:thời\s*tiết|thoi\s*tiet|weather|trời|troi)\s*(?:hôm\s*nay|hom\s*nay|ngày\s*mai|ngay\s*mai|hiện\s*tại|today|forecast|tại|ở|khu\s*vực)?\s*(.*)$", re.IGNORECASE)
  ```
  matches `"Trời hôm nay thế nào?"` and extracts to `shell_exec` via `_make_weather_intent`.
- Single-word entries in `self.rule_engine`:
  - `"dừng"` at lines 95–96 in `tests/eval/routing_eval_n150.py` and in `self.rule_engine` maps to `system_power` (`action: "lock"`).
  - `"tắt"` at line 1151 maps to `system_power` (`action: "shutdown"`).
  - `"nhac"` at line 1184 maps to `spotify` (`action_name="spotify"`).

### 1.3 Eval Infrastructure in `tests/eval/stt_intent_eval.py`
In `tests/eval/stt_intent_eval.py` (lines 149–174), `predict_intent` currently does NOT invoke the production router pipeline:
```python
149: def predict_intent(transcript: str) -> str:
150:     """
151:     Route transcript through Tier-1 rule_engine (deterministic substring match).
152:     Returns router action_name (e.g. 'system_power') or 'NO_INTENT'.
153:     Use EXPECTED_ACTIONS to map action_name back to eval intent.
154:     """
155:     global _ROUTER
156:     if _ROUTER is None:
157:         _ROUTER = _build_router()
158:     t = transcript.lower().strip()
159:     if not t: return "NO_INTENT"
160:     if _ROUTER is not None:
161:         for keyword, result in _ROUTER.rule_engine.items():
162:             if keyword in t:
163:                 return result.action_name
```
Lines 161–163 iterate `_ROUTER.rule_engine.items()` raw in insertion order, skipping `self._sorted_rule_keys`, `_match_rule_key`, and `self._regex_rules`.

---

## 2. Logic Chain

### 2.1 The Need for Two-Class Word Token Matching
- **Observation 1.1** demonstrates that `_match_rule_key` currently applies substring matching without considering word count.
- In Vietnamese phonetics, monosyllabic words (single words) have extensive homophonic and tonal collisions when tone marks are removed:
  - `nhạc` (music) stripped becomes `nhac`. `nhắc` (remind, as in `nhắc nhở`) stripped becomes `nhac`. If diacritics are removed from single words or substring matching is permitted, saying `"nhắc nhở lúc 8 giờ"` matches `nhạc` and triggers music playback instead of a reminder.
  - `dừng` (stop) stripped becomes `dung`. `dụng` (application, as in `ứng dụng`) stripped becomes `dung`. If single-word diacritic stripping or substring matching is allowed, saying `"mở ứng dụng chrome"` matches `dừng` and shuts down / locks the machine.
  - `dán` (paste) stripped becomes `dan`. `dẫn` (guide, as in `hướng dẫn` or `hấp dẫn`) stripped becomes `dan`.
- Conversely, polysyllabic phrases (`len(words) >= 2`) possess high contextual and semantic specificity (e.g. `"điều chỉnh âm lượng"`, `"tìm kiếm google"`, `"tắt máy tính"`, `"ghi chú mới"`). No cross-domain collisions exist for 2+ word Vietnamese phrases in the JARVIS command dictionary.
- **Deduction:** Diacritic folding must strictly apply **only** to multi-word phrases (`len(words) >= 2`). Single-word rules (`len(words) == 1`) must strictly preserve diacritics and enforce whole-word token boundaries `(?:\b|^)key(?:\b|$)`.

### 2.2 Unicode Decomposition Architecture for Diacritic Normalization
- Standard Vietnamese diacritics encompass 5 tone marks across 12 vowels (a, ă, â, e, ê, i, o, ô, ơ, u, ư, y) in uppercase and lowercase, plus the consonant letter `đ`/`Đ`.
- In Unicode:
  - Vowel tone marks, circumflexes (`^`), breves (`˘`), and horns (`ơ`, `ư`) decompose canonically under `unicodedata.normalize('NFD', text)` into base ASCII Latin letters + combining diacritical marks in the Unicode range `\u0300-\u036f`.
  - The consonant `đ` (`\u0111`) and `Đ` (`\u0110`) does NOT decompose under NFD or NFKD. It must be explicitly mapped to `d` / `D`.
- Applying `_COMBINING_DIACRITICS_RE.sub("", text.replace('đ', 'd').replace('Đ', 'D'))` on NFD-normalized text guarantees that both precomposed (NFC) and decomposed (NFD) representations produce identical, canonical ASCII text with zero loss or corruption of punctuation, whitespace, or digits.

### 2.3 Sub-millisecond Execution Strategy
- Iterating 1,000+ rules and running `strip_vietnamese_diacritics` inside the matching loop would incur $O(N)$ string normalization overhead per voice utterance (~5 ms).
- **Optimization:** Normalize the incoming query `clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)` **exactly once** before entering the rule loop.
- Precompute `self._stripped_rule_keys` and `self._rule_word_counts` at initialization time in `IntentRouter.__init__`.
- Check `key_stripped in clean_lower_stripped` in Python/C (~15 ns) as an immediate fast-reject filter before applying regex boundary evaluation.

---

## 3. Caveats

1. **Compound Word Tokenization:** Vietnamese is an isolating language where words consist of single or multiple syllables separated by spaces. Treating whitespace-separated tokens as `words` matches standard NLP practice in Vietnamese voice commands (`len(key.strip().split())`).
2. **Punctuation Stripping:** Voice transcripts frequently append terminal punctuation (`.`, `?`, `!`, `,`). Regex token boundaries `(?:\b|^)key(?:\b|$)` properly handle trailing punctuation because punctuation characters are `\W`.
3. **No Codebase Write In This Step:** As an Explorer agent, this report provides exact architectural blueprints, before/after code diffs, and verification commands without directly modifying source files outside `.agents/`.

---

## 4. Conclusion & Technical Design

### 4.1 Specification of `strip_vietnamese_diacritics(text: str) -> str`
Add the following implementation to `jarvis/llm/router.py`:

```python
import unicodedata
import re

_COMBINING_DIACRITICS_RE = re.compile(r"[\u0300-\u036f]")

def strip_vietnamese_diacritics(text: str) -> str:
    """
    Strips all Vietnamese diacritics / tone marks and normalizes 'đ'/'Đ' to 'd'/'D'.
    Supports both precomposed NFC and decomposed NFD Unicode representations.
    Preserves all ASCII characters, whitespace, numbers, and punctuation.

    Examples:
        'Điều chỉnh âm lượng' -> 'Dieu chinh am luong'
        'Tìm kiếm Google.'    -> 'Tim kiem Google.'
        'Trời hôm nay thế nào?' -> 'Troi hom nay the nao?'
        'đặc nhắc'            -> 'dac nhac'
        'nhạc'                -> 'nhac'
    """
    if not text:
        return ""
    nfd = unicodedata.normalize("NFD", text)
    d_mapped = nfd.replace("đ", "d").replace("Đ", "D")
    return _COMBINING_DIACRITICS_RE.sub("", d_mapped)
```

### 4.2 Optimized Implementation of `_match_rule_key`
Replace lines 1803–1820 in `jarvis/llm/router.py` with:

```python
    def _get_word_boundary_pattern(self, pattern_key: str) -> re.Pattern:
        """Retrieves or compiles a cached word-boundary pattern."""
        if not hasattr(self, "_rule_key_regexes"):
            self._rule_key_regexes: dict[str, re.Pattern] = {}
        pattern = self._rule_key_regexes.get(pattern_key)
        if pattern is None:
            pattern = re.compile(r"(?:\b|^)" + re.escape(pattern_key) + r"(?:\b|$)", re.IGNORECASE)
            self._rule_key_regexes[pattern_key] = pattern
        return pattern

    def _match_rule_key(
        self,
        key: str,
        clean_lower: str,
        clean_lower_stripped: str | None = None,
    ) -> bool:
        """
        Determines if clean_lower matches the deterministic key with safe diacritic folding.
        - Single-word rules (len(words) == 1): STRICT whole-word token match with diacritics PRESERVED.
          Never substring, never diacritic-folded, completely preventing homophone collisions.
        - Multi-word rules (len(words) >= 2): Diacritic folding enabled with word boundary verification.
        """
        if not key or not clean_lower:
            return False

        word_count = getattr(self, "_rule_word_counts", {}).get(key)
        if word_count is None:
            word_count = len(key.strip().split())

        # 1. Single-word rules: preserve diacritics, enforce whole-word token boundary
        if word_count == 1:
            if key not in clean_lower:
                return False
            if clean_lower == key:
                return True
            pattern = self._get_word_boundary_pattern(key)
            return bool(pattern.search(clean_lower))

        # 2. Multi-word rules: check exact match first
        if key in clean_lower:
            if clean_lower == key:
                return True
            pattern = self._get_word_boundary_pattern(key)
            if pattern.search(clean_lower):
                return True

        # 3. Multi-word rules: safe diacritic folding
        if clean_lower_stripped is None:
            clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)

        key_stripped = getattr(self, "_stripped_rule_keys", {}).get(key)
        if key_stripped is None:
            key_stripped = strip_vietnamese_diacritics(key)

        if key_stripped not in clean_lower_stripped:
            return False
        if clean_lower_stripped == key_stripped:
            return True

        pattern_stripped = self._get_word_boundary_pattern(key_stripped)
        return bool(pattern_stripped.search(clean_lower_stripped))
```

### 4.3 Precomputing Tables in `IntentRouter.__init__`
In `IntentRouter.__init__` around lines 1285–1292:

```python
        # Pre-sort rule dictionary keys by descending length for greedy exact match
        self._sorted_rule_keys: list[str] = sorted(self.rule_engine.keys(), key=len, reverse=True)
        # Precompute stripped representations and word counts for sub-millisecond matching
        self._stripped_rule_keys: dict[str, str] = {
            k: strip_vietnamese_diacritics(k) for k in self.rule_engine
        }
        self._rule_word_counts: dict[str, int] = {
            k: len(k.strip().split()) for k in self.rule_engine
        }
        self._rule_key_regexes: dict[str, re.Pattern] = {}
```

### 4.4 Loop Optimization in `parse_intent`
In `parse_intent` (lines 2355–2370 and lines 2448–2462), compute `clean_lower_stripped` once:

```python
        clean_lower = clean_lower_full
        clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)

        # Then check sorted rule dictionary keys — full text, O(n) substring checks are fast
        for key in self._sorted_rule_keys:
            if self._match_rule_key(key, clean_lower, clean_lower_stripped):
                intent = self.rule_engine[key]
                ...
```

### 4.5 R3 Phonetic Drift Aliases Mapping Table
Add the following 15 new phonetic drift rules into `self.rule_engine`:

| Intent Action | Utterance Key | Length | Word Count | Parameters | Confirmation / Danger | Rationale |
|---|---|---|---|---|---|---|
| `system_power` | `"tắc máy"` | 7 | 2 | `{"action": "shutdown"}` | Yes, CRITICAL | Faster-Whisper hearing "tắc" for "tắt" |
| `system_power` | `"tập máy tính"` | 12 | 3 | `{"action": "shutdown"}` | Yes, CRITICAL | Faster-Whisper hearing "tập" for "tắt" |
| `system_power` | `"sắt đau má"` | 10 | 3 | `{"action": "shutdown"}` | Yes, CRITICAL | Faster-Whisper phonetic drift for "shut down máy" |
| `app_open` | `"cái đặt"` | 7 | 2 | `{"app_name": "Settings", "app": "ms-settings:"}` | None | Faster-Whisper tone shift (acute "cái" vs grave "cài") |
| `app_open` | `"má kẻ đặt"` | 9 | 3 | `{"app_name": "Settings", "app": "ms-settings:"}` | None | Faster-Whisper phonetic drift for "mở cài đặt" |
| `app_open` | `"open sentence"` | 13 | 2 | `{"app_name": "Settings", "app": "ms-settings:"}` | None | Faster-Whisper acoustic confusion for "open settings" |
| `app_open` | `"open sente"` | 10 | 2 | `{"app_name": "Settings", "app": "ms-settings:"}` | None | Truncated STT token for "open settings" |
| `reminder` | `"đặt time"` | 8 | 2 | `{"message": "nhắc nhở chung"}` | None | Faster-Whisper acoustic confusion for "đặt timer" |
| `reminder` | `"đặc nhắc"` | 8 | 2 | `{"message": "nhắc nhở chung"}` | None | Faster-Whisper tone shift (dot below "đặc" vs acute "đặt") |
| `system_volume` | `"tắc tính"` | 8 | 2 | `{"mute": True}` | None | Faster-Whisper acoustic confusion for "tắt tiếng" |
| `system_volume` | `"tắt tính"` | 8 | 2 | `{"mute": True}` | None | Faster-Whisper tone shift for "tắt tiếng" |
| `memory_save_fact` | `"ghi chú"` | 7 | 2 | `{}` | None | Direct note command without trailing colon |
| `memory_save_fact` | `"ghi chu"` | 7 | 2 | `{}` | None | Unaccented direct note command |
| `memory_save_fact` | `"tạo ghi chú mới"` | 15 | 4 | `{}` | None | Standard Vietnamese phrase for create note |
| `memory_save_fact` | `"tao ghi chu moi"` | 15 | 4 | `{}` | None | Unaccented phrase for create note |

### 4.6 Synchronization of `tests/eval/stt_intent_eval.py`
In `tests/eval/stt_intent_eval.py`, update `predict_intent` (lines 149–175) to route via the production `_ROUTER`:

```python
def predict_intent(transcript: str) -> str:
    """
    Route transcript through Tier-1 production router with safe diacritic normalization.
    Returns router action_name (e.g. 'system_power') or 'NO_INTENT'.
    """
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = _build_router()
    t = transcript.strip()
    if not t:
        return "NO_INTENT"
    if _ROUTER is not None:
        res = _ROUTER.parse_intent(t, force_llm=False)
        if res and res.action_name not in ("unknown_intent", "generic_llm_response"):
            return res.action_name
    # Fallback: ASCII/English keyword match
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
```

Also add an explicit guard in `jarvis/llm/router.py` before Tier 2:
```python
        # 2. TIER 2: LLM Semantic Reasoning
        if self.llm is None:
            return IntentResult(
                action_name="unknown_intent",
                parameters={"raw_text": text},
                confidence=0.0,
                source="rule_fast_path",
                raw_text=text,
                response_text="Tôi chưa hiểu lệnh này, vui lòng thử cách khác",
            )
```
This avoids unnecessary exception throwing when evaluating offline without an LLM.

---

## 5. Verification Method

### 5.1 Static Test Assertions for Implementation Verification
To independently verify the implementation, the following assertions must hold:

```python
from jarvis.llm.router import strip_vietnamese_diacritics, LLMIntentRouter
import unicodedata

# 1. Unicode diacritic stripping verification
assert strip_vietnamese_diacritics("Điều chỉnh âm lượng") == "Dieu chinh am luong"
assert strip_vietnamese_diacritics("Tìm kiếm Google.") == "Tim kiem Google."
assert strip_vietnamese_diacritics("Trời hôm nay thế nào?") == "Troi hom nay the nao?"
assert strip_vietnamese_diacritics("đặc nhắc") == "dac nhac"
assert strip_vietnamese_diacritics("sắt đau má") == "sat dau ma"
# Decomposed NFD verification:
nfd_input = unicodedata.normalize("NFD", "Điều chỉnh âm lượng")
assert strip_vietnamese_diacritics(nfd_input) == "Dieu chinh am luong"

# 2. Zero-homophone-collision verification
router = LLMIntentRouter(llm_client=None, fast_path_enabled=True)

# Single word "dừng" must NOT match inside "ứng dụng"
res_app = router.parse_intent("mở ứng dụng chrome", force_llm=False)
assert res_app.action_name == "app_open"

# Single word "nhạc" must NOT match inside "nhắc nhở"
res_remind = router.parse_intent("nhắc nhở lúc 8 giờ", force_llm=False)
assert res_remind.action_name == "reminder"

# Single word "dán" must NOT match inside "hướng dẫn"
res_guide = router.parse_intent("hướng dẫn sử dụng", force_llm=False)
assert res_guide.action_name != "clipboard_paste"

# 3. Acceptance criteria test cases
assert router.parse_intent("Điều chỉnh âm lượng", force_llm=False).action_name == "system_volume"
assert router.parse_intent("Tìm kiếm Google.", force_llm=False).action_name == "web_open"
assert router.parse_intent("Trời hôm nay thế nào?", force_llm=False).action_name == "shell_exec"

# 4. Phonetic drift aliases
assert router.parse_intent("tắc máy", force_llm=False).action_name == "system_power"
assert router.parse_intent("tập máy tính", force_llm=False).action_name == "system_power"
assert router.parse_intent("sắt đau má", force_llm=False).action_name == "system_power"
assert router.parse_intent("cái đặt", force_llm=False).action_name == "app_open"
assert router.parse_intent("má kẻ đặt", force_llm=False).action_name == "app_open"
assert router.parse_intent("open sentence", force_llm=False).action_name == "app_open"
assert router.parse_intent("đặt time", force_llm=False).action_name == "reminder"
assert router.parse_intent("đặc nhắc", force_llm=False).action_name == "reminder"
assert router.parse_intent("tắc tính", force_llm=False).action_name == "system_volume"
assert router.parse_intent("tắt tính", force_llm=False).action_name == "system_volume"
assert router.parse_intent("ghi chú", force_llm=False).action_name == "memory_save_fact"
assert router.parse_intent("tạo ghi chú mới", force_llm=False).action_name == "memory_save_fact"
```

### 5.2 Test Suite Execution Commands
Once implemented by the worker/implementer agent, verify with:
1. `pytest tests/unit/test_router_p0.py tests/test_adversarial_m1_intent_router.py -q` (0 failures)
2. `python tests/eval/routing_eval_n150.py` (CORRECT 100%, SILENT <= 5%, MISROUTED = 0)
3. `pytest tests/eval/test_voice_generalization_heldout.py -q` (0 failures)
4. `python tests/eval/stt_intent_eval.py --models large-v3 --backend direct` (eval on 90 WAV files)
