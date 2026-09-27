# Integration evidence, 2026-09-27

Input and merge SHAs: integration-git.json. Original DOCX rows and hash: docx-requirements.json.
Test console: each RUN.txt; JUnit: RUN.xml; actual command, start UTC, native exit, wall time: RUN.json.

`full-integrated-red` is the fresh pre-remediation integration run, not the historical main run.
Intermediate names containing `green` describe an attempted stage, not a passing verdict: inspect exit_code.
`release-candidate-2-manifest.json` fingerprints the code/test/workflow snapshot used by final-full-2
and final-scoped-2 before the commit was created. `release-candidate-manifest.json` belongs to the earlier
final-unit and interrupted final-full attempt. Metadata HEAD therefore identifies the parent
merge; the manifest identifies tested uncommitted source. Documentation/evidence updates do not change
that source snapshot. Earlier source manifests belong to earlier runs and are retained separately.

run_pytest.py records the actual local Python/environment/arguments; its paths reflect this Windows host.
For another machine, install the project browser/dev dependencies and cryptography, install Chromium,
set JARVIS_RUN_BROWSER_E2E=1, headless/mock audio, and the CI sandbox compatibility flag, then invoke
the recorded pytest arguments with that machine's interpreter and artifact directory.
No live network/provider opt-in is enabled. Mock audio, sandbox compatibility, optional skips and loopback
transport success are not physical audio, Restricted Token isolation, or provider/device runtime evidence.

clock_probe.py is a deliberate background-clock consumer, loaded explicitly with -p clock_probe and this
folder on PYTHONPATH. It reproduced the finite global-monotonic-patch failure without weakening the guard.
Synthetic canary strings in RED logs are test fixtures, not secrets. Real credentials were not used.
Hosted JSON records exact SHA/job results; hosted-test-summary text comes from GitHub job logs.
See docs/eval/t01_t07_integration_20260927.md for criteria, causal findings, task verdicts and resource checklist.
