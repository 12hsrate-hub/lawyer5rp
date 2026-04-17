# Глубокий технический аудит админ-панели (2026-04-12)

## 1. Краткий итог
- Основной триггер ошибки «Не удалось загрузить данные админ-панели» — падение `GET /api/admin/overview` на backend при любой ошибке в зависимостях (`user_store`, `admin_metrics_store`, `exam_answers_store`) без graceful-degradation.
- UI маскирует причины: в `web/ogp_web/static/pages/admin.js` (`loadAdminOverview`) показывается общий fallback-текст, если `detail` отсутствует/непарсится.
- Есть рассинхрон контрактов для производительности: `renderPerformance` ожидает одну структуру, а `/api/admin/performance` возвращает другую.
- Наблюдаемость недостаточна: нет request/correlation ID, нет гарантированного логирования неотловленных 5xx в `metric_events`, нет admin-ориентированного error explorer.
- Админ-API подвержен перегрузке из-за тяжелого `overview` (полный users+events+exam summary) и регулярного live-refresh.
- Есть риск неожиданных 403/429 для админа из-за роли/квот (middleware считает квоту и для admin API).
- В UI/шаблонах зафиксированы артефакты кодировки (mojibake), осложняющие диагностику и UX.

## 2. Карта потока данных
- Frontend entrypoints:
  - Страница: `GET /admin`, `/admin/dashboard`, `/admin/users` через [admin.py](../../../web/ogp_web/routes/admin.py).
  - Шаблон: [admin.html](../../../web/ogp_web/templates/admin.html).
  - JS: [admin.js](../../../web/ogp_web/static/pages/admin.js).
- Hooks/stores/clients:
  - Клиент: `window.OGPWeb.apiFetch` и `parsePayload` в [common.js](../../../web/ogp_web/static/shared/common.js).
  - Главная загрузка: `loadAdminOverview()` + `loadAdminPerformance()` в `admin.js`.
- Backend endpoints:
  - `GET /api/admin/overview` (ядро данных UI).
  - `GET /api/admin/performance` (блок производительности).
  - Дополнительно: `GET /api/admin/dashboard`, `GET /api/admin/users`, `GET /api/admin/ai-pipeline`, CSV, user actions.
- Services/queries:
  - `admin_overview()` -> `metrics_store.get_overview(...)` + `exam_store.count_entries_needing_scores/list_entries/list_entries_with_failed_scores` + `user_store.list_users(...)`.
  - `get_overview()` в [admin_metrics_store.py](../../../web/ogp_web/storage/admin_metrics_store.py) тянет totals/top_endpoints/recent_events/user_metrics/ai_exam_stats.
- External dependencies:
  - DB backend (`PostgresBackend`).
  - (косвенно) rate limit + quota middleware в [app.py](../../../web/ogp_web/app.py).
- Где именно ломается цепочка:
  - `require_admin_user` (401/403).
  - middleware quota block (429 на `/api/*` включая admin).
  - исключения внутри `admin_overview` dependency chain -> 500.
  - фронт: generic fallback при непарсимом/non-JSON ответе (502/504/proxy HTML).

## 3. Найденные проблемы

### Проблема 1: Общая ошибка в UI скрывает первопричину
- Критичность: high
- Где находится: [admin.js](../../../web/ogp_web/static/pages/admin.js), `loadAdminOverview()`, сообщение `"Не удалось загрузить данные админ-панели."`
- Симптом: пользователь видит один и тот же текст при разных реальных причинах.
- Причина: fallback используется и для fetch exception, и для непарсимых payload, и для пустого `detail`.
- Последствие: сложно отличить 403/429/500/502/timeout, растет MTTR.
- Как исправить:
  - В UI разделить состояния: `auth_error`, `quota_error`, `server_error`, `network_error`, `upstream_error`.
  - Показывать `status`, `request_id`, `endpoint` в expandable error details.

