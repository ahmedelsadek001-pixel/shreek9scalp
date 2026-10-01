"""Fail-closed V5.3 execution-safety evidence gate.

This module evaluates evidence about paper/shadow execution controls only. It
never authorizes MT5, opens a broker connection, or sends an order.
"""
from __future__ import annotations

from dataclasses import dataclass

from execution.broker_outcome import BrokerOutcome, BrokerOutcomeDecision
from execution.execution_journal import JournalSnapshot, validate_snapshot
from execution.idempotency import IdempotencyLedger
from execution.quote_safety import QuoteSafetyDecision
from execution.reconciliation import ReconciliationResult
from execution.recovery import RecoveryDecision, RecoveryState


@dataclass(frozen=True)
class ExecutionSafetyEvidence:
    quote_safety_validated: bool
    idempotency_validated: bool
    outcome_classification_validated: bool
    reconciliation_validated: bool
    recovery_validated: bool
    journal_integrity_validated: bool
    live_execution_disabled: bool


@dataclass(frozen=True)
class ExecutionSafetyDecision:
    ready: bool
    failures: tuple[str, ...]


def evaluate_execution_safety(evidence: ExecutionSafetyEvidence) -> ExecutionSafetyDecision:
    """Require every V5.3 control and the live-disabled invariant explicitly."""
    if not isinstance(evidence, ExecutionSafetyEvidence):
        raise TypeError("evidence must be ExecutionSafetyEvidence")
    checks = {
        "quote safety is not validated": evidence.quote_safety_validated,
        "idempotency is not validated": evidence.idempotency_validated,
        "broker outcome classification is not validated": evidence.outcome_classification_validated,
        "execution reconciliation is not validated": evidence.reconciliation_validated,
        "disconnect/recovery is not validated": evidence.recovery_validated,
        "execution journal integrity is not validated": evidence.journal_integrity_validated,
        "live execution is not explicitly disabled": evidence.live_execution_disabled,
    }
    failures = tuple(reason for reason, passed in checks.items() if type(passed) is not bool or not passed)
    return ExecutionSafetyDecision(not failures, failures)


def require_execution_safety(evidence: ExecutionSafetyEvidence) -> None:
    """Raise instead of allowing an incomplete V5.3 evidence package."""
    decision = evaluate_execution_safety(evidence)
    if not decision.ready:
        raise RuntimeError("V5.3 execution-safety gate blocked: " + "; ".join(decision.failures))


def derive_execution_safety_evidence(
    *,
    quote_decisions: tuple[QuoteSafetyDecision, ...],
    outcome_decisions: tuple[BrokerOutcomeDecision, ...],
    ledger: IdempotencyLedger,
    journal: JournalSnapshot,
    recovery: RecoveryDecision,
    reconciliation_results: tuple[ReconciliationResult, ...],
    live_execution_enabled: bool,
) -> ExecutionSafetyEvidence:
    """Derive V5.3 evidence from validated runtime artifacts.

    This helper is intentionally conservative: empty samples, malformed
    objects, checksum mismatches, unresolved recovery state, or enabled live
    execution all produce a failing evidence field. It has no transport
    authority and never contacts MT5.
    """
    quote_ok = (
        isinstance(quote_decisions, tuple)
        and bool(quote_decisions)
        and all(
            isinstance(item, QuoteSafetyDecision)
            and type(item.allowed) is bool
            and isinstance(item.reason, str)
            and bool(item.reason.strip())
            for item in quote_decisions
        )
    )

    outcome_ok = (
        isinstance(outcome_decisions, tuple)
        and bool(outcome_decisions)
        and all(
            isinstance(item, BrokerOutcomeDecision)
            and isinstance(item.outcome, BrokerOutcome)
            and type(item.retry_allowed) is bool
            and isinstance(item.reason, str)
            and bool(item.reason.strip())
            and (item.retry_allowed is (item.outcome is BrokerOutcome.REJECTED_RETRYABLE))
            for item in outcome_decisions
        )
    )

    idempotency_ok = isinstance(ledger, IdempotencyLedger)
    ledger_records = ()
    if idempotency_ok:
        try:
            ledger_records = ledger.records()
            idempotency_ok = bool(ledger_records)
        except (TypeError, ValueError, AttributeError):
            idempotency_ok = False

    journal_ok = False
    if isinstance(journal, JournalSnapshot) and idempotency_ok:
        try:
            validate_snapshot(journal)
            journal_ok = journal.records == ledger_records
        except (TypeError, ValueError, AttributeError):
            journal_ok = False

    recovery_ok = (
        isinstance(recovery, RecoveryDecision)
        and recovery.state is RecoveryState.CONNECTED
        and type(recovery.can_submit) is bool
        and recovery.can_submit is True
        and isinstance(recovery.reason, str)
        and bool(recovery.reason.strip())
    )

    reconciliation_ok = (
        isinstance(reconciliation_results, tuple)
        and bool(reconciliation_results)
        and all(
            isinstance(item, ReconciliationResult)
            and type(item.matched) is bool
            and item.matched is True
            and isinstance(item.reasons, tuple)
            for item in reconciliation_results
        )
    )

    return ExecutionSafetyEvidence(
        quote_safety_validated=quote_ok,
        idempotency_validated=idempotency_ok,
        outcome_classification_validated=outcome_ok,
        reconciliation_validated=reconciliation_ok,
        recovery_validated=recovery_ok,
        journal_integrity_validated=journal_ok,
        live_execution_disabled=type(live_execution_enabled) is bool and live_execution_enabled is False,
    )
