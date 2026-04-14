# SCALE_OUT_CHECKLIST_TEMPLATE.md

Status: Phase G reusable template  
Date: 2026-04-15

## Purpose

Use this checklist before adding the next server/procedure after the pilot `blackberry + complaint`.

## Candidate

- Server:
- Procedure:
- Owner:
- Planned rollout window:

## Preconditions

1. Pilot observation window is accepted.
2. Pilot rollback path remains available.
3. No unresolved rollout warning signals remain for the candidate server.
4. Provenance review remains available for the candidate flow.
5. Async/job surfaces are visible and operational for the candidate server.

## Activation path

1. Enable `shadow_compare` for the candidate.
2. Observe drift and operator signals.
3. Confirm route compatibility remains stable.
4. Confirm provenance-critical fields remain visible in snapshots/review context.
5. Only then consider `new_runtime_active`.

## Evidence to attach

- drift report
- fallback count
- rollback visibility
- provenance screenshots or payload examples
- async/job dashboard snapshot

## Exit criteria

- Candidate is accepted for activation, or
- candidate remains in `legacy_only` / `shadow_compare` with a recorded reason.
