# GitHub deploy flow

Recommended production flow for this project:

1. Make changes locally.
2. Run local tests and checks.
3. Push to GitHub.
4. Server updates from GitHub checkout.
5. Run migrations and restart the web process.
6. Verify `/health`.

## Why this flow is better

- production is tied to a concrete Git commit
- rollback becomes easier
- server updates are reproducible
- no manual file copying is needed
- GitHub Actions can automate the final step later

## Server layout

Keep two separate directories on the server:

```text
/srv/lawyer5rp.ru
  live runtime directory

/srv/lawyer5rp-deploy/repo
  Git checkout used as the deployment source
```

The live runtime directory keeps server-only state:

- `web/.env`
- `web/.venv/`
- `web/data/`
- `backups/`

The deploy checkout is disposable and can always be refreshed from GitHub.

## One-time server bootstrap

Run this once on the server:

```bash
mkdir -p /srv/lawyer5rp-deploy
if [ ! -d /srv/lawyer5rp-deploy/repo/.git ]; then
  git clone https://github.com/12hsrate-hub/lawyer5rp.git /srv/lawyer5rp-deploy/repo
fi
```

## Manual deploy from GitHub

Refresh the checkout and deploy:

```bash
git -C /srv/lawyer5rp-deploy/repo fetch origin
git -C /srv/lawyer5rp-deploy/repo checkout main
git -C /srv/lawyer5rp-deploy/repo reset --hard origin/main
bash /srv/lawyer5rp-deploy/repo/scripts/deploy_from_checkout.sh
```

What the deploy script does:

- backs up current deploy-managed files from `shared`, `web`, and `scripts`
- syncs fresh files from the Git checkout
- preserves `web/.env`, `web/.venv`, and `web/data`
- runs PostgreSQL migrations
- restarts the FastAPI process
- checks `/health`

## GitHub Actions auto-deploy

The repository includes `.github/workflows/deploy-production.yml`.

Before enabling it, add these GitHub repository secrets:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_PORT` (optional, defaults to `22`)

Recommended values:

- `DEPLOY_HOST=89.111.153.129`
- `DEPLOY_USER=root`
- `DEPLOY_PORT=22`

`DEPLOY_SSH_KEY` should be a private key whose public part is added to `/root/.ssh/authorized_keys` on the server.

## Health checks

Manual checks after deploy:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS -i http://127.0.0.1:8000/api/admin/overview
tail -n 80 /srv/lawyer5rp.ru/web/data/logs/server.out
```

`/api/admin/overview` returns `401 Unauthorized` without a logged-in session. That is expected.
