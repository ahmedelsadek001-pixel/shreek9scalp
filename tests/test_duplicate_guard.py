from concurrent.futures import ThreadPoolExecutor

import pytest

from core.duplicate_guard import DuplicateSignalGuard, signal_fingerprint
from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.models import TradeSignal


def _signal(entry=100.0, stop=99.0):
    return TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.COMBINED,
        frame=Timeframe.M15,
        direction=Direction.BUY,
        entry_price=entry,
        sl_price=stop,
        confidence=0.9,
    )


def test_fingerprint_is_stable_and_symbol_case_insensitive():
    assert signal_fingerprint("xauusd", _signal()) == signal_fingerprint("XAUUSD", _signal())


@pytest.mark.parametrize("entry,stop", [(float("nan"), 99.0), (100.0, float("inf")), (float("-inf"), 99.0)])
def test_fingerprint_rejects_non_finite_prices(entry, stop):
    with pytest.raises(ValueError, match="signal prices must be finite"):
        signal_fingerprint("XAUUSD", _signal(entry, stop))


def test_guard_reserves_once_and_blocks_duplicate():
    guard = DuplicateSignalGuard()
    fingerprint = signal_fingerprint("XAUUSD", _signal())
    first = guard.reserve(fingerprint)
    second = guard.reserve(fingerprint)

    assert first.allowed
    assert not second.allowed
    assert second.reason == "duplicate signal identity"
    assert guard.size() == 1


def test_distinct_execution_levels_create_distinct_identity():
    first = signal_fingerprint("XAUUSD", _signal(100.0, 99.0))
    second = signal_fingerprint("XAUUSD", _signal(100.1, 99.0))
    assert first != second


def test_discard_allows_retry_after_rejected_submission():
    guard = DuplicateSignalGuard()
    fingerprint = signal_fingerprint("XAUUSD", _signal())
    guard.reserve(fingerprint)
    guard.discard(fingerprint)
    assert guard.reserve(fingerprint).allowed


def test_concurrent_reservation_is_atomic():
    guard = DuplicateSignalGuard()
    fingerprint = signal_fingerprint("XAUUSD", _signal())

    def reserve():
        return guard.reserve(fingerprint).allowed

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: reserve(), range(64)))

    assert sum(results) == 1
    assert guard.size() == 1
