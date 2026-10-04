from app.evcc import _num, _int, _nested

def test_numeric_helpers():
    assert _num("42.5") == 42.5
    assert _num(True) is None
    assert _int("3") == 3

def test_nested():
    assert _nested({"grid": {"power": -120.0}}, "grid", "power") == -120.0
    assert _nested({}, "grid", "power") is None
