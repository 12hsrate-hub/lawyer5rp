# PRODUCT_BRIEF.md

## Название задачи
Построение конкретного плана миграции и внедрения мультисерверной правовой платформы с визуальной администрацией.

## Контекст проекта
Проект — это платформа для нескольких серверов (например, разные серверы GTA5RP-подобной экосистемы), где общая логика работы похожа, но содержимое серверов может сильно отличаться.

От сервера к серверу могут различаться:
- ББ-коды
- виды судопроизводств / обращений / процессов
- названия сущностей
- формы заполнения
- правила проверки
- шаблоны документов
- наборы законов
- дополнительные функции и ограничения

При этом общая пользовательская логика должна быть единой:
1. пользователь выбирает сервер
2. выбирает вид процесса / обращения
3. заполняет форму
4. проходит проверку
5. получает результат
6. сохраняет / редактирует / экспортирует документ

## Главная цель
Нужно не просто улучшить код, а построить конкретный, поэтапный и безопасный план перехода к новой архитектуре, где:
- всё управление идёт через понятную визуальную администрацию
- нетехнический администратор может управлять системой без кода
- серверные различия описываются через управляемую конфигурацию, а не через хаотичные if/else
- есть versioning, draft, publish, rollback, audit
- существует единый экспортируемый master manifest
- документация и названия понятны обычному пользователю

## Что есть сейчас
Текущий проект примерно состоит из:
- FastAPI backend
- PostgreSQL
- legacy routes / services
- complaint / cases / validation / document builder
- admin logic
- imports / jobs
- law-related modules
- exports / attachments
- server-aware logic в ограниченном виде

Пример старой архитектуры:
- routes: pages.py, auth.py, profile.py, complaint.py, cases.py, validation.py, exam_import.py, jobs.py, document_builder.py, attachments.py, exports.py, admin.py
- services: auth_service, profile_service, complaint_service, generation_orchestrator, legal_pipeline_service, exam_import_service, law_admin_service, law_bundle_service, attachment_service, export_service, admin_dashboard_service, feature_flags, validation_service
- storage / data: PostgreSQL, local object storage, logs/files
- external: SMTP, AI provider, forum/legal sources

## Архитектурная позиция
Нужен НЕ полный rewrite с нуля, а controlled rebuild / staged migration внутри текущего проекта.

Целевой подход:
- modular monolith
- platform core
- domain-driven decomposition
- visual admin first
- server configs as data
- law registry with versioning
- document workflow engine
- Redis + S3-compatible storage + queue/workers как целевая инфраструктура

## Ключевые принципы
1. Не делать полный rewrite, если можно мигрировать поэтапно.
2. Не добавлять новые server-specific if/else в legacy.
3. Не хардкодить ББ-коды, виды процессов и серверные правила в Python enum и config-файлах без версий.
4. Вся предметная настройка должна управляться через визуальную администрацию.
5. Один общий файл должен существовать как export/import manifest, а не как основной ручной способ управления.
6. Все важные сущности должны поддерживать:
   - draft
   - version
   - publish
   - rollback
   - audit
7. UI и документация должны быть человеко-понятными, без перегруза техническими терминами.

## Что нужно получить от Codex
Нужно получить НЕ реализацию, а сначала конкретный исполняемый план миграции.

Codex должен:
1. Изучить кодовую базу и текущую структуру проекта.
2. Найти и описать текущие архитектурные блоки.
3. Найти узкие места и опасные зависимости.
4. Определить, что можно оставить, а что нужно заменить.
5. Сформировать подробный план миграции по этапам.
6. Разложить работу по модулям, зависимостям и очередности.
7. Отдельно учесть:
   - visual admin
   - human-readable terminology
   - law registry
   - server packs / server configuration
   - procedures / BB catalogs / forms / rules / templates
   - draft/publish/rollback/audit
   - master manifest
   - legacy transition strategy
  
  ## Mandatory risk constraints

The migration plan is incomplete unless it explicitly addresses the following 5 risks.

These are not optional notes.
They must be treated as binding planning constraints.

For EACH mandatory risk, the plan must include:
- why it matters
- where it exists now or is likely to appear in the current repo
- target architectural rule that prevents it
- mitigation steps
- earliest phase where it must be addressed
- acceptance criteria / validation method
- fallback / rollback / containment plan
- whether it is a pre-launch blocker, pre-scale blocker, or later optimization

### Risk 1 — Dual source of truth between legacy logic and new DB-driven workflow
There is a major risk that legacy routes/services and the new configuration-driven runtime become two competing sources of truth.

The plan must:
- define the single source of truth for each migrated scenario
- define when legacy becomes adapter-only
- define compatibility boundaries during transition
- define how drift between old and new behavior is detected
- define cutover criteria

### Risk 2 — Hardcoded server-specific business logic for new servers
There is a major risk that new servers will be added through scattered hardcoded conditionals, one-off enums, or ad hoc logic branches.

The plan must:
- prohibit new server-specific hardcoding as the default approach
- define how server differences are represented through versioned configuration/data
- define where configuration ends and explicit plugin-style extension begins
- define review rules that reject scattered server conditionals

