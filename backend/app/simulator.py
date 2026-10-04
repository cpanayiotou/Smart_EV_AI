from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import pi, sin
from zoneinfo import ZoneInfo
from .models import SiteTelemetry, LoadpointTelemetry, TelemetrySnapshot

CYPRUS=ZoneInfo("Europe/Nicosia")

@dataclass
class SimulationConfig:
    battery_capacity_kwh:float=86.5 # development assumption, configurable
    initial_soc_pct:float=46.0
    target_soc_pct:float=80.0
    max_pv_w:float=5000.0
    max_ac_charge_w:float=11000.0
    ac_to_battery_efficiency:float=0.90 # simulation assumption only
    service_limit_a:float=32.0 # provisional; must be verified on site

class HomeSimulator:
    """Stateful deterministic digital twin. Never talks to physical hardware."""
    def __init__(self,config:SimulationConfig|None=None):
        self.cfg=config or SimulationConfig()
        self.reset()

    def reset(self,start:datetime|None=None)->None:
        self.now=start or datetime.now(CYPRUS).replace(second=0,microsecond=0)
        self.soc=self.cfg.initial_soc_pct
        self.energy_wh=0.0
        self.grid_import_wh=0.0
        self.grid_export_wh=0.0
        self.pv_wh=0.0
        self.ev_pv_wh=0.0
        self.ev_grid_wh=0.0

    def _powers(self,now:datetime)->tuple[float,float,bool,float,int]:
        hour=now.hour+now.minute/60
        daylight=max(0.0,sin(pi*(hour-6.5)/12.0)) if 6.5<=hour<=18.5 else 0.0
        pv=self.cfg.max_pv_w*daylight
        base=650.0
        morning=1150.0 if 6.5<=hour<=9.0 else 0.0
        evening=1650.0 if 18.0<=hour<=22.5 else 0.0
        house=base+morning+evening
        plugged=hour>=17.0 or hour<8.0
        surplus=max(0.0,pv-house)
        charge=0.0
        phases=0
        if plugged and self.soc<self.cfg.target_soc_pct and surplus>=1380:
            # Simplified evcc-like surplus model; exact real switching remains evcc's job.
            if surplus<4140:
                phases=1
                charge=min(3680.0,surplus) # simulated 1P band
            else:
                phases=3
                charge=min(self.cfg.max_ac_charge_w,surplus)
        return pv,house,plugged,charge,phases

    def step(self,seconds:int=60)->TelemetrySnapshot:
        seconds=max(1,min(int(seconds),3600))
        pv,house,plugged,charge,phases=self._powers(self.now)
        hours=seconds/3600
        grid=house+charge-pv
        self.pv_wh+=pv*hours
        if grid>=0:self.grid_import_wh+=grid*hours
        else:self.grid_export_wh+=(-grid)*hours
        if charge>0:
            # Attribute EV AC energy by source for simulation analytics. PV first serves the house;\n            # only the remaining PV can supply the EV. Any balance is grid energy.\n            ev_pv=min(charge,max(0.0,pv-house))\n            ev_grid=max(0.0,charge-ev_pv)\n            self.ev_pv_wh+=ev_pv*hours\n            self.ev_grid_wh+=ev_grid*hours\n            self.energy_wh+=charge*hours
            battery_kwh=charge*hours/1000*self.cfg.ac_to_battery_efficiency
            self.soc=min(self.cfg.target_soc_pct,self.soc+(battery_kwh/self.cfg.battery_capacity_kwh*100))
        self.now+=timedelta(seconds=seconds)
        return self.snapshot()

    def advance(self,minutes:int,step_seconds:int=60)->TelemetrySnapshot:
        remaining=max(0,int(minutes)*60)
        snap=self.snapshot()
        while remaining:
            s=min(step_seconds,remaining)
            snap=self.step(s)
            remaining-=s
        return snap

    def snapshot(self,now:datetime|None=None)->TelemetrySnapshot:
        if now is not None:self.now=now.astimezone(CYPRUS)
        pv,house,plugged,charge,phases=self._powers(self.now)
        grid=house+charge-pv
        return TelemetrySnapshot(
            site=SiteTelemetry(timestamp=self.now,home_power_w=round(house+charge,1),
                pv_power_w=round(pv,1),grid_power_w=round(grid,1),grid_importing=grid>0),
            loadpoints=[LoadpointTelemetry(id=1,title="Audi e-tron 55",connected=plugged,
                charging=charge>0,enabled=plugged,mode="pv",charge_power_w=round(charge,1),
                charged_energy_wh=round(self.energy_wh,1),vehicle_soc_pct=round(self.soc,2),
                phases_active=phases,session_energy_wh=round(self.energy_wh,1))],
            source="simulator",read_only=True)

    def apply_shadow_objective(self,target_soc_pct:int)->dict:\n        """Apply an AI objective only to the in-memory digital twin. Never touches evcc or hardware."""\n        target=max(0,min(100,int(target_soc_pct)))\n        previous=self.cfg.target_soc_pct\n        self.cfg.target_soc_pct=float(target)\n        return {"previous_target_soc_pct":previous,"target_soc_pct":target,"simulation_only":True}\n\n    def status(self)->dict:
        return {"time":self.now.isoformat(),"soc_pct":round(self.soc,2),
            "ac_energy_kwh":round(self.energy_wh/1000,3),
            "pv_generated_kwh":round(self.pv_wh/1000,3),
            "grid_import_kwh":round(self.grid_import_wh/1000,3),
            "grid_export_kwh":round(self.grid_export_wh/1000,3),\n            "ev_pv_energy_kwh":round(self.ev_pv_wh/1000,3),\n            "ev_grid_energy_kwh":round(self.ev_grid_wh/1000,3),
            "target_soc_pct":self.cfg.target_soc_pct,"live_actuation":False}
