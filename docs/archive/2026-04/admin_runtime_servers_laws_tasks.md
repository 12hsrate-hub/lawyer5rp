# План задач: админка серверов и законов (UI-first)

## Этап 1 — Runtime серверы через UI (MVP)

- [x] Добавить API для runtime серверов:
  - `GET /api/admin/runtime-servers`
  - `POST /api/admin/runtime-servers`
  - `PUT /api/admin/runtime-servers/{server_code}`
  - `POST /api/admin/runtime-servers/{server_code}/activate`
  - `POST /api/admin/runtime-servers/{server_code}/deactivate`
- [x] Добавить схему валидации payload для создания/редактирования сервера.
- [x] Добавить UI-блок в админке (вкладка `servers`) для:
  - просмотра runtime серверов,
  - добавления сервера,
  - изменения названия,
  - активации/деактивации.
- [x] Добавить e2e/API тесты на новые endpoints.

## Этап 2 — Связь сервер ↔ закон (явная модель)

- [ ] Спроектировать и внедрить таблицы:
  - `law_sets`
  - `law_set_items`
  - `law_source_registry`
- [ ] Реализовать API для управления наборами законов по серверу.
- [ ] Добавить UI выбора активного law set для сервера.
- [ ] Поддержать publish/review workflow для law set изменений.

## Этап 3 — Источники законов в UI

- [ ] Добавить раздел-справочник источников (`law_source_registry`) в админке.
- [ ] Позволить выбирать источник из справочника при добавлении закона.
- [ ] Сохранить текущую совместимость с `law_sources_manifest`.

## Этап 4 — Эксплуатация и безопасность

- [ ] Ограничить права доступа:
  - `manage_runtime_servers`
  - `manage_law_sets`
  - `publish_law_sets`
- [ ] Добавить dry-run перед rebuild.
- [ ] Добавить rollback до предыдущей law version в UI.
- [ ] Добавить мониторинг длительности rebuild и ошибок.
