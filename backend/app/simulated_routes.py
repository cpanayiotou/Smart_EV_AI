from __future__ import annotations
from dataclasses import dataclass,asdict

@dataclass(frozen=True)
class SimulatedRoute:
    key:str
    label:str
    one_way_km:float
    round_trip_km:float
    assumed_kwh_per_100km:float
    reserve_pct:int
    confidence:str
    basis:str

    @property
    def simulated_trip_kwh(self)->float:
        return round(self.round_trip_km*self.assumed_kwh_per_100km/100,1)

# Route distances are web-researched development values, not ABRP/live navigation.
# Consumption is deliberately configurable simulation input and must be replaced by learned Audi/ABRP data.
ROUTES={
 "larnaca":SimulatedRoute("larnaca","Lakatamia ↔ Splish Splash, Larnaca",45.0,90.0,25.0,15,"medium",
    "Public route sources put Lakatamia-Larnaca around 42-53 km; Splish Splash is at Archiepiskopou Kyprianou 38. Use 45 km one-way as a conservative simulation midpoint until ABRP."),
 "stasikratous":SimulatedRoute("stasikratous","Lakatamia ↔ Stasikratous, Nicosia",8.0,16.0,27.0,15,"low",
    "Central Stasikratous is about 6.2 km from a Lakatamia reference in public local listings; 8 km one-way is used as a conservative simulation value until ABRP."),
 "sunday":SimulatedRoute("sunday","Optional Sunday trip",30.0,60.0,25.0,15,"user_estimate",
    "User supplied approximately 60 km total; optional and no departure deadline.")
}

def payload()->dict:
    return {k:{**asdict(v),"simulated_trip_kwh":v.simulated_trip_kwh,
        "energy_status":"SIMULATED_NOT_ABRP"} for k,v in ROUTES.items()}
