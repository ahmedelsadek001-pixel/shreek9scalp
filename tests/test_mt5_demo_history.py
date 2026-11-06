from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
import sqlite3
from types import SimpleNamespace
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


@pytest.mark.parametrize("field,value", [
    ("order", 9003), ("type", 1), ("volume", .02), ("price", 4000.2),
    ("profit", 5), ("commission", -.20), ("swap", -.30), ("fee", -.01),
    ("symbol", "OTHER.s"), ("magic", 0), ("time_msc", 1),
])
def test_opening_metadata_must_agree_between_order_and_position_queries(tmp_path, field, value):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000) - 2000
    opened = Deal(456, 9001, 771, 0, 0, .01, 4000.1, 0, -.10, 0, 0, timestamp)
    inconsistent = replace(opened, **{field: timestamp + value if field == "time_msc" else value})
    closed = Deal(457, 9002, 771, 1, 1, .01, 4002, 1.90, -.10, 0, 0,
                  timestamp + 1000, magic=0)
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (opened,) if ticket is not None else (inconsistent, closed))
    sends_before, stops_before = len(api.sends), api.stops
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert report.reason == "broker position opening history contradicts DEMO ledger"
    assert len(api.sends) == sends_before
    assert api.stops == stops_before + 1


@pytest.mark.parametrize("history_offset", [0, 10800])
def test_consistent_split_opening_copies_can_be_reordered_between_queries(tmp_path, history_offset):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_300
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    assert submit_demo_order(api, config, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000) - 2000 + history_offset * 1000
    first = Deal(456, 9001, 771, 0, 0, .004, 4000.1, 0, -.04, 0, 0, timestamp)
    second = Deal(458, 9001, 771, 0, 0, .006, 4000.1, 0, -.06, 0, 0, timestamp + 1)
    closed = Deal(459, 9002, 771, 1, 1, .01, 4002, 1.90, -.10, 0, 0,
                  timestamp + 1000, magic=0)
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (first, second) if ticket is not None else (closed, replace(second), replace(first)))
    sends_before = len(api.sends)
    report = inspect_demo_history(api, config, ledger)
    assert report.verified_demo
    item = report.attempts[0]
    assert item["status"] == "closed_observed"
    assert item["observed_broker_deal_utc_offset_seconds"] == history_offset
    assert item["realized_net_usd"] == pytest.approx(1.70)
    assert len(api.sends) == sends_before


def _history_fixture_for_side(tmp_path, side):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    order = ORDER if side == "BUY" else replace(ORDER, side="SELL", stop_loss=4002, take_profit=3998)

    def check(request):
        assert request["type"] == (api.ORDER_TYPE_BUY if side == "BUY" else api.ORDER_TYPE_SELL)
        assert request["sl"] == order.stop_loss and request["tp"] == order.take_profit
        return SimpleNamespace(retcode=0)

    api.order_check = check
    assert submit_demo_order(api, CONFIG, order, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000) - 2000
    opening_type = api.DEAL_TYPE_BUY if side == "BUY" else api.DEAL_TYPE_SELL
    closing_type = api.DEAL_TYPE_SELL if side == "BUY" else api.DEAL_TYPE_BUY
    opened = Deal(456, 9001, 771, 0, opening_type, .01, 4000.1, 0, -.10, 0, 0, timestamp)
    closed = Deal(457, 9002, 771, 1, closing_type, .01, 4002 if side == "BUY" else 3998.2,
                  1.90, -.10, 0, 0, timestamp + 1000, magic=0)
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    return api, ledger, opened, closed


def _copy_history_attempt(ledger, broker_order_id, broker_deal_id):
    with sqlite3.connect(ledger) as db:
        db.execute(
            "INSERT INTO attempts SELECT account_hash, ?, status, ?, ?, broker_price, "
            "symbol, side, volume, stop_loss, take_profit, reserved_at, ?, "
            "server_utc_offset_seconds FROM attempts",
            ("second-test-intent", broker_order_id, broker_deal_id, "strategy_experiment"))


