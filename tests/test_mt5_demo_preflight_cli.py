from datetime import datetime, timezone
import json
import sqlite3

import pytest

from execution import mt5_demo_preflight_cli
from test_mt5_demo_auto import _api
from test_mt5_demo_transport import Account, FakeMT5, Symbol, CONFIG, ORDER
from execution.mt5_demo_transport import submit_demo_order
from execution.mt5_demo_session_journal import DemoSessionJournal


def _env(monkeypatch):
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", str(CONFIG.expected_login))
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)
    monkeypatch.setenv("SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS", "10800")
    # A read-only command cannot inherit execution authority from the shell.
    monkeypatch.setenv("SHREEK_DEMO_AUTO_ACK", "DEMO_ONLY_RESEARCH")
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")


def test_preflight_reports_broker_fok_and_dry_strategy_scan(monkeypatch, capsys, tmp_path):
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
    assert mt5_demo_preflight_cli.main(["--ledger", str(tmp_path / "demo.sqlite3")]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["connected_demo"] and report["ready_for_demo_attempt"]
    assert report["ready_for_demo_session"] and report["session_blockers"] == []
    assert report["readiness"]["observed_filling_policy"] == "FOK"
    assert report["strategy_scan"]["sent"] is False
    assert str(CONFIG.expected_login) not in json.dumps(report)
    assert not api.sends


def test_preflight_refuses_real_account_and_missing_binding(monkeypatch, capsys, tmp_path):
    _env(monkeypatch)
    api = FakeMT5(account=Account(trade_mode=2))
    monkeypatch.setattr(mt5_demo_preflight_cli, "read_only_mt5_runtime", lambda: api)
    args = ["--ledger", str(tmp_path / "demo.sqlite3")]
    assert mt5_demo_preflight_cli.main(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert not report["connected_demo"] and report["strategy_scan"] is None
    monkeypatch.delenv("SHREEK_DEMO_LOGIN")
    assert mt5_demo_preflight_cli.main(args) == 2
    assert "binding incomplete" in capsys.readouterr().out
    assert not api.sends


def test_preflight_stale_quote_never_scans_or_sends(monkeypatch, capsys, tmp_path):
    _env(monkeypatch)
    api = FakeMT5(symbol=Symbol(filling_mode=1))
    api.tick_ms += 10_800_000 - 60_000
    monkeypatch.setattr(mt5_demo_preflight_cli, "read_only_mt5_runtime", lambda: api)
    assert mt5_demo_preflight_cli.main(["--ledger", str(tmp_path / "demo.sqlite3")]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["readiness"]["observed_tick_utc_offset_seconds"] is None
    assert report["strategy_scan"] is None and not api.sends


def test_preflight_blocks_stop_file_and_unresolved_ledger(monkeypatch, capsys, tmp_path):
    _env(monkeypatch)
    ledger = tmp_path / "demo.sqlite3"
    args = ["--ledger", str(ledger)]
    api, _, _ = _api(datetime.now(timezone.utc))
    api.tick_ms += 10_800_000
    monkeypatch.setattr(mt5_demo_preflight_cli, "read_only_mt5_runtime", lambda: api)
    ledger.with_suffix(".stop").touch()
    assert mt5_demo_preflight_cli.main(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["ready_for_demo_attempt"] and not report["ready_for_demo_session"]
    assert "automatic DEMO stop file active" in report["session_blockers"]
    assert report["strategy_scan"] is None
    ledger.with_suffix(".stop").unlink()
    uncertain = FakeMT5()
    uncertain.order_send = lambda request: None
    assert submit_demo_order(uncertain, CONFIG, ORDER, ledger).sent
    assert mt5_demo_preflight_cli.main(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert "unresolved DEMO submission in ledger" in report["session_blockers"]
    assert not api.sends


def test_preflight_rejects_malformed_or_missing_ledger_location(monkeypatch, capsys, tmp_path):
    _env(monkeypatch)
    api, _, _ = _api(datetime.now(timezone.utc))
    api.tick_ms += 10_800_000
    monkeypatch.setattr(mt5_demo_preflight_cli, "read_only_mt5_runtime", lambda: api)
    ledger = tmp_path / "demo.sqlite3"
    ledger.write_text("not a database", encoding="utf-8")
    assert mt5_demo_preflight_cli.main(["--ledger", str(ledger)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert "DEMO ledger or stop file unreadable or malformed" in report["session_blockers"]
    assert report["strategy_scan"] is None
    assert mt5_demo_preflight_cli.main(["--ledger", str(tmp_path / "missing" / "demo.sqlite3")]) == 2
    report = json.loads(capsys.readouterr().out)
    assert "DEMO ledger directory unavailable" in report["session_blockers"]
    assert not api.sends


@pytest.mark.parametrize("kind", ["corrupt", "wrong_schema", "directory"])
def test_preflight_blocks_invalid_scan_journal_without_modifying_it(monkeypatch, capsys, tmp_path, kind):
    _env(monkeypatch)
    ledger = tmp_path / "demo.sqlite3"
    journal = ledger.with_suffix(".scans.sqlite3")
    if kind == "directory":
        journal.mkdir()
    elif kind == "wrong_schema":
        with sqlite3.connect(journal) as db:
            db.execute("CREATE TABLE unrelated (value TEXT)")
    else:
        journal.write_bytes(b"invalid journal")
    before = journal.read_bytes() if journal.is_file() else None
    api, _, _ = _api(datetime.now(timezone.utc))
    api.tick_ms += 10_800_000
    monkeypatch.setattr(mt5_demo_preflight_cli, "read_only_mt5_runtime", lambda: api)
    assert mt5_demo_preflight_cli.main(["--ledger", str(ledger)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["ready_for_demo_attempt"] and not report["ready_for_demo_session"]
    assert "DEMO scan journal unreadable or malformed" in report["session_blockers"]
    assert report["strategy_scan"] is None and not api.sends
    assert not ledger.exists()
    if before is not None:
        assert journal.read_bytes() == before


def test_preflight_accepts_healthy_scan_journal_read_only(monkeypatch, capsys, tmp_path):
    _env(monkeypatch)
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=False, watch_minutes=0)
    journal.finish("scan_complete")
    before = journal.path.read_bytes()
    api, _, _ = _api(datetime.now(timezone.utc))
    api.tick_ms += 10_800_000
    monkeypatch.setattr(mt5_demo_preflight_cli, "read_only_mt5_runtime", lambda: api)
    assert mt5_demo_preflight_cli.main(["--ledger", str(ledger)]) == 0
    assert json.loads(capsys.readouterr().out)["ready_for_demo_session"]
    assert journal.path.read_bytes() == before and not ledger.exists() and not api.sends
