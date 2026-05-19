# Deployment, RBAC, And Diagnostics Setup

This app is intended to run as user-level `systemd` services so FastAPI, Redis, Celery workers, collectors, and sidecars recover after reboot without a manual terminal session.

## Autostart Setup

Install or refresh all runtime unit files:

```bash
./scripts/setup_runtime_autostart.sh
```

The script copies the unit templates into `~/.config/systemd/user`, reloads user `systemd`, enables lingering when possible, enables the services, and restarts them.

FastAPI enables the bearer bypass only for loopback addresses so local sidecars can call authenticated routes without a browser session. Keep `API_SECRET_KEY` strong, and do not widen `DASHBOARD_API_BEARER_BYPASS_IP_ALLOWLIST` beyond trusted internal automation hosts.

Runtime units managed by the setup:

- `whatnot-redis.service`
- `whatnot-fastapi.service`
- `whatnot-celery-default.service`
- `whatnot-celery-analytics.service`
- `whatnot-celery-ingest.service`
- `whatnot-celery-business.service`
- `whatnot-celery-beat.service`
- `whatnot-scanner.service`

Verify the stack:

```bash
./scripts/check_runtime_health.sh
```

Optionally test frontend diagnostics ingestion with a synthetic event:

```bash
./scripts/check_runtime_health.sh --emit-frontend-test
```

Useful manual checks:

```bash
loginctl show-user "$USER" -p Linger
systemctl --user list-unit-files 'whatnot*'
systemctl --user --no-pager status whatnot-fastapi.service whatnot-redis.service
journalctl --user -u whatnot-fastapi.service -n 100 --no-pager
```

## RBAC Workflow

The dashboard now exposes a structured RBAC summary at:

```text
GET /api/auth/rbac
```

Use it while logged in as staff or admin to confirm the active role, route policy groups, and the current permission model.

Role model:

- `admin`: user management, employee login management, POS token management, cookie upload, review sync, and approval/rejection workflows.
- `staff`: authenticated read access plus normal non-admin write operations.
- `public-token`: scoped token access for internal POS endpoints only.
- `public`: health, auth bootstrap/login, feed reads, and frontend diagnostics ingestion.

Operational rule of thumb:

- Add routes to an explicit policy before shipping sensitive features.
- Prefer `admin` for identity, token, cookie, approval, and destructive workflows.
- Prefer `staff_write` only for workflows normal staff should perform.
- Keep `public-token` narrow and auditable.

## Diagnostics Dashboard Workflow

Frontend error capture is wired into the React app and posts to:

```text
POST /api/v2/diagnostics/frontend-error
```

Captured events include browser runtime errors, unhandled promise rejections, React error boundary crashes, useful failed API/network responses, URL, timestamp, user agent, and stack traces when available.

Inspect recent frontend errors in the app:

```text
Company -> Diagnostics -> Frontend Error Capture
```

The API backing that panel is:

```text
GET /api/v2/diagnostics/frontend-errors?limit=80
```

Storage prefers Postgres when available and falls back to `data/frontend_errors.jsonl`, so there is still one structured source even when the database is temporarily unavailable.

When the page is blank or data stops loading:

- Run `./scripts/check_runtime_health.sh`.
- Open `Company -> Diagnostics` after login.
- Check `journalctl --user -u whatnot-fastapi.service -n 100 --no-pager`.
- Look for matching frontend errors by route and timestamp in the diagnostics panel.
