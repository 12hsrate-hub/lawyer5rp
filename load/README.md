# Suggest Load Suite

This directory contains the single-profile load testing foundation for `/api/ai/suggest`.

## What is included

- `load/k6/suggest_load.js`: k6 scenario for authenticated suggest requests
- `load/k6/suggest_payload_profiles.js`: short/mid/long payload profiles
- `scripts/run_suggest_load.py`: wrapper that logs in, runs k6, and writes artifacts
- `load/suggest_load_support.py`: shared helpers for artifact layout and report generation

## Supported payload profiles

- `short`
- `mid`
- `long`

## Suggested concurrency tiers

- `5`
- `10`
- `30`
- `50`

## Artifact layout

Each run writes into:

`artifacts/load/<run_id>/<profile>/`

Artifacts include:

- `summary.json`
- `report.md`
- `run_config.json`

## Example

```powershell
py scripts/run_suggest_load.py `
  --base-url https://lawyer5rp.online `
  --profile short `
  --vus 10 `
  --duration 1m `
  --username your_user `
  --password your_password
```

If you already have a valid `ogp_web_session`, you can use:

```powershell
py scripts/run_suggest_load.py `
  --base-url https://lawyer5rp.online `
  --profile long `
  --vus 30 `
  --duration 2m `
  --session-cookie <cookie>
```
