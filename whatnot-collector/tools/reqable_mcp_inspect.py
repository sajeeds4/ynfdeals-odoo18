#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from reqable_mcp.config import config
from reqable_mcp.models import DetailLevel
from reqable_mcp.storage import RequestStorage


def dump(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def build_storage() -> RequestStorage:
    return RequestStorage(
        db_path=config.db_path,
        max_body_size=config.max_body_size,
        summary_body_preview_length=config.summary_body_preview_length,
        key_body_preview_length=config.key_body_preview_length,
        retention_days=config.retention_days,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect reqable-mcp local capture DB")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    p_list = sub.add_parser("requests")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--domain")
    p_list.add_argument("--method")
    p_list.add_argument("--status", type=int)

    p_ws = sub.add_parser("ws")
    p_ws.add_argument("--limit", type=int, default=20)
    p_ws.add_argument("--domain")
    p_ws.add_argument("--active-within-seconds", type=int, default=3600)
    p_ws.add_argument("--include-closing", action="store_true")

    p_search = sub.add_parser("search")
    p_search.add_argument("keyword")
    p_search.add_argument("--search-in", default="all")
    p_search.add_argument("--limit", type=int, default=20)

    p_tail = sub.add_parser("tail-ws")
    p_tail.add_argument("request_id")
    p_tail.add_argument("--after-seq", type=int)
    p_tail.add_argument("--direction")
    p_tail.add_argument("--message-type")
    p_tail.add_argument("--include-raw", action="store_true")
    p_tail.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    storage = build_storage()

    if args.cmd == "status":
        dump(
            {
                "db_path": str(config.db_path),
                "total_requests": storage.total_requests(),
                "total_websocket_sessions": storage.total_websocket_sessions(),
                "total_websocket_messages": storage.total_websocket_messages(),
                "recent_events": storage.recent_events(limit=10),
            }
        )
        return

    if args.cmd == "requests":
        items = storage.get_requests(
            limit=max(1, min(args.limit, 100)),
            detail_level=DetailLevel.SUMMARY,
            domain=args.domain,
            method=args.method,
            status_code=args.status,
        )
        dump([item.model_dump() for item in items])
        return

    if args.cmd == "ws":
        items = storage.list_active_websocket_sessions(
            limit=max(1, min(args.limit, 200)),
            domain=args.domain,
            active_within_seconds=max(1, min(args.active_within_seconds, 86400)),
            include_closing=args.include_closing,
        )
        dump(items)
        return

    if args.cmd == "search":
        items = storage.search(
            keyword=args.keyword,
            search_in=args.search_in,
            limit=max(1, min(args.limit, 100)),
        )
        dump(items)
        return

    if args.cmd == "tail-ws":
        items = storage.tail_websocket_messages(
            request_id=args.request_id,
            after_seq=args.after_seq,
            direction=args.direction,
            message_type=args.message_type,
            include_raw=args.include_raw,
            limit=max(1, min(args.limit, 200)),
        )
        dump(items)
        return


if __name__ == "__main__":
    main()
