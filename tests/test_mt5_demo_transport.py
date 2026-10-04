"""DEMO transport safety behaviour against a fake, unprivileged MT5 API."""
from dataclasses import dataclass
from datetime import datetime, timezone
from dataclasses import replace
import sqlite3
import pytest

from execution.mt5_demo_probe import DemoTerminalConfig
from execution.mt5_demo_transport import DemoOrder, submit_demo_order
from execution.mt5_demo_readiness import inspect_demo_readiness
from execution import mt5_demo_order_cli


@dataclass
class Account:
    login: int = 123456
    server: str = "Sandbox-Demo"
    trade_mode: int = 0
    currency: str = "USD"
    trade_allowed: bool = True
    trade_expert: bool = True
    equity: float = 1000.0


@dataclass
class Terminal:
    connected: bool = True
    trade_allowed: bool = True
    tradeapi_disabled: bool = False


@dataclass
class Symbol:
    visible: bool = True
    chart_mode: int = 0
    currency_profit: str = "USD"
    trade_mode: int = 4
    trade_contract_size: float = 100.0
    volume_min: float = 0.01
    volume_step: float = 0.01
    point: float = 0.01
    filling_mode: int = 2
    trade_stops_level: int = 1


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    SYMBOL_TRADE_MODE_FULL = 4
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_FOK = 0
    TRADE_RETCODE_DONE = 10009
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1

    def __init__(self, account=None, terminal=None, symbol=None):
        self.account = account or Account()
        self.terminal = terminal or Terminal()
        self.symbol = symbol or Symbol()
        self.sends = []
        self.stops = 0
        self.tick_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def initialize(self, path, *, timeout):
        assert path == "C:/DEMO/terminal64.exe" and timeout == 5000
        return True

    def shutdown(self):
        self.stops += 1

    def account_info(self):
        return self.account

    def terminal_info(self):
        return self.terminal

    def symbol_info(self, symbol):
        assert symbol == "XAUUSD.s"
        return self.symbol

    def positions_get(self):
        return ()

    def orders_get(self):
        return ()

    def symbol_info_tick(self, symbol):
        assert symbol == "XAUUSD.s"
        return type("Tick", (), {"bid": 4000.0, "ask": 4000.1,
                                   "time_msc": self.tick_ms})()

    def order_check(self, request):
        assert request["symbol"] == "XAUUSD.s" and request["volume"] == 0.01
        assert request["sl"] == 3998.0 and request["tp"] == 4002.0
        return type("Check", (), {"retcode": 0})()

    def order_send(self, request):
        self.sends.append(request)
        return type("Result", (), {"retcode": 10009, "order": 9001,
                                   "deal": 456, "price": 4000.1})()


class ForgedSuccessRetcode:
    """Spoof equality with documented success and refusal codes."""

    def __eq__(self, other):
        return other in (0, 10009, 10013)

    def __ne__(self, other):
        return not self == other


class HiddenBrokerRecords:
    """Hide an exposure while impersonating an empty broker tuple."""

    records = (object(),)

    def __bool__(self):
        return False

    def __eq__(self, other):
        return other == ()

    def __ne__(self, other):
        return not self == other


CONFIG = DemoTerminalConfig("C:/DEMO/terminal64.exe", 123456, "Sandbox-Demo", "XAUUSD.s")
ORDER = DemoOrder("test-intent-1", "XAUUSD.s", "BUY", 0.01, 3998.0, 4002.0)


class ChangingVolumeOrder(DemoOrder):
    """Expose safe values during validation, then enlarge the broker request."""

    def __getattribute__(self, name):
        if name == "volume":
            reads = object.__getattribute__(self, "_volume_reads")
            object.__setattr__(self, "_volume_reads", reads + 1)
            # submit_demo_order reads volume seven times before constructing
            # the request. A caller-owned subclass can change the eighth read.
            return 1.0 if reads >= 7 else 0.01
        return super().__getattribute__(name)


class ValidatorOverridingConfig(DemoTerminalConfig):
    validate_called = False

    def validate(self):
        type(self).validate_called = True


def test_transport_rejects_order_subclass_before_values_can_change(tmp_path):
    order = ChangingVolumeOrder(
        "changing-order", "XAUUSD.s", "BUY", 0.01, 3998.0, 4002.0)
    object.__setattr__(order, "_volume_reads", 0)
    api = FakeMT5()
    api.order_check = lambda request: type("Check", (), {"retcode": 0})()

    result = submit_demo_order(api, CONFIG, order, tmp_path / "demo.sqlite3")

    assert not result.sent
    assert api.sends == []
    assert order._volume_reads == 0


