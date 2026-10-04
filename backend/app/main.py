from fastapi import FastAPI, HTTPException
import httpx
from .config import settings
from .evcc import EvccClient
from .models import TelemetrySnapshot
from .simulator import HomeSimulator

app = FastAPI(title="Smart EV AI", version="0.1.0",
              description="Local-first intelligence layer for evcc. Phase 1 is read-only.")
evcc = EvccClient()
simulator = HomeSimulator()

@app.get("/health")
async def health() -> dict[str, object]:
    return {"status":"ok","mode":"simulation" if settings.simulation_enabled else "read-only-live",
            "live_actuation":False}

@app.get("/api/v1/telemetry", response_model=TelemetrySnapshot)
async def telemetry() -> TelemetrySnapshot:
    if settings.simulation_enabled:
        return simulator.snapshot()
    try:
        return await evcc.snapshot()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="evcc telemetry unavailable") from exc

@app.get("/api/v1/safety")
async def safety() -> dict[str, object]:
    return {"battery_guardian":"enabled-policy-design","normal_daily_soc_limit_pct":80,
            "simulation":settings.simulation_enabled,"live_actuation":False,
            "reason":"Development validates simulation and telemetry before any AI write path is enabled."}
