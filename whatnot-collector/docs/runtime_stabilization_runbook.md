# Runtime Stabilization Runbook

Use this runbook while the main runtime is in stabilization mode.

Scope:
- `FastAPI` public runtime
- `Redis` runtime state, cache, locks, and observability
- `Celery` workers and queues
- compatibility bridge monitoring

Out of scope:
- deferred TikTok migration
- deferred export/report migration
- deferred low-frequency admin ops

## Before Starting

Run from:

```bash
cd "/home/cybertechna/AethrixSystems_Portable/hjay9672-WN /whatnot-collector"
```

Confirm the main runtime process is reachable:

```bash
curl -s http://127.0.0.1:8088/healthz | jq
curl -s http://127.0.0.1:8088/api/v2/health | jq
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq
```

## FastAPI Runtime Health

Check:

```bash
curl -s http://127.0.0.1:8088/healthz | jq
curl -s http://127.0.0.1:8088/api/v2/health | jq
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq '.fastapi_runtime'
```

Healthy signs:
- `/healthz` returns `{"ok": true}`
- `/api/v2/health` returns `{"ok": true}`
- runtime diagnostics return without error
- no unexpected `5xx` responses on core routes

## Redis Health And Usage

Check:

```bash
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq '.fastapi_runtime.redis_connected'
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq '.fastapi_runtime.runtime_state.request_summary'
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq '.fastapi_runtime.runtime_state.bridge_summary'
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq '.fastapi_runtime.runtime_state.task_summary'
```

Healthy signs:
- `redis_connected` is `true`
- request metrics are present
- bridge metrics are present
- task summaries are present
- summaries keep updating over time

## Celery Queue And Worker Health

Check:

```bash
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq '.fastapi_runtime.celery_queue_health'
```

Healthy signs:
- `inspect_ok` is `true`
- default queue appears
- analytics queue appears if worker is running
- ingest/support queue appears if worker is running
- queue depths are not growing without explanation

## Bridge-Hit Monitoring

Check:

```bash
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq '.fastapi_runtime.runtime_state.bridge_summary'
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq '.fastapi_runtime.runtime_state.bridge_metrics'
```

Healthy signs:
- bridge hits stay limited to deferred tracks only
- no core runtime endpoints appear in top bridge-hit routes
- bridge-hit totals are stable or low during normal use

Watch for:
- core runtime endpoints unexpectedly showing up here
- sudden growth after a deploy

## Request Latency And Error Monitoring

Check:

```bash
curl -s http://127.0.0.1:8088/api/v2/diagnostics/runtime | jq '.fastapi_runtime.runtime_state.request_summary'
```

Healthy signs:
- `error_rate_pct` remains low
- top slow routes are understandable
- no core endpoint stays persistently slow

Watch for:
- repeated `5xx` on core routes
- large latency spikes on:
  - spectator routes
  - session stats
  - inventory reads
  - alerts
  - analytics overview
  - market pulse

## Session Review Template

Record after each stabilization check:

```text
Date/Time:
FastAPI Health:
Redis Connected:
Celery Inspect:
Bridge Summary:
Top Slow Routes:
Task Summary:
Issues Seen:
Action Taken:
Verdict: PASS / PASS WITH WARNINGS / FAIL
```

## Hard-Stop Signals

Pause and investigate immediately if:
- FastAPI health endpoints stop returning `200`
- Redis disconnects and runtime state stops updating
- Celery inspect fails repeatedly
- queue depths keep growing unexpectedly
- core runtime endpoints start hitting the bridge
- `error_rate_pct` spikes or `5xx` errors repeat on core routes

## Stabilization Exit Criteria

We can treat stabilization as healthy when:
- FastAPI health remains consistently green
- Redis-backed summaries stay populated and current
- Celery queue health stays visible and stable
- bridge hits remain limited to deferred tracks
- request latency and error metrics remain acceptable under real usage
