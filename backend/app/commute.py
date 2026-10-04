from __future__ import annotations
from dataclasses import dataclass
from datetime import time

@dataclass(frozen=True)
class RecurringJourney:
    days: tuple[int,...]  # Monday=0
    depart: time
    origin: str
    destination: str
    return_time: time|None
    distance_km: float|None
    certainty: str
    note: str=""

COMMUTE_PROFILE=[
    RecurringJourney((0,1,2,3),time(7,30),"Lakatamia","Splish Splash, Larnaca",time(18,0),None,"required",
        "Regular Monday-Thursday commute. Route energy/distance will come from ABRP; do not invent it."),
    RecurringJourney((4,),time(7,30),"Lakatamia","Stasikratous, Nicosia",time(16,0),None,"required",
        "Regular Friday commute. Route energy/distance will come from ABRP."),
    RecurringJourney((5,),time(10,0),"Lakatamia","Short Saturday journey",None,5.0,"required",
        "User described approximately 5 km during the 10:00-10:20 period."),
    RecurringJourney((5,),time(11,15),"Saturday location","Saturday journey 2",None,None,"required",
        "Journey window described as 11:15-11:45; distance/destination not yet defined."),
    RecurringJourney((5,),time(12,15),"Saturday location","Saturday journey 3",None,None,"required",
        "Journey window described as 12:15-12:45; distance/destination not yet defined."),
    RecurringJourney((6,),time(9,0),"Lakatamia","Optional Sunday trip",None,60.0,"optional",
        "Approx. 60 km and optional. Placeholder 09:00 is not a charging deadline; actual departure is unknown."),
]

def profile_payload()->list[dict]:
    return [{
        "days":list(j.days),"depart":j.depart.strftime("%H:%M"),"origin":j.origin,
        "destination":j.destination,"return_time":j.return_time.strftime("%H:%M") if j.return_time else None,
        "distance_km":j.distance_km,"certainty":j.certainty,"note":j.note
    } for j in COMMUTE_PROFILE]