### Проблема 2: Нет graceful-degradation у `/api/admin/overview`
- Критичность: critical
- Где находится: [admin.py](../../../web/ogp_web/routes/admin.py), `admin_overview`
- Симптом: падение одной подсистемы валит всю админ-панель.
- Причина: endpoint собирает единый payload из нескольких storage-источников без частичного fallback.
- Последствие: total outage админки вместо частичной деградации.
- Как исправить:
  - Обернуть подблоки (`users`, `events`, `exam_import`) в независимые `try/except` и возвращать `partial_errors[]`.

### Проблема 3: Контракт `performance` рассинхронизирован
- Критичность: high
- Где находится:
  - Front: `renderPerformance` в [admin.js](../../../web/ogp_web/static/pages/admin.js)
  - Back: `admin_performance` в [admin.py](../../../web/ogp_web/routes/admin.py), `get_performance_overview` в [admin_metrics_store.py](../../../web/ogp_web/storage/admin_metrics_store.py)
- Симптом: пустые/некорректные значения в блоке производительности.
- Причина: фронт читает `payload.latency/rates/top_endpoints/totals.failed_requests`, backend отдает `p50_ms/p95_ms/endpoint_overview/error_count/total_api_requests`.
- Последствие: недостоверная операционная картина.
- Как исправить:
  - Унифицировать DTO (единая схема + тест контракта API->UI).

### Проблема 4: 5xx не гарантированно попадают в metric_events
- Критичность: high
- Где находится: middleware `capture_admin_metrics` в [app.py](../../../web/ogp_web/app.py)
- Симптом: в админке нет события, хотя пользователь видел падение.
- Причина: при exception до формирования response middleware re-raise делает без `log_event`.
- Последствие: нет трассы для разбора аварии.
- Как исправить:
  - Логировать отдельный `event_type=api_exception` с path/method/error_class/request_id даже при re-raise.

### Проблема 5: Риск 429 для админа из-за квоты API
- Критичность: medium
- Где находится: quota logic в `capture_admin_metrics` ([app.py](../../../web/ogp_web/app.py))
- Симптом: админ-панель «не грузится» при исчерпанной квоте администратора.
- Причина: квота проверяется для всех `/api/*` кроме `/api/auth/*`.
- Последствие: блокируются и админские операции диагностики.
- Как исправить:
  - Exempt admin endpoints или admin role от quota throttle (или отдельный admin quota policy).

### Проблема 6: Роль admin завязана на env/fallback username
- Критичность: medium
- Где находится: `is_admin_user` / `require_admin_user` в [auth_service.py](../../../web/ogp_web/services/auth_service.py)
- Симптом: внезапные 403 для реального админа после смены окружения/аккаунта.
- Причина: при пустых env работает fallback `username == "12345"`.
- Последствие: ложные отказа доступа.
- Как исправить:
  - Обязательная конфигурация `OGP_WEB_ADMIN_USERNAMES`, health warning если пусто.

### Проблема 7: Тяжелый synchronous payload + live refresh
- Критичность: high
- Где находится:
  - Front polling в [admin.js](../../../web/ogp_web/static/pages/admin.js) (`setInterval` + `Promise.all`)
  - Backend `admin_overview` в [admin.py](../../../web/ogp_web/routes/admin.py)
- Симптом: просадки/таймауты под ростом users/events.
- Причина: нет декомпозиции по lightweight endpoints, нет server-side caching overview.
- Последствие: нестабильная загрузка, особенно через прокси/туннели.
- Как исправить:
  - Разделить overview на секции с lazy-load и независимыми retries.
  - Для тяжелых блоков использовать агрегаты/снимки.

### Проблема 8: Отсутствуют correlation/request IDs
- Критичность: high
- Где находится: глобально (`app.py`, admin endpoints, frontend error handling)
- Симптом: невозможно быстро сопоставить UI-ошибку с backend-записью.
- Причина: нет единого request_id в response/header/log/meta.
- Последствие: долгий ручной разбор.
- Как исправить:
  - Ввести `X-Request-ID`, писать его в `metric_events.meta` и показывать в UI ошибок.

