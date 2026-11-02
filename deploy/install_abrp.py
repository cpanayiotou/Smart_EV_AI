#!/usr/bin/env python3
"""Run locally on the Pi: sudo python3 install_abrp.py. No chat credentials."""
import io
import hashlib
import json
import os
from pathlib import Path
try:
    import pwd
except ImportError:  # Allow offline installer tests on Windows.
    pwd = None
import shlex
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request

ADAPTER = '703c42af787be38bea4bf516e31671d0158b54b5'
CONNECTOR = '30f429823829ccd09512346ed1956ed0b75668cd'
PREVIOUS_ADAPTER_SHA256 = 'a8fddc56d723c9bf7d4c0db10129259c18ec87b2ab2ac04781c58cf3cc86a4ca'
REPO = 'cpanayiotou/Smart_EV_AI'
SERVICE = 'smart-ev-connector'
ENV = dict(os.environ)


class Stop(Exception):
    pass


def known_adapter(installed, desired):
    return installed == desired or hashlib.sha256(installed).hexdigest() in {
        PREVIOUS_ADAPTER_SHA256, '139b4d880c9064d94ed9b418325f04dc153844e38b159f1b55b1750b2f2d7743',
        '5e31fbeb4e45135fc29bf2742df34a23ad939b0f9a65ba1184eb4d52285b50f1'}


