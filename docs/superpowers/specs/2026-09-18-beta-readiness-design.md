# Beta Readiness Architecture Design

## Goal

Make JARVIS truthful by construction: action outcomes, health, safety, Labs
gating and release evidence must use explicit contracts.  Produce repeatable
acceptance runbooks without treating missing hardware or credentials as a pass.

## Scope and release boundary

This design has two independent streams.  The code stream is complete when its
contracts and regression tests pass.  The acceptance stream is complete only
when a real environment produces an evidence manifest with a passing verdict.
Neither a skipped test nor a fail-closed result closes a runtime acceptance
gate.  Product release remains NO-GO until every required acceptance gate is
passed or formally removed from the release scope.

## Canonical action outcome

`jarvis.core.models.ActionStatus` remains the only action-status enum.  It
retains existing values and adds `BLOCKED` and `UNAVAILABLE` if absent;
`LABS_DISABLED` remains a distinct status.  `ActionResult` is the canonical
public result and exposes `success`, `status`, `code`, `message`, `data`, and
`retryable`.  Legacy `error` and `error_code` remain read-compatible aliases
during migration.

`success` is true only for `ActionStatus.SUCCESS`.  The dispatcher normalizes
legacy handler results through one adapter and never treats an unknown dict,
bare boolean, empty data, or absent handler as success.  Adapters may preserve
the original payload under `data`, but must map configuration, dependency,
timeout and safety failures to the canonical result.

## Canonical health contract

Health is independent from action success.  `HealthStatus` has exactly
`READY`, `LIMITED`, `UNAVAILABLE`, and `ERROR`.  A `HealthResult` includes the
status, a stable code, human-readable message, remediation hint, and probe
metadata.  A backend can return READY only after a side-effect-free real probe;
successful import, object construction, or a configured-looking value is not a
probe.  UI code receives a `HealthResult` and renders it without changing the
status.

## Central safety contract

The dispatcher is the mandatory execution seam for public actions.  A single
`SafetyGateInterceptor` classifies destructive OS, data deletion, update or
rollback, external send (Telegram, Zalo, Discord, email), Home Assistant write,
registry and destructive shell actions.  Non-dangerous query and local utility
actions do not require confirmation.

A confirmation token is bound to an action and canonical payload.  The token
payload contains the action name, SHA-256 of canonical JSON payload, issue and
expiry timestamps, and a random nonce.  It is authenticated with an HMAC using
a server-held secret.  Verification occurs in the dispatcher immediately before
handler execution, rejects action or payload mismatch and expiry, and consumes
the nonce atomically after a successful check.  Planner, webhook, terminal,
voice and communications adapters may request confirmation but cannot execute a
high-risk handler outside this seam.

## Core and Labs

Core contains features with stable regression and acceptance evidence.  Labs is
disabled by default and requires both `labs.enabled=true` and an explicit
feature allowlist entry.  A blocked Labs invocation returns an `ActionResult`
with `success=false`, `status=LABS_DISABLED`, `code=LABS_FEATURE_DISABLED`, and
`retryable=false`.  Browser CDP and packet capture remain Labs until their
separate runtime gates pass.  No empty-config, async, instance-method, or
fallback path may bypass the guard.

## Evidence manifest

All runtime runners emit one versioned JSON manifest before generating a human
Markdown report.  The schema is:

```json
{
  "schema_version": 1,
  "runner_id": "tshark_v2",
  "timestamp": "2026-09-18T00:00:00Z",
  "verdict": "UNAVAILABLE",
  "verdict_code": "KERNEL_DRIVER_PENDING",
  "host": {"os": "Windows", "redacted_id": "..."},
  "evidence_path": "docs/eval/tshark_live_evidence_v2.md",
  "gates_closed": [],
  "gates_pending": ["tshark_live_capture"],
  "details": {}
}
```

The allowed verdicts are `PASS`, `NOT_CONFIGURED`, `UNAVAILABLE`, `BLOCKED`,
`ERROR`, and `TIMEOUT`.  Runners must distinguish absent credentials from an
unreachable configured service and from a configured service that times out.
Manifests must redact secrets and personally identifying content.  The beta
report reads manifests and never turns a non-PASS verdict into an acceptance
pass.

## Governance and acceptance

The credential registry records connector, test-account reference, primary
owner, backup owner, storage location category, CI identity separation and
rotation review date; it contains no secret value.  The risk register records
P0/P1 issue, owner, workaround, acceptance authority and expiry date.

Acceptance runbooks cover TShark, Browser, IMAP, Telegram, Discord, Zalo, Home
Assistant, clean-machine installer/updater/rollback, ten core workflows and the
voice protocol.  The ten-workflow gate needs per-workflow evidence, aggregate
success >=95%, and no individual workflow below 90%.  Human voice testing,
third-party credentials, Npcap/HA, clean VM and production signing are external
dependencies; their runbooks state the needed operator action and retain a
non-PASS verdict until evidence is recorded.

## Constraints

- Follow `AGENTS.md`: fail closed, no fabricated evidence, atomic Windows
  persistence, TDD, documentation and release records.
- Add a failing behavioral test before each production change.
- Preserve public compatibility only through explicit adapters; no silent
  success fallback.
- Separate code-complete, fail-closed, runtime-evidenced, pilot and production
  verdicts in every report.
