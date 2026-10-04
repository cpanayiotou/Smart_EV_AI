from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CYPRUS=ZoneInfo("Europe/Nicosia")

@dataclass(frozen=True)
class RecurringJourney:
    days:tuple[int,...]
    depart:time|None
    origin:str
    destination:str
    return_time:time|None
    distance_km:float|None
    certainty:str
    note:str=""

COMMUTE_PROFILE=[
    RecurringJourney((0,1,2,3),time(7,30),"Lakatamia","Splish Splash, Larnaca",time(18,0),None,"required",
        "Regular Monday-Thursday commute. Route energy/distance must come from ABRP."),
    RecurringJourney((4,),time(7,30),"Lakatamia","Stasikratous, Nicosia",time(16,0),None,"required",
        "Regular Friday commute. Route energy/distance must come from ABRP."),
    RecurringJourney((5,),time(10,0),"Lakatamia","Short Saturday journey",None,5.0,"required",
        "Approx. 5 km during the 10:00-10:20 period."),
    RecurringJourney((5,),time(11,15),"Saturday location","Saturday journey 2",None,None,"incomplete",
        "11:15-11:45; distance/destination not yet defined."),
    RecurringJourney((5,),time(12,15),"Saturday location","Saturday journey 3",None,None,"incomplete",
        "12:15-12:45; distance/destination not yet defined."),
    RecurringJourney((6,),None,"Lakatamia","Optional Sunday trip",None,60.0,"optional",
        "Approx. 60 km; departure unknown. Must not create a charging deadline until confirmed."),
]

def _occurrence(j:RecurringJourney,d:date)->datetime|None:
    if j.depart is None:return None
    return datetime.combine(d,j.depart,tzinfo=CYPRUS)

def next_required_journey(now:datetime)->dict|None:
    now=now.astimezone(CYPRUS)
    candidates=[]
    for offset in range(8):
        d=now.date()+timedelta(days=offset)
        for j in COMMUTE_PROFILE:
            if d.weekday() not in j.days or j.certainty!="required":continue
            dt=_occurrence(j,d)
            if dt and dt>now:candidates.append((dt,j))
    if not candidates:return None
    dt,j=min(candidates,key=lambda x:x[0])
    return {"departure":dt.isoformat(),"origin":j.origin,"destination":j.destination,
        "distance_km":j.distance_km,"hours_until":round((dt-now).total_seconds()/3600,2),
        "route_energy_status":"known" if j.distance_km is not None else "awaiting_abrp",
        "charging_deadline":True}

def profile_payload()->list[dict]:
    return [{"days":list(j.days),"depart":j.depart.strftime("%H:%M") if j.depart else None,
        "origin":j.origin,"destination":j.destination,
        "return_time":j.return_time.strftime("%H:%M") if j.return_time else None,
        "distance_km":j.distance_km,"certainty":j.certainty,"note":j.note} for j in COMMUTE_PROFILE]
