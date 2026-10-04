from app.simulated_routes import ROUTES

def test_larnaca_round_trip():
    assert ROUTES["larnaca"].round_trip_km==90
    assert ROUTES["larnaca"].simulated_trip_kwh==22.5

def test_nicosia_round_trip():
    assert ROUTES["stasikratous"].round_trip_km==16

def test_sunday_stays_optional_dataset():
    assert ROUTES["sunday"].round_trip_km==60
