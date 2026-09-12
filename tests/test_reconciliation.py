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
    try:
        reconcile_execution(_intent(), report, price_tolerance=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative tolerance must fail")
