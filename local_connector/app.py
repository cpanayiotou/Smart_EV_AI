"""Smart EV Local Connector — read-only evcc bridge.

This service intentionally supports GET-only access to evcc. It never sends
charger-control commands. The upstream /api/state payload is passed through
with a small connector envelope so the cloud/product adapter can normalize it.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from socket import gethostbyname
from typing import Any

EVCC_URL = os.getenv("EVCC_URL", "http://evcc.local:7070").rstrip("/")
LISTEN_HOST = os.getenv("CONNECTOR_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("CONNECTOR_PORT", "7080"))
TIMEOUT = float(os.getenv("EVCC_TIMEOUT_SECONDS", "5"))


def _is_private_target(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost"} or host.endswith(".local"):
        return True
    try:
        return ip_address(host).is_private or ip_address(host).is_loopback
    except ValueError:
        try:
            resolved = ip_address(gethostbyname(host))
            return resolved.is_private or resolved.is_loopback
        except OSError:
            return False


def _evcc_get(path: str) -> tuple[int, Any, float]:
    if not _is_private_target(EVCC_URL):
        raise ValueError("EVCC_URL must resolve to a local/private network address")
    url = f"{EVCC_URL}{path}"
    started = time.monotonic()
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read()
            latency_ms = (time.monotonic() - started) * 1000
            return response.status, json.loads(raw), latency_ms
    except urllib.error.HTTPError as exc:
        latency_ms = (time.monotonic() - started) * 1000
        return exc.code, {"error": f"evcc returned HTTP {exc.code}"}, latency_ms


def health() -> dict[str, Any]:
    try:
        status, state, latency = _evcc_get("/api/state")
        verified = status == 200 and isinstance(state, dict) and (
            "loadpoints" in state or "apiReady" in state or "startupCompleted" in state
        )
        return {
            "status": "ready" if verified else "connection_problem",
            "verified_evcc": verified,
            "evcc_url": EVCC_URL,
            "latency_ms": round(latency, 1),
            "api_ready": state.get("apiReady") if isinstance(state, dict) else None,
            "startup_completed": state.get("startupCompleted") if isinstance(state, dict) else None,
        }
    except Exception as exc:
        return {
            "status": "offline",
            "verified_evcc": False,
            "evcc_url": EVCC_URL,
            "error": str(exc),
        }


class Handler(BaseHTTPRequestHandler):
    server_version = "SmartEVConnector/0.1"

    def _json(self, code: int, body: Any) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, health())
            return
        if self.path == "/v1/evcc/state":
            try:
                status, state, latency = _evcc_get("/api/state")
                if status != 200:
                    self._json(502, {"status": "connection_problem", "upstream": state})
                    return
                self._json(200, {
                    "source": "evcc",
                    "read_only": True,
                    "observed_at_unix": time.time(),
                    "latency_ms": round(latency, 1),
                    "state": state,
                })
            except Exception as exc:
                self._json(502, {"status": "offline", "error": str(exc)})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        self._json(405, {"error": "read_only"})

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[connector] {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    print(f"Smart EV Local Connector listening on {LISTEN_HOST}:{LISTEN_PORT}")
    print(f"Read-only evcc target: {EVCC_URL}")
    ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler).serve_forever()
