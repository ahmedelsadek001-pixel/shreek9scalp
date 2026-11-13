import hashlib
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core.backtest_engine import BacktestTrade
from core.enums import Direction
from research.evidence_export import _build_execution_cost_evidence
from research.research_run_artifact import _validate_execution_cost_evidence


def _trades():
    start = datetime(2026, 1, 1)
    return (
        BacktestTrade(
            signal_time=start,
            entry_time=start + timedelta(minutes=5),
            exit_time=start + timedelta(minutes=10),
            direction=Direction.BUY,
            entry=100.0,
            exit=110.0,
            volume=1.0,
            gross_pnl=10.0,
            costs=0.5,
            net_pnl=9.5,
            exit_reason="TP",
            spread_cost=0.2,
            slippage_cost=0.1,
            commission_cost=0.2,
        ),
        BacktestTrade(
            signal_time=start + timedelta(minutes=15),
            entry_time=start + timedelta(minutes=20),
            exit_time=start + timedelta(minutes=25),
            direction=Direction.SELL,
            entry=110.0,
            exit=112.0,
            volume=1.0,
            gross_pnl=-2.0,
            costs=0.5,
            net_pnl=-2.5,
            exit_reason="SL",
            spread_cost=0.2,
            slippage_cost=0.1,
            commission_cost=0.2,
        ),
    )


def _payload():
    trades = _trades()
    wfo = SimpleNamespace(oos_results=(SimpleNamespace(trades=trades),))
    ledger = _build_execution_cost_evidence(wfo, 1.5, 2.0)
    return {
        "schema_version": "3",
        "evidence": {
            "oos_trade_count": 2,
            "oos_net_pnl": 7.0,
            "oos_expectancy": 3.5,
        },
        "wfo_evidence": {"windows": [{}]},
        "execution_cost_evidence": ledger,
    }


def _refresh_ledger_digest(payload):
    rows = payload["execution_cost_evidence"]["rows"]
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False)
    payload["execution_cost_evidence"]["ledger_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def test_oos_cost_ledger_preserves_trade_components_and_additive_stress():
    payload = _payload()
    ledger = payload["execution_cost_evidence"]
    assert ledger["trade_count"] == 2
    assert ledger["stress"]["totals"]["baseline_net_pnl"] == pytest.approx(7.0)
    assert ledger["stress"]["totals"]["cost_stressed_net_pnl"] == pytest.approx(6.6)
    assert ledger["stress"]["commission_unchanged"] is True
    _validate_execution_cost_evidence(payload)


def test_oos_cost_ledger_rejects_component_tampering_even_after_ledger_rehash():
    payload = _payload()
    payload["execution_cost_evidence"]["rows"][0]["spread_cost"] += 1.0
    _refresh_ledger_digest(payload)
    with pytest.raises(ValueError, match="total does not reconcile"):
        _validate_execution_cost_evidence(payload)


def test_oos_cost_ledger_rejects_net_pnl_tampering_even_after_ledger_rehash():
    payload = _payload()
    payload["execution_cost_evidence"]["rows"][0]["net_pnl"] += 1.0
    _refresh_ledger_digest(payload)
    with pytest.raises(ValueError, match="net P&L does not reconcile"):
        _validate_execution_cost_evidence(payload)


def test_oos_cost_ledger_rejects_digest_mismatch():
    payload = _payload()
    payload["execution_cost_evidence"]["ledger_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        _validate_execution_cost_evidence(payload)


def test_wfo_export_cannot_omit_execution_cost_ledger():
    payload = _payload()
    del payload["execution_cost_evidence"]
    with pytest.raises(ValueError, match="requires an execution-cost ledger"):
        _validate_execution_cost_evidence(payload)
