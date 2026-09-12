from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.models import TradeSignal
from core.signal_pipeline import admit_signal
from risk.trade_gates import GateResult


def valid_signal(direction=Direction.BUY):
    return TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.COMBINED,
        frame=Timeframe.M5,
        direction=direction,
        entry_price=100.0,
        sl_price=99.0 if direction == Direction.BUY else 101.0,
    )


def test_admission_requires_valid_signal():
    s = valid_signal()
    s.status = SignalStatus.WAIT
    assert not admit_signal(s, []).allowed


def test_admission_rejects_non_executable_direction():
    s = valid_signal(Direction.RANGE)
    assert not admit_signal(s, []).allowed


def test_admission_rejects_invalid_stop_side():
    s = valid_signal(Direction.BUY)
    s.sl_price = 101.0
    assert not admit_signal(s, []).allowed


def test_admission_stops_on_first_failed_gate():
    calls = []

    def first():
        calls.append("first")
        return GateResult(False, "blocked")

    def second():
        calls.append("second")
        return GateResult(True, "ok")

    result = admit_signal(valid_signal(), [("first", first), ("second", second)])
    assert not result.allowed
    assert result.failed_gate == "first"
    assert calls == ["first"]


def test_admission_allows_signal_when_all_gates_pass():
    result = admit_signal(valid_signal(), [("spread", lambda: GateResult(True, "ok"))])
    assert result.allowed
