"""Experimental, read-only ABRP sidecar. Python 3.11+; standard library only.

Protocol adapted from MichelFR/ha-abrp (MIT); see THIRD_PARTY_NOTICES.md.
No vehicle commands, settings writes, telemetry uploads or evcc calls exist here.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

HOME = "https://abetterrouteplanner.com"
ACCOUNTS = "https://accounts.abetterrouteplanner.com"
TELEMETRY = "https://api.iternio.com/1/session/get_tlm"
REDIRECT = HOME + "/abrpAuthRedirect"
MAX_BODY = 8 * 1024 * 1024


class Unavailable(Exception):
    """Only fixed, non-sensitive reason codes may leave this boundary."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(NoRedirect(), HTTPCookieProcessor(self.cookies))

    def request(self, url, *, body=None, form=False, api_key=None, redirect=False, text=False):
        # Explicit allowlist: no caller-selected hosts or mutation endpoints.
        parsed = urlparse(url)
        allowed = (
            url == TELEMETRY
            or (parsed.scheme == "https" and parsed.netloc == "accounts.abetterrouteplanner.com"
                and parsed.path in {"/authorize", "/login/abrp", "/login/abrp/status", "/token"})
            or (parsed.scheme == "https" and parsed.netloc == "abetterrouteplanner.com"
                and (parsed.path == "/" or re.fullmatch(r"/_expo/static/js/[\w./-]+\.js", parsed.path)))
        )
        if not allowed:
            raise Unavailable("endpoint_rejected")
        headers = {"User-Agent": "Smart-EV-AI-readonly/0.1", "Accept": "application/json"}
        data = None
        if body is not None:
            data = (urlencode(body) if form else json.dumps(body)).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        if api_key:
            headers.update({"Authorization": "APIKEY " + api_key, "Origin": HOME, "Referer": HOME + "/"})
        try:
            try:
                response = self.opener.open(Request(url, data=data, headers=headers), timeout=20)
            except HTTPError as exc:
                if redirect and exc.code in (302, 303):
                    location = exc.headers.get("Location", "")
                    exc.close()
                    return location
                code = exc.code
                exc.close()
                auth_error = code in (401, 403) or (url == ACCOUNTS + "/token" and code == 400)
                raise Unavailable("auth_required" if auth_error else "rate_limited" if code == 429 else "upstream_http") from None
            with response:
                raw = response.read(MAX_BODY + 1)
                is_bundle = text and parsed.netloc == "abetterrouteplanner.com" and parsed.path.startswith("/_expo/static/js/")
                if len(raw) > MAX_BODY and not is_bundle:
                    raise Unavailable("response_too_large")
                if redirect:
                    raise Unavailable("login_protocol_changed")
                return raw[:MAX_BODY].decode("utf-8", errors="replace") if text else json.loads(raw)
        except (URLError, OSError, ValueError):
            raise Unavailable("upstream_unavailable") from None


class CredentialStore:
    """Single-process ownership and atomic, private rotation (Linux deployment)."""
    def __init__(self, path):
        self.path = Path(path)
        parent = self.path.parent
        if not parent.is_dir() or parent.is_symlink():
            raise Unavailable("credential_directory_required")
        if os.name == "posix":
            info = parent.stat()
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise Unavailable("credential_directory_not_private")
        self.lock = None

    def acquire(self):
        if os.name == "posix":
            import fcntl
            fd = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            self.lock = os.fdopen(fd, "w")
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Unavailable("credentials_in_use") from None

    def read(self):
        if self.path.is_symlink():
            raise Unavailable("credential_file_not_private")
        info = self.path.stat()
        if os.name == "posix" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise Unavailable("credential_file_not_private")
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("refresh_token"), str) or not data["refresh_token"]:
            raise Unavailable("auth_required")
        return data["refresh_token"]

    def write(self, refresh):
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".rotation-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"refresh_token": refresh}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            if os.name == "posix":
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def tokens(data):
    if not isinstance(data, dict):
        raise Unavailable("auth_required")
    access, refresh, expiry = (data.get(k) for k in ("access_token", "refresh_token", "expires_in"))
    if not all(isinstance(x, str) and x for x in (access, refresh)) or not number(expiry) or not 60 < expiry <= 86400:
        raise Unavailable("auth_required")
    return access, refresh, expiry


