from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class ElectricalLimits:
    service_limit_a: Optional[float] = None
    reserve_a: float = 2.0
    verified: bool = False

def electrical_safety_gate(
    phase_current_a: tuple[Optional[float],Optional[float],Optional[float]],
    telemetry_fresh: bool,
    requested_charge_a: float,
    limits: ElectricalLimits,
)->dict:
    reasons=[]
    if not telemetry_fresh:
        reasons.append("grid_or_phase_telemetry_not_fresh")
    if not limits.verified or limits.service_limit_a is None:
        reasons.append("service_limit_unverified")
    if any(x is None for x in phase_current_a):
        reasons.append("phase_current_missing")
    if requested_charge_a < 0:
        reasons.append("requested_current_invalid")

    headroom=None
    if limits.verified and limits.service_limit_a is not None and all(x is not None for x in phase_current_a):
        usable=limits.service_limit_a-limits.reserve_a
        headroom=tuple(round(usable-float(x),2) for x in phase_current_a)
        if min(headroom) < requested_charge_a:
            reasons.append("insufficient_per_phase_headroom")

    safe=not reasons
    return {
        "safe":safe,
        "eligible_for_real_output":safe,
        "requested_charge_a":requested_charge_a,
        "service_limit_a":limits.service_limit_a,
        "service_limit_verified":limits.verified,
        "reserve_a":limits.reserve_a,
        "per_phase_headroom_a":headroom,
        "reasons":reasons,
        "fallback":"SAFE_FALLBACK" if not safe else "CONTROL_READY",
    }
