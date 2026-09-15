# H-05 No-Diacritic Vietnamese Regression (Text/Router Layer)

**Status**: new evidence, added during the H-05 acceptance audit. This is a
**separate** artifact from, and does not modify, the historical 420-trial
acoustic benchmark in `docs/eval/stt_eval_independent_summary.md`.

## Why this exists

`tests/eval/independent_test_manifest.py` (the corpus behind the 420-trial
acoustic benchmark) uses full Vietnamese diacritics in all 210 phrases —
confirmed by inspection, zero exceptions. The H-05 acceptance contract
requires both diacritic and no-diacritic Vietnamese coverage. Spoken audio
inherently carries true pronunciation regardless of how ground-truth text is
spelled, so an audio waveform cannot honestly be made "without accents" —
no-diacritic coverage is a text/router regression question, not an acoustic
one. See `tests/eval/no_diacritic_regression.py` for the full rationale and
the phrase manifest itself.

## What was measured

43 naturally-typed unaccented Vietnamese phrases, spanning all 14 of the
same workflow domains as the acoustic corpus (`open_app`, `system_shutdown`,
`system_restart`, `volume_control`, `weather_query`, `timer_set`,
`reminder_set`, `screenshot`, `stop`, `search`, `music_play`, `screen_off`,
`note_take`, `settings_open`), routed through the real production Tier-1
rule engine (`jarvis.llm.router.LLMIntentRouter`, `force_llm=False`, no
network/LLM calls) — the same router class the acoustic eval uses, and the
same `EXPECTED_ACTIONS` ground-truth mapping from
`tests/eval/failure_decomposition.py` (single-sourced, not a second
taxonomy).

These are genuine measured results, not a curated "always passes" list —
some phrases legitimately abstain, exactly as the acoustic corpus shows a
real abstention rate for its own conditions.

| Outcome | Count | Rate |
| --- | ---: | ---: |
| `CORRECT` | 31 | 72.1% |
| `MISROUTED` | 0 | 0.0% |
| `STT_EMPTY` | 0 | 0.0% (definitional — text input, not audio) |
| `ROUTER_ABSTAIN` | 12 | 27.9% |

**Zero misrouting**: every phrase the router could not confidently match
abstained (`ROUTER_ABSTAIN`/`NO_INTENT`) rather than routing to a wrong
action — consistent with the project's fail-closed posture, and with the
zero-misroute-inflation pattern already seen in the acoustic benchmark's
noise-condition results.

Full per-phrase results: `docs/eval/no_diacritic_regression_results.json`
(regenerate deterministically with
`python -m tests.eval.no_diacritic_regression`).

## Relationship to the acoustic benchmark

| | Acoustic benchmark (historical) | No-diacritic regression (this layer) |
| --- | --- | --- |
| Input | 420 real WAV recordings (spoken Vietnamese, full diacritics) | 43 literal Vietnamese text strings, no diacritics |
| Measures | STT transcription + routing, end-to-end | Router behavior on unaccented text only |
| `STT_EMPTY` possible? | Yes (measured at 0.0% across all 840 trials) | No — definitionally 0, there is no STT step |
| File | `docs/eval/stt_eval_independent_summary.md` | this file |

Neither file's numbers were changed to produce the other.
