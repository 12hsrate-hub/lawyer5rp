# Suggest Load Suite

This directory contains the single-profile load testing foundation for `/api/ai/suggest`.

## What is included

- `load/k6/suggest_load.js`: k6 scenario for authenticated suggest requests
- `load/k6/suggest_payload_profiles.js`: short/mid/long payload profiles
- `scripts/run_suggest_load.py`: wrapper that logs in, runs k6, and writes artifacts
- `scripts/run_parallel_load.py`: launches multiple profile runs in parallel and writes a consolidated report
- `scripts/run_mixed_load.py`: runs Group B baseline + mixed Group A/Group B impact test with collateral-impact SLA
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
- `server_metrics.csv` when `--sample-server` is enabled
- `server_metrics_summary.json` when `--sample-server` is enabled

Parallel runs additionally write:

`artifacts/load/<run_id>/parallel/`

with:

- `summary.json`
- `report.md`
- `run_config.json`
- `server_metrics.csv` when `--sample-server` is enabled
- `server_metrics_summary.json` when `--sample-server` is enabled

Mixed-load runs additionally write:

`artifacts/load/<run_id>/mixed/`

with:

- `summary.json`
- `report.md`
- `run_config.json`
- `baseline_group_b/summary.json`
- `mixed_group_ab/summary.json`
- `server_metrics.csv` / `server_metrics_summary.json` per phase when `--sample-server` is enabled

## Example

```powershell
py scripts/run_suggest_load.py `
  --base-url https://lawyer5rp.online `
  --profile short `
  --vus 10 `
  --duration 1m `
  --sample-server `
  --server-sampler-interval 1 `
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

## Parallel example

```powershell
py scripts/run_parallel_load.py `
  --base-url https://lawyer5rp.online `
  --profiles short,mid,long `
  --profile-vus short:5 `
  --profile-vus mid:10 `
  --profile-vus long:30 `
  --duration 1m `
  --sample-server `
  --server-sampler-interval 1 `
  --username your_user `
  --password your_password `
  --fail-on-sla `
  --threshold-p95-ms 2500 `
  --threshold-error-rate 0.05
```

## CI-style example

```powershell
py scripts/run_parallel_load.py `
  --base-url $env:LOAD_BASE_URL `
  --profiles short,mid,long `
  --profile-vus short:5 `
  --profile-vus mid:10 `
  --profile-vus long:30 `
  --duration 45s `
  --sample-server `
  --server-sampler-interval 2 `
  --session-cookie $env:OGP_LOAD_SESSION_COOKIE `
  --fail-on-sla `
  --threshold-p95-ms 2500 `
  --threshold-error-rate 0.05
```

## Mixed-load impact example

```powershell
py scripts/run_mixed_load.py `
  --base-url https://lawyer5rp.online `
  --group-a-profile long `
  --group-a-vus 30 `
  --group-b-vus 10 `
  --duration 1m `
  --sample-server `
  --server-sampler-interval 1 `
  --username your_user `
  --password your_password `
  --fail-on-sla `
  --collateral-p95-growth-limit 0.25 `
  --collateral-p99-growth-limit 0.25
```

## Notes on server telemetry

`scripts/server_sampler.py` uses `psutil` and samples the host where the runner executes.
For remote/app-server telemetry, run the load harness on the same host as the app or adapt the sampler launch for your deployment topology.
