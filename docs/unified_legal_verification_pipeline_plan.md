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

## Stable Internal Contract

Чтобы `complaint_p3` и `law_qa` не расходились по логике при дальнейших изменениях, shared pipeline должен иметь стабильный внутренний контракт.

Минимальные сущности контракта:

- `normalized_input`
- `facts`
- `retrieval_result`
- `decision_mode`
- `prompt_budget`
- `generation_result`
- `guard_result`
- `feedback_record`

### normalized_input

Нормализованный пользовательский ввод:

- исходный текст;
- очищенный текст;
- server-aware metadata;
- технические флаги нормализации.

### facts

Результат extract-слоя:

- выделенные факты;
- спорные факты;
- отсутствующие обязательные данные;
- признаки ложной предпосылки;
- confidence по извлечению.

### retrieval_result

Единый результат поиска по законодательной базе:

- `server_code`
- `profile` (`complaint_p3` / `law_qa`)
- `confidence`
- `selected_norms`
- `used_sources`
- `indexed_documents`
- `debug_trace`

`selected_norms` должен быть основным переносимым объектом между retrieval, prompt и guard.

### decision_mode

Единый результат выбора режима:

- `specific`
- `generalized`
- `fallback_reason`

### prompt_budget

Должен фиксировать:

- лимит контекста;
- лимит output;
- число выбранных норм;
- сокращения/компрессии, применённые перед generation.

### generation_result

Должен хранить:

- итоговый ответ;
- модель;
- токены;
- estimated cost;
- число регенераций.

### guard_result

Guard должен возвращать не только `pass/fail`, но и причину:

- `wrong_fact`
- `wrong_law`
- `unsupported_inference`
- `bad_format`
- `out_of_scope`

## Data Handling, Masking and Retention

Так как жалобы и служебные кейсы могут содержать чувствительные данные, логирование не должно копировать пользовательский ввод в сыром виде без ограничений.

### Logging Rules

- Полные тексты логируются только там, где это действительно нужно для quality triage.
- Паспортные данные, телефоны, Discord-теги, email и прямые персональные идентификаторы должны маскироваться или хешироваться.
- В `ai_generation_logs` отдельно хранить:
  - masked payload;
  - raw payload access policy;
  - reason code, почему raw payload сохранён.
- Для law-QA предпочтителен режим без хранения полного текста вопроса, если достаточно нормализованной версии и retrieval trace.

### Retention Policy

- Для `ai_generation_logs` задать ограниченный retention.
- Для `ai_response_feedback` можно хранить дольше, так как это рабочая база для исправлений, но без лишних сырых данных.
- Для raw prompts и raw model outputs желательно задать отдельный TTL и ограничить доступ только админам/разработчикам.

### Access Policy

- Доступ к raw generation logs должен быть ограничен ролью.
- Экспорт из админки должен по умолчанию использовать masked формат.
- Любой full export должен быть явным действием с audit trail.

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

## Practical Nuances and Additional Risks

### 1. Bundle Freshness Drift

Даже при правильной архитектуре качество может падать, если bundle выбранного сервера устарел относительно форума или внутренней редакции законов.

Что может вылезти:

- retrieval выбирает формально релевантные, но уже устаревшие нормы;
- prompt и guard начинают быть консистентными между собой, но неверными относительно текущей редакции.

### 2. Retrieval / Prompt Mismatch

Новый retrieval может стать лучше сам по себе, но при этом ухудшить generation, если prompt продолжит ожидать старую структуру контекста.

Что может вылезти:

- больше выбранных норм, но хуже итоговый ответ;
- правильные статьи, но плохой режим `specific` / `generalized`;
- рост стоимости без реального роста качества.

### 3. Overfitting to BlackBerry

Первые эвристики почти неизбежно будут оптимизированы под один сервер.

Что может вылезти:

- отличная точность на BlackBerry и слабая переносимость;
- alias, эвристики и budget policy начнут зависеть от одной терминологии;
- multi-server rollout окажется дороже, чем ожидалось.

### 4. Guard False Positives

Слишком строгий guard может начать отбрасывать полезные ответы.

Что может вылезти:

- рост числа регенераций;
- деградация latency;
- ухудшение UX при формально более строгой системе.

### 5. Guard False Negatives

Слишком мягкий guard, наоборот, будет пропускать аккуратно сформулированные, но всё же неверные ответы.

Что может вылезти:

- низкий `guard fail rate`, но высокий `wrong-law rate`;
- ложное ощущение качества по внутренним метрикам.

### 6. Cost Visibility Without Cost Control

Сам факт логирования токенов и стоимости ещё не даёт экономии.

Что может вылезти:

- расходы станут наблюдаемыми, но не управляемыми;
- prompt budget будет описан, но не enforced;
- редкие дорогие кейсы будут незаметно раздувать общую стоимость.

### 7. Feedback Loop Noise

Если feedback-система не будет нормализована, она быстро превратится в шум.

Что может вылезти:

- разные люди будут по-разному размечать один и тот же дефект;
- triage станет дорогим и непредсказуемым;
- regression-suite будет строиться на грязных кейсах.

### 8. Migration Complexity

Даже если PR документальный, реальное внедрение затронет несколько уже работающих слоёв:

- retrieval;
- prompt building;
- routes;
- admin analytics;
- feedback UI;
- storage/migrations.

Главный нюанс: лучше внедрять через feature flags, profile-based rollout и shadow mode, а не одним переключением всей системы.

## Metrics

- `wrong-law rate`;
- `wrong-fact rate`;
- `guard pass rate`;
- `median token usage`;
- `p95 token usage`;
- `cost per successful response`;
- `MTTR` по исправлению отмеченных неточностей.
