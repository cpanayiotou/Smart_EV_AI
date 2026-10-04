from datetime import datetime
from zoneinfo import ZoneInfo
from app.commute import COMMUTE_PROFILE,next_required_journey

CY=ZoneInfo("Europe/Nicosia")

def test_weekday_larnaca_commute_is_mon_thu():
    j=COMMUTE_PROFILE[0]
    assert j.days==(0,1,2,3) and j.depart.hour==7 and j.return_time.hour==18

def test_friday_returns_at_1600():
    assert COMMUTE_PROFILE[1].return_time.hour==16

def test_sunday_has_no_invented_deadline():
    assert COMMUTE_PROFILE[-1].certainty=="optional"
    assert COMMUTE_PROFILE[-1].depart is None

def test_monday_evening_points_to_tuesday_0730():
    n=next_required_journey(datetime(2026,10,5,18,30,tzinfo=CY))
    assert n["departure"].startswith("2026-10-06T07:30")
    assert n["route_energy_status"]=="awaiting_abrp"

def test_thursday_evening_points_to_friday_nicosia():
    n=next_required_journey(datetime(2026,10,8,18,30,tzinfo=CY))
    assert n["destination"]=="Stasikratous, Nicosia"
    assert n["departure"].startswith("2026-10-09T07:30")
