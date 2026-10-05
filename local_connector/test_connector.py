import importlib.util
import pathlib
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("connector", pathlib.Path(__file__).with_name("app.py"))
connector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(connector)


class ConnectorTests(unittest.TestCase):
    def test_private_targets_only(self):
        self.assertTrue(connector._is_private_target("http://192.168.1.5:7070"))
        self.assertTrue(connector._is_private_target("http://evcc.local:7070"))
        self.assertTrue(connector._is_private_target("http://localhost:7070"))
        self.assertFalse(connector._is_private_target("https://8.8.8.8:7070"))

    @patch.object(connector, "_evcc_get")
    def test_health_verifies_evcc_state(self, get):
        get.return_value = (200, {"apiReady": True, "startupCompleted": True, "loadpoints": []}, 12.4)
        result = connector.health()
        self.assertTrue(result["verified_evcc"])
        self.assertEqual(result["status"], "ready")

    def test_source_has_no_evcc_write_request(self):
        source = pathlib.Path(__file__).with_name("app.py").read_text()
        self.assertNotIn('method="POST"', source)
        self.assertNotIn('method="PUT"', source)
        self.assertNotIn('method="PATCH"', source)
        self.assertNotIn('method="DELETE"', source)


if __name__ == "__main__":
    unittest.main()
