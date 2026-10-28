import asyncio
import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
from http.server import ThreadingHTTPServer

from bridge import AudiReader, Cache, atomic_json, failure_detail, handler_for, normalize, select_vin

RAW = {'charging': {'batteryStatus': {'value': {
    'currentSOC_pct': 58, 'carCapturedTimestamp': '2026-10-28T10:00:00Z'}}},
    'fuelStatus': {'rangeStatus': {'value': {
        'carCapturedTimestamp': '2026-10-28T09:55:00Z',
        'primaryEngine': {'type': 'electric', 'remainingRange_km': 242}}}}}


class ReadingsTest(unittest.TestCase):
    def setUp(self):
        self.data = normalize(RAW)
        self.now = self.data['captured_at'] + 300
        self.cache = Cache()
        self.cache.update(self.data)

    def test_original_capture_time_and_range(self):
        status, data = self.cache.read('/vehicle', self.now)
        self.assertEqual(status, 200)
        self.assertEqual(data['soc'], 58)
        self.assertEqual(data['range_km'], 242)
        self.assertEqual(data['age_seconds'], 300)
        self.assertEqual(data['captured_at'], self.data['captured_at'])

    def test_repeated_fetch_cannot_make_stale_reading_fresh(self):
        self.cache.update(normalize(RAW))
        self.assertEqual(self.cache.read('/soc', self.now + 3600)[0], 503)

    def test_future_capture_rejected(self):
        self.assertEqual(self.cache.read('/soc', self.data['captured_at'] - 61)[0], 503)

    def test_independent_range_expiry(self):
        self.assertEqual(self.cache.read('/soc', self.now + 3100)[0], 200)
        self.assertEqual(self.cache.read('/range', self.now + 3100)[0], 503)

    def test_error_invalidates_previous_reading(self):
        self.cache.fail()
        self.assertEqual(self.cache.read('/soc', self.now)[0], 503)
        self.assertEqual(self.cache.read('/health', self.now)[0], 200)

    def test_missing_capture_not_replaced_with_now(self):
        raw = copy.deepcopy(RAW)
        del raw['charging']['batteryStatus']['value']['carCapturedTimestamp']
        with self.assertRaises(ValueError):
            normalize(raw)

    def test_missing_soc_is_not_zero(self):
        with self.assertRaises(ValueError):
            normalize({})

    def test_bad_soc_values(self):
        for value in (None, True, '58', -1, 101, float('nan'), float('inf')):
            with self.subTest(value=value):
                raw = copy.deepcopy(RAW)
                raw['charging']['batteryStatus']['value']['currentSOC_pct'] = value
                with self.assertRaises(ValueError):
                    normalize(raw)

    def test_zero_soc_is_valid(self):
        raw = copy.deepcopy(RAW)
        raw['charging']['batteryStatus']['value']['currentSOC_pct'] = 0
        self.assertEqual(normalize(raw)['soc'], 0)

    def test_timezone_required(self):
        raw = copy.deepcopy(RAW)
        raw['charging']['batteryStatus']['value']['carCapturedTimestamp'] = '2026-10-28T10:00:00'
        with self.assertRaises(ValueError):
            normalize(raw)

    def test_no_combustion_range(self):
        raw = copy.deepcopy(RAW)
        raw['fuelStatus']['rangeStatus']['value']['primaryEngine']['type'] = 'gasoline'
        self.assertNotIn('range_km', normalize(raw))

    def test_multiple_vehicles_require_selection(self):
        vehicles = [{'vin': 'ONE'}, {'vin': 'TWO'}]
        with self.assertRaises(ValueError):
            select_vin(vehicles, '')
        with self.assertRaises(ValueError):
            select_vin(vehicles, 'UNKNOWN')
        self.assertEqual(select_vin(vehicles, 'TWO'), 'TWO')
        self.assertEqual(select_vin(vehicles[:1], ''), 'ONE')


class HttpTest(unittest.TestCase):
    def setUp(self):
        cache = Cache()
        cache.update({'soc': 58, 'captured_at': time.time(), 'source': 'audi'})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(cache))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, method='GET', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response.status, body

    def test_numeric_soc(self):
        self.assertEqual(self.request('/soc'), (200, b'58'))

    def test_no_remote_actions(self):
        for path in ('/lock', '/unlock', '/charge', '/climate', '/refresh'):
            self.assertEqual(self.request(path)[0], 404)
            self.assertEqual(self.request(path, 'POST')[0], 501)

    def test_rebinding_and_browser_origin_rejected(self):
        self.assertEqual(self.request('/soc', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.request('/soc', headers={'Origin': 'http://attacker.example'})[0], 403)

    def test_health_contains_no_vehicle_identity(self):
        self.assertEqual(json.loads(self.request('/health')[1]),
                         {'status': 'running', 'read_only': True})


class ProviderTest(unittest.TestCase):
    def test_device_rejection_diagnostic_omits_private_fields(self):
        exc = Exception('Device authorization did not return a device_code: ' +
                        json.dumps({'error': 'unauthorized_client', 'token': 'SECRET',
                                    'error_description': 'PRIVATE ACCOUNT'}))
        self.assertEqual(failure_detail(exc),
                         'Audi device authorization rejected: unauthorized_client')

    def test_unknown_and_truncated_errors_never_echo_response(self):
        for message in ('SECRET',
                        'Device authorization did not return a device_code: {"token":"SECRET',
                        'Device authorization did not return a device_code: {"error":"SECRET"}'):
            self.assertNotIn('SECRET', failure_detail(Exception(message)))

    def test_only_stored_status_read_and_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            atomic_json(directory / 'config.json', dict(country='CY', username='', password='', vin=''))
            auth = Mock(spec=['login', 'refresh_tokens', 'get_stored_vehicle_data'])
            auth.login = AsyncMock(return_value=[{'vin': 'ONE'}])
            auth.refresh_tokens = AsyncMock(return_value=True)
            auth.get_stored_vehicle_data = AsyncMock(return_value=RAW)
            module = types.ModuleType('audi_connect')
            module.AudiAPI = Mock()
            module.AudiAuth = Mock(return_value=auth)
            tokens = types.ModuleType('audi_connect.token_store')
            tokens.TokenStore = Mock # subclass accepts positional path
            with patch.dict('sys.modules', {'audi_connect': module, 'audi_connect.token_store': tokens}):
                reader = AudiReader(directory)
                self.assertEqual(asyncio.run(reader.fetch(object()))['soc'], 58)
                asyncio.run(reader.fetch(object()))
                auth.login.assert_awaited_once()
                auth.refresh_tokens.assert_awaited_once_with(1800, force=True)
                self.assertEqual(auth.get_stored_vehicle_data.await_count, 2)
                auth.get_stored_vehicle_data.assert_awaited_with('ONE')

    def test_background_requires_interactive_approval(self):
        with self.assertRaises(RuntimeError):
            AudiReader(Path('/unused')).verification({'user_code': 'secret'})


if __name__ == '__main__':
    unittest.main()
