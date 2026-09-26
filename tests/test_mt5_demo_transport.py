"""DEMO transport safety behaviour against a fake, unprivileged MT5 API."""
from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3

from execution.mt5_demo_probe import DemoTerminalConfig
from execution.mt5_demo_transport import DemoOrder, submit_demo_order
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
    TRADE_RETCODE_DONE = 10009

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


CONFIG = DemoTerminalConfig("C:/DEMO/terminal64.exe", 123456, "Sandbox-Demo", "XAUUSD.s")
ORDER = DemoOrder("test-intent-1", "XAUUSD.s", "BUY", 0.01, 3998.0, 4002.0)


def test_one_real_demo_ack_is_durable_and_duplicate_never_sends(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    api = FakeMT5()
    first = submit_demo_order(api, CONFIG, ORDER, ledger)
    assert first.sent and first.accepted and first.broker_order_id == 9001
    assert api.stops == 1 and len(api.sends) == 1
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT status, broker_order_id, broker_deal_id, broker_price, "
                          "symbol, side, volume, stop_loss, take_profit FROM attempts").fetchall() == [
                              ("ACCEPTED", 9001, 456, 4000.1, "XAUUSD.s", "BUY", 0.01, 3998, 4002)]
    again = submit_demo_order(api, CONFIG, ORDER, ledger)
    assert not again.sent and len(api.sends) == 1


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


def test_excess_loss_and_existing_exposure_never_send(tmp_path):
    risk = DemoOrder("test-intent-2", "XAUUSD.s", "BUY", 0.01, 3990, 4002)
    api = FakeMT5()
    assert not submit_demo_order(api, CONFIG, risk, tmp_path / "demo.sqlite3").sent
    api.positions_get = lambda: (object(),)
    assert not submit_demo_order(api, CONFIG, ORDER, tmp_path / "demo.sqlite3").sent
    assert not api.sends


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
