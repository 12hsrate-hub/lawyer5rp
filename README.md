# lawyer5rp

OGP Builder for `lawyer5rp`: desktop tooling, shared domain logic, and a FastAPI-based web application.

## Project Layout

- `desktop/` - desktop app and local support code
- `shared/` - shared business logic used by both desktop and web
- `web/` - FastAPI web app, templates, static files, database integration
- `scripts/` - migrations, backups, and maintenance utilities
- `tests/` - unit and integration-style test coverage
- `docs/` - deployment and migration notes

## Current Runtime Direction

- Web runtime is PostgreSQL-first.
- Production is already running on PostgreSQL.
- SQLite is kept only for migration, backup, and some explicit test scenarios.

## Review Starting Points

If you are reviewing the recent infrastructure/runtime changes, start here:

- [web/ogp_web/app.py](/c:/Users/12hs/Desktop/VS/web/ogp_web/app.py)
- [web/ogp_web/rate_limit.py](/c:/Users/12hs/Desktop/VS/web/ogp_web/rate_limit.py)
- [web/ogp_web/db/config.py](/c:/Users/12hs/Desktop/VS/web/ogp_web/db/config.py)
- [web/ogp_web/db/factory.py](/c:/Users/12hs/Desktop/VS/web/ogp_web/db/factory.py)
- [web/ogp_web/routes/auth.py](/c:/Users/12hs/Desktop/VS/web/ogp_web/routes/auth.py)
- [web/ogp_web/storage/user_store.py](/c:/Users/12hs/Desktop/VS/web/ogp_web/storage/user_store.py)
- [web/ogp_web/storage/exam_answers_store.py](/c:/Users/12hs/Desktop/VS/web/ogp_web/storage/exam_answers_store.py)
- [web/ogp_web/storage/admin_metrics_store.py](/c:/Users/12hs/Desktop/VS/web/ogp_web/storage/admin_metrics_store.py)
- [web/ogp_web/services/exam_import_tasks.py](/c:/Users/12hs/Desktop/VS/web/ogp_web/services/exam_import_tasks.py)

## Local Web Run

See [web/README_WEB.md](/c:/Users/12hs/Desktop/VS/web/README_WEB.md) for the full web setup.

Minimal expectation:

```env
OGP_DB_BACKEND=postgres
DATABASE_URL=postgresql://user:password@host:5432/dbname
OGP_WEB_SECRET=change-me
```

Then:

```powershell
cd web
py -m pip install -r requirements_web.txt
py run_web.py
```

