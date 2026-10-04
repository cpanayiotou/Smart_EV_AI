from dataclasses import dataclass
from .models import TelemetrySnapshot

@dataclass(frozen=True)
class MobilityAdvice:
    required_soc_pct:int
    reason:str

@dataclass(frozen=True)
class SolarAdvice:
    strategy:str
    reason:str

@dataclass(frozen=True)
class HomeEnergyAdvice:
    headroom_w:float|None
    reason:str

def mobility_agent(distance_km: float, current_soc_pct: float) -> MobilityAdvice:
    # Development heuristic only; ABRP will replace this estimate.
    required=min(100,max(20,round(distance_km*0.28 + 15)))
    return MobilityAdvice(required, f"Simulation heuristic for {distance_km:.0f} km plus reserve.")

def solar_agent(t:TelemetrySnapshot)->SolarAdvice:
    pv=t.site.pv_power_w or 0
    grid=t.site.grid_power_w or 0
    if pv>1500 and grid<0: return SolarAdvice("charge_from_surplus","PV surplus is currently available.")
    return SolarAdvice("defer_if_mobility_allows","No meaningful PV surplus is available now.")

def home_energy_agent(t:TelemetrySnapshot, service_limit_w:float=22000)->HomeEnergyAdvice:
    home=t.site.home_power_w
    if home is None:return HomeEnergyAdvice(None,"Home power unavailable.")
    return HomeEnergyAdvice(max(0,service_limit_w-home),"Development estimate only; real per-phase limits must be validated.")
