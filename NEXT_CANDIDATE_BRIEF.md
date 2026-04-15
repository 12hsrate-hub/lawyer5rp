# NEXT_CANDIDATE_BRIEF.md

Status: `H.1 draft`  
Date: `2026-04-15`

## Selected next bounded candidate

- Server: `blackberry`
- Procedure / document kind: `rehab`
- Rollout class: `same-server / second-procedure`

## Why this candidate is recommended first

`blackberry + rehab` is the safest post-pilot expansion because it reuses the same runtime server, law bundle, admin workspace, and publication/governance path that were already stabilized for the pilot `blackberry + complaint`.

This keeps the next rollout bounded in one dimension:
- new procedure
- same server
- same operational owners
- same rollback surface

That is materially safer than choosing:
- a second server with incomplete law/runtime readiness such as `strawberry`
- or a broad multi-scenario activation wave

## Rejected alternatives for H.1

### 1. `strawberry + complaint`

Not recommended for the first post-pilot candidate.

Reason:
- the runtime/admin surface already showed readiness gaps (`active_law_version_missing`)
- server readiness would introduce a second migration dimension at once:
  - new server
  - pilot-template reuse

### 2. multi-server complaint rollout

Not recommended.

Reason:
- violates the bounded-candidate rule established in `Phase G`
- makes rollback and evidence attribution noisier

## Why `rehab` is a good fit

Evidence from the current repo:
- `blackberry.bootstrap.json` already contains template/document mappings for `rehab`
- the server navigation and runtime config already expose both `complaint` and `rehab`
- admin catalog workflow already seeds and publishes procedure/template content on the same server scope
- rollout, provenance, async, and admin explainability surfaces are already stabilized for the `blackberry` environment

## Rollout gate for this candidate

Before any activation change for `blackberry + rehab`, all of the following must be true:

1. `Pilot rollout` remains `hold` or `go`, but not `rollback`, for the original pilot.
2. `Observation sign-off` for the pilot has no unmet critical criteria.
3. `Legacy cleanup backlog` stays informational only; no cleanup wave is coupled to the rehab rollout.
4. `rehab` has published:
- procedure version
- template version
- validation rule version
- law/runtime linkage equivalent to the complaint pilot standard
5. provenance for generated `rehab` output must expose:
- config lineage
- retrieval / citations when applicable
- validation summary
- artifact/export context
6. rollback remains per-scenario and does not widen to multi-server rollback.

## Initial H.1 execution slice

The first executable slice for `H.1` should be:

- map current `rehab` runtime/config path against the pilot `complaint` path
- identify missing published content or provenance gaps
- produce a short `rehab rollout gate checklist`

This stays planning-first and does not activate the candidate yet.

