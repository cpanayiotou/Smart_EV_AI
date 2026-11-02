"""Target contract tests: all evcc writes mocked, never contact hardware."""
from datetime import datetime, timezone
import os
import tempfile
import time
import unittest
from unittest.mock import Mock, MagicMock, patch
import control
import pairing

POST_TARGET = control.post_target


def request():
    return {'id': '11111111-1111-4111-8111-111111111111', 'command': 'evcc.set_target',
            'params': {'loadpoint': 1, 'target_soc': 74, 'expected_limit_soc': 80,
                       'expires_at': datetime.fromtimestamp(time.time()+45, timezone.utc).isoformat()}}


def state(limit=80, **extra):
    return dict(connected=True, charging=False, mode='off', limitSoc=limit,
                effectiveLimitSoc=limit) | extra


class TargetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = directory.name
        self.env = patch.dict(os.environ, {'CONNECTOR_ALLOW_CONTROL': 'true'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.read = self.enterContext(patch('control.state_loadpoint', return_value=state()))
        self.write = self.enterContext(patch('control.post_target'))
        self.mode = self.enterContext(patch('control.post_mode'))
        self.enterContext(patch('control.time.sleep'))
        self.grant = Mock(return_value={'authorized': True})

    def execute(self, item=None):
        return control.execute(item or request(), self.grant, self.root)

    def test_verified_target_does_not_start_or_replay(self):
        self.read.side_effect = [state(), state(), state(74)]
        self.assertEqual(self.execute(), {'loadpoint': 1, 'target_soc': 74, 'verified': True, 'mode': 'off'})
        self.write.assert_called_once_with(1, 74)
        self.mode.assert_not_called()
        self.read.side_effect = None
        with self.assertRaises(control.ControlError): self.execute()
        self.assertEqual(self.write.call_count, 1)
        self.assertEqual(self.grant.call_count, 1)

    def test_disabled_no_reads_or_writes(self):
        with patch.dict(os.environ, {'CONNECTOR_ALLOW_CONTROL': 'false'}):
            with self.assertRaises(control.ControlError): self.execute()
        self.read.assert_not_called()
        self.write.assert_not_called()

    def test_strict_target_params(self):
        for key, value in [('target_soc', True), ('target_soc', 0), ('target_soc', 81),
                           ('target_soc', 74.0), ('target_soc', '74'), ('expected_limit_soc', False),
                           ('expected_limit_soc', 0), ('expected_limit_soc', 101),
                           ('loadpoint', True), ('loadpoint', 21), ('url', 'http://other'),
                           ('expires_at', '2000-01-01T00:00:00Z')]:
            item = request(); item['params'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(control.ControlError): self.execute(item)
        self.write.assert_not_called()
        self.grant.assert_not_called()

    def test_unready_state_and_changed_limit(self):
        for extra in [{'connected': False}, {'charging': True}, {'charging': None},
                      {'mode': 'now'}, {'mode': 'pv'}, {'effectiveLimitSoc': 79},
                      {'effectiveLimitSoc': None}, {'effectiveLimitSoc': True}]:
            self.read.return_value = state(**extra)
            with self.subTest(extra=extra), self.assertRaises(control.ControlError): self.execute()
        self.write.assert_not_called()
        self.grant.assert_not_called()

    def test_lease_blocks_target_without_relinquishing(self):
        with patch('automation.read', return_value={'run_id': 'active'}), patch('automation.relinquish') as release:
            with self.assertRaises(control.ControlError): self.execute()
            release.assert_not_called()
        self.write.assert_not_called()

    def test_denial_does_not_write(self):
        self.grant.return_value = {'authorized': False}
        with self.assertRaises(control.ControlError): self.execute()
        self.write.assert_not_called()

    def test_state_change_after_grant_prevents_write(self):
        self.read.side_effect = [state(), state(mode='now')]
        with self.assertRaises(control.ControlError): self.execute()
        self.write.assert_not_called()

    def test_lease_arriving_after_grant_prevents_write(self):
        with patch('automation.read', side_effect=[None, {'run_id': 'active'}]):
            with self.assertRaises(control.ControlError): self.execute()
        self.write.assert_not_called()

    def test_expiry_after_grant(self):
        item = request()
        def grant(_):
            item['params']['expires_at'] = '2000-01-01T00:00:00Z'
            return {'authorized': True}
        self.grant.side_effect = grant
        with self.assertRaises(control.ControlError): self.execute(item)
        self.write.assert_not_called()

    def test_ambiguous_failure_not_replayed(self):
        self.write.side_effect = TimeoutError
        with self.assertRaises(TimeoutError): self.execute()
        with self.assertRaises(control.ControlError): self.execute()
        self.write.assert_called_once()

    def test_readback_must_verify_actual_session_and_effective_limit(self):
        self.read.side_effect = [state(), state()] + [state(74, limitSoc=0)] * 3
        with self.assertRaisesRegex(control.ControlError, 'not verified'): self.execute()
        self.mode.assert_not_called()

    def test_disconnection_after_write_not_success(self):
        self.read.side_effect = [state(), state()] + [state(74, connected=False)] * 3
        with self.assertRaisesRegex(control.ControlError, 'not verified'): self.execute()

    def test_fixed_local_post_no_redirects(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.status = 200
        with patch('control.urllib.request.build_opener', return_value=opener), patch.object(control.app, 'EVCC_URL', 'http://127.0.0.1:7070'):
            POST_TARGET(1, 74)
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, 'http://127.0.0.1:7070/api/loadpoints/1/limitsoc/74')
        self.assertEqual(req.method, 'POST')

    def test_capability_local_opt_in(self):
        opener = MagicMock(); opener.open.return_value.__enter__.return_value.read.return_value = b'{}'
        with patch('pairing.urllib.request.build_opener', return_value=opener), patch.object(pairing, 'CLOUD_URL', 'https://cloud.example'):
            pairing._request('/api/public/local-connectors/work', token='test')
            self.assertEqual(opener.open.call_args.args[0].get_header('X-smart-ev-target'), 'target-v1')
            with patch.dict(os.environ, {'CONNECTOR_ALLOW_CONTROL': 'false'}):
                pairing._request('/api/public/local-connectors/work', token='test')
            self.assertIsNone(opener.open.call_args.args[0].get_header('X-smart-ev-target'))

    def test_target_dispatch_uses_authorization_and_result(self):
        item = request()
        with patch('pairing._request') as cloud, patch('control.execute') as execute, patch('pairing.time.sleep', side_effect=InterruptedError):
            cloud.side_effect = [{'requests': [item]}, {'authorized': True}, {'ok': True}]
            def run(received, authorize):
                self.assertEqual(authorize(received['id']), {'authorized': True})
                return {'loadpoint': 1, 'target_soc': 74, 'verified': True, 'mode': 'off'}
            execute.side_effect = run
            with self.assertRaises(InterruptedError): pairing.run('test', Mock())
            self.assertEqual(cloud.call_args.args[2]['command'], 'evcc.set_target')
            self.assertEqual(cloud.call_args.args[2]['data']['target_soc'], 74)


if __name__ == '__main__': unittest.main()
