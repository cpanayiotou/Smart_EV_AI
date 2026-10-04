import pytest
import httpx
from app.evcc import EvccClient, _num, _int, _nested

def test_numeric_helpers():
    assert _num("42.5")==42.5
    assert _num(True) is None
    assert _int("3")==3

def test_nested():
    assert _nested({"grid":{"power":-120.0}},"grid","power")==-120.0
    assert _nested({},"grid","power") is None

@pytest.mark.asyncio
async def test_current_evcc_state_contract(monkeypatch):
    payload={"result":{
        "gridPower":1250.0,"pvPower":3200.0,"homePower":1950.0,
        "loadpoints":[{"title":"Simulated Peblar","connected":True,"charging":False,
        "enabled":False,"mode":"off","chargePower":0,"vehicleSoc":46,
        "phasesActive":3,"sessionEnergy":0}]
    }}
    async def fake_get(self,url):
        return httpx.Response(200,json=payload,request=httpx.Request("GET",url))
    monkeypatch.setattr(httpx.AsyncClient,"get",fake_get)
    snap=await EvccClient("http://evcc:7070").snapshot()
    assert snap.site.grid_power_w==1250
    assert snap.site.grid_importing is True
    assert snap.site.pv_power_w==3200
    assert snap.loadpoints[0].vehicle_soc_pct==46
    assert snap.loadpoints[0].phases_active==3
