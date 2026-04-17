# AI Quality & Cost Runbook (Admin)

Дата версии: 2026-04-17  
Статус: PROD primary ops runbook

## 1. Цель и статус документа

Этот документ — **основной operational runbook** для администраторов AI quality/cost policy.

Он задает:
- что ежедневно и еженедельно оценивать по качеству, стоимости и стабильности;
- какие пороги считаются нормой, риском и инцидентом;
- какие policy-действия выполняются автоматически и вручную;
- как эскалировать инциденты и кто владеет решением.

`docs/MODEL_POLICY_SLO.md` считается superseded и оставлен как краткий reference с указанием на этот runbook.

---

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

---

## 3. Routing Policy (без UI выбора модели)

### Law QA
- Default: `gpt-5.4-mini`
- Если `retrieval_confidence=low` или `context_compacted=true`: `gpt-5.4`
- Если `retrieval_confidence=high`, запрос короткий и warning-history отсутствует: `gpt-5.4-nano` (только под feature flag)
- При `guard_fail`: эскалация на один tier и один retry

### Suggest
- Default: `gpt-5.4-mini`
- Если `low_confidence_context` или есть prior `wrong_fact`/`wrong_law` history: `gpt-5.4`
- Для коротких editorial cleanup кейсов: `gpt-5.4-nano` (feature flag)
- Если critical `guard_warn` случается дважды подряд: отключить `nano`, использовать `mini/full` 24h

---

## 4. Policy Actions

### 4.1 Automatic actions

- Любой единичный `guard_fail`: immediate retry на следующем tier (`nano -> mini`, `mini -> full`).
- `guard_fail_rate > 3%` за 1h: отключить `nano` и зафиксировать minimum tier = `mini` на 6h.
- `wrong_law_rate > 4%` за 24h: принудительно `full` для `law_qa` на 24h.
- `hallucination_rate > 1.5%`: включить strict-mode и использовать `full` для low-confidence на 24h.
- Red по latency при Green quality: временно снизить tier для simple-segment на 2h.
- Cost uplift >30% при Green quality: увеличить долю cheap-tier на 15% до следующего review.

### 4.2 Manual actions (admin)

- `keep`: оставить текущий policy-микс без изменений.
- `expand cheap tier`: расширить `nano/mini` rollout поэтапно (10% -> 30% -> 60% -> 100%).
- `rollback`: вернуть предыдущий stable policy.

---

## 5. Escalation

### 5.1 Trigger conditions

Немедленная эскалация в incident channel при любом условии:
- `guard_fail_rate` остается в Red 2 часа подряд;
- `wrong_law_rate > 5%` за 24h;
- жалобы на неточность растут >2x к baseline;
- повторный Red по `hallucination_rate` в течение 24h после ручной коррекции policy.

### 5.2 Escalation levels

- **L1 (On-duty admin):** подтверждение алерта, первичный triage, запуск авто/ручного mitigation (до 30 минут).
- **L2 (AI policy owner):** решение по rollback/forced full tier, фиксация change-log и гипотез (до 60 минут).
- **L3 (Platform/incident lead):** координация при затяжном инциденте, временное ограничение risky сегментов, пост-инцидентный разбор.

### 5.3 Communication checklist

- Зафиксировать time-to-detect, time-to-mitigate, выбранное действие.
- Обновить policy action log: что изменено, почему, на какой срок.
- Оставить follow-up задачи: prompt/routing/guard tuning, A/B validation, дата проверки эффекта.

---

## 6. Daily/Weekly Cadence

### 6.1 Daily cadence (операционный цикл)

1. Проверить 24h summary по quality/cost/stability.
2. Проверить Red/Yellow зоны, особенно `wrong_law`, `hallucination`, `guard_fail_rate`, `validation_retry_rate`, `safe_fallback_rate`.
3. Проверить accuracy drill-down (top generation incidents): `generation_id`, issue type, output preview, guard warnings, feedback note.
4. Принять действие: `keep` / `expand cheap tier` / `rollback`.
5. Обновить action log и зафиксировать owner/follow-up.

### 6.2 Weekly cadence (policy review)

Сравнить baseline и candidate policy:
- delta cost (%),
- delta quality (critical issue rate),
- delta latency p95.

Решение:
- **expand candidate**, если экономия >=25% и нет роста critical quality >10%;
- **rollback**, если quality деградирует выше порогов;
- **keep**, если итог нейтральный.

---

## 7. Owner Matrix

| Зона ответственности | Primary owner | Backup owner | SLA по реакции |
| --- | --- | --- | --- |
| Daily KPI мониторинг | Admin on duty | Ops backup | 30 мин |
| Policy action (keep/expand/rollback) | AI Policy Owner | Product/AI Lead | 60 мин |
| Incident coordination (Red) | Incident Lead | Platform Lead | 15 мин на ack |
| Cost anomaly review | FinOps/Ops | AI Policy Owner | 1 рабочий день |
| Weekly policy review | AI Policy Owner | Admin + Product | еженедельно |

---

## 8. Обязательные артефакты в админке

- Quality traffic-light (Green / Yellow / Red)
- Cost by model / flow
- Accuracy taxonomy (`wrong_law`, `wrong_fact`, `hallucination`, `unclear`)
- Drill-down по `generation_id`
- Policy action log (когда и почему переключили tier)
- Incident timeline (detect -> mitigate -> recover)
