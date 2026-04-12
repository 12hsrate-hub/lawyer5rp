# PostgreSQL production cutover runbook

This runbook is for the final SQLite -> PostgreSQL runtime cutover in production.

## Preconditions

- Latest `main` commit is green in runtime CI (`postgres-runtime` job).
- Optional migration suite (`legacy-sqlite-migration`) was run at least once on the release candidate.
- A fresh backup exists for `/srv/lawyer5rp.ru/web/data`.

## Cutover steps

1. **Freeze writes**
   - Put the app in maintenance mode or block mutating endpoints at reverse proxy level.
   - Confirm no active write traffic (auth/register, complaint generation, exam import writes).

2. **Final SQLite -> PostgreSQL migration**

```bash
cd /srv/lawyer5rp-deploy/repo
export OGP_DB_BACKEND=postgres
export DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<db>
python scripts/migrate_sqlite_to_postgres.py --source-dir /srv/lawyer5rp.ru/web/data
```

3. **Run schema migrations on PostgreSQL**

```bash
python scripts/run_db_migrations.py --backend postgres
```

4. **Deploy latest commit from GitHub checkout**

```bash
git -C /srv/lawyer5rp-deploy/repo fetch origin
git -C /srv/lawyer5rp-deploy/repo checkout main
git -C /srv/lawyer5rp-deploy/repo reset --hard origin/main
bash /srv/lawyer5rp-deploy/repo/scripts/deploy_from_checkout.sh
```

5. **Smoke checks**

```bash
curl -sS http://127.0.0.1:8000/health
```

Then manually verify end-to-end paths:

- auth: register/login/logout
- complaint: generate + draft save/load
- admin: `/api/admin/overview` (authorized session)
- exam import: import rows + score task lifecycle

6. **Unfreeze writes**
   - Re-enable mutating endpoints after smoke checks pass.

## Rollback (if required)

- Freeze writes again.
- Restore previous application backup from `/srv/lawyer5rp.ru/backups`.
- Point runtime back to the previous known-good commit and restart service.
- Keep PostgreSQL data snapshot for incident analysis.
