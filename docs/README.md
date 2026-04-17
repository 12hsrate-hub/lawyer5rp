# Docs Index

This directory keeps active operational docs plus two active planning-source documents.

## Canonical Planning Inputs

- `../PLANS.md` - main execution plan and canonical phased backlog
- `../MIGRATION_MAP.md` - migration seams, route/service/storage map, and cutover baseline
- `PRODUCT_BRIEF.md` - active product and architecture brief for future planning
- `ARCHITECT_AGENT_GUIDE.md` - active planning rules and architecture guidance for Codex

## Operational Docs

- `OPERATIONS_INDEX.md` - primary entrypoint for deploy/run/rollback docs
- `RUNBOOK.md` - incident handling for point3 legal mode
- `ASYNC_OPERATIONS_RUNBOOK.md` - async jobs, law rebuild, and exam import ops response
- `ROLL_OUT.md` - rollout stages and go/no-go rules
- `ROLLBACK_PLAYBOOK.md` - rollback procedure by feature flag
- `github_deploy.md` - GitHub-to-server deploy flow
- `postgresql_migrations.md` - PostgreSQL migration flow
- `domain_rollout_su_online.md` - domain and nginx setup
- `MODEL_POLICY_SLO.md` - policy, KPI, and SLO targets
- `AI_QUALITY_COST_RUNBOOK_ADMIN.md` - admin quality/cost runbook
- `FEATURE_FLAGS.md` - active feature-flag reference
- `ACCEPTANCE_CHECKLIST.md` - release acceptance gates
- `CODEX_RUN_GUIDE.md` - execution guide for Codex-driven task work
- `../RETRY_IDEMPOTENCY_MATRIX.md` - current retry/idempotency contract and gaps
- `exam_scoring_incident_runbook.md` - exam scoring incident response
- `exam_scoring_rollout_gates_and_kpis.md` - exam scoring rollout gates

## ADR And Archive Rules

- `docs/adr/` - ADRs and active architectural invariants only
- `docs/archive/YYYY-MM/` - historical plans, superseded planning docs, audits, and one-off materials

Files moved out of active planning in this cleanup live in `docs/archive/2026-04/`.

## Rules

- There must be only one active root execution plan: `PLANS.md`.
- There must be only one active root migration map: `MIGRATION_MAP.md`.
- Product/architecture prompt docs live in `docs/PRODUCT_BRIEF.md` and `docs/ARCHITECT_AGENT_GUIDE.md`.
- If a document is no longer part of current operations or the canonical planning set, archive it.
- In `docs/archive/`, use relative links that resolve from the current file's folder (e.g., links from `docs/archive/YYYY-MM/*.md` to docs root should start with `../../`).