def test_transport_rejects_config_subclass_without_running_validator(tmp_path):
    ValidatorOverridingConfig.validate_called = False
    config = ValidatorOverridingConfig(
        "C:/DEMO/terminal64.exe", 123456, "Sandbox-Demo", "XAUUSD.s")
    api = FakeMT5()

    result = submit_demo_order(api, config, ORDER, tmp_path / "demo.sqlite3")

    assert not result.sent
    assert api.sends == []
    assert ValidatorOverridingConfig.validate_called is False


def test_one_real_demo_ack_is_durable_and_duplicate_never_sends(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    first = submit_demo_order(api, CONFIG, ORDER, ledger)
    assert first.sent and first.accepted and first.broker_order_id == 9001
    assert api.stops == 1 and len(api.sends) == 1
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT status, broker_order_id, broker_deal_id, broker_price, "
                          "symbol, side, volume, stop_loss, take_profit, source_kind FROM attempts").fetchall() == [
                              ("ACCEPTED", 9001, 456, 4000.1, "XAUUSD.s", "BUY", 0.01, 3998, 4002,
                               "manual_sandbox")]
    again = submit_demo_order(api, CONFIG, ORDER, ledger)
    assert not again.sent and len(api.sends) == 1


def test_old_ledger_rows_remain_unattributed_when_source_column_is_migrated(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE attempts (account_hash TEXT NOT NULL, intent_id TEXT NOT NULL, "
                   "status TEXT NOT NULL, broker_order_id INTEGER, broker_deal_id INTEGER, "
                   "broker_price REAL, symbol TEXT NOT NULL, side TEXT NOT NULL, volume REAL NOT NULL, "
                   "stop_loss REAL NOT NULL, take_profit REAL NOT NULL, reserved_at TEXT NOT NULL, "
                   "PRIMARY KEY (account_hash, intent_id))")
        db.execute("INSERT INTO attempts (account_hash, intent_id, status, broker_order_id, "
                   "symbol, side, volume, stop_loss, take_profit, reserved_at) "
                   "VALUES (?, 'old-intent', 'ACCEPTED', 9000, 'XAUUSD.s', 'BUY', 0.01, 3998, 4002, ?)",
                   ("0" * 64, datetime.now(timezone.utc).isoformat()))
    assert submit_demo_order(FakeMT5(), CONFIG, ORDER, ledger).accepted
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT source_kind FROM attempts ORDER BY intent_id").fetchall() == [
            ("legacy_unattributed",), ("manual_sandbox",)]


def test_real_account_disallowed_even_when_login_and_server_match(tmp_path):
    api = FakeMT5(account=Account(trade_mode=2))
    result = submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3")
    assert not result.sent and not api.sends


def test_terminal_disabled_and_stale_quote_never_send(tmp_path):
    api = FakeMT5(terminal=Terminal(trade_allowed=False))
    assert not submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3").sent
    api = FakeMT5()
    api.tick_ms -= 60_000
    assert not submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3").sent
    assert not api.sends


def test_broker_fok_and_explicit_three_hour_clock_offset(tmp_path):
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_000
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    result = submit_demo_order(api, config, ORDER, tmp_path / "demo.sqlite3")
    assert result.accepted and api.sends[0]["type_filling"] == api.ORDER_FILLING_FOK


def test_shifted_tick_with_subsecond_future_skew_is_bound_through_order_ledger(tmp_path):
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_300
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    ledger = tmp_path / "demo.sqlite3"
    readiness = inspect_demo_readiness(api, config)
    assert readiness.ready_for_demo_attempt
    assert readiness.observed_tick_utc_offset_seconds == 10800
    assert not submit_demo_order(api, CONFIG, ORDER, ledger).sent
    sent = submit_demo_order(api, config, ORDER, ledger)
    assert sent.accepted and len(api.sends) == 1
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT server_utc_offset_seconds FROM attempts").fetchone() == (10800,)


def test_shifted_tick_beyond_one_second_future_tolerance_never_sends(tmp_path):
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_803_000
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    assert not inspect_demo_readiness(api, config).ready_for_demo_attempt
    assert not submit_demo_order(api, config, ORDER, tmp_path / "demo.sqlite3").sent
    assert not api.sends


def test_fok_future_quote_without_offset_and_stale_offset_quote_refuse(tmp_path):
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_000
    assert not submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3").sent
    api.tick_ms -= 60_000
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    assert not submit_demo_order(api, config, ORDER, tmp_path / "demo.sqlite3").sent
    assert not api.sends


