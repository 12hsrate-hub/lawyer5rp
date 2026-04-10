# Review Notes

## Suggested Review Scope

This repository was pushed for code review after a PostgreSQL-oriented runtime cleanup and production hardening pass.

Focus areas:

1. PostgreSQL runtime assumptions for web
2. Persistent auth rate limiting
3. Health and production diagnostics
4. Remaining SQLite boundaries

## Key Changes To Review

### 1. Runtime defaults moved toward PostgreSQL

- `web` runtime now assumes PostgreSQL by default
- production configuration was validated against the live server
- SQLite remains only as an explicit path for migration, backup, and some tests

Primary files:

- `web/ogp_web/db/config.py`
- `web/ogp_web/db/factory.py`

### 2. Rate limiting is no longer single-process only

- old in-memory auth limiter was replaced with a DB-backed limiter for shared enforcement across processes
- limiter health is now visible through `/health`

Primary files:

- `web/ogp_web/rate_limit.py`
- `web/ogp_web/app.py`
- `web/ogp_web/routes/auth.py`

### 3. Store defaults no longer silently prefer SQLite

Primary files:

- `web/ogp_web/storage/user_store.py`
- `web/ogp_web/storage/exam_answers_store.py`
- `web/ogp_web/storage/admin_metrics_store.py`
- `web/ogp_web/services/exam_import_tasks.py`

### 4. Test harness was adjusted to keep explicit SQLite fixtures where needed

Primary files:

- `tests/test_web_api.py`
- `tests/test_web_pages.py`
- `tests/test_web_storage.py`
- `tests/test_web_services.py`

## Verified During This Pass

- Production PostgreSQL connectivity on the live server
- Migration runner returned no pending PostgreSQL migrations
- Production `/health` returned `status=ok`
- Production rate limiter now reports `storage=database`
- Targeted local tests and compile checks passed

## Known Remaining Follow-Up

- `web` still contains some dual-path code branches for PostgreSQL vs SQLite internals
- there is a separate production bug in exam import timestamp handling that should be handled next
- FastAPI shutdown wiring still uses deprecated `on_event`
