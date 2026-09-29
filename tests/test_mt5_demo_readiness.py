"""Read-only operator diagnostics never substitute for DEMO transport gates."""
from dataclasses import replace
from datetime import datetime, timezone
import json

from execution.mt5_demo_readiness import inspect_demo_readiness
from execution import mt5_demo_readiness_cli
from test_mt5_demo_transport import Account, CONFIG, FakeMT5, Symbol, Terminal


def test_ready_demo_is_observational_only():
    api = FakeMT5()
    result = inspect_demo_readiness(api, CONFIG)
    assert result.ready_for_demo_attempt
    assert result.order_transport_enabled is False
    assert api.sends == [] and api.stops == 1


def test_real_and_wrong_identity_refused_without_order_call():
    api = FakeMT5(account=Account(trade_mode=2))
    assert not inspect_demo_readiness(api, CONFIG).ready_for_demo_attempt
    assert api.sends == []
    assert not inspect_demo_readiness(api, replace(CONFIG, expected_login=456789)).ready_for_demo_attempt


def test_disabled_terminal_weekend_quote_exposure_and_non_bid_mode_report_blockers():
    api = FakeMT5(terminal=Terminal(trade_allowed=False), symbol=Symbol(chart_mode=1))
    api.tick_ms -= 60_000
    api.positions_get = lambda: (object(),)
    result = inspect_demo_readiness(api, CONFIG)
    assert not result.ready_for_demo_attempt
    assert len(result.blockers) >= 4
    assert api.sends == []


def test_failed_exposure_read_and_account_switch_refused():
    api = FakeMT5()
    api.orders_get = lambda: None
    assert not inspect_demo_readiness(api, CONFIG).ready_for_demo_attempt
    api = FakeMT5()
    reads = 0

    def account_info():
        nonlocal reads
        reads += 1
        return Account() if reads == 1 else Account(trade_mode=2)

    api.account_info = account_info
    assert not inspect_demo_readiness(api, CONFIG).ready_for_demo_attempt


def test_missing_contract_details_cannot_look_ready():
    api = FakeMT5(symbol=Symbol(point=0))
    assert not inspect_demo_readiness(api, CONFIG).ready_for_demo_attempt


def test_fok_broker_with_explicit_offset_is_read_only_and_stale_refuses():
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_000
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    ready = inspect_demo_readiness(api, config)
    assert ready.ready_for_demo_attempt
    assert ready.observed_filling_policy == "FOK"
    assert ready.observed_tick_utc_offset_seconds == 10800
    assert not api.sends
    api.tick_ms -= 60_000
    assert not inspect_demo_readiness(api, config).ready_for_demo_attempt
    assert inspect_demo_readiness(api, config).observed_tick_utc_offset_seconds is None
    assert not inspect_demo_readiness(api, CONFIG).ready_for_demo_attempt


def test_diagnostic_does_not_turn_future_quote_into_readiness():
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_000
    report = inspect_demo_readiness(api, CONFIG)
    assert not report.ready_for_demo_attempt
    assert report.observed_filling_policy == "FOK"
    assert report.observed_tick_utc_offset_seconds == 10800
    assert "DEMO quote missing, stale or wide" in report.blockers
    assert not api.sends


def test_cli_redacts_account_even_for_ready_demo(monkeypatch, capsys):
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", str(CONFIG.expected_login))
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)
    monkeypatch.setattr(mt5_demo_readiness_cli, "read_only_mt5_runtime", lambda: FakeMT5())
    assert mt5_demo_readiness_cli.main() == 0
    output = capsys.readouterr().out
    assert str(CONFIG.expected_login) not in output and CONFIG.expected_server not in output
    assert json.loads(output)["order_transport_enabled"] is False


def test_cli_uses_explicit_broker_tick_offset(monkeypatch, capsys):
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", str(CONFIG.expected_login))
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)
    monkeypatch.setenv("SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS", "10800")
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_000
    monkeypatch.setattr(mt5_demo_readiness_cli, "read_only_mt5_runtime", lambda: api)
    assert mt5_demo_readiness_cli.main() == 0
    assert json.loads(capsys.readouterr().out)["ready_for_demo_attempt"]
    assert not api.sends


def test_future_or_naive_readiness_clock_refused():
    api = FakeMT5()
    assert not inspect_demo_readiness(api, CONFIG, now=datetime.now()).ready_for_demo_attempt
    assert not inspect_demo_readiness(api, CONFIG,
                                      now=datetime.now(timezone.utc).replace(year=2020)).ready_for_demo_attempt
