from server.collector_manager import collector_status


def get_health_snapshot():
    status = collector_status()
    return {
        "ok": True,
        "collector_running": bool(status.get("running")),
        "stream_url": status.get("stream_url"),
    }

