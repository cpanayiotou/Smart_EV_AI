import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from solar import daily, cloud_daily


class SolarTests(unittest.TestCase):
    def test_cloud_contract_rejects_remote_parameters_and_incomplete_history(self):
        now = datetime.fromisoformat('2026-11-02T00:30:00+02:00')
        params = dict(date='2026-11-02', timezone='Europe/Nicosia',
                      **{'from': '2026-11-02T00:00:00+02:00', 'to': '2026-11-03T00:00:00+02:00'},
                      aggregate='15m', group='pv')
        def get(path):
            return 200, [dict(group='pv', data=[self.row(), self.row('00:15', '00:30')])], 0
        result = cloud_daily(get, params, now)
        self.assertEqual(result['energy_kwh'], 2)
        self.assertEqual(result['source'], 'evcc_history_energy')
        self.assertNotIn('complete_through_last_interval', result)
        updated = cloud_daily(get, {**params, 'timezone': 'Asia/Nicosia'}, now)
        self.assertEqual(updated['source'], 'evcc/history/pv')
        self.assertEqual(updated['timezone'], 'Asia/Nicosia')
        self.assertTrue(updated['complete_through_last_interval'])
        for bad in [None, {}, {**params, 'url': 'http://external.test'}, {**params, 'date': '2026-11-01'}]:
            with self.assertRaises(ValueError):
                cloud_daily(lambda _: self.fail('invalid query must not access evcc'), bad, now)
        with self.assertRaises(ValueError):
            cloud_daily(lambda _: (200, [dict(group='pv', data=[self.row('00:15', '00:30')])], 0), params, now)

    def read(self, rows, now='2026-11-02T00:30:00+02:00'):
        def get(path):
            self.assertTrue(path.startswith('/api/history/energy?'))
            self.assertIn('group=pv', path)
            self.assertIn('aggregate=15m', path)
            return 200, [dict(group='pv', data=rows)], 0
        return daily(get, datetime.fromisoformat(now))

    def row(self, start='00:00', end='00:15', energy=1):
        return dict(start=f'2026-11-02T{start}:00+02:00',
                    end=f'2026-11-02T{end}:00+02:00', energy=energy)

    def test_total_and_missing_coverage(self):
        result = self.read([self.row(), self.row('00:15', '00:30', 2)])
        self.assertEqual(result['energy_kwh'], 3)
        self.assertTrue(result['complete_through_last_interval'])
        self.assertFalse(self.read([self.row('00:15', '00:30')])['complete_through_last_interval'])

    def test_reject_duplicate_future_negative_and_nonfinite(self):
        for rows in [[self.row(), self.row()], [self.row('00:30', '00:45')],
                     [self.row(energy=-1)], [self.row(energy=float('nan'))],
                     [self.row(energy=True)]]:
            with self.assertRaises(ValueError):
                self.read(rows)

    def test_empty_is_not_zero(self):
        with self.assertRaises(ValueError):
            self.read([])

    def test_dst_days_use_local_midnight_not_fixed_24_hours(self):
        for date, slots in [('2026-03-29', 92), ('2026-10-25', 100)]:
            zone = ZoneInfo('Asia/Nicosia')
            start = datetime.fromisoformat(date).replace(tzinfo=zone)
            end = start + timedelta(days=1)
            now = end - timedelta(seconds=1)
            rows = []
            for i in range(slots - 1):
                a = start.astimezone(timezone.utc) + timedelta(minutes=15*i)
                rows.append(dict(start=a.isoformat(), end=(a+timedelta(minutes=15)).isoformat(), energy=0.1))
            result = daily(lambda path: (200, [dict(group='pv', data=rows)], 0), now)
            self.assertEqual(result['energy_kwh'], round((slots-1)*0.1, 6))
            self.assertTrue(result['complete_through_last_interval'])


if __name__ == '__main__':
    unittest.main()
