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
        self.assertEqual(pairing.ALLOWED_COMMANDS, {"evcc.health", "evcc.state"})
        source = pathlib.Path(__file__).with_name("pairing.py").read_text()
        for forbidden in ["maxcurrent", "mode/smart", "mode/now", "charge_start", "charge_stop"]:
            self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
