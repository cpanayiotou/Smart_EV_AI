import copy
import importlib.util
import json
import io
import os
import tarfile
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install_abrp.py'))
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_extracted_source_is_readable_despite_private_umask(self):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w:gz') as stream:
            member = tarfile.TarInfo('repo/local_connector/abrp.py')
            payload = b'# public source\n'
            member.size = len(payload)
            member.mode = 0o600
            stream.addfile(member, io.BytesIO(payload))
        with tempfile.TemporaryDirectory() as folder:
            previous = os.umask(0o077)
            try:
                with patch.object(installer.urllib.request, 'urlopen', return_value=io.BytesIO(archive.getvalue())):
                    installer.extract('fixture', Path(folder), ['local_connector'])
            finally:
                os.umask(previous)
            source = Path(folder) / 'local_connector/abrp.py'
            self.assertEqual(source.read_bytes(), payload)
            if os.name == 'posix':
                self.assertEqual(source.stat().st_mode & 0o777, 0o644)

    def test_upgrade_rejects_unrecognized_adapter(self):
        self.assertTrue(installer.known_adapter(b'new', b'new'))
        self.assertFalse(installer.known_adapter(b'custom local edit', b'new'))
        with patch.object(installer, 'PREVIOUS_ADAPTER_SHA256', installer.hashlib.sha256(b'old reviewed').hexdigest()):
            self.assertTrue(installer.known_adapter(b'old reviewed', b'new'))

    def test_requires_exact_running_host_network_compose_service(self):
        data = {'State': {'Running': True}, 'HostConfig': {'NetworkMode': 'host'}, 'Config': {'Labels': {
            'com.docker.compose.service': 'smart-ev-connector',
            'com.docker.compose.project': 'existing-project',
            'com.docker.compose.project.working_dir': '/existing',
            'com.docker.compose.project.config_files': '/existing/compose.yml',
            'com.docker.compose.config-hash': 'original-hash'}}}
        with patch.object(Path, 'is_dir', return_value=True), patch.object(Path, 'is_file', return_value=True):
            command, digest = installer.compose_base(data)
            self.assertEqual(command, ['docker', 'compose', '--project-directory', '/existing', '-p', 'existing-project', '-f', '/existing/compose.yml'])
            self.assertEqual(digest, 'original-hash')
            for path, value in ((('State', 'Running'), False), (('HostConfig', 'NetworkMode'), 'bridge')):
                changed = copy.deepcopy(data)
                changed[path[0]][path[1]] = value
                with self.assertRaises(installer.Stop):
                    installer.compose_base(changed)

    def test_hash_mismatch_fails_closed(self):
        self.assertTrue(installer.same_hash('smart-ev-connector abc123', 'abc123'))
        self.assertFalse(installer.same_hash('abc1234', 'abc123'))
        self.assertFalse(installer.same_hash('', None))

    def test_rollback_on_failed_verification(self):
        calls = []
        def check():
            raise installer.Stop('fixture failure')
        with patch.object(installer, 'run', side_effect=lambda c: calls.append(c)), patch('builtins.print'):
            with self.assertRaises(installer.Stop):
                installer.replace_connector(['apply'], ['rollback'], check)
        self.assertEqual(calls, [['apply'], ['rollback']])

    def test_rollback_on_failed_apply(self):
        with patch.object(installer, 'run', side_effect=[installer.Stop('failed'), '']) as run, patch('builtins.print'):
            with self.assertRaises(installer.Stop):
                installer.replace_connector(['apply'], ['rollback'], lambda: None)
            self.assertEqual(run.call_args_list[1].args, (['rollback'],))

    def test_success_does_not_rollback(self):
        with patch.object(installer, 'run') as run:
            installer.replace_connector(['apply'], ['rollback'], lambda: None)
            run.assert_called_once_with(['apply'])

    def test_override_changes_only_connector_image_build_and_read_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'override.json'
            installer.overlay(path, 'reviewed-image', Path('/release/local_connector'))
            service = json.loads(path.read_text())['services']
            self.assertEqual(list(service), ['smart-ev-connector'])
            self.assertEqual(service['smart-ev-connector']['environment'], {'CONNECTOR_ABRP_READONLY': 'true'})
            self.assertNotIn('volumes', service['smart-ev-connector'])
            self.assertNotIn('network_mode', service['smart-ev-connector'])


if __name__ == '__main__':
    unittest.main()
