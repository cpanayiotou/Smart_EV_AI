from dataclasses import dataclass

@dataclass(frozen=True)
class CostAdvice:
    grid_price_eur_kwh: float
    estimated_grid_cost_eur: float
    strategy: str
    reason: str

def advise(required_ac_kwh:float, expected_pv_kwh:float, grid_price_eur_kwh:float=0.30)->CostAdvice:
    grid=max(0.0,required_ac_kwh-expected_pv_kwh)
    cost=grid*grid_price_eur_kwh
    strategy="prefer_pv" if expected_pv_kwh>0 else "lowest_cost_window"
    return CostAdvice(grid_price_eur_kwh,round(cost,2),strategy,
        f"Estimated {grid:.1f} kWh grid energy after {min(required_ac_kwh,expected_pv_kwh):.1f} kWh PV.")
