from app.orchestrator import plan
from app.models import SiteTelemetry,LoadpointTelemetry,TelemetrySnapshot

def snapshot(soc=50):
    return TelemetrySnapshot(site=SiteTelemetry(pv_power_w=3000,grid_power_w=0,home_power_w=1000),
        loadpoints=[LoadpointTelemetry(id=1,vehicle_soc_pct=soc)])

def test_default_target_is_minimum_mobility_need_not_automatic_80():
    objective=plan(snapshot(),trip_distance_km=16)
    assert objective.target_soc_pct < 80
    assert objective.allowed

def test_explicit_80_remains_allowed():
    objective=plan(snapshot(),trip_distance_km=16,requested_target_pct=80)
    assert objective.target_soc_pct == 80
    assert objective.allowed

def test_unjustified_90_is_capped_at_80():
    objective=plan(snapshot(),trip_distance_km=16,requested_target_pct=90)
    assert objective.target_soc_pct == 80
    assert not objective.allowed


def test_execution_plan_is_non_actuating_and_minimum_target():
    from app.orchestrator import execution_plan
    obj=plan(snap(30),trip_distance_km=90)
    cmd=execution_plan(obj)
    assert cmd.allowed is True
    assert cmd.target_soc_pct < 80
    assert cmd.phases == 0
    assert cmd.actuation_performed is False
    assert cmd.execution_target == "EVCC_DEMO"

def test_execution_plan_blocks_guardian_rejection():
    from app.orchestrator import execution_plan
    obj=plan(snap(30),trip_distance_km=60,requested_target_pct=90,approved_once=False)
    cmd=execution_plan(obj)
    assert cmd.allowed is False
    assert cmd.mode == "off"
    assert cmd.actuation_performed is False
