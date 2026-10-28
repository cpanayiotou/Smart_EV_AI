"""Secure outbound cloud pairing client for Smart EV Local Connector.

The connector initiates every cloud request. No inbound internet port is needed.
Cloud protocol v0.3 adds separately authorized, locally opted-in manual mode commands.
"""
from __future__ import annotations

import json
import control
import os
import ssl
import time
import urllib.error
import urllib.request
import urllib.parse
from typing import Any, Callable

CLOUD_URL = os.getenv("SMART_EV_CLOUD_URL", "").rstrip("/")
PAIRING_CODE = os.getenv("SMART_EV_PAIRING_CODE", "")
CONNECTOR_TOKEN = os.getenv("SMART_EV_CONNECTOR_TOKEN", "")
POLL_SECONDS = max(5, int(os.getenv("SMART_EV_POLL_SECONDS", "15")))
TIMEOUT = float(os.getenv("SMART_EV_CLOUD_TIMEOUT_SECONDS", "10"))
PROTOCOL = "0.3"
ALLOWED_COMMANDS = {"evcc.health", "evcc.state"}


class PairingResponseError(ValueError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Cloud redirects are not allowed")


def validate_cloud_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("Enter an HTTPS cloud origin without credentials, path or query")
    if parsed.port not in (None, 443):
        raise ValueError("Cloud HTTPS must use port 443")
    return url.rstrip("/")


def _request(path: str, method: str = "GET", body: dict[str, Any] | None = None,
             token: str | None = None) -> dict[str, Any]:
    if not validate_cloud_url(CLOUD_URL):
        raise ValueError("SMART_EV_CLOUD_URL must use HTTPS")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if path == '/api/public/local-connectors/work' and control.enabled():
        headers['X-Smart-EV-Control'] = 'mode-v1'
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{CLOUD_URL}{path}", data=data, method=method, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                         urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(req, timeout=TIMEOUT) as response:
        return json.loads(response.read(1048577))


def pair() -> tuple[str, int]:
    if not PAIRING_CODE:
        raise ValueError("SMART_EV_PAIRING_CODE is required for first pairing")
    result = _request("/api/public/local-connectors/pair", "POST", {
        "code": PAIRING_CODE,
        "version": PROTOCOL,
    })
    if not isinstance(result, dict):
        raise PairingResponseError('cloud_invalid_response', 'Cloud pairing response must be a JSON object.')
    token = result.get("token")
    if not isinstance(token, str) or not token:
        raise PairingResponseError('cloud_missing_token', 'Cloud returned JSON without the required token. Check the cloud connector API contract.')
    interval = int(result.get("poll_interval_s", POLL_SECONDS))
    return token, max(5, interval)


def _result(token: str, request_id: str, command: str, ok: bool,
            data: dict[str, Any] | None = None, error: str | None = None,
            latency_ms: float | None = None, error_message: str | None = None) -> None:
    body: dict[str, Any] = {
        "request_id": request_id,
        "command": command,
        "ok": ok,
    }
    if data is not None:
        body["data"] = data
    if error is not None:
        body["error"] = {"code": error if error in {"auth_required", "unreachable", "timeout", "invalid_response"} else "unreachable"}
        if error_message:
            body['error']['message'] = error_message
    if latency_ms is not None:
        body["latency_ms"] = max(0, min(600000, round(latency_ms)))
    _request("/api/public/local-connectors/result", "POST", body, token=token)


def run(token: str, state_reader: Callable[[], dict[str, Any]],
        health_reader: Callable[[], dict[str, Any]] | None = None,
        poll_seconds: int = POLL_SECONDS, status_callback=lambda status: None) -> None:
    """Poll telemetry and explicitly authorized manual controls."""
    interval = max(5, poll_seconds)
    while True:
        try:
            work = _request("/api/public/local-connectors/work", token=token)
            interval = max(5, int(work.get("poll_interval_s", interval)))
            status_callback("online")
            requests = work.get("requests", [])
            if not isinstance(requests, list):
                raise ValueError("cloud work response requests must be a list")

            for item in requests:
                if not isinstance(item, dict):
                    continue
                command = item.get("command")
                request_id = item.get("id")
                if not isinstance(command, str) or not isinstance(request_id, str):
                    continue
                if command == 'evcc.set_mode':
                    try:
                        data = control.execute(item, lambda rid: _request(
                            '/api/public/local-connectors/authorize', 'POST',
                            {'request_id': rid}, token=token))
                    except Exception as exc:
                        message = str(exc) if isinstance(exc, control.ControlError) else 'Control failed; check evcc before retrying'
                        _result(token, request_id, command, False, error='invalid_response', error_message=message)
                    else:
                        _result(token, request_id, command, True, data=data)
                    continue
                if command not in ALLOWED_COMMANDS:
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
                            error="unreachable", latency_ms=latency)
        except Exception:
            status_callback("unavailable")
        time.sleep(interval)
