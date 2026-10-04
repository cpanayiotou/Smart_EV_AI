from app.acceptance import run_monday_larnaca_acceptance

def test_monday_larnaca_pipeline_derives_and_reaches_minimum_soc():
    result=run_monday_larnaca_acceptance()
    assert result["departure_plan"]["destination"]=="Splish Splash, Larnaca"
    assert result["departure_plan"]["minimum_departure_soc_pct"]==42
    assert result["guardian"]["allowed"] is True
    assert result["guardian"]["approval_required"] is False
    assert result["objective"]["target_soc_pct"]==42
    assert result["evcc_execution_plan"]["execution_target"]=="EVCC_DEMO"
    assert result["evcc_execution_plan"]["actuation_performed"] is False
    assert result["target_reached"] is True
    assert result["session"]["soc_start_pct"]==30
    assert 42 <= result["session"]["soc_end_pct"] < 43
    assert result["session"]["grid_energy_kwh"] > 0
    assert result["unnecessary_80pct_charge_avoided"] is True
    assert result["simulation_only"] is True
    assert result["actuation_performed"] is False
