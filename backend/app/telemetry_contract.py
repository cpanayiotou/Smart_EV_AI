from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

@dataclass(frozen=True)
class SourceQuality:
    source: str
    observed_at: datetime
    received_at: datetime
    max_age_seconds: int
    valid: bool = True
    reason: str = "ok"

    @property
    def age_seconds(self)->float:
        return max(0.0,(self.received_at-self.observed_at).total_seconds())

    @property
    def fresh(self)->bool:
        return self.valid and self.age_seconds <= self.max_age_seconds

@dataclass(frozen=True)
class CanonicalTelemetry:
    observed_at: datetime
    grid_power_w: Optional[float]
    pv_power_w: Optional[float]
    phase_current_a: tuple[Optional[float],Optional[float],Optional[float]]
    charger_power_w: Optional[float]
    charger_current_a: Optional[float]
    charger_phases: Optional[int]
    vehicle_soc_pct: Optional[float]
    sources: tuple[SourceQuality,...]

def validate(t:CanonicalTelemetry)->dict:
    faults=[]
    if t.vehicle_soc_pct is not None and not 0 <= t.vehicle_soc_pct <= 100:
        faults.append("vehicle_soc_out_of_range")
    if t.charger_phases not in (None,0,1,3):
        faults.append("charger_phases_invalid")
    if any(x is not None and (x < 0 or x > 200) for x in t.phase_current_a):
        faults.append("phase_current_implausible")
    stale=[s.source for s in t.sources if not s.fresh]
    control_inputs_fresh=not stale and not faults
    return {
        "valid":not faults,
        "faults":faults,
        "stale_sources":stale,
        "control_inputs_fresh":control_inputs_fresh,
        "real_output_eligible":False,
        "mode":"SHADOW_LIVE" if control_inputs_fresh else "SAFE_FALLBACK",
        "sources":[{**asdict(s),"age_seconds":s.age_seconds,"fresh":s.fresh} for s in t.sources],
    }
