import json
from hashlib import sha256
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from execution import mt5_demo_auto_cli
from execution.mt5_demo_auto import DemoAutoResult
from execution.mt5_demo_session_journal import DemoSessionJournal, exclusive_demo_session
from execution.mt5_demo_session_report_cli import inspect_sessions, main as report_main
from execution.mt5_demo_ledger_preflight import ledger_session_blockers
from test_mt5_demo_transport import CONFIG, FakeMT5, ORDER
from execution.mt5_demo_transport import submit_demo_order
from execution.mt5_demo_handover import assess_handover


def _env(monkeypatch):
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", str(CONFIG.expected_login))
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)


def test_opt_in_session_lock_blocks_second_runner_and_preflight(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    lock = ledger.with_suffix(".watch.lock")
    with exclusive_demo_session(ledger):
        assert lock.is_file()
        assert "automatic DEMO session lock present" in ledger_session_blockers(ledger, CONFIG)
        with pytest.raises(FileExistsError):
            with exclusive_demo_session(ledger):
                pytest.fail("second runner entered the DEMO session")
    assert not lock.exists()
    assert "automatic DEMO session lock present" not in ledger_session_blockers(ledger, CONFIG)


def test_stale_lock_requires_manual_reconciliation_before_new_session(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    lock = ledger.with_suffix(".watch.lock")
    lock.write_text("prior runner terminated", encoding="utf-8")
    with pytest.raises(FileExistsError):
        with exclusive_demo_session(ledger):
            pytest.fail("stale lock was ignored")
    assert "automatic DEMO session lock present" in ledger_session_blockers(ledger, CONFIG)
    assert lock.read_text(encoding="utf-8") == "prior runner terminated"


def test_watcher_stops_after_passive_scan_then_session_gap(monkeypatch, tmp_path, capsys):
    _env(monkeypatch)
    monkeypatch.setenv("SHREEK_DEMO_AUTO_ACK", "DEMO_ONLY_RESEARCH")
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")
    ledger = tmp_path / "demo.sqlite3"
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: object())
    results = iter((
        DemoAutoResult(False, False, False, "no unique current closed-bar strategy signal"),
        DemoAutoResult(False, False, False, "M5 context has a session gap"),
    ))
    monkeypatch.setattr(mt5_demo_auto_cli, "scan_and_submit_demo", lambda *a, **k: next(results))
    monkeypatch.setattr(mt5_demo_auto_cli.time, "sleep", lambda seconds: None)
    assert mt5_demo_auto_cli.main(["--ledger", str(ledger), "--execute-demo-auto",
                                    "--watch-minutes", "1"]) == 2
    assert len(capsys.readouterr().out.splitlines()) == 2
    session = inspect_sessions(ledger)["sessions"][0]
    assert session["scans"] == 2 and session["end_reason"] == "safety_refusal"
    assert not ledger.with_suffix(".watch.lock").exists()


def test_active_watcher_lock_prevents_any_broker_runtime(monkeypatch, tmp_path, capsys):
    _env(monkeypatch)
    monkeypatch.setenv("SHREEK_DEMO_AUTO_ACK", "DEMO_ONLY_RESEARCH")
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")
    ledger = tmp_path / "demo.sqlite3"
    def forbidden_runtime():
        raise AssertionError("second runner must not reach MT5")
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", forbidden_runtime)
    with exclusive_demo_session(ledger):
        assert mt5_demo_auto_cli.main(["--ledger", str(ledger), "--execute-demo-auto",
                                        "--watch-minutes", "1"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert not result["sent"] and "lock unavailable" in result["reason"]
    assert not ledger.with_suffix(".scans.sqlite3").exists()


def test_opt_in_runner_refuses_corrupt_scan_journal_before_mt5(monkeypatch, tmp_path, capsys):
    _env(monkeypatch)
    monkeypatch.setenv("SHREEK_DEMO_AUTO_ACK", "DEMO_ONLY_RESEARCH")
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")
    ledger = tmp_path / "demo.sqlite3"
    journal = ledger.with_suffix(".scans.sqlite3")
    journal.write_bytes(b"corrupt prior scan journal")
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime",
                        lambda: pytest.fail("local preflight must prevent MT5 access"))
    assert mt5_demo_auto_cli.main(["--ledger", str(ledger), "--execute-demo-auto",
                                    "--watch-minutes", "1"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert not result["sent"] and "local preflight blocked" in result["reason"]
    assert journal.read_bytes() == b"corrupt prior scan journal"
    assert not ledger.with_suffix(".watch.lock").exists()


def test_opt_in_runner_refuses_foreign_ledger_before_mt5(monkeypatch, tmp_path, capsys):
    _env(monkeypatch)
    monkeypatch.setenv("SHREEK_DEMO_AUTO_ACK", "DEMO_ONLY_RESEARCH")
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")
    ledger = tmp_path / "demo.sqlite3"
    assert submit_demo_order(FakeMT5(), CONFIG, ORDER, ledger).accepted
    with sqlite3.connect(ledger) as db:
        db.execute("UPDATE attempts SET account_hash=?",
                   (sha256(b"another-demo-account").hexdigest(),))
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime",
                        lambda: pytest.fail("foreign ledger must prevent MT5 access"))

    assert mt5_demo_auto_cli.main(["--ledger", str(ledger), "--execute-demo-auto",
                                   "--watch-minutes", "1"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert not result["sent"] and "local preflight blocked" in result["reason"]
    assert not ledger.with_suffix(".watch.lock").exists()
    assert not ledger.with_suffix(".scans.sqlite3").exists()


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
    latest.record(DemoAutoResult(True, True, False, "submission uncertain; do not retry",
                                 "a" * 40))
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


@pytest.fixture
def timed_session(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=True, watch_minutes=60)
    for _ in range(2):
        journal.record(DemoAutoResult(False, False, False, "no signal"))
    journal.finish("watch_expired")
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    with sqlite3.connect(journal.path) as db:
        db.execute("UPDATE sessions SET started_at=?, ended_at=?",
                   (start.isoformat(), (start + timedelta(seconds=30)).isoformat()))
        events = db.execute("SELECT event_id FROM scan_events ORDER BY event_id").fetchall()
        for index, (event_id,) in enumerate(events, 1):
            db.execute("UPDATE scan_events SET recorded_at=? WHERE event_id=?",
                       ((start + timedelta(seconds=10 * index)).isoformat(), event_id))
    return ledger, journal, start


@pytest.mark.parametrize("fault", [
    "end_before_start", "scan_before_start", "scan_after_end", "scan_time_reversed",
    "future_session", "future_end", "future_active_scan", "naive_start", "naive_end",
    "naive_scan", "invalid_start", "invalid_scan", "unrepresentable_utc",
])
def test_inconsistent_session_chronology_blocks_report_and_handover(timed_session, fault, capsys):
    ledger, journal, start = timed_session
    with sqlite3.connect(journal.path) as db:
        if fault == "end_before_start":
            db.execute("UPDATE sessions SET ended_at=?", ((start - timedelta(seconds=1)).isoformat(),))
        elif fault in ("scan_before_start", "scan_after_end", "scan_time_reversed"):
            event, seconds = {"scan_before_start": (1, -1), "scan_after_end": (2, 31),
                              "scan_time_reversed": (1, 25)}[fault]
            db.execute("UPDATE scan_events SET recorded_at=? WHERE event_id=?",
                       ((start + timedelta(seconds=seconds)).isoformat(), event))
        elif fault == "future_session":
            future = datetime.now(timezone.utc) + timedelta(days=1)
            db.execute("UPDATE sessions SET started_at=?, ended_at=?",
                       (future.isoformat(), (future + timedelta(seconds=30)).isoformat()))
            db.execute("UPDATE scan_events SET recorded_at=?", ((future + timedelta(seconds=10)).isoformat(),))
        elif fault == "future_end":
            db.execute("UPDATE sessions SET ended_at=?",
                       ((datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),))
        elif fault == "future_active_scan":
            db.execute("UPDATE sessions SET ended_at=NULL, end_reason=NULL")
            db.execute("UPDATE scan_events SET recorded_at=? WHERE event_id=2",
                       ((datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),))
        elif fault in ("naive_start", "naive_end"):
            column = "started_at" if fault == "naive_start" else "ended_at"
            db.execute(f"UPDATE sessions SET {column}=?", (start.replace(tzinfo=None).isoformat(),))
        elif fault == "naive_scan":
            db.execute("UPDATE scan_events SET recorded_at=? WHERE event_id=1",
                       ((start + timedelta(seconds=10)).replace(tzinfo=None).isoformat(),))
        elif fault == "invalid_start":
            db.execute("UPDATE sessions SET started_at='private-timestamp-details'")
        elif fault == "invalid_scan":
            db.execute("UPDATE scan_events SET recorded_at='private-timestamp-details' WHERE event_id=1")
        else:
            db.execute("UPDATE sessions SET started_at='0001-01-01T00:00:00+14:00'")
    before = journal.path.read_bytes()
    with pytest.raises(ValueError):
        inspect_sessions(ledger)
    assert report_main(["--ledger", str(ledger)]) == 2
    printed = capsys.readouterr().out
    report = json.loads(printed)
    assert report["journal_readable"] is False
    assert "private-timestamp-details" not in printed
    envelope = {"independent_broker_export_verified": False,
                "local_sessions": {"exit_code": 2, "report": report},
                "broker_history": {"exit_code": 0, "report": {"verified_demo": True, "attempts": []}}}
    assert assess_handover(envelope)["state"] == "blocked"
    assert journal.path.read_bytes() == before and not ledger.exists()


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("same_scan_instant", [False, True])
def test_valid_session_chronology_normalizes_offsets_without_changing_journal(
        timed_session, completed, same_scan_instant):
    ledger, journal, start = timed_session
    first = start + timedelta(seconds=10)
    second = first if same_scan_instant else start + timedelta(seconds=20)
    with sqlite3.connect(journal.path) as db:
        db.execute("UPDATE sessions SET started_at=?, ended_at=?, end_reason=?",
                   (start.astimezone(timezone(timedelta(hours=3))).isoformat(),
                    (start + timedelta(seconds=30)).astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()
                    if completed else None, "watch_expired" if completed else None))
        db.execute("UPDATE scan_events SET recorded_at=? WHERE event_id=1",
                   (first.astimezone(timezone(timedelta(hours=-8))).isoformat(),))
        db.execute("UPDATE scan_events SET recorded_at=? WHERE event_id=2",
                   (second.isoformat().replace("+00:00", "Z"),))
    before = journal.path.read_bytes()
    report = inspect_sessions(ledger)
    session, = report["sessions"]
    assert report["journal_readable"] is True
    assert session["scans"] == 2 and session["end_recorded"] is completed
    assert session["submission_observations"] == session["accepted_observations"] == 0
    assert journal.path.read_bytes() == before and not ledger.exists()


@pytest.fixture
def metadata_session(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=True, watch_minutes=60)
    journal.record(DemoAutoResult(False, False, False, "no signal"))
    journal.finish("watch_expired")
    return ledger, journal


@pytest.mark.parametrize("fault", [
    "invalid_session_id", "non_boolean_execute", "text_execute", "negative_watch",
    "excessive_watch", "text_watch", "passive_watch", "invalid_end_reason",
    "missing_end_reason", "dangling_end_reason",
])
def test_invalid_session_metadata_blocks_report_without_disclosure(metadata_session, fault, capsys):
    ledger, journal = metadata_session
    with sqlite3.connect(journal.path) as db:
        if fault == "invalid_session_id":
            db.execute("UPDATE sessions SET session_id='private-session-details'")
        elif fault == "non_boolean_execute":
            db.execute("UPDATE sessions SET execute_requested=2")
        elif fault == "text_execute":
            db.execute("UPDATE sessions SET execute_requested='private-session-details'")
        elif fault == "negative_watch":
            db.execute("UPDATE sessions SET watch_minutes=-1")
        elif fault == "excessive_watch":
            db.execute("UPDATE sessions SET watch_minutes=61")
        elif fault == "text_watch":
            db.execute("UPDATE sessions SET watch_minutes='private-session-details'")
        elif fault == "passive_watch":
            db.execute("UPDATE sessions SET execute_requested=0, watch_minutes=1")
        elif fault == "invalid_end_reason":
            db.execute("UPDATE sessions SET end_reason='private-session-details'")
        elif fault == "missing_end_reason":
            db.execute("UPDATE sessions SET end_reason=NULL")
        else:
            db.execute("UPDATE sessions SET ended_at=NULL, end_reason='private-session-details'")
    before = journal.path.read_bytes()
    with pytest.raises(ValueError):
        inspect_sessions(ledger)
    assert report_main(["--ledger", str(ledger)]) == 2
    printed = capsys.readouterr().out
    report = json.loads(printed)
    assert report["journal_readable"] is False
    assert "private-session-details" not in printed
    envelope = {"independent_broker_export_verified": False,
                "local_sessions": {"exit_code": 2, "report": report},
                "broker_history": {"exit_code": 2, "report": {
                    "verified_demo": False, "attempts": [],
                    "reason": "durable DEMO ledger unavailable"}}}
    assert assess_handover(envelope)["state"] == "blocked"
    assert journal.path.read_bytes() == before and not ledger.exists()


@pytest.mark.parametrize("execute,minutes,completed,reason", [
    (False, 0, True, "scan_complete"),
    (True, 0, True, "scan_complete"),
    (True, 60, True, "watch_expired"),
    (True, 60, False, None),
])
def test_valid_session_metadata_remains_readable_and_unchanged(
        tmp_path, execute, minutes, completed, reason):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=execute, watch_minutes=minutes)
    journal.record(DemoAutoResult(False, False, False, "no signal"))
    if completed:
        journal.finish(reason)
    before = journal.path.read_bytes()
    session, = inspect_sessions(ledger)["sessions"]
    assert session["execute_requested"] is execute
    assert session["watch_minutes"] == minutes
    assert session["end_recorded"] is completed and session["end_reason"] == reason
    assert journal.path.read_bytes() == before and not ledger.exists()


@pytest.mark.parametrize("fault", [
    "accepted_without_sent", "sent_without_signal", "signal_id_without_signal",
    "missing_signal_id", "object_signal_id", "non_hex_signal_id",
    "order_without_acceptance", "missing_accepted_order", "object_order",
    "nonpositive_order", "empty_reason", "overlong_reason", "control_reason",
])
def test_invalid_scan_outcome_blocks_report_without_disclosure(metadata_session, fault, capsys):
    ledger, journal = metadata_session
    signal_id = "a" * 40
    with sqlite3.connect(journal.path) as db:
        event_id, raw = db.execute(
            "SELECT event_id, result_json FROM scan_events ORDER BY event_id LIMIT 1"
        ).fetchone()
        result = json.loads(raw)
        if fault == "accepted_without_sent":
            result.update(signal_detected=True, sent=False, accepted=True,
                          signal_id=signal_id, broker_order_id=123)
        elif fault == "sent_without_signal":
            result.update(signal_detected=False, sent=True)
        elif fault == "signal_id_without_signal":
            result["signal_id"] = signal_id
        elif fault == "missing_signal_id":
            result["signal_detected"] = True
        elif fault == "object_signal_id":
            result.update(signal_detected=True,
                          signal_id={"private": "private-result-details"})
        elif fault == "non_hex_signal_id":
            result.update(signal_detected=True, signal_id="not-a-strategy-signal")
        elif fault == "order_without_acceptance":
            result["broker_order_id"] = 123
        elif fault in ("missing_accepted_order", "object_order", "nonpositive_order"):
            order = {"missing_accepted_order": None,
                     "object_order": {"private": "private-result-details"},
                     "nonpositive_order": 0}[fault]
            result.update(signal_detected=True, sent=True, accepted=True,
                          signal_id=signal_id, broker_order_id=order)
        elif fault == "empty_reason":
            result["reason"] = ""
        elif fault == "overlong_reason":
            result["reason"] = "private-result-details" * 10
        else:
            result["reason"] = "private-result-details\nsecond-line"
        db.execute("UPDATE scan_events SET result_json=? WHERE event_id=?",
                   (json.dumps(result), event_id))
    before = journal.path.read_bytes()
    with pytest.raises(ValueError):
        inspect_sessions(ledger)
    assert report_main(["--ledger", str(ledger)]) == 2
    printed = capsys.readouterr().out
    report = json.loads(printed)
    assert report["journal_readable"] is False
    assert "private-result-details" not in printed
    envelope = {"independent_broker_export_verified": False,
                "local_sessions": {"exit_code": 2, "report": report},
                "broker_history": {"exit_code": 2, "report": {
                    "verified_demo": False, "attempts": [],
                    "reason": "durable DEMO ledger unavailable"}}}
    assert assess_handover(envelope)["state"] == "blocked"
    assert journal.path.read_bytes() == before and not ledger.exists()


@pytest.mark.parametrize("result", [
    DemoAutoResult(False, False, False, "no unique current closed-bar strategy signal"),
    DemoAutoResult(True, False, False, "automatic DEMO execution disabled", "a" * 40),
    DemoAutoResult(True, True, False, "DEMO submission uncertain; do not retry", "a" * 40),
    DemoAutoResult(True, True, True, "DEMO broker acknowledged; reconcile independently",
                   "a" * 40, 123),
])
def test_valid_scan_outcome_shapes_remain_readable_and_unchanged(tmp_path, result):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=True, watch_minutes=0)
    journal.record(result)
    journal.finish("submission_attempted" if result.sent else "scan_complete")
    before = journal.path.read_bytes()
    session, = inspect_sessions(ledger)["sessions"]
    expected = asdict(result)
    expected.pop("strategy_diagnostics")
    assert session["last_result"] == expected
    assert session["signals"] == int(result.signal_detected)
    assert session["submission_observations"] == int(result.sent)
    assert session["accepted_observations"] == int(result.accepted)
    assert journal.path.read_bytes() == before and not ledger.exists()


@pytest.mark.parametrize("fault", [
    "hidden_submission", "escaped_sent", "same_sent", "hidden_reason",
    "hidden_signal_id", "diagnostic_counter", "nested_diagnostic_counter",
])
def test_duplicate_json_fields_block_session_report_and_handover(tmp_path, fault, capsys):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=True, watch_minutes=1)
    journal.record(DemoAutoResult(False, False, False, "no signal",
                                  strategy_diagnostics=_diagnostics()))
    journal.finish("watch_expired")
    with sqlite3.connect(journal.path) as db:
        event_id, raw = db.execute("SELECT event_id, result_json FROM scan_events").fetchone()
        if fault == "hidden_submission":
            earlier = dict(signal_detected=True, sent=True, accepted=True,
                           reason="accepted", signal_id="a" * 40, broker_order_id=123)
            ambiguous = json.dumps(earlier)[:-1] + "," + raw[1:]
        elif fault == "escaped_sent":
            ambiguous = raw[:-1] + ',"\\u0073ent":true,"sent":false}'
        elif fault == "same_sent":
            ambiguous = raw[:-1] + ',"sent":false}'
        elif fault == "hidden_reason":
            ambiguous = raw[:-1] + ',"reason":"private-json-details","reason":"no signal"}'
        elif fault == "hidden_signal_id":
            ambiguous = raw[:-1] + ',"signal_id":{"private":"private-json-details"},"signal_id":null}'
        else:
            diagnostic = db.execute(
                "SELECT diagnostics_json FROM strategy_scan_diagnostics WHERE event_id=?", (event_id,)
            ).fetchone()[0]
            if fault == "diagnostic_counter":
                ambiguous_diagnostic = diagnostic[:-1] + ',"candidates":4}'
            else:
                ambiguous_diagnostic = diagnostic.replace(
                    '"consolidation_range": 4', '"consolidation_range": 0,"consolidation_range":4')
            assert ambiguous_diagnostic != diagnostic
            db.execute("UPDATE strategy_scan_diagnostics SET diagnostics_json=? WHERE event_id=?",
                       (ambiguous_diagnostic, event_id))
            ambiguous = raw
        db.execute("UPDATE scan_events SET result_json=? WHERE event_id=?", (ambiguous, event_id))
    before = journal.path.read_bytes()
    with pytest.raises(ValueError):
        inspect_sessions(ledger)
    assert report_main(["--ledger", str(ledger)]) == 2
    printed = capsys.readouterr().out
    report = json.loads(printed)
    assert report["journal_readable"] is False and report["broker_history_verified"] is False
    assert "private-json-details" not in printed
    envelope = {"independent_broker_export_verified": False,
                "local_sessions": {"exit_code": 2, "report": report},
                "broker_history": {"exit_code": 2, "report": {
                    "verified_demo": False, "attempts": [],
                    "reason": "durable DEMO ledger unavailable"}}}
    assert assess_handover(envelope)["state"] == "blocked"
    assert journal.path.read_bytes() == before and not ledger.exists()


@pytest.mark.parametrize("with_diagnostics", [False, True])
def test_unique_json_fields_remain_readable_in_any_key_order(tmp_path, with_diagnostics):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=True, watch_minutes=1)
    journal.record(DemoAutoResult(False, False, False, "no signal",
                                  strategy_diagnostics=_diagnostics() if with_diagnostics else None))
    journal.finish("watch_expired")
    with sqlite3.connect(journal.path) as db:
        event_id, raw = db.execute("SELECT event_id, result_json FROM scan_events").fetchone()
        result = json.loads(raw)
        db.execute("UPDATE scan_events SET result_json=? WHERE event_id=?",
                   (json.dumps(dict(reversed(list(result.items())))), event_id))
        if with_diagnostics:
            diagnostic = db.execute(
                "SELECT diagnostics_json FROM strategy_scan_diagnostics WHERE event_id=?", (event_id,)
            ).fetchone()[0]
            counters = json.loads(diagnostic)
            db.execute("UPDATE strategy_scan_diagnostics SET diagnostics_json=? WHERE event_id=?",
                       (json.dumps(dict(reversed(list(counters.items())))), event_id))
    before = journal.path.read_bytes()
    report = inspect_sessions(ledger)
    session, = report["sessions"]
    assert report["journal_readable"] is True and session["last_result"] == result
    assert session["submission_observations"] == session["accepted_observations"] == 0
    if with_diagnostics:
        assert session["last_strategy_diagnostics"]["counters"] == _diagnostics()
    else:
        assert session["last_strategy_diagnostics"] is None
    assert journal.path.read_bytes() == before and not ledger.exists()


def test_legacy_journal_is_readable_and_migrates_without_claiming_session_end(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    path = ledger.with_suffix(".scans.sqlite3")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, "
                   "execute_requested INTEGER NOT NULL, watch_minutes INTEGER NOT NULL)")
        db.execute("CREATE TABLE scan_events (event_id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, "
                   "recorded_at TEXT NOT NULL, result_json TEXT NOT NULL)")
        db.execute("INSERT INTO sessions VALUES (?, '2026-09-29T20:00:00+00:00', 0, 0)",
                   ("a" * 32,))
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
                        DemoAutoResult(True, True, True, "accepted", "a" * 40, 123))
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
                        DemoAutoResult(sent, sent, accepted, "observed",
                                       "a" * 40 if sent else None,
                                       123 if accepted else None))
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
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")
    ledger = tmp_path / "demo.sqlite3"
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: object())
    monkeypatch.setattr(mt5_demo_auto_cli, "scan_and_submit_demo", lambda *a, **k:
                        DemoAutoResult(False, False, False, "no unique current closed-bar strategy signal"))
    ticks = iter((0, 61))
    monkeypatch.setattr(mt5_demo_auto_cli.time, "monotonic", lambda: next(ticks))
    def unexpected(*a):
        raise AssertionError("expired watcher must not sleep")
    monkeypatch.setattr(mt5_demo_auto_cli.time, "sleep", unexpected)
    assert mt5_demo_auto_cli.main(["--ledger", str(ledger), "--execute-demo-auto", "--watch-minutes", "1"]) == 2
    assert inspect_sessions(ledger)["sessions"][0]["end_reason"] == "watch_expired"


