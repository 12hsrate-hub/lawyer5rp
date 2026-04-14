# AI Service Refactoring Boundaries (2026-04-13)

## Цель
Сделать `web/ogp_web/services/ai_service.py` тонким фасадом и зафиксировать стабильные интерфейсы между шагами пайплайна.

## Новые границы ответственности

- `web/ogp_web/services/ai_pipeline/transport.py`
  - OpenAI transport/client factory.
  - Retry policy контракт (`RetryPolicy`).
- `web/ogp_web/services/ai_pipeline/orchestration.py`
  - Оркестрация публичных входных точек: law_qa, suggest, principal scan.
  - Контракты зависимостей через dataclass (`LawQaOrchestrationDeps`, `SuggestOrchestrationDeps`, `PrincipalScanDeps`).
- `web/ogp_web/services/ai_pipeline/guardrails.py`
  - Пост-обработка suggest-текста и ограничение контекста.
- `web/ogp_web/services/ai_pipeline/telemetry_meta.py`
  - Формирование telemetry/budget meta для suggest/law_qa.
- `web/ogp_web/services/ai_pipeline/interfaces.py`
  - Стабильные типизированные интерфейсы (dataclass + protocol) между этапами, включая result DTO (`LawQaAnswerResult`, `SuggestTextResult`, `SuggestContextBuildResult`).

## Фасад `ai_service.py`

`ai_service.py` оставлен как API-совместимый фасад:
- делегирует публичные вызовы в новые модули,
- сохраняет обратную совместимость импорта для роутов и существующих тестов,
- агрегирует legacy-утилиты и internal helpers.

## Импорты и интеграция

- `web/ogp_web/routes/complaint.py` продолжает импортировать публичные функции из `ai_service` (без изменения API-контракта).
- Внутренние модули `ai_pipeline/*` используются из фасада и покрываются контрактными тестами.
