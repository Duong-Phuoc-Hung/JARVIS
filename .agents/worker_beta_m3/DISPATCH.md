## 2026-09-13T11:09:46Z
You are Worker M3 for the JARVIS Beta v1 project.

Your working directory is: d:\Software GitCode\JARVIS\.agents\worker_beta_m3
Your parent is: fcbdbddb-159a-4432-af21-f3ef3e4e8c4e (Project Orchestrator)

Authoritative User Request: d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md (You MUST read this file first).
Scope Document: d:\Software GitCode\JARVIS\PROJECT.md
Worker M2 Handoff: d:\Software GitCode\JARVIS\.agents\worker_beta_m2\handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All benchmarks and evaluations must be genuine. DO NOT hardcode benchmark numbers, fake outcome tables, or fabricate results. An independent auditor will verify your logs and artifacts against execution traces.

File Write Ownership:
- d:\Software GitCode\JARVIS\docs\eval\independent_benchmark\ (and files within)
- d:\Software GitCode\JARVIS\docs\eval\stt_eval_independent_summary.md

Objectives:
Execute the direct multi-condition benchmark for Requirement R3 (H-05 / A3, A4) on the 420-utterance independent audio dataset created in `tests/eval/audio_independent/`:
1. Execute Whisper `small` model evaluation across `clean` and `noisy` conditions:
   ```powershell
   python tests/eval/stt_intent_eval.py --audio-dir tests/eval/audio_independent --manifest tests/eval/independent_test_manifest.py --models small --conditions clean noisy --backend direct --out-dir docs/eval/independent_benchmark
   ```
2. Execute Whisper `large-v3` model evaluation across `clean` and `noisy` conditions:
   ```powershell
   python tests/eval/stt_intent_eval.py --audio-dir tests/eval/audio_independent --manifest tests/eval/independent_test_manifest.py --models large-v3 --conditions clean noisy --backend direct --out-dir docs/eval/independent_benchmark
   ```
3. Inspect and verify the 4-way outcome classification (`CORRECT`, `MISROUTED`, `STT_EMPTY`, `ROUTER_ABSTAIN`) across all 4 runs:
   - Whisper small, clean (N=210)
   - Whisper small, noisy (N=210)
   - Whisper large-v3, clean (N=210)
   - Whisper large-v3, noisy (N=210)
4. Aggregate the empirical metrics into `docs/eval/stt_eval_independent_summary.md` with:
   - Sample size N for each condition
   - Rates and counts for CORRECT, MISROUTED, STT_EMPTY, and ROUTER_ABSTAIN
   - Latency metrics (p50, p90)
   - Comparison between clean vs. noisy and small vs. large-v3 tradeoffs
5. Output:
   - Write your handoff report to `d:\Software GitCode\JARVIS\.agents\worker_beta_m3\handoff.md` including verbatim stdout logs.
   - Send message to parent with completion summary.
