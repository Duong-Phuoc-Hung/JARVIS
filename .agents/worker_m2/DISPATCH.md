## 2026-08-24T02:38:07Z
You are the Worker implementing Milestone M2: Sandboxed Self-Coding & Persistent Skill Library for the JARVIS Autonomous Agentic Superpower upgrade.
Your assigned working directory is `d:/Software GitCode/JARVIS/.agents/worker_m2`.
You MUST read `d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md`, `d:/Software GitCode/JARVIS/PROJECT.md`, and `d:/Software GitCode/JARVIS/.agents/explorer_survey_2/handoff.md`.

Exclusively Owned Files:
- `jarvis/sandbox/__init__.py`
- `jarvis/sandbox/interpreter.py`
- `jarvis/sandbox/validator.py`
- `jarvis/sandbox/artifacts.py`
- `jarvis/skills/__init__.py`
- `jarvis/skills/models.py`
- `jarvis/skills/registry.py`
- `jarvis/skills/synthesizer.py`

Key Specifications:
1. Code Interpreter Sandbox:
   - ASTCodeValidator: Static code safety check, parses AST, forbids dangerous modules (`ctypes`, `win32api`, direct low-level socket tampering), permits scientific stack (`pandas`, `openpyxl`, `matplotlib`, `numpy`, `requests`, `bs4`, `csv`, `json`, etc.).
   - CodeInterpreterSandbox: Subprocess execution in isolated scratch directory (`workspace/sandbox/run_<id>/`), timeout bounds (e.g. 15s default), memory/process cleanup, stdout/stderr capture. Supports Python and safe PowerShell scripts.
   - ArtifactManager: Compares directory before and after execution, detects generated files (.png, .xlsx, .csv, .pdf), indexes them as `ArtifactInfo` with mime types and sizes.
2. Persistent Skill Library:
   - SkillMetadata, SkillDefinition, SkillExecutionResult dataclasses.
   - DynamicSkillSynthesizer: Takes successful code from sandbox, formats into standard Python module with docstrings and schema, saves under `jarvis/skills/<skill_name>/` or `jarvis/skills/<skill_name>.py` with `metadata.json`.
   - SkillRegistry: Auto-discovers skills from `jarvis/skills/`, dynamically imports entrypoints (`importlib`), validates entrypoint `execute(**kwargs)`, registers into `ActionDispatcher`, tracks invocation counts, success rates, and latency metrics.
