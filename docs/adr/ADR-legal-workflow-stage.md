# ADR: Legal Workflow Stage Invariants and Migration Policy

- Status: Accepted
- Date: 2026-04-13
- Owners: Legal AI / Backend

## Context

Для поэтапного развития единого server-aware legal pipeline (complaint generation + law QA) нужны стабильные архитектурные инварианты и единая политика миграций. Без формализации правил высок риск скрытых зависимостей на default server, drift между API и данными, а также опасных schema-изменений без окна совместимости.

## Decision

### 1) Scope rules for new entities

Все новые сущности (domain models, persistent records, config objects, service contracts) должны быть:

- **server-scoped по умолчанию** (явный `server_code`/`server_id` в контракте), или
- **explicit global** с документированным обоснованием, почему сущность не зависит от сервера.

Неявные “общие” сущности без явной маркировки scope запрещены.

### 2) Append-only invariants for versioned domain records

Следующие сущности фиксируются как **immutable / append-only**:

- `LawVersion`
- `TemplateVersion`
- `DocumentVersion`
- `ValidationRun`

Правила:

- обновление существующей версии через destructive update запрещено;
- изменения публикуются добавлением новой версии;
- ссылки на исторические версии должны оставаться валидными и воспроизводимыми.

### 3) API invariant: no hidden default server for new APIs

Для всех новых API endpoints запрещено поведение “скрытый server по умолчанию”.

Обязательные варианты:

- либо сервер передаётся явно параметром/контекстом;
- либо endpoint относится к explicit global contract и это отражено в документации.

### 4) Compatibility layer status for legacy generation endpoints

Эндпоинты:

- `/api/generate`
- `/api/complaint-draft`

фиксируются как **compatibility layer** над новым staged workflow. Новая функциональность должна развиваться через stage-aware contracts, а эти маршруты обязаны сохранять обратную совместимость на период миграции.

## Legal Workflow Stages

- **Stage 1 (MVP Foundation):** preprocessing, optimized prompt, basic guard, базовое логирование.
- **Stage 2 (Unified Verifier):** общий verifier, единый decision mode (`specific`/`generalized`), shared usage в complaint + law QA.
- **Stage 3 (Feedback Loop):** feedback API/UI, triage process, категоризация неточностей.
- **Stage 4 (Multi-Server Expansion):** масштабирование bundles/configs на несколько серверов, per-server monitoring и quality/cost контроль.

## Migration Policy

### Backward-compatible first

Любая миграция в staged workflow делается по принципу **backward-compatible first**:

1. сначала добавляются совместимые schema/API изменения;
2. включается dual-read/dual-write (или shadow-read + dual-write, где уместно);
3. проверяется консистентность данных и метрик;
4. только после подтверждённого окна совместимости допускаются destructive changes.

### Destructive changes gate

Destructive changes (drop/rename columns, hard switch формата, удаление legacy paths) разрешены только после:

- завершённого dual-read/dual-write окна;
- документированного cutover decision;
- наличия rollback-плана и rollback-window.

## Consequences

- Снижается риск cross-server leakage и неявной связанности.
- Повышается воспроизводимость legal outputs за счёт append-only версионности.
- Уменьшается вероятность аварийного релиза за счёт migration gating.
- Legacy API остаются стабильным внешним контрактом до завершения поэтапного cutover.