def _split_history_fixture(tmp_path, side, history_offset):
    api, ledger, opened, closed = _history_fixture_for_side(tmp_path, side)
    config = replace(CONFIG, server_utc_offset_seconds=history_offset)
    with sqlite3.connect(ledger) as db:
        db.execute("UPDATE attempts SET server_utc_offset_seconds=?", (history_offset,))
    opened = replace(opened, time_msc=opened.time_msc + history_offset * 1000)
    closed = replace(closed, time_msc=closed.time_msc + history_offset * 1000)
    return api, ledger, config, opened, closed


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("history_offset", [0, 10800])
@pytest.mark.parametrize("closed_volume", [.006, .01], ids=["partial", "full"])
def test_close_cannot_consume_a_later_opening_fill(tmp_path, side, history_offset, closed_volume):
    api, ledger, config, opened, closed = _split_history_fixture(tmp_path, side, history_offset)
    first = replace(opened, volume=.004, commission=-.04)
    second = replace(opened, ticket=458, volume=.006, commission=-.06,
                     time_msc=opened.time_msc + 1500)
    closed = replace(closed, volume=closed_volume)
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (first, second) if ticket is not None else (second, closed, first))
    before = ledger.read_bytes()
    sends_before, stops_before = len(api.sends), api.stops
    report = inspect_demo_history(api, config, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert report.reason == "broker closing chronology contradicts DEMO ledger"
    assert len(api.sends) == sends_before
    assert api.stops == stops_before + 1
    assert ledger.read_bytes() == before


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("history_offset", [0, 10800])
@pytest.mark.parametrize("shape", ["interleaved_partial", "interleaved_full", "same_millisecond"])
def test_valid_split_fill_chronology_preserves_observations(tmp_path, side, history_offset, shape):
    api, ledger, config, opened, closed = _split_history_fixture(tmp_path, side, history_offset)
    first = replace(opened, volume=.004, commission=-.04)
    second = replace(opened, ticket=458, volume=.006, commission=-.06,
                     time_msc=opened.time_msc + 1000)
    if shape == "same_millisecond":
        related = (first, closed, second)
    else:
        early_close = replace(closed, volume=.003,
                              profit=.76, commission=-.04, time_msc=opened.time_msc + 500)
        related = (first, early_close, second)
        if shape == "interleaved_full":
            related += (replace(closed, ticket=459, order=9003, volume=.007, profit=1.14,
                                commission=-.06, time_msc=opened.time_msc + 1500),)
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (second, first) if ticket is not None else tuple(reversed(related)))
    before = ledger.read_bytes()
    sends_before, stops_before = len(api.sends), api.stops
    report = inspect_demo_history(api, config, ledger)
    assert report.verified_demo
    assert len(report.attempts) == 1
    item = report.attempts[0]
    assert item["observed_broker_deal_utc_offset_seconds"] == history_offset
    if shape == "interleaved_partial":
        assert item["status"] == "open_or_partial"
        assert "realized_net_usd" not in item
    else:
        assert item["status"] == "closed_observed"
        assert item["realized_net_usd"] == pytest.approx(1.70)
    assert len(api.sends) == sends_before
    assert api.stops == stops_before + 1
    assert ledger.read_bytes() == before


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("deal_acknowledged", [False, True])
def test_duplicate_ledger_order_binding_cannot_repeat_a_broker_result(
        tmp_path, side, deal_acknowledged):
    api, ledger, opened, closed = _history_fixture_for_side(tmp_path, side)
    _copy_history_attempt(ledger, opened.order, opened.ticket if deal_acknowledged else None)
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (opened,) if ticket is not None else (opened, closed))
    before = ledger.read_bytes()
    sends_before, stops_before = len(api.sends), api.stops
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert report.reason == "duplicate broker order binding in DEMO ledger"
    assert len(api.sends) == sends_before
    assert api.stops == stops_before + 1
    assert ledger.read_bytes() == before


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("fully_closed", [False, True])
def test_distinct_ledger_order_bindings_preserve_independent_results(tmp_path, side, fully_closed):
    api, ledger, opened, closed = _history_fixture_for_side(tmp_path, side)
    second_opening = replace(opened, ticket=458, order=9003, position_id=772)
    second_close = replace(closed, ticket=459, order=9004, position_id=772)
    _copy_history_attempt(ledger, second_opening.order, second_opening.ticket)
    histories = {opened.order: (opened, closed), second_opening.order: (second_opening, second_close)}

    def history(*, ticket=None, position=None):
        if ticket is not None:
            return (histories[ticket][0],)
        deals = histories[opened.order if position == opened.position_id else second_opening.order]
        return deals if fully_closed else deals[:1]

    api.history_deals_get = history
    before = ledger.read_bytes()
    sends_before = len(api.sends)
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo
    assert len(report.attempts) == 2
    assert {item["broker_order_id"] for item in report.attempts} == {opened.order, second_opening.order}
    for item in report.attempts:
        assert item["status"] == ("closed_observed" if fully_closed else "open_or_partial")
        if fully_closed:
            assert item["realized_net_usd"] == pytest.approx(1.70)
        else:
            assert "realized_net_usd" not in item
    assert len(api.sends) == sends_before
    assert ledger.read_bytes() == before


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("collision", ["opening", "closing", "cross_entry"])
def test_deal_ticket_cannot_be_reused_by_independent_ledger_positions(tmp_path, side, collision):
    api, ledger, opened, closed = _history_fixture_for_side(tmp_path, side)
    second_opening = replace(opened, ticket=458, order=9003, position_id=772)
    second_close = replace(closed, ticket=459, order=9004, position_id=772)
    if collision == "opening":
        second_opening = replace(second_opening, ticket=opened.ticket)
    else:
        second_close = replace(second_close, ticket=closed.ticket if collision == "closing"
                               else opened.ticket)
    _copy_history_attempt(ledger, second_opening.order, second_opening.ticket)
    histories = {opened.order: (opened, closed), second_opening.order: (second_opening, second_close)}

    def history(*, ticket=None, position=None):
        if ticket is not None:
            return (histories[ticket][0],)
        return tuple(reversed(histories[opened.order if position == opened.position_id
                                      else second_opening.order]))

    api.history_deals_get = history
    before = ledger.read_bytes()
    sends_before, stops_before = len(api.sends), api.stops
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert report.reason == "broker deal ticket reused across DEMO ledger attempts"
    assert len(api.sends) == sends_before
    assert api.stops == stops_before + 1
    assert ledger.read_bytes() == before


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("entry", [
    pytest.param(2, id="reversal"),
    pytest.param(3, id="close_by"),
    pytest.param(99, id="unknown"),
])
@pytest.mark.parametrize("ordinary_close", [False, True])
def test_unsupported_position_transition_blocks_the_entire_history_report(
        tmp_path, side, entry, ordinary_close):
    api, ledger, opened, closed = _history_fixture_for_side(tmp_path, side)
    transition = replace(closed, ticket=458, order=9003, entry=entry, profit=7.0,
                         time_msc=closed.time_msc + 1)
    related = (opened, closed, transition) if ordinary_close else (opened, transition)
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (opened,) if ticket is not None else related)
    sends_before, stops_before = len(api.sends), api.stops
    ledger_before = ledger.read_bytes()
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert report.reason == "unsupported broker position transition; reconcile broker history"
    assert len(api.sends) == sends_before
    assert api.stops == stops_before + 1
    assert ledger.read_bytes() == ledger_before


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("fully_closed", [False, True])
def test_ordinary_position_transitions_preserve_partial_and_full_reports(
        tmp_path, side, fully_closed):
    api, ledger, opened, closed = _history_fixture_for_side(tmp_path, side)
    if not fully_closed:
        closed = replace(closed, volume=.004, profit=.76, commission=-.04)
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (opened,) if ticket is not None else (opened, closed))
    sends_before = len(api.sends)
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo
    item = report.attempts[0]
    assert item["status"] == ("closed_observed" if fully_closed else "open_or_partial")
    assert [deal["entry"] for deal in item["broker_deals"]] == [0, 1]
    if fully_closed:
        assert item["realized_net_usd"] == pytest.approx(1.70)
    else:
        assert "realized_net_usd" not in item
    assert item["manual_intervention"] is True
    assert len(api.sends) == sends_before


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("closing_kind", ["same_side", "other_type", "opposite"])
def test_closing_deal_direction_must_be_opposite_to_bound_opening(tmp_path, side, closing_kind):
    api, ledger, opened, closed = _history_fixture_for_side(tmp_path, side)
    if closing_kind == "same_side":
        closed = replace(closed, type=opened.type)
    elif closing_kind == "other_type":
        closed = replace(closed, type=99)
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (opened,) if ticket is not None else (opened, closed))
    sends_before, stops_before = len(api.sends), api.stops
    report = inspect_demo_history(api, CONFIG, ledger)
    if closing_kind == "opposite":
        assert report.verified_demo
        assert report.attempts[0]["status"] == "closed_observed"
        assert report.attempts[0]["realized_net_usd"] == pytest.approx(1.70)
        assert report.attempts[0]["manual_intervention"] is True
    else:
        assert report.verified_demo is False
        assert report.attempts == ()
        assert report.reason == "broker closing direction contradicts DEMO ledger"
    assert len(api.sends) == sends_before
    assert api.stops == stops_before + 1


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("constant", ["missing", "aliased"])
def test_ambiguous_closing_type_constant_cannot_validate_history(tmp_path, side, constant):
    api, ledger, opened, closed = _history_fixture_for_side(tmp_path, side)
    name = "DEAL_TYPE_SELL" if side == "BUY" else "DEAL_TYPE_BUY"
    if constant == "missing":
        setattr(api, name, None)
    else:
        setattr(api, name, opened.type)
        closed = replace(closed, type=opened.type)
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (opened,) if ticket is not None else (opened, closed))
    sends_before = len(api.sends)
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert report.reason == "broker closing direction contradicts DEMO ledger"
    assert len(api.sends) == sends_before


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


