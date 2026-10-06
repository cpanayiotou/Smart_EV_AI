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

    def test_pair_matches_deployed_contract_and_declares_read_only(self):
        with patch.object(pairing, "PAIRING_CODE", "ABC"), patch.object(pairing, "_request") as request:
            request.return_value = {
                "protocol": "0.2", "connector_id": "id", "token": "secret",
                "capabilities": ["evcc.health", "evcc.state"], "poll_interval_s": 20,
            }
            self.assertEqual(pairing.pair(), ("secret", 20))
            self.assertEqual(request.call_args.args[0], "/api/public/local-connectors/pair")
            body = request.call_args.args[2]
            self.assertTrue(body["read_only"])
            self.assertEqual(body["capabilities"], ["evcc.health", "evcc.state"])

    def test_result_matches_deployed_contract(self):
        with patch.object(pairing, "_request") as request:
            pairing._result("token", "req", "evcc.state", True, data={"x": 1}, latency_ms=12.3)
            path, method, body = request.call_args.args[:3]
            self.assertEqual(path, "/api/public/local-connectors/result")
            self.assertEqual(method, "POST")
            self.assertEqual(body["command"], "evcc.state")
            self.assertEqual(body["data"], {"x": 1})
            self.assertNotIn("payload", body)

    def test_no_control_commands_in_allowlist(self):
        self.assertEqual(pairing.ALLOWED_COMMANDS, {"evcc.health", "evcc.state"})
        source = pathlib.Path(__file__).with_name("pairing.py").read_text()
        for forbidden in ["maxcurrent", "mode/smart", "mode/now", "charge_start", "charge_stop"]:
            self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
