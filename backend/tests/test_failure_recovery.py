from app.failure_recovery import FailureState, evaluate_failure_state

def test_stale_meter_falls_back():
    r=evaluate_failure_state(FailureState(telemetry_fresh=False))
    assert r["mode"]=="SAFE_FALLBACK" and not r["real_output_eligible"]

def test_wrong_phase_mapping_falls_back():
    assert evaluate_failure_state(FailureState(phase_mapping_valid=False))["mode"]=="SAFE_FALLBACK"

def test_evcc_or_charger_loss_falls_back():
    assert evaluate_failure_state(FailureState(evcc_available=False))["mode"]=="SAFE_FALLBACK"
    assert evaluate_failure_state(FailureState(charger_available=False))["mode"]=="SAFE_FALLBACK"

def test_ai_restart_falls_back():
    assert evaluate_failure_state(FailureState(ai_available=False))["mode"]=="SAFE_FALLBACK"

def test_cloud_outage_does_not_become_control_authority():
    r=evaluate_failure_state(FailureState(cloud_available=False))
    assert r["cloud_degraded"] is True
    assert r["local_control_independent_of_cloud"] is True
    assert r["real_output_eligible"] is False

def test_recovery_requires_revalidation_and_stays_shadow_only():
    r=evaluate_failure_state(FailureState())
    assert r["mode"]=="SHADOW_LIVE"
    assert r["recovery_requires_fresh_revalidation"] is True
    assert r["real_output_eligible"] is False
