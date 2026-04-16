# Orange Multi-Server RC Cutover Report

Use this record for the first multi-server RC candidate `orange`.

Status: pre-window ready  
Date: 2026-04-16

## 1. Scope

- Date: `next controlled production window after orange preflight sign-off on main@c1dabbb`
- Operator: `platform-ops`
- Server: `orange`
- Procedure scope: `runtime/admin/law/config surfaces only`
- Target mode:
  - `inactive`
  - `active_rc_candidate`
- Selected target mode for this RC window: `active_rc_candidate`

## 2. Preflight result

- Orange checklist reviewed: `pending execution-window confirmation`
- Runtime server record exists: `pending execution-window confirmation`
- Published/bootstrap-backed config path verified: `pre-window regression evidence present; execution-window payload capture pending`
- Warning signals clear: `pending execution-window confirmation`
- Fallback path understood: `yes`
- Rollback path confirmed: `yes — deactivate orange; code-wide fallback to main@4f3b059 via Deploy Production if needed`
- Admin/runtime visibility available: `pre-window regression evidence present; execution-window payload capture pending`
- Law set / law binding / active version evidence available: `pre-window regression evidence present; execution-window payload capture pending`
- Document-builder sample available: `pre-window regression evidence present; activation-window sample pending`

## 3. Evidence

- Dashboard runtime snapshot:
  - paste orange runtime/admin snapshot here during the RC window
- Runtime server health payload:
  - paste `/api/admin/runtime-servers/orange/health` payload here during the RC window
- Document-builder payload sample:
  - paste a representative orange document-builder payload here during the RC window
- Law set / binding / rollback sample:
  - paste orange law evidence here during the RC window
- Deploy workflow:
  - baseline known-good deploy run: `24487474591`
  - RC window deploy run: `pending`
- Health output:
  - baseline: `status=ok` on main@`4f3b059`
  - RC window: `pending`
- Synthetic smoke output:
  - baseline: `pass` on deploy run `24487474591`
  - RC window: `pending`

## 4. Decision

- Decision:
  - `proceed`
  - `hold`
  - `rollback`
- Reason:
- Required follow-up:

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
