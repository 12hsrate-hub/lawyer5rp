# AI Quality & Cost Runbook (Admin)

Дата версии: 2026-04-17
Статус: PROD primary ops runbook

## 1. Цель и статус документа

Этот документ является основным operational runbook для администраторов AI quality/cost policy.

Он задаёт:

- что ежедневно и еженедельно оценивать по качеству, стоимости и стабильности
- какие пороги считаются нормой, риском и инцидентом
- какие policy-действия выполняются автоматически и вручную
- как эскалировать инциденты и кто владеет решением

Архивный reference по прежнему SLO-документу сохранён в архиве `docs/archive/2026-04/`.

## 2. SLO/KPI Baseline Bands

### 2.1 Quality KPI

| Метрика | Green | Yellow | Red |
| --- | ---: | ---: | ---: |
| `guard_fail_rate` (24h) | <1.5% | 1.5-3.0% | >3.0% |
| `guard_warn_rate` (24h) | <8% | 8-15% | >15% |
| `wrong_law_rate` (24h) | <2.0% | 2.0-4.0% | >4.0% |
| `hallucination_rate` (24h) | <0.8% | 0.8-1.5% | >1.5% |
| `wrong_fact_rate` (24h) | <2.0% | 2.0-4.0% | >4.0% |
| `unclear_answer_rate` (24h) | <5% | 5-9% | >9% |
| `new_fact_validation_rate` (24h) | <1.0% | 1.0-2.0% | >2.0% |
| `unsupported_article_rate` (24h) | <1.0% | 1.0-3.0% | >3.0% |
| `format_violation_rate` (24h) | <3.0% | 3.0-5.0% | >5.0% |
| `validation_retry_rate` (24h) | <8.0% | 8.0-12.0% | >12.0% |
| `safe_fallback_rate` (24h) | <8.0% | 8.0-12.0% | >12.0% |

### 2.2 Stability KPI

| Метрика | Green | Yellow | Red |
| --- | ---: | ---: | ---: |
| `p95_latency_law_qa` | <7s | 7-10s | >10s |
| `p95_latency_suggest` | <9s | 9-13s | >13s |
| `fallback_rate` | baseline | +20% | +40% |

### 2.3 Cost KPI

| Метрика | Green | Yellow | Red |
| --- | ---: | ---: | ---: |
| `avg_cost_per_req_law_qa` | target | +15% | +30% |
| `avg_cost_per_req_suggest` | target | +15% | +30% |
| `estimated_cost_total_usd` (day-to-date) | budget | +10% | +20% |
| `total_tokens_total` (flow/model) | baseline | +20% | +35% |

## 3. Routing Policy

### Law QA

- Default: `gpt-5.4-mini`
- Если `retrieval_confidence=low` или `context_compacted=true`: `gpt-5.4`
- Если `retrieval_confidence=high`, запрос короткий и warning-history отсутствует: `gpt-5.4-nano` только под feature flag
- При `guard_fail`: эскалация на один tier и один retry

### Suggest

- Default: `gpt-5.4-mini`
- Если `low_confidence_context` или есть prior `wrong_fact` / `wrong_law` history: `gpt-5.4`
- Для коротких editorial cleanup кейсов: `gpt-5.4-nano` под feature flag
- Если critical `guard_warn` случается дважды подряд: отключить `nano` и использовать `mini/full` 24h

## 4. Policy Actions

### 4.1 Automatic actions

- Любой единичный `guard_fail`: immediate retry на следующем tier
- `guard_fail_rate > 3%` за 1h: отключить `nano` и зафиксировать minimum tier = `mini` на 6h
- `wrong_law_rate > 4%` за 24h: принудительно `full` для `law_qa` на 24h
- `hallucination_rate > 1.5%`: включить strict-mode и использовать `full` для low-confidence на 24h
- Red по latency при Green quality: временно снизить tier для simple-segment на 2h
- Cost uplift >30% при Green quality: увеличить долю cheap-tier до следующего review

### 4.2 Manual actions

- `keep` - оставить текущий policy-микс без изменений
- `expand cheap tier` - расширить `nano/mini` rollout поэтапно
- `rollback` - вернуть предыдущий stable policy

## 5. Escalation

Немедленная эскалация требуется, если:

- `guard_fail_rate` остаётся в Red 2 часа подряд
- `wrong_law_rate > 5%` за 24h
- жалобы на неточность растут >2x к baseline
- повторный Red по `hallucination_rate` происходит в течение 24h после ручной коррекции policy

Уровни:

- `L1` - on-duty admin
- `L2` - AI policy owner
- `L3` - platform or incident lead

## 6. Daily And Weekly Cadence

Ежедневно:

1. Проверить 24h summary по quality, cost, and stability
2. Просмотреть red/yellow trends по `wrong_law`, `hallucination`, `wrong_fact`, `fallback`
3. Зафиксировать любые manual policy actions

