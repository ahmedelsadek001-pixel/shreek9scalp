"""Recovery admission must be issued by, and remain current for, its shadow."""
from dataclasses import replace
from datetime import datetime, timezone

from core.enums import Direction
from execution.broker_outcome import BrokerOutcome, BrokerOutcomeDecision
from execution.broker_safety import BrokerSafetyPolicy
from execution.execution_gate import evaluate_environment_gate
from execution.execution_journal import build_snapshot
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.idempotency import IdempotencyLedger, SubmissionState
from execution.operational_guard import OperationalPolicy, OperationalSnapshot
from execution.quote_safety import evaluate_quote_safety
from execution.reconciliation import ExecutionReport, OrderIntent, reconcile_execution
from execution.recovery import (
    RecoveryDecision,
    RecoveryState,
    ShadowRecovery,
    is_recovery_issued,
)
from execution.safety_gate import derive_execution_safety_evidence
from execution.shadow import ShadowExecution


def _intent(order_id: str) -> OrderIntent:
    return OrderIntent(order_id, "XAUUSD", Direction.BUY, .03, 2500)


def _environment_gate(recovery: RecoveryDecision):
    now = datetime.now(timezone.utc)
    return evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=OperationalSnapshot(now, now, now, True, True),
        broker_policy=BrokerSafetyPolicy(
            frozenset({"XAUUSD"}), 1.0, .01, 1.0, .5),
        symbol="XAUUSD", spread=.2, volume=.03, slippage=.1,
        kill_switch_active=False, recovery=recovery,
    )


def _safe_quote(intent: OrderIntent):
    now = datetime.now(timezone.utc)
    return evaluate_quote_safety(
        symbol=intent.symbol, direction=intent.direction,
        quote_time=now, now=now, intended_price=intent.expected_price,
        market_price=intent.expected_price, max_age_seconds=2,
        max_deviation_points=3, point_size=.01,
    )


def _execute(gate, order_id: str):
    calls: list[str] = []
    intent = _intent(order_id)
    result = GuardedExecutionAdapter(
        lambda received: calls.append(received.order_id) or "offline-accepted",
        IdempotencyLedger(),
    ).execute_intent(gate, intent, _safe_quote(intent))
    return result, calls


def test_forged_positive_recovery_cannot_bypass_pending_shadow_order():
    shadow = ShadowExecution()
    shadow.submit_intent(_intent("pending-forged"))
    actual = ShadowRecovery(shadow).admission()
    forged = RecoveryDecision(
        RecoveryState.CONNECTED, True, "execution channel available")

    result, calls = _execute(_environment_gate(forged), "transport-forged")

    assert actual.can_submit is False
    assert not result.executed
    assert result.reasons == (
        "recovery decision not issued or no longer current",)
    assert calls == []


def test_issued_recovery_expires_when_shadow_state_changes():
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    stale = recovery.admission()
    shadow.submit_intent(_intent("pending-stale"))

    result, calls = _execute(_environment_gate(stale), "transport-stale")

    assert not recovery.admission().can_submit
    assert not result.executed
    assert result.reasons == (
        "recovery decision not issued or no longer current",)
    assert calls == []


def test_environment_gate_expires_when_shadow_changes_before_transport():
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    gate = _environment_gate(recovery.admission())
    shadow.submit_intent(_intent("pending-after-gate"))

    result, calls = _execute(gate, "transport-after-gate")

    assert not result.executed
    assert result.reasons == (
        "execution gate decision not issued by execution gate",)
    assert calls == []


def test_current_issued_recovery_allows_offline_control_path():
    recovery = ShadowRecovery(ShadowExecution())
    decision = recovery.admission()

    result, calls = _execute(
        _environment_gate(decision), "transport-current-control")

    assert is_recovery_issued(decision)
    assert result.executed
    assert calls == ["transport-current-control"]


def test_copy_and_edited_issued_recovery_fail_provenance():
    recovery = ShadowRecovery(ShadowExecution())
    decision = recovery.admission()
    copied = replace(decision)

    assert not is_recovery_issued(copied)
    assert not _environment_gate(copied).allowed

    object.__setattr__(decision, "reason", "caller-edited")
    assert not is_recovery_issued(decision)
    assert not _environment_gate(decision).allowed


def test_new_decision_supersedes_prior_decision_without_shadow_change():
    recovery = ShadowRecovery(ShadowExecution())
    superseded = recovery.admission()
    current = recovery.admission()

    assert not is_recovery_issued(superseded)
    assert is_recovery_issued(current)
    assert not _environment_gate(superseded).allowed
    assert _environment_gate(current).allowed


def test_disconnect_supersedes_connected_approval():
    recovery = ShadowRecovery(ShadowExecution())
    connected = recovery.admission()
    disconnected = recovery.disconnect()

    assert not is_recovery_issued(connected)
    assert is_recovery_issued(disconnected)
    assert not _environment_gate(connected).allowed
    assert not _environment_gate(disconnected).allowed


def test_successful_reconciliation_expires_prior_recovery_decision():
    shadow = ShadowExecution()
    shadow.submit_intent(_intent("pending-reconciled"))
    recovery = ShadowRecovery(shadow)
    blocked = recovery.admission()
    before = shadow.state_revision

    report = ExecutionReport(
        "pending-reconciled", "XAUUSD", Direction.BUY, .03, 2500)
    assert shadow.observe(report).matched

    assert shadow.state_revision == before + 1
    assert not is_recovery_issued(blocked)
    assert is_recovery_issued(recovery.admission())


def test_failed_reconciliation_keeps_revision_and_decision_current():
    shadow = ShadowExecution()
    shadow.submit_intent(_intent("pending-mismatch"))
    recovery = ShadowRecovery(shadow)
    blocked = recovery.admission()
    before = shadow.state_revision

    mismatch = ExecutionReport(
        "pending-mismatch", "XAUUSD", Direction.BUY, .04, 2500)
    assert not shadow.observe(mismatch).matched

    assert shadow.state_revision == before
    assert is_recovery_issued(blocked)


def test_unavailable_shadow_query_revokes_positive_decision(monkeypatch):
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    decision = recovery.admission()

    monkeypatch.setattr(shadow, "pending_order_ids", lambda: None)

    assert not is_recovery_issued(decision)
    assert not _environment_gate(decision).allowed


def test_forged_recovery_cannot_validate_runtime_safety_evidence():
    intent = _intent("safety-forged")
    ledger = IdempotencyLedger()
    ledger.begin(intent)
    ledger.finish(intent.order_id, SubmissionState.ACCEPTED)
    evidence = derive_execution_safety_evidence(
        quote_decisions=(_safe_quote(intent),),
        outcome_decisions=(BrokerOutcomeDecision(
            BrokerOutcome.ACCEPTED, False, "accepted"),),
        ledger=ledger,
        journal=build_snapshot(ledger.records()),
        recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "ready"),
        reconciliation_results=(reconcile_execution(
            intent,
            ExecutionReport(
                intent.order_id, intent.symbol, intent.direction,
                intent.volume, intent.expected_price,
            ),
        ),),
        live_execution_enabled=False,
    )

    assert evidence.recovery_validated is False
