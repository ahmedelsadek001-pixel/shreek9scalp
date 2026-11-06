"""Audit saved DEMO delivery reports offline; never grant execution authority."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

from execution.mt5_demo_handover import assess_handover
from execution.mt5_demo_session_report_cli import (
    _unique_json_object, _utc_timestamp, _valid_scan_result,
)


_MAX_REPORT_BYTES = 2 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SESSION = re.compile(r"[0-9a-f]{32}\Z")
_REMAINING = (
    "candidate_source_and_ci_verification", "windows_operator_review",
    "independent_broker_export_and_reconciliation", "causal_oos_and_robustness",
    "sustained_paper_and_shadow", "disconnect_and_recovery_evidence",
    "final_security_review", "human_release_approval",
)


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON value")


def _read_report(path: Path) -> dict:
    # Bound the read before decoding. Windows PowerShell 5 captures can have
    # a UTF-16 BOM; PowerShell 7 commonly writes UTF-8 with or without a BOM.
    with path.open("rb") as stream:
        data = stream.read(_MAX_REPORT_BYTES + 1)
    if len(data) > _MAX_REPORT_BYTES:
        raise ValueError("report size limit")
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    report = json.loads(data.decode(encoding), object_pairs_hook=_unique_json_object,
                        parse_constant=_reject_constant)
    if type(report) is not dict:
        raise ValueError("report object required")
    return report


def audit_delivery_reports(candidate_sha: str, doctor: dict, preflight: dict,
                           session: dict, report_demo: dict,
                           *, now: datetime | None = None) -> dict:
    """Check historical report structure and correlation, not report origin.

    A supplied commit label and content digests cannot prove which program or
    terminal produced the files. Even a reviewable report keeps source, broker,
    paper, delivery and release acceptance false.
    """
    result = {
        "schema": "shreek.demo-delivery-audit.v1", "state": "blocked",
        "reason": "delivery inputs malformed", "candidate_commit_sha": None,
        "canonical_report_sha256": {}, "handover_state": None,
        "session_counts": None, "historical_preflight_only": True,
        "candidate_source_verified": False,
        "independent_broker_export_verified": False,
        "paper_trading_validated": False, "demo_delivery_accepted": False,
        "order_transport_enabled": False, "release_authorized": False,
        "live_authorized": False, "remaining_evidence": list(_REMAINING),
    }

    def blocked(reason: str) -> dict:
        result["reason"] = reason
        return result

    if type(candidate_sha) is not str or _SHA.fullmatch(candidate_sha) is None:
        return result
    result["candidate_commit_sha"] = candidate_sha
    reports = {"doctor": doctor, "preflight": preflight,
               "session": session, "report_demo": report_demo}
    if any(type(value) is not dict for value in reports.values()):
        return result
    try:
        for label, report in reports.items():
            canonical = json.dumps(report, sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode("utf-8")
            result["canonical_report_sha256"][label] = sha256(canonical).hexdigest()
        clock = datetime.now(timezone.utc) if now is None else now
        if type(clock) is not datetime or clock.tzinfo is None or clock.utcoffset() is None:
            return blocked("audit clock invalid")
        clock = clock.astimezone(timezone.utc)
        if (doctor.get("schema") != "shreek.demo-bootstrap.v1"
                or doctor.get("ready_to_prepare") is not True
                or doctor.get("runtime_present") is not True
                or doctor.get("reason") is not None
                or type(doctor.get("required_free_mib")) is not int
                or doctor["required_free_mib"] != 64
                or type(doctor.get("available_free_mib")) is not int
                or doctor["available_free_mib"] < doctor["required_free_mib"]):
            return blocked("doctor report unavailable or contradictory")
        probe, readiness = preflight.get("probe"), preflight.get("readiness")
        scan = preflight.get("strategy_scan")
        if (any(preflight.get(key) is not True for key in (
                "connected_demo", "ready_for_demo_attempt", "ready_for_demo_session"))
                or preflight.get("session_blockers") != []
                or type(probe) is not dict or type(readiness) is not dict
                or probe.get("connected_demo") is not True
                or probe.get("terminal_trade_allowed") is not True
                or probe.get("order_transport_enabled") is not False
                or readiness.get("ready_for_demo_attempt") is not True
                or readiness.get("order_transport_enabled") is not False
                or readiness.get("blockers") != []
                or type(probe.get("symbol")) is not str or not probe["symbol"]
                or probe["symbol"] != readiness.get("symbol")
                or type(readiness.get("observed_tick_utc_offset_seconds")) is not int
                or readiness["observed_tick_utc_offset_seconds"] not in (0, 10800)
                or readiness.get("observed_filling_policy") not in ("FOK", "IOC", "FOK+IOC")
                or not _valid_scan_result(scan) or scan["sent"] or scan["accepted"]):
            return blocked("preflight report refused or contradictory")
        local = report_demo.get("local_sessions")
        if (report_demo.get("schema") != "shreek.demo-handover.v1"
                or type(local) is not dict or local.get("report") != session
                or session.get("journal_readable") is not True
                or session.get("broker_history_verified") is not False):
            return blocked("session and report-demo snapshots do not match")
        sessions = session.get("sessions")
        if type(sessions) is not list or not sessions or type(sessions[0]) is not dict:
            return blocked("latest session unavailable")
        latest = sessions[0]
        session_id = latest.get("session_id")
        if (type(session_id) is not str or _SESSION.fullmatch(session_id) is None
                or not _valid_scan_result(latest.get("last_result"))):
            return blocked("latest session identity or scan invalid")
        started = _utc_timestamp(latest.get("started_at"))
        scanned = _utc_timestamp(latest.get("last_scan_at"))
        ended = _utc_timestamp(latest.get("ended_at"))
        if not started <= scanned <= ended <= clock or clock - ended > timedelta(hours=24):
            return blocked("latest session chronology invalid or older than 24 hours")
        assessment = assess_handover(report_demo)
        state = assessment["state"]
        result["handover_state"] = state
        if ("handover_assessment" in report_demo
                and report_demo["handover_assessment"] != assessment):
            return blocked("retained handover assessment contradicts recomputed reports")
        if state not in ("observation_only", "local_observation_only", "manual_review_required"):
            return blocked("handover requires inspection or reconciliation")
        result["session_counts"] = {key: latest[key] for key in (
            "scans", "signals", "submission_observations", "accepted_observations")}
        if latest["submission_observations"] == 0:
            result["remaining_evidence"].append("broker_order_execution_evidence")
        result.update(state="local_evidence_reviewable", reason="saved reports ready for local review")
        if state == "local_observation_only":
            result.update(state="local_observation_only",
                          reason="local no-submission evidence; broker history unavailable")
        return result
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        return blocked("delivery reports malformed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True,
                        help="candidate commit label; not proof of report origin")
    for label in ("doctor", "preflight", "session", "report-demo"):
        parser.add_argument("--" + label, type=Path, required=True,
                            help="saved JSON object from the read-only report")
    args = parser.parse_args(argv)
    try:
        report = audit_delivery_reports(args.candidate_sha, _read_report(args.doctor),
                                        _read_report(args.preflight), _read_report(args.session),
                                        _read_report(args.report_demo))
    except (OSError, UnicodeError, TypeError, ValueError, RecursionError):
        report = audit_delivery_reports(args.candidate_sha, {}, {}, {}, {})
        report["reason"] = "saved report unavailable or invalid JSON"
    print(json.dumps(report, sort_keys=True))
    return 0 if report["state"] == "local_evidence_reviewable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
