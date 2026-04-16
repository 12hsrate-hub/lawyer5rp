# Orange Multi-Server RC Cutover Report

Use this record for the first multi-server RC candidate `orange`.

Status: hold after live preflight  
Date: 2026-04-16

## 1. Scope

- Date: `next controlled production window after orange preflight sign-off on main@4b6049e`
- Operator: `platform-ops`
- Server: `orange`
- Procedure scope: `runtime/admin/law/config surfaces only`
- Target mode:
  - `inactive`
  - `active_rc_candidate`
- Selected target mode for this RC window: `active_rc_candidate`

## 2. Preflight result

- Orange checklist reviewed: `yes — live preflight executed at 2026-04-16T02:12:19Z`
- Runtime server record exists: `no — orange is missing from production runtime server storage`
- Published/bootstrap-backed config path verified: `no — cannot verify live runtime path while orange runtime server record is missing`
- Warning signals clear: `no — live preflight found missing runtime server, missing law evidence, and missing orange-owned document-builder metadata`
- Fallback path understood: `yes`
- Rollback path confirmed: `yes — deactivate orange; code-wide fallback to main@4b6049e via Deploy Production if needed`
- Admin/runtime visibility available: `no — /api/admin/runtime-servers/orange/health has no live server payload because orange is absent`
- Law set / law binding / active version evidence available: `no — live preflight found zero orange law sets, zero bindings, and no active law version`
- Document-builder sample available: `yes — sample captured, but it shows only base court_claim fallback and does not prove orange-owned metadata`

## 3. Evidence

- Dashboard runtime snapshot:
  - live preflight timestamp: `2026-04-16T02:12:19Z`
  - orange runtime server record: `missing`
  - orange activation state: `not available because server record is missing`
- Runtime server health payload:
  - live preflight result: `unavailable`
  - reason: orange runtime server record is missing, so no operator-readable health payload can be captured
- Document-builder payload sample:
  - live preflight result: captured pre-activation
  - summary:
    - `server = orange`
    - `document_type = court_claim`
    - `choice_sets.claim_kind_by_court_type = {}`
    - `validators.required_fields_by_claim_kind = {}`
    - sample does not show orange-owned metadata and therefore does not satisfy RC proof
- Law set / binding / rollback sample:
  - live preflight result:
    - law sets: `[]`
    - bindings: `[]`
    - active law version: `null`
    - rollback handle cannot be evidenced because no orange law runtime state exists
- Deploy workflow:
  - baseline known-good deploy run: `24487921717`
  - RC window deploy run: `pending`
- Health output:
  - baseline: `status=ok` on main@`4b6049e`
  - RC window: `pending`
- Synthetic smoke output:
  - baseline: `pass` on deploy run `24487921717`
  - RC window: `pending`

## 4. Decision

- Decision:
  - `proceed`
  - `hold`
  - `rollback`
- Decision: `hold`
- Reason: `orange` is not present as a production runtime server; no live health payload, no law runtime evidence, and no orange-owned document-builder metadata could be confirmed
- Required follow-up: `create and verify the orange runtime server record, publish/verify its live config-owned metadata, seed law set/binding/active version state, then rerun live preflight before activation`

## 5. Observation window

- Window start: `pending RC activation`
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
