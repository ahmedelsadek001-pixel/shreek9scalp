from datetime import datetime, timedelta, timezone

import pytest

from research.breakout_retest import ResearchBar
from research.xauusd_source_manifest import XAUUSDSourceManifest


def _manifest(**overrides):
    values = {
        "broker": "One World Markets Ltd",
        "server": "OWMarkets-Server",
        "symbol": "XAUUSD",
        "timezone_offset_minutes": 180,
        "digits": 2,
        "point_size": 0.01,
        "contract_size": 100.0,
        "minimum_volume": 0.01,
        "volume_step": 0.01,
        "observed_spread_points": 19.0,
        "round_turn_commission_per_lot": 7.0,
        "slippage_points": 1.5,
    }
    values.update(overrides)
    return XAUUSDSourceManifest(**values)


def test_manifest_converts_owmarkets_metadata_to_engine_units():
    manifest = _manifest()
    manifest.validate()
    assert manifest.timezone == timezone(timedelta(hours=3))
    assert manifest.spread_price == pytest.approx(0.19)
    assert manifest.slippage_price == pytest.approx(0.015)
    assert manifest.point_value == pytest.approx(100.0)
    assert manifest.commission_per_execution == pytest.approx(3.5)
    costs = manifest.to_cost_model()
    assert costs.slippage == pytest.approx(0.015)
    assert costs.point_value == pytest.approx(100.0)
    assert costs.commission_per_volume == pytest.approx(3.5)
    config = manifest.to_breakout_retest_config(pip_size=0.10)
    assert config.spread == pytest.approx(0.19)
    assert config.slippage == pytest.approx(0.015)
    assert config.point_value == pytest.approx(100.0)
    assert config.commission_per_volume == pytest.approx(3.5)


def test_manifest_rejects_inconsistent_price_precision_and_identity():
    with pytest.raises(ValueError, match="point_size does not match digits"):
        _manifest(point_size=0.1).validate()
    with pytest.raises(ValueError, match="symbol must be XAUUSD"):
        _manifest(symbol="EURUSD").validate()
    with pytest.raises(ValueError, match="timezone_offset_minutes"):
        _manifest(timezone_offset_minutes=15 * 60).validate()


def test_manifest_rejects_bars_from_a_different_server_offset():
    manifest = _manifest()
    matching = ResearchBar(
        datetime(2026, 9, 24, 13, 45, tzinfo=timezone(timedelta(hours=3))),
        4258.39, 4259.01, 4257.91, 4258.95, 156,
    )
    manifest.validate_bars_timezone((matching,))
    mismatched = ResearchBar(
        matching.timestamp.astimezone(timezone.utc), matching.open, matching.high,
        matching.low, matching.close, matching.volume,
    )
    with pytest.raises(ValueError, match="offset does not match"):
        manifest.validate_bars_timezone((mismatched,))