### Проблема 9: Неполное покрытие тестами error-path для admin panel
- Критичность: medium
- Где находится: [tests/test_web_api.py](../../../tests/test_web_api.py), [tests/test_web_pages.py](../../../tests/test_web_pages.py)
- Симптом: регрессии контракта UI<->API проходят незамеченными.
- Причина: есть smoke/permission тесты, но нет end-to-end тестов на:
  - `/api/admin/performance` schema compatibility с UI,
  - частичную деградацию overview,
  - non-JSON error bodies (proxy 502/504).
- Последствие: повторяющиеся «панель не грузится».
- Как исправить:
  - Контрактные тесты response-schema + UI state mapping tests.

### Проблема 10: Кодировочные артефакты в админ UI
- Критичность: medium
- Где находится: [admin.html](../../../web/ogp_web/templates/admin.html), [admin.js](../../../web/ogp_web/static/pages/admin.js), [auth_service.py](../../../web/ogp_web/services/auth_service.py), [README_WEB.md](../../../web/README_WEB.md)
- Симптом: `Р...`-строки вместо нормального русского текста.
- Причина: часть файлов сохранена в неверной кодировке/конвертирована с mojibake.
- Последствие: плохой UX, неоднозначные ошибки, риск неверной интерпретации команд.
- Как исправить:
  - Нормализовать UTF-8 без BOM на всем web слое, добавить pre-commit check.

### Проблема 11: `/api/admin/dashboard` не участвует в реальном рендере страницы
- Критичность: low
- Где находится: endpoint в [admin.py](../../../web/ogp_web/routes/admin.py), текущий JS в [admin.js](../../../web/ogp_web/static/pages/admin.js)
- Симптом: есть endpoint с KPI/alerts, но UI продолжает жить от legacy `/overview`.
- Причина: миграция не завершена.
- Последствие: двойная логика, риск дрейфа контрактов.
- Как исправить:
  - Либо перевести UI на `/dashboard` + modular APIs, либо удалить неиспользуемый слой.

## 4. Что сейчас уже выводится в админку
- Сводка totals: users, api requests, complaints, rehabs, AI usage, exam scoring counters, bytes/resource units, avg api duration, events_last_24h.
- Performance-блок (но частично с некорректными полями из-за mismatch).
- Top endpoints (из overview).
- Exam import operational block: pending scores, last sync/score, recent/failed entries, recent failures.
- Пользователи: фильтры, сортировки, bulk actions, модалка управления.
- События: общий журнал + отдельный аудит admin-событий.
- CSV export users/events.
- Live refresh controls.

## 5. Что отсутствует, но нужно добавить
- Полноценный `Error Explorer` (group by exception, endpoint, service, first_seen/last_seen, count).
- Billing/Cost dashboard:
  - total cost, cost/day-week-month, by model/user/feature/endpoint.
  - top expensive requests + anomaly spikes.
- Latency dashboards:
  - p50/p95/p99 по endpoint и по feature.
  - разбивка total latency на retrieval/openai/db/serialization.
- Надежность интеграций:
  - openai/smtp/db status history, деградация по времени, flapping alerts.
- Query diagnostics:
  - slow SQL table, N+1 detector hints, cache hit/miss.
- Job monitor:
  - фоновые задачи с queue depth, running/failed/retry, ETA.
- Drill-down страницы:
  - `/admin/errors`, `/admin/costs`, `/admin/performance`, `/admin/jobs`, `/admin/users/{id}/usage`.

## 6. Что сейчас неудобно и почему
- Данных много, но нет явной иерархии “критично сейчас / аналитика / аудит”.
- Нет удобного drill-down из KPI в первопричину.
- Нет фильтров по server_code/model/feature в основных блоках.
- Нет time-range control (1h/24h/7d/30d) на всех ключевых виджетах.
- Один общий error-host скрывает параллельные причины (overview/performance/actions).
- Нет раздельных состояний loading/error/empty per widget.

