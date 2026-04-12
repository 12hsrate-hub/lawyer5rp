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
