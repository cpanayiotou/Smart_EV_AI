from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo
from .simulator import HomeSimulator, SimulationConfig
from .departure_planner import build_departure_plan
from .guardian import evaluate_target
from .orchestrator import ChargingObjective, execution_plan
from .learning import ChargingSession

CY=ZoneInfo("Europe/Nicosia")

def run_monday_larnaca_acceptance()->dict:
    """End-to-end digital-twin milestone. No evcc network calls or physical actuation."""
    sim=HomeSimulator(SimulationConfig(initial_soc_pct=30.0))
    sim.reset(datetime(2026,10,5,18,30,tzinfo=CY))
    before=sim.snapshot()
    departure=build_departure_plan(sim.now,before)
    if departure is None:
        raise RuntimeError("required journey was not found")

    guardian=evaluate_target(
        departure.minimum_departure_soc_pct,
        departure.minimum_departure_soc_pct,
        False,
    )
    objective=ChargingObjective(
        target_soc_pct=guardian.recommended_target_pct,
        mode="mobility_required",
        approval_required=guardian.approval_required,
        allowed=guardian.allowed,
        explanation=[guardian.reason],
    )
    command=execution_plan(objective)
    if objective.allowed:
        sim.apply_shadow_objective(objective.target_soc_pct,mobility_required=True)
        minutes=max(1,int(departure.hours_until*60))
        sim.advance(minutes)

    after=sim.snapshot()
    ac_kwh=max(0.0,(after.loadpoints[0].charged_energy_wh or 0)
                       -(before.loadpoints[0].charged_energy_wh or 0))/1000
    status=sim.status()
    session=ChargingSession(
        started_at=before.site.timestamp,
        ac_energy_kwh=round(ac_kwh,3),
        pv_energy_kwh=status["ev_pv_energy_kwh"],
        grid_energy_kwh=status["ev_grid_energy_kwh"],
        soc_start_pct=float(before.loadpoints[0].vehicle_soc_pct or 0),
        soc_end_pct=float(after.loadpoints[0].vehicle_soc_pct or 0),
        avg_charge_power_kw=round(ac_kwh/(departure.hours_until or 1),2),
        phases=int(after.loadpoints[0].phases_active or 0),
        cost_eur=0.0,
    )
    return {
        "scenario":"MONDAY_1830_TO_TUESDAY_0730_LARNACA",
        "departure_plan":asdict(departure),
        "guardian":asdict(guardian),
        "objective":asdict(objective),
        "evcc_execution_plan":asdict(command),
        "session":asdict(session),
        "target_reached":session.soc_end_pct >= departure.minimum_departure_soc_pct,
        "unnecessary_80pct_charge_avoided":objective.target_soc_pct < 80,
        "route_basis":"SIMULATED_NOT_ABRP",
        "simulation_only":True,
        "actuation_performed":False,
    }
