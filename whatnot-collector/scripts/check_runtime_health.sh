#!/usr/bin/env bash
set -euo pipefail

PORT="${FASTAPI_PORT:-8088}"
BASE_URL="${BASE_URL:-http://127.0.0.1:$PORT}"
EMIT_FRONTEND_TEST=0

if [[ "${1:-}" == "--emit-frontend-test" ]]; then
  EMIT_FRONTEND_TEST=1
fi

units=(
  "whatnot-redis.service"
  "whatnot-fastapi.service"
  "whatnot-celery-default.service"
  "whatnot-celery-analytics.service"
  "whatnot-celery-ingest.service"
  "whatnot-celery-business.service"
  "whatnot-celery-beat.service"
  "whatnot-scanner.service"
)

failures=0

check_unit() {
  local unit="$1"
  local state
  state="$(systemctl --user is-active "$unit" 2>/dev/null || true)"
  if [[ "$state" == "active" ]]; then
    printf "OK   service %-36s active\n" "$unit"
  else
    printf "WARN service %-36s %s\n" "$unit" "${state:-missing}"
    failures=$((failures + 1))
  fi
}

check_http() {
  local path="$1"
  local expected="${2:-200}"
  local status
  status="$(curl -sS -o /tmp/whatnot-health-response.json -w '%{http_code}' "$BASE_URL$path" 2>/dev/null || true)"
  if [[ "$status" == "$expected" ]]; then
    printf "OK   http %-42s %s\n" "$path" "$status"
  else
    printf "FAIL http %-42s got %s expected %s\n" "$path" "${status:-curl_error}" "$expected"
    failures=$((failures + 1))
  fi
}

echo "Checking Whatnot runtime at $BASE_URL"
echo

for unit in "${units[@]}"; do
  check_unit "$unit"
done

echo
check_http "/healthz" "200"
check_http "/api/v2/health" "200"

diag_status="$(curl -sS -o /tmp/whatnot-diagnostics-response.json -w '%{http_code}' "$BASE_URL/api/v2/diagnostics/runtime" 2>/dev/null || true)"
case "$diag_status" in
  200) echo "OK   diagnostics runtime endpoint returned 200" ;;
  401) echo "OK   diagnostics runtime endpoint is protected by auth (401)" ;;
  *) echo "WARN diagnostics runtime endpoint returned ${diag_status:-curl_error}"; failures=$((failures + 1)) ;;
esac

redis_cli=""
if command -v redis-cli >/dev/null 2>&1; then
  redis_cli="redis-cli"
elif [[ -x /opt/gitlab/embedded/bin/redis-cli ]]; then
  redis_cli="/opt/gitlab/embedded/bin/redis-cli"
fi
if [[ -n "$redis_cli" ]]; then
  if "$redis_cli" -h 127.0.0.1 -p 6379 ping 2>/dev/null | grep -q PONG; then
    echo "OK   redis ping returned PONG"
  else
    echo "FAIL redis ping failed"
    failures=$((failures + 1))
  fi
else
  echo "WARN redis-cli not found; skipped direct Redis ping"
fi

if [[ "$EMIT_FRONTEND_TEST" == "1" ]]; then
  payload='{"type":"runtime_health_check","message":"Synthetic frontend diagnostics ingestion check","source":"check_runtime_health.sh","url":"health-check","timestamp":"'"$(date -Iseconds)"'"}'
  status="$(curl -sS -o /tmp/whatnot-frontend-error-response.json -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d "$payload" \
    "$BASE_URL/api/v2/diagnostics/frontend-error" 2>/dev/null || true)"
  if [[ "$status" == "200" ]]; then
    echo "OK   frontend diagnostics ingest accepted a synthetic event"
  else
    echo "FAIL frontend diagnostics ingest returned ${status:-curl_error}"
    failures=$((failures + 1))
  fi
fi

echo
if [[ "$failures" -eq 0 ]]; then
  echo "Runtime health check passed."
else
  echo "Runtime health check completed with $failures warning/failure item(s)."
fi

exit "$failures"
