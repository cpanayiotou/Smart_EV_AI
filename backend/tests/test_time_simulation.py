from datetime import datetime
from zoneinfo import ZoneInfo
from app.simulator import HomeSimulator

CY=ZoneInfo("Europe/Nicosia")

def test_advance_changes_clock():
    s=HomeSimulator()
    s.reset(datetime(2026,6,1,17,0,tzinfo=CY))
    before=s.now
    s.advance(30)
    assert (s.now-before).total_seconds()==1800

def test_stateful_energy_and_soc_can_accumulate():
    s=HomeSimulator()
    s.reset(datetime(2026,6,1,17,0,tzinfo=CY))
    start=s.soc
    # Late afternoon still has PV; repeated steps integrate rather than static snapshots.
    s.advance(30)
    assert s.soc>=start
    assert s.energy_wh>=0

def test_reset_restores_initial_soc():
    s=HomeSimulator()
    s.soc=70
    s.reset(datetime(2026,6,1,12,0,tzinfo=CY))
    assert s.soc==s.cfg.initial_soc_pct


def test_mobility_required_can_charge_after_sunset_and_stops_at_minimum_target():
    s=HomeSimulator()
    s.reset(datetime(2026,10,5,18,30,tzinfo=CY))
    s.soc=30.0
    s.apply_shadow_objective(42,mobility_required=True)
    s.advance(13*60)
    assert s.soc >= 42
    assert s.soc < 43
    assert s.ev_grid_wh > 0
    assert s.cfg.target_soc_pct == 42
