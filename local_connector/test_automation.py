from datetime import datetime, timezone
import os
import tempfile
import time
import unittest
import uuid
from unittest.mock import Mock, MagicMock, patch

import automation as a
import control
import pairing


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.env = patch.dict(os.environ, {'CONNECTOR_ALLOW_CONTROL': 'true', 'CONNECTOR_ALLOW_AUTOMATION': 'true'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.cap = patch('automation.capable', return_value=True)
        self.cap.start(); self.addCleanup(self.cap.stop)
        self.state = {'connected': True, 'charging': False, 'mode': 'off', 'effectiveLimitSoc': 80}
        self.reader = patch('control.state_loadpoint', side_effect=lambda _: dict(self.state))
        self.reader.start(); self.addCleanup(self.reader.stop)
        self.writer = patch('control.post_mode', side_effect=lambda _, m: self.state.update(mode=m))
        self.write = self.writer.start(); self.addCleanup(self.writer.stop)
        self.grant = Mock(return_value={'authorized': True})
        self.run = str(uuid.uuid4())
        self.end = iso(time.time() + 3600)
        a._monotonic_expiry.clear()

    def item(self, action='start'):
        return {'id': str(uuid.uuid4()), 'command': 'evcc.automation', 'params': {
            'loadpoint': 1, 'action': action, 'run_id': self.run,
            'expires_at': iso(time.time() + 45), 'lease_until': iso(time.time() + 90), 'deadline': self.end}}

    def execute(self, item=None):
        return a.execute(item or self.item(), self.grant, self.root)

    def test_start_renew_stop_and_mode_is_not_claim_of_charging(self):
        result = self.execute()
        self.assertEqual(result['mode'], 'now')
        self.assertNotIn('charging', result)
        self.execute(self.item('renew'))
        self.assertEqual(self.write.call_count, 1)
        self.execute(self.item('stop'))
        self.assertEqual(self.state['mode'], 'off')
        self.assertIsNone(a.read(self.root))

    def test_no_capability_no_calls(self):
        with patch('automation.capable', return_value=False), self.assertRaises(control.ControlError):
            self.execute()
        self.grant.assert_not_called(); self.write.assert_not_called()

    def test_native_evcc_limit_required_and_removal_stops_owned_run(self):
        for value in (None, 0, True, float('nan'), 101):
            self.state['effectiveLimitSoc'] = value
            with self.assertRaises(control.ControlError): self.execute()
        self.write.assert_not_called()
        self.state['effectiveLimitSoc'] = 80
        self.execute()
        self.state['effectiveLimitSoc'] = 0
        a.tick(self.root)
        self.assertEqual(self.state['mode'], 'off')

    def test_manual_pv_now_or_unknown_state_cannot_be_taken_over(self):
        for state in ({'mode': 'pv'}, {'mode': 'now'}, {'charging': None}, {'connected': False}):
            previous = dict(self.state); self.state.update(state)
            with self.assertRaises(control.ControlError):
                self.execute()
            self.state = previous
        self.write.assert_not_called()

    def test_reject_extra_fields_bad_ids_bool_loadpoint_and_expired(self):
        for key, value in [('url', 'http://bad'), ('loadpoint', True), ('run_id', 'bad'), ('action', 'set_current'), ('expires_at', iso(time.time()-1)), ('lease_until', iso(time.time()+121)), ('deadline', iso(time.time()+86410))]:
            command = self.item(); command['params'][key] = value
            with self.subTest(key=key), self.assertRaises(control.ControlError):
                self.execute(command)
        self.write.assert_not_called()

    def test_replay_and_restarting_finished_run_refused(self):
        command = self.item(); self.execute(command)
        with self.assertRaises(control.ControlError): self.execute(command)
        self.execute(self.item('stop'))
        with self.assertRaises(control.ControlError): self.execute()
        self.assertEqual(self.write.call_count, 2)

    def test_stop_and_renew_unknown_run_never_touch_mode(self):
        self.execute()
        for action in ('stop', 'renew'):
            command = self.item(action); command['params']['run_id'] = str(uuid.uuid4())
            with self.assertRaises(control.ControlError): self.execute(command)
        self.assertEqual(self.write.call_count, 1)

    def test_deadline_is_immutable(self):
        self.execute()
        command = self.item('renew'); command['params']['deadline'] = iso(time.time()+7200)
        with self.assertRaises(control.ControlError): self.execute(command)

    def test_denied_authorization_no_lease_or_write(self):
        self.grant.return_value = {'authorized': False}
        with self.assertRaises(control.ControlError): self.execute()
        self.assertIsNone(a.read(self.root)); self.write.assert_not_called()

    def test_state_rechecked_after_authorization(self):
        self.grant.side_effect = lambda _: self.state.update(connected=False) or {'authorized': True}
        with self.assertRaises(control.ControlError): self.execute()
        self.write.assert_not_called()

    def test_expiry_rechecked_after_authorization(self):
        command = self.item()
        self.grant.side_effect = lambda _: command['params'].update(expires_at=iso(time.time()-1)) or {'authorized': True}
        with self.assertRaises(control.ControlError): self.execute(command)
        self.write.assert_not_called()

    def test_ambiguous_start_retains_lease_for_stop(self):
        def ambiguous(_, mode):
            self.state['mode'] = mode
            raise TimeoutError()
        self.write.side_effect = ambiguous
        with self.assertRaises(TimeoutError): self.execute()
        self.assertIsNotNone(a.read(self.root))
        self.write.side_effect = lambda _, m: self.state.update(mode=m)
        a.tick(self.root, recovering=True)
        self.assertEqual(self.state['mode'], 'off')

    def test_lease_expiry_stops_even_without_cloud(self):
        self.execute()
        with patch('automation.time.time', return_value=time.time()+121): a.tick(self.root)
        self.assertEqual(self.state['mode'], 'off'); self.assertIsNone(a.read(self.root))

    def test_monotonic_expiry_handles_wall_clock_rollback(self):
        self.execute()
        a._monotonic_expiry[self.run] = time.monotonic()-1
        with patch('automation.time.time', return_value=time.time()-3600): a.tick(self.root)
        self.assertEqual(self.state['mode'], 'off')

    def test_recovery_and_disablement_stop_owned_session(self):
        for recovering in (False, True):
            self.run = str(uuid.uuid4()); self.execute()
            with patch('automation.enabled', return_value=False): a.tick(self.root, recovering=recovering)
            self.assertEqual(self.state['mode'], 'off')

    def test_manual_mode_change_relinquishes_without_post(self):
        self.execute(); self.state['mode'] = 'pv'
        a.tick(self.root)
        self.assertEqual(self.write.call_count, 1); self.assertIsNone(a.read(self.root))

    def test_disconnect_stops_and_run_does_not_restart(self):
        self.execute(); self.state['connected'] = False
        a.tick(self.root)
        self.state['connected'] = True
        with self.assertRaises(control.ControlError): self.execute()
        self.assertEqual(self.state['mode'], 'off')

    def test_failed_stop_retains_ownership_for_watchdog_retry(self):
        self.execute(); self.write.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): a.tick(self.root, recovering=True)
        self.assertIsNotNone(a.read(self.root))

    def test_manual_action_relinquishes_only_after_accepted_write(self):
        self.execute()
        manual = {'id': str(uuid.uuid4()), 'command': 'evcc.set_mode', 'params': {'loadpoint': 1, 'mode': 'off', 'expires_at': iso(time.time()+45)}}
        self.write.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): control.execute(manual, self.grant, self.root)
        self.assertIsNotNone(a.read(self.root))
        self.write.side_effect = lambda _, m: self.state.update(mode=m)
        manual['id'] = str(uuid.uuid4())
        control.execute(manual, self.grant, self.root)
        self.assertIsNone(a.read(self.root))

    def test_manual_other_loadpoint_does_not_drop_lease(self):
        self.execute(); a.relinquish(self.root, 2)
        self.assertIsNotNone(a.read(self.root))

    def test_journal_failure_blocks_start(self):
        with patch('automation.save', side_effect=OSError()), self.assertRaises(OSError): self.execute()
        self.write.assert_not_called()

    def test_capability_header_requires_healthy_local_watchdog(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'{}'
        with patch('pairing.urllib.request.build_opener', return_value=opener), patch.object(pairing, 'CLOUD_URL', 'https://cloud.example'):
            pairing._request('/api/public/local-connectors/work', token='test')
            self.assertEqual(opener.open.call_args.args[0].get_header('X-smart-ev-automation'), 'lease-v1')
            with patch('automation.capable', return_value=False):
                pairing._request('/api/public/local-connectors/work', token='test')
                self.assertIsNone(opener.open.call_args.args[0].get_header('X-smart-ev-automation'))
            pairing._request('/api/public/local-connectors/result', token='test')
            self.assertIsNone(opener.open.call_args.args[0].get_header('X-smart-ev-automation'))

    def test_work_dispatch_uses_automation_authorization_and_result(self):
        command = self.item()
        with patch('pairing._request') as request, patch('automation.execute') as execute, patch('pairing.time.sleep', side_effect=InterruptedError):
            request.side_effect = [{'requests': [command]}, {'authorized': True}, {'ok': True}]
            def run(received, authorize):
                self.assertEqual(authorize(received['id']), {'authorized': True})
                return {'verified': True}
            execute.side_effect = run
            with self.assertRaises(InterruptedError): pairing.run('test', Mock())
            self.assertEqual(request.call_args.args[2]['command'], 'evcc.automation')
            self.assertEqual(request.call_args_list[1].args[0], '/api/public/local-connectors/authorize')

    def test_watchdog_keeps_ownership_when_state_is_unavailable(self):
        self.execute()
        with patch('control.state_loadpoint', side_effect=TimeoutError()), self.assertRaises(TimeoutError): a.tick(self.root)
        self.assertIsNotNone(a.read(self.root))

    def test_renewal_after_monotonic_expiry_never_extends_lease(self):
        self.execute(); a._monotonic_expiry[self.run] = time.monotonic()-1
        before = a.read(self.root)
        with self.assertRaises(control.ControlError): self.execute(self.item('renew'))
        self.assertEqual(before, a.read(self.root))


if __name__ == '__main__':
    unittest.main()
