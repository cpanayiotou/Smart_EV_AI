from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from math import pi, sin
from zoneinfo import ZoneInfo
from .models import SiteTelemetry, LoadpointTelemetry, TelemetrySnapshot

CYPRUS = ZoneInfo("Europe/Nicosia")

@dataclass
class SimulationConfig:
    battery_capacity_kwh: float = 86.5
    initial_soc_pct: float = 46.0
    target_soc_pct: float = 80.0
    max_pv_w: float = 5000.0
    max_ac_charge_w: float = 11000.0

class HomeSimulator:
    """Deterministic development simulator. Never talks to physical hardware."""
    def __init__(self, config: SimulationConfig | None = None):
        self.cfg = config or SimulationConfig()
        self.soc = self.cfg.initial_soc_pct
        self.energy_wh = 0.0

    def snapshot(self, now: datetime | None = None) -> TelemetrySnapshot:
        now = now or datetime.now(CYPRUS)
        hour = now.hour + now.minute / 60
        daylight = max(0.0, sin(pi * (hour - 6.5) / 12.0)) if 6.5 <= hour <= 18.5 else 0.0
        pv = round(self.cfg.max_pv_w * daylight, 1)

        # Repeatable household profile with morning/evening peaks.
        base = 650.0
        morning = 1150.0 if 6.5 <= hour <= 9.0 else 0.0
        evening = 1650.0 if 18.0 <= hour <= 22.5 else 0.0
        home_without_ev = base + morning + evening

        plugged = hour >= 17.0 or hour < 8.0
        surplus = max(0.0, pv - home_without_ev)
        charging = plugged and self.soc < self.cfg.target_soc_pct
        # Simulator approximates evcc surplus behaviour: 1P minimum ~1.38kW,
        # then 3P as sufficient surplus becomes available.
        if charging and surplus >= 1380:
            charge = min(self.cfg.max_ac_charge_w, surplus)
            phases = 1 if charge < 4140 else 3
        else:
            charge, phases = 0.0, 0

        grid = home_without_ev + charge - pv
        return TelemetrySnapshot(
            site=SiteTelemetry(
                home_power_w=home_without_ev + charge,
                pv_power_w=pv,
                grid_power_w=grid,
                grid_importing=grid > 0,
            ),
            loadpoints=[LoadpointTelemetry(
                id=1, title="Audi e-tron 55", connected=plugged,
                charging=charge > 0, enabled=plugged, mode="pv",
                charge_power_w=charge, charged_energy_wh=self.energy_wh,
                vehicle_soc_pct=self.soc, phases_active=phases,
                session_energy_wh=self.energy_wh,
            )],
            source="simulator",
            read_only=True,
        )
