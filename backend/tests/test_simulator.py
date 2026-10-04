from datetime import datetime
from zoneinfo import ZoneInfo
from app.simulator import HomeSimulator

TZ=ZoneInfo("Europe/Nicosia")

def test_midday_has_pv():
    s=HomeSimulator().snapshot(datetime(2026,6,21,12,0,tzinfo=TZ))
    assert s.site.pv_power_w > 4000
    assert s.source == "simulator"

def test_night_has_no_pv_and_car_connected():
    s=HomeSimulator().snapshot(datetime(2026,6,21,23,0,tzinfo=TZ))
    assert s.site.pv_power_w == 0
    assert s.loadpoints[0].connected is True

def test_simulator_never_claims_live_control():
    s=HomeSimulator().snapshot(datetime(2026,6,21,12,0,tzinfo=TZ))
    assert s.read_only is True
