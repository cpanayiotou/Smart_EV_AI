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
from .learning import SessionStore, ChargingSession
from .acceptance import run_monday_larnaca_acceptance
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


from .simulated_routes import payload as simulated_route_payload

@app.get("/api/v1/mobility/simulated-routes")
async def simulated_routes()->dict:
    return {
        "routes":simulated_route_payload(),
        "warning":"Distances are web-researched simulation values and consumption is an assumption. Replace with ABRP and learned Audi data when connected.",
        "mode":"simulation",
    }


from .departure_planner import build_departure_plan

@app.get("/api/v1/mobility/departure-plan")
async def departure_plan()->dict:
    snapshot=simulator.snapshot() if settings.simulation_enabled else await evcc.snapshot()
    result=build_departure_plan(simulator.now,snapshot)
    return {"plan":asdict(result) if result else None,"mode":"simulation" if settings.simulation_enabled else "read-only-live",
            "actuation_performed":False}


class ClosedLoopRequest(BaseModel):
    trip_distance_km:float=60
    requested_target_pct:int|None=None
    approved_once:bool=False
    advance_minutes:int=60

@app.post("/api/v1/simulation/closed-loop")
async def simulation_closed_loop(request:ClosedLoopRequest)->dict:
    before=simulator.snapshot()
    before_status=simulator.status()
    objective=plan(before,request.trip_distance_km,request.requested_target_pct,request.approved_once)
    if not objective.allowed:
        return {"objective":asdict(objective),"executed":False,
                "reason":"Battery Guardian did not allow the objective.","before":before.model_dump(mode="json"),
                "after":before.model_dump(mode="json"),"simulation_only":True}
    applied=simulator.apply_shadow_objective(objective.target_soc_pct)
    minutes=max(1,min(request.advance_minutes,24*60))
    after=simulator.advance(minutes)
    before_lp=before.loadpoints[0]
    after_lp=after.loadpoints[0]
    ac_delta=max(0.0,((after_lp.charged_energy_wh or 0)-(before_lp.charged_energy_wh or 0))/1000)
    if ac_delta>0:
        after_status=simulator.status()
        pv_delta=max(0.0,after_status["ev_pv_energy_kwh"]-before_status["ev_pv_energy_kwh"])
        grid_delta=max(0.0,after_status["ev_grid_energy_kwh"]-before_status["ev_grid_energy_kwh"])
        sessions.add(ChargingSession(started_at=before.site.timestamp,ac_energy_kwh=round(ac_delta,3),
            pv_energy_kwh=round(pv_delta,3),grid_energy_kwh=round(grid_delta,3),
            soc_start_pct=float(before_lp.vehicle_soc_pct or 0),soc_end_pct=float(after_lp.vehicle_soc_pct or 0),
            avg_charge_power_kw=round(ac_delta/(minutes/60),2),phases=int(after_lp.phases_active or 0),cost_eur=0.0))
    return {"objective":asdict(objective),"executed":True,"applied":applied,
            "before":before.model_dump(mode="json"),"after":after.model_dump(mode="json"),
            "result":{"soc_delta_pct":round((after.loadpoints[0].vehicle_soc_pct or 0)-(before.loadpoints[0].vehicle_soc_pct or 0),2),
                      "charged_energy_delta_wh":round((after.loadpoints[0].charged_energy_wh or 0)-(before.loadpoints[0].charged_energy_wh or 0),1)},
            "simulation_only":True,"evcc_actuation_performed":False}


@app.post("/api/v1/simulation/acceptance/monday-larnaca")
async def monday_larnaca_acceptance()->dict:
    """Run the deterministic milestone and expose its result to history/learning."""
    result=run_monday_larnaca_acceptance()
    raw=result["session"]
    session=ChargingSession(
        started_at=raw["started_at"],
        ac_energy_kwh=raw["ac_energy_kwh"],
        pv_energy_kwh=raw["pv_energy_kwh"],
        grid_energy_kwh=raw["grid_energy_kwh"],
        soc_start_pct=raw["soc_start_pct"],
        soc_end_pct=raw["soc_end_pct"],
        avg_charge_power_kw=raw["avg_charge_power_kw"],
        phases=raw["phases"],
        cost_eur=raw["cost_eur"],
    )
    sessions.add(session)
    return {
        **result,
        "history_recorded":True,
        "learning_session_count":len(sessions.all()),
        "pwa_ready":True,
    }
