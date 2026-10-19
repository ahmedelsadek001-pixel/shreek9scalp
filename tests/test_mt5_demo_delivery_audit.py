"""Saved report correlation cannot become terminal or release authority."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys

import pytest

from execution import mt5_demo_delivery_audit_cli as audit
from execution.mt5_demo_handover import assess_handover


SHA = "a" * 40
NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)


def _reports():
    scan = {"signal_detected": False, "sent": False, "accepted": False,
            "reason": "no unique current closed-bar strategy signal",
            "signal_id": None, "broker_order_id": None}
    doctor = {"schema": "shreek.demo-bootstrap.v1", "ready_to_prepare": True,
              "runtime_present": True, "reason": None,
              "available_free_mib": 3077, "required_free_mib": 64}
    preflight = {
        "connected_demo": True, "ready_for_demo_attempt": True,
        "ready_for_demo_session": True, "session_blockers": [],
        "probe": {"connected_demo": True, "terminal_trade_allowed": True,
                  "order_transport_enabled": False, "symbol": "XAUUSD.s"},
        "readiness": {"ready_for_demo_attempt": True, "order_transport_enabled": False,
                      "blockers": [], "symbol": "XAUUSD.s", "observed_filling_policy": "FOK",
                      "observed_tick_utc_offset_seconds": 10800},
        "strategy_scan": deepcopy(scan),
    }
    session = {"journal_readable": True, "broker_history_verified": False, "sessions": [{
        "session_id": "b" * 32, "started_at": "2026-10-09T11:00:00Z",
        "last_scan_at": "2026-10-09T11:59:00Z", "ended_at": "2026-10-09T12:00:00Z",
        "execute_requested": True, "end_recorded": True, "end_reason": "watch_expired",
        "scans": 121, "signals": 0, "submission_observations": 0,
        "accepted_observations": 0, "last_result": scan,
    }]}
    handover = {"schema": "shreek.demo-handover.v1", "independent_broker_export_verified": False,
                "local_sessions": {"exit_code": 0, "report": session},
                "broker_history": {"exit_code": 0, "report": {"verified_demo": True, "attempts": []}}}
    return doctor, preflight, session, handover


def _decision(reports=None):
    return audit.audit_delivery_reports(SHA, *(reports or _reports()), now=NOW)


def test_no_signal_reports_are_reviewable_without_any_acceptance_or_source_claim():
    result = _decision()
    assert result["state"] == "local_evidence_reviewable"
    assert result["session_counts"]["scans"] == 121
    assert result["historical_preflight_only"] is True
    assert "broker_order_execution_evidence" in result["remaining_evidence"]
    for flag in ("candidate_source_verified", "independent_broker_export_verified",
                 "paper_trading_validated", "demo_delivery_accepted", "order_transport_enabled",
                 "release_authorized", "live_authorized"):
        assert result[flag] is False
    assert len(result["canonical_report_sha256"]) == 4
    assert all(len(value) == 64 for value in result["canonical_report_sha256"].values())


@pytest.mark.parametrize("candidate", ["main", "A" * 40, "a" * 39, "g" * 40, True])
def test_candidate_commit_label_must_be_exact(candidate):
    result = audit.audit_delivery_reports(candidate, *_reports(), now=NOW)
    assert result["state"] == "blocked"
    assert result["candidate_commit_sha"] is None


@pytest.mark.parametrize("field,value", [
    ("ready_to_prepare", False), ("runtime_present", False),
    ("required_free_mib", True), ("required_free_mib", 0), ("available_free_mib", 63),
])
def test_doctor_refusal_and_contradictory_disk_reports_block(field, value):
    reports = _reports()
    reports[0][field] = value
    assert _decision(reports)["state"] == "blocked"


@pytest.mark.parametrize("change", ["outer_ready", "session_blocker", "probe_transport",
                                     "terminal_permission", "nested_blocker", "symbol", "offset_bool", "sent"])
def test_preflight_cannot_hide_a_nested_refusal_or_submission(change):
    reports = _reports()
    preflight = reports[1]
    if change == "outer_ready":
        preflight["ready_for_demo_session"] = False
    elif change == "session_blocker":
        preflight["session_blockers"] = ["stop file active"]
    elif change == "probe_transport":
        preflight["probe"]["order_transport_enabled"] = True
    elif change == "terminal_permission":
        preflight["probe"]["terminal_trade_allowed"] = False
    elif change == "nested_blocker":
        preflight["readiness"]["blockers"] = ["stale quote"]
    elif change == "symbol":
        preflight["readiness"]["symbol"] = "other"
    elif change == "offset_bool":
        preflight["readiness"]["observed_tick_utc_offset_seconds"] = False
    else:
        preflight["strategy_scan"]["sent"] = True
    assert _decision(reports)["state"] == "blocked"


def test_different_session_snapshot_is_rejected_even_if_both_individually_look_clean():
    reports = _reports()
    reports[3]["local_sessions"]["report"] = deepcopy(reports[2])
    reports[3]["local_sessions"]["report"]["sessions"][0]["session_id"] = "c" * 32
    assert _decision(reports)["state"] == "blocked"


@pytest.mark.parametrize("field,value", [
    ("started_at", "2026-10-09T12:00:01Z"), ("last_scan_at", "2026-10-09T12:00:01Z"),
    ("ended_at", "2026-10-09T12:00:01Z"), ("ended_at", "2026-10-09T12:00:00"),
    ("session_id", "private account text"),
])
def test_latest_session_chronology_and_identity_are_required(field, value):
    reports = _reports()
    reports[2]["sessions"][0][field] = value
    result = _decision(reports)
    assert result["state"] == "blocked"
    assert "private account text" not in json.dumps(result)


def test_session_age_limit_and_explicit_timezone_boundary():
    reports = _reports()
    reports[2]["sessions"][0]["ended_at"] = "2026-10-09T14:00:00+02:00"
    assert _decision(reports)["state"] == "local_evidence_reviewable"
    assert audit.audit_delivery_reports(SHA, *reports, now=NOW + timedelta(hours=24))["state"] == "local_evidence_reviewable"
    assert audit.audit_delivery_reports(SHA, *reports, now=NOW + timedelta(hours=24, microseconds=1))["state"] == "blocked"


def test_unknown_submission_and_fabricated_retained_approval_are_blocked():
    reports = _reports()
    reports[2]["sessions"][0]["end_reason"] = "safety_refusal"
    assert _decision(reports)["state"] == "blocked"
    reports = _reports()
    reports[3]["handover_assessment"] = {"state": "approved", "paper_trading_validated": True}
    assert _decision(reports)["state"] == "blocked"


def test_missing_ledger_preserves_local_only_status_and_unknown_broker_history():
    reports = _reports()
    reports[3]["broker_history"] = {"exit_code": 2, "report": {
        "reason": "durable DEMO ledger unavailable", "verified_demo": False, "attempts": []}}
    assert _decision(reports)["state"] == "local_observation_only"
    assert _decision(reports)["independent_broker_export_verified"] is False


def test_submitted_local_match_still_requires_independent_review():
    reports = _reports()
    latest = reports[2]["sessions"][0]
    latest.update(signals=1, submission_observations=1, accepted_observations=1,
                  end_reason="submission_attempted", last_result={
                      "signal_detected": True, "sent": True, "accepted": True,
                      "reason": "DEMO accepted", "signal_id": "d" * 40, "broker_order_id": 123})
    reports[3]["broker_history"]["report"]["attempts"] = [{
        "intent_id": "d" * 40, "broker_order_id": 123, "local_source_kind": "strategy_experiment",
        "status": "closed_observed", "broker_deals": [{"ticket": 456}]}]
    reports[3]["handover_assessment"] = assess_handover(reports[3])
    result = _decision(reports)
    assert result["handover_state"] == "manual_review_required"
    assert result["demo_delivery_accepted"] is False
    assert "independent_broker_export_and_reconciliation" in result["remaining_evidence"]


def _saved_reports(tmp_path, encoding="utf-8"):
    args = ["--candidate-sha", SHA]
    for label, report in zip(("doctor", "preflight", "session", "report-demo"), _reports()):
        path = tmp_path / (label + ".json")
        path.write_text(json.dumps(report), encoding=encoding)
        args.extend(["--" + label, str(path)])
    return args


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_cli_reads_windows_encodings_without_writing_inputs(tmp_path, monkeypatch, capsys, encoding):
    args = _saved_reports(tmp_path, encoding)
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    original = audit.audit_delivery_reports
    monkeypatch.setattr(audit, "audit_delivery_reports", lambda *a, **k: original(*a, now=NOW))
    assert audit.main(args) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "local_evidence_reviewable"
    assert before == {path: path.read_bytes() for path in tmp_path.iterdir()}


@pytest.mark.parametrize("raw", [
    '{"ready_to_prepare":false,"ready_to_prepare":true}',
    '{"ready_to_prepare":false,"ready_to_\\u0070repare":true}',
    '{"nested":{"x":1,"x":2}}', '{"value":NaN}', '{"value":Infinity}',
    '[{}]', 'private account text',
])
def test_cli_rejects_ambiguous_or_invalid_json_without_echoing_it(tmp_path, capsys, raw):
    args = _saved_reports(tmp_path)
    (tmp_path / "doctor.json").write_text(raw, encoding="utf-8")
    assert audit.main(args) == 2
    output = capsys.readouterr().out
    assert json.loads(output)["state"] == "blocked"
    assert "private account text" not in output and str(tmp_path) not in output


def test_cli_bounds_reads_and_hides_missing_input_details(tmp_path, capsys):
    args = _saved_reports(tmp_path)
    doctor = tmp_path / "doctor.json"
    doctor.write_bytes(b" " * (audit._MAX_REPORT_BYTES + 1))
    assert audit.main(args) == 2
    doctor.unlink()
    assert audit.main(args) == 2
    assert str(tmp_path) not in capsys.readouterr().out


def test_import_does_not_load_broker_transport_or_mt5_in_fresh_interpreter():
    code = '''
import importlib.abc
import sys
class NoBroker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"MetaTrader5", "execution.mt5_demo_transport", "utils.mt5_compat"}:
            raise AssertionError("broker module imported")
sys.meta_path.insert(0, NoBroker())
import execution.mt5_demo_delivery_audit_cli
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
