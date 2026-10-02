"""Original reservation binding, using only local ledger and journal APIs."""
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from core.enums import Direction
from execution.broker_outcome import classify_broker_outcome
from execution.execution_journal import build_snapshot, deserialize_snapshot, serialize_snapshot
from execution.execution_lifecycle import ExecutionLifecycleCoordinator
from execution.idempotency import IdempotencyLedger, SubmissionRecord, SubmissionState
from execution.reconciliation import ExecutionReport, OrderIntent
from execution.restart_recovery import snapshot_unresolved, validate_restart


def _intent():
    return OrderIntent("original-A", "XAUUSD", Direction.BUY, .03, 2500)


def _round_trip(ledger):
    raw = serialize_snapshot(build_snapshot(ledger.records()))
    restored = IdempotencyLedger.restore(deserialize_snapshot(raw).records)
    assert serialize_snapshot(build_snapshot(restored.records())) == raw
    return restored


def _operate(coordinator, intent, operation):
    if operation == "outcome":
        return coordinator.apply_outcome(intent, classify_broker_outcome(acknowledged=True, accepted=True))
    if operation == "report":
        report = ExecutionReport(intent.order_id, intent.symbol, intent.direction, intent.volume, intent.expected_price)
        return coordinator.reconcile(intent, report, price_tolerance=10, volume_tolerance=.1)
    return coordinator.resolve_unknown_presence(intent, broker_order_exists=operation == "presence")


@pytest.mark.parametrize("changes", [
    {"symbol": "EURUSD"}, {"direction": Direction.SELL},
    {"volume": .04}, {"expected_price": 2505},
])
@pytest.mark.parametrize("operation", ["outcome", "report", "presence", "absence"])
@pytest.mark.parametrize("restored", [False, True])
def test_substituted_intent_cannot_resolve_original_reservation(changes, operation, restored):
    original = _intent()
    ledger = IdempotencyLedger()
    ledger.begin(original)
    if operation != "outcome":
        ledger.mark_transport_failure(original.order_id)
    if restored:
        ledger = _round_trip(ledger)
    before = ledger.records()
    with pytest.raises(ValueError, match="original reservation"):
        _operate(ExecutionLifecycleCoordinator(ledger), replace(original, **changes), operation)
    assert ledger.records() == before
    assert not validate_restart(snapshot_unresolved(ledger))[0]
    with pytest.raises(ValueError, match="cannot be resubmitted"):
        ledger.begin(original)


@pytest.mark.parametrize("operation", ["outcome", "report", "presence", "absence"])
def test_legacy_record_cannot_be_bound_using_later_supplied_intent(operation):
    state = SubmissionState.IN_FLIGHT if operation == "outcome" else SubmissionState.UNKNOWN
    record = SubmissionRecord(_intent().order_id, state, 2)
    ledger = _round_trip(IdempotencyLedger.restore((record,)))
    before = ledger.records()
    with pytest.raises(ValueError, match="original intent binding unavailable"):
        _operate(ExecutionLifecycleCoordinator(ledger), _intent(), operation)
    assert ledger.records() == before
    assert not validate_restart(snapshot_unresolved(ledger))[0]


@pytest.mark.parametrize("operation", ["outcome", "report", "presence", "absence"])
def test_matching_original_intent_remains_resolvable_after_restart(operation):
    original = _intent()
    ledger = IdempotencyLedger()
    ledger.begin(original)
    if operation != "outcome":
        ledger.mark_transport_failure(original.order_id)
    ledger = _round_trip(ledger)
    fingerprint = ledger.get(original.order_id).intent_fingerprint
    result = _operate(ExecutionLifecycleCoordinator(ledger), original, operation)
    if operation == "report":
        assert result.matched
    else:
        assert result.safe is (operation != "absence")
    assert ledger.get(original.order_id).state is (
        SubmissionState.REJECTED if operation == "absence" else SubmissionState.ACCEPTED)
    assert ledger.get(original.order_id).attempts == 1
    assert ledger.get(original.order_id).intent_fingerprint == fingerprint
    assert _round_trip(ledger).get_for_intent(original) == ledger.get(original.order_id)
    assert validate_restart(snapshot_unresolved(ledger))[0]
    with pytest.raises(ValueError):
        ledger.begin(original)


