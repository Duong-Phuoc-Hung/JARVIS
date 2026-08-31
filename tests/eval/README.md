# tests/eval/ — STT Intent Misrouting Rate Evaluation

## Purpose
Measure the **intent misrouting rate** of STT models for architecture decision
(small vs large-v3 as interactive tier). This is a domain-closed system —
WER on free text is NOT the right metric.

## Three outcome classes (each has different implications)
| Outcome | Meaning | Risk |
|---------|---------|------|
| CORRECT | Transcript routed to correct intent | None |
| MISROUTED | Routed to WRONG intent | Safety risk (may execute wrong action) |
| SILENT_FAILURE | No intent recognized | UX issue only (user retries) |

## Two acoustic conditions
| Condition | Setup |
|-----------|-------|
| clean | Quiet room, normal distance, clear speech |
| 
oisy | Fan/TV at moderate level, or speaker farther from mic |

## Confidence threshold curve
Run at multiple thresholds (0.3-0.9) to find Pareto-optimal operating point.
Goal: minimize misrouting_rate while keeping silent_failure_rate < 30%.

## Recording structure
`
tests/eval/audio/
  clean/
    open_app/variant_0.wav
    open_app/variant_1.wav
    stop/variant_0.wav
    ...
  noisy/
    open_app/variant_0.wav
    ...
`

## Run evaluation
`powershell
.venv\Scripts\python.exe tests/eval/stt_intent_eval.py --models small large-v3
`

Results saved to docs/eval/stt_eval_results.json and stt_eval_summaries.json.
