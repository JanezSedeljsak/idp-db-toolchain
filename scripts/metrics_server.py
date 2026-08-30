from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.config import Config


class _MetricsHandler(BaseHTTPRequestHandler):
    config: Config

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        from scripts.metrics import prometheus_text

        if self.path == "/metrics":
            body = prometheus_text(self.config).encode()
            content_type = "text/plain; version=0.0.4"
        elif self.path in ("/health", "/healthz"):
            body = b"ok"
            content_type = "text/plain"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_metrics(cfg: Config, port: int = 8080) -> HTTPServer:
    handler = type("Handler", (_MetricsHandler,), {"config": cfg})
    server = HTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
