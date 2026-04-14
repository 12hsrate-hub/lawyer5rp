# Docs Index

This directory now keeps only active operational and developer-facing docs.

## Keep In `docs/`

- `brief.md` - active product/architecture brief for future planning
- `agents.md` - active planning rules and architecture guidance
- `OPERATIONS_INDEX.md` - primary entrypoint for deploy/run/rollback docs
- `RUNBOOK.md` - incident handling for point3 legal mode
- `ROLL_OUT.md` - rollout stages and go/no-go rules
- `ROLLBACK_PLAYBOOK.md` - rollback procedure by feature flag
- `github_deploy.md` - GitHub-to-server deploy flow
- `postgresql_migrations.md` - PostgreSQL migration flow
- `domain_rollout_su_online.md` - domain and nginx setup
- `MODEL_POLICY_SLO.md` - policy, KPI, and SLO targets
- `AI_QUALITY_COST_RUNBOOK_ADMIN.md` - admin quality/cost runbook
- `FEATURE_FLAGS.md` - active feature-flag reference
- `ACCEPTANCE_CHECKLIST.md` - release acceptance gates
- `IMPLEMENTATION_PLAN.md` - still-active execution plan referenced by task tracking
- `CODEX_RUN_GUIDE.md` - execution guide for Codex-driven task work
- `exam_scoring_incident_runbook.md` - exam scoring incident response
- `exam_scoring_rollout_gates_and_kpis.md` - exam scoring rollout gates

## Keep In `docs/adr/`

- ADRs and active architectural invariants only

## Keep In `docs/archive/YYYY-MM/`

- completed plans
- one-off briefs that are no longer current
- audits
- historical blueprints
- temporary hardening/backlog notes that are no longer current source-of-truth

Files moved out of active docs in this cleanup live in `docs/archive/2026-04/`.

## Rules

- If a document is not part of current operations or current execution, archive it.
- Active docs should point to active docs or ADRs, not to archived planning material.
- Do not keep duplicate briefs or scratch notes in the root `docs/` directory unless they are explicitly designated as active planning sources.
