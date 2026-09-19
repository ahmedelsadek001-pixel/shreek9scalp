from datetime import datetime, timezone

from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.models import TradeSignal
from core.setup_quality import SetupQualityInput
from core.trade_orchestrator import TradeOrchestrator
from paper_trading.engine import PaperTradingEngine
from risk.risk_budget import RiskBudget


TIMESTAMP = datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc)


def _bars():
    return [
        {
            "timestamp": datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc),
            "open": 99.0,
            "high": 101.0,
            "low": 98.0,
            "close": 100.0,
        }
        for i in range(3)
    ]


def _setup():
    return SetupQualityInput(
        htf_structure=True,
        liquidity_sweep=True,
        fvg=True,
        order_block=True,
        m15_confirmation=True,
        m5_confirmation=True,
        m3_confirmation=True,
        rr_valid=True,
        session_valid=True,
    )


def _signal(entry=100.0, stop=99.0):
    return TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.COMBINED,
        frame=Timeframe.M15,
        direction=Direction.BUY,
        entry_price=entry,
        sl_price=stop,
        confidence=0.9,
        aligned=True,
    )


def test_orchestrator_admits_sizes_and_submits():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))

    result = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(), timestamp=TIMESTAMP, symbol="XAUUSD", setup_min_score=70
    )

    assert result.allowed
    assert result.stage == "paper_execution"
    assert result.volume == 10.0
    assert result.fingerprint
    assert engine.open_order is not None


def test_orchestrator_blocks_duplicate_signal_identity():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))
    signal = _signal()

    first = orchestrator.evaluate_and_submit(
        signal, _bars(), _setup(), timestamp=TIMESTAMP, symbol="XAUUSD", setup_min_score=70
    )
    second = orchestrator.evaluate_and_submit(
        signal, _bars(), _setup(), timestamp=TIMESTAMP, symbol="XAUUSD", setup_min_score=70
    )

    assert first.allowed
    assert not second.allowed
    assert second.stage == "duplicate"
    assert second.fingerprint == first.fingerprint


def test_orchestrator_allows_identity_release_after_lifecycle():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))
    result = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(), timestamp=TIMESTAMP, symbol="XAUUSD", setup_min_score=70
    )
    engine.close(101.0, datetime(2026, 9, 12, 10, 5, tzinfo=timezone.utc), "TP")
    orchestrator.release_signal(result.fingerprint)

    retry = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(), timestamp=datetime(2026, 9, 12, 10, 6, tzinfo=timezone.utc),
        symbol="XAUUSD", setup_min_score=70,
    )
    assert retry.allowed


def test_orchestrator_blocks_invalid_signal_before_market_admission():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000))
    invalid = _signal()
    invalid.status = SignalStatus.WAIT

    result = orchestrator.evaluate_and_submit(
        invalid, _bars(), _setup(), timestamp=TIMESTAMP, symbol="XAUUSD", setup_min_score=70
    )

    assert not result.allowed
    assert result.stage == "signal"
    assert engine.open_order is None


def test_orchestrator_blocks_when_risk_budget_is_exceeded():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))

    result = orchestrator.evaluate_and_submit(
        _signal(entry=100.0, stop=90.0),
        _bars(),
        _setup(),
        timestamp=TIMESTAMP,
        symbol="XAUUSD",
        setup_min_score=70,
        volume=2.0,
    )

    assert not result.allowed
    assert result.stage == "risk"
    assert engine.open_order is None


def test_orchestrator_blocks_timezone_naive_timestamp():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000))

    result = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(), timestamp=datetime(2026, 9, 12, 10, 2),
        symbol="XAUUSD", setup_min_score=70
    )

    assert not result.allowed
    assert result.stage == "input"
    assert engine.open_order is None


def test_orchestrator_rejects_non_numeric_signal_prices_without_raising():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000))

    result = orchestrator.evaluate_and_submit(
        _signal(entry="not-a-price"), _bars(), _setup(), timestamp=TIMESTAMP,
        symbol="XAUUSD", setup_min_score=70,
    )

    assert not result.allowed
    assert result.stage == "signal"
    assert result.reason == "entry/stop price must be numeric"
    assert engine.open_order is None


def test_orchestrator_rejects_non_numeric_volume_without_raising():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000))

    result = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(), timestamp=TIMESTAMP,
        symbol="XAUUSD", setup_min_score=70, volume="invalid",
    )

    assert not result.allowed
    assert result.stage == "risk"
    assert result.reason == "volume must be numeric"
    assert engine.open_order is None


def test_orchestrator_rejects_non_finite_computed_volume(monkeypatch):
    engine = PaperTradingEngine(1000, 0.05)
    budget = RiskBudget(1000, risk_pct=0.01)
    monkeypatch.setattr(RiskBudget, "size_for_stop", lambda self, *args: float("inf"))
    orchestrator = TradeOrchestrator(engine, budget)

    result = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(), timestamp=TIMESTAMP,
        symbol="XAUUSD", setup_min_score=70,
    )

    assert not result.allowed
    assert result.stage == "risk"
    assert result.reason == "position volume must be positive and finite"
    assert engine.open_order is None


def test_orchestrator_rejects_boolean_risk_values_before_paper_submission():
    cases = (
        (_signal(entry=True), {}),
        (_signal(stop=True), {}),
        (_signal(), {"point_value": True}),
        (_signal(), {"volume": True}),
    )

    for signal, kwargs in cases:
        engine = PaperTradingEngine(1000, 0.05)
        orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))
        result = orchestrator.evaluate_and_submit(
            signal, _bars(), _setup(), timestamp=TIMESTAMP, symbol="XAUUSD",
            setup_min_score=70, **kwargs,
        )
        assert not result.allowed
        assert result.stage == "risk"
        assert engine.open_order is None
