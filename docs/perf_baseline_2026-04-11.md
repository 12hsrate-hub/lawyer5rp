# Performance Baseline (2026-04-11)

## Scope
- UI rollout validation after shared style adoption.
- Local test-time baseline for web pages and API smoke coverage.

## Measured checks
- `python -m unittest tests.test_web_pages`
  - Result: `OK`
  - Duration: `2.144s`
  - Tests: `7`
- `python -m unittest tests.test_web_api`
  - Result: `OK`
  - Duration: `9.854s`
  - Tests: `31`

## Current warnings / follow-up
- FastAPI deprecation warning: `@app.on_event("shutdown")` should move to lifespan handlers.
- Local log rotation lock on Windows (`PermissionError` for `web/data/logs/ogp_web.log`) appears during tests.
- Resource warnings around SQLite handles in tests should be cleaned up separately.

## Target after next optimization cycle
- Keep `tests.test_web_pages` below `3s`.
- Keep `tests.test_web_api` below `12s`.
- Remove repeated deprecation/resource warnings from CI logs.
