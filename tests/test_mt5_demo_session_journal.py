import json
import sqlite3
from dataclasses import asdict

import pytest

from execution import mt5_demo_auto_cli
from execution.mt5_demo_auto import DemoAutoResult
from execution.mt5_demo_session_journal import DemoSessionJournal
from execution.mt5_demo_session_report_cli import inspect_sessions, main as report_main
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


def test_interruption_inside_poll_records_end_without_inventing_submission(monkeypatch, tmp_path, capsys):
    _env(monkeypatch)
    ledger = tmp_path / "demo.sqlite3"
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: object())
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(mt5_demo_auto_cli, "scan_and_submit_demo", interrupt)
    assert mt5_demo_auto_cli.main(["--ledger", str(ledger)]) == 130
    output = json.loads(capsys.readouterr().out)
    assert "sent" not in output and output["session_status"] == "interrupted"
    session = inspect_sessions(ledger)["sessions"][0]
    assert session["end_recorded"] and session["end_reason"] == "interrupted"
    assert session["scans"] == 0 and session["last_result"] is None


def test_unexpected_failure_records_aborted_and_does_not_hide_exception(monkeypatch, tmp_path):
    _env(monkeypatch)
    ledger = tmp_path / "demo.sqlite3"
    def unavailable():
        raise RuntimeError("native runtime failure")
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", unavailable)
    with pytest.raises(RuntimeError):
        mt5_demo_auto_cli.main(["--ledger", str(ledger)])
    assert inspect_sessions(ledger)["sessions"][0]["end_reason"] == "aborted"


def test_offline_report_bounds_sessions_and_preserves_uncertain_submission(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    older = DemoSessionJournal(ledger, execute=False, watch_minutes=0)
    older.record(DemoAutoResult(False, False, False, "no signal"))
    older.finish("scan_complete")
    latest = DemoSessionJournal(ledger, execute=True, watch_minutes=60)
    latest.record(DemoAutoResult(False, False, False, "no signal"))
    latest.record(DemoAutoResult(True, True, False, "submission uncertain; do not retry"))
    latest.finish("submission_attempted")
    path = ledger.with_suffix(".scans.sqlite3")
    before = path.read_bytes()
    report = inspect_sessions(ledger, 1)
    assert report["broker_history_verified"] is False
    session, = report["sessions"]
    assert session["session_id"] == latest.session_id and session["end_recorded"]
    assert (session["scans"], session["signals"], session["submission_observations"],
            session["accepted_observations"]) == (2, 1, 1, 0)
    assert session["last_result"]["sent"] and not session["last_result"]["accepted"]
    assert path.read_bytes() == before and not ledger.exists()


def test_legacy_journal_is_readable_and_migrates_without_claiming_session_end(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    path = ledger.with_suffix(".scans.sqlite3")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, "
                   "execute_requested INTEGER NOT NULL, watch_minutes INTEGER NOT NULL)")
        db.execute("CREATE TABLE scan_events (event_id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, "
                   "recorded_at TEXT NOT NULL, result_json TEXT NOT NULL)")
        db.execute("INSERT INTO sessions VALUES ('legacy', '2026-09-29T20:00:00+00:00', 0, 0)")
    before = path.read_bytes()
    session, = inspect_sessions(ledger)["sessions"]
    assert not session["end_recorded"] and session["end_reason"] is None
    assert path.read_bytes() == before
    new = DemoSessionJournal(ledger, execute=False, watch_minutes=0)
    new.finish("scan_complete")
    sessions = inspect_sessions(ledger)["sessions"]
    assert sessions[0]["end_recorded"] and not sessions[1]["end_recorded"]


def test_missing_journal_report_never_creates_files(tmp_path, capsys):
    ledger = tmp_path / "demo.sqlite3"
    assert report_main(["--ledger", str(ledger)]) == 2
    assert not json.loads(capsys.readouterr().out)["journal_readable"]
    assert list(tmp_path.iterdir()) == []


def test_malformed_observation_fails_without_printing_raw_data(tmp_path, capsys):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=False, watch_minutes=0)
    raw = asdict(DemoAutoResult(False, False, False, "no signal"))
    raw["private_identity"] = "should-not-appear"
    with sqlite3.connect(journal.path) as db:
        db.execute("INSERT INTO scan_events VALUES (1, ?, 'now', ?)", (journal.session_id, json.dumps(raw)))
    assert report_main(["--ledger", str(ledger)]) == 2
    assert "should-not-appear" not in capsys.readouterr().out


