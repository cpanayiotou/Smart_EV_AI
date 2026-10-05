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

    def test_pair_declares_read_only(self):
        with patch.object(pairing, "PAIRING_CODE", "ABC"), patch.object(pairing, "_request") as request:
            request.return_value = {"connector_token": "secret"}
            self.assertEqual(pairing.pair(), "secret")
            body = request.call_args.args[2]
            self.assertTrue(body["read_only"])
            self.assertEqual(body["capabilities"], ["evcc.health", "evcc.state"])

    def test_no_control_commands_in_allowlist(self):
        source = pathlib.Path(__file__).with_name("pairing.py").read_text()
        for forbidden in ["maxcurrent", "phases", "mode/smart", "mode/now", "charge_start", "charge_stop"]:
            self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
