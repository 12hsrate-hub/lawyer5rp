# lawyer5rp

OGP Builder for `lawyer5rp`: shared domain logic and a FastAPI-based web application.

## Project Layout

- `shared/` - shared business logic used by the web app, tests, and maintenance scripts
- `web/` - FastAPI web app, templates, static files, database integration
- `scripts/` - migrations, backups, and maintenance utilities
- `tests/` - unit and integration-style test coverage
- `docs/` - deployment and migration notes

## Current Runtime Direction

- Web runtime is PostgreSQL-only.
- `DATABASE_URL` is mandatory at startup; app initialization fails fast without it.
- SQLite runtime/backends are not supported.

## Review Starting Points

If you are reviewing the recent infrastructure/runtime changes, start here:

- `web/ogp_web/app.py`
- `web/ogp_web/rate_limit.py`
- `web/ogp_web/db/config.py`
- `web/ogp_web/db/factory.py`
- `web/ogp_web/routes/auth.py`
- `web/ogp_web/storage/user_store.py`
- `web/ogp_web/storage/exam_answers_store.py`
- `web/ogp_web/storage/admin_metrics_store.py`
- `web/ogp_web/services/exam_import_tasks.py`

## Local Web Run

See `web/README_WEB.md` for the full web setup.

Minimal expectation:

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
OGP_WEB_SECRET=change-me
```

Then:

```powershell
cd web
py -m pip install -r requirements_web.txt
py run_web.py
```

## Production Deploy Flow

Recommended deploy path:

1. Develop and test locally.
2. Push to GitHub.
3. Update the server from a GitHub checkout.
4. Run migrations and restart the web process.

Deploy docs:

- `AGENTS.md`
- `docs/github_deploy.md`
- `docs/postgresql_migrations.md`
