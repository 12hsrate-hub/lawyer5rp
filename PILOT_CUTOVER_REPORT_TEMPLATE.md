# Pilot Cutover Report Template

Use this template after a pilot rollout decision for `blackberry + complaint`.

## 1. Scope

- Date:
- Operator:
- Server:
- Procedure:
- Target mode:
  - `legacy_only`
  - `shadow_compare`
  - `new_runtime_active`

## 2. Preflight result

- Activation checklist reviewed:
- Shadow compare enabled before cutover:
- Warning signals clear:
- Fallback path confirmed:
- Rollback path confirmed:
- Provenance review available:

## 3. Evidence

- Dashboard release snapshot:
- Drift report:
- Async operations status:
- Provenance review sample:
- Validation sample:

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
  - output drift
  - fallback signals
  - async failures
  - provenance regressions

## 6. Outcome

- Final state:
- Incidents seen:
- Rollback used:
- Notes:

## 7. Scale-out readiness

- Reusable lessons captured:
- `SCALE_OUT_CHECKLIST_TEMPLATE.md` updated if needed:
- `LEGACY_DEPRECATION_CANDIDATES.md` reviewed:
