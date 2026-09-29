"""Durable local DEMO scan observations, separate from broker-order evidence."""
from __future__ import annotations

from dataclasses import asdict
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from execution.mt5_demo_auto import DemoAutoResult


class DemoSessionJournal:
    def __init__(self, ledger: Path, *, execute: bool, watch_minutes: int):
        if not ledger.is_absolute() or ledger.suffix != ".sqlite3" or not ledger.parent.is_dir():
            raise ValueError("absolute local DEMO ledger directory required")
        self.path = ledger.with_suffix(".scans.sqlite3")
        self.session_id = uuid4().hex
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions "
                       "(session_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, "
                       "execute_requested INTEGER NOT NULL, watch_minutes INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS scan_events "
                       "(event_id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, "
                       "recorded_at TEXT NOT NULL, result_json TEXT NOT NULL)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            for column in ("ended_at", "end_reason"):
                if column not in columns:
                    db.execute(f"ALTER TABLE sessions ADD COLUMN {column} TEXT")
            db.execute("INSERT INTO sessions (session_id, started_at, execute_requested, watch_minutes) "
                       "VALUES (?, ?, ?, ?)",
                       (self.session_id, datetime.now(timezone.utc).isoformat(),
                        int(execute), watch_minutes))

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=1)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def record(self, result: DemoAutoResult) -> None:
        if not isinstance(result, DemoAutoResult):
            raise TypeError("DEMO scan result required")
        with self._connect() as db:
            db.execute("INSERT INTO scan_events (session_id, recorded_at, result_json) VALUES (?, ?, ?)",
                       (self.session_id, datetime.now(timezone.utc).isoformat(),
                        json.dumps(asdict(result), sort_keys=True)))

    def finish(self, reason: str) -> None:
        if reason not in {"scan_complete", "submission_attempted", "watch_expired", "stop_file",
                          "journal_error", "interrupted", "binding_error", "aborted"}:
            raise ValueError("unknown DEMO session end reason")
        with self._connect() as db:
            db.execute("UPDATE sessions SET ended_at=?, end_reason=? WHERE session_id=? AND ended_at IS NULL",
                       (datetime.now(timezone.utc).isoformat(), reason, self.session_id))
