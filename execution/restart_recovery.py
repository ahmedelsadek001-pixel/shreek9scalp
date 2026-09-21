"""Serializable fail-closed execution recovery snapshot for SHREEK V5.3."""
from __future__ import annotations
from dataclasses import dataclass
from execution.idempotency import IdempotencyLedger, SubmissionState

@dataclass(frozen=True)
class RecoverySnapshot:
    unresolved_order_ids: tuple[str,...]

def snapshot_unresolved(ledger:IdempotencyLedger)->RecoverySnapshot:
    if not isinstance(ledger,IdempotencyLedger): raise TypeError("ledger must be IdempotencyLedger")
    # Access is intentionally exposed through known identities supplied by caller in
    # production persistence; this helper restores explicit serialized IDs only.
    records=getattr(ledger,"_records",None)
    if not isinstance(records,dict): raise ValueError("ledger storage unavailable")
    unresolved=tuple(sorted(k for k,v in records.items() if v.state in (SubmissionState.IN_FLIGHT,SubmissionState.UNKNOWN)))
    return RecoverySnapshot(unresolved)

def validate_restart(snapshot:RecoverySnapshot)->tuple[bool,tuple[str,...]]:
    if not isinstance(snapshot,RecoverySnapshot): raise TypeError("snapshot must be RecoverySnapshot")
    if not isinstance(snapshot.unresolved_order_ids,tuple) or any(not isinstance(x,str) or not x.strip() for x in snapshot.unresolved_order_ids):
        return False,("recovery snapshot malformed",)
    if len(snapshot.unresolved_order_ids)!=len(set(snapshot.unresolved_order_ids)):
        return False,("recovery snapshot contains duplicate identities",)
    if snapshot.unresolved_order_ids:
        return False,tuple(f"unresolved order requires reconciliation: {x}" for x in snapshot.unresolved_order_ids)
    return True,()
