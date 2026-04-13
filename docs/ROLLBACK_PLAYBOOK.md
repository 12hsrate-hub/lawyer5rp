# Rollback Playbook (Feature Flags)

## Global trigger thresholds

Rollback (or step down rollout mode) when one or more hold for 10+ minutes:

- `error_rate` increases by > 2x baseline or exceeds 5%
- `generation_latency p95` exceeds baseline by > 40%
- `validation_fail_rate` exceeds baseline by > 30%
- `async_queue_lag p95` exceeds 60s for affected job type

Immediate action order:

1. move flag from `all` -> `beta` or `internal`
2. if still unstable, move to `off`
3. keep compatibility/legacy path active
4. verify smoke checks and regression metrics

---

## `cases_v1`

- **Trigger:** case API errors, case-backed history/read failures.
- **Immediate action:** set `cases_v1=off` (or `internal`).
- **Fallback:** route reads/writes through compatibility path.
- **Data safety:** do not delete existing `cases`; keep document history intact.
- **Post-checks:** `/api/generate`, history snapshot APIs, case read smoke.
- **Owner:** backend platform lead; escalation to release owner.

## `documents_v2`

- **Trigger:** document version write/read errors, bridge failures.
- **Immediate action:** set `documents_v2=off`.
- **Fallback:** serve primary responses from legacy flow.
- **Data safety:** keep `document_versions` created by shadow/dual-write.
- **Post-checks:** `/api/generate`, generated-doc history, version read compatibility.
- **Owner:** backend platform lead.

## `citations_required`

- **Trigger:** spike in blocked responses or external API breakage.
- **Immediate action:** downgrade enforcement `hard -> warn -> off`; if needed `mode=off`.
- **Fallback:** preserve external `/api/generate` and `/api/ai/law-qa-test` behavior.
- **Data safety:** keep stored citations and retrieval links.
- **Post-checks:** citation fail rate, law QA success rate, client compatibility smoke.
- **Owner:** legal AI owner.

## `validation_gate_v1`

- **Trigger:** export/publish blocking spike, false-positive gate failures.
- **Immediate action:** downgrade enforcement `hard -> warn/off`; optionally `mode=off`.
- **Fallback:** emergency mode must not block export/publish.
- **Data safety:** retain validation history for audit.
- **Post-checks:** validation fail trend, export smoke, readiness decision parity.
- **Owner:** quality owner.

## `async_jobs_v1`

- **Trigger:** queue lag growth, worker failures, dead-letter growth.
- **Immediate action:** set `async_jobs_v1=off` and stop unstable enqueue path.
- **Fallback:** route allowed operations to sync/transitional mode.
- **Data safety:** do not drop enqueued jobs; keep job history.
- **Post-checks:** queue drain, worker health, async-to-sync fallback smoke.
- **Owner:** platform ops.

---

## Operational verification after rollback

- Check `error_rate`, `generation_latency`, `validation_fail_rate`, `async_queue_lag` by flag/cohort/server.
- Run API smoke:
  - `/api/generate`
  - `/api/ai/law-qa-test`
  - `/api/generated-documents/history`
- Confirm compatibility layers are active and stable.
