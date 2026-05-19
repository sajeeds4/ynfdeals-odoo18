from __future__ import annotations

import threading
import time
from http.server import ThreadingHTTPServer

from server.api import Handler


class LegacyBridgeManager:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> str:
        if self._server is not None:
            return self.url
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError:
            # The standalone legacy API may already be serving this port. Keep
            # FastAPI alive and point callers at the existing bridge address.
            return self.url
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="legacy-api-bridge",
            daemon=True,
        )
        self._thread.start()
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if self._thread.is_alive():
                break
            time.sleep(0.05)
        return self.url

    def stop(self) -> None:
        if self._server is None:
            return
        try:
            self._server.shutdown()
            self._server.server_close()
        finally:
            self._server = None
            self._thread = None
