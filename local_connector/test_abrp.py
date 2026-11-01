import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
import unittest
from unittest.mock import patch

import abrp
from setup_web import Handler


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        now = time.time()
        self.payload = dict(available=True, read_only=True, source='abrp/enode',
                            vehicle_id=123, soc_percent=51, soc_timestamp=now-10,
                            fetched_at=now, max_age_seconds=900, age_seconds=10)
        self.status, self.calls = 200, []
        owner = self
        class Sidecar(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.calls.append((self.command, self.path))
                self.send_response(owner.status)
                self.end_headers()
                self.wfile.write(json.dumps(owner.payload).encode())
            def log_message(self, *_):
                pass
        self.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Sidecar)
        self.connector = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.threads = [threading.Thread(target=s.serve_forever, daemon=True)
                        for s in (self.upstream, self.connector)]
        for thread in self.threads:
            thread.start()
        self.env = patch.dict(os.environ, {'CONNECTOR_ABRP_READONLY': 'true'})
        self.url = patch.object(abrp, 'URL', f'http://127.0.0.1:{self.upstream.server_port}/v1/abrp/telemetry')
        self.env.start()
        self.url.start()

    def tearDown(self):
        self.url.stop()
        self.env.stop()
        for server in (self.upstream, self.connector):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join()

    def request(self, path='/v1/abrp/telemetry', method='GET', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.connector.server_port, timeout=5)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.read().decode(), dict(response.getheaders())
        connection.close()
        return result

    def test_live_http_forwarding_and_no_secret_passthrough(self):
        self.payload['refresh_token'] = 'SHOULD_NOT_LEAVE_UPSTREAM'
        code, raw, headers = self.request()
        self.assertEqual(code, 200)
        self.assertNotIn('SHOULD_NOT', raw)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.request('/v1/abrp/soc')[:2], (200, '51'))
        self.assertEqual(self.calls, [('GET', '/v1/abrp/telemetry')] * 2)

    def test_disabled_does_not_contact_sidecar(self):
        with patch.dict(os.environ, {'CONNECTOR_ABRP_READONLY': 'false'}):
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.calls, [])

    def test_failure_never_reuses_success(self):
        self.assertEqual(self.request('/v1/abrp/soc')[0], 200)
        for status in (503, 401, 302, 500):
            self.status = status
            code, raw, _ = self.request('/v1/abrp/soc')
            self.assertEqual(code, 503)
            self.assertIsNone(json.loads(raw)['soc_percent'])

    def test_invalid_or_stale_success_fails_closed(self):
        for key, value in (('soc_timestamp', time.time()-901), ('soc_timestamp', time.time()+60),
                           ('soc_percent', float('nan')), ('soc_percent', True),
                           ('age_seconds', 901), ('age_seconds', -1),
                           ('source', 'other'), ('available', False),
                           ('read_only', False), ('max_age_seconds', 9999)):
            original = self.payload[key]
            self.payload[key] = value
            with self.subTest(key=key, value=value):
                self.assertEqual(self.request()[0], 503)
            self.payload[key] = original

    def test_same_origin_and_method_protections_preserved(self):
        self.assertEqual(self.request(headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request(headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request(method='DELETE')[0], 405)
        self.assertEqual(self.request('/v1/abrp/soc?refresh=true')[0], 404)
        self.assertEqual(self.calls, [])

    def test_evcc_routes_unchanged_and_independent(self):
        with patch('app._evcc_get', return_value=(200, {'loadpoints': []}, 1)) as evcc:
            self.assertEqual(self.request('/v1/evcc/state')[0], 200)
            evcc.assert_called_once_with('/api/state')
        self.assertEqual(self.calls, [])

    def test_timeout_redacted(self):
        with patch('abrp.urllib.request.build_opener', side_effect=TimeoutError('SECRET')):
            code, raw, _ = self.request()
        self.assertEqual(code, 503)
        self.assertNotIn('SECRET', raw)


if __name__ == '__main__':
    unittest.main()
