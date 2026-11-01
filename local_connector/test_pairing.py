import importlib.util
import pathlib
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("pairing", pathlib.Path(__file__).with_name("pairing.py"))
pairing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pairing)


class PairingTests(unittest.TestCase):
    def test_https_required(self):
        with patch.object(pairing, "CLOUD_URL", "http://example.test"):
            with self.assertRaises(ValueError):
                pairing._request("/x")

    def test_pair_matches_cloud_strict_schema(self):
        with patch.object(pairing, "PAIRING_CODE", "ABC"), patch.object(pairing, "_request") as request:
            request.return_value = {
                "protocol": "0.2", "connector_id": "id", "token": "secret",
                "capabilities": ["evcc.health", "evcc.state"], "poll_interval_s": 20,
            }
            self.assertEqual(pairing.pair(), ("secret", 20))
            self.assertEqual(request.call_args.args[0], "/api/public/local-connectors/pair")
            body = request.call_args.args[2]
            self.assertEqual(body, {"code": "ABC", "version": "0.3"})

    def test_result_matches_deployed_contract(self):
        with patch.object(pairing, "_request") as request:
            pairing._result("token", "req", "evcc.state", True, data={"x": 1}, latency_ms=12.3)
            path, method, body = request.call_args.args[:3]
            self.assertEqual(path, "/api/public/local-connectors/result")
            self.assertEqual(method, "POST")
            self.assertEqual(body["command"], "evcc.state")
            self.assertEqual(body["data"], {"x": 1})
            self.assertNotIn("payload", body)
            self.assertEqual(body["latency_ms"], 12)
            self.assertIsInstance(body["latency_ms"], int)

    def test_cloud_work_id_and_raw_state_roundtrip(self):
        from cloud_main import state_payload
        state = {"version": "0.1", "loadpoints": [{"vehicleSoc": 64, "charging": False}]}
        request_id = '00000000-0000-4000-8000-000000000001'
        with patch('app._evcc_get', return_value=(200, state, 1.2)):
            self.assertEqual(state_payload(), state)
        with patch.object(pairing, '_request') as request, patch.object(pairing.time, 'sleep', side_effect=InterruptedError):
            request.side_effect = [{'requests': [{'id': request_id, 'command': 'evcc.state', 'params': {}}]}, {'ok': True}]
            with self.assertRaises(InterruptedError):
                pairing.run('token', lambda: state)
            body = request.call_args.args[2]
            self.assertEqual(body['request_id'], request_id)
            self.assertEqual(body['data'], state)
            self.assertTrue(body['ok'])
            self.assertIsInstance(body['latency_ms'], int)

    def test_failed_result_uses_cloud_error_object(self):
        with patch.object(pairing, '_request') as request:
            pairing._result('token', 'id', 'evcc.state', False, error='unreachable', latency_ms=1.6)
            body = request.call_args.args[2]
            self.assertEqual(body['error'], {'code': 'unreachable'})
            self.assertEqual(body['latency_ms'], 2)

    def test_no_control_commands_in_allowlist(self):
        self.assertEqual(pairing.ALLOWED_COMMANDS, {"evcc.health", "evcc.state", "abrp.fields"})
        source = pathlib.Path(__file__).with_name("pairing.py").read_text()
        for forbidden in ["maxcurrent", "mode/smart", "mode/now", "charge_start", "charge_stop"]:
            self.assertNotIn(forbidden, source.lower())

    def test_abrp_roundtrip_independent_of_evcc(self):
        payload = {'read_only': True, 'fields': {'soc': {'value': 74}}}
        with patch.dict(pairing.os.environ, {'CONNECTOR_ABRP_READONLY': 'true'}), \
                patch.object(pairing, '_request') as request, \
                patch.object(pairing.time, 'sleep', side_effect=InterruptedError):
            request.side_effect = [{'requests': [{'id': 'id', 'command': 'abrp.fields', 'params': {}}]}, {'ok': True}]
            with self.assertRaises(InterruptedError):
                pairing.run('token', lambda: self.fail('evcc must not be read'), abrp_reader=lambda: payload)
            body = request.call_args.args[2]
            self.assertEqual(body['command'], 'abrp.fields')
            self.assertEqual(body['data'], payload)
            self.assertTrue(body['ok'])

    def test_abrp_disabled_or_remote_parameters_never_read(self):
        for enabled, params in [('false', {}), ('true', {'url': 'http://example.test'})]:
            with self.subTest(enabled=enabled, params=params), \
                    patch.dict(pairing.os.environ, {'CONNECTOR_ABRP_READONLY': enabled}), \
                    patch.object(pairing, '_request') as request, \
                    patch.object(pairing.time, 'sleep', side_effect=InterruptedError):
                request.side_effect = [{'requests': [{'id': 'id', 'command': 'abrp.fields', 'params': params}]}, {'ok': True}]
                with self.assertRaises(InterruptedError):
                    pairing.run('token', lambda: {}, abrp_reader=lambda: self.fail('must not read'))
                body = request.call_args.args[2]
                self.assertFalse(body['ok'])
                self.assertNotIn('data', body)

    def test_abrp_failure_does_not_block_next_evcc_result(self):
        def unavailable():
            raise RuntimeError('private upstream detail')
        with patch.dict(pairing.os.environ, {'CONNECTOR_ABRP_READONLY': 'true'}), \
                patch.object(pairing, '_request') as request, \
                patch.object(pairing.time, 'sleep', side_effect=InterruptedError):
            request.side_effect = [{'requests': [
                {'id': 'a', 'command': 'abrp.fields', 'params': {}},
                {'id': 'b', 'command': 'evcc.state', 'params': {}}]}, {'ok': True}, {'ok': True}]
            with self.assertRaises(InterruptedError):
                pairing.run('token', lambda: {'version': 'test'}, abrp_reader=unavailable)
            failed = request.call_args_list[1].args[2]
            self.assertFalse(failed['ok'])
            self.assertNotIn('private', str(failed))
            self.assertTrue(request.call_args_list[2].args[2]['ok'])

    def test_cloud_abrp_reader_only_returns_validated_fields(self):
        from cloud_main import abrp_payload
        with patch('abrp.read_fields', return_value=(503, {'reason': 'unavailable'})):
            with self.assertRaises(RuntimeError):
                abrp_payload()
        with patch('abrp.read_fields', return_value=(200, {'fields': {}})):
            self.assertEqual(abrp_payload(), {'fields': {}})

    def test_capability_header_only_on_enabled_work_poll(self):
        from unittest.mock import MagicMock
        for enabled, path, expected in [
                ('true', '/api/public/local-connectors/work', 'abrp-fields-v1'),
                ('false', '/api/public/local-connectors/work', None),
                ('true', '/api/public/local-connectors/result', None)]:
            with self.subTest(enabled=enabled, path=path), \
                    patch.dict(pairing.os.environ, {'CONNECTOR_ABRP_READONLY': enabled}), \
                    patch.object(pairing, 'CLOUD_URL', 'https://example.test'), \
                    patch.object(pairing.urllib.request, 'build_opener') as build:
                response = MagicMock()
                response.__enter__.return_value.read.return_value = b'{}'
                build.return_value.open.return_value = response
                pairing._request(path, token='test-token')
                req = build.return_value.open.call_args.args[0]
                self.assertEqual(req.get_header('X-smart-ev-telemetry'), expected)


if __name__ == "__main__":
    unittest.main()
