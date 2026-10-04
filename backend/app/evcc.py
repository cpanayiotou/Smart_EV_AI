from typing import Any
import httpx
from .config import settings
from .models import SiteTelemetry, LoadpointTelemetry, TelemetrySnapshot

class EvccClient:
    """Read-only Phase 1 adapter for evcc's documented system state API."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.evcc_base_url).rstrip("/")

    async def state(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=settings.evcc_timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/api/state")
            response.raise_for_status()
            payload = response.json()
            # evcc responses may wrap the state in "result".
            return payload.get("result", payload)

    async def snapshot(self) -> TelemetrySnapshot:
        raw = await self.state()
        grid = _nested(raw, "grid", "power")
        site = SiteTelemetry(
            home_power_w=_num(raw.get("homePower")),
            pv_power_w=_num(raw.get("pvPower")),
            grid_power_w=_num(grid),
            grid_importing=(grid > 0) if isinstance(grid, (int, float)) else None,
            tariff_grid=_num(raw.get("tariffGrid")),
        )
        loadpoints = []
        for index, lp in enumerate(raw.get("loadpoints") or [], start=1):
            loadpoints.append(LoadpointTelemetry(
                id=index,
                title=lp.get("title"),
                connected=lp.get("connected"),
                charging=lp.get("charging"),
                enabled=lp.get("enabled"),
                mode=lp.get("mode"),
                charge_power_w=_num(lp.get("chargePower")),
                charged_energy_wh=_num(lp.get("chargedEnergy")),
                vehicle_soc_pct=_num(lp.get("vehicleSoc")),
                vehicle_range_km=_num(lp.get("vehicleRange")),
                phases_active=_int(lp.get("phasesActive")),
                session_energy_wh=_num(lp.get("sessionEnergy")),
                session_solar_percentage=_num(lp.get("sessionSolarPercentage")),
            ))
        return TelemetrySnapshot(site=site, loadpoints=loadpoints)

def _nested(value: dict[str, Any], *keys: str) -> Any:
    cur: Any = value
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur

def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _int(value: Any) -> int | None:
    n = _num(value)
    return int(n) if n is not None else None
