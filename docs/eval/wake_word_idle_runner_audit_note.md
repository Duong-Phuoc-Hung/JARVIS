# H-06 Idle-Soak Runner: Historical Evidence Validity Note

**Status**: audit note, added while auditing H-06. Does **not** modify
`docs/eval/wake_word_idle_results.json` (kept exactly as committed, for
historical record) or `docs/ROADMAP.md`'s existing H-06 line.

## Finding

`docs/eval/wake_word_idle_results.json` (60-minute run, `"total_false_triggers": 0`,
`"false_positive_rate_per_hour": 0.0`) was produced by the **pre-correction**
version of `tests/eval/wake_word_idle_runner.py`, which had two confirmed
defects that make this specific "0 FP/hr" result unreliable as evidence of
genuine false-positive resistance:

1. **Sample-rate mismatch.** The runner opened a real `16000 Hz`
   `sounddevice.InputStream` (correctly recorded in the JSON's
   `"sample_rate": 16000` field) but constructed
   `WakeWordDetector(vad_threshold=threshold)` with **no `sample_rate=`
   argument**, so the detector used its constructor default of `44100`.
   Every incoming 16kHz block was then resampled inside
   `feed_audio_block()` as if it were 44.1kHz source audio — a ~2.75x
   time-compression and pitch-shift of the real signal reaching every
   downstream detector tier.
2. **Threshold parameter mismatch.** The `--threshold` CLI flag (default
   `0.5`, described as a "Sensitivity Threshold" in the log output and in
   the historical JSON's `"sensitivity_threshold": 0.5` field) was actually
   passed as `WakeWordDetector(vad_threshold=0.5)` — an unrelated RMS
   energy pre-filter gate whose sane range is roughly `0.001–0.02` for
   normalized float32 audio. A value of `0.5` sets that gate so high that
   ordinary room audio essentially never exceeds it, so the detector's
   confidence-computation tiers were rarely, if ever, actually reached
   during the run.

Combined, these two defects mean the historical `0 false triggers in
3600.1s` result cannot be trusted as evidence of good tuning — it is at
least partly (likely largely) an artifact of the detector being fed
corrupted/mis-rate audio through an effectively-disabled energy gate, not
of a well-tuned system correctly rejecting real ambient sound.

## What was NOT done

Per the audit's explicit instructions, this pass:
- did **not** delete, edit, or renumber `docs/eval/wake_word_idle_results.json`;
- did **not** change `docs/ROADMAP.md`'s existing H-06 status line;
- did **not** run a new live 30–60 minute microphone session to produce a
  replacement number (no live acceptance is claimed by this audit pass).

## What to do next

`tests/eval/wake_word_idle_runner.py` has been corrected (sample rate is
always explicit and matches the real stream; `--sensitivity` and
`--vad-threshold` are now two separate, correctly-wired flags; every
trigger's `engine`/`confidence`/`keyword` comes from the real
`WakeWordResult` returned by `feed_audio_block()`, never a fabricated
default). A genuine H-06 live acceptance result requires an operator with
real microphone hardware to run the corrected commands documented at the
top of that file (one per condition: `quiet`, `fan`, `music`, `youtube`,
`conversation`), and to save each run's JSON output under a **new**,
condition-specific filename (e.g. `docs/eval/wake_word_idle_quiet_results.json`)
— never overwriting the historical file above, which stays as the frozen
record of what was actually run under the old (defective) harness.
