"""Read-only local ledger and stop-file checks for a DEMO session."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3

from execution.mt5_demo_probe import DemoTerminalConfig


def ledger_session_blockers(ledger: Path, config: DemoTerminalConfig) -> tuple[str, ...]:
    config.validate()
    if not isinstance(ledger, Path) or not ledger.is_absolute() or ledger.suffix != ".sqlite3":
        return ("absolute DEMO SQLite ledger path required",)
    blockers = []
    try:
        if ledger.with_suffix(".stop").exists():
            blockers.append("automatic DEMO stop file active")
        if not ledger.parent.is_dir():
            blockers.append("DEMO ledger directory unavailable")
        if ledger.exists():
            if not ledger.is_file():
                raise OSError("not a file")
            fingerprint = sha256(f"{config.expected_login}|{config.expected_server}".encode()).hexdigest()
            with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
                if not {"account_hash", "status", "intent_id"} <= columns:
                    raise sqlite3.DatabaseError("missing ledger columns")
                if db.execute("SELECT 1 FROM attempts WHERE account_hash=? AND status='UNKNOWN' LIMIT 1",
                              (fingerprint,)).fetchone():
                    blockers.append("unresolved DEMO submission in ledger")
    except (OSError, ValueError, sqlite3.Error):
        blockers.append("DEMO ledger or stop file unreadable or malformed")
    return tuple(blockers)
