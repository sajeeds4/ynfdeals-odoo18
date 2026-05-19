from server.auth import auth_enabled


def auth_runtime_status():
    return {"ok": True, "auth_enabled": auth_enabled()}

