from server.collector_manager import collector_status, live_collector_status


def get_collector_runtime():
    return {"ok": True, **collector_status()}


def get_live_collector_runtime():
    return {"ok": True, **live_collector_status()}

