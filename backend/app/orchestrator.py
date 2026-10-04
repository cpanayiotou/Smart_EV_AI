from dataclasses import asdict,dataclass
from .guardian import evaluate_target
from .agents import mobility_agent,solar_agent,home_energy_agent
from .models import TelemetrySnapshot

@dataclass(frozen=True)
class ChargingObjective:
    target_soc_pct:int
    mode:str
    approval_required:bool
    allowed:bool
    explanation:list[str]
    shadow_mode:bool=True

def plan(snapshot:TelemetrySnapshot, trip_distance_km:float=60,
         requested_target_pct:int|None=None, approved_once:bool=False)->ChargingObjective:
    lp=snapshot.loadpoints[0] if snapshot.loadpoints else None
    soc=(lp.vehicle_soc_pct if lp and lp.vehicle_soc_pct is not None else 50)
    mobility=mobility_agent(trip_distance_km,soc)
    requested=requested_target_pct if requested_target_pct is not None else max(80,mobility.required_soc_pct)
    guardian=evaluate_target(requested,mobility.required_soc_pct,approved_once)
    solar=solar_agent(snapshot)
    home=home_energy_agent(snapshot)
    return ChargingObjective(
        target_soc_pct=guardian.recommended_target_pct,
        mode=solar.strategy,
        approval_required=guardian.approval_required,
        allowed=guardian.allowed,
        explanation=[mobility.reason,guardian.reason,solar.reason,home.reason],
    )
