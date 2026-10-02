from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
import sqlite3
import pytest

from execution.mt5_demo_history import inspect_demo_history
from execution.mt5_demo_transport import submit_demo_order
from test_mt5_demo_transport import CONFIG, ORDER, Account, FakeMT5, Symbol


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
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000) - 2000
    opened = Deal(456, 9001, 771, 0, 0, 0.01, 4000.1, 0.0, -0.10, 0.0, 0.0, timestamp)
    closed = Deal(457, 9002, 771, 1, 1, 0.01, 4002.0, 1.90, -0.10, 0.0, 0.0, timestamp + 1000,
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


def test_fok_multiple_opening_deals_reconcile_full_volume(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000) - 2000
    first = Deal(456, 9001, 771, 0, 0, 0.004, 4000.1, 0, -0.04, 0, 0, timestamp)
    second = Deal(458, 9001, 771, 0, 0, 0.006, 4000.1, 0, -0.06, 0, 0, timestamp + 1)
    close = Deal(459, 9002, 771, 1, 1, 0.01, 4002, 1.9, -0.10, 0, 0, timestamp + 1000)
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (first, second) if ticket is not None else (first, second, close))
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo
    assert report.attempts[0]["status"] == "closed_observed"
    assert len(report.attempts[0]["broker_deals"]) == 3
    assert report.attempts[0]["realized_net_usd"] == pytest.approx(1.70)


@pytest.mark.parametrize("history_offset", [0, 10800])
def test_history_clock_is_checked_against_bound_intent_before_utc_reporting(tmp_path, history_offset):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_300
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    assert submit_demo_order(api, config, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000) - 1000
    opened = Deal(456, 9001, 771, 0, 0, .01, 4000.1, 0, 0, 0, 0,
                  timestamp + history_offset * 1000)
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    api.history_deals_get = lambda *, ticket=None, position=None: (opened,)
    report = inspect_demo_history(api, config, ledger)
    assert report.verified_demo
    item = report.attempts[0]
    assert item["local_server_utc_offset_seconds"] == 10800
    assert item["observed_broker_deal_utc_offset_seconds"] == history_offset
    assert datetime.fromisoformat(item["broker_deals"][0]["time_utc"]).timestamp() == pytest.approx(timestamp / 1000)


def test_unbound_history_clock_or_future_close_refuses_attribution(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    opened = Deal(456, 9001, 771, 0, 0, .01, 4000.1, 0, 0, 0, 0, timestamp + 3_600_000)
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    api.history_deals_get = lambda *, ticket=None, position=None: (opened,)
    assert "clock" in inspect_demo_history(api, CONFIG, ledger).reason
    opened.time_msc = timestamp
    future_close = Deal(457, 9002, 771, 1, 1, .01, 4001.0, 1.0, 0, 0, 0,
                        timestamp + 3_600_000)
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (opened,) if ticket is not None else (opened, future_close))
    assert "future fill" in inspect_demo_history(api, CONFIG, ledger).reason


def test_extra_or_duplicate_opening_deals_refuse_attribution(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    first = Deal(456, 9001, 771, 0, 0, 0.004, 4000.1, 0, 0, 0, 0, timestamp)
    second = Deal(458, 9001, 771, 0, 0, 0.006, 4000.1, 0, 0, 0, 0, timestamp + 1)
    foreign = Deal(460, 9003, 771, 0, 0, 0.01, 4000.2, 0, 0, 0, 0, timestamp + 2)
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (first, second) if ticket is not None else (first, second, foreign))
    assert not inspect_demo_history(api, CONFIG, ledger).verified_demo
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (first, first, second) if ticket is not None else (first, second))
    assert not inspect_demo_history(api, CONFIG, ledger).verified_demo


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


@pytest.mark.parametrize("failure", ["account", "unknown", "lookup", "empty", "observed"])
@pytest.mark.parametrize("error", [AttributeError, OSError, RuntimeError])
def test_history_shutdown_failure_overrides_early_refusal_and_success(tmp_path, failure, error):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    if failure == "account":
        api.account = Account(trade_mode=2)
    elif failure == "unknown":
        with sqlite3.connect(ledger) as db:
            db.execute("UPDATE attempts SET status='UNKNOWN'")
    elif failure == "lookup":
        api.history_deals_get = lambda **kwargs: None
    elif failure == "empty":
        with sqlite3.connect(ledger) as db:
            db.execute("DELETE FROM attempts")
    else:
        api.history_deals_get = lambda **kwargs: ()
    sends_before_read = len(api.sends)
    shutdown_calls = []

    def broken_shutdown():
        shutdown_calls.append(True)
        raise error("private terminal details")

    api.shutdown = broken_shutdown
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert report.reason == "DEMO history shutdown failed"
    assert shutdown_calls == [True]
    assert len(api.sends) == sends_before_read
    assert "private" not in str(report)
