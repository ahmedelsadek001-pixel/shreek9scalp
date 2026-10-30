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
