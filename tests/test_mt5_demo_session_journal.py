import json
import sqlite3

from execution import mt5_demo_auto_cli
from execution.mt5_demo_auto import DemoAutoResult
from test_mt5_demo_transport import CONFIG


def _env(monkeypatch):
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", str(CONFIG.expected_login))
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)


def test_no_signal_observation_is_durable_and_contains_no_identity(monkeypatch, tmp_path, capsys):
    _env(monkeypatch)
    ledger = tmp_path / "demo.sqlite3"
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: object())
    monkeypatch.setattr(mt5_demo_auto_cli, "scan_and_submit_demo", lambda *a, **k:
                        DemoAutoResult(False, False, False, "no unique current closed-bar strategy signal"))
    assert mt5_demo_auto_cli.main(["--ledger", str(ledger)]) == 2
    assert not ledger.exists()
    with sqlite3.connect(str(ledger.with_suffix(".scans.sqlite3"))) as db:
        rows = db.execute("SELECT result_json FROM scan_events").fetchall()
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    assert len(rows) == 1 and json.loads(rows[0][0])["sent"] is False
    assert str(CONFIG.expected_login) not in rows[0][0] + capsys.readouterr().out


def test_journal_failure_before_poll_never_calls_broker(monkeypatch, tmp_path, capsys):
    _env(monkeypatch)
    def unavailable():
        raise AssertionError("native runtime must not be reached")
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", unavailable)
    assert mt5_demo_auto_cli.main(["--ledger", str(tmp_path / "missing" / "demo.sqlite3")]) == 2
    assert "execution refused" in capsys.readouterr().out


def test_post_submission_log_failure_preserves_sent_outcome(monkeypatch, tmp_path, capsys):
    _env(monkeypatch)
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: object())
    monkeypatch.setattr(mt5_demo_auto_cli, "scan_and_submit_demo", lambda *a, **k:
                        DemoAutoResult(True, True, False, "DEMO submission uncertain; do not retry"))
    def fail(*args):
        raise sqlite3.OperationalError("disk unavailable")
    monkeypatch.setattr(mt5_demo_auto_cli.DemoSessionJournal, "record", fail)
    assert mt5_demo_auto_cli.main(["--ledger", str(tmp_path / "demo.sqlite3")]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["sent"] is True and "session_journal_error" in result