Еженедельно:

1. Пересмотреть rollout долю cheap tiers
2. Сверить стоимость с budget и baseline
3. Согласовать follow-up по routing, prompts, guards, and validation

## 7. Owner Matrix

| Area | Primary owner | Backup / escalation |
| --- | --- | --- |
| Routing policy | AI policy owner | platform lead |
| Quality incidents | on-duty admin | AI policy owner |
| Cost control | AI policy owner | platform lead |
| Runtime / deployment impact | platform lead | incident lead |
- `wrong_law_rate`
- `hallucination_rate`
- `wrong_fact_rate`
- `unclear_answer_rate`
- `new_fact_validation_rate`
- `unsupported_article_rate`
- `format_violation_rate`
- `validation_retry_rate`
- `safe_fallback_rate`

### Cost KPI
- `avg_cost_per_req_law_qa`
- `avg_cost_per_req_suggest`
- `estimated_cost_total_usd`
- `total_tokens_total` (flow/model)

### Stability KPI
- `p95_latency_law_qa`
- `p95_latency_suggest`
- `fallback_rate` (auto-escalation usage)

---

## 3. Пороговые значения (SLA/SLO)

| Метрика | Green | Yellow | Red |
| --- | ---: | ---: | ---: |
| guard_fail_rate (24h) | <1.5% | 1.5-3.0% | >3.0% |
| guard_warn_rate (24h) | <8% | 8-15% | >15% |
| wrong_law_rate (24h) | <2.0% | 2.0–4.0% | >4.0% |
| hallucination_rate (24h) | <0.8% | 0.8–1.5% | >1.5% |
| wrong_fact_rate (24h) | <2.0% | 2.0–4.0% | >4.0% |
| unclear_answer_rate (24h) | <5% | 5–9% | >9% |
| new_fact_validation_rate (24h) | <1.0% | 1.0–2.0% | >2.0% |
| unsupported_article_rate (24h) | <1.0% | 1.0–3.0% | >3.0% |
| format_violation_rate (24h) | <3.0% | 3.0–5.0% | >5.0% |
| validation_retry_rate (24h) | <8.0% | 8.0–12.0% | >12.0% |
| safe_fallback_rate (24h) | <8.0% | 8.0–12.0% | >12.0% |
| p95 law_qa | <7s | 7–10s | >10s |
| p95 suggest | <9s | 9–13s | >13s |
| avg_cost_per_req_law_qa | target | +15% | +30% |
| avg_cost_per_req_suggest | target | +15% | +30% |

---

## 4. Автодействия policy

1. На уровне генерации:
   - `guard_fail` => один retry с эскалацией модели (`nano -> mini`, `mini -> full`).

2. На уровне окна 1h:
   - `guard_fail_rate > 3%` => запрет `nano` на 6 часов.

3. На уровне окна 24h:
   - `wrong_law_rate > 4%` => law_qa принудительно на `full` на 24 часа.
   - `hallucination_rate > 1.5%` => strict режим + `full` для low-confidence.

4. Rollback:
   - 2 часа подряд Red по `guard_fail_rate` => немедленный rollback policy.
   - `wrong_law_rate > 5%` за 24h => rollback policy.
   - жалобы на неточность растут >2x к baseline => rollback policy.

---

## 5. Программный роутинг моделей (без UI выбора)

### Law QA
- default: `mini`
- low confidence / context compacted: `full`
- high confidence + короткий вопрос + без warning history: `nano` (если включен флаг)

### Suggest
- default: `mini`
- low-confidence-context или повторный quality-risk: `full`
- короткие редактурные кейсы: `nano` (флаг)

---

## 6. Ежедневный чек-лист администратора

1. Открыть сводку за 24h:
   - quality блок
   - cost блок
   - latency блок

2. Проверить красные зоны:
   - `wrong_law` / `hallucination` / `wrong_fact` всплеск
   - рост `guard_fail_rate`, `validation_retry_rate`, `safe_fallback_rate`
   - аномальный рост стоимости на запрос

3. Проверить top inaccurate generations:
   - `generation_id`
   - `issue_type`
   - `output_preview`
   - `guard_warnings`
   - feedback note

4. Принять действие:
   - keep / expand cheap tier / rollback

---

## 7. Еженедельная переоценка policy

Сравнить baseline и candidate:
- delta cost (%)
- delta quality (% по критичным issue)
- delta latency p95

Решение:
- expand candidate, если cost win >= 25% и нет роста critical quality > 10%
- rollback, если quality деградировало выше порога
- keep, если эффект нейтральный

---

## 8. Обязательные артефакты в админке

- Quality traffic-light (Green / Yellow / Red)
- Cost by model / flow
- Accuracy taxonomy (`wrong_law`, `wrong_fact`, `hallucination`, `unclear`)
- Drill-down по `generation_id`
- Policy action log (когда и почему переключили tier)
