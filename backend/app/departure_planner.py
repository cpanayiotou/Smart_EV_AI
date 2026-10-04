from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from .commute import next_required_journey
from .models import TelemetrySnapshot

SIM_BATTERY_KWH=86.5
SIM_AC_EFFICIENCY=0.90
SIM_MAX_AC_KW=11.0

@dataclass(frozen=True)
class DeparturePlan:
    departure:str
    destination:str
    hours_until:float
    route_kwh:float
    reserve_pct:int
    minimum_departure_soc_pct:int
    current_soc_pct:float
    energy_deficit_kwh:float
    minimum_ac_input_kwh:float
    minimum_charge_hours_at_11kw:float
    status:str
    planning_charge_kw:float
    safety_margin_minutes:int
    planned_charge_hours:float
    latest_start:str|None
    source:str="SIMULATED_NOT_ABRP"

def build_departure_plan(now:datetime,snapshot:TelemetrySnapshot)->DeparturePlan|None:
    journey=next_required_journey(now)
    if not journey:return None
    route_kwh=journey.get("simulated_trip_kwh")
    reserve=journey.get("reserve_pct")
    if route_kwh is None or reserve is None:return None
    lp=snapshot.loadpoints[0] if snapshot.loadpoints else None
    soc=float(lp.vehicle_soc_pct) if lp and lp.vehicle_soc_pct is not None else 50.0
    minimum_soc=min(100,ceil(route_kwh/SIM_BATTERY_KWH*100+reserve))
    deficit_pct=max(0.0,minimum_soc-soc)
    deficit_kwh=SIM_BATTERY_KWH*deficit_pct/100
    ac_kwh=deficit_kwh/SIM_AC_EFFICIENCY if deficit_kwh else 0.0
    hours=ac_kwh/SIM_MAX_AC_KW if ac_kwh else 0.0
    # Do not plan against the theoretical 11 kW ceiling. 7 kW is a conservative\n    # development assumption until real house/per-phase headroom is measured.\n    planning_kw=7.0\n    safety_margin_minutes=30\n    planned_hours=(ac_kwh/planning_kw) if ac_kwh else 0.0\n    departure=datetime.fromisoformat(journey["departure"])\n    from datetime import timedelta\n    latest=departure-timedelta(hours=planned_hours,minutes=safety_margin_minutes) if deficit_kwh else None\n    available_hours=journey["hours_until"]-(safety_margin_minutes/60)\n    status="ready" if deficit_kwh==0 else ("time_tight" if planned_hours>available_hours else "charge_required")\n    return DeparturePlan(journey["departure"],journey["destination"],journey["hours_until"],\n        route_kwh,reserve,minimum_soc,soc,round(deficit_kwh,2),round(ac_kwh,2),round(hours,2),status,\n        planning_kw,safety_margin_minutes,round(planned_hours,2),latest.isoformat() if latest else None)
