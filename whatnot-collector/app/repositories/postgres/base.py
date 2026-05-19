from server.postgres_cutover import _pg_connect, postgres_available


def get_connection():
    if not postgres_available():
        raise RuntimeError("Postgres is not available")
    return _pg_connect()