def test_session_end_write_failure_stops_and_preserves_accepted_result(monkeypatch, tmp_path, capsys):
    _env(monkeypatch)
    ledger = tmp_path / "demo.sqlite3"
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: object())
    monkeypatch.setattr(mt5_demo_auto_cli, "scan_and_submit_demo", lambda *a, **k:
                        DemoAutoResult(True, True, True, "accepted"))
    def fail(*args):
        raise sqlite3.OperationalError("disk unavailable")
    monkeypatch.setattr(DemoSessionJournal, "finish", fail)
    assert mt5_demo_auto_cli.main(["--ledger", str(ledger)]) == 2
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0]["sent"] is True and lines[0]["accepted"] is True
    assert "session_journal_error" in lines[1]
    assert not inspect_sessions(ledger)["sessions"][0]["end_recorded"]


@pytest.mark.parametrize("sent, accepted, expected", [
    (False, False, "scan_complete"),
    (True, False, "submission_attempted"),
    (True, True, "submission_attempted"),
])
def test_runner_records_scan_and_submission_ends(monkeypatch, tmp_path, sent, accepted, expected):
    _env(monkeypatch)
    ledger = tmp_path / "demo.sqlite3"
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: object())
    monkeypatch.setattr(mt5_demo_auto_cli, "scan_and_submit_demo", lambda *a, **k:
                        DemoAutoResult(sent, sent, accepted, "observed"))
    assert mt5_demo_auto_cli.main(["--ledger", str(ledger)]) == (0 if accepted else 2)
    session, = inspect_sessions(ledger)["sessions"]
    assert session["end_reason"] == expected and session["end_recorded"]


def test_stop_file_records_end_without_polling(monkeypatch, tmp_path):
    _env(monkeypatch)
    ledger = tmp_path / "demo.sqlite3"
    ledger.with_suffix(".stop").touch()
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: object())
    def unexpected(*a, **k):
        raise AssertionError("stopped watcher must not poll")
    monkeypatch.setattr(mt5_demo_auto_cli, "scan_and_submit_demo", unexpected)
    assert mt5_demo_auto_cli.main(["--ledger", str(ledger)]) == 2
    assert inspect_sessions(ledger)["sessions"][0]["end_reason"] == "stop_file"


def test_watch_expiry_records_end_and_does_not_sleep(monkeypatch, tmp_path):
    _env(monkeypatch)
    monkeypatch.setenv("SHREEK_DEMO_AUTO_ACK", "DEMO_ONLY_RESEARCH")
    ledger = tmp_path / "demo.sqlite3"
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: object())
    monkeypatch.setattr(mt5_demo_auto_cli, "scan_and_submit_demo", lambda *a, **k:
                        DemoAutoResult(False, False, False, "no signal"))
    ticks = iter((0, 61))
    monkeypatch.setattr(mt5_demo_auto_cli.time, "monotonic", lambda: next(ticks))
    def unexpected(*a):
        raise AssertionError("expired watcher must not sleep")
    monkeypatch.setattr(mt5_demo_auto_cli.time, "sleep", unexpected)
    assert mt5_demo_auto_cli.main(["--ledger", str(ledger), "--execute-demo-auto", "--watch-minutes", "1"]) == 2
    assert inspect_sessions(ledger)["sessions"][0]["end_reason"] == "watch_expired"
