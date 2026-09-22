import pytest
from dataclasses import replace

from core.enums import Direction
from execution.reconciliation import ExecutionReport, OrderIntent, reconcile_execution


def _intent() -> OrderIntent:
    return OrderIntent("sig-001", "XAUUSD", Direction.BUY, 0.03, 2500.0)


def test_reconciliation_accepts_exact_match():
    report = ExecutionReport("sig-001", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    result = reconcile_execution(_intent(), report)
    assert result.matched
    assert result.reasons == ()


def test_reconciliation_blocks_identity_mismatch():
    report = ExecutionReport("sig-002", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    result = reconcile_execution(_intent(), report)
    assert not result.matched
    assert "order identity mismatch" in result.reasons


def test_reconciliation_allows_configured_price_tolerance():
    report = ExecutionReport("sig-001", "XAUUSD", Direction.BUY, 0.03, 2500.05)
    result = reconcile_execution(_intent(), report, price_tolerance=0.05)
    assert result.matched


def test_reconciliation_allows_boundary_volume_tolerance_despite_float_noise():
    report = ExecutionReport("sig-001", "XAUUSD", Direction.BUY, 0.030000000000000002, 2500.0)
    result = reconcile_execution(_intent(), report, volume_tolerance=0.0)
    assert result.matched


def test_reconciliation_blocks_volume_and_direction_mismatch():
    report = ExecutionReport("sig-001", "XAUUSD", Direction.SELL, 0.04, 2500.0)
    result = reconcile_execution(_intent(), report)
    assert not result.matched
    assert "direction mismatch" in result.reasons
    assert "volume mismatch" in result.reasons


def test_reconciliation_rejects_invalid_tolerances():
    report = ExecutionReport("sig-001", "XAUUSD", Direction.BUY, 0.03, 2500.0)
    with pytest.raises(ValueError):
        reconcile_execution(_intent(), report, price_tolerance=-1)


def test_reconciliation_rejects_boolean_and_non_numeric_tolerances():
    intent = OrderIntent("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    report = ExecutionReport("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    for value in (True, "0.1", None):
        with pytest.raises(ValueError):
            reconcile_execution(intent, report, price_tolerance=value)
        with pytest.raises(ValueError):
            reconcile_execution(intent, report, volume_tolerance=value)


def test_reconciliation_fails_closed_on_malformed_identity_fields():
    valid_intent = OrderIntent("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    valid_report = ExecutionReport("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    for malformed in ("", "   ", None, 7):
        assert not reconcile_execution(
            replace(valid_intent, order_id=malformed), valid_report
        ).matched
        assert not reconcile_execution(
            valid_intent, replace(valid_report, order_id=malformed)
        ).matched
        assert not reconcile_execution(
            replace(valid_intent, symbol=malformed), valid_report
        ).matched
        assert not reconcile_execution(
            valid_intent, replace(valid_report, symbol=malformed)
        ).matched


@pytest.mark.parametrize("bad", [True, "0.1", None, float("nan"), float("inf"), 10**10000])
def test_reconciliation_fails_closed_on_malformed_volume(bad):
    intent = OrderIntent("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    report = ExecutionReport("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    assert not reconcile_execution(replace(intent, volume=bad), report).matched
    assert not reconcile_execution(intent, replace(report, volume=bad)).matched


@pytest.mark.parametrize("bad", [True, "2500", None, float("nan"), float("inf"), 10**10000])
def test_reconciliation_fails_closed_on_malformed_prices(bad):
    intent = OrderIntent("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    report = ExecutionReport("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    assert not reconcile_execution(replace(intent, expected_price=bad), report).matched
    assert not reconcile_execution(intent, replace(report, fill_price=bad)).matched


def test_reconciliation_fails_closed_on_malformed_direction():
    intent = OrderIntent("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    report = ExecutionReport("o-1", "XAUUSD", Direction.BUY, 0.1, 2500.0)
    for bad in ("BUY", None, 1):
        result = reconcile_execution(replace(intent, direction=bad), report)
        assert not result.matched
        assert "invalid direction" in result.reasons
