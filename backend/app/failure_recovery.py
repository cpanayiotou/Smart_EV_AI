from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class FailureState:
    telemetry_fresh: bool = True
    phase_mapping_valid: bool = True
    evcc_available: bool = True
    charger_available: bool = True
    cloud_available: bool = True
    ai_available: bool = True

def evaluate_failure_state(s: FailureState)->dict:
    reasons=[]
    if not s.telemetry_fresh: reasons.append("telemetry_stale")
    if not s.phase_mapping_valid: reasons.append("phase_mapping_invalid")
    if not s.evcc_available: reasons.append("evcc_unavailable")
    if not s.charger_available: reasons.append("charger_unavailable")
    if not s.ai_available: reasons.append("ai_backend_unavailable")
    control_safe=not reasons
    return {
        "mode":"SHADOW_LIVE" if control_safe else "SAFE_FALLBACK",
        "real_output_eligible":False,
        "reasons":reasons,
        "cloud_degraded":not s.cloud_available,
        "local_control_independent_of_cloud":True,
        "recovery_requires_fresh_revalidation":True,
    }
