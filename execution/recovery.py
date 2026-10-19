"""Fail-closed shadow execution recovery state for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from execution.decision_provenance import IssuedDecisionRegistry
from execution.shadow import ShadowExecution


_RECOVERY_DECISION_CAPABILITY = object()
_ISSUED_RECOVERY_DECISIONS = IssuedDecisionRegistry()


class RecoveryState(Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    RECOVERING = "RECOVERING"


@dataclass(frozen=True)
class RecoveryDecision:
    state: RecoveryState
    can_submit: bool
    reason: str
    _capability: object | None = field(default=None, repr=False, compare=False)
    _owner: object | None = field(default=None, repr=False, compare=False)
    _decision_revision: int | None = field(default=None, repr=False, compare=False)
    _shadow_revision: int | None = field(default=None, repr=False, compare=False)


def _issued_state(decision: RecoveryDecision) -> tuple[object, ...]:
    return (
        decision.state, decision.can_submit, decision.reason,
        id(decision._owner), decision._decision_revision,
        decision._shadow_revision,
    )


class ShadowRecovery:
    """Connection state machine that blocks submissions until recovery is safe."""

    def __init__(self, shadow: ShadowExecution) -> None:
        if not isinstance(shadow, ShadowExecution):
            raise TypeError("shadow must be ShadowExecution")
        self._shadow = shadow
        self._state = RecoveryState.CONNECTED
        self._decision_revision = 0

    @property
    def shadow(self) -> ShadowExecution:
        return self._shadow

    @property
    def state(self) -> RecoveryState:
        return self._state

    def _pending_order_ids(self) -> tuple[str, ...] | None:
        """Return validated pending identities, or None when shadow state is untrustworthy."""
        try:
            pending = self._shadow.pending_order_ids()
        except Exception:
            return None
        if not isinstance(pending, tuple):
            return None
        if any(type(order_id) is not str or not order_id.strip() for order_id in pending):
            return None
        if len(pending) != len(set(pending)):
            return None
        return tuple(sorted(pending))

    def _issue(self, can_submit: bool, reason: str) -> RecoveryDecision:
        """Issue a decision bound to this state machine and shadow revision."""
        self._decision_revision += 1
        decision = RecoveryDecision(
            self._state,
            can_submit,
            reason,
            _RECOVERY_DECISION_CAPABILITY,
            self,
            self._decision_revision,
            self._shadow.state_revision,
        )
        _ISSUED_RECOVERY_DECISIONS.issue(decision, _issued_state(decision))
        return decision

    def _decision_is_current(self, decision: RecoveryDecision) -> bool:
        """Recheck mutable recovery facts before an approval is consumed."""
        try:
            shadow_revision = self._shadow.state_revision
        except Exception:
            return False
        if (type(self._decision_revision) is not int
                or type(shadow_revision) is not int
                or shadow_revision < 0
                or decision._owner is not self
                or type(decision._decision_revision) is not int
                or type(decision._shadow_revision) is not int
                or decision._decision_revision != self._decision_revision
                or decision._shadow_revision != shadow_revision
                or decision.state is not self._state):
            return False
        if decision.can_submit:
            return (decision.state is RecoveryState.CONNECTED
                    and self._pending_order_ids() == ())
        return True

    def disconnect(self) -> RecoveryDecision:
        self._state = RecoveryState.DISCONNECTED
        return self._issue(False, "execution channel disconnected")

    def begin_recovery(self) -> RecoveryDecision:
        if self._state is not RecoveryState.DISCONNECTED:
            return self._issue(False, "recovery requires disconnected state")
        self._state = RecoveryState.RECOVERING
        return self._issue(False, "recovery in progress")

    def complete_recovery(self) -> RecoveryDecision:
        if self._state is not RecoveryState.RECOVERING:
            return self._issue(False, "recovery is not in progress")
        pending = self._pending_order_ids()
        if pending is None:
            return self._issue(False, "shadow recovery state unavailable")
        if pending:
            return self._issue(False, "pending shadow orders require reconciliation")
        self._state = RecoveryState.CONNECTED
        return self._issue(True, "execution channel recovered")

    def admission(self) -> RecoveryDecision:
        if self._state is not RecoveryState.CONNECTED:
            return self._issue(False, "execution channel is not ready")
        pending = self._pending_order_ids()
        if pending is None:
            return self._issue(False, "shadow recovery state unavailable")
        if pending:
            return self._issue(False, "pending shadow orders require reconciliation")
        return self._issue(True, "execution channel available")


def is_recovery_issued(decision: RecoveryDecision) -> bool:
    """Return whether a recovery decision is authentic and still current."""
    if (not isinstance(decision, RecoveryDecision)
            or decision._capability is not _RECOVERY_DECISION_CAPABILITY
            or not isinstance(decision._owner, ShadowRecovery)
            or not _ISSUED_RECOVERY_DECISIONS.is_issued(
                decision, _issued_state(decision))):
        return False
    return decision._owner._decision_is_current(decision)
