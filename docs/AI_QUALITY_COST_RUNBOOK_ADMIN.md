# AI Quality & Cost Runbook (Admin)

Дата версии: 2026-04-12
Статус: PROD baseline

## 1. Цель

Этот документ задает:
- что ежедневно оценивать по качеству AI-выдачи;
- какие пороги считаются нормой, риском и инцидентом;
- какие действия предпринимать автоматически и вручную;
- как принимать решение о смене model-policy.

---

## 2. Основные KPI

### Quality KPI
- `guard_fail_rate`
- `guard_warn_rate`
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