## 7. Метрики и графики, которые обязательно нужны
- Error rate (общий, по endpoint, по feature).
  - Зачем: раннее обнаружение деградации.
  - Данные: `metric_events.status_code`, `path`, `event_type`.
- Latency p50/p95/p99 (общий и per endpoint/model/flow).
  - Зачем: SLA и поиск узких мест.
  - Данные: `duration_ms`, `meta.latency_ms`, `meta.retrieval_ms`, `meta.openai_ms`.
- Throughput/RPS + concurrency.
  - Зачем: capacity planning.
  - Данные: `api_request` windowed counts.
- Cost & tokens.
  - Зачем: контроль расходов API.
  - Данные: `ai_generation.meta.input_tokens/output_tokens/total_tokens/estimated_cost_usd/model`.
- Reliability of integrations.
  - Зачем: быстро понять, где внешний сбой.
  - Данные: health checks + exception logs.
- User usage/risk.
  - Зачем: abuse/rate anomalies.
  - Данные: per-user API counts/errors/quota/risk flags.

## 8. Самые дорогие и самые долгие процессы
- Вероятно самые дорогие:
  - AI генерации (`/api/ai/suggest`, law_qa, exam scoring через LLM) — токены и external API.
  - Массовые проверки импортов экзамена (batch + retry).
- Вероятно самые долгие:
  - `GET /api/admin/overview` при большом объеме users/events.
  - AI pipeline paths с retrieval + LLM вызовами.
  - Любые операции с холодным/нагруженным DB backend.
- Вероятные узкие места:
  - Монолитный overview endpoint.
  - Отсутствие кэша/агрегатов для тяжелых админских срезов.
  - Polling без backpressure/abort/retry-policy.

## 9. Что нужно вынести в админку вместо команд
- Проверка sync local/main/prod + текущий deploy commit.
- Статус фоновых задач (exam import/bulk actions/AI batch jobs).
- Перезапуск безопасных джобов (retry failed batch/single).
- Проверка “open PR / merged / deployed version” (read-only status board).
- Просмотр healthcheck истории, а не только текущего `/health`.
- Диагностика quota/rate-limit блокировок по пользователям.

## 10. План доработок
### Критично
- Разделить `/api/admin/overview` на независимые блоки с partial errors.
- Устранить mismatch контракта `performance` (backend DTO <-> frontend renderer).
- Ввести request_id/correlation_id end-to-end.
- Гарантированно логировать `api_exception` при неотловленных 5xx.
- Убрать общий fallback-текст без статуса; добавить typed error UI.

### Важно
- Ввести cost/token dashboards и drill-down.
- Добавить time-range + filters (server/model/feature/user).
- Перевести live-refresh на widget-level и адаптивный backoff.
- Добавить контрактные тесты admin API + UI mapping.

### Желательно
- Завершить декомпозицию admin frontend (`admin-api`, `admin-state`, `admin-renderers`).
- Нормализовать кодировки во всех web-файлах.
- Убрать/консолидировать дублирующие legacy endpoints.

## 11. Точки изменения в коде
- Первоочередные:
  - [web/ogp_web/routes/admin.py](../../../web/ogp_web/routes/admin.py)
  - [web/ogp_web/storage/admin_metrics_store.py](../../../web/ogp_web/storage/admin_metrics_store.py)
  - [web/ogp_web/app.py](../../../web/ogp_web/app.py)
  - [web/ogp_web/static/pages/admin.js](../../../web/ogp_web/static/pages/admin.js)
  - [web/ogp_web/static/shared/common.js](../../../web/ogp_web/static/shared/common.js)
- По доступам/ролям:
  - [web/ogp_web/services/auth_service.py](../../../web/ogp_web/services/auth_service.py)
- По тестам:
  - [tests/test_web_api.py](../../../tests/test_web_api.py)
  - [tests/test_web_pages.py](../../../tests/test_web_pages.py)
  - [tests/test_web_storage.py](../../../tests/test_web_storage.py)
