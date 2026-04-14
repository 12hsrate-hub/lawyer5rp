# Docs Index

Этот каталог теперь разделен на 4 зоны:

- `docs/` — только живые документы, которые используются в текущей разработке и эксплуатации.
- `docs/adr/` — архитектурные решения (ADR), действующие инварианты и правила.
- `docs/archive/YYYY-MM/` — исторические планы, аудиты и разовые runbook-файлы.
- `examples/` и `artifacts/` — примеры кода и выгрузки данных, которые не являются operational docs.

## Active Docs (Keep Here)

- `github_deploy.md`
- `postgresql_migrations.md`
- `RUNBOOK.md`
- `ROLLBACK_PLAYBOOK.md`
- `FEATURE_FLAGS.md`
- `MODEL_POLICY_SLO.md`
- `AI_QUALITY_COST_RUNBOOK_ADMIN.md`
- `ACCEPTANCE_CHECKLIST.md`
- `IMPLEMENTATION_PLAN.md`
- `unified_legal_verification_pipeline_plan.md`
- `code_quality_audit_2026-04-14.md`
- `domain_rollout_su_online.md`
- `exam_scoring_incident_runbook.md`
- `exam_scoring_rollout_gates_and_kpis.md`
- `utf8_hardening_plan.md`
- `ROLL_OUT.md`
- `CODEX_RUN_GUIDE.md`

## Archive Policy

- Любой документ с датой в имени, который больше не ведет текущую работу, переносится в `docs/archive/YYYY-MM/`.
- Архивные файлы не удаляем сразу: сначала перенос, затем удаление в отдельной чистке при необходимости.
- Ссылки из активных инструкций должны вести только на `docs/` или `docs/adr/`.

## Data and Examples Policy

- JSON/CSV выгрузки и прочие артефакты храним в `artifacts/`.
- Технические шаблоны и стартовые заготовки храним в `examples/`.
- В `docs/` не добавляем бинарники и сырьевые выгрузки.
