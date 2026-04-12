# Point3 Legal Mode Runbook

## Incident Triggers
- elevated retry rate
- cost uplift beyond target
- any factual integrity regression
- degraded legal linkage relevance on high-confidence cases

## First Response
1. Freeze rollout progression.
2. Enable emergency rollback.
3. Force `factual_only`.
4. Capture the failing diff, checks output, and metric snapshot.

## Recovery Steps
1. Confirm rollback flags are active.
2. Re-run `bash scripts/codex_run_checks.sh`.
3. Validate the point3 config and retry policy.
4. Review the latest cases against `tests/fixtures/point3_cases.jsonl`.
5. Resume rollout only after metrics return to target.

## Required Evidence Before Resume
- green point3 checks
- no rollback trigger currently active
- documented root cause
- documented mitigation

## Operational Cadence
1. **Before Sprint 1**: capture baseline for login success rate, `/health`, and key endpoint latency.
2. **After each sprint**: run regression on registration/login, complaint generation, admin review, and exam import.
3. **Before cutover**: confirm rollback procedure and set rollback validity window to 7 days after release.
4. **Governance**: ensure owners are fixed for DB migrations, runtime stores, scripts, tests, and release.
