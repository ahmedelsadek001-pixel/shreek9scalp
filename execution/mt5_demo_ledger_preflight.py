"""Read-only local ledger and stop-file checks for a DEMO session."""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3

from execution.mt5_demo_probe import DemoTerminalConfig


def stop_marker_present(ledger: Path) -> bool:
    """Treat a dangling stop-marker symlink as an active stop request."""
    marker = ledger.with_suffix(".stop")
    return marker.exists() or marker.is_symlink()


def ledger_session_blockers(ledger: Path, config: DemoTerminalConfig,
                            *, check_lock: bool = True) -> tuple[str, ...]:
    config.validate()
    if type(check_lock) is not bool:
        return ("DEMO session lock check invalid",)
    if not isinstance(ledger, Path) or not ledger.is_absolute() or ledger.suffix != ".sqlite3":
        return ("absolute DEMO SQLite ledger path required",)
    blockers = []
    try:
        if stop_marker_present(ledger):
            blockers.append("automatic DEMO stop file active")
        lock = ledger.with_suffix(".watch.lock")
        if check_lock and (lock.exists() or lock.is_symlink()):
            blockers.append("automatic DEMO session lock present")
        if not ledger.parent.is_dir():
            blockers.append("DEMO ledger directory unavailable")
        if ledger.exists():
            if not ledger.is_file():
                raise OSError("not a file")
            fingerprint = sha256(f"{config.expected_login}|{config.expected_server}".encode()).hexdigest()
            with closing(sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro",
                                         uri=True, timeout=1)) as db:
                # Inspect one read-only snapshot. A readable attempts table does
                # not establish that the rest of the order evidence is intact.
                db.execute("BEGIN")
                if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise sqlite3.DatabaseError("ledger integrity failure")
                columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
                if not {"account_hash", "status", "intent_id"} <= columns:
                    raise sqlite3.DatabaseError("missing ledger columns")
                for account_hash, status in db.execute(
                        "SELECT DISTINCT account_hash, status FROM attempts"):
                    if (type(account_hash) is not str or len(account_hash) != 64
                            or any(c not in "0123456789abcdef" for c in account_hash)
                            or status not in ("UNKNOWN", "ACCEPTED")):
                        raise sqlite3.DatabaseError("malformed ledger identity or status")
                    if account_hash != fingerprint:
                        if "DEMO ledger account mismatch" not in blockers:
                            blockers.append("DEMO ledger account mismatch")
                    elif status == "UNKNOWN":
                        blockers.append("unresolved DEMO submission in ledger")
    except (OSError, ValueError, sqlite3.Error):
        blockers.append("DEMO ledger or stop file unreadable or malformed")
    journal = ledger.with_suffix(".scans.sqlite3")
    try:
        if journal.exists():
            if not journal.is_file():
                raise OSError("not a file")
            with closing(sqlite3.connect(journal.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
                db.execute("BEGIN")
                if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise sqlite3.DatabaseError("journal integrity failure")
                for table, required in (
                    ("sessions", {"session_id", "started_at", "execute_requested", "watch_minutes"}),
                    ("scan_events", {"event_id", "session_id", "recorded_at", "result_json"}),
                ):
                    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                    if not required <= columns:
                        raise sqlite3.DatabaseError("missing journal columns")
    except (OSError, ValueError, sqlite3.Error):
        blockers.append("DEMO scan journal unreadable or malformed")
    return tuple(blockers)
