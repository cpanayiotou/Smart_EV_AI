"""Opt-in bounded automatic mode control with a durable local expiry watchdog.

No cloud URL, arbitrary evcc setting, current or phase can be supplied here.
An acknowledged mode is NOT proof of charging. Cloud must observe charging power.
"""
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

import control

_ready = threading.Event()
_thread = None
_monotonic_expiry = {}


def enabled():
    return control.enabled() and os.getenv('CONNECTOR_ALLOW_AUTOMATION', '').lower() == 'true'


def capable():
    return enabled() and _ready.is_set() and _thread is not None and _thread.is_alive()


def directory(value=None):
    return value or os.getenv('CONNECTOR_DATA_DIR', '/data')


def connection(root):
    path = Path(root) / 'automation.sqlite3'
    db = sqlite3.connect(path)
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS lease (slot INTEGER PRIMARY KEY CHECK(slot=1), run TEXT NOT NULL, loadpoint INTEGER NOT NULL, deadline TEXT NOT NULL, lease_until TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS runs (run TEXT PRIMARY KEY)')
    db.commit()
    os.chmod(path, 0o600)
    return db


def read(root):
    with closing(connection(root)) as db:
        row = db.execute('SELECT run,loadpoint,deadline,lease_until FROM lease WHERE slot=1').fetchone()
    return dict(zip(('run_id', 'loadpoint', 'deadline', 'lease_until'), row)) if row else None


def relinquish(root, index=None):
    with control.WRITE_LOCK, closing(connection(root)) as db, db:
        if index is None:
            db.execute('DELETE FROM lease')
            _monotonic_expiry.clear()
        else:
            row = db.execute('SELECT run FROM lease WHERE loadpoint=?', (index,)).fetchone()
            db.execute('DELETE FROM lease WHERE loadpoint=?', (index,))
            if row:
                _monotonic_expiry.pop(row[0], None)


def instant(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.timestamp()
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise control.ControlError('Invalid automation timestamp') from None


def identifier(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (AttributeError, TypeError, ValueError):
        raise control.ControlError('Invalid automation ID') from None


def validate(item, now=None):
    now = time.time() if now is None else now
    if not isinstance(item, dict) or item.get('command') != 'evcc.automation':
        raise control.ControlError('Unsupported automation command')
    identifier(item.get('id'))
    p = item.get('params')
    if not isinstance(p, dict) or set(p) != {'loadpoint', 'action', 'run_id', 'expires_at', 'lease_until', 'deadline'}:
        raise control.ControlError('Invalid automation parameters')
    identifier(p['run_id'])
    if type(p['loadpoint']) is not int or not 1 <= p['loadpoint'] <= 20 or p['action'] not in ('start', 'renew', 'stop'):
        raise control.ControlError('Invalid automation action')
    if not 0 < instant(p['expires_at']) - now <= 65:
        raise control.ControlError('Automation command expired')
    lease, end = instant(p['lease_until']), instant(p['deadline'])
    if p['action'] != 'stop' and not (now < lease <= now + 120 and lease <= end <= now + 86400):
        raise control.ControlError('Invalid automation lease')
    return p


def save(root, p, new=False):
    with closing(connection(root)) as db, db:
        if new:
            try:
                db.execute('INSERT INTO runs VALUES (?)', (p['run_id'],))
            except sqlite3.IntegrityError:
                raise control.ControlError('Automation run cannot be restarted') from None
        db.execute('INSERT OR REPLACE INTO lease VALUES (1,?,?,?,?)',
                   (p['run_id'], p['loadpoint'], p['deadline'], p['lease_until']))
    _monotonic_expiry[p['run_id']] = time.monotonic() + max(0, min(instant(p['lease_until']), instant(p['deadline'])) - time.time())


def owned(p, lease):
    return lease and all(p[k] == lease[k] for k in ('run_id', 'loadpoint', 'deadline'))


def stop_owned(root, lease):
    state = control.state_loadpoint(lease['loadpoint'])
    if state.get('mode') == 'now':
        control.post_mode(lease['loadpoint'], 'off')
        if control.state_loadpoint(lease['loadpoint']).get('mode') != 'off':
            raise control.ControlError('Automation stop not confirmed')
    elif state.get('mode') not in ('off', 'pv', 'minpv'):
        raise control.ControlError('Cannot verify automation ownership')
    relinquish(root)


def tick(root=None, recovering=False):
    root = directory(root)
    with control.WRITE_LOCK:
        lease = read(root)
        if not lease:
            return
        state = control.state_loadpoint(lease['loadpoint'])
        # An observed manual mode change ends our ownership. Never restore it.
        if state.get('mode') in ('off', 'pv', 'minpv'):
            relinquish(root)
            return
        if state.get('mode') != 'now':
            raise control.ControlError('Cannot verify automation mode')
        expiry = min(instant(lease['lease_until']), instant(lease['deadline']))
        mono = _monotonic_expiry.get(lease['run_id'], -1)
        if recovering or not enabled() or state.get('connected') is not True or time.time() >= expiry or time.monotonic() >= mono:
            stop_owned(root, lease)


def execute(item, authorize, root=None):
    root = directory(root)
    with control.WRITE_LOCK:
        if not capable():
            raise control.ControlError('Local automatic charging is disabled')
        p = validate(item)
        lease = read(root)
        if p['action'] == 'start':
            if lease:
                raise control.ControlError('An automation run already owns this connector')
        elif not owned(p, lease):
            raise control.ControlError('Automation run does not own this loadpoint')
        state = control.state_loadpoint(p['loadpoint'])
        if p['action'] == 'start' and (state.get('mode') != 'off' or state.get('connected') is not True or state.get('charging') is not False):
            raise control.ControlError('Start requires a connected, stopped loadpoint in off mode')
        if p['action'] == 'renew' and (state.get('mode') != 'now' or state.get('connected') is not True or time.time() >= instant(lease['lease_until']) or time.monotonic() >= _monotonic_expiry.get(p['run_id'], -1)):
            raise control.ControlError('Automation lease is no longer active')
        control.reserve(item['id'], root)
        grant = authorize(item['id'])
        if not isinstance(grant, dict) or grant.get('authorized') is not True:
            raise control.ControlError('Automatic charging authorization denied')
        validate(item)
        if not capable():
            raise control.ControlError('Local automatic charging is disabled')
        # Re-read after the cloud round trip; a driver may have taken over.
        current = control.state_loadpoint(p['loadpoint'])
        if p['action'] == 'start':
            if current.get('mode') != 'off' or current.get('connected') is not True or current.get('charging') is not False:
                raise control.ControlError('Loadpoint changed before start')
            save(root, p, new=True)  # Persist BEFORE write, including ambiguous failures.
            control.post_mode(p['loadpoint'], 'now')
        elif p['action'] == 'renew':
            if current.get('mode') != 'now' or current.get('connected') is not True or time.time() >= instant(lease['lease_until']) or time.monotonic() >= _monotonic_expiry.get(p['run_id'], -1):
                raise control.ControlError('Automation lease changed before renewal')
            save(root, p)
        else:
            stop_owned(root, lease)
        mode = 'off' if p['action'] == 'stop' else 'now'
        if control.state_loadpoint(p['loadpoint']).get('mode') != mode:
            raise control.ControlError('Automatic mode could not be verified')
        return {k: p[k] for k in ('loadpoint', 'run_id', 'action', 'lease_until', 'deadline')} | {'mode': mode, 'verified': True}


def start_watchdog(root=None):
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    root = directory(root)
    def watch():
        recovering = True
        while True:
            try:
                tick(root, recovering=recovering)
                recovering = False
                _ready.set()
            except Exception:
                # Never advertise a new capability while ownership cannot be recovered.
                _ready.clear()
            time.sleep(2)
    _thread = threading.Thread(target=watch, name='automation-watchdog', daemon=True)
    _thread.start()