def test_unsupported_filling_and_invalid_offset_refuse(tmp_path):
    api = FakeMT5(symbol=Symbol(filling_mode=0))
    assert not submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3").sent
    assert not submit_demo_order(FakeMT5(), replace(CONFIG, server_utc_offset_seconds=3600),
                                 ORDER, tmp_path / "demo.sqlite3").sent
    assert not api.sends


def test_excess_loss_and_existing_exposure_never_send(tmp_path):
    risk = DemoOrder("test-intent-2", "XAUUSD.s", "BUY", 0.01, 3990, 4002)
    api = FakeMT5()
    assert not submit_demo_order(api, CONFIG, risk, tmp_path / "demo.sqlite3").sent
    api.positions_get = lambda: (object(),)
    assert not submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3").sent
    assert not api.sends


@pytest.mark.parametrize("method_name", ["positions_get", "orders_get"])
def test_hidden_broker_exposure_cannot_spoof_empty_results(tmp_path, method_name):
    api = FakeMT5()
    setattr(api, method_name, lambda: HiddenBrokerRecords())
    ledger = tmp_path / "demo.sqlite3"

    result = submit_demo_order(api, CONFIG, ORDER, ledger)

    assert not result.sent
    assert not result.accepted
    assert api.sends == []
    assert not ledger.exists()


def test_account_switch_during_broker_precheck_refuses_send(tmp_path):
    api = FakeMT5()

    def switch_account(request):
        api.account = Account(trade_mode=2)
        return type("Check", (), {"retcode": 0})()

    api.order_check = switch_account
    result = submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3")
    assert not result.sent and not api.sends
    assert not (tmp_path / "demo.sqlite3").exists()


def test_no_broker_approval_or_read_error_never_reserves(tmp_path):
    api = FakeMT5()
    api.order_check = lambda request: type("Check", (), {"retcode": 10013})()
    assert not submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3").sent
    assert not (tmp_path / "demo.sqlite3").exists()
    api = FakeMT5()
    api.orders_get = lambda: None
    assert not submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3").sent
    assert not api.sends


def test_order_check_cannot_mutate_the_broker_bound_request(tmp_path):
    api = FakeMT5()

    def mutating_check(request):
        request["symbol"] = "BTCUSD"
        request["volume"] = 1.0
        request["type"] = api.ORDER_TYPE_SELL
        return type("Check", (), {"retcode": 0})()

    api.order_check = mutating_check
    ledger = tmp_path / "demo.sqlite3"

    result = submit_demo_order(api, CONFIG, ORDER, ledger)

    assert not result.sent
    assert api.sends == []
    assert not ledger.exists()


@pytest.mark.parametrize("retcode", [False, 0.0, ForgedSuccessRetcode()])
def test_order_check_requires_exact_integer_success_retcode(tmp_path, retcode):
    api = FakeMT5()
    api.order_check = lambda request: type("Check", (), {"retcode": retcode})()
    ledger = tmp_path / "demo.sqlite3"

    result = submit_demo_order(api, CONFIG, ORDER, ledger)

    assert not result.sent
    assert not result.accepted
    assert api.sends == []
    assert not ledger.exists()


@pytest.mark.parametrize("retcode", [10009.0, ForgedSuccessRetcode()])
def test_order_send_requires_exact_integer_success_retcode(tmp_path, retcode):
    api = FakeMT5()

    def forged_send(request):
        api.sends.append(request)
        return type("Result", (), {"retcode": retcode, "order": 9001,
                                   "deal": 456, "price": 4000.1})()

    api.order_send = forged_send
    ledger = tmp_path / "demo.sqlite3"

    result = submit_demo_order(api, CONFIG, ORDER, ledger)

    assert result.sent
    assert not result.accepted
    assert result.broker_order_id is None
    assert len(api.sends) == 1
    with sqlite3.connect(ledger) as db:
        assert db.execute(
            "SELECT status, broker_order_id, broker_deal_id, broker_price FROM attempts"
        ).fetchall() == [("UNKNOWN", None, None, None)]


def test_order_send_requires_documented_integer_success_constant(tmp_path):
    api = FakeMT5()
    api.TRADE_RETCODE_DONE = ForgedSuccessRetcode()

    def refused_send(request):
        api.sends.append(request)
        return type("Result", (), {"retcode": 10013, "order": 9001,
                                   "deal": 456, "price": 4000.1})()

    api.order_send = refused_send
    ledger = tmp_path / "demo.sqlite3"

    result = submit_demo_order(api, CONFIG, ORDER, ledger)

    assert result.sent
    assert not result.accepted
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT status, broker_order_id FROM attempts").fetchall() == [
            ("UNKNOWN", None)]


