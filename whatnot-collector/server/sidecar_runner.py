"""
Retired sidecar runner.

SQLite is no longer part of the normal runtime path. The historical sidecar
process that mirrored SQLite into Postgres/Redis is intentionally disabled.
"""

from __future__ import annotations

import argparse


def run_once(*, enable_postgres: bool, enable_redis: bool, account: str) -> dict:
    return {
        "ok": False,
        "retired": True,
        "error": "sqlite_sidecar_retired",
        "postgres_requested": bool(enable_postgres),
        "redis_requested": bool(enable_redis),
        "account": account,
    }


def run_loop(*, enable_postgres: bool, enable_redis: bool, account: str) -> int:
    _ = run_once(enable_postgres=enable_postgres, enable_redis=enable_redis, account=account)
    raise RuntimeError("sqlite_sidecar_retired")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retired SQLite sidecar runner")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--account", default="ynfdeals")
    parser.add_argument("--postgres", dest="postgres", action="store_true", default=False)
    parser.add_argument("--no-postgres", dest="postgres", action="store_false")
    parser.add_argument("--redis", dest="redis", action="store_true", default=False)
    parser.add_argument("--no-redis", dest="redis", action="store_false")
    args = parser.parse_args(argv)
    if args.once:
        run_once(enable_postgres=args.postgres, enable_redis=args.redis, account=args.account)
        return 0
    return run_loop(enable_postgres=args.postgres, enable_redis=args.redis, account=args.account)


if __name__ == "__main__":
    raise SystemExit(main())