def login(http, store):
    """Run only in the user's local terminal; link never enters service logs."""
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    location = http.request(ACCOUNTS + "/authorize?" + urlencode({
        "response_type": "code", "client_id": "app", "redirect_uri": REDIRECT,
        "scope": "oidc profile email offline_access", "state": state,
        "nonce": secrets.token_urlsafe(24), "code_challenge": challenge, "code_challenge_method": "S256",
    }), redirect=True)
    parsed = urlparse(location)
    if parsed.scheme and (parsed.scheme != "https" or parsed.netloc != "accounts.abetterrouteplanner.com"):
        raise Unavailable("login_protocol_changed")
    session = parse_qs(parsed.query).get("session", [None])[0]
    csrf = next((c.value for c in http.cookies if c.name == "_csrf" and c.domain.lstrip(".") == "accounts.abetterrouteplanner.com"), None)
    if not session or not csrf:
        raise Unavailable("login_protocol_changed")
    html = http.request(ACCOUNTS + "/login/abrp?" + urlencode({"session": session}), text=True)
    match = re.search(r"connect_session_token=([A-Za-z0-9-]+)", html)
    if not match:
        raise Unavailable("login_protocol_changed")
    print("Open this private, short-lived link on your own signed-in ABRP device. Do not share it:")
    print(HOME + "/?connect_session_token=" + match[1], flush=True)
    for _ in range(90):
        time.sleep(2)
        approval = http.request(ACCOUNTS + "/login/abrp/status?" + urlencode({"code": match[1]}))
        if isinstance(approval, dict) and approval.get("approved") is True:
            break
    else:
        raise Unavailable("login_expired")
    location = http.request(ACCOUNTS + "/login/abrp", body={"session": session, "csrf": csrf}, form=True, redirect=True)
    target = urlparse(location)
    query = parse_qs(target.query)
    if target.scheme + "://" + target.netloc + target.path != REDIRECT or query.get("state") != [state] or not query.get("code"):
        raise Unavailable("login_state_mismatch")
    _, refresh, _ = tokens(http.request(ACCOUNTS + "/token", form=True, body={
        "grant_type": "authorization_code", "code": query["code"][0], "redirect_uri": REDIRECT,
        "client_id": "app", "code_verifier": verifier,
    }))
    store.write(refresh)
    print("Authorization saved locally. No password was collected.")


class Client:
    def __init__(self, http, store):
        self.http, self.store = http, store
        self.access, self.expires, self.key, self.key_expires = None, 0, None, 0

    def metadata(self):
        if self.key and time.monotonic() < self.key_expires:
            return self.key
        html = self.http.request(HOME + "/", text=True)
        queue = re.findall(r'src="(/_expo/static/js/[^" ]+\.js)"', html)
        seen = set()
        while queue and len(seen) < 8:
            path = queue.pop(0)
            if path in seen:
                continue
            seen.add(path)
            bundle = self.http.request(HOME + path, text=True)
            match = re.search(r"API_KEY:'([0-9a-fA-F-]{16,})'", bundle)
            if match:
                self.key, self.key_expires = match[1], time.monotonic() + 21600
                return self.key
            queue.extend(p for p in re.findall(r"/_expo/static/js/[\w./-]+\.js", bundle) if p not in seen)
        raise Unavailable("web_metadata_changed")

    def fetch(self):
        if not self.access or time.monotonic() >= self.expires:
            access, refresh, expiry = tokens(self.http.request(ACCOUNTS + "/token", form=True, body={
                "grant_type": "refresh_token", "refresh_token": self.store.read(), "client_id": "app",
            }))
            # Persist rotated credentials before using the new access token.
            self.store.write(refresh)
            self.access, self.expires = access, time.monotonic() + expiry - 60
        result = self.http.request(TELEMETRY, body={"session_id": self.access}, api_key=self.metadata())
        if not isinstance(result, dict) or result.get("status") != "ok" or not isinstance(result.get("result"), list):
            raise Unavailable("telemetry_protocol_changed")
        return result["result"]


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def normalize(items, vehicle_id, now):
    selected = [x for x in items if isinstance(x, dict) and type(x.get("vehicle_id")) is int and x["vehicle_id"] == vehicle_id]
    if len(selected) != 1:
        raise Unavailable("vehicle_missing_or_ambiguous")
    item = selected[0]
    tlm = item.get("tlm")
    if not isinstance(tlm, dict):
        raise Unavailable("invalid_telemetry")
    soc = tlm.get("soc")
    timestamps, providers = tlm.get("timestamps"), tlm.get("providers")
    ts = timestamps.get("soc") if isinstance(timestamps, dict) else None
    provider = providers.get("soc") if isinstance(providers, dict) else None
    if not number(soc) or not 0 <= soc <= 100:
        raise Unavailable("invalid_soc")
    # Never substitute fetch time, tlm.utc or ota_tlm_time for SoC's own time.
    if not number(ts) or ts <= 0 or ts > now + 30:
        raise Unavailable("invalid_soc_timestamp")
    if provider != "enode" or item.get("tlm_authorized") is False:
        raise Unavailable("enode_unverified_or_unauthorized")
    return {"vehicle_id": vehicle_id, "soc_percent": soc, "soc_timestamp": ts,
            "fetched_at": now, "source": "abrp/enode", "read_only": True}