def run(args, capture=False):
    result = subprocess.run(args, env=ENV, text=True, stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if result.returncode:
        raise Stop('A local command failed: ' + args[0] + '. No private output was printed.')
    return result.stdout.strip() if capture else ''


def inspect(kind, name):
    return json.loads(run(['docker', kind, 'inspect', name], True))[0]


def get(path, port=7080):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{port}{path}', timeout=5) as response:
        return json.load(response)


def compose_base(container):
    if not container.get('State', {}).get('Running'):
        raise Stop('The existing connector must be running; it has not been changed.')
    if container.get('HostConfig', {}).get('NetworkMode') != 'host':
        raise Stop('Expected host networking. Review this deployment before proceeding.')
    labels = container['Config'].get('Labels') or {}
    project = labels.get('com.docker.compose.project')
    directory = labels.get('com.docker.compose.project.working_dir')
    files = labels.get('com.docker.compose.project.config_files', '').split(',')
    if labels.get('com.docker.compose.service') != SERVICE or not project or not directory or not all(files):
        raise Stop('Existing Compose deployment labels are missing; no container was changed.')
    if not Path(directory).is_dir() or not all(Path(f).is_file() for f in files):
        raise Stop('Existing Compose source files are unavailable; no container was changed.')
    command = ['docker', 'compose', '--project-directory', directory, '-p', project]
    for file in files:
        command += ['-f', file]
    return command, labels.get('com.docker.compose.config-hash')


def same_hash(output, expected):
    # Compose versions print either the hash or '<service> <hash>'.
    return bool(expected) and expected in output.split()


def extract(commit, destination, prefixes):
    url = f'https://codeload.github.com/{REPO}/tar.gz/{commit}'
    with urllib.request.urlopen(url, timeout=60) as response:
        raw = response.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise Stop('Repository download exceeded the expected size.')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            relative = '/'.join(member.name.split('/')[1:])
            if not any(relative == p or relative.startswith(p + '/') for p in prefixes):
                continue
            if member.isdir():
                continue
            if not member.isfile() or '..' in Path(relative).parts or Path(relative).is_absolute():
                raise Stop('Unexpected archive entry.')
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source:
                target.write_bytes(source.read())
            target.chmod(0o644)  # Public source, not credentials; Docker COPY retains modes.


def overlay(path, image, source=None):
    service = {'image': image}
    if source:
        service.update(build={'context': str(source)}, environment={'CONNECTOR_ABRP_READONLY': 'true',
                                                                   'CONNECTOR_PV_HISTORY_READONLY': 'true'})
    path.write_text(json.dumps({'services': {SERVICE: service}}))
    path.chmod(0o600)


def save_launcher(path, command):
    lines = ['#!/bin/sh', 'set -eu']
    for key in ('CONNECTOR_ALLOW_CONTROL', 'CONNECTOR_HOST'):
        if key in ENV:
            lines.append('export ' + key + '=' + shlex.quote(ENV[key]))
    lines.append('exec ' + shlex.join(command))
    path.write_text('\n'.join(lines) + '\n')
    path.chmod(0o700)


def replace_connector(apply, rollback, check):
    try:
        run(apply)
        check()
    except BaseException:
        print('Connector verification failed; restoring its previous image and settings.', flush=True)
        run(rollback)
        raise


def main():
    if os.name != 'posix' or os.geteuid() != 0 or sys.version_info < (3, 11):
        raise Stop('Run with sudo python3 on the Pi; Python 3.11+ is required.')
    os.umask(0o077)
    run(['docker', 'compose', 'version'], True)
    if run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'], True) != 'yes':
        raise Stop('Synchronize the Pi clock before installing telemetry freshness checks.')
    current = inspect('container', SERVICE)
    base, expected_hash = compose_base(current)
    values = dict(entry.split('=', 1) for entry in current['Config'].get('Env', []) if '=' in entry)
    # Recover only known non-secret interpolation settings from the running container.
    for key in ('CONNECTOR_ALLOW_CONTROL', 'CONNECTOR_HOST'):
        if key in values:
            ENV[key] = values[key]
    if not same_hash(run(base + ['config', '--hash', SERVICE], True), expected_hash):
        raise Stop('Current Compose files do not reproduce the running connector. Nothing was changed. Review the deployment settings first.')
    before = get('/health')
    if before.get('status') != 'running':
        raise Stop('Connector health preflight failed.')
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:7070/', timeout=5) as response:
        if response.status != 200:
            raise Stop('evcc baseline check failed.')
    stamp = time.strftime('%Y%m%d-%H%M%S')
    release = Path('/opt') / ('smart-ev-abrp-release-' + stamp)
    release.mkdir(mode=0o700)
    print('Downloading pinned, reviewed source and running tests. Existing services stay running.', flush=True)
    extract(CONNECTOR, release, ['local_connector'])
    extract(ADAPTER, release, ['backend/abrp_adapter.py', 'backend/test_abrp_adapter.py',
                              'deploy/smart-ev-abrp.service', 'THIRD_PARTY_NOTICES.md', 'docs/ABRP_DEPLOYMENT.md'])
    run([sys.executable, '-m', 'unittest', 'discover', '-s', str(release / 'local_connector'), '-v'])
    run([sys.executable, '-m', 'unittest', 'discover', '-s', str(release / 'backend'), '-p', 'test_abrp_adapter.py', '-v'])
    tag = 'smart-ev-connector:abrp-' + stamp
    rollback_tag = 'smart-ev-connector:before-abrp-' + stamp
    run(['docker', 'image', 'tag', current['Image'], rollback_tag])
    apply_file, rollback_file = release / 'connector.override.json', release / 'rollback.override.json'
    overlay(apply_file, tag, release / 'local_connector')
    overlay(rollback_file, rollback_tag)
    apply_base, rollback_base = base + ['-f', str(apply_file)], base + ['-f', str(rollback_file)]
    apply_command = apply_base + ['up', '-d', '--no-deps', '--no-build', SERVICE]
    rollback_command = rollback_base + ['up', '-d', '--no-deps', '--no-build', SERVICE]
    save_launcher(release / 'apply-connector.sh', apply_command)
    save_launcher(release / 'rollback-connector.sh', rollback_command)
    run(apply_base + ['build', SERVICE])
    run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
         '--security-opt', 'no-new-privileges', '--entrypoint', 'python', tag, '-B', '-c',
         "import os, app, abrp, cloud_main, setup_web; from pathlib import Path; "
         "assert os.getuid() != 0; "
         "[Path(p).read_bytes() for p in ('/app/wizard.html', '/app/wizard.js', '/app/wizard.css')]"])
    target = Path('/opt/smart-ev-abrp/abrp_adapter.py')
    code = (release / 'backend/abrp_adapter.py').read_bytes()
    unit = Path('/etc/systemd/system/smart-ev-abrp.service')
    unit_code = (release / 'deploy/smart-ev-abrp.service').read_bytes()
    if target.exists() and not known_adapter(target.read_bytes(), code):
        raise Stop('A different adapter is already installed; it has not been replaced.')
    if target.exists():
        (release / 'previous_adapter.py').write_bytes(target.read_bytes())
    if unit.exists() and unit.read_bytes() not in (unit_code, unit_code.replace(b'--max-age-seconds 86400', b'--max-age-seconds 900')):
        raise Stop('A different adapter unit already exists; it has not been replaced.')
    active = subprocess.run(['systemctl', 'is-active', '--quiet', 'smart-ev-abrp']).returncode == 0
    if active:
        if not target.exists() or not unit.exists():
            raise Stop('Unrecognized adapter service; leaving it unchanged.')
        run(['systemctl', 'stop', 'smart-ev-abrp'])
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 7081))
        except OSError:
            raise Stop('Port 7081 is occupied; no existing listener was stopped.')
    try:
        account = pwd.getpwnam('smart-ev-abrp')
    except KeyError:
        run(['useradd', '--system', '--user-group', '--home-dir', '/var/lib/smart-ev-abrp',
             '--shell', '/usr/sbin/nologin', 'smart-ev-abrp'])
        account = pwd.getpwnam('smart-ev-abrp')
    target.parent.mkdir(mode=0o755, exist_ok=True)
    if target.parent.is_symlink() or target.is_symlink() or unit.is_symlink():
        raise Stop('Unexpected symlink at an installation path.')
    target.parent.chmod(0o755)
    target.write_bytes(code)
    target.chmod(0o644)
    data = Path('/var/lib/smart-ev-abrp')
    if data.is_symlink():
        raise Stop('Unexpected credential-directory symlink.')
    data.mkdir(mode=0o700, exist_ok=True)
    os.chown(data, account.pw_uid, account.pw_gid)
    data.chmod(0o700)
    credentials = str(data / 'tokens.json')
    local = ['runuser', '-u', 'smart-ev-abrp', '--', sys.executable, str(target)]
    if not Path(credentials).exists():
        print('Approve the following private ABRP link on your signed-in device. Do not paste it into chat.', flush=True)
        run(local + ['login', '--credentials', credentials])
    print('Select your Audi from this local vehicle list:', flush=True)
    run(local + ['vehicles', '--credentials', credentials])
    config = Path('/etc/smart-ev-abrp.conf')
    existing = config.read_text().strip() if config.exists() else ''
    vehicle = existing.removeprefix('ABRP_VEHICLE_ID=') if existing.startswith('ABRP_VEHICLE_ID=') else ''
    if not vehicle.isascii() or not vehicle.isdigit() or int(vehicle) <= 0:
        vehicle = input('Audi ABRP vehicle_id: ').strip()
    else:
        print('Keeping your configured Audi vehicle ID.', flush=True)
    if not vehicle.isascii() or not vehicle.isdigit() or int(vehicle) <= 0:
        raise Stop('A positive numeric vehicle ID is required. The connector has not been changed.')
    config.write_text('ABRP_VEHICLE_ID=' + str(int(vehicle)) + '\n')
    config.chmod(0o644)
    unit.write_bytes(unit_code)
    unit.chmod(0o644)
    run(['systemd-analyze', 'verify', str(unit)])
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'start', 'smart-ev-abrp'])
    print('Waiting up to 90 seconds for timestamped Enode display data (older readings are labelled stale)...', flush=True)
    for _ in range(45):
        try:
            sample = get('/v1/abrp/display', 7081)
            if sample.get('display_available') is True and sample.get('vehicle_id') == int(vehicle):
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        raise Stop('Adapter is installed, but validated Enode display data is unavailable. Connector remains unchanged. Check http://127.0.0.1:7081/v1/abrp/display locally.')
    print('Last-known SoC verified. Updating only the connector; evcc remains running.', flush=True)

    def check():
        for _ in range(20):
            try:
                after = get('/health')
                sample = get('/v1/abrp/display')
                fields = get('/v1/abrp/fields')
                if (after.get('status') == 'running' and sample.get('display_available') is True
                        and isinstance(fields.get('fields'), dict)
                        and all(after.get(k) == before.get(k) for k in ('read_only', 'control_capable'))):
                    return
            except Exception:
                pass
            time.sleep(2)
        raise Stop('New connector health or ABRP routes did not validate.')

    if inspect('container', SERVICE)['Id'] != current['Id'] or not same_hash(
            run(base + ['config', '--hash', SERVICE], True), expected_hash):
        raise Stop('Connector or Compose settings changed during setup. Leaving that deployment unchanged.')
    replace_connector(apply_command, rollback_command, check)
    run(['systemctl', 'enable', 'smart-ev-abrp'])
    print('Installed. Battery display: http://smart-ev-ai.local:7080/')
    print('Last-known JSON: http://smart-ev-ai.local:7080/v1/abrp/display')
    print('Full telemetry: http://smart-ev-ai.local:7080/v1/abrp/fields')
    print('Cloud telemetry: abrp.fields capability enabled for the existing paired Smart EV AI cloud.')
    print('Daily solar: http://smart-ev-ai.local:7080/v1/evcc/solar/daily')
    print('Read-only daily solar cloud capability enabled; the matching cloud receiver must be published.')
    print('The matching cloud receiver must be published before readings appear on its dashboard.')
    try:
        fields = get('/v1/abrp/fields')['fields']
        for key, label in (('odometer', 'Odometer'), ('est_battery_range', 'Range')):
            field = fields.get(key, {})
            value = field.get('value')
            print(label + ': ' + (str(value) + ' km (available to evcc)' if field.get('available') is True
                                  else 'not reported or not independently verified; see telemetry table'))
    except Exception:
        print('Optional telemetry summary unavailable; inspect the local telemetry table.')
    print('No charging commands or evcc configuration changes were made.')
    print('Keep this release directory; Docker uses its override configuration.')
    print('Reapply: sudo ' + str(release / 'apply-connector.sh'))
    print('Rollback connector: sudo ' + str(release / 'rollback-connector.sh'))
    print('Stop adapter if retiring it: sudo systemctl disable --now smart-ev-abrp')


if __name__ == '__main__':
    try:
        main()
    except (Stop, KeyboardInterrupt) as error:
        print('\nStopped: ' + (str(error) if isinstance(error, Stop) else 'interrupted locally'))
        sys.exit(1)
    except Exception:
        print('\nStopped: unexpected local/deployment error. Private exception details were withheld.')
        sys.exit(1)
