"""Interpret read-only DEMO reports without certifying execution or research."""
from __future__ import annotations

from typing import Any


def assess_handover(envelope: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on missing, conflicting or unlinked session observations.

    A broker-history match is still local observational evidence. An external
    broker export and human review remain separate release prerequisites.
    """
    def result(state: str, reason: str) -> dict[str, Any]:
        return {"state": state, "reason": reason,
                "independent_broker_export_verified": False,
                "paper_trading_validated": False}

    if not isinstance(envelope, dict) or envelope.get("independent_broker_export_verified") is not False:
        return result("blocked", "independent export state is invalid")
    local = envelope.get("local_sessions")
    broker = envelope.get("broker_history")
    if not isinstance(local, dict) or not isinstance(broker, dict):
        return result("blocked", "both read-only reports are required")
    if type(local.get("exit_code")) is not int or type(broker.get("exit_code")) is not int:
        return result("blocked", "report exit status is malformed")
    if local["exit_code"] != 0 or broker["exit_code"] != 0:
        return result("blocked", "local session or broker history is unavailable")
    sessions = local.get("report")
    history = broker.get("report")
    if (not isinstance(sessions, dict) or sessions.get("journal_readable") is not True
            or not isinstance(sessions.get("sessions"), list)
            or not isinstance(history, dict) or history.get("verified_demo") is not True
            or not isinstance(history.get("attempts"), list)):
        return result("blocked", "DEMO reports are malformed or unverified")
    if not sessions["sessions"] or not isinstance(sessions["sessions"][0], dict):
        return result("blocked", "no recorded DEMO session")
    current = sessions["sessions"][0]
    if (current.get("end_recorded") is not True
            or current.get("end_reason") not in ("scan_complete", "watch_expired", "submission_attempted")
            or current.get("execute_requested") is not True):
        return result("blocked", "latest DEMO watcher did not end cleanly")
    counts = ("scans", "signals", "submission_observations", "accepted_observations")
    if any(type(current.get(key)) is not int or current[key] < 0 for key in counts):
        return result("blocked", "session counters are malformed")
    scans, signals, sent, accepted = (current[key] for key in counts)
    if scans < 1 or not 0 <= accepted <= sent <= signals <= scans:
        return result("blocked", "session observations contradict each other")
    last = current.get("last_result")
    if (not isinstance(last, dict) or type(last.get("signal_detected")) is not bool
            or type(last.get("sent")) is not bool or type(last.get("accepted")) is not bool):
        return result("blocked", "last scan observation is malformed")
    if sent == 0:
        if (signals != 0 or last["signal_detected"] or last["sent"] or last["accepted"]
                or current["end_reason"] not in ("scan_complete", "watch_expired")):
            return result("blocked", "a signal or safety refusal needs inspection")
        return result("observation_only", "no DEMO order was submitted in the latest session")
    if (sent != 1 or accepted != 1 or current["end_reason"] != "submission_attempted"
            or last["signal_detected"] is not True
            or last["sent"] is not True or last["accepted"] is not True
            or not isinstance(last.get("signal_id"), str) or not last["signal_id"]
            or type(last.get("broker_order_id")) is not int or last["broker_order_id"] <= 0):
        return result("blocked", "submitted order outcome needs reconciliation")
    matches = [attempt for attempt in history["attempts"]
               if isinstance(attempt, dict) and attempt.get("intent_id") == last["signal_id"]]
    if (len(matches) != 1 or matches[0].get("broker_order_id") != last["broker_order_id"]
            or matches[0].get("local_source_kind") != "strategy_experiment"
            or matches[0].get("status") not in ("open_or_partial", "closed_observed")
            or not isinstance(matches[0].get("broker_deals"), list)
            or not matches[0]["broker_deals"]):
        return result("blocked", "latest submitted intent is not matched to observed broker deals")
    return result("manual_review_required", "local broker match needs independent export and review")
