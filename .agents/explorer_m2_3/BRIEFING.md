# BRIEFING — 2026-08-22T16:11:24Z

## Mission
Formulate the parameter extraction and safety confirmation blueprint for M2 (Smart Keyword Router Fallback in Vietnamese) in `jarvis/llm/router.py`, covering entity extraction, safety confirmation for power/restart actions, and regression prevention against existing tests.

## 🔒 My Identity
- Archetype: explorer
- Roles: read-only investigation, parameter extraction & safety confirmation design, blueprint synthesis
- Working directory: d:/Software GitCode/JARVIS/.agents/explorer_m2_3
- Original parent: 88e315c1-4bbc-4194-bae5-c1ca88628303
- Milestone: M2 - Smart Keyword Router Fallback in Vietnamese

## 🔒 Key Constraints
- Read-only investigation — do NOT implement directly in source code
- Zero regression on existing router tests (`tests/test_llm_router.py`, `tests/test_adversarial_m3_stt_llm.py`)
- Explicit safety confirmation for destructive/system power actions (`requires_confirmation=True` / dry-run)

## Current Parent
- Conversation ID: 88e315c1-4bbc-4194-bae5-c1ca88628303
- Updated: 2026-08-22T16:11:24Z

## Investigation State
- **Explored paths**:
  - `jarvis/llm/router.py`
  - `jarvis/core/app.py`
  - `jarvis/smart_home/home_assistant.py`
  - `jarvis/hardware/reporter.py`
  - `jarvis/plugins/spotify.py`, `jarvis/plugins/shell.py`
  - `tests/test_llm_router.py`
  - `tests/test_adversarial_m3_stt_llm.py`
  - `tests/unit/test_llm_engine.py`
  - `tests/test_empirical_challenger_m3_2.py`
- **Key findings**:
  - Entity extraction required for Smart Home (lights, fans, climate temperature), Spotify (song/artist search query), Reminders (duration/clock time/message), Weather (locations), Hardware (prefix-less).
  - Safety confirmation protocol formulated with `requires_confirmation=True`, `danger_level="critical"`, 2-step confirmation ("xác nhận tắt máy" vs "hủy lệnh"), and safe dry-run execution guard.
  - Zero regression guaranteed by preserving all 8 existing fast-path dictionary keys and signature contracts.
- **Unexplored areas**: None for M2_3 scope.

## Key Decisions Made
- Extended `IntentResult` with `requires_confirmation`, `confirmation_prompt`, `response_text`, and `danger_level`.
- Designed `get_natural_response()` covering all 7+ action categories in polite conversational Vietnamese.
- Full blueprint delivered to `d:/Software GitCode/JARVIS/.agents/explorer_m2_3/report.md`.

## Artifact Index
- `d:/Software GitCode/JARVIS/.agents/explorer_m2_3/DISPATCH.md` — User/parent dispatch record
- `d:/Software GitCode/JARVIS/.agents/explorer_m2_3/BRIEFING.md` — Situational awareness
- `d:/Software GitCode/JARVIS/.agents/explorer_m2_3/progress.md` — Liveness & progress tracking
- `d:/Software GitCode/JARVIS/.agents/explorer_m2_3/report.md` — Final blueprint report
- `d:/Software GitCode/JARVIS/.agents/explorer_m2_3/handoff.md` — 5-component handoff
