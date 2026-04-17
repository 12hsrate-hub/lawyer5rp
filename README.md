# lawyer5rp

OGP Builder for `lawyer5rp`: shared domain logic plus a FastAPI-based web application with multi-server admin, law, and AI-assisted document flows.

## Project Layout

- `shared/` - shared business logic used by the web app, tests, and maintenance scripts
- `web/` - FastAPI web app, templates, static files, and database integration
- `scripts/` - migrations, smoke checks, and maintenance utilities
- `tests/` - unit and integration-style test coverage
- `docs/` - active operational, architecture, and product documentation
- `docs/archive/` - historical plans, audits, rollout packets, and superseded docs
- `examples/` - starter examples and non-runtime samples
- `artifacts/` - generated exports and run artifacts

## Current Runtime Direction

- Web runtime is PostgreSQL-only.
- Production is updated from a GitHub-backed checkout, not by copying local files into the live runtime.

## Main Documentation Entry Points

Start here:

- `AGENTS.md` - repository rules, deploy target, and definition of done
- `docs/README.md` - canonical documentation index
- `docs/OPERATIONS_INDEX.md` - deploy, rollback, and live-ops entrypoint

Primary active reference docs:

- `docs/ADMIN_PANEL.md` - admin IA, entrypoints, and terminology
- `docs/AI_INTEGRATION.md` - AI/provenance contract and traceability baseline
- `docs/ASYNC_JOB_CONTRACTS.md` - async state, retry, and idempotency contracts
- `docs/LEGACY_COMPATIBILITY.md` - legacy seams to preserve or retire
- `docs/FEATURE_FLAGS.md` - rollout flags and rollout-state mapping
- `docs/AI_QUALITY_COST_RUNBOOK_ADMIN.md` - admin AI quality/cost operations
- `docs/github_deploy.md` - GitHub-to-server deploy flow
- `docs/postgresql_migrations.md` - migration flow

## Local Web Run

See `web/README_WEB.md` for the full web setup.

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

## Production Deploy Flow

Recommended deploy path:

1. Develop and test locally.
2. Push to GitHub.
3. Update the server from the GitHub checkout in `/srv/lawyer5rp-deploy/repo`.
4. Run the deploy script, migrations, restart, and `/health` verification.

See:

- `AGENTS.md`
- `docs/OPERATIONS_INDEX.md`
- `docs/github_deploy.md`
- `docs/postgresql_migrations.md`
