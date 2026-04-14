# Operations Index

Единая точка входа для эксплуатации и релизного контура.

## 1) Деплой и инфраструктура (source of truth)

- [`github_deploy.md`](./github_deploy.md) — основной GitHub-to-server поток деплоя.
- [`postgresql_migrations.md`](./postgresql_migrations.md) — запуск и порядок миграций.
- [`domain_rollout_su_online.md`](./domain_rollout_su_online.md) — домены и nginx-конфигурация.

## 2) Роллаут и откат

- [`ROLLBACK_PLAYBOOK.md`](./ROLLBACK_PLAYBOOK.md) — триггеры и порядок rollback по feature flags.
- [`RUNBOOK.md`](./RUNBOOK.md) — инцидентный порядок действий для point3 режима.
- [`ROLL_OUT.md`](./ROLL_OUT.md) — этапы промоушена и go/no-go критерии.

## 3) Качество, модельная политика, приемка

- [`MODEL_POLICY_SLO.md`](./MODEL_POLICY_SLO.md) — целевые KPI/SLO и policy actions.
- [`AI_QUALITY_COST_RUNBOOK_ADMIN.md`](./AI_QUALITY_COST_RUNBOOK_ADMIN.md) — ежедневный admin-runbook по качеству/стоимости.
- [`ACCEPTANCE_CHECKLIST.md`](./ACCEPTANCE_CHECKLIST.md) — релизные acceptance-гейты.

## 4) Архитектурные инварианты и планы

- [`adr/ADR-legal-workflow-stage.md`](./adr/ADR-legal-workflow-stage.md) — обязательные инварианты staged workflow.
- [`unified_legal_verification_pipeline_plan.md`](./unified_legal_verification_pipeline_plan.md) — целевая логика pipeline.
- [`performance_optimization_plan.md`](./performance_optimization_plan.md) — performance backlog.
- [`utf8_hardening_plan.md`](./utf8_hardening_plan.md) — UTF-8 hardening.

## 5) Статусные и служебные документы

- [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) — исходный план point3 rollout (использовать вместе с RUNBOOK/ROLL_OUT).
- [`code_quality_audit_2026-04-14.md`](./code_quality_audit_2026-04-14.md) — аудит кода и follow-up.
- [`CODEX_RUN_GUIDE.md`](./CODEX_RUN_GUIDE.md) — процессный гайд для задач через Codex.

## Правило навигации

Если документ пересекается по теме с несколькими файлами, сначала открывать этот индекс и идти по соответствующему разделу.