def test_strategy_expected_price_deviation_is_checked_at_transport(tmp_path):
    order = DemoOrder("auto-price-1", "XAUUSD.s", "BUY", .01, 3998, 4002, 3999.0)
    api = FakeMT5()
    result = submit_demo_order(api, CONFIG, order, tmp_path / "demo.sqlite3")
    assert not result.sent and not api.sends


def test_unknown_outcome_stays_reserved_and_blocks_following_orders(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    api.order_send = lambda request: None
    first = submit_demo_order(api, CONFIG, ORDER, ledger)
    assert first.sent and not first.accepted
    second = submit_demo_order(api, CONFIG,
                               DemoOrder("test-intent-3", "XAUUSD.s", "BUY", .01, 3998, 4002), ledger)
    assert not second.sent


def test_cli_needs_explicit_ack_and_never_displays_identity(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", "123456")
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)
    monkeypatch.delenv("SHREEK_DEMO_TRADING_ACK", raising=False)
    api = FakeMT5()
    monkeypatch.setattr(mt5_demo_order_cli, "demo_only_mt5_runtime", lambda: api)
    args = ["--intent-id", "test-intent-4", "--side", "BUY", "--stop-loss", "3998",
            "--take-profit", "4002", "--ledger", str(tmp_path / "demo.sqlite3")]
    assert mt5_demo_order_cli.main(args) == 2
    assert mt5_demo_order_cli.main(["--execute-demo"] + args) == 2
    assert not api.sends
    monkeypatch.setenv("SHREEK_DEMO_TRADING_ACK", "DEMO_ONLY")
    assert mt5_demo_order_cli.main(["--execute-demo"] + args) == 0
    output = capsys.readouterr().out
    assert "123456" not in output and "Sandbox-Demo" not in output
    assert len(api.sends) == 1


@pytest.mark.parametrize("blocker", ["kill", "lock", "stop", "ledger", "journal"])
def test_manual_cli_local_blockers_prevent_runtime_access(monkeypatch, capsys, tmp_path, blocker):
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", "123456")
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)
    monkeypatch.setenv("SHREEK_DEMO_TRADING_ACK", "DEMO_ONLY")
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")
    ledger = tmp_path / "demo.sqlite3"
    if blocker == "kill":
        monkeypatch.delenv("SHREEK_DEMO_KILL_SWITCH")
    else:
        path = {"lock": ledger.with_suffix(".watch.lock"),
                "stop": ledger.with_suffix(".stop"),
                "ledger": ledger,
                "journal": ledger.with_suffix(".scans.sqlite3")}[blocker]
        path.write_text("blocked")

    def forbidden_runtime():
        pytest.fail("blocked manual order accessed broker runtime")

    monkeypatch.setattr(mt5_demo_order_cli, "demo_only_mt5_runtime", forbidden_runtime)
    args = ["--execute-demo", "--intent-id", "manual-blocked", "--side", "BUY",
            "--stop-loss", "3998", "--take-profit", "4002", "--ledger", str(ledger)]
    assert mt5_demo_order_cli.main(args) == 2
    import json
    result = json.loads(capsys.readouterr().out)
    assert not result["sent"] and not result["accepted"]
    assert ledger.with_suffix(".watch.lock").exists() == (blocker == "lock")


def test_manual_cli_holds_shared_lock_and_preserves_sent_outcome_on_cleanup_failure(
        monkeypatch, capsys, tmp_path):
    from contextlib import contextmanager
    import json
    from execution.mt5_demo_session_journal import exclusive_demo_session

    monkeypatch.setenv("SHREEK_DEMO_LOGIN", "123456")
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)
    monkeypatch.setenv("SHREEK_DEMO_TRADING_ACK", "DEMO_ONLY")
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    original_send = api.order_send

    def checked_send(request):
        assert ledger.with_suffix(".watch.lock").exists()
        with pytest.raises(FileExistsError):
            with exclusive_demo_session(ledger):
                pytest.fail("second runner acquired an active manual session")
        return original_send(request)

    @contextmanager
    def failed_cleanup(path):
        with exclusive_demo_session(path):
            yield
        raise OSError("cleanup failure")

    api.order_send = checked_send
    monkeypatch.setattr(mt5_demo_order_cli, "demo_only_mt5_runtime", lambda: api)
    monkeypatch.setattr(mt5_demo_order_cli, "exclusive_demo_session", failed_cleanup)
    args = ["--execute-demo", "--intent-id", "manual-cleanup", "--side", "BUY",
            "--stop-loss", "3998", "--take-profit", "4002", "--ledger", str(ledger)]
    assert mt5_demo_order_cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["sent"] and result["accepted"]
    assert "session_lock_error" in result
    assert len(api.sends) == 1
