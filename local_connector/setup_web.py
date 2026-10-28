"""Password-free, same-origin LAN setup; credentials never returned by HTTP."""
import ipaddress
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

import app
import pairing

NETWORKS = tuple(map(ipaddress.ip_network, (
    '127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '::1/128', 'fc00::/7')))


def local_address(value):
    try:
        address = ipaddress.ip_address(value)
        return any(address in network for network in NETWORKS)
    except ValueError:
        return False


def valid_browser_host(value):
    """Allow numeric LAN addresses and mDNS names, never arbitrary DNS hosts."""
    if not value:
        return False
    value = value.lower().rstrip('.')
    return (local_address(value) or value == 'localhost' or
            (value.endswith('.local') and all(
                label and len(label) <= 63 and
                label[0].isalnum() and label[-1].isalnum() and
                all(c.isascii() and (c.isalnum() or c == '-') for c in label)
                for label in value.split('.'))))


def save_secret(path, value):
    """Atomic durable replace on the same filesystem, with owner-only permissions."""
    temporary = path.with_name('.' + path.name + '.' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        if os.name == 'posix':
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class Setup:
    def __init__(self, directory, start_worker):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        self.lock = threading.Lock()
        self.start_worker = start_worker
        self.config = None
        self.cloud_status = 'not_paired'
        self.next_attempt = 0
        config_file = self.directory / 'connector.json'
        if config_file.exists():
            os.chmod(config_file, 0o600)
            self.config = json.loads(config_file.read_text())
            pairing.CLOUD_URL = pairing.validate_cloud_url(self.config['cloud_url'])
            self.start()

    def start(self):
        self.cloud_status = 'connecting'
        self.start_worker(self.config['token'], self.config['poll_interval_s'], self.set_status)

    def set_status(self, status):
        self.cloud_status = status

    def pair(self, cloud_url, code):
        with self.lock:
            if self.config:
                return 409, {'error': 'Already paired. Use the documented local reset procedure.'}
            if time.monotonic() < self.next_attempt:
                return 429, {'error': 'Wait before trying again.'}
            self.next_attempt = time.monotonic() + 5
            cloud_url = pairing.validate_cloud_url(cloud_url)
            if not isinstance(code, str) or not 4 <= len(code.strip()) <= 128:
                return 400, {'error': 'Enter a fresh pairing code.'}
            pairing.CLOUD_URL = cloud_url
            pairing.PAIRING_CODE = code.strip()
            try:
                token, interval = pairing.pair()
                config = {'cloud_url': cloud_url, 'token': token, 'poll_interval_s': interval}
                save_secret(self.directory / 'connector.json', json.dumps(config))
                self.config = config
            except Exception:
                self.cloud_status = 'pairing_failed'
                return 502, {'error': 'Pairing or secure storage failed. Check cloud URL and request a fresh code.'}
            finally:
                pairing.PAIRING_CODE = ''
            self.start()
            return 200, {'paired': True}


class Handler(app.Handler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def end_headers(self):
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        super().end_headers()

    def allowed(self, mutation=False):
        host = self.headers.get('Host', '')
        try:
            parsed = urlsplit('http://' + host)
            valid_host = (not parsed.username and not parsed.password and not parsed.path and
                          parsed.port == self.server.server_port and valid_browser_host(parsed.hostname))
        except ValueError:
            valid_host = False
        if not local_address(self.client_address[0]) or not valid_host:
            self._json(403, {'error': 'LAN IP access required'})
            return False
        origin = self.headers.get('Origin')
        if ((mutation and origin != 'http://' + host) or
                (origin and origin != 'http://' + host) or
                self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self._json(403, {'error': 'Same-origin access required'})
            return False
        return True

    def do_GET(self):
        if self.path in ('/setup', '/setup/'):
            self.path = '/'
        if not self.allowed():
            return
        if self.path == '/health':
            self._json(200, {'status': 'running', 'read_only': True})
        elif self.path in ('/', '/wizard.js', '/wizard.css'):
            name = {'/': 'wizard.html', '/wizard.js': 'wizard.js', '/wizard.css': 'wizard.css'}[self.path]
            content = Path(__file__).with_name(name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', {'/': 'text/html; charset=utf-8', '/wizard.js': 'text/javascript', '/wizard.css': 'text/css'}[self.path])
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/api/setup/status':
            state = self.server.setup_state
            self._json(200, {'paired': bool(state.config), 'cloud_status': state.cloud_status,
                             'cloud_url': state.config['cloud_url'] if state.config else '',
                             'evcc': app.health(), 'read_only': True})
        else:
            super().do_GET()

    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if self.headers.get('Transfer-Encoding') or not 0 < size <= 4096:
                raise ValueError()
            raw = self.rfile.read(size)
        except ValueError:
            self._json(400, {'error': 'Invalid request size'})
            return
        if not self.allowed(mutation=True):
            return
        if self.path != '/api/setup/pair':
            self._json(405, {'error': 'read_only'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if self.headers.get('Transfer-Encoding') or not 0 < size <= 4096:
                raise ValueError()
            if self.headers.get('Content-Type') != 'application/json':
                raise ValueError()
            body = json.loads(raw)
            if not isinstance(body, dict) or not isinstance(body.get('cloud_url'), str):
                raise ValueError()
            code, result = self.server.setup_state.pair(body['cloud_url'], body.get('pairing_code'))
            self._json(code, result)
        except (ValueError, TypeError):
            self._json(400, {'error': 'Invalid setup request or HTTPS cloud origin.'})

    def reject(self):
        self._json(405, {'error': 'read_only'})

    do_PUT = reject
    do_PATCH = reject
    do_DELETE = reject

    def log_message(self, fmt, *args):
        pass  # Never log user-controlled paths, headers, codes or upstream errors.
