# Orange Multi-Server RC Final Report

Status: proceed; production-ready accepted within current RC scope  
Date: 2026-04-16  
Server: `orange`

## Source References

### Workflow run IDs

- Orange Projection Pilot: `24494653859`  
  https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24494653859
- Deploy Production (accepted baseline): `24494677193`  
  https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24494677193
- CI Runtime: `24487677670`  
  https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24487677670
- UTF-8 Check: `24487677658`  
  https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24487677658

### PR and commit references

- RC transition package PR: `#307`  
  https://github.com/12hsrate-hub/lawyer5rp/pull/307
- Orange enablement follow-up PRs: `#312`, `#313`
- RC transition merged commit: `c1dabbb451170008cedcb622951a14dd113b1908`
- Known-good deployed baseline commit: `3293acf`

## Checklist Summary

- Candidate accepted as first staged multi-server RC candidate within scoped surfaces (`runtime/admin/law/config`).
- Preconditions were satisfied:
  - `orange` runtime server record exists and remained operator-visible.
  - Config resolution proved through `published_pack` (not neutral fallback) with `uses_transitional_fallback=false`.
  - Law evidence present: approved projection run `1`, materialized law set `4`, active `law_version_id=247`, rollback path retained.
  - Document-builder evidence present: `orange_appeal_admin_claim` confirms orange-owned metadata.
- Exit criteria achieved via successful projection pilot + successful production deploy + successful smoke evidence.
- Explicitly out of scope for this RC: second-server complaint runtime and full platform-wide parity claim.

## Evidence Summary

- Baseline deployment validated on `main@3293acf` with `/health: status=ok`, deploy smoke `passed`, synthetic smoke `pass`.
- Live enablement snapshot (`2026-04-16T05:57:21Z`) confirmed:
  - `orange` is active.
  - Runtime health: `highest_completed_state=rollout-ready`, `next_required_state=production-ready`, `summary.is_ready=true`.
  - Runtime provenance: `resolution_mode=published_pack`, `uses_transitional_fallback=false`.
  - Law runtime: `projection_run_id=1`, `law_set_id=4`, `binding_count=2`, `active_law_version_id=247`, `chunk_count=1`.
  - Document-builder bundle resolves from orange-owned metadata (`orange_appeal_admin_claim`).
- Local/CI validation evidence remained green for targeted runtime/server-config/document-builder/admin runtime API test packs.

## Observation Log

- Observation window: `2026-04-16T02:47:53Z` → `2026-04-16T05:57:21Z`.
- Checkpoint status at final sign-off:
  - Warning signals: `0`
  - Unexpected neutral fallback use: `no`
  - Rollback events: `0`
  - Runtime health: `green`
  - Onboarding state coherence: `rollout-ready` with next required `production-ready`
  - Law activation and rollback visibility: intact (`projection_run_id=1`, `law_set_id=4`, `active_law_version_id=247`, `chunk_count=1`)
  - Selected-server switching safety: no live regression observed
- Incidents during window: no blocking incidents; one zero-chunk activation reuse gap was fixed before final acceptance.

## Cutover Decision

- Final decision: **proceed**.
- Reason:
  - `orange` completed live projection pilot in production.
  - Runtime advanced to `law_version_id=247` with `chunk_count=1`.
  - Rollout-ready health requirements were met with operator-readable provenance.
  - Manual production-ready sign-off completed for the current RC scope.
- Rollback used: `no`.
- Rollback reference (if needed): deactivate `orange` and redeploy previous known-good `main@3293acf` via Deploy Production.
- Remaining follow-up: broader multi-server rollout work remains deferred and is outside this RC acceptance.
