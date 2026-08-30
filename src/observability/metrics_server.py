from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Config


class _MetricsHandler(BaseHTTPRequestHandler):
    config: Config

    def log_message(self, format: str, *args: object) -> None:
        return

    def _write(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        from observability.health import readiness
        from observability.metrics import prometheus_text

        if self.path == "/metrics":
            body = prometheus_text(self.config).encode()
            self._write(200, body, "text/plain; version=0.0.4")
            return
        if self.path in ("/health", "/healthz", "/live", "/livez"):
            self._write(200, b"ok", "text/plain")
            return
        if self.path in ("/ready", "/readyz"):
            report = readiness(self.config)
            body = json.dumps(report.to_dict()).encode()
            status = 200 if report.ok else 503
            self._write(status, body, "application/json")
            return
        if self.path == "/health/full":
            report = readiness(self.config)
            body = json.dumps(report.to_dict(), indent=2).encode()
            status = 200 if report.ok else 503
            self._write(status, body, "application/json")
            return
        self.send_response(404)
        self.end_headers()


def serve_metrics(cfg: Config, port: int = 8080) -> HTTPServer:
    handler = type("Handler", (_MetricsHandler,), {"config": cfg})
    server = HTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
