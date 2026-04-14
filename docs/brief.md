# BRIEF

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
- `ARCHITECTURE_NOTES.md`
- `MIGRATION_MAP.md`
- `UI_ADMIN_STRUCTURE.md`
- `DATA_MODEL_DRAFT.md`

Но первый и обязательный документ — `PLANS.md`.

## Что считать хорошим результатом
Хороший результат — это такой план, по которому команда реально сможет:
- стартовать миграцию
- не сломать текущую систему
- поэтапно внедрять новую архитектуру
- управлять проектом через понятные вехи и критерии готовности