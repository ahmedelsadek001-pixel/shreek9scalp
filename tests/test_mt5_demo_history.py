from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
import pytest

from execution.mt5_demo_history import inspect_demo_history
from execution.mt5_demo_transport import submit_demo_order
from test_mt5_demo_transport import CONFIG, ORDER, Account, FakeMT5


@dataclass
class Deal:
    ticket: int
    order: int
    position_id: int
    entry: int
    type: int
    volume: float
    price: float
    profit: float
    commission: float
    swap: float
    fee: float
    time_msc: int
    symbol: str = "XAUUSD.s"
    magic: int = 521000


def test_broker_history_observes_closed_demo_order_without_strategy_attribution(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    opened = Deal(456, 9001, 771, 0, 0, 0.01, 4000.1, 0.0, -0.10, 0.0, 0.0, timestamp)
    closed = Deal(457, 9002, 771, 1, 1, 0.01, 4002.0, 1.90, -0.10, 0.0, 0.0, timestamp + 10000,
                  magic=0)
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    api.history_deals_get = lambda *, ticket=None, position=None: (opened,) if ticket else (opened, closed)
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo and len(report.attempts) == 1
    item = report.attempts[0]
    assert item["status"] == "closed_observed"
    assert item["local_source_kind"] == "manual_sandbox"
    assert item["manual_intervention"] is True
    assert item["broker_deals"][1]["profit"] == 1.90
    assert item["realized_net_usd"] == pytest.approx(1.70)
    assert "strategy" in report.reason.lower() and "123456" not in str(report)


def test_real_account_or_missing_broker_history_refused(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    api.account = Account(trade_mode=2)
    assert not inspect_demo_history(api, CONFIG, ledger).verified_demo
    api.account = Account()
    api.history_deals_get = lambda **kwargs: None
    api.DEAL_ENTRY_IN = 0
    assert not inspect_demo_history(api, CONFIG, ledger).verified_demo


def test_mixed_account_ledger_never_reports_another_demo_as_ours(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    with sqlite3.connect(ledger) as db:
        db.execute("UPDATE attempts SET account_hash=?", ("0" * 64,))
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert "ledger identity malformed" in report.reason


@pytest.mark.parametrize("override", [{"ticket": 999}, {"type": 1}, {"volume": 0.02}])
def test_wrong_broker_fill_cannot_validate_ledger_order(tmp_path, override):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    values = dict(ticket=456, order=9001, position_id=771, entry=0, type=0,
                  volume=0.01, price=4000.1, profit=0.0, commission=0.0,
                  swap=0.0, fee=0.0, time_msc=timestamp)
    values.update(override)
    api.DEAL_ENTRY_IN = 0
    api.history_deals_get = lambda *, ticket=None, position=None: (Deal(**values),)
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()


def test_unknown_broker_submission_cannot_disappear_from_history_report(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    api.order_send = lambda request: None
    result = submit_demo_order(api, CONFIG, ORDER, ledger)
    assert result.sent and not result.accepted
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert "unresolved DEMO submission" in report.reason


@pytest.mark.parametrize("account_currency,symbol_currency", [("EUR", "USD"), ("USD", "EUR")])
def test_non_usd_demo_cannot_report_usd_profit(tmp_path, account_currency, symbol_currency):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    api.account.currency = account_currency
    api.symbol.currency_profit = symbol_currency
    assert not inspect_demo_history(api, CONFIG, ledger).verified_demo
