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

    async def demo_command(self, mode: str, max_current_a: int, phases: int) -> dict[str, Any]:
        """Execute commands only when the explicit demo-write gate is enabled.

        This adapter is for the isolated upstream-evcc demo runtime used by CI.
        Production/physical charger actuation remains disabled by default.
        """
        if not settings.evcc_write_enabled:
            raise RuntimeError("evcc write gate is disabled")
        if mode not in {"off", "smart", "now"}:
            raise ValueError("unsupported evcc mode")
        if not 6 <= max_current_a <= 16:
            raise ValueError("max current must be 6..16 A")
        if phases not in {0, 1, 3}:
            raise ValueError("phases must be 0, 1 or 3")
        async with httpx.AsyncClient(timeout=settings.evcc_timeout_seconds) as client:
            for path in (
                f"/api/loadpoints/1/mode/{mode}",
                f"/api/loadpoints/1/maxcurrent/{max_current_a}",
                f"/api/loadpoints/1/phases/{phases}",
            ):
                response = await client.post(f"{self.base_url}{path}")
                response.raise_for_status()
        return await self.state()

    async def snapshot(self) -> TelemetrySnapshot:
        raw = await self.state()
        grid = _num(raw.get("gridPower"))
        # Current evcc /api/state exposes top-level gridPower/pvPower/homePower.
        # Keep legacy nested-grid fallback for fixtures/older states only.
        if grid is None:
            grid = _num(_nested(raw, "grid", "power"))
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
                vehicle_soc_pct=_num(lp.get("vehicleSoc") if lp.get("vehicleSoc") is not None else lp.get("vehicleSoC")),
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
