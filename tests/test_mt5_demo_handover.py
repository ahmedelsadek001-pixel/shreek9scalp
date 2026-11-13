"""No local observation can certify broker fills or research performance."""
from copy import deepcopy

from execution.mt5_demo_handover import assess_handover


def _report():
    return {
        "independent_broker_export_verified": False,
        "local_sessions": {"exit_code": 0, "report": {
            "journal_readable": True, "sessions": [{
                "execute_requested": True, "end_recorded": True,
                "end_reason": "watch_expired", "scans": 3, "signals": 0,
                "submission_observations": 0, "accepted_observations": 0,
                "last_result": {"signal_detected": False, "sent": False,
                                "accepted": False, "signal_id": None,
                                "broker_order_id": None},
            }],
        }},
        "broker_history": {"exit_code": 0, "report": {
            "verified_demo": True, "attempts": [],
        }},
    }


def _submitted():
    report = _report()
    session = report["local_sessions"]["report"]["sessions"][0]
    session.update(end_reason="submission_attempted", scans=1, signals=1,
                   submission_observations=1, accepted_observations=1,
                   last_result={"signal_detected": True, "sent": True,
                                "accepted": True, "signal_id": "signal-1",
                                "broker_order_id": 123})
    report["broker_history"]["report"]["attempts"] = [{
        "intent_id": "signal-1", "broker_order_id": 123,
        "local_source_kind": "strategy_experiment", "status": "open_or_partial",
        "broker_deals": [{"ticket": 456}],
    }]
    return report


def test_completed_no_signal_session_is_observation_only():
    decision = assess_handover(_report())
    assert decision["state"] == "observation_only"
    assert decision["independent_broker_export_verified"] is False
    assert decision["paper_trading_validated"] is False


def test_local_broker_match_still_needs_independent_review():
    decision = assess_handover(_submitted())
    assert decision["state"] == "manual_review_required"
    assert decision["paper_trading_validated"] is False


def test_mismatched_intent_or_order_never_becomes_observed_fill():
    for field, value in (("intent_id", "other-signal"), ("broker_order_id", 124),
                         ("local_source_kind", "manual_sandbox"),
                         ("status", "opening_not_verified"), ("broker_deals", [])):
        report = _submitted()
        report["broker_history"]["report"]["attempts"][0][field] = value
        assert assess_handover(report)["state"] == "blocked"
    report = _submitted()
    duplicate = deepcopy(report["broker_history"]["report"]["attempts"][0])
    duplicate["broker_order_id"] = 999
    report["broker_history"]["report"]["attempts"].append(duplicate)
    assert assess_handover(report)["state"] == "blocked"


def test_incomplete_or_contradictory_session_fails_closed():
    for field, value in (("end_recorded", False), ("end_reason", "journal_error"),
                         ("scans", 0), ("signals", True),
                         ("accepted_observations", 1), ("execute_requested", False)):
        report = _report()
        report["local_sessions"]["report"]["sessions"][0][field] = value
        assert assess_handover(report)["state"] == "blocked"


def test_sent_but_unknown_outcome_is_blocked():
    report = _submitted()
    session = report["local_sessions"]["report"]["sessions"][0]
    session["accepted_observations"] = 0
    session["last_result"]["accepted"] = False
    assert assess_handover(report)["state"] == "blocked"


def test_unavailable_broker_history_or_claimed_export_is_blocked():
    report = _report()
    report["broker_history"]["exit_code"] = 2
    assert assess_handover(report)["state"] == "blocked"
    report = deepcopy(_submitted())
    report["independent_broker_export_verified"] = True
    assert assess_handover(report)["state"] == "blocked"


def _missing_ledger(report):
    report["broker_history"] = {"exit_code": 2, "report": {
        "reason": "durable DEMO ledger unavailable", "verified_demo": False, "attempts": []}}
    return report


def test_clean_no_submission_with_missing_ledger_is_explicitly_local_only():
    decision = assess_handover(_missing_ledger(_report()))
    assert decision["state"] == "local_observation_only"
    assert "unverified" in decision["reason"]
    assert not decision["paper_trading_validated"]
    assert not decision["independent_broker_export_verified"]


def test_missing_ledger_never_explains_away_submitted_or_uncertain_order():
    assert assess_handover(_missing_ledger(_submitted()))["state"] == "blocked"
    for field, value in (("end_reason", "safety_refusal"), ("end_recorded", False),
                         ("signals", 1), ("submission_observations", 1)):
        report = _missing_ledger(_report())
        report["local_sessions"]["report"]["sessions"][0][field] = value
        assert assess_handover(report)["state"] == "blocked"
    for field, value in (("signal_id", "unresolved"), ("broker_order_id", 123)):
        report = _missing_ledger(_report())
        report["local_sessions"]["report"]["sessions"][0]["last_result"][field] = value
        assert assess_handover(report)["state"] == "blocked"


def test_other_broker_failures_are_not_classified_as_missing_ledger():
    for field, value in (("reason", "DEMO account changed or disconnected"),
                         ("verified_demo", True), ("attempts", [{}])):
        report = _missing_ledger(_report())
        report["broker_history"]["report"][field] = value
        assert assess_handover(report)["state"] == "blocked"
