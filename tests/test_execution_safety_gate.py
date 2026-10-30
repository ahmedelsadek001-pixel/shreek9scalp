import pytest

from core.enums import Direction
from execution.broker_outcome import BrokerOutcomeDecision, BrokerOutcome
from execution.execution_journal import build_snapshot
from execution.idempotency import IdempotencyLedger, SubmissionState
from execution.quote_safety import QuoteSafetyDecision
from execution.reconciliation import ExecutionReport, OrderIntent, ReconciliationResult, reconcile_execution
from execution.recovery import RecoveryDecision, RecoveryState
from execution.safety_gate import (
    ExecutionSafetyEvidence,
    derive_execution_safety_evidence,
    evaluate_execution_safety,
    require_execution_safety,
)


def _complete() -> ExecutionSafetyEvidence:
    return ExecutionSafetyEvidence(True, True, True, True, True, True, True)


def test_complete_v53_safety_evidence_passes_without_live_authority():
    decision = evaluate_execution_safety(_complete())
    assert decision.ready is True
    assert decision.failures == ()


@pytest.mark.parametrize(
    "field",
    [
        "quote_safety_validated",
        "idempotency_validated",
        "outcome_classification_validated",
        "reconciliation_validated",
        "recovery_validated",
        "journal_integrity_validated",
        "live_execution_disabled",
    ],
)
def test_each_missing_v53_control_blocks(field):
    values = _complete().__dict__
    values[field] = False
    decision = evaluate_execution_safety(ExecutionSafetyEvidence(**values))
    assert decision.ready is False
    assert decision.failures
    if field == "live_execution_disabled":
        assert "live execution" in decision.failures[0]


def test_non_boolean_evidence_fails_closed():
    values = _complete().__dict__
    values["recovery_validated"] = 1
    decision = evaluate_execution_safety(ExecutionSafetyEvidence(**values))
    assert decision.ready is False
    with pytest.raises(RuntimeError, match="V5.3 execution-safety gate blocked"):
        require_execution_safety(ExecutionSafetyEvidence(**values))


def test_raw_mapping_is_not_accepted():
    with pytest.raises(TypeError):
        evaluate_execution_safety({"live_execution_disabled": True})


def test_runtime_artifacts_derive_complete_safety_evidence():
    intent = OrderIntent("V53-1", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    ledger = IdempotencyLedger()
    ledger.begin(intent)
    ledger.finish(intent.order_id, SubmissionState.ACCEPTED)
    journal = build_snapshot(ledger.records())
    reconciliation = reconcile_execution(
        intent,
        ExecutionReport("V53-1", "XAUUSD", Direction.BUY, 0.03, 2500.0),
    )
    evidence = derive_execution_safety_evidence(
        quote_decisions=(QuoteSafetyDecision(True, "accepted"), QuoteSafetyDecision(False, "stale")),
        outcome_decisions=(BrokerOutcomeDecision(BrokerOutcome.ACCEPTED, False, "accepted"),),
        ledger=ledger,
        journal=journal,
        recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "ready"),
        reconciliation_results=(reconciliation,),
        live_execution_enabled=False,
    )
    assert evaluate_execution_safety(evidence).ready is True


def test_runtime_artifacts_fail_closed_on_journal_mismatch_or_live_enabled():
    ledger = IdempotencyLedger()
    evidence = derive_execution_safety_evidence(
        quote_decisions=(QuoteSafetyDecision(True, "accepted"),),
        outcome_decisions=(BrokerOutcomeDecision(BrokerOutcome.ACCEPTED, False, "accepted"),),
        ledger=ledger,
        journal=object(),
        recovery=RecoveryDecision(RecoveryState.CONNECTED, True, "ready"),
        reconciliation_results=(ReconciliationResult(True, ()),),
        live_execution_enabled=True,
    )
    decision = evaluate_execution_safety(evidence)
    assert decision.ready is False
    assert "idempotency" in " ".join(decision.failures)
    assert "journal" in " ".join(decision.failures)
    assert "live execution" in " ".join(decision.failures)
