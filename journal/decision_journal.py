"""Append-only decision journal for SHREEK V5.1.

The journal records strategy decisions and lifecycle events without granting
any execution authority. Records are deterministic, JSON-serializable and
safe to persist locally or in a database adapter later.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class DecisionRecord:
    timestamp: str
    symbol: str
    decision: str
    direction: str
    fingerprint: Optional[str]
    score: Optional[int]
    setup_type: Optional[str]
    frame: Optional[str]
    entry: Optional[float]
    sl: Optional[float]
    reason: str
    failed_gate: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def now(cls, symbol: str, decision: str, direction: str, reason: str, **kwargs: Any) -> "DecisionRecord":
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol=symbol.upper(), decision=decision.upper(), direction=direction.upper(),
            reason=reason, **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionJournal:
    """Append-only JSONL journal; one malformed write cannot alter prior records."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, record: DecisionRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()

    def read(self) -> list[DecisionRecord]:
        if not self.path.exists():
            return []
        records: list[DecisionRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(DecisionRecord(**json.loads(line)))
        return records
