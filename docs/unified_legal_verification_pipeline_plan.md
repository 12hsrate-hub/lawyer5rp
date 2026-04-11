# Unified Server-Aware Legal Verification Pipeline

## Summary

Этот документ фиксирует целевую архитектуру единой логики для:

- генерации описательной части жалобы (пункт 3);
- тестовой функции ответов на вопросы по законодательной базе.

Цель: пользователь вводит только свободный текст, а система автоматически:

- нормализует факты;
- верифицирует их относительно законодательной базы выбранного сервера;
- выбирает формат правовой опоры (`specific` / `generalized`);
- генерирует ответ с валидацией и логированием качества.

## Scope

В рамках этого плана описываются:

- целевая архитектура и этапы внедрения;
- единые правила выбора норм и fallback-режима;
- подход к оптимизации prompt/token/cost;
- план логирования и контура точечных исправлений по неточным ответам;
- план масштабирования на несколько серверов.

Кодовые изменения не являются предметом этого документа.

## Product Requirements

- Пользователь не выбирает маркеры вручную; вводит только описание или вопрос.
- Верификация и retrieval идут строго по `server_code`.
- Если явные основания есть, используется режим `specific` с точными нормами.
- Если маркеры неочевидны, используется режим `generalized` с обобщенным правовым форматом.
- Логика должна быть общей для `complaint_p3` и `law_qa`.

## Shared Pipeline

Для обоих сценариев должен использоваться один общий конвейер:

`normalize -> extract facts -> retrieve -> verify -> decide mode -> build optimized prompt -> generate -> guard validate -> log`

## Server-Aware Law Validation

- Использовать только bundle выбранного сервера.
- Поддерживать белый список норм (`allowed_norms`) по server snapshot.
- Блокировать ссылки на нормы вне текущей законодательной базы.
- Исключить использование внешних правовых знаний вне внутриигровой базы.

## Prompt Optimization and Token Budget

- Ввести budget manager по задачам: `complaint_p3`, `law_qa`.
- Ограничить длину prompt, контекста и итогового вывода.
- Использовать многошаговый режим:
  - дешёвый preprocessing step;
  - основной generation step.
- Логировать:
  - `input_tokens`;
  - `output_tokens`;
  - `total_tokens`;
  - `estimated_cost`.

## Dynamic Legal Basis Width

- Базово использовать 1–2 нормы.
- При высокой уверенности разрешать расширение до 3, редко до 4 норм, если они не дублируют друг друга.
- Проверить через A/B-сравнение баланс качества и стоимости.

## Guard Validation

Guard-слой должен проверять:

- формат ответа;
- появление новых фактов, которых не было во входе;
- валидность ссылок на нормы;
- соответствие норм текущему `server_code`.

Дополнительные правила:

- регенерация допускается только при `guard fail`;
- при неоднозначности должен использоваться controlled fallback.

## Logging and Feedback Loop

### AI Generation Logs

Необходима таблица `ai_generation_logs` с полным следом:

- входных данных;
- выбранного режима;
- retrieval-решений;
- финального prompt budget;
- результата generation;
- результата guard validation.

### AI Response Feedback

Необходима таблица `ai_response_feedback` для фиксации неточностей:

- `wrong_fact`;
- `wrong_law`;
- `unsupported_inference`;
- `bad_format`;
- `other`.

### Operational Loop

- добавить админ-фильтры по типу ошибки, серверу, профилю и confidence;
- добавить экспорт кейсов для точечных правок retrieval/prompt/guard;
- использовать feedback как источник для regression-набора.

## Rollout Plan

### Phase 1. MVP

- preprocessing;
- optimized prompt;
- базовый guard;
- logging.

### Phase 2. Unified Verifier

- общий verifier;
- режимы `specific` / `generalized`;
- shared usage in both flows.

### Phase 3. Feedback Loop

- feedback UI/API;
- quality triage process;
- разбор неточных ответов по категориям.

### Phase 4. Multi-Server Expansion

- конфиги и bundles для новых серверов;
- per-server monitoring;
- контроль качества и стоимости по каждому серверу отдельно.

## Acceptance Criteria

- Оба сценария используют один shared pipeline.
- Нет ссылок на нормы вне законодательной базы выбранного сервера.
- Включены token/cost лимиты и трекинг расходов.
- Есть fallback `generalized`-режима при низкой уверенности.
- Неточности можно просматривать, фильтровать и разбирать через feedback loop.

## Risks

- Недостаточная полнота bundle для отдельных серверов.
- Перекомпрессия prompt может ухудшить точность.
- Излишняя строгость guard может повышать количество регенераций.

## Metrics

- `wrong-law rate`;
- `wrong-fact rate`;
- `guard pass rate`;
- `median token usage`;
- `p95 token usage`;
- `cost per successful response`;
- `MTTR` по исправлению отмеченных неточностей.
