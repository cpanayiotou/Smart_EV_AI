from dataclasses import dataclass
from .learning import ChargingSession

@dataclass(frozen=True)
class EfficiencyAdvice:
    preferred_profile: str
    confidence: str
    reason: str

def advise(history:list[ChargingSession])->EfficiencyAdvice:
    if len(history)<6:
        return EfficiencyAdvice("evcc_dynamic","low",
            "Not enough measured sessions to optimize charging efficiency safely; keep evcc dynamic control.")
    # Future: compare repeatable operating bands after enough real observations.
    return EfficiencyAdvice("learned_profile","medium",
        "Enough sessions exist for a first measured efficiency comparison; battery policy still has veto.")
