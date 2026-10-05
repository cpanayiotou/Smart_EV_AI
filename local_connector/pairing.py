"""Secure outbound cloud pairing client for Smart EV Local Connector.

The connector initiates every cloud request. No inbound internet port is needed.
The cloud returns read-only commands; only evcc.state is accepted.
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


def pair() -> str:
    if not PAIRING_CODE:
        raise ValueError("SMART_EV_PAIRING_CODE is required for first pairing")
    result = _request("/api/local-connectors/pair", "POST", {
        "pairing_code": PAIRING_CODE,
        "connector_version": "0.2",
        "capabilities": ["evcc.health", "evcc.state"],
        "read_only": True,
    })
    token = result.get("connector_token")
    if not isinstance(token, str) or not token:
        raise ValueError("cloud pairing response did not include connector_token")
    return token


def run(token: str, state_reader: Callable[[], dict[str, Any]]) -> None:
    """Poll cloud for read-only work. The allowlist is deliberately tiny."""
    while True:
        try:
            work = _request("/api/local-connectors/work", token=token)
            command = work.get("command")
            request_id = work.get("request_id")
            if command == "evcc.state" and request_id:
                payload = state_reader()
                _request("/api/local-connectors/result", "POST", {
                    "request_id": request_id,
                    "ok": True,
                    "payload": payload,
                }, token=token)
            elif command not in {None, "none"}:
                _request("/api/local-connectors/result", "POST", {
                    "request_id": request_id,
                    "ok": False,
                    "error": "unsupported_read_only_command",
                }, token=token)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"[pairing] cloud unavailable: {exc}")
        time.sleep(POLL_SECONDS)
