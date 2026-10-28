"""Local, read-only Audi battery data for evcc. No vehicle commands."""
import argparse
import asyncio
import getpass
import json
import logging
import math
import os
from pathlib import Path
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POLL_SECONDS = 1800
MAX_AGE_SECONDS = 3600


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Missing vehicle capture time')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Vehicle capture time must include timezone')
    return result.timestamp()


def number(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Missing numeric vehicle reading')
    if not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError('Invalid vehicle reading')
    return value


def normalize(raw):
    """Keep each value's Audi capture time, never replace it with fetch time."""
    battery = raw.get('charging', {}).get('batteryStatus', {}).get('value', {})
    result = {
        'soc': number(battery.get('currentSOC_pct'), 100),
        'captured_at': timestamp(battery.get('carCapturedTimestamp')),
        'source': 'audi',
    }
    ranges = raw.get('fuelStatus', {}).get('rangeStatus', {}).get('value', {})
    for key in ('primaryEngine', 'secondaryEngine'):
        engine = ranges.get(key) or {}
        if engine.get('type') == 'electric':
            try:
                result['range_km'] = number(engine.get('remainingRange_km'), 2000)
                result['range_captured_at'] = timestamp(ranges.get('carCapturedTimestamp'))
            except (ValueError, TypeError):
                result.pop('range_km', None)
            break
    return result


def fresh(captured_at, now):
    return -60 <= now - captured_at <= MAX_AGE_SECONDS


class Cache:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = None
        self.error = 'waiting_for_audi'

    def update(self, data):
        with self.lock:
            self.data, self.error = dict(data), None

    def fail(self):
        with self.lock:
            self.data, self.error = None, 'audi_unavailable'

    def read(self, path, now=None):
        now = time.time() if now is None else now
        if path == '/health':
            return 200, {'status': 'running', 'read_only': True}
        if path not in ('/vehicle', '/soc', '/range'):
            return 404, {'error': 'not_found'}
        with self.lock:
            data = dict(self.data) if self.data else None
            error = self.error
        if not data:
            return 503, {'error': error}
        if not fresh(data['captured_at'], now):
            return 503, {'error': 'vehicle_data_stale'}
        if not fresh(data.get('range_captured_at', 0), now):
            data.pop('range_km', None)
            data.pop('range_captured_at', None)
        if path == '/range':
            if 'range_km' not in data:
                return 503, {'error': 'range_unavailable'}
            return 200, data['range_km']
        if path == '/soc':
            return 200, data['soc']
        data['age_seconds'] = max(0, round(now - data['captured_at']))
        return 200, data


def handler_for(cache):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Prevent browser requests through DNS rebinding or cross-origin fetch.
            allowed = {f'127.0.0.1:{self.server.server_port}',
                       f'localhost:{self.server.server_port}'}
            if (self.headers.get('Host') not in allowed or
                    self.headers.get('Origin') or
                    self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                status, value = 403, {'error': 'local_service_only'}
            else:
                status, value = cache.read(self.path)
            body = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    return Handler


def atomic_json(path, data):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(directory):
    country = input('Audi account country code (for example CY): ').strip().upper()
    if len(country) != 2 or not country.isalpha():
        raise ValueError('Use a two-letter Audi account country code')
    from audi_connect.oauth import uses_device_code
    username = password = ''
    if not uses_device_code(country):
        username = input('Audi username: ').strip()
        password = getpass.getpass('Audi password: ')
        if not username or not password:
            raise ValueError('Credentials required for this account region')
    vin = input('Vehicle VIN (leave empty only if account has one vehicle): ').strip().upper()
    atomic_json(directory / 'config.json', dict(country=country, username=username,
                                               password=password, vin=vin))
    # Tokens belong to the previous account/region; require fresh approval after setup.
    (directory / 'tokens.json').unlink(missing_ok=True)
    print('Saved locally. Run the probe next; do not share token files.')


def select_vin(vehicles, requested):
    vins = [v['vin'] for v in vehicles if isinstance(v.get('vin'), str)]
    if requested and requested in vins:
        return requested
    if not requested and len(vins) == 1:
        return vins[0]
    raise ValueError('Configure a VIN belonging to this account')


class AudiReader:
    def __init__(self, directory, interactive=False):
        self.directory, self.interactive = directory, interactive
        self.auth = self.vin = None

    def verification(self, info):
        if not self.interactive:
            raise RuntimeError('Run probe interactively to approve Audi access')
        print('Open this Audi approval link privately:',
              info.get('verification_uri_complete') or info.get('verification_uri'), flush=True)
        print('Approval code:', info.get('user_code'), flush=True)

    async def fetch(self, session):
        from audi_connect import AudiAPI, AudiAuth
        from audi_connect.token_store import TokenStore

        class StrictTokenStore(TokenStore):
            # Upstream logs and swallows write failures. Fail instead and save atomically.
            def save(store, state):
                data = state.to_dict()
                data['saved_at'] = time.time()
                atomic_json(self.directory / 'tokens.json', data)

        if self.auth is None:
            config = json.loads((self.directory / 'config.json').read_text())
            auth = AudiAuth(AudiAPI(session), country=config['country'],
                            token_store=StrictTokenStore(str(self.directory / 'tokens.json')))
            vehicles = await auth.login(config['username'], config['password'],
                                        on_verification=self.verification)
            self.vin = select_vin(vehicles, config['vin'])
            self.auth = auth
        else:
            # The upstream bearer tokens can expire sooner than the MBB token.
            if not await self.auth.refresh_tokens(POLL_SECONDS, force=True):
                self.auth = None
                raise RuntimeError('Audi token refresh unavailable')
        raw = await self.auth.get_stored_vehicle_data(self.vin)
        return normalize(raw)


async def run(directory, probe=False):
    from audi_connect.connection import create_session
    reader = AudiReader(directory, interactive=probe)
    cache = Cache()
    server = None
    if not probe:
        server = ThreadingHTTPServer(('127.0.0.1', 7081), handler_for(cache))
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with create_session() as session:
            while True:
                try:
                    # Interactive device approval may take several minutes.
                    data = await asyncio.wait_for(reader.fetch(session), 900 if probe else 120)
                    cache.update(data)
                    if probe:
                        status, result = cache.read('/vehicle')
                        print(json.dumps(result))
                        return 0 if status == 200 else 2
                    print('Audi read completed; capture time retained.', flush=True)
                except Exception as exc:
                    cache.fail()
                    reader.auth = None
                    # Never log upstream messages: they may contain VINs or credentials.
                    print(f'Audi read failed ({type(exc).__name__}); run probe for approval if needed.', flush=True)
                    if probe:
                        return 1
                await asyncio.sleep(POLL_SECONDS)
    finally:
        if server:
            server.shutdown()
            server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('configure', 'probe', 'serve'))
    parser.add_argument('--data-dir', type=Path, default=Path('/data'))
    args = parser.parse_args()
    # This service runs on Linux. One writer across configure/probe/serve.
    import fcntl
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    with (args.data_dir / '.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, 'Stop the bridge before configure/probe; another instance holds its data lock.\n')
        if args.command == 'configure':
            configure(args.data_dir)
            return 0
        return asyncio.run(run(args.data_dir, probe=args.command == 'probe'))


if __name__ == '__main__':
    raise SystemExit(main())
