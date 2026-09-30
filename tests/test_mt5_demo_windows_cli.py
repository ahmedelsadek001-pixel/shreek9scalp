"""Windows launcher gates without native MT5 or any broker connection."""
import os

import pytest

from execution import mt5_demo_auto_cli, mt5_demo_preflight_cli, mt5_demo_windows_cli
from utils import mt5_compat


def binding(monkeypatch, tmp_path):
    terminal = tmp_path / "terminal64.exe"
    terminal.touch()
    monkeypatch.setattr(mt5_demo_windows_cli.platform, "system", lambda: "Windows")
    monkeypatch.setattr(mt5_compat, "AVAILABLE", True)
    for key, value in {"SHREEK_DEMO_TERMINAL_PATH": str(terminal),
                       "SHREEK_DEMO_LOGIN": "123456", "SHREEK_DEMO_SERVER": "Sandbox-Demo",
                       "SHREEK_DEMO_SYMBOL": "XAUUSD.s", "SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS": "0",
                       "LOCALAPPDATA": str(tmp_path), "SHREEK_DEMO_TRADING_ACK": "DEMO_ONLY",
                       "SHREEK_DEMO_AUTO_ACK": "old-value", "SHREEK_DEMO_KILL_SWITCH": "ON"}.items():
        monkeypatch.setenv(key, value)
    return tmp_path / "SHREEK" / "demo_orders.sqlite3"


def test_windows_launcher_refuses_linux_without_prompts_or_runtime(monkeypatch, capsys):
    monkeypatch.setattr(mt5_demo_windows_cli.platform, "system", lambda: "Linux")
    assert mt5_demo_windows_cli.main(["--watch-demo"]) == 2
    assert "Windows PC" in capsys.readouterr().out


@pytest.mark.parametrize("watch_requested,preflight_code", [(False, 0), (False, 2), (True, 2)])
def test_read_only_or_failed_preflight_never_starts_watch(
        monkeypatch, tmp_path, watch_requested, preflight_code):
    ledger = binding(monkeypatch, tmp_path)
    calls = []

    def preflight(argv):
        assert argv == ["--ledger", str(ledger)]
        assert os.environ["SHREEK_DEMO_TRADING_ACK"] == ""
        assert os.environ["SHREEK_DEMO_AUTO_ACK"] == ""
        assert os.environ["SHREEK_DEMO_KILL_SWITCH"] == "ON"
        calls.append("preflight")
        return preflight_code

    monkeypatch.setattr(mt5_demo_preflight_cli, "main", preflight)
    monkeypatch.setattr(mt5_demo_auto_cli, "main", lambda argv: pytest.fail("unexpected DEMO watch"))
    assert mt5_demo_windows_cli.main(["--watch-demo"] if watch_requested else []) == preflight_code
    assert calls == ["preflight"]
    assert os.environ["SHREEK_DEMO_AUTO_ACK"] == "old-value"
    assert os.environ["SHREEK_DEMO_TRADING_ACK"] == "DEMO_ONLY"


def test_explicit_watch_follows_preflight_and_restores_flags_on_failure(monkeypatch, tmp_path):
    ledger = binding(monkeypatch, tmp_path)
    calls = []

    def preflight(argv):
        calls.append("preflight")
        return 0

    def watch(argv):
        assert calls == ["preflight"]
        assert argv == ["--execute-demo-auto", "--watch-minutes", "60", "--ledger", str(ledger)]
        assert os.environ["SHREEK_DEMO_AUTO_ACK"] == "DEMO_ONLY_RESEARCH"
        assert os.environ["SHREEK_DEMO_KILL_SWITCH"] == "OFF"
        raise OSError("private diagnostic")

    monkeypatch.setattr(mt5_demo_preflight_cli, "main", preflight)
    monkeypatch.setattr(mt5_demo_auto_cli, "main", watch)
    assert mt5_demo_windows_cli.main(["--watch-demo"]) == 2
    assert os.environ["SHREEK_DEMO_KILL_SWITCH"] == "ON"
    assert os.environ["SHREEK_DEMO_AUTO_ACK"] == "old-value"


@pytest.mark.parametrize("invalid", ["runtime", "terminal", "clock", "login", "local_data"])
def test_invalid_windows_binding_never_calls_preflight(monkeypatch, tmp_path, invalid):
    binding(monkeypatch, tmp_path)
    if invalid == "runtime":
        monkeypatch.setattr(mt5_compat, "AVAILABLE", False)
    else:
        key, value = {"terminal": ("SHREEK_DEMO_TERMINAL_PATH", str(tmp_path / "missing.exe")),
                      "clock": ("SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS", "3600"),
                      "login": ("SHREEK_DEMO_LOGIN", "invalid"),
                      "local_data": ("LOCALAPPDATA", "relative")}[invalid]
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(mt5_demo_preflight_cli, "main", lambda argv: pytest.fail("invalid preflight"))
    assert mt5_demo_windows_cli.main(["--watch-demo"]) == 2
