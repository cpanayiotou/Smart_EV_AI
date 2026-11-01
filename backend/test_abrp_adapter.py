import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import HTTPServer
from unittest.mock import Mock, patch

from abrp_adapter import (Client, CredentialStore, State, Transport, Unavailable,
                          handler, login, normalize, poll, tokens, TELEMETRY, ACCOUNTS, REDIRECT)

NOW = 1800000000


def fixture(soc=51, timestamp=NOW - 10):
    return [{"vehicle_id": 123, "tlm_authorized": True, "tlm": {
        "soc": soc, "utc": NOW, "timestamps": {"soc": timestamp},
        "providers": {"soc": "enode"}}}]


class SafetyTests(unittest.TestCase):
    def test_login_pkce_state_and_local_persistence(self):
        from urllib.parse import parse_qs, urlparse, urlencode
        for correct_state in (True, False):
            http, store = Mock(), Mock()
            cookie = Mock()
            cookie.name, cookie.domain, cookie.value = "_csrf", "accounts.abetterrouteplanner.com", "csrf-fixture"
            http.cookies = [cookie]
            state = None
            def request(url, **kwargs):
                nonlocal state
                if "/authorize?" in url:
                    query = parse_qs(urlparse(url).query)
                    self.assertEqual(query["code_challenge_method"], ["S256"])
                    state = query["state"][0]
                    return ACCOUNTS + "/login/abrp?session=session-fixture"
                if "/status?" in url:
                    return {"approved": True}
                if "/login/abrp?" in url:
                    return 'connect_session_token=fixture-link'
                if url.endswith("/login/abrp"):
                    return REDIRECT + "?" + urlencode({"code": "code-fixture", "state": state if correct_state else "wrong"})
                self.assertEqual(url, ACCOUNTS + "/token")
                self.assertIn("code_verifier", kwargs["body"])
                return {"access_token": "access-fixture", "refresh_token": "refresh-fixture", "expires_in": 900}
            http.request.side_effect = request
            with patch("abrp_adapter.time.sleep"), patch("builtins.print"):
                if correct_state:
                    login(http, store)
                    store.write.assert_called_once_with("refresh-fixture")
                else:
                    with self.assertRaisesRegex(Unavailable, "login_state_mismatch"):
                        login(http, store)
                    store.write.assert_not_called()

    def test_http_error_never_discloses_upstream_secret(self):
        import io
        for code, reason in ((400, "auth_required"), (401, "auth_required"), (429, "rate_limited"), (500, "upstream_http")):
            http = Transport()
            http.opener = Mock()
            http.opener.open.side_effect = HTTPError(ACCOUNTS + "/token", code, "SECRET", {}, io.BytesIO(b"SECRET"))
            with self.assertRaises(Unavailable) as caught:
                http.request(ACCOUNTS + "/token", body={"refresh_token": "SECRET"}, form=True)
            self.assertEqual(str(caught.exception), reason)

    def test_valid_and_zero(self):
        for value in (0, 51.5, 100):
            self.assertEqual(normalize(fixture(value), 123, NOW)["soc_percent"], value)

    def test_invalid_soc(self):
        for value in (-1, 101, True, "50", None, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(Unavailable):
                normalize(fixture(value), 123, NOW)

    def test_timestamp_never_uses_latest_response(self):
        for value in (None, True, "1800000000", 0, NOW + 31, NOW * 1000, float("nan")):
            with self.subTest(value=value), self.assertRaises(Unavailable):
                normalize(fixture(timestamp=value), 123, NOW)

    def test_vehicle_selection(self):
        for items in ([], fixture() * 2, [{"vehicle_id": True}]):
            with self.assertRaises(Unavailable):
                normalize(items, 123, NOW)
        items = [{"vehicle_id": 456, "tlm": {"soc": 99}}] + fixture()
        self.assertEqual(normalize(items, 123, NOW)["soc_percent"], 51)

    def test_provider_and_authorization(self):
        for provider in (None, "obdble", "unknown"):
            items = fixture()
            items[0]["tlm"]["providers"]["soc"] = provider
            with self.assertRaises(Unavailable):
                normalize(items, 123, NOW)
        items = fixture()
        items[0]["tlm_authorized"] = False
        with self.assertRaises(Unavailable):
            normalize(items, 123, NOW)

    def test_staleness_ages_without_poll_and_survives_clock_rollback(self):
        state = State(123, 900)
        state.update(fixture(), NOW, 100)
        self.assertEqual(state.response(NOW + 890, 990)[0], 200)
        for wall in (NOW + 901, NOW - 100):
            code, data = state.response(wall, 1001)
            self.assertEqual(code, 503)
            self.assertIsNone(data["soc_percent"])

    def test_old_soc_with_fresh_other_fields(self):
        state = State(123)
        state.update(fixture(timestamp=NOW - 901), NOW, 100)
        self.assertEqual(state.response(NOW, 100)[0], 503)
        sample = state.response(NOW, 100)[1]
        self.assertEqual(sample['last_known_soc_percent'], 51)
        self.assertTrue(sample['stale'])
        self.assertTrue(sample['display_available'])
        self.assertIsNone(sample['soc_percent'])

    def test_failure_clears_available_and_recovery(self):
        state = State(123)
        state.update(fixture(), NOW, 100)
        state.fail("upstream_unavailable")
        self.assertIsNone(state.response(NOW, 100)[1]["soc_percent"])
        state.update(fixture(), NOW, 100)
        self.assertEqual(state.response(NOW, 100)[0], 200)

    def test_regression_and_same_timestamp_changed_value(self):
        state = State(123)
        state.update(fixture(), NOW, 100)
        for items in (fixture(timestamp=NOW-11), fixture(soc=52)):
            with self.assertRaises(Unavailable):
                state.update(items, NOW, 101)

    def test_transport_rejects_mutations_and_other_hosts(self):
        for url in ("http://127.0.0.1:7070/api/loadpoints/1/mode/now",
                    "https://api.iternio.com/1/session/set_settings",
                    "https://evil.example/token"):
            with self.assertRaises(Unavailable):
                Transport().request(url, body={})

    def test_token_validation(self):
        for data in (None, {}, {"access_token": "secret", "refresh_token": "secret", "expires_in": True}):
            with self.assertRaises(Unavailable):
                tokens(data)

    def test_rotation_persisted_before_telemetry(self):
        http, store = Mock(), Mock()
        store.read.return_value = "old-secret"
        http.request.side_effect = [{"access_token": "access-secret", "refresh_token": "new-secret", "expires_in": 900},
                                    {"status": "ok", "result": fixture()}]
        client = Client(http, store)
        client.metadata = Mock(return_value="public-web-key")
        self.assertEqual(client.fetch(), fixture())
        store.write.assert_called_once_with("new-secret")
        self.assertEqual(http.request.call_args.args, (TELEMETRY,))
        store.write.side_effect = OSError("disk full")
        client.access = None
        http.request.side_effect = [{"access_token": "access-secret", "refresh_token": "new-secret", "expires_in": 900}]
        before = http.request.call_count
        with self.assertRaises(OSError):
            client.fetch()
        self.assertEqual(http.request.call_count, before + 1)

    def test_private_store_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder).chmod(0o700)
            store = CredentialStore(Path(folder) / "tokens.json")
            store.write("fixture-token")
            self.assertEqual(store.read(), "fixture-token")
            store.write("rotated-token")
            self.assertEqual(store.read(), "rotated-token")
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_poll_revocation_stops_and_redacts(self):
        state, client, stop = State(123), Mock(), threading.Event()
        client.fetch.side_effect = Unavailable("auth_required")
        poll(client, state, stop, 600)
        self.assertEqual(client.fetch.call_count, 1)
        self.assertEqual(state.response()[1]["reason"], "auth_required")


class HttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.state = State(123)
        self.server = HTTPServer(("127.0.0.1", 0), handler(self.state))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def test_readonly_http_contract(self):
        import time
        now = time.time()
        self.state.update(fixture(timestamp=now - 10))
        with urlopen(self.base + "/v1/abrp/soc") as response:
            self.assertEqual(response.read(), b"51")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        with urlopen(self.base + "/v1/abrp/telemetry") as response:
            data = json.load(response)
            self.assertEqual(data["source"], "abrp/enode")
            self.assertTrue(data["read_only"])
            self.assertNotIn("session_id", data)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.base + "/v1/abrp/soc", method=method))
            self.assertEqual(caught.exception.code, 405)
            caught.exception.close()
        self.state.fail("upstream_unavailable")
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + "/v1/abrp/soc")
        self.assertEqual(caught.exception.code, 503)
        self.assertIsNone(json.load(caught.exception)["soc_percent"])
        caught.exception.close()

    def test_stale_display_is_200_but_soc_is_503(self):
        import time
        self.state.update(fixture(timestamp=time.time()-4800))
        with urlopen(self.base + '/v1/abrp/display') as response:
            data = json.load(response)
            self.assertTrue(data['stale'])
            self.assertFalse(data['available'])
            self.assertEqual(data['last_known_soc_percent'], 51)
            self.assertIsNone(data['soc_percent'])
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + '/v1/abrp/soc')
        self.assertEqual(caught.exception.code, 503)
        caught.exception.close()


if __name__ == "__main__":
    unittest.main()
