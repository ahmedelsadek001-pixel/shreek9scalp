"""Serializable fail-closed execution recovery snapshot for SHREEK V5.3."""
from __future__ import annotations

from dataclasses import dataclass

from execution.idempotency import IdempotencyLedger, SubmissionState


@dataclass(frozen=True)
class RecoverySnapshot:
    unresolved_order_ids: tuple[str, ...]


def snapshot_unresolved(ledger: IdempotencyLedger) -> RecoverySnapshot:
    if not isinstance(ledger, IdempotencyLedger):
        raise TypeError("ledger must be IdempotencyLedger")
    records = getattr(ledger, "_records", None)
    if not isinstance(records, dict):
        raise ValueError("ledger storage unavailable")

    unresolved: list[str] = []
    for key, record in records.items():
        if type(key) is not str or not key.strip():
            raise ValueError("ledger contains malformed order identity")
        state = getattr(record, "state", None)
        if not isinstance(state, SubmissionState):
            raise ValueError("ledger contains malformed submission state")
        if state in (SubmissionState.IN_FLIGHT, SubmissionState.UNKNOWN):
            unresolved.append(key)

    if len(unresolved) != len(set(unresolved)):
        raise ValueError("ledger contains duplicate order identities")
    return RecoverySnapshot(tuple(sorted(unresolved)))


def validate_restart(snapshot: RecoverySnapshot) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(snapshot, RecoverySnapshot):
        raise TypeError("snapshot must be RecoverySnapshot")
    if (
        not isinstance(snapshot.unresolved_order_ids, tuple)
        or any(type(x) is not str or not x.strip() for x in snapshot.unresolved_order_ids)
    ):
        return False, ("recovery snapshot malformed",)
    if len(snapshot.unresolved_order_ids) != len(set(snapshot.unresolved_order_ids)):
        return False, ("recovery snapshot contains duplicate identities",)
    if tuple(sorted(snapshot.unresolved_order_ids)) != snapshot.unresolved_order_ids:
        return False, ("recovery snapshot is not canonical",)
    if snapshot.unresolved_order_ids:
        return False, tuple(
            f"unresolved order requires reconciliation: {x}"
            for x in snapshot.unresolved_order_ids
        )
    return True, ()