def _diagnostics():
    return dict(schema="shreek.strategy-diagnostics.v1", candidates=4,
                valid_breakouts=0, returned_signals=0,
                rejected={"consolidation_range": 4})


def test_strategy_diagnostics_survive_later_stale_scan_and_remain_read_only(tmp_path):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=True, watch_minutes=60)
    diagnostic = _diagnostics()
    diagnostic["unknown_private_field"] = "must not persist"
    journal.record(DemoAutoResult(False, False, False, "no unique current closed-bar strategy signal",
                                  strategy_diagnostics=diagnostic))
    journal.record(DemoAutoResult(False, False, False,
                                  "last completed M5 candle is stale or not yet closed"))
    before = journal.path.read_bytes()
    report = inspect_sessions(ledger)["sessions"][0]
    assert report["last_strategy_diagnostics"]["counters"] == _diagnostics()
    assert report["scans"] == 2 and report["submission_observations"] == 0
    assert "strategy_diagnostics" not in report["last_result"]
    assert "must not persist" not in json.dumps(report)
    assert journal.path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("candidates", True), ("valid_breakouts", -1),
                                         ("returned_signals", 5),
                                         ("rejected", {"account_secret": 1})])
def test_invalid_diagnostics_do_not_write_partial_scan(tmp_path, field, value):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=True, watch_minutes=60)
    diagnostic = _diagnostics()
    diagnostic[field] = value
    with pytest.raises(ValueError):
        journal.record(DemoAutoResult(False, False, False, "no signal",
                                      strategy_diagnostics=diagnostic))
    assert inspect_sessions(ledger)["sessions"][0]["scans"] == 0


def test_corrupt_strategy_diagnostics_block_report(tmp_path, capsys):
    ledger = tmp_path / "demo.sqlite3"
    journal = DemoSessionJournal(ledger, execute=True, watch_minutes=60)
    journal.record(DemoAutoResult(False, False, False, "no signal",
                                  strategy_diagnostics=_diagnostics()))
    with sqlite3.connect(journal.path) as db:
        db.execute("UPDATE strategy_scan_diagnostics SET diagnostics_json='{}'")
    assert report_main(["--ledger", str(ledger)]) == 2
    assert not json.loads(capsys.readouterr().out)["journal_readable"]
