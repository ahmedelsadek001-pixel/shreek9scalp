import json

import pytest

from journal.decision_journal import DecisionJournal
from paper_trading.engine import PaperOrder, PaperTradingEngine


def order(volume=0.5):
    return PaperOrder("XAUUSD", "LONG", 100.0, 99.0, 102.0, volume)


class Decision:
    def __init__(self, allowed):
        self.allowed = allowed


class Robustness:
    def __init__(self, passed):
        self.passed = passed


def test_rejected_order_never_opens():
    engine = PaperTradingEngine(1000)
    assert engine.submit(order(), admitted=False, robustness_passed=True) is False
    assert engine.open_order is None
    assert engine.equity == 1000


def test_robustness_failure_never_opens():
    engine = PaperTradingEngine(1000)
    assert engine.submit(order(), admitted=True, robustness_passed=False) is False
    assert engine.open_order is None
    assert engine.equity == 1000


def test_risk_budget_blocks_oversized_paper_order():
    engine = PaperTradingEngine(1000)
    assert engine.submit(order(volume=2.0), admitted=True, robustness_passed=True, max_risk_usd=1.0) is False
    assert engine.open_order is None


def test_risk_budget_allows_order_within_limit():
    engine = PaperTradingEngine(1000)
    assert engine.submit(order(volume=0.5), admitted=True, robustness_passed=True, max_risk_usd=1.0) is True


def test_admitted_and_robust_order_closes_and_updates_equity():
    engine = PaperTradingEngine(1000)
    assert engine.submit(order(), admitted=True, robustness_passed=True) is True
    fill = engine.close(102.0, "TP")
    assert fill.realized_pnl == pytest.approx(1.0)
    assert engine.equity == pytest.approx(1001.0)
    assert engine.open_order is None


def test_typed_gate_results_are_consumed_fail_closed():
    engine = PaperTradingEngine(1000)
    assert engine.submit_decision(order(), Decision(True), Robustness(False)) is False
    assert engine.submit_decision(order(), Decision(False), Robustness(True)) is False
    assert engine.submit_decision(order(), Decision(True), Robustness(True)) is True


def test_second_position_is_blocked_until_close():
    engine = PaperTradingEngine()
    engine.submit(order(), admitted=True, robustness_passed=True)
    with pytest.raises(RuntimeError):
        engine.submit(order(), admitted=True, robustness_passed=True)


def test_invalid_order_geometry_fails_closed():
    with pytest.raises(ValueError):
        PaperOrder("XAUUSD", "LONG", 100, 101, 102, 1).validate()
    with pytest.raises(ValueError):
        PaperOrder("XAUUSD", "SHORT", 100, 99, 98, 1).validate()


def test_journal_records_open_and_close(tmp_path):
    path = tmp_path / "paper.jsonl"
    journal = DecisionJournal(path)
    engine = PaperTradingEngine(1000, journal=journal)
    assert engine.submit(order(), admitted=True, robustness_passed=True)
    engine.close(101.0, "manual")

    records = journal.read()
    assert [record.decision for record in records] == ["PAPER_OPEN", "PAPER_CLOSE"]

    # JSONL is deliberately one JSON object per line; json.loads() must be
    # applied per non-empty line rather than json.load() over the whole file.
    raw_records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [record["decision"] for record in raw_records] == ["PAPER_OPEN", "PAPER_CLOSE"]
