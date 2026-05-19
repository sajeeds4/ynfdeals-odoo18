#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for postgres bootstrap" >&2
  exit 1
fi

if [[ -f .env ]]; then
  sed -i 's|^POSTGRES_SIDECAR_DSN=.*|POSTGRES_SIDECAR_DSN=dbname=whatnot_sidecar host=127.0.0.1 port=5433 user=postgres password=postgres|' .env || true
  sed -i 's|^POSTGRES_SIDECAR_DBNAME=.*|POSTGRES_SIDECAR_DBNAME=whatnot_sidecar|' .env || true
fi

docker compose -f docker-compose.postgres.yml up -d

for _ in {1..40}; do
  if docker exec whatnot-postgres pg_isready -U postgres -d whatnot_sidecar >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if [[ ! -x .venv/bin/python ]]; then
  echo "python virtual environment not found at .venv; create it and install requirements first" >&2
  exit 1
fi

./.venv/bin/python - <<'PY'
from server.postgres_cutover import ensure_wave1_postgres_schema

ensure_wave1_postgres_schema()
print("postgres schema initialized")
PY

SEED_DIR="data/strong_backups/session_cleanup_keep_18_20260430_180610"
SEED_SCHEMA_SQL="$SEED_DIR/postgres_session_tables_schema.sql"
SEED_DEMO_SQL="$SEED_DIR/postgres_session_tables_demo.sql"
SEED_DEMO="${SEED_DEMO:-1}"

if [[ "$SEED_DEMO" == "1" ]]; then
  if [[ -f "$SEED_SCHEMA_SQL" ]]; then
    docker exec -i whatnot-postgres psql -U postgres -d whatnot_sidecar < "$SEED_SCHEMA_SQL"
  fi
  if [[ -f "$SEED_DEMO_SQL" ]]; then
    docker exec -i whatnot-postgres psql -U postgres -d whatnot_sidecar < "$SEED_DEMO_SQL"
  fi
  echo "demo seed applied (set SEED_DEMO=0 to skip)"
fi

echo "Bootstrap complete. Postgres is running on 127.0.0.1:5433"
