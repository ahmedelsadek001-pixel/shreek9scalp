from datetime import datetime, timezone
import json

from execution import mt5_demo_preflight_cli
from test_mt5_demo_auto import _api
from test_mt5_demo_transport import Account, FakeMT5, Symbol, CONFIG


def _env(monkeypatch):
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", str(CONFIG.expected_login))
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)
    monkeypatch.setenv("SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS", "10800")
    # A read-only command cannot inherit execution authority from the shell.
    monkeypatch.setenv("SHREEK_DEMO_AUTO_ACK", "DEMO_ONLY_RESEARCH")
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")


def test_preflight_reports_broker_fok_and_dry_strategy_scan(monkeypatch, capsys):
    _env(monkeypatch)
    api, _, _ = _api(datetime.now(timezone.utc))
    api.symbol = Symbol(filling_mode=1)
    api.tick_ms += 10_800_000
    original = mt5_demo_preflight_cli.scan_and_submit_demo

    def observed_scan(*args, **kwargs):
        assert kwargs == {"execute": False, "kill_switch_off": False}
        return original(*args, **kwargs)

    monkeypatch.setattr(mt5_demo_preflight_cli, "scan_and_submit_demo", observed_scan)
    monkeypatch.setattr(mt5_demo_preflight_cli, "read_only_mt5_runtime", lambda: api)
    assert mt5_demo_preflight_cli.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["connected_demo"] and report["ready_for_demo_attempt"]
    assert report["readiness"]["observed_filling_policy"] == "FOK"
    assert report["strategy_scan"]["sent"] is False
    assert str(CONFIG.expected_login) not in json.dumps(report)
    assert not api.sends


def test_preflight_refuses_real_account_and_missing_binding(monkeypatch, capsys):
    _env(monkeypatch)
    api = FakeMT5(account=Account(trade_mode=2))
    monkeypatch.setattr(mt5_demo_preflight_cli, "read_only_mt5_runtime", lambda: api)
    assert mt5_demo_preflight_cli.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert not report["connected_demo"] and report["strategy_scan"] is None
    monkeypatch.delenv("SHREEK_DEMO_LOGIN")
    assert mt5_demo_preflight_cli.main() == 2
    assert "binding incomplete" in capsys.readouterr().out
    assert not api.sends


def test_preflight_stale_quote_never_scans_or_sends(monkeypatch, capsys):
    _env(monkeypatch)
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_000 - 60_000
    monkeypatch.setattr(mt5_demo_preflight_cli, "read_only_mt5_runtime", lambda: api)
    assert mt5_demo_preflight_cli.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert report["readiness"]["observed_tick_utc_offset_seconds"] is None
    assert report["strategy_scan"] is None and not api.sends
