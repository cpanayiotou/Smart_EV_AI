"""Opt-in mode and bounded daily session-target control; no arbitrary URLs."""
from datetime import datetime
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import time
import urllib.request
import uuid
import threading

import app

# Serialize all writers with the local automation watchdog.
WRITE_LOCK = threading.RLock()


def enabled():
    return os.getenv('CONNECTOR_ALLOW_CONTROL', '').lower() == 'true'


class ControlError(Exception):
    pass


def validate(item, now=None):
    now = time.time() if now is None else now
    if not isinstance(item, dict) or item.get('command') != 'evcc.set_mode':
        raise ControlError('Unsupported control command')
    identifier = item.get('id')
    try:
        if str(uuid.UUID(identifier)) != identifier:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ControlError('Invalid control request ID') from None
    params = item.get('params')
    if not isinstance(params, dict) or set(params) != {'loadpoint', 'mode', 'expires_at'}:
        raise ControlError('Invalid control parameters')
    lp = params['loadpoint']
    if type(lp) is not int or not 1 <= lp <= 20 or params['mode'] not in ('off', 'now'):
        raise ControlError('Invalid loadpoint or mode')
    try:
        expiry = datetime.fromisoformat(params['expires_at'].replace('Z', '+00:00'))
        if expiry.tzinfo is None:
            raise ValueError()
        remaining = expiry.timestamp() - now
        if not 0 < remaining <= 65:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ControlError('Expired control request or incorrect clock') from None
    return identifier, lp, params['mode']


def reserve(identifier, directory):
    """Persist before authorization/write; never replay after a crash or restart."""
    path = Path(directory) / 'control-journal.sqlite3'
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE IF NOT EXISTS attempted (id TEXT PRIMARY KEY, at REAL NOT NULL)')
        try:
            db.execute('INSERT INTO attempted VALUES (?, ?)', (identifier, time.time()))
        except sqlite3.IntegrityError:
            raise ControlError('Control request already attempted') from None
    os.chmod(path, 0o600)


def state_loadpoint(index):
    status, state, _ = app._evcc_get('/api/state')
    if status != 200 or not isinstance(state, dict):
        raise ControlError('Cannot read current evcc state')
    state = state.get('result', state)
    points = state.get('loadpoints') if isinstance(state, dict) else None
    if not isinstance(points, list) or index > len(points) or not isinstance(points[index - 1], dict):
        raise ControlError('Loadpoint is unavailable')
    return points[index - 1]


