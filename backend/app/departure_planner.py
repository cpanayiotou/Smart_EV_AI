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
    status="ready" if deficit_kwh==0 else ("time_tight" if hours>journey["hours_until"] else "charge_required")
    return DeparturePlan(journey["departure"],journey["destination"],journey["hours_until"],
        route_kwh,reserve,minimum_soc,soc,round(deficit_kwh,2),round(ac_kwh,2),round(hours,2),status)
