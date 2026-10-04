from dataclasses import asdict, dataclass
from .guardian import evaluate_target
from .agents import mobility_agent, solar_agent, home_energy_agent
from .models import TelemetrySnapshot

@dataclass(frozen=True)
class ChargingObjective:
    target_soc_pct: int
    mode: str
    approval_required: bool
    allowed: bool
    explanation: list[str]
    shadow_mode: bool = True

@dataclass(frozen=True)
class EvccExecutionPlan:
    """Non-actuating contract describing what the local evcc bridge should do."""
    target_soc_pct: int
    mode: str
    max_current_a: int
    phases: int
    allowed: bool
    approval_required: bool
    execution_target: str = "EVCC_DEMO"
    actuation_performed: bool = False

def plan(snapshot: TelemetrySnapshot, trip_distance_km: float = 60,
         requested_target_pct: int | None = None, approved_once: bool = False) -> ChargingObjective:
    lp = snapshot.loadpoints[0] if snapshot.loadpoints else None
    soc = lp.vehicle_soc_pct if lp and lp.vehicle_soc_pct is not None else 50
    mobility = mobility_agent(trip_distance_km, soc)
    requested = requested_target_pct if requested_target_pct is not None else mobility.required_soc_pct
    guardian = evaluate_target(requested, mobility.required_soc_pct, approved_once)
    solar = solar_agent(snapshot)
    home = home_energy_agent(snapshot)
    return ChargingObjective(
        target_soc_pct=guardian.recommended_target_pct,
        mode=solar.strategy,
        approval_required=guardian.approval_required,
        allowed=guardian.allowed,
        explanation=[mobility.reason, guardian.reason, solar.reason, home.reason],
    )

def execution_plan(objective: ChargingObjective) -> EvccExecutionPlan:
    """Translate an approved objective into a deterministic evcc demo plan.

    This function does not perform network I/O and cannot actuate a charger.
    """
    if not objective.allowed:
        return EvccExecutionPlan(
            target_soc_pct=objective.target_soc_pct, mode="off", max_current_a=6,
            phases=0, allowed=False, approval_required=objective.approval_required,
        )
    mode = "smart" if objective.mode in {"pv_surplus", "solar", "smart"} else "now"
    return EvccExecutionPlan(
        target_soc_pct=objective.target_soc_pct, mode=mode, max_current_a=16,
        phases=0, allowed=True, approval_required=objective.approval_required,
    )
