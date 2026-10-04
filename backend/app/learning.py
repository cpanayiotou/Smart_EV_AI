from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from statistics import mean

@dataclass
class ChargingSession:
    started_at: datetime
    ac_energy_kwh: float
    pv_energy_kwh: float
    grid_energy_kwh: float
    soc_start_pct: float
    soc_end_pct: float
    avg_charge_power_kw: float
    phases: int
    cost_eur: float

    @property
    def soc_gain_pct(self) -> float:
        return max(0.0, self.soc_end_pct-self.soc_start_pct)

    @property
    def pv_share_pct(self) -> float:
        return 100*self.pv_energy_kwh/self.ac_energy_kwh if self.ac_energy_kwh>0 else 0.0

class SessionStore:
    """In-memory Phase 1 store. PostgreSQL replaces this after the data contract settles."""
    def __init__(self):
        now=datetime.now(timezone.utc)
        self._sessions=[
            ChargingSession(now,12.4,9.8,2.6,46,59,2.9,1,0.78),
            ChargingSession(now,18.1,14.9,3.2,52,71,4.8,3,0.96),
            ChargingSession(now,8.6,2.1,6.5,61,70,6.7,3,1.95),
        ]

    def add(self,session:ChargingSession)->None:
        self._sessions.append(session)

    def all(self)->list[ChargingSession]:
        return list(self._sessions)

    def summary(self)->dict:
        s=self._sessions
        return {
            "sessions":len(s),
            "ac_energy_kwh":round(sum(x.ac_energy_kwh for x in s),2),
            "pv_energy_kwh":round(sum(x.pv_energy_kwh for x in s),2),
            "grid_energy_kwh":round(sum(x.grid_energy_kwh for x in s),2),
            "cost_eur":round(sum(x.cost_eur for x in s),2),
            "average_pv_share_pct":round(mean(x.pv_share_pct for x in s),1) if s else 0,
            "note":"Simulation history; not measured vehicle or battery data.",
        }
