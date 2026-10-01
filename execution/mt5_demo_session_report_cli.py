"""Offline, read-only DEMO session observations; never broker-fill evidence."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from execution.strategy_diagnostics import bounded_diagnostics


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
        sessions = []
        for session_id, started_at, execute, minutes, ended_at, end_reason in rows:
            counts = {"scans": 0, "signals": 0, "submission_observations": 0, "accepted_observations": 0}
            last_at = last_result = None
            for recorded_at, raw in db.execute(
                    "SELECT recorded_at, result_json FROM scan_events WHERE session_id=? ORDER BY event_id",
                    (session_id,)):
                result = json.loads(raw)
                if (not isinstance(result, dict)
                        or set(result) != {"signal_detected", "sent", "accepted", "reason",
                                           "signal_id", "broker_order_id"}
                        or any(type(result[key]) is not bool for key in ("signal_detected", "sent", "accepted"))
                        or not isinstance(result["reason"], str)):
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
                             "execute_requested": bool(execute), "watch_minutes": minutes,
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
