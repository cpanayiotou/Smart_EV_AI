import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import app
import pairing
from setup_web import Handler, Setup, local_address


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.worker = Mock()
        self.state = Setup(self.directory.name, self.worker)
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.setup_state = self.state
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def request(self, path, method='GET', body=None, auth=True, **headers):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        if auth:
            headers['X-Setup-Password'] = self.state.password
        if body is not None:
            body = json.dumps(body)
            headers.setdefault('Content-Type', 'application/json')
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        status, raw = response.status, response.read().decode()
        connection.close()
        return status, raw

    def test_access_boundaries(self):
        self.assertEqual(self.request('/')[0], 200)
        self.assertEqual(self.request('/api/setup/status', auth=False)[0], 401)
        self.assertEqual(self.request('/v1/evcc/state', auth=False)[0], 401)
        self.assertEqual(self.request('/', Host='evil.example')[0], 403)
        self.assertEqual(self.request('/api/setup/pair', 'POST', {})[0], 403)
        self.assertEqual(self.request('/api/setup/pair', 'POST', {}, Origin='https://evil.example')[0], 403)
        self.assertEqual(self.request('/anything', 'DELETE')[0], 405)
        self.assertFalse(local_address('8.8.8.8'))
        self.assertFalse(local_address('0.0.0.0'))
        self.assertTrue(local_address('192.168.1.2'))

    @patch('app.health', return_value={'verified_evcc': True})
    @patch('pairing.pair', return_value=('secret-test-token', 15))
    def test_pair_persist_restart_and_redaction(self, pair, health):
        origin = 'http://127.0.0.1:' + str(self.server.server_port)
        status, raw = self.request('/api/setup/pair', 'POST', {'cloud_url': 'https://cloud.example', 'pairing_code': 'ABCD-EFGH'}, Origin=origin)
        self.assertEqual(status, 200)
        self.assertNotIn('secret-test-token', raw)
        status, raw = self.request('/api/setup/status')
        self.assertNotIn('secret-test-token', raw)
        self.assertNotIn('ABCD-EFGH', raw)
        self.assertEqual(pairing.PAIRING_CODE, '')
        worker = Mock()
        restored = Setup(self.directory.name, worker)
        self.assertEqual(restored.config['token'], 'secret-test-token')
        worker.assert_called_once()
        self.assertEqual(self.state.pair('https://other.example', 'CODE')[0], 409)
        if __import__('os').name == 'posix':
            self.assertEqual((Path(self.directory.name) / 'connector.json').stat().st_mode & 0o777, 0o600)

    @patch('pairing.pair', side_effect=ValueError('secret upstream response'))
    def test_failure_is_redacted_and_retry_limited(self, pair):
        status, result = self.state.pair('https://cloud.example', 'CODE')
        self.assertEqual(status, 502)
        self.assertNotIn('secret upstream', str(result))
        self.assertFalse((Path(self.directory.name) / 'connector.json').exists())
        self.assertEqual(self.state.pair('https://cloud.example', 'CODE')[0], 429)

    def test_unknown_cloud_work_never_reads_evcc(self):
        reader = Mock()
        with patch('pairing._request') as request, patch('pairing.time.sleep', side_effect=InterruptedError):
            request.side_effect = [{'requests': [{'request_id': 'r', 'command': 'charge_start'}]}, {}]
            with self.assertRaises(InterruptedError):
                pairing.run('test-token', reader)
            reader.assert_not_called()
            result = request.call_args.args[2]
            self.assertFalse(result['ok'])
            self.assertEqual(result['error'], 'unsupported_read_only_command')

    def test_cloud_origins_and_redirects(self):
        for url in ['http://cloud.example', 'https://user:pass@cloud.example', 'https://cloud.example/path', 'https://cloud.example?secret=x', 'https://cloud.example:444']:
            with self.assertRaises(ValueError):
                pairing.validate_cloud_url(url)
        with self.assertRaises(ValueError):
            pairing.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example')

    @patch('pairing.pair', return_value=('secret-test-token', 15))
    @patch('setup_web.save_secret', side_effect=OSError('disk full'))
    def test_storage_failure_does_not_start_worker(self, save, pair):
        self.assertEqual(self.state.pair('https://cloud.example', 'CODE')[0], 502)
        self.worker.assert_not_called()
        self.assertIsNone(self.state.config)


if __name__ == '__main__':
    unittest.main()
