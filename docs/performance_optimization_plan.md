# Performance Optimization Plan

## 1) Baseline and Metrics (1-2 days)

- Capture baseline:
  - `scripts/perf_baseline.py` – p50/p95/error_rate/throughput by windows.
  - `scripts/perf_sql_profile.py` – SQL profile for hot paths.
- Check indexes:
  - `web/ogp_web/storage/admin_metrics_store.py`
    - `metric_events(event_type, created_at)`
    - `metric_events(path, created_at)`
    - `metric_events(username, created_at)`
  - `web/ogp_web/storage/exam_answers_store.py`
    - `exam_answers(source_row, import_key)`
    - `exam_answers(source_row, average_score, needs_rescore)`
- Confirm migration:
  - `web/ogp_web/db/migrations/versions/postgres/0002_performance_indexes.sql`
- Verify endpoint hardening:
  - `/api/admin/performance` cache = 10s
  - payload for `/api/admin/overview` and `/api/admin/users.csv`
- Verify throttling/429 behavior.

### Commands

```bash
py scripts/perf_baseline.py --window-minutes 15,60,1440 --top-endpoints 10 --output scripts/perf-baseline.json
py scripts/perf_sql_profile.py --backend postgres
```

### Baseline format

- `generated_at`
- `database_backend`
- `windows` entries:
  - `p50_ms`
  - `p95_ms`
  - `error_rate`
  - `throughput_rps`
  - `total_api_requests`

## 2) Quick Improvements (2-4 days)

- Fix slow SQL paths shown by profile.
- Remove N+1 / redundant DB reads in `web/storage/*`.
- Reduce read-heavy payloads and tune API timeouts.
- Add and run perf smoke tests.

### KPI vs baseline check

```bash
py -m unittest tests.test_perf_threshold_check
py scripts/perf_threshold_check.py \
  --baseline scripts/perf-baseline.json \
  --input scripts/perf-baseline.json \
  --max-p95-growth 0.20 \
  --error-rate-delta 0.005 \
  --max-throughput-drop-ratio 0.10 \
  --min-requests 10
```

The check fails only on real KPI regressions when sample volume is enough; small samples are reported as warnings.

## 3) Medium-term (1-2 weeks)

- Move heavy operations to background jobs.
- Add concurrency/rate protection on hot endpoints.
- Add 2-3 critical performance smoke scenarios.

## 4) Stabilization (ongoing)

- Keep baseline report history and weekly trend review.
- Budget gates:
  - p95 growth <= 20%
  - error_rate increase <= 0.5%
  - throughput drop <= 10%
- Stop release if KPIs are worse than baseline.
