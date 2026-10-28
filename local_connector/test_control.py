from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, MagicMock, patch
import control
import pairing


def item(mode='now'):
    return {'id': '11111111-1111-4111-8111-111111111111', 'command': 'evcc.set_mode',
            'params': {'loadpoint': 1, 'mode': mode,
                       'expires_at': datetime.fromtimestamp(time.time()+45, timezone.utc).isoformat()}}


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env = patch.dict(os.environ, {'CONNECTOR_ALLOW_CONTROL': 'true'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_default_disabled_never_reads_or_writes(self):
        with patch.dict(os.environ, {'CONNECTOR_ALLOW_CONTROL': 'false'}), patch('control.state_loadpoint') as read, patch('control.post_mode') as write:
            with self.assertRaises(control.ControlError):
                control.execute(item(), Mock(), self.directory.name)
            read.assert_not_called()
            write.assert_not_called()

    def test_expired_invalid_and_extra_parameters_fail_closed(self):
        bad=[]
        for key,value in [('mode','smart'),('mode','now/../../settings'),('loadpoint',True),('loadpoint',0),('loadpoint',21),('expires_at','2000-01-01T00:00:00Z')]:
            command=item();command['params'][key]=value;bad.append(command)
        command=item();command['params']['url']='https://evil.example';bad.append(command)
        command=item();command['id']='invalid';bad.append(command)
        with patch('control.post_mode') as write:
            for command in bad:
                with self.subTest(command=command), self.assertRaises(control.ControlError):
                    control.execute(command, Mock(), self.directory.name)
            write.assert_not_called()

    @patch('control.post_mode')
    @patch('control.state_loadpoint', return_value={'connected': True, 'mode': 'now'})
    def test_requires_authorization_and_never_replays(self, read, write):
        authorize=Mock(return_value={'authorized': True})
        command=item()
        result=control.execute(command,authorize,self.directory.name)
        self.assertEqual(result, {'loadpoint':1,'mode':'now','verified':True})
        write.assert_called_once_with(1,'now')
        authorize.assert_called_once_with(command['id'])
        with self.assertRaises(control.ControlError):
            control.execute(command,authorize,self.directory.name)
        self.assertEqual(write.call_count,1)
        self.assertEqual(authorize.call_count,1)

    @patch('control.post_mode')
    @patch('control.state_loadpoint', return_value={'connected': True})
    def test_denied_authorization_does_not_write(self,read,write):
        with self.assertRaises(control.ControlError):
            control.execute(item(),Mock(return_value={'authorized':False}),self.directory.name)
        write.assert_not_called()

    @patch('control.post_mode')
    @patch('control.state_loadpoint', return_value={'connected': False,'mode':'off'})
    def test_disconnected_start_rejected_but_stop_allowed(self,read,write):
        with self.assertRaises(control.ControlError):
            control.execute(item(),Mock(),self.directory.name)
        write.assert_not_called()
        control.execute(item('off'),Mock(return_value={'authorized':True}),self.directory.name)
        write.assert_called_once_with(1,'off')

    @patch('control.post_mode', side_effect=TimeoutError)
    @patch('control.state_loadpoint', return_value={'connected': True})
    def test_ambiguous_write_failure_never_replayed(self,read,write):
        command=item()
        with self.assertRaises(TimeoutError):
            control.execute(command,Mock(return_value={'authorized':True}),self.directory.name)
        with self.assertRaises(control.ControlError):
            control.execute(command,Mock(return_value={'authorized':True}),self.directory.name)
        self.assertEqual(write.call_count,1)

    @patch('control.time.sleep')
    @patch('control.post_mode')
    @patch('control.state_loadpoint', return_value={'connected': True,'mode':'off'})
    def test_readback_required(self,read,write,sleep):
        with self.assertRaisesRegex(control.ControlError,'could not be verified'):
            control.execute(item(),Mock(return_value={'authorized':True}),self.directory.name)

    @patch('control.post_mode')
    @patch('control.state_loadpoint', return_value={'connected': True})
    def test_expiry_rechecked_after_authorization(self,read,write):
        command=item()
        def authorize(_):
            command['params']['expires_at']='2000-01-01T00:00:00Z'
            return {'authorized':True}
        with self.assertRaises(control.ControlError):
            control.execute(command,authorize,self.directory.name)
        write.assert_not_called()

    def test_capability_advertised_only_when_locally_enabled(self):
        opener=MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value=b'{}'
        with patch('pairing.urllib.request.build_opener',return_value=opener), patch.object(pairing,'CLOUD_URL','https://cloud.example'):
            pairing._request('/api/public/local-connectors/work',token='test')
            self.assertEqual(opener.open.call_args.args[0].get_header('X-smart-ev-control'),'mode-v1')
            with patch.dict(os.environ,{'CONNECTOR_ALLOW_CONTROL':'false'}):
                pairing._request('/api/public/local-connectors/work',token='test')
            self.assertIsNone(opener.open.call_args.args[0].get_header('X-smart-ev-control'))

    def test_hardware_write_uses_only_fixed_local_endpoint_and_no_redirects(self):
        opener=MagicMock()
        opener.open.return_value.__enter__.return_value.status=200
        with patch('control.urllib.request.build_opener',return_value=opener), patch.object(control.app,'EVCC_URL','http://127.0.0.1:7070'):
            control.post_mode(1,'off')
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,'http://127.0.0.1:7070/api/loadpoints/1/mode/off')
        self.assertEqual(request.method,'POST')

    @patch('control.post_mode')
    @patch('control.reserve', side_effect=OSError('storage unavailable'))
    @patch('control.state_loadpoint', return_value={'connected': True})
    def test_durable_journal_required_before_authorization(self,read,reserve,write):
        authorize=Mock()
        with self.assertRaises(OSError):
            control.execute(item(),authorize,self.directory.name)
        authorize.assert_not_called()
        write.assert_not_called()

    def test_work_dispatch_authorizes_control_separately_from_reads(self):
        command=item()
        with patch('pairing._request') as request, patch('control.execute') as execute, patch('pairing.time.sleep',side_effect=InterruptedError):
            request.side_effect=[{'requests':[command]}, {'authorized':True}, {'ok':True}]
            def run_command(received, authorize):
                self.assertEqual(authorize(received['id']), {'authorized':True})
                return {'loadpoint':1,'mode':'now','verified':True}
            execute.side_effect=run_command
            reader=Mock()
            with self.assertRaises(InterruptedError):
                pairing.run('test-token',reader)
            self.assertEqual(request.call_args_list[1].args[0],'/api/public/local-connectors/authorize')
            self.assertEqual(request.call_args.args[2]['data']['verified'],True)
            reader.assert_not_called()


if __name__=='__main__':
    unittest.main()
