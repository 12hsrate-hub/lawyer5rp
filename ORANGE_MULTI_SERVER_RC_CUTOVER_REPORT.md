# Orange Multi-Server RC Cutover Report

Use this record for the first multi-server RC candidate `orange`.

## 1. Scope

- Date:
- Operator:
- Server: `orange`
- Procedure scope: `runtime/admin/law/config surfaces only`
- Target mode:
  - `inactive`
  - `active_rc_candidate`

## 2. Preflight result

- Orange checklist reviewed:
- Runtime server record exists:
- Published/bootstrap-backed config path verified:
- Warning signals clear:
- Fallback path understood:
- Rollback path confirmed:
- Admin/runtime visibility available:
- Law set / law binding / active version evidence available:
- Document-builder sample available:

## 3. Evidence

- Dashboard runtime snapshot:
- Runtime server health payload:
- Document-builder payload sample:
- Law set / binding / rollback sample:
- Deploy workflow:
- Health output:
- Synthetic smoke output:

## 4. Decision

- Decision:
  - `proceed`
  - `hold`
  - `rollback`
- Reason:
- Required follow-up:

## 5. Observation window

- Window start:
- Window end:
- Expected checks:
  - runtime health
  - onboarding state consistency
  - law activation / rollback visibility
  - selected-server safety
  - default-server stability

## 6. Outcome

- Final state:
- Incidents seen:
- Rollback used:
- Notes:

## 7. Scale-out readiness

- Reusable lessons captured:
- `ORANGE_MULTI_SERVER_RC_CHECKLIST.md` updated if needed:
- `LEGACY_DEPRECATION_CANDIDATES.md` reviewed:
