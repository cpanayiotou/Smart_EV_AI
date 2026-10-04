from app.cost_agent import advise as cost
from app.efficiency_agent import advise as efficiency
from app.learning import SessionStore

def test_cost_uses_pv_first():
    a=cost(20,12,0.30)
    assert a.estimated_grid_cost_eur==2.4
    assert a.strategy=="prefer_pv"

def test_efficiency_refuses_to_overlearn_small_sample():
    a=efficiency(SessionStore().all())
    assert a.confidence=="low"
    assert a.preferred_profile=="evcc_dynamic"
