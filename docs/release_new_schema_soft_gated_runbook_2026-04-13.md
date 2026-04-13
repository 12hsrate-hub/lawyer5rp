# Release Runbook: новая схема в production (soft-gated)

Дата запуска: 2026-04-13  
Primary repo: `https://github.com/12hsrate-hub/lawyer5rp`  
Production host: `root@89.111.153.129`  
Deploy checkout: `/srv/lawyer5rp-deploy/repo`  
Runtime dir: `/srv/lawyer5rp.ru`

---

## 0) Роли и ответственность на сегодня

- **Ops/DBA**: T1, T3, T6, T9, T10
- **Backend**: T3, T4, T5, T6, T7, T8, T10
- **QA**: T5, T7, T8
- **Tech Lead/Owner**: T2, T8 (финальный GO/NO-GO)

---

## 1) Подготовка релиза (до деплоя)

## T1. Backup/snapshot production БД (P0)

### Цель
Снять backup/snapshot перед изменениями схемы и зафиксировать артефакт в релиз-ноте.

### Команды (пример для PostgreSQL dump)

> Выполнять на production-сервере под доступами DBA.

```bash
# Пример переменных (заменить на реальные)
export PGHOST=127.0.0.1
export PGPORT=5432
export PGDATABASE=lawyer5rp
export PGUSER=postgres

TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_DIR=/srv/lawyer5rp-deploy/backups
BACKUP_FILE="$BACKUP_DIR/lawyer5rp_${TS}.dump"

mkdir -p "$BACKUP_DIR"
pg_dump -Fc -f "$BACKUP_FILE" "$PGDATABASE"

# Минимальная проверка целостности/метаданных
ls -lh "$BACKUP_FILE"
pg_restore -l "$BACKUP_FILE" | head -n 20
sha256sum "$BACKUP_FILE"
```

### DoD
- [ ] Backup/snapshot создан.
- [ ] Проверен факт чтения метаданных (`pg_restore -l`) и размер файла (`ls -lh`).
- [ ] В релиз-ноте сохранены: `backup_id/filename`, UTC-время, checksum.

## T2. Release freeze (P0)

### Действия
- [ ] Заморозить feature-разработку до завершения T8.
- [ ] Разрешить только bugfix для текущего запуска.
- [ ] Уведомить команду в общем канале (шаблон ниже).

### Шаблон сообщения в канал

```text
[RELEASE FREEZE] Введён freeze на релиз новой схемы (soft-gated), дата: 2026-04-13.
Разрешены только bugfix-изменения, связанные с данным запуском.
Ответственный TL: <name>. Окно GO/NO-GO после полного smoke и gate-review.
```

---

## 2) Деплой и миграции

## T3. Деплой кода новой схемы (флаги OFF) (P0)

### Команды

```bash
# На production-сервере
set -euo pipefail

git -C /srv/lawyer5rp-deploy/repo fetch origin
git -C /srv/lawyer5rp-deploy/repo checkout main
git -C /srv/lawyer5rp-deploy/repo reset --hard origin/main

bash /srv/lawyer5rp-deploy/repo/scripts/deploy_from_checkout.sh
curl -sS http://127.0.0.1:8000/health
```

### Контроль
- [ ] Код выкачен в production из GitHub-backed checkout.
- [ ] Сервисы поднялись.
- [ ] Все новые флаги остаются **OFF** перед миграциями и smoke.

## T4. Применить миграции 0006–0011 (P0)

### Пакет миграций
- `0006_cases_core.sql`
- `0007_generation_bridge.sql`
- `0008_validation_domain.sql`
- `0009_attachments_exports.sql`
- `0010_content_workflow.sql`
- `0011_async_jobs.sql`

### Выполнение
- [ ] Прогнать стандартный migration runner проекта в production-окружении.
- [ ] Проверить, что каждая миграция из диапазона 0006–0011 отмечена как applied.
- [ ] Перезапустить приложение/воркер после миграций.
- [ ] Проверить startup-логи на критические ошибки.

### DoD
- [ ] Все миграции 0006–0011 применены без ошибок.
- [ ] Приложение стартует после миграций.
- [ ] В startup-логах нет критичных ошибок.

---

## 3) Smoke при OFF-флагах

## T5. Базовый smoke (OFF) (P0)

### Чек-лист
- [ ] Старт приложения.
- [ ] Auth.
- [ ] `/api/generate`.
- [ ] Admin UI.
- [ ] Worker/queue стартует.

