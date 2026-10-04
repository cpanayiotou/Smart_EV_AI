from fastapi.testclient import TestClient
from app.main import app, sessions

client=TestClient(app)

def test_acceptance_api_records_session_for_history_and_learning():
    before=len(sessions.all())
    response=client.post("/api/v1/simulation/acceptance/monday-larnaca")
    assert response.status_code==200
    data=response.json()
    assert data["target_reached"] is True
    assert data["history_recorded"] is True
    assert data["pwa_ready"] is True
    assert data["simulation_only"] is True
    assert data["actuation_performed"] is False
    assert data["session"]["soc_start_pct"]==30
    assert 42 <= data["session"]["soc_end_pct"] < 43
    assert len(sessions.all())==before+1

    history=client.get("/api/v1/history").json()
    assert history["sessions"][-1]["soc_start_pct"]==30
    assert history["sessions"][-1]["soc_end_pct"] >= 42
