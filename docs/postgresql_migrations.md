# PostgreSQL migrations

Current migration runner:

```powershell
py scripts/run_db_migrations.py --backend postgres --dry-run
py scripts/run_db_migrations.py --backend postgres
```

Required environment variables:

```env
OGP_DB_BACKEND=postgres
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

Current migration set:

- `0001_postgres_core`

What `0001_postgres_core` creates:

- `schema_migrations`
- `servers`
- `users`
- `user_server_roles`
- `complaint_drafts`
- `metric_events`
- `exam_answers`
- `exam_import_tasks`

Notes:

- Runner currently applies PostgreSQL migrations only.
- Web runtime is PostgreSQL-only across application code, CI, and maintenance scripts.
- The migration runner is intentionally simple: SQL files are versioned and applied in sorted order.
