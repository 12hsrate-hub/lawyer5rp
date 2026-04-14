# Operations Index

Primary entrypoint for deploy, rollback, and live-operations work.

## Deployment And Infra

- [`github_deploy.md`](./github_deploy.md) - main GitHub-to-server deploy flow
- [`postgresql_migrations.md`](./postgresql_migrations.md) - migration order and checks
- [`domain_rollout_su_online.md`](./domain_rollout_su_online.md) - domain and nginx setup

## Rollout And Rollback

- [`ROLL_OUT.md`](./ROLL_OUT.md) - rollout stages and go/no-go criteria
- [`ROLLBACK_PLAYBOOK.md`](./ROLLBACK_PLAYBOOK.md) - rollback triggers and procedures
- [`RUNBOOK.md`](./RUNBOOK.md) - point3 legal mode incident handling

## Quality And Acceptance

- [`MODEL_POLICY_SLO.md`](./MODEL_POLICY_SLO.md) - KPI, SLO, and policy actions
- [`AI_QUALITY_COST_RUNBOOK_ADMIN.md`](./AI_QUALITY_COST_RUNBOOK_ADMIN.md) - admin review cadence for quality/cost
- [`ACCEPTANCE_CHECKLIST.md`](./ACCEPTANCE_CHECKLIST.md) - release acceptance gates

## Execution Docs

- [`../PLANS.md`](../PLANS.md) - canonical execution plan
- [`../MIGRATION_MAP.md`](../MIGRATION_MAP.md) - canonical migration baseline map
- [`PRODUCT_BRIEF.md`](./PRODUCT_BRIEF.md) - active product/architecture brief
- [`ARCHITECT_AGENT_GUIDE.md`](./ARCHITECT_AGENT_GUIDE.md) - active planning rules for Codex
- [`CODEX_RUN_GUIDE.md`](./CODEX_RUN_GUIDE.md) - Codex task execution loop
- [`adr/ADR-legal-workflow-stage.md`](./adr/ADR-legal-workflow-stage.md) - active staged-workflow invariant

## Exam Scoring

- [`exam_scoring_incident_runbook.md`](./exam_scoring_incident_runbook.md) - incident handling
- [`exam_scoring_rollout_gates_and_kpis.md`](./exam_scoring_rollout_gates_and_kpis.md) - rollout gates and KPIs

## Archive Policy

Historical plans, audits, blueprints, and one-off briefs live under `docs/archive/YYYY-MM/`.
They are retained for context, but they are not the current source-of-truth.
