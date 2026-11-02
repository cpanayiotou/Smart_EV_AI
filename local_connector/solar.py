"""Bounded GET-only daily PV history; never uses a lifetime counter as daily energy."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import math
from urllib.parse import urlencode


def daily(get, now=None):
    now = now or datetime.now(timezone.utc)
    zone = ZoneInfo('Asia/Nicosia')
    day = now.astimezone(zone).date()
    start = datetime.combine(day, time(), zone)
    end = datetime.combine(day + timedelta(days=1), time(), zone)
    query = urlencode(dict(from_=start.isoformat())).replace('from_=', 'from=')
    query += '&' + urlencode(dict(to=end.isoformat(), aggregate='15m', group='pv'))
    status, series, _ = get('/api/history/energy?' + query)
    if status != 200 or not isinstance(series, list) or not 1 <= len(series) <= 32:
        raise ValueError('Solar history unavailable')
    total, last, coverage = 0.0, None, []
    for meter in series:
        if not isinstance(meter, dict) or meter.get('group') != 'pv':
            raise ValueError('Unexpected solar series')
        rows = meter.get('data')
        if not isinstance(rows, list) or not rows or len(rows) > 100:
            raise ValueError('Missing or excessive solar history')
        previous, meter_complete = start, True
        for row in rows:
            a = datetime.fromisoformat(row['start'])
            b = datetime.fromisoformat(row['end'])
            value = row.get('energy')
            if (a.tzinfo is None or b.tzinfo is None or a.timestamp() < start.timestamp() or b.timestamp() > end.timestamp()
                    or b.timestamp() <= a.timestamp() or a.timestamp() < previous.timestamp() or b.timestamp()-a.timestamp() != 900
                    or b > now + timedelta(seconds=60)
                    or type(value) not in (int, float) or not math.isfinite(value)
                    or not 0 <= value <= 1000):
                raise ValueError('Invalid solar interval')
            meter_complete = meter_complete and a.timestamp() == previous.timestamp()
            previous = b
            total += value
            last = b if last is None or b > last else last
        # Coverage only refers to completed 15-minute periods, not the whole day.
        expected = datetime.fromtimestamp(int(now.timestamp() // 900) * 900, timezone.utc)
        coverage.append(meter_complete and previous >= expected)
    return dict(date=str(day), timezone='Asia/Nicosia', energy_kwh=round(total, 6),
                period_start=start.isoformat(), period_end=end.isoformat(),
                last_interval_end=last.isoformat(), fetched_at=now.isoformat(),
                source='evcc/history/pv', complete_through_last_interval=all(coverage))
