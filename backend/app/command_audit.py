from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Optional
from uuid import uuid4

@dataclass(frozen=True)
class CommandAuditRecord:
    audit_id: str
    created_at: str
    environment: str
    execution_target: str
    actor: str
    requested_action: str
    requested_value: Any
    guardian_allowed: bool
    electrical_gate_safe: bool
    approval_required: bool
    approval_id: Optional[str]
    telemetry_observed_at: Optional[str]
    telemetry_sources: tuple[str, ...]
    outcome: str
    actuation_performed: bool
    reason: str
    previous_hash: Optional[str]
    record_hash: str

class CommandAuditTrail:
    def __init__(self):
        self._records:list[CommandAuditRecord]=[]

    def append(self, *, environment:str, execution_target:str, actor:str,
               requested_action:str, requested_value:Any, guardian_allowed:bool,
               electrical_gate_safe:bool, approval_required:bool=False,
               approval_id:Optional[str]=None, telemetry_observed_at:Optional[str]=None,
               telemetry_sources:tuple[str,...]=(), outcome:str="PROPOSED",
               actuation_performed:bool=False, reason:str="")->CommandAuditRecord:
        if environment != "simulation" and actuation_performed:
            raise ValueError("real actuation audit is locked in this phase")
        previous=self._records[-1].record_hash if self._records else None
        payload={
            "audit_id":str(uuid4()), "created_at":datetime.now(timezone.utc).isoformat(),
            "environment":environment, "execution_target":execution_target, "actor":actor,
            "requested_action":requested_action, "requested_value":requested_value,
            "guardian_allowed":guardian_allowed, "electrical_gate_safe":electrical_gate_safe,
            "approval_required":approval_required, "approval_id":approval_id,
            "telemetry_observed_at":telemetry_observed_at,
            "telemetry_sources":list(telemetry_sources), "outcome":outcome,
            "actuation_performed":actuation_performed, "reason":reason,
            "previous_hash":previous,
        }
        digest=sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
        rec=CommandAuditRecord(**{**payload,"telemetry_sources":tuple(telemetry_sources),"record_hash":digest})
        self._records.append(rec)
        return rec

    def all(self)->list[dict]:
        return [asdict(x) for x in self._records]

    def verify_chain(self)->bool:
        previous=None
        for rec in self._records:
            d=asdict(rec); digest=d.pop("record_hash"); d["telemetry_sources"]=list(d["telemetry_sources"])
            if d["previous_hash"] != previous: return False
            expected=sha256(json.dumps(d,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
            if expected != digest: return False
            previous=digest
        return True
