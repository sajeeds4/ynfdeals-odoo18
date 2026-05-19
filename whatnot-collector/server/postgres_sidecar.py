"""
Retired SQLite mirror sidecar.

The application now runs directly on Postgres. The historical SQLite snapshot
mirror is intentionally disabled.
"""

from __future__ import annotations


HOT_TABLES: tuple[str, ...] = ()


class PostgresMirror:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("sqlite_sidecar_retired")


def ensure_database() -> None:
    raise RuntimeError("sqlite_sidecar_retired")


def build_default_mirror() -> PostgresMirror:
    raise RuntimeError("sqlite_sidecar_retired")
