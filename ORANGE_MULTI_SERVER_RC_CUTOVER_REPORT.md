# Orange Multi-Server RC Cutover Report

Use this record for the first multi-server RC candidate `orange`.

Status: proceed; RC window open  
Date: 2026-04-16

## 1. Scope

- Date: `2026-04-16T02:47:53Z RC window opened on main@916811f`
- Operator: `platform-ops`
- Server: `orange`
- Procedure scope: `runtime/admin/law/config surfaces only`
- Target mode:
  - `inactive`
  - `active_rc_candidate`
- Selected target mode for this RC window: `active_rc_candidate`

## 2. Preflight result

- Orange checklist reviewed: `yes — live preflight rerun executed at 2026-04-16T02:47:53Z`
- Runtime server record exists: `yes — orange exists in production runtime server storage`
- Published/bootstrap-backed config path verified: `yes — orange resolves through published_pack in live runtime`
- Warning signals clear: `yes — no live pre-activation blockers remained at rerun time`
- Fallback path understood: `yes`
- Rollback path confirmed: `yes — deactivate orange; code-wide fallback to main@916811f via Deploy Production if needed`
- Admin/runtime visibility available: `yes — operator-readable orange health payload is available pre- and post-activation`
- Law set / law binding / active version evidence available: `yes — published law_set_id=3, binding count=1, active law_version_id=203`
- Document-builder sample available: `yes — sample proves orange-owned metadata via orange_appeal_admin_claim`

## 3. Evidence

- Dashboard runtime snapshot:
  - live preflight rerun timestamp: `2026-04-16T02:47:53Z`
  - orange runtime server record: `present`
  - orange activation state before GO: `inactive`
  - orange activation state after GO: `active`
- Runtime server health payload:
  - pre-activation result: `highest_completed_state=workflow-ready`, `next_required_state=rollout-ready`, `resolution_mode=published_pack`, `uses_transitional_fallback=false`
  - post-activation Checkpoint 1: `highest_completed_state=workflow-ready`, `next_required_state=rollout-ready`, `activation=active`
- Document-builder payload sample:
  - live preflight result: captured pre-activation and verified again at Checkpoint 1
  - summary:
    - `server = orange`
    - `document_type = court_claim`
    - `choice_sets.claim_kind_by_court_type.appeal[0].value = orange_appeal_admin_claim`
    - sample shows orange-owned metadata and satisfies RC proof
- Law set / binding / rollback sample:
  - live preflight result:
    - law sets: `[3]`
    - bindings: `1`
    - active law version: `203`
    - rollback handle: existing admin law-version rollback flow remains available
- Deploy workflow:
  - baseline known-good deploy run: `24489154809`
  - RC window deploy run: `not needed; activation opened RC window on current deploy baseline`
- Health output:
  - baseline: `status=ok` on main@`916811f`
  - RC window: `status=ok` at `2026-04-16T02:48:44Z`
- Synthetic smoke output:
  - baseline: `pass` on deploy run `24489154809`
  - RC window: `inherited green baseline from deploy run 24489154809`

## 4. Decision

- Decision:
  - `proceed`
  - `hold`
  - `rollback`
- Decision: `proceed`
- Reason: `orange` passed the live preflight rerun while inactive and met the pre-activation GO gate for opening the RC window`
- Required follow-up: `continue observation checkpoint cadence; verify rollout-ready evidence after activation without expanding scope`

## 5. Observation window

- Window start: `2026-04-16T02:47:53Z`
- Window end: `pending RC sign-off`
- Expected checks:
  - runtime health
  - onboarding state consistency
  - law activation / rollback visibility
  - selected-server safety
  - default-server stability
- Observation log reference: `ORANGE_MULTI_SERVER_RC_OBSERVATION_LOG.md`

## 6. Outcome

- Final state:
- Incidents seen:
- Rollback used:
- Notes:

## 7. Scale-out readiness

- Reusable lessons captured: `pending RC outcome`
- `ORANGE_MULTI_SERVER_RC_CHECKLIST.md` updated if needed: `pending RC outcome`
- `LEGACY_DEPRECATION_CANDIDATES.md` reviewed: `pending RC outcome`
