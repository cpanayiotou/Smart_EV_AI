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


from .orchestrator import plan

@app.get("/api/v1/plan")
async def ai_plan(trip_distance_km: float = 60, requested_target_pct: int | None = None,
                  approved_once: bool = False) -> dict:
    snapshot = simulator.snapshot() if settings.simulation_enabled else await evcc.snapshot()
    objective = plan(snapshot, trip_distance_km, requested_target_pct, approved_once)
    return {
        "target_soc_pct": objective.target_soc_pct,
        "mode": objective.mode,
        "approval_required": objective.approval_required,
        "allowed": objective.allowed,
        "explanation": objective.explanation,
        "shadow_mode": True,
        "actuation_performed": False,
    }


from dataclasses import asdict
from .learning import SessionStore
from .cost_agent import advise as cost_advice
from .efficiency_agent import advise as efficiency_advice

sessions = SessionStore()

@app.get("/api/v1/history")
async def history() -> dict:
    return {
        "summary": sessions.summary(),
        "sessions": [asdict(x) for x in sessions.all()],
        "source": "simulation",
    }

@app.get("/api/v1/agents")
async def agent_status(required_ac_kwh: float = 20, expected_pv_kwh: float = 12) -> dict:
    return {
        "cost": asdict(cost_advice(required_ac_kwh, expected_pv_kwh)),
        "efficiency": asdict(efficiency_advice(sessions.all())),
        "battery_guardian": {"status":"active","normal_daily_limit_pct":80},
        "mode":"shadow",
        "actuation_performed":False,
    }


from pydantic import BaseModel

class AdvanceRequest(BaseModel):
    minutes:int=60

@app.get("/api/v1/simulation")
async def simulation_status()->dict:
    return {"status":simulator.status(),"telemetry":simulator.snapshot().model_dump(mode="json")}

@app.post("/api/v1/simulation/advance")
async def simulation_advance(request:AdvanceRequest)->dict:
    minutes=max(1,min(request.minutes,24*60))
    snapshot=simulator.advance(minutes)
    objective=plan(snapshot)
    return {"status":simulator.status(),"telemetry":snapshot.model_dump(mode="json"),
            "shadow_plan":asdict(objective)}

@app.post("/api/v1/simulation/reset")
async def simulation_reset()->dict:
    simulator.reset()
    return {"status":simulator.status(),"telemetry":simulator.snapshot().model_dump(mode="json")}


from .commute import profile_payload, next_required_journey

@app.get("/api/v1/mobility/profile")
async def mobility_profile()->dict:
    return {
        "timezone":"Europe/Nicosia",
        "profile":profile_payload(),
        "next_required_journey":next_required_journey(simulator.now),
        "distance_source":"ABRP planned; unknown route distances are intentionally not guessed",
        "mode":"simulation",
    }
