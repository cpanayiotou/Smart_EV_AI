from app.commute import COMMUTE_PROFILE

def test_weekday_larnaca_commute_is_mon_thu():
    j=COMMUTE_PROFILE[0]
    assert j.days==(0,1,2,3)
    assert j.depart.hour==7 and j.depart.minute==30
    assert j.return_time.hour==18

def test_friday_returns_at_1600():
    j=COMMUTE_PROFILE[1]
    assert j.days==(4,)
    assert j.return_time.hour==16

def test_sunday_is_optional():
    assert COMMUTE_PROFILE[-1].certainty=="optional"
    assert COMMUTE_PROFILE[-1].distance_km==60