def test_mutating_original_object_cannot_change_reserved_economics():
    original = _intent()
    ledger = IdempotencyLedger()
    ledger.begin(original)
    ledger.mark_transport_failure(original.order_id)
    before = ledger.records()
    object.__setattr__(original, "volume", .04)
    with pytest.raises(ValueError, match="original reservation"):
        _operate(ExecutionLifecycleCoordinator(ledger), original, "report")
    assert ledger.records() == before


def test_legacy_json_and_checksum_remain_byte_compatible():
    payload = [{"order_id": "original-A", "state": "unknown", "attempts": 2}]
    checksum = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    raw = json.dumps({"records": payload, "checksum": checksum}, sort_keys=True, separators=(",", ":"))
    assert serialize_snapshot(deserialize_snapshot(raw)) == raw
    assert serialize_snapshot(build_snapshot((SubmissionRecord("original-A", SubmissionState.UNKNOWN, 2),))) == raw


@pytest.mark.parametrize("fingerprint", ["", "a" * 63, "A" * 64, "z" * 64, True, 1, {}])
@pytest.mark.parametrize("boundary", ["ledger", "restore", "journal"])
def test_damaged_fingerprint_is_refused_even_with_matching_journal_checksum(fingerprint, boundary):
    record = SubmissionRecord("original-A", SubmissionState.UNKNOWN, 1, fingerprint)
    with pytest.raises(ValueError, match="fingerprint"):
        if boundary == "ledger":
            ledger = IdempotencyLedger()
            ledger._records[record.order_id] = record
            ledger.get(record.order_id)
        elif boundary == "restore":
            IdempotencyLedger.restore((record,))
        else:
            payload = [{"order_id": record.order_id, "state": "unknown", "attempts": 1,
                        "intent_fingerprint": fingerprint}]
            checksum = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            deserialize_snapshot(json.dumps({"records": payload, "checksum": checksum}))


@pytest.mark.parametrize("change", ["replace", "remove", "null"])
def test_binding_cannot_be_changed_or_dropped_under_original_checksum(change):
    ledger = IdempotencyLedger()
    ledger.begin(_intent())
    data = json.loads(serialize_snapshot(build_snapshot(ledger.records())))
    if change == "remove":
        del data["records"][0]["intent_fingerprint"]
    else:
        data["records"][0]["intent_fingerprint"] = "0" * 64 if change == "replace" else None
    with pytest.raises(ValueError):
        deserialize_snapshot(json.dumps(data))


@pytest.mark.parametrize("field", ["volume", "expected_price"])
@pytest.mark.parametrize("value", [True, "1", 0, float("nan"), float("inf"), 10 ** 1000])
def test_unbindable_economics_fail_before_creating_reservation(field, value):
    ledger = IdempotencyLedger()
    with pytest.raises(ValueError, match="economics"):
        ledger.begin(replace(_intent(), **{field: value}))
    assert ledger.records() == ()


@pytest.mark.parametrize("changes", [{"symbol": " "}, {"direction": "BUY"}])
def test_unbindable_symbol_or_direction_fail_before_reservation(changes):
    ledger = IdempotencyLedger()
    with pytest.raises(ValueError):
        ledger.begin(replace(_intent(), **changes))
    assert ledger.records() == ()


def test_equivalent_numeric_types_and_normalized_identity_preserve_binding():
    ledger = IdempotencyLedger()
    original = replace(_intent(), order_id=" original-A ", volume=1)
    record = ledger.begin(original)
    equivalent = replace(original, order_id="original-A", volume=1.0, expected_price=2500.0)
    assert _round_trip(ledger).get_for_intent(equivalent) == record


def test_distinct_large_integer_prices_cannot_collapse_to_same_binding():
    ledger = IdempotencyLedger()
    original = replace(_intent(), expected_price=2 ** 53)
    ledger.begin(original)
    with pytest.raises(ValueError, match="original reservation"):
        ledger.get_for_intent(replace(original, expected_price=2 ** 53 + 1))


def test_report_tolerance_does_not_require_a_change_to_original_intent():
    ledger = IdempotencyLedger()
    original = _intent()
    ledger.begin(original)
    ledger.mark_transport_failure(original.order_id)
    ledger = _round_trip(ledger)
    report = ExecutionReport(original.order_id, original.symbol, original.direction, .0301, 2500.5)
    assert ExecutionLifecycleCoordinator(ledger).reconcile(
        original, report, price_tolerance=.5, volume_tolerance=.0001).matched
    assert ledger.get_for_intent(original).state is SubmissionState.ACCEPTED
