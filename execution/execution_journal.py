"""Durable, checksum-protected execution journal for SHREEK V5.3."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from execution.idempotency import SubmissionRecord,SubmissionState,validate_intent_fingerprint

@dataclass(frozen=True)
class JournalSnapshot:
    records: tuple[SubmissionRecord,...]
    checksum: str

def _payload(records):
    payload=[]
    for r in sorted(records,key=lambda x:x.order_id):
        item={"order_id":r.order_id,"state":r.state.value,"attempts":r.attempts}
        if r.intent_fingerprint is not None:
            item["intent_fingerprint"]=r.intent_fingerprint
        payload.append(item)
    return payload

def build_snapshot(records:tuple[SubmissionRecord,...])->JournalSnapshot:
    if not isinstance(records,tuple): raise TypeError("records must be tuple")
    seen=set()
    for r in records:
        if not isinstance(r,SubmissionRecord): raise TypeError("invalid journal record")
        if type(r.order_id) is not str or not r.order_id.strip() or r.order_id != r.order_id.strip():
            raise ValueError("invalid journal order identity")
        if not isinstance(r.state,SubmissionState) or r.state is SubmissionState.NEW:
            raise ValueError("invalid journal submission state")
        if r.order_id in seen or type(r.attempts) is not int or r.attempts<1:
            raise ValueError("invalid or duplicate journal record")
        validate_intent_fingerprint(r.intent_fingerprint)
        seen.add(r.order_id)
    raw=json.dumps(_payload(records),sort_keys=True,separators=(",",":"))
    return JournalSnapshot(records,sha256(raw.encode()).hexdigest())

def validate_snapshot(snapshot:JournalSnapshot)->None:
    if not isinstance(snapshot,JournalSnapshot): raise TypeError("snapshot must be JournalSnapshot")
    rebuilt=build_snapshot(snapshot.records)
    if snapshot.checksum!=rebuilt.checksum: raise ValueError("execution journal checksum mismatch")

def serialize_snapshot(snapshot:JournalSnapshot)->str:
    validate_snapshot(snapshot)
    return json.dumps({"records":_payload(snapshot.records),"checksum":snapshot.checksum},sort_keys=True,separators=(",",":"))

def deserialize_snapshot(raw:str)->JournalSnapshot:
    if not isinstance(raw,str) or not raw.strip(): raise ValueError("journal payload required")
    try: data=json.loads(raw)
    except (TypeError,ValueError) as exc: raise ValueError("invalid execution journal JSON") from exc
    if not isinstance(data,dict) or set(data)!={"records","checksum"} or not isinstance(data["records"],list) or not isinstance(data["checksum"],str):
        raise ValueError("malformed execution journal")
    try:
        records=[]
        for x in data["records"]:
            if not isinstance(x,dict): raise ValueError("journal record must be an object")
            if "intent_fingerprint" in x and x["intent_fingerprint"] is None:
                raise ValueError("explicit intent fingerprint must not be null")
            records.append(SubmissionRecord(x["order_id"],SubmissionState(x["state"]),x["attempts"],x.get("intent_fingerprint")))
        records=tuple(records)
    except (KeyError,TypeError,ValueError) as exc: raise ValueError("malformed execution journal record") from exc
    snapshot=JournalSnapshot(records,data["checksum"]); validate_snapshot(snapshot); return snapshot
