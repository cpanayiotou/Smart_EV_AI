from app.guardian import evaluate_target

def test_daily_80_allowed():
    d=evaluate_target(80)
    assert d.allowed and not d.approval_required

def test_unjustified_above_80_rejected():
    d=evaluate_target(95,70)
    assert not d.allowed and d.recommended_target_pct==80

def test_mobility_exception_needs_approval():
    d=evaluate_target(95,92)
    assert not d.allowed and d.approval_required and d.recommended_target_pct==92

def test_approved_exception_uses_minimum_need():
    d=evaluate_target(95,92,True)
    assert d.allowed and d.recommended_target_pct==92
