# Suggest Performance, Load, and Rollout Plan

## Summary

Этот документ фиксирует поэтапный план улучшения производительности и устойчивости
`/api/ai/suggest` без потери качества генерации.

Фокус плана:

- сначала включить наблюдаемость и измеримость;
- затем оптимизировать retrieval и OpenAI path;
- после этого добавить защиту от перегрузки;
- в конце подтвердить результат нагрузочными и mixed-load тестами;
- выкатывать изменения через feature flags и staged rollout.

План рассчитан так, чтобы по нему можно было идти отдельными PR без необходимости
переделывать всю систему одним большим релизом.

## Goals

- улучшить `p95/p99` для `/api/ai/suggest` относительно baseline;
- уменьшить стоимость и CPU-нагрузку на один suggest-запрос;
- ограничить collateral impact на не-AI endpoints;
- получить воспроизводимые local/CI load reports;
- обеспечить безопасный rollback и поэтапное включение.

## Non-Goals

- полный редизайн AI-layer;
- миграция на новый transport/provider;
- немедленное включение hard budget enforcement;
- изменение продуктовой логики жалоб вне suggest/retrieval-пути.

## Execution Order

1. Observability first
2. Suggest retrieval optimization
3. Two-stage retrieval ranking
4. Route-level concurrency safety
5. OpenAI path strategy
6. Load test suite
7. Parallel load execution
8. Real server telemetry during load
9. Mixed-load impact test
10. Rollout & safety

## 0) Observability First

### Objective

Сначала получить точную картину по времени и стоимости каждого этапа suggest-пути.

### Planned changes

- Добавить в `web/ogp_web/services/ai_service.py` для `suggest_text_details`:
  - `retrieval_ms`
  - `openai_ms`
  - `total_suggest_ms`
- Расширить `build_suggest_metrics_meta(...)` новыми полями.
- Убедиться, что `metrics_store.log_ai_generation(...)` сохраняет эти значения.
- Обновить `web/ogp_web/storage/admin_metrics_store.py`:
  - aggregation по новым полям;
  - `p50` и `p95` для новых timing metrics.
- Добавить/обновить тесты на backward-compatible aggregation.

### Expected outcome

- точная декомпозиция latency;
- отдельная видимость retrieval и OpenAI time;
- база для дальнейших оптимизаций и сравнений.

## 1) Suggest Retrieval Optimization

### Objective

Сделать retrieval-query легче и дешевле без потери качества generation prompt.

### Planned changes

- Ввести `build_suggest_retrieval_query_light(payload)` в `web/ogp_web/services/ai_service.py`.
- Использовать lightweight query только внутри `_build_suggest_law_context`.
- Полный `raw_desc` сохранить в generation prompt path.
- Добавить deterministic unit tests:
  - формат query;
  - truncation behavior;
  - отсутствие влияния на основной generation input.

### Expected outcome

- меньше лишнего текста в retrieval;
- дешевле и быстрее ranking path;
- полный user input остаётся доступным для финальной генерации.

## 2) Two-Stage Retrieval Ranking

### Objective

Уменьшить стоимость ranking без ухудшения релевантности.

### Planned changes

- Рефакторинг `_select_law_qa_chunks`:
  - cheap prefilter;
  - expensive rerank только на `top-K`.
- Для `profile='suggest'` возвращать максимум `3-4` chunks.
- Добавить internal counters/telemetry:
  - prefilter size;
  - rerank size;
  - rerank duration;
  - selected chunk count.
- Добавить relevance-regression tests на representative fixtures.

### Expected outcome

- меньше токенов и меньше CPU на suggest retrieval;
- релевантный context остаётся точным;
- появляется измеримость качества retrieval.

## 3) Route-Level Concurrency Safety

### Objective

Сделать `/api/ai/suggest` устойчивым под burst-load.

### Planned changes

- В `web/ogp_web/routes/complaint.py` выполнять suggest generation через `run_in_threadpool`.
- Добавить per-instance concurrency limiter:
  - semaphore или token bucket.
- При перегрузке возвращать контролируемый `429`:
  - с понятным `Retry-After`.
- Добавить API tests:
  - normal flow;
  - overload flow.

### Expected outcome

- предсказуемое поведение под нагрузкой;
- отсутствие каскадной деградации worker-а;
- понятная клиентская реакция на overload.

## 4) OpenAI Path Strategy

### Objective

Сделать path policy управляемой и измеримой.

### Planned changes

- Добавить routing policy в `shared/ogp_ai.py`:
  - `proxy_only`
  - `proxy_first`
  - `direct_first`
- Логировать:
  - `attempt_path`
  - `attempt_duration_ms`
- Для failing-first branch задать более низкий connect timeout.
- Добавить tests:
  - route-policy behavior;
  - fallback correctness.

### Expected outcome

- понятная стратегия попыток;
- меньше времени на заведомо плохой first path;
- полная диагностика fallback-поведения.

## 5) Load Test Suite

### Objective

Сделать воспроизводимые нагрузочные сценарии для suggest-flow.

### Planned changes

