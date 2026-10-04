from dataclasses import dataclass

@dataclass(frozen=True)
class GuardianDecision:
    allowed: bool
    approval_required: bool
    recommended_target_pct: int
    reason: str

def evaluate_target(requested_pct: int, mobility_required_pct: int | None = None,
                    approved_once: bool = False) -> GuardianDecision:
    requested=max(0,min(100,int(requested_pct)))
    need=max(0,min(100,int(mobility_required_pct))) if mobility_required_pct is not None else None
    if requested <= 80:
        return GuardianDecision(True,False,requested,"Within normal 80% daily battery-health policy.")
    if need is None or need <= 80:
        return GuardianDecision(False,False,80,"No mobility requirement justifies charging above 80%.")
    minimum=min(100,max(81,need))
    if not approved_once:
        return GuardianDecision(False,True,minimum,
            f"Mobility requires about {need}%. Above-normal charging requires explicit one-time approval.")
    return GuardianDecision(True,False,minimum,
        "One-time above-normal target approved for the mobility requirement.")
