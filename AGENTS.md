# Repository Instructions

## Production deploy target

- Primary GitHub repository: `https://github.com/12hsrate-hub/lawyer5rp`
- Production server: `89.111.153.129`
- Production SSH user: `root`
- Live runtime directory: `/srv/lawyer5rp.ru`
- Deploy checkout directory: `/srv/lawyer5rp-deploy/repo`

## Expected deploy flow

When changes are ready:

1. Validate locally.
2. Commit and push to `origin/main`.
3. Update the deploy checkout on the server:

```bash
git -C /srv/lawyer5rp-deploy/repo fetch origin
git -C /srv/lawyer5rp-deploy/repo checkout main
git -C /srv/lawyer5rp-deploy/repo reset --hard origin/main
```

4. Run:

```bash
bash /srv/lawyer5rp-deploy/repo/scripts/deploy_from_checkout.sh
```

5. Verify:

```bash
curl -sS http://127.0.0.1:8000/health
```

## Important notes

- Do not deploy by copying random local files directly into `/srv/lawyer5rp.ru`.
- Production should be updated from the GitHub-backed checkout in `/srv/lawyer5rp-deploy/repo`.
- Preserve server-only runtime files in `/srv/lawyer5rp.ru/web`:
  - `.env`
  - `.venv/`
  - `data/`
- If GitHub Actions deploy secrets are configured, prefer the workflow in `.github/workflows/deploy-production.yml`.
- If auto-deploy is not configured, use the manual GitHub-to-server flow above.
