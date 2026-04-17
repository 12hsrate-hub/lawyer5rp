# Docs Index

This directory contains the active documentation set for the repository. Historical materials stay under `docs/archive/` and are intentionally excluded from the active lists below.

## Canonical Planning Inputs

- `../PLANS.md` - main execution plan and canonical phased backlog
- `../MIGRATION_MAP.md` - migration seams, route/service/storage map, and cutover baseline
- `PRODUCT_BRIEF.md` - active product and architecture brief for future planning
- `ARCHITECT_AGENT_GUIDE.md` - active planning rules and architecture guidance for Codex

## Active Product And Technical Docs

- `ADMIN_PANEL.md` - admin IA, entrypoints, and visible terminology
- `AI_INTEGRATION.md` - AI/provenance architecture and traceability baseline
- `ASYNC_JOB_CONTRACTS.md` - async state, retry, and idempotency contracts
- `LEGACY_COMPATIBILITY.md` - legacy seams to preserve and removal candidates
- `FEATURE_FLAGS.md` - canonical feature-flag reference and rollout-state mapping

## Operations And Rollout Docs

- `OPERATIONS_INDEX.md` - primary entrypoint for deploy, rollback, and live-ops docs
- `github_deploy.md` - GitHub-to-server deploy flow
- `postgresql_migrations.md` - PostgreSQL migration flow
- `domain_rollout_su_online.md` - domain and nginx setup
- `AI_QUALITY_COST_RUNBOOK_ADMIN.md` - admin quality/cost operations runbook
- `PUBLISH_RELEASE_CHECKLIST.md` - release checklist for workflow-backed publishes
- `ROLL_OUT.md` - rollout stages and go/no-go rules
- `ROLLBACK_PLAYBOOK.md` - rollback procedure by feature flag
- `RUNBOOK.md` - incident handling for point3 legal mode
- `ASYNC_OPERATIONS_RUNBOOK.md` - async jobs, law rebuild, and exam import ops response
- `ACCEPTANCE_CHECKLIST.md` - release acceptance gates
- `CODEX_RUN_GUIDE.md` - Codex task execution loop
- `exam_scoring_incident_runbook.md` - exam scoring incident response
- `exam_scoring_rollout_gates_and_kpis.md` - exam scoring rollout gates

## Templates

- `templates/COMPATIBILITY_SEAM_NOTE.md` - required seam-note template
- `templates/PILOT_CUTOVER_REPORT_TEMPLATE.md` - pilot cutover report template
- `templates/PILOT_OBSERVATION_LOG_TEMPLATE.md` - pilot observation log template
- `templates/SCALE_OUT_CHECKLIST_TEMPLATE.md` - reusable scale-out checklist

## ADRs, Architecture, And Seams

- `adr/` - accepted ADRs and architectural invariants
- `architecture/` - active architecture documents and proposed designs
- `seams/` - compatibility seam notes and seam-note rules

## Archive

- `archive/YYYY-MM/` - historical plans, superseded docs, audits, rollout packets, and one-off material

## Rules

- There must be only one active root execution plan: `PLANS.md`.
- There must be only one active root migration map: `MIGRATION_MAP.md`.
- Archived materials must not appear as first-class active references.
- If a document is no longer part of current operations or the canonical planning set, archive it instead of leaving it in active navigation.
