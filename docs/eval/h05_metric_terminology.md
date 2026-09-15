# H-05 Metric Terminology Mapping

**Status**: documentation note, added during the H-05 acceptance audit. Does
**not** change, recompute, or supersede any previously measured/committed
number in `docs/eval/stt_eval_independent_summary.md`,
`docs/eval/stt_eval_failure_decomposition.md`, or any file under
`docs/eval/independent_benchmark*/`. Those remain the frozen historical
evidence for the 420-trial (N=210 clean + N=210 noisy, small & large-v3)
independent benchmark.

## Why this note exists

The evaluator's 4-way taxonomy (`tests/eval/failure_decomposition.py`) —
`CORRECT` / `MISROUTED` / `STT_EMPTY` / `ROUTER_ABSTAIN` — is the taxonomy
actually implemented and measured throughout this project's eval history.
The official H-05 acceptance contract describes results in different,
higher-level terms: **STT success**, **intent success**, **misroute**,
**abstain**. This note makes the mapping between the two explicit and
unambiguous, so a reader does not have to infer it.

## The mapping

| Official H-05 term | Definition (per the H-05 contract) | Existing 4-way taxonomy equivalent | Field in `_bucket_stats()` output |
| --- | --- | --- | --- |
| **STT success** | Non-empty STT transcript rate | `1 - STT_EMPTY_rate` (i.e. every trial that is *not* `STT_EMPTY`, regardless of whether the router then routes correctly, misroutes, or abstains) | `stt_success_count` / `stt_success_rate` |
| **Intent success** | Correct routed intent/action rate | `CORRECT` | `intent_success_count` / `intent_success_rate` (alias of `n_correct` / `correct_rate`) |
| **Misroute** | Wrong routed action rate | `MISROUTED` | `misroute_count` / `misroute_rate` (alias of `n_misrouted` / `misrouting_rate`) |
| **Abstain** | Router produced no actionable intent *after* a non-empty STT transcript | `ROUTER_ABSTAIN` (explicitly **not** `STT_EMPTY` — an empty transcript is an STT failure, not a router abstention) | `abstain_count` / `abstain_rate` (alias of `n_router_abstain` / `router_abstain_rate`) |

Every trial falls into exactly one of the four buckets, so:

```
STT success (non-empty transcripts) = intent_success + misroute + abstain
                                     = n_trials - STT_EMPTY
```

## Where these aliases live

`tests/eval/failure_decomposition.py::_bucket_stats()` now returns both the
original field names (`n_correct`, `correct_rate`, `n_misrouted`,
`misrouting_rate`, `n_stt_empty`, `stt_empty_rate`, `n_router_abstain`,
`router_abstain_rate`, `end_to_end_abstention_rate` — all unchanged, byte-
for-byte the same computation as before) **and** the new official-terminology
alias fields (`stt_success_count`/`stt_success_rate`,
`intent_success_count`/`intent_success_rate`, `misroute_count`/
`misroute_rate`, `abstain_count`/`abstain_rate`). This is purely additive:
any code or historical JSON that reads the original field names is
unaffected; the aliases are new keys layered on top for callers that want
the official H-05 vocabulary directly.

`tests/eval/stt_intent_eval.py`'s own `Summary` dataclass (used to produce
`docs/eval/independent_benchmark*/stt_eval_summaries_direct.json`) was
deliberately **not** modified, to avoid touching the exact schema that
historical evidence file already committed under. `_bucket_stats()` in
`failure_decomposition.py` is the recommended entry point when official
H-05 terminology is needed going forward.

## Historical evidence is unaffected

No number in `docs/eval/stt_eval_independent_summary.md` changed. The
420-trial benchmark (Whisper `small` and `large-v3`, clean + noisy) and its
`CORRECT` / `MISROUTED` / `STT_EMPTY` / `ROUTER_ABSTAIN` counts remain
exactly as originally measured and reported. This note only clarifies
vocabulary and adds non-destructive derived fields to the evaluator's
in-memory/JSON output shape for *future* runs.
