# Codex Run Guide

## Execution Order
Run tasks strictly in this order:
1. `phase`
2. `priority`
3. `depends_on`

## Required Loop Per Task
After each completed task:
1. Show the diff for files in the task scope.
2. Run:

```sh
bash scripts/codex_run_checks.sh
```

3. Report which `acceptance_targets` are already satisfied and which are still only configured.

## Stop Conditions
- Stop only on a critical blocker that cannot be resolved safely in the current environment.
- If a blocker is environmental, report it clearly and continue only when the task order allows a safe fix.

## Rollback Policy
If any trigger is detected:
- `retry_rate > 0.12`
- `cost_uplift > 0.35`
- any drop in `factual_integrity`

Immediately apply:
- `rollout_legal_mode.emergency_off=true`
- `rollout_legal_mode.force_mode=factual_only`

## Optional Dependency Behavior
If optional tooling is missing, checks must print a clear `skip` or `hint` message instead of failing silently.

## Expected Checks
- Python syntax validation for point3 test files
- Point3 pytest suite
- Admin runtime API pytest subset (`catalog_audit` / `platform_blueprint_status`) when `fastapi` dependency is available
- `git diff --check`
- optional shell lint when available
