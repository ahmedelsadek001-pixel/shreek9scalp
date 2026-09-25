from datetime import datetime, timezone

import pytest

from core.enums import Direction
from core.paper_trade_pipeline import admit_and_submit_paper
from core.setup_quality import SetupQualityInput
from paper_trading.engine import PaperTradingEngine
from research.xauusd_source_manifest import XAUUSDSourceManifest
from risk.news_firewall import NewsFirewallPolicy


def _bars():
    return [
        {"timestamp": datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc), "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0}
        for i in range(3)
    ]


def _setup():
    return SetupQualityInput(
        htf_structure=True, liquidity_sweep=True, fvg=True, order_block=True,
        m15_confirmation=True, m5_confirmation=True, m3_confirmation=True,
        rr_valid=True, session_valid=True,
    )


def _call(engine, setup=None, entry=100.0, sl=99.0, volume=1.0, direction=Direction.BUY, timestamp=None):
    return admit_and_submit_paper(
        engine, _bars(), setup or _setup(), timestamp=timestamp or datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc),
        symbol="XAUUSD", direction=direction, entry=entry, sl=sl, volume=volume,
        setup_min_score=70, news_events=[], currencies=[], news_policy=NewsFirewallPolicy(),
    )


def test_pipeline_admits_and_submits():
    engine = PaperTradingEngine(1000, 0.05)
    result = _call(engine)
    assert result.allowed
    assert result.stage == "paper_execution"
    assert engine.open_order is not None


def test_pipeline_blocks_before_execution_on_weak_setup():
    engine = PaperTradingEngine(1000, 0.05)
    result = _call(engine, SetupQualityInput(htf_structure=True))
    assert not result.allowed
    assert result.stage == "admission"
    assert engine.open_order is None


def test_pipeline_blocks_on_daily_risk_before_execution():
    engine = PaperTradingEngine(1000, 0.05)
    engine.ledger.record(datetime(2026, 9, 12, tzinfo=timezone.utc).date(), -49.5)
    result = _call(engine, entry=100.0, sl=99.0)
    assert not result.allowed
    assert result.stage == "risk"
    assert engine.open_order is None


@pytest.mark.parametrize(
    ("entry", "sl", "volume"),
    [
        (None, 99.0, 1.0),
        (100.0, "bad-stop", 1.0),
        (100.0, 99.0, None),
        (float("nan"), 99.0, 1.0),
        (100.0, float("inf"), 1.0),
        (100.0, 99.0, float("inf")),
        (0.0, 99.0, 1.0),
        (100.0, 99.0, -1.0),
        (100.0, 100.0, 1.0),
        (10**10000, 99.0, 1.0),
    ],
    ids=["missing-entry", "invalid-stop-text", "missing-volume", "nan-entry", "infinite-stop", "infinite-volume", "zero-entry", "negative-volume", "equal-prices", "oversized-entry"],
)
def test_pipeline_rejects_invalid_order_inputs_without_submission(entry, sl, volume):
    engine = PaperTradingEngine(1000, 0.05)
    result = _call(engine, entry=entry, sl=sl, volume=volume)
    assert not result.allowed
    assert result.stage == "order_validation"
    assert engine.open_order is None


@pytest.mark.parametrize(
    ("direction", "entry", "sl"),
    [
        (Direction.BUY, 100.0, 100.0),
        (Direction.BUY, 100.0, 101.0),
        (Direction.SELL, 100.0, 99.0),
        (Direction.RANGE, 100.0, 99.0),
        (Direction.UNKNOWN, 100.0, 99.0),
    ],
    ids=["buy-equal", "buy-stop-above", "sell-stop-below", "range-direction", "unknown-direction"],
)
def test_pipeline_rejects_invalid_direction_or_stop_orientation(direction, entry, sl):
    engine = PaperTradingEngine(1000, 0.05)
    result = _call(engine, direction=direction, entry=entry, sl=sl)
    assert not result.allowed
    assert result.stage == "order_validation"
    assert engine.open_order is None


def test_pipeline_accepts_sell_with_stop_above_entry():
    engine = PaperTradingEngine(1000, 0.05)
    result = _call(engine, direction=Direction.SELL, entry=100.0, sl=101.0)
    assert result.allowed
    assert engine.open_order is not None
    assert engine.open_order.direction is Direction.SELL


def test_pipeline_rejects_naive_timestamp_without_submission():
    engine = PaperTradingEngine(1000, 0.05)
    result = _call(engine, timestamp=datetime(2026, 9, 12, 10, 2))
    assert not result.allowed
    assert result.stage == "order_validation"
    assert engine.open_order is None


def test_pipeline_uses_contract_risk_before_paper_submission():
    manifest = XAUUSDSourceManifest(
        "research-broker", "research-server", "XAUUSD", 0,
        2, 0.01, 100.0, 0.01, 0.01, 19.0, 7.0, 1.5,
    )
    engine = PaperTradingEngine.from_xauusd_manifest(
        manifest, starting_equity=1000, max_daily_loss_pct=0.05,
    )
    result = _call(engine, entry=100, sl=99, volume=1.0)
    assert not result.allowed and result.stage == "risk"
    assert engine.open_order is None
