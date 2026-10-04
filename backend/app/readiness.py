from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass(frozen=True)
class ReadinessCheck:
    key: str
    label: str
    passed: bool
    mandatory_for_live_control: bool = True

CHECKS=(
    ReadinessCheck("battery_guardian","Battery Guardian",True),
    ReadinessCheck("mobility_deadline","Mobility deadline logic",True),
    ReadinessCheck("minimum_target","Minimum-target charging",True),
    ReadinessCheck("evcc_demo_contract","EVCC demo contract",True),
    ReadinessCheck("session_accounting","Session accounting",True),
    ReadinessCheck("simulation_isolation","Simulation isolation",True),
    ReadinessCheck("telemetry_contract","Canonical real telemetry contract",True),
    ReadinessCheck("freshness_watchdog","Data freshness watchdog",True),
    ReadinessCheck("per_phase_safety","Per-phase electrical safety",True),
    ReadinessCheck("electrical_safety_gate","Electrical Safety Gate",True),
    ReadinessCheck("failure_recovery","Failure/recovery tests",True),
    ReadinessCheck("production_auth","Production authentication / owner-scoped data",False),
    ReadinessCheck("command_audit","Command audit trail",True),
)

def readiness_payload()->dict:
    mandatory=[c for c in CHECKS if c.mandatory_for_live_control]
    ready=all(c.passed for c in mandatory)
    return {
        "checks":[asdict(c) for c in CHECKS],
        "passed":sum(1 for c in CHECKS if c.passed),
        "total":len(CHECKS),
        "shadow_live_inputs_allowed":True,
        "control_ready":ready,
        "real_output_control":"UNLOCKED" if ready else "LOCKED",
        "next_stage":"Connect real inputs read-only in SHADOW_LIVE; keep all real outputs locked.",
    }
