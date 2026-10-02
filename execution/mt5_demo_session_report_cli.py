"""Offline, read-only DEMO session observations; never broker-fill evidence."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3

from execution.strategy_diagnostics import bounded_diagnostics


_SESSION_ID = re.compile(r"[0-9a-f]{32}\Z")
_SIGNAL_ID = re.compile(r"[0-9a-f]{40}\Z")
_SESSION_END_REASONS = frozenset({
    "scan_complete", "submission_attempted", "watch_expired", "stop_file",
    "journal_error", "interrupted", "binding_error", "safety_refusal", "aborted",
})


def _valid_scan_result(result: object) -> bool:
    if (not isinstance(result, dict)
            or set(result) != {"signal_detected", "sent", "accepted", "reason",
                               "signal_id", "broker_order_id"}
            or any(type(result[key]) is not bool
                   for key in ("signal_detected", "sent", "accepted"))):
        return False
    signal, sent, accepted = (result[key]
                              for key in ("signal_detected", "sent", "accepted"))
    reason = result["reason"]
    signal_id = result["signal_id"]
    broker_order_id = result["broker_order_id"]
    return (
        accepted <= sent <= signal
        and isinstance(reason, str) and 1 <= len(reason) <= 160
        and reason.isascii() and reason.isprintable()
        and ((not signal and signal_id is None)
             or (signal and isinstance(signal_id, str)
                 and _SIGNAL_ID.fullmatch(signal_id) is not None))
        and ((not accepted and broker_order_id is None)
             or (accepted and type(broker_order_id) is int and broker_order_id > 0))
    )


def _utc_timestamp(value: str) -> datetime:
    try:
        if type(value) is not str:
            raise ValueError
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("invalid DEMO session timestamp") from None


def inspect_sessions(ledger: Path, limit: int = 5) -> dict:
    if (not ledger.is_absolute() or ledger.suffix != ".sqlite3"
            or type(limit) is not int or not 1 <= limit <= 100):
        raise ValueError("absolute DEMO ledger and bounded session limit required")
    journal = ledger.with_suffix(".scans.sqlite3")
    # mode=ro cannot create a missing journal. A transaction gives one snapshot
    # while a watcher may still be appending observations.
    with closing(sqlite3.connect(journal.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
        db.execute("BEGIN")
        columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
        lifecycle = {"ended_at", "end_reason"} <= columns
        end_columns = "ended_at, end_reason" if lifecycle else "NULL, NULL"
        rows = db.execute("SELECT session_id, started_at, execute_requested, watch_minutes, "
                          + end_columns + " FROM sessions ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        has_diagnostics = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='strategy_scan_diagnostics'"
        ).fetchone() is not None
        observed_at = datetime.now(timezone.utc)
        sessions = []
        for session_id, started_at, execute, minutes, ended_at, end_reason in rows:
            completed = ended_at is not None
            if (not isinstance(session_id, str) or _SESSION_ID.fullmatch(session_id) is None
                    or type(execute) is not int or execute not in (0, 1)
                    or type(minutes) is not int or not 0 <= minutes <= 60
                    or (execute == 0 and minutes != 0)
                    or (completed and (not isinstance(end_reason, str)
                                       or end_reason not in _SESSION_END_REASONS))
                    or (not completed and end_reason is not None)):
                raise ValueError("invalid DEMO session metadata")
            started = _utc_timestamp(started_at)
            ended = _utc_timestamp(ended_at) if ended_at is not None else None
            if started > observed_at or (ended is not None and not started <= ended <= observed_at):
                raise ValueError("invalid DEMO session chronology")
            previous = started
            ceiling = ended if ended is not None else observed_at
            counts = {"scans": 0, "signals": 0, "submission_observations": 0, "accepted_observations": 0}
            last_at = last_result = None
            for recorded_at, raw in db.execute(
                    "SELECT recorded_at, result_json FROM scan_events WHERE session_id=? ORDER BY event_id",
                    (session_id,)):
                recorded = _utc_timestamp(recorded_at)
                if not previous <= recorded <= ceiling:
                    raise ValueError("invalid DEMO scan chronology")
                previous = recorded
                result = json.loads(raw)
                if not _valid_scan_result(result):
                    raise ValueError("invalid scan observation")
                counts["scans"] += 1
                counts["signals"] += int(result["signal_detected"])
                counts["submission_observations"] += int(result["sent"])
                counts["accepted_observations"] += int(result["accepted"])
                # Emit only the known result fields, never arbitrary JSON additions.
                last_at, last_result = recorded_at, result
            diagnostics = None
            if has_diagnostics:
                row = db.execute(
                    "SELECT e.recorded_at, d.diagnostics_json FROM strategy_scan_diagnostics d "
                    "JOIN scan_events e ON e.event_id=d.event_id WHERE e.session_id=? "
                    "ORDER BY e.event_id DESC LIMIT 1", (session_id,)
                ).fetchone()
                if row is not None:
                    diagnostics = {"recorded_at": row[0],
                                   "counters": bounded_diagnostics(json.loads(row[1]))}
            sessions.append({"session_id": session_id, "started_at": started_at,
                             "execute_requested": execute == 1, "watch_minutes": minutes,
                             "ended_at": ended_at, "end_reason": end_reason,
                             "end_recorded": ended_at is not None,
                             **counts, "last_scan_at": last_at, "last_result": last_result,
                             "last_strategy_diagnostics": diagnostics})
    return {"journal_readable": True, "broker_history_verified": False,
            "sessions": sessions}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read local DEMO session observations without MT5")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        report = inspect_sessions(args.ledger, args.limit)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        print(json.dumps({"journal_readable": False, "broker_history_verified": False,
                          "reason": "DEMO session journal unavailable or malformed"}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
