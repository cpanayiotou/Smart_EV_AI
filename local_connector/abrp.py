"""Opt-in, uncached read-only view of the local ABRP sidecar. No credentials."""
import json
import math
import os
import re
import time
import urllib.error
import urllib.request

from pairing import NoRedirect

URL = 'http://127.0.0.1:7081/v1/abrp/telemetry'
LIMIT = 256 * 1024


def enabled():
    return os.getenv('CONNECTOR_ABRP_READONLY', 'false').lower() == 'true'


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def read_fields():
    unavailable = {'available': False, 'read_only': True, 'fields': {}, 'reason': 'abrp_unavailable'}
    if not enabled():
        return 503, {**unavailable, 'reason': 'abrp_disabled'}
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(URL.replace('/telemetry', '/fields'), timeout=5) as response:
            raw = response.read(LIMIT+1)
            if response.status != 200 or len(raw) > LIMIT:
                return 503, unavailable
            data = json.loads(raw)
        now = time.time()
        if (not isinstance(data, dict) or data.get('read_only') is not True
                or not number(data.get('fetched_at')) or not -30 <= now-data['fetched_at'] <= 900
                or type(data.get('vehicle_id')) is not int or data['vehicle_id'] <= 0
                or not isinstance(data.get('fields'), dict) or len(data['fields']) > 256):
            return 503, unavailable
        fields = {}
        for key, record in data['fields'].items():
            if (not re.fullmatch(r'[A-Za-z0-9_.]{1,129}', key)
                    or re.search(r'token|password|secret|session|authorization|cookie|api.?key|credential', key, re.I)
                    or not isinstance(record, dict)):
                continue
            value = record.get('last_known_value')
            if not (value is None or type(value) is bool or number(value) or isinstance(value, str) and len(value) <= 256):
                continue
            ts, age, ttl = (record.get(k) for k in ('timestamp', 'age_seconds', 'max_age_seconds'))
            valid_time = number(ts) and ts > 0 and ts <= now+30 and number(age) and age >= 0
            age = max(age, now-ts, 0) if valid_time else None
            provider = record.get('provider')
            usable = (record.get('available') is True and valid_time and number(ttl) and 60 <= ttl <= 86400
                      and age <= ttl and provider == 'enode' and value is not None)
            if key in ('odometer', 'est_battery_range'):
                usable = usable and number(value) and value >= 0
            unit = record.get('unit')
            fields[key] = {'last_known_value': value, 'value': value if usable else None,
                           'available': bool(usable), 'timestamp': ts if number(ts) else None,
                           'age_seconds': round(age, 2) if age is not None else None,
                           'stale': age > ttl if age is not None and number(ttl) else None,
                           'max_age_seconds': ttl if number(ttl) else None,
                           'provider': provider if isinstance(provider, str) and re.fullmatch(r'[\w-]{1,64}', provider) else None,
                           'unit': unit if isinstance(unit, str) and len(unit) <= 32 else None}
        connection = data.get('connection', {})
        return 200, {'vehicle_id': data['vehicle_id'], 'fetched_at': data['fetched_at'],
                     'read_only': True, 'fields': fields,
                     'connection': {k: connection[k] for k in ('is_connected', 'is_asleep', 'tlm_authorized', 'ota_is_connected', 'local_is_connected') if type(connection.get(k)) is bool},
                     'omitted_fields': [k for k in data.get('omitted_fields', []) if isinstance(k, str) and re.fullmatch(r'[A-Za-z0-9_.]{1,129}', k)]}
    except urllib.error.HTTPError as exc:
        exc.close()
        return 503, unavailable
    except Exception:
        return 503, unavailable


def read(display=False):
    unavailable = {'available': False, 'soc_percent': None,
                   'read_only': True, 'reason': 'abrp_unavailable'}
    if not enabled():
        return 503, {**unavailable, 'reason': 'abrp_disabled'}
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        url = URL.replace('/telemetry', '/display') if display else URL
        request = urllib.request.Request(url, method='GET', headers={'Accept': 'application/json'})
        with opener.open(request, timeout=5) as response:
            raw = response.read(LIMIT + 1)
            if response.status != 200 or len(raw) > LIMIT:
                return 503, unavailable
            data = json.loads(raw)
        if not isinstance(data, dict):
            return 503, unavailable
        soc, ts, age = (data.get(k) for k in ('soc_percent', 'soc_timestamp', 'age_seconds'))
        if display:
            soc = data.get('last_known_soc_percent')
        fetched, max_age, vehicle = (data.get(k) for k in ('fetched_at', 'max_age_seconds', 'vehicle_id'))
        now = time.time()
        if ((data.get('display_available') if display else data.get('available')) is not True or data.get('read_only') is not True
                or data.get('source') != 'abrp/enode'
                or type(vehicle) is not int or vehicle <= 0
                or not all(number(x) for x in (soc, ts, age, fetched, max_age))
                or not 0 <= soc <= 100 or not 60 <= max_age <= 86400
                or ts <= 0 or age < 0 or (not display and age > max_age)
                or now - ts < -30 or (not display and now - ts > max_age)
                or not -30 <= now - fetched <= 900):
            return 503, unavailable
        # Copy only the public contract, never arbitrary upstream fields/errors.
        result = {key: data[key] for key in (
            'available', 'read_only', 'source', 'vehicle_id', 'soc_percent',
            'soc_timestamp', 'fetched_at', 'max_age_seconds')}
        result['age_seconds'] = round(max(age, now - ts, 0), 2)
        if display:
            fresh = result['age_seconds'] <= max_age and data.get('available') is True
            result.update(display_available=True, last_known_soc_percent=soc,
                          stale=not fresh, available=fresh, soc_percent=soc if fresh else None)
        return 200, result
    except urllib.error.HTTPError as exc:
        exc.close()
        return 503, unavailable
    except Exception:
        return 503, unavailable
