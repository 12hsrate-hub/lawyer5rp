# ARCHITECTURE_RULES.md

## Anti-patterns

### Anti-pattern: route-level business orchestration
Bad:
- route validates request
- route reads multiple stores
- route builds context
- route runs retries/fallbacks
- route assembles domain decisions

Good:
- route resolves auth/deps
- route calls service
- route stays transport-first
- no new route orchestration is added
- legacy-heavy route orchestration is extracted into services when touched
- service owns orchestration

### Anti-pattern: scattered server branching
Bad:
- ad hoc server-specific business branching in unrelated services
- logic branches that bypass config/workflow/bindings/capabilities

Good:
- capability lookup
- server binding
- workflow/config-driven behavior
- legitimate permission/ownership/scope guards where needed

### Anti-pattern: regrowing `ai_service.py`
Bad:
- new retries/finalization/context assembly added back to `ai_service.py`

Good:
- `ai_service.py` remains facade
- orchestration lives in `services/ai_pipeline`

### Anti-pattern: workflow bypass
Bad:
- direct mutation of runtime-effective law/template/rule state without draft/validate/publish tracking

Good:
- draft -> validate -> publish -> rollback + audit

### Anti-pattern: admin monolith growth
Bad:
- new domain behavior embedded directly into route/controller/UI glue

Good:
- dedicated admin helper/service per bounded admin domain

## Good / bad concrete examples

### Layering
Bad:
```python
# routes/*.py
payload = store.read(...)
result = complex_domain_decision(payload)
store.write(result)
```

Good:
```python
# routes/*.py
result = domain_service.handle(request_payload, actor)
return serialize(result)
```

### Multi-server behavior
Bad:
```python
if server_code == "blackberry":
    apply_special_rule()
```

Good:
```python
capabilities = server_capability_service.resolve(server_code)
apply_rule_set(capabilities)
```

### Compatibility seam discipline
Bad:
- new and legacy paths both write runtime state without seam ownership

Good:
- one declared source of truth + explicit adapter/seam boundary + documented removal gate

## Allowed extension points

- shared service helpers
- ai_pipeline orchestration helpers
- workflow-backed content items / versions / bindings
- source connector registry
- admin domain modules

## Non-negotiable guardrails

- Keep boundaries strict with a transport-first route stance: no new route orchestration; prefer extraction when touching legacy-heavy handlers.
- Prefer config/workflow-driven server behavior over ad hoc server-specific business conditionals.
- Legitimate permission/ownership/scope guards are allowed.
- Maintain backward compatibility unless an explicit breaking change is approved and documented.
- Whenever a compatibility seam is touched, create/update `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md`.
