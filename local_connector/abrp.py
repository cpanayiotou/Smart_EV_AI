"""Opt-in, uncached read-only view of the local ABRP sidecar. No credentials."""
import json
import math
import os
import time
import urllib.error
import urllib.request

from pairing import NoRedirect

URL = 'http://127.0.0.1:7081/v1/abrp/telemetry'
LIMIT = 16 * 1024


def enabled():
    return os.getenv('CONNECTOR_ABRP_READONLY', 'false').lower() == 'true'


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def read():
    unavailable = {'available': False, 'soc_percent': None,
                   'read_only': True, 'reason': 'abrp_unavailable'}
    if not enabled():
        return 503, {**unavailable, 'reason': 'abrp_disabled'}
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(URL, method='GET', headers={'Accept': 'application/json'})
        with opener.open(request, timeout=5) as response:
            raw = response.read(LIMIT + 1)
            if response.status != 200 or len(raw) > LIMIT:
                return 503, unavailable
            data = json.loads(raw)
        if not isinstance(data, dict):
            return 503, unavailable
        soc, ts, age = (data.get(k) for k in ('soc_percent', 'soc_timestamp', 'age_seconds'))
        fetched, max_age, vehicle = (data.get(k) for k in ('fetched_at', 'max_age_seconds', 'vehicle_id'))
        now = time.time()
        if (data.get('available') is not True or data.get('read_only') is not True
                or data.get('source') != 'abrp/enode'
                or type(vehicle) is not int or vehicle <= 0
                or not all(number(x) for x in (soc, ts, age, fetched, max_age))
                or not 0 <= soc <= 100 or not 60 <= max_age <= 900
                or ts <= 0 or not 0 <= age <= max_age
                or not -30 <= now - ts <= max_age
                or not -30 <= now - fetched <= max_age):
            return 503, unavailable
        # Copy only the public contract, never arbitrary upstream fields/errors.
        result = {key: data[key] for key in (
            'available', 'read_only', 'source', 'vehicle_id', 'soc_percent',
            'soc_timestamp', 'fetched_at', 'max_age_seconds')}
        result['age_seconds'] = round(max(age, now - ts, 0), 2)
        return 200, result
    except urllib.error.HTTPError as exc:
        exc.close()
        return 503, unavailable
    except Exception:
        return 503, unavailable
