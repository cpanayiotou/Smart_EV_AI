from datetime import datetime, timedelta, timezone
from app.telemetry_contract import CanonicalTelemetry, SourceQuality, validate

NOW=datetime(2026,10,5,18,30,tzinfo=timezone.utc)

def sample(age=2,soc=42,phases=3):
    q=SourceQuality("huawei_dtsu",NOW-timedelta(seconds=age),NOW,10)
    return CanonicalTelemetry(NOW,-1200,3500,(5.1,4.8,5.0),2300,10,phases,soc,(q,))

def test_fresh_real_input_is_shadow_only():
    r=validate(sample())
    assert r["control_inputs_fresh"] is True
    assert r["mode"]=="SHADOW_LIVE"
    assert r["real_output_eligible"] is False

def test_stale_grid_input_forces_safe_fallback():
    r=validate(sample(age=11))
    assert "huawei_dtsu" in r["stale_sources"]
    assert r["mode"]=="SAFE_FALLBACK"
    assert r["real_output_eligible"] is False

def test_implausible_values_are_rejected():
    r=validate(sample(soc=101,phases=2))
    assert r["valid"] is False
    assert "vehicle_soc_out_of_range" in r["faults"]
    assert "charger_phases_invalid" in r["faults"]
    assert r["real_output_eligible"] is False
