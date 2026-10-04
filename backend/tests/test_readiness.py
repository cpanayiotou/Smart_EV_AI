from app.readiness import readiness_payload

def test_real_output_control_stays_locked_until_mandatory_checks_pass():
    r=readiness_payload()
    assert r["shadow_live_inputs_allowed"] is True
    assert r["control_ready"] is False
    assert r["real_output_control"]=="LOCKED"
    assert r["passed"]==6
    assert r["total"]==13
    failed={x["key"] for x in r["checks"] if not x["passed"]}
    assert "freshness_watchdog" in failed
    assert "per_phase_safety" in failed
    assert "electrical_safety_gate" in failed
    assert "production_auth" in failed