### Risk 3 — Frontend admin complexity collapsing into a monolithic admin UI
There is a major risk that the visual admin becomes one giant tightly coupled module, making future changes expensive and unsafe.

The plan must:
- define admin UI boundaries by domain
- define read-only views first and editable tools later
- define reusable UI patterns and shared component boundaries
- avoid one mega-module or one mega-page approach
- keep human-readable admin UX as a core product requirement

### Risk 4 — Transitional instability of background jobs, imports, exports, retries, and async processing
There is a major risk that migration destabilizes async behavior before core product flows visibly fail.

The plan must:
- treat jobs/imports/exports/retries/workers as a dedicated migration concern
- define idempotency expectations
- define visibility of job states in admin or ops surfaces
- define retry/failure/containment behavior
- define phased migration of background operations instead of silent replacement

### Risk 5 — Incomplete AI / citation provenance for audit and explainability
There is a major risk that generated documents or legal outputs cannot be traced back to the exact legal and configuration context used.

The plan must:
- treat provenance as a required product and audit capability
- define minimum stored provenance fields
- define citation trace storage
- define how provenance appears in admin/audit/review flows
- define acceptance criteria for explainability and traceability

Minimum provenance fields expected in planning:
- server_id
- server configuration version
- procedure version
- template version
- law_set version
- citation / fragment identifiers
- model/provider identifier
- prompt version
- generation timestamp

## Required risk section in PLANS.md

`PLANS.md` must contain a dedicated section named:

## Risk Register and Closure Strategy

That section must include, for each mandatory risk:
- priority
- owner area
- trigger / warning signs
- mitigation
- validation
- closure milestone

Owner area examples:
- backend
- admin UI
- infra
- AI / retrieval
- migration / rollout

## Quality gate for the plan

A valid plan must explicitly include:
- single-source-of-truth transition strategy
- anti-hardcoding strategy for server differences
- modular admin UI strategy
- async/jobs stabilization strategy
- AI/citation provenance strategy
- acceptance criteria for each major phase
- rollback / containment logic for risky migration steps

If any mandatory risk is deferred, the plan must explicitly state:
- why it is deferred
- what keeps the system safe until then
- which later milestone closes it

## Expected discipline from Codex

Do not produce a vague or generic migration plan.
Do not only mention the risks at a high level.
The plan must stage them, constrain them, and define how they will be closed.

## Что особенно важно про предметную модель
Похожей должна быть только машина обработки.
Нельзя унифицировать все серверы в одну жёсткую юридическую модель.

Общим должно быть:
- workflow engine
- document lifecycle
- form processing
- validation framework
- generation pipeline
- export
- audit
- permissions
- publication flow

Серверно-зависимым должно быть:
- виды процессов
- ББ-коды
- формы
- правила
- шаблоны
- наборы законов
- терминология
- capabilities / дополнительные функции

## Что нужно в итоговом плане
Итоговый план должен содержать:
- этапы
- подэтапы
- зависимости
- приоритеты
- артефакты результата
- риски
- критерии приёмки
- что делать первым
- что не делать
- что можно отложить
- порядок миграции legacy -> new core
- какие части делать read-only first
- какие части делать editable later
- какие части делать через admin UI
- какие части должны быть runtime-only
- какие части должны попадать в manifest

## Обязательные отдельные блоки в плане
План обязательно должен отдельно разобрать:
1. Platform Core
2. Visual Admin
3. Server Configurations / Server Packs
4. Procedures / BB catalogs / Forms / Validation Rules / Templates
5. Law Registry / Law Sets / Publications
6. Document Workflow Engine
7. AI / Retrieval / Citations
8. Draft / Publish / Rollback / Audit
9. Redis / Queue / S3 migration
10. Master Manifest
11. Documentation strategy
12. Legacy cleanup strategy

## Ожидаемый целевой результат
Нужно прийти к системе, где:
- администратор может управлять сервером без кода
- пользователь может пройти путь от выбора сервера до генерации документа
- каждый документ знает, по какой версии процесса и закона он создан
- серверные различия не размазаны по коду
- вся настройка проходит через понятную администрацию
- конфигурация экспортируется единым manifest-файлом

## Ограничения
- не делать сразу большой rewrite
- не предлагать микросервисы как первый этап
- не предлагать хранить всё только в одном ручном YAML/JSON
- не переносить всё сразу без эталонного сценария
- не строить систему вокруг технических терминов, непонятных пользователю

## Предпочитаемый стиль ответа
Нужен жёсткий, структурированный, инженерный ответ.
Не нужен общий обзор.
Нужен конкретный план по действиям.

## Ожидаемый output от Codex
Сначала Codex должен создать:
- `PLANS.md`

Опционально затем:
- `MIGRATION_MAP.md`
- `docs/ADMIN_PANEL.md`
- `docs/AI_INTEGRATION.md`

Но первый и обязательный документ — `PLANS.md`.

## Что считать хорошим результатом
Хороший результат — это такой план, по которому команда реально сможет:
- стартовать миграцию
- не сломать текущую систему
- поэтапно внедрять новую архитектуру
- управлять проектом через понятные вехи и критерии готовности
