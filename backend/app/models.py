from datetime import datetime, timezone
from pydantic import BaseModel, Field

class SiteTelemetry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    home_power_w: float | None = None
    pv_power_w: float | None = None
    grid_power_w: float | None = None
    grid_importing: bool | None = None
    tariff_grid: float | None = None

class LoadpointTelemetry(BaseModel):
    id: int
    title: str | None = None
    connected: bool | None = None
    charging: bool | None = None
    enabled: bool | None = None
    mode: str | None = None
    charge_power_w: float | None = None
    charged_energy_wh: float | None = None
    vehicle_soc_pct: float | None = None
    vehicle_range_km: float | None = None
    phases_active: int | None = None
    session_energy_wh: float | None = None
    session_solar_percentage: float | None = None

class TelemetrySnapshot(BaseModel):
    site: SiteTelemetry
    loadpoints: list[LoadpointTelemetry] = []
    source: str = "evcc"
    read_only: bool = True
