from app.electrical_safety import ElectricalLimits, electrical_safety_gate

def test_unverified_service_limit_blocks_real_output():
    r=electrical_safety_gate((8,9,7),True,16,ElectricalLimits())
    assert r["safe"] is False
    assert r["eligible_for_real_output"] is False
    assert "service_limit_unverified" in r["reasons"]

def test_stale_phase_data_blocks_even_with_verified_limit():
    r=electrical_safety_gate((8,9,7),False,16,ElectricalLimits(32,2,True))
    assert r["safe"] is False
    assert "grid_or_phase_telemetry_not_fresh" in r["reasons"]

def test_weakest_phase_controls_headroom():
    r=electrical_safety_gate((10,20,8),True,16,ElectricalLimits(32,2,True))
    assert r["safe"] is False
    assert r["per_phase_headroom_a"]==(20.0,10.0,22.0)
    assert "insufficient_per_phase_headroom" in r["reasons"]

def test_verified_fresh_three_phase_headroom_can_be_control_ready():
    r=electrical_safety_gate((8,9,7),True,16,ElectricalLimits(32,2,True))
    assert r["safe"] is True
    assert r["fallback"]=="CONTROL_READY"
