import pytest
from app.command_audit import CommandAuditTrail

def test_records_proposed_command_without_actuation():
    a=CommandAuditTrail()
    r=a.append(environment="simulation",execution_target="EVCC_DEMO",actor="orchestrator",
      requested_action="target_soc",requested_value=42,guardian_allowed=True,
      electrical_gate_safe=True,telemetry_sources=("simulator",),outcome="APPROVED",
      actuation_performed=False,reason="minimum mobility target")
    assert r.requested_value==42
    assert r.actuation_performed is False
    assert a.verify_chain() is True

def test_audit_chain_links_records():
    a=CommandAuditTrail()
    x=a.append(environment="simulation",execution_target="EVCC_DEMO",actor="orchestrator",
      requested_action="mode",requested_value="smart",guardian_allowed=True,electrical_gate_safe=True)
    y=a.append(environment="simulation",execution_target="EVCC_DEMO",actor="orchestrator",
      requested_action="max_current_a",requested_value=10,guardian_allowed=True,electrical_gate_safe=True)
    assert y.previous_hash==x.record_hash
    assert a.verify_chain() is True

def test_non_simulated_actuation_is_hard_locked():
    a=CommandAuditTrail()
    with pytest.raises(ValueError):
        a.append(environment="production",execution_target="PEBLAR_REAL",actor="orchestrator",
          requested_action="max_current_a",requested_value=16,guardian_allowed=True,
          electrical_gate_safe=True,actuation_performed=True)