- Добавить сценарии в `load/` для `/api/ai/suggest`:
  - `k6` и/или `Locust`.
- Ввести payload profiles:
  - `short`
  - `mid`
  - `long`
- Ввести concurrency tiers:
  - `5`
  - `10`
  - `30`
  - `50+`
- Сохранять артефакты в:
  - `artifacts/load/<run_id>/<profile>/`
- Генерировать:
  - `summary.json`
  - `report.md`

### Expected outcome

- единый baseline для suggest;
- воспроизводимые local/CI отчёты;
- сравнимые результаты до и после оптимизаций.

## 6) Parallel Load Execution

### Objective

Проверять систему не только в одиночных сценариях, но и в параллельных профилях.

### Planned changes

- Добавить `scripts/run_parallel_load.py`.
- Запускать несколько profiles одновременно.
- Собирать consolidated report по всем профилям.
- Добавить `--fail-on-sla` для CI/manual gate.
- Описать usage examples для local и CI.

### Expected outcome

- единый запуск для performance gate;
- меньше ручной сборки отчётов;
- быстрый ответ на вопрос "выдерживает ли система смешанную нагрузку".

## 7) Real Server Telemetry During Load

### Objective

Во время нагрузочных тестов видеть не только app metrics, но и системную нагрузку сервера.

### Planned changes

- Добавить `scripts/server_sampler.py`:
  - CPU
  - RAM
  - load average
  - I/O
  - network
  - process count
- Делать sampling каждые `1-2s`.
- Сохранять `server_metrics.csv` рядом с load artifacts.
- Добавить корреляцию server metrics с app telemetry в итоговом отчёте.

### Expected outcome

- видно, где bottleneck: app, DB, network или host;
- можно оценивать CPU cost per suggest request;
- проще принимать решения по rollout.

## 8) Mixed-Load Impact Test

### Objective

Проверить, не ломает ли heavy suggest обычных пользователей.

### Planned changes

- Добавить mixed scenario:
  - Group A: heavy `/api/ai/suggest`
  - Group B: обычные endpoints (`/api/complaint-draft`, `/api/profile`, etc.)
- Зафиксировать baseline Group B без Group A.
- Прогнать mixed load и посчитать `p95/p99 delta` для Group B.
- Добавить SLA gate по collateral impact:
  - например `p95 growth <= 25%`.

### Expected outcome

- понятное влияние AI-нагрузки на обычные сценарии;
- возможность блокировать rollout при неприемлемом impact.

## 9) Rollout & Safety

### Objective

Включать изменения безопасно и обратимо.

### Planned changes

- Feature-flag для:
  - lightweight retrieval;
  - two-stage ranking.
- Rollout strategy:
  - telemetry-only first;
  - затем optimization;
  - затем limits.
- Валидация через:
  - single-profile reports;
  - parallel-profile reports;
  - mixed-load reports.
- Документировать:
  - rollback steps;
  - operational thresholds.

### Expected outcome

- контролируемое включение;
- быстрый rollback;
- минимальный риск сломать suggest под реальной нагрузкой.

## Test Matrix

### Unit

- timing meta
- suggest retrieval query builder
- two-stage ranking behavior
- route-policy fallback
- budget/telemetry compatibility

### API

- normal suggest flow
- overloaded suggest flow (`429 + Retry-After`)
- feature-flag compatibility

### Performance

- single-profile load
- parallel-profile load
- mixed-load impact

## Feature Flags

Рекомендуемые флаги:

- `suggest_retrieval_light_query`
- `suggest_two_stage_ranking`
- `suggest_route_concurrency_guard`
- `suggest_openai_route_policy`
- `suggest_load_gate_enforced`

## Artifacts

Структура артефактов:

```text
artifacts/
  load/
    <run_id>/
      <profile>/
        summary.json
        report.md
        server_metrics.csv
      consolidated/
        summary.json
        report.md
```

## Rollback Plan

- отключить feature flags для lightweight retrieval и two-stage ranking;
- вернуть route policy к безопасному baseline;
- отключить concurrency limit enforcement, если он создаёт ложные 429;
- использовать последний стабильный load baseline как reference.

## Risks

- Недостаточная observability до включения optimizations приведёт к ложным выводам.
- Слишком агрессивный lightweight retrieval ухудшит юридическую точность.
- Two-stage ranking может потерять редкие, но релевантные нормы, если prefilter слишком узкий.
- Concurrency limiter может быть слишком жёстким и ухудшить UX даже без реальной перегрузки.
- Path policy может дать ложную оптимизацию, если timeout настроен слишком резко.
- Load tests без real server telemetry дадут неполную картину bottleneck-ов.
- Mixed-load без baseline приведёт к спорным выводам про collateral impact.

## Definition of Done

- `/api/ai/suggest p95/p99` улучшены относительно baseline.
- CPU usage per suggest request снижен или стабилизирован.
- Mixed-load показывает приемлемое влияние на non-AI endpoints.
- Есть воспроизводимые local и CI reports.
- Rollback steps и thresholds задокументированы.

