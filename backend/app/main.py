from fastapi import FastAPI, HTTPException
import httpx
from .evcc import EvccClient
from .models import TelemetrySnapshot

app = FastAPI(
    title="Smart EV AI",
    version="0.1.0",
    description="Local-first intelligence layer for evcc. Phase 1 is read-only.",
)
evcc = EvccClient()

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "read-only"}

@app.get("/api/v1/telemetry", response_model=TelemetrySnapshot)
async def telemetry() -> TelemetrySnapshot:
    try:
        return await evcc.snapshot()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="evcc telemetry unavailable") from exc

@app.get("/api/v1/safety")
async def safety() -> dict[str, object]:
    return {
        "battery_guardian": "enabled-policy-design",
        "normal_daily_soc_limit_pct": 80,
        "live_actuation": False,
        "reason": "Phase 1 validates telemetry before any AI write path is enabled.",
    }
