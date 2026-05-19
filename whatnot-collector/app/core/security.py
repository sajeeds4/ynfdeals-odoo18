from server.auth import auth_enabled


def runtime_auth_enabled() -> bool:
    return auth_enabled()

