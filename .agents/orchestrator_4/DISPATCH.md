## 2026-09-03T15:11:17Z

You are the Project Orchestrator for JARVIS.
Your task is to orchestrate the implementation and verification of the user request recorded in `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`):
Voice Pipeline Upgrade (v4.8.1) for JARVIS:
- R1. Safe Preprocessing Diacritic Normalization (`strip_vietnamese_diacritics` in `jarvis/llm/router.py`, safe multi-word folding, single-word whole-token match to prevent homophone collisions, sync `tests/eval/stt_intent_eval.py`).
- R2. Baseline Evaluation on 90 Real Audio Files (`tests/eval/stt_intent_eval.py --models large-v3 --backend direct` on 90 WAV files, measure ablation results: CORRECT >= 44.4%, ROUTER_ABSTAIN <= 50.0%, MISROUTED <= 3.3%).
- R3. Selective & Safe Phonetic Drift Aliases (Step 3: add high-specificity phonetic drift aliases like "tắc máy", "tập máy tính", "sắt đau má" for system_power; "cái đặt", "má kẻ đặt", "open sentence", "open sente" for app_open; "đặt time", "đặc nhắc" for reminder; "tắc tính", "tắt tính" for system_volume; "ghi chú", "ghi chu", "tạo ghi chú mới", "tao ghi chu moi" for memory_save_fact; verify 0 misrouting). Real audio eval target: CORRECT >= 50%, MISROUTED <= 4.4%, results saved in `docs/eval/stt_eval_results_direct.json` and `docs/eval/stt_eval_summaries_direct.json`.
- R4. Held-Out Generalization Evaluation (Anti-Overfitting Verification: `tests/eval/test_voice_generalization_heldout.py` with >= 25-30 unseen test cases across weather, reminder, system, search, volume, notes, apps; CORRECT >= 85%, MISROUTED == 0; all tests pass).
- R5. Full Test Suite Integrity, CHANGELOG v4.8.1, README, Git Main Push (`pytest tests/unit/ tests/test_adversarial_*.py -q` -> 0 failures; CHANGELOG.md updated with v4.8.1 details; README.md updated; clean git commit and push to origin main).

Your working directory for coordination files is `d:\Software GitCode\JARVIS\.agents\orchestrator_4\`.
Maintain your `BRIEFING.md`, `plan.md`, and `progress.md` in that directory.
Follow the subagent decomposition rules, deploy specialists (explorers, workers, reviewers, challengers), coordinate rigorous verification, and report back to Sentinel upon completion.

## 2026-09-03T16:18:00Z

You are the successor agent (generation 2) executing the remaining milestones for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\orchestrator_4\`.
Read `d:\Software GitCode\JARVIS\.agents\orchestrator_4\handoff.md`.
Read `d:\Software GitCode\JARVIS\.agents\orchestrator_4\PROJECT.md`.
Read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`).

Your parent is `e1930c7b-1696-49bd-b50d-8cdb48e7dd8f`.

Milestones M1 and M2 are fully completed and verified:
- M1: Safe diacritic normalization implemented and verified.
- M2: Real audio eval on 90 WAV files verified (CORRECT=46.67%, ROUTER_ABSTAIN=50.00%, MISROUTED=3.33%).

Your tasks to finish the sprint:
1. Milestone 3 (Selective & Safe Phonetic Drift Aliases & Eval):
   - Add the 15 phonetic drift aliases in `jarvis/llm/router.py`:
     - system_power: "tắc máy", "tập máy tính", "sắt đau má"
     - app_open: "cái đặt", "má kẻ đặt", "open sentence", "open sente"
     - reminder: "đặt time", "đặc nhắc"
     - system_volume: "tắc tính", "tắt tính"
     - memory_save_fact: "ghi chú", "ghi chu", "tạo ghi chú mới", "tao ghi chu moi"
   - Re-run eval on 90 WAV files:
     `python tests/eval/stt_intent_eval.py --models large-v3 --backend direct --cached-transcripts` (or live)
   - Verify: CORRECT >= 50.0% (expected ~63.3%), MISROUTED <= 4.4% (expected ~2.2%).
   - Verify updated `docs/eval/stt_eval_results_direct.json` and `docs/eval/stt_eval_summaries_direct.json`.
2. Milestone 4 (Held-Out Generalization Evaluation):
   - Create `tests/eval/test_voice_generalization_heldout.py` with >= 25–30 completely unseen utterances across 7 domains (weather, reminder, system, search, volume, notes, apps) with ZERO overlap with `PHRASE_MANIFEST` (the 45 phrases in `tests/eval/phrase_manifest.py`).
   - Verify: CORRECT >= 85%, MISROUTED == 0, 100% pytest pass.
3. Milestone 5 (Full Test Suite Integrity, CHANGELOG, README & Git Push):
   - Run `pytest tests/unit/ tests/test_adversarial_*.py -q` -> 0 failures.
   - Update `CHANGELOG.md` with v4.8.1 release details.
   - Update `README.md` voice recognition section.
   - Clean git commit & push to origin main.
   - Send complete final report to parent `e1930c7b-1696-49bd-b50d-8cdb48e7dd8f`.

## 2026-09-03T16:30:50Z

[Sentinel Acknowledgement]
Sprint Completion Report received.
Per Sentinel Protocol, Victory Audit is MANDATORY and BLOCKING.
Independent Victory Auditor (da62a71e-d4d0-4a01-a148-755e09558a10) is currently conducting the independent 3-phase audit across R1-R5.
Please stand by for the audit verdict.