class State:
    def __init__(self, vehicle_id, max_age=900):
        self.vehicle_id, self.max_age = vehicle_id, max_age
        self.lock = threading.Lock()
        self.sample, self.received, self.reason = None, 0, "not_ready"
        self.latest_ts, self.latest_soc = 0, None

    def update(self, items, now=None, monotonic=None):
        now = time.time() if now is None else now
        monotonic = time.monotonic() if monotonic is None else monotonic
        sample = normalize(items, self.vehicle_id, now)
        with self.lock:
            ts, soc = sample["soc_timestamp"], sample["soc_percent"]
            if ts < self.latest_ts or (ts == self.latest_ts and soc != self.latest_soc):
                raise Unavailable("soc_timestamp_regression")
            self.latest_ts, self.latest_soc = ts, soc
            self.sample, self.received, self.reason = sample, monotonic, None

    def fail(self, reason):
        with self.lock:
            self.reason = reason

    def response(self, now=None, monotonic=None):
        now = time.time() if now is None else now
        monotonic = time.monotonic() if monotonic is None else monotonic
        with self.lock:
            if self.reason or self.sample is None:
                return 503, {"available": False, "reason": self.reason or "not_ready", "soc_percent": None, "read_only": True}
            sample = dict(self.sample)
            elapsed = max(0, monotonic - self.received)
            age = max(now - sample["soc_timestamp"], sample["fetched_at"] - sample["soc_timestamp"] + elapsed, 0)
            valid = age <= self.max_age and now >= sample["soc_timestamp"] - 30
            clock_valid = now >= sample["soc_timestamp"] - 30
            sample.update(available=valid, age_seconds=round(age, 2), max_age_seconds=self.max_age,
                          last_known_soc_percent=sample["soc_percent"] if clock_valid else None,
                          display_available=clock_valid, stale=not valid)
            if not valid:
                sample.update(soc_percent=None, reason="stale_or_clock_invalid")
            return (200 if valid else 503), sample


def handler(state):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path not in ("/v1/abrp/telemetry", "/v1/abrp/soc", "/v1/abrp/display", "/healthz"):
                self.send_error(404)
                return
            code, payload = state.response()
            if self.path == "/v1/abrp/display" and payload.get("display_available") is True:
                code = 200
            if self.path == "/healthz":
                code, payload = 200, {"running": True, "telemetry_available": code == 200, "read_only": True}
            raw = (str(payload["soc_percent"]) if self.path == "/v1/abrp/soc" and code == 200 else json.dumps(payload, allow_nan=False)).encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain" if self.path == "/v1/abrp/soc" and code == 200 else "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            self.send_error(405)

        do_PUT = do_PATCH = do_DELETE = do_POST
    return Handler


def poll(client, state, stop, interval):
    failures = 0
    while not stop.is_set():
        try:
            state.update(client.fetch())
            failures = 0
        except Unavailable as exc:
            state.fail(str(exc))
            failures += 1
            if str(exc) == "auth_required":
                # Do not loop against a revoked/consumed grant.
                return
        except Exception:
            state.fail("adapter_error")
            return
        stop.wait(min(3600, interval * 2 ** min(failures, 5)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("login", "vehicles", "serve"))
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--vehicle-id", type=int)
    parser.add_argument("--port", type=int, default=7081)
    parser.add_argument("--poll-seconds", type=int, default=600)
    parser.add_argument("--max-age-seconds", type=int, default=900)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("credential-bearing commands require Linux/POSIX; run them on the Raspberry Pi")
    if not 60 <= args.poll_seconds <= 3600 or not 60 <= args.max_age_seconds <= 3600:
        parser.error("poll and max age must be between 60 and 3600 seconds")
    if args.command == "serve" and (not args.vehicle_id or args.vehicle_id < 1 or args.port in (7070, 7080) or not 1024 <= args.port <= 65535):
        parser.error("serve needs a positive vehicle ID and an unoccupied port other than 7070/7080")
    try:
        store = CredentialStore(args.credentials)
        store.acquire()
        http = Transport()
        if args.command == "login":
            login(http, store)
            return
        client = Client(http, store)
        if args.command == "vehicles":
            # Minimal local identification; no VIN, GPS, tokens or raw payloads.
            for item in client.fetch():
                if isinstance(item, dict):
                    print(json.dumps({k: item.get(k) for k in ("vehicle_id", "name", "car_model")}))
            return
        state, stop = State(args.vehicle_id, args.max_age_seconds), threading.Event()
        with HTTPServer(("127.0.0.1", args.port), handler(state)) as server:
            server.timeout = 1
            threading.Thread(target=poll, args=(client, state, stop, args.poll_seconds), daemon=True).start()
            try:
                server.serve_forever()
            finally:
                stop.set()
    except (Unavailable, OSError, ValueError) as exc:
        print("Adapter stopped: " + (str(exc) if isinstance(exc, Unavailable) else "local_configuration_error"))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