def post_mode(index, mode):
    # Endpoint and origin are local configuration only; cloud cannot supply URLs.
    if type(index) is not int or not 1 <= index <= 20 or mode not in ('off', 'now'):
        raise ControlError('Invalid loadpoint or mode')
    if not app._is_private_target(app.EVCC_URL):
        raise ControlError('evcc address must be local')
    from pairing import NoRedirect
    request = urllib.request.Request(
        f'{app.EVCC_URL}/api/loadpoints/{index}/mode/{mode}', method='POST',
        headers={'Accept': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=app.TIMEOUT) as response:
        if response.status != 200:
            raise ControlError('evcc did not accept the mode')
        response.read(4096)


def execute(item, authorize, directory=None):
    with WRITE_LOCK:
        if isinstance(item, dict) and item.get('command') == 'evcc.set_target':
            return _execute_target(item, authorize, directory)
        return _execute(item, authorize, directory)


def validate_target(item):
    params = item.get('params')
    if not isinstance(params, dict) or set(params) != {'loadpoint', 'target_soc', 'expected_limit_soc', 'expires_at'}:
        raise ControlError('Invalid target parameters')
    if (type(params['target_soc']) is not int or not 1 <= params['target_soc'] <= 80
            or type(params['expected_limit_soc']) is not int or not 1 <= params['expected_limit_soc'] <= 100):
        raise ControlError('Daily target must be 1 to 80 percent with a known previous limit')
    identifier, index, _ = validate({'id': item.get('id'), 'command': 'evcc.set_mode',
                                   'params': {'loadpoint': params['loadpoint'], 'mode': 'off',
                                              'expires_at': params['expires_at']}})
    return identifier, index, params['target_soc'], params['expected_limit_soc']


def target_guard(index, expected, root):
    import automation
    if automation.read(root) is not None:
        raise ControlError('Pause automation and confirm it stopped before changing the target')
    current = state_loadpoint(index)
    if (current.get('connected') is not True or current.get('charging') is not False
            or current.get('mode') != 'off'):
        raise ControlError('Target requires the car connected with charging off')
    limit = current.get('effectiveLimitSoc')
    if type(limit) not in (int, float) or limit != expected:
        raise ControlError('evcc limit changed; refresh the plan before applying')


def post_target(index, target):
    if type(index) is not int or not 1 <= index <= 20 or type(target) is not int or not 1 <= target <= 80:
        raise ControlError('Invalid daily target')
    if not app._is_private_target(app.EVCC_URL):
        raise ControlError('evcc address must be local')
    from pairing import NoRedirect
    request = urllib.request.Request(
        f'{app.EVCC_URL}/api/loadpoints/{index}/limitsoc/{target}', method='POST',
        headers={'Accept': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=app.TIMEOUT) as response:
        if response.status != 200:
            raise ControlError('evcc did not accept the target')
        response.read(4096)


def _execute_target(item, authorize, directory=None):
    if not enabled():
        raise ControlError('Local charging controls are disabled')
    identifier, index, target, expected = validate_target(item)
    root = directory or os.getenv('CONNECTOR_DATA_DIR', '/data')
    target_guard(index, expected, root)
    reserve(identifier, root)
    grant = authorize(identifier)
    if not isinstance(grant, dict) or grant.get('authorized') is not True:
        raise ControlError('Cloud target authorization denied')
    if not enabled():
        raise ControlError('Local charging controls are disabled')
    # Recheck the exact request, state and lease after the cloud round trip.
    if validate_target(item) != (identifier, index, target, expected):
        raise ControlError('Target request changed during authorization')
    target_guard(index, expected, root)
    post_target(index, target)
    for attempt in range(3):
        current = state_loadpoint(index)
        if (current.get('connected') is True and current.get('charging') is False
                and current.get('mode') == 'off'
                and type(current.get('limitSoc')) in (int, float)
                and type(current.get('effectiveLimitSoc')) in (int, float)
                and current['limitSoc'] == target and current['effectiveLimitSoc'] == target):
            return {'loadpoint': index, 'target_soc': target, 'verified': True, 'mode': 'off'}
        if attempt < 2:
            time.sleep(0.5)
    raise ControlError('Target sent but not verified; check evcc before retrying')


def _execute(item, authorize, directory=None):
    if not enabled():
        raise ControlError('Local charging controls are disabled')
    identifier, index, mode = validate(item)
    current = state_loadpoint(index)
    if mode == 'now' and current.get('connected') is not True:
        raise ControlError('No connected vehicle reported by evcc')
    reserve(identifier, directory or os.getenv('CONNECTOR_DATA_DIR', '/data'))
    grant = authorize(identifier)
    if not isinstance(grant, dict) or grant.get('authorized') is not True:
        raise ControlError('Cloud charging authorization denied')
    # Network/state checks may have consumed the short validity period.
    validate(item)
    if not enabled():
        raise ControlError('Local charging controls are disabled')
    # Explicit manual authorization takes ownership from an automated run.
    import automation
    post_mode(index, mode)
    automation.relinquish(directory or os.getenv('CONNECTOR_DATA_DIR', '/data'), index)
    for attempt in range(3):
        if state_loadpoint(index).get('mode') == mode:
            return {'loadpoint': index, 'mode': mode, 'verified': True}
        if attempt < 2:
            time.sleep(0.5)
    raise ControlError('Mode was sent but could not be verified; check evcc before retrying')