### DoD
- [ ] Все пункты зелёные, критических регрессий нет.

---

## 4) Включение feature flags (строго по порядку)

## T6. Пошаговое включение (P0)

### Порядок (не менять)
1. `cases_v1 = on`
2. `documents_v2 = on`
3. `async_jobs_v1 = on`
4. `validation_gate_v1 = on` (**warn mode**)
5. `citations_required = on` (**warn mode**)

### Журнал изменений флагов

| UTC time | Actor | Flag | Old | New | Mode/Notes |
|---|---|---|---|---|---|
| _YYYY-MM-DDThh:mm:ssZ_ | _name_ | `cases_v1` | off | on | |
| _YYYY-MM-DDThh:mm:ssZ_ | _name_ | `documents_v2` | off | on | |
| _YYYY-MM-DDThh:mm:ssZ_ | _name_ | `async_jobs_v1` | off | on | |
| _YYYY-MM-DDThh:mm:ssZ_ | _name_ | `validation_gate_v1` | off | on | warn |
| _YYYY-MM-DDThh:mm:ssZ_ | _name_ | `citations_required` | off | on | warn |

### DoD
- [ ] Флаги включены в требуемом порядке.
- [ ] Для каждого шага зафиксированы кто/когда/значение.

---

## 5) Smoke после включения

## T7. E2E smoke (ON) (P0)

### Обязательные сценарии
- [ ] create case
- [ ] add document
- [ ] generate
- [ ] history read
- [ ] law qa
- [ ] export
- [ ] async export/job
- [ ] content publish
- [ ] 1 retry/idempotency кейс
- [ ] 1 cross-server negative кейс

### DoD
- [ ] Все обязательные сценарии проходят.

---

## 6) GO/NO-GO gate

## T8. Release gate-review (P0)

### GO-критерии
- [ ] Миграции стабильны.
- [ ] Case/document/version flow жив.
- [ ] Контракт `/api/generate` не сломан.
- [ ] Generate пишет `document_version` + snapshot.
- [ ] Citations сохраняются (happy path).
- [ ] Создаётся validation run.
- [ ] Минимум 1 async job проходит полный цикл.
- [ ] Publish/rollback работают.

### NO-GO триггеры
- [ ] Нестабильные миграции.
- [ ] Сломан `/api/generate`.
- [ ] `document_versions` не append-only.
- [ ] Cross-server leakage.
- [ ] Очередь не обрабатывает jobs.
- [ ] Publish/rollback ломают state.

### Decision log

```text
[GO/NO-GO] Date(UTC): <...>
Decision: GO | NO-GO
Participants: TL=<...>, QA=<...>, Ops=<...>, Backend=<...>
Evidence: smoke report, logs, metrics links
Notes: <...>
```

### DoD
- [ ] Письменно зафиксировано решение GO/NO-GO.

---

## 7) Пост-релизный мониторинг (в день запуска)

## T9. Усиленный мониторинг (P1)

### Метрики под наблюдением
- [ ] error rate
- [ ] generation latency
- [ ] validation fail rate
- [ ] async queue lag
- [ ] DLQ count
- [ ] export failures
- [ ] fallback-to-legacy usage

### DoD
- [ ] Метрики выведены на дашборд/в канал.
- [ ] Назначен on-call и подтверждён в канале.

---

## 8) План быстрого отката (флаги)

## T10. Flag rollback playbook (P0)

### Порядок rollback
1. `citations_required -> off`
2. `validation_gate_v1 -> off`
3. `async_jobs_v1 -> off`
4. `documents_v2 -> off` (если требуется)

### После rollback повторить smoke
- [ ] generate
- [ ] history
- [ ] export
- [ ] admin

### DoD
- [ ] Playbook размещён в доступном месте.
- [ ] Ответственный за rollback подтверждён.

---

## Релиз-нота (минимальный шаблон)

```text
Release: New schema soft-gated rollout
Date UTC: <...>
Commit SHA: <...>
Backup: <backup filename/id>, checksum=<sha256>, time=<UTC>
Migration status: 0006..0011 applied=<yes/no>
Flags timeline: <link/table>
Smoke OFF: <pass/fail + ссылка>
Smoke ON: <pass/fail + ссылка>
Gate decision: GO/NO-GO
On-call: <name>
Rollback owner: <name>
```