@pytest.mark.parametrize("duplicate", ["same_close", "conflicting_close", "opening_collision"])
def test_duplicate_position_deal_tickets_cannot_report_a_full_close(tmp_path, duplicate):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000) - 2000
    opened = Deal(456, 9001, 771, 0, 0, .01, 4000.1, 0, -.10, 0, 0, timestamp)
    closed = Deal(457, 9002, 771, 1, 1, .005, 4002, .95, -.05, 0, 0,
                  timestamp + 1000, magic=0)
    if duplicate == "same_close":
        related = (opened, closed, closed)
    elif duplicate == "conflicting_close":
        related = (opened, replace(closed, volume=.004), replace(closed, volume=.006))
    else:
        related = (opened, replace(closed, ticket=opened.ticket, volume=.01))
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (opened,) if ticket is not None else related)
    sends_before, stops_before = len(api.sends), api.stops
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo is False
    assert report.attempts == ()
    assert report.reason == "duplicate broker deal ticket in position history"
    assert len(api.sends) == sends_before
    assert api.stops == stops_before + 1


@pytest.mark.parametrize("fully_closed", [False, True])
def test_unique_split_closes_preserve_partial_or_full_observations(tmp_path, fully_closed):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    assert submit_demo_order(api, CONFIG, ORDER, ledger).accepted
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000) - 2000
    opened = Deal(456, 9001, 771, 0, 0, .01, 4000.1, 0, -.10, 0, 0, timestamp)
    first = Deal(457, 9002, 771, 1, 1, .004, 4002, .76, -.04, 0, 0,
                 timestamp + 1000, magic=0)
    second = Deal(458, 9002, 771, 1, 1, .006 if fully_closed else .002,
                  4002, 1.14 if fully_closed else .38, -.06 if fully_closed else -.02,
                  0, 0, timestamp + 1001, magic=0)
    api.DEAL_ENTRY_IN = 0
    api.DEAL_ENTRY_OUT = 1
    api.history_deals_get = lambda *, ticket=None, position=None: (
        (opened,) if ticket is not None else (second, opened, first))
    sends_before = len(api.sends)
    report = inspect_demo_history(api, CONFIG, ledger)
    assert report.verified_demo
    item = report.attempts[0]
    assert [deal["ticket"] for deal in item["broker_deals"]] == [456, 457, 458]
    assert item["manual_intervention"] is True
    if fully_closed:
        assert item["status"] == "closed_observed"
        assert item["realized_net_usd"] == pytest.approx(1.70)
    else:
        assert item["status"] == "open_or_partial"
        assert "realized_net_usd" not in item
    assert len(api.sends) == sends_before


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
