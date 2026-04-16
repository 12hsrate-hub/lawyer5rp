# Orange Multi-Server RC Cutover Report

Use this record for the first multi-server RC candidate `orange`.

Status: proceed; accepted staged RC candidate
Date: 2026-04-16

## 1. Scope

- Date: `2026-04-16T05:57:21Z acceptance confirmed on main@3293acf`
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
- Rollback path confirmed: `yes — deactivate orange; code-wide fallback via Deploy Production remains available`
- Admin/runtime visibility available: `yes — operator-readable orange health payload is available pre- and post-activation`
- Law set / law binding / active version evidence available: `yes — projection_run_id=1, materialized law_set_id=4, binding count=2, active law_version_id=247`
- Document-builder sample available: `yes — sample proves orange-owned metadata via orange_appeal_admin_claim`

## 3. Evidence

- Dashboard runtime snapshot:
  - live pilot timestamp: `2026-04-16T05:57:21Z`
  - orange runtime server record: `present`
  - orange activation state: `active`
- Runtime server health payload:
  - accepted result: `highest_completed_state=rollout-ready`, `next_required_state=production-ready`, `resolution_mode=published_pack`, `uses_transitional_fallback=false`, `summary.is_ready=true`
- Document-builder payload sample:
  - live pilot result: verified on accepted runtime state
  - summary:
    - `server = orange`
    - `document_type = court_claim`
    - `choice_sets.claim_kind_by_court_type.appeal[0].value = orange_appeal_admin_claim`
    - sample shows orange-owned metadata and satisfies RC proof
- Law set / binding / rollback sample:
  - live pilot result:
    - projection run: `1`
    - materialized law set: `4`
    - active law version: `247`
    - `chunk_count = 1`
    - rollback handle: existing admin law-version rollback flow remains available
- Deploy workflow:
  - accepted baseline deploy run: `24494677193`
- Health output:
  - accepted baseline: `status=ok` on main@`3293acf`
- Synthetic smoke output:
  - accepted baseline: `pass` on deploy run `24494677193`

## 4. Decision

- Decision:
  - `proceed`
  - `hold`
  - `rollback`
- Decision: `proceed`
- Reason: `orange` completed the live projection pilot on production, reached active law_version_id=247 with chunk_count=1, and satisfied rollout-ready health requirements`
- Required follow-up: `manual production-ready evidence remains separate; no further runtime blocker is open`

## 5. Observation window

- Window start: `2026-04-16T02:47:53Z`
- Window end: `2026-04-16T05:57:21Z accepted staged RC sign-off`
- Expected checks:
  - runtime health
  - onboarding state consistency
  - law activation / rollback visibility
  - selected-server safety
  - default-server stability
- Observation log reference: `ORANGE_MULTI_SERVER_RC_OBSERVATION_LOG.md`

## 6. Outcome

- Final state:
  - `orange accepted as the first staged multi-server RC candidate`
- Incidents seen:
  - `none blocking; one zero-chunk activation reuse gap was fixed before final acceptance`
- Rollback used:
  - `no`
- Notes:
  - `rollout-ready is confirmed; production-ready remains manual/evidence-based and intentionally narrower than a blanket platform claim`

## 7. Scale-out readiness

- Reusable lessons captured: `yes — projection activation must import canonical parsed runtime snapshot directly and must not reuse zero-chunk activations`
- `ORANGE_MULTI_SERVER_RC_CHECKLIST.md` updated if needed: `yes`
- `LEGACY_DEPRECATION_CANDIDATES.md` reviewed: `not yet`
