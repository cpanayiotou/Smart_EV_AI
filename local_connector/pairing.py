"""Secure outbound cloud pairing client for Smart EV Local Connector.

The connector initiates every cloud request. No inbound internet port is needed.
Cloud protocol v0.2 is strictly read-only: evcc.health and evcc.state only.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Callable

CLOUD_URL = os.getenv("SMART_EV_CLOUD_URL", "").rstrip("/")
PAIRING_CODE = os.getenv("SMART_EV_PAIRING_CODE", "")
CONNECTOR_TOKEN = os.getenv("SMART_EV_CONNECTOR_TOKEN", "")
POLL_SECONDS = max(5, int(os.getenv("SMART_EV_POLL_SECONDS", "15")))
TIMEOUT = float(os.getenv("SMART_EV_CLOUD_TIMEOUT_SECONDS", "10"))
PROTOCOL = "0.2"
ALLOWED_COMMANDS = {"evcc.health", "evcc.state"}


def _request(path: str, method: str = "GET", body: dict[str, Any] | None = None,
             token: str | None = None) -> dict[str, Any]:
    if not CLOUD_URL.startswith("https://"):
        raise ValueError("SMART_EV_CLOUD_URL must use HTTPS")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{CLOUD_URL}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as response:
        return json.loads(response.read())


def pair() -> tuple[str, int]:
    if not PAIRING_CODE:
        raise ValueError("SMART_EV_PAIRING_CODE is required for first pairing")
    result = _request("/api/public/local-connectors/pair", "POST", {
        "pairing_code": PAIRING_CODE,
        "connector_version": PROTOCOL,
        "capabilities": sorted(ALLOWED_COMMANDS),
        "read_only": True,
    })
    token = result.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("cloud pairing response did not include token")
    interval = int(result.get("poll_interval_s", POLL_SECONDS))
    return token, max(5, interval)


def _result(token: str, request_id: str, command: str, ok: bool,
            data: dict[str, Any] | None = None, error: str | None = None,
            latency_ms: float | None = None) -> None:
    body: dict[str, Any] = {
        "request_id": request_id,
        "command": command,
        "ok": ok,
    }
    if data is not None:
        body["data"] = data
    if error is not None:
        body["error"] = error
    if latency_ms is not None:
        body["latency_ms"] = round(latency_ms, 1)
    _request("/api/public/local-connectors/result", "POST", body, token=token)


def run(token: str, state_reader: Callable[[], dict[str, Any]],
        health_reader: Callable[[], dict[str, Any]] | None = None,
        poll_seconds: int = POLL_SECONDS) -> None:
    """Poll cloud for read-only work using the deployed cloud v0.2 contract."""
    interval = max(5, poll_seconds)
    while True:
        try:
            work = _request("/api/public/local-connectors/work", token=token)
            interval = max(5, int(work.get("poll_interval_s", interval)))
            requests = work.get("requests", [])
            if not isinstance(requests, list):
                raise ValueError("cloud work response requests must be a list")

            for item in requests:
                if not isinstance(item, dict):
                    continue
                command = item.get("command")
                request_id = item.get("request_id")
                if not isinstance(command, str) or not isinstance(request_id, str):
                    continue
                if command not in ALLOWED_COMMANDS:
                    _result(token, request_id, command, False,
                            error="unsupported_read_only_command")
                    continue

                started = time.monotonic()
                try:
                    if command == "evcc.state":
                        data = state_reader()
                    elif health_reader is not None:
                        data = health_reader()
                    else:
                        data = {"status": "ready", "read_only": True}
                    latency = (time.monotonic() - started) * 1000
                    _result(token, request_id, command, True, data=data, latency_ms=latency)
                except Exception as exc:
                    latency = (time.monotonic() - started) * 1000
                    _result(token, request_id, command, False,
                            error=str(exc), latency_ms=latency)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"[pairing] cloud unavailable: {exc}")
        time.sleep(interval)
