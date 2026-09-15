"""Strict, broker-neutral CSV ingestion for SHREEK research datasets.

The adapter performs no network, broker, or execution work. It converts a
well-defined OHLCV CSV schema into ``ResearchBar`` objects and immediately
runs fail-closed chronological validation.
"""
from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from typing import TextIO

from research.breakout_retest import ResearchBar
from research.data_validation import MarketDataValidation, validate_market_data


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def _parse_timestamp(value: str, row_number: int) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError(f"row {row_number}: timestamp is required")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"row {row_number}: invalid timestamp") from exc
    if timestamp.tzinfo is None:
        raise ValueError(f"row {row_number}: timestamp must be timezone-aware")
    return timestamp


def _parse_float(value: str, field: str, row_number: int) -> float:
    text = value.strip()
    if not text:
        raise ValueError(f"row {row_number}: {field} is required")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"row {row_number}: invalid {field}") from exc


def load_ohlcv_csv(source: str | TextIO) -> tuple[tuple[ResearchBar, ...], MarketDataValidation]:
    """Load strict OHLCV CSV text or a text stream and validate it.

    Required header: ``timestamp,open,high,low,close,volume``. Timestamps
    must be ISO-8601 with an explicit timezone (``Z`` is accepted).
    """
    if hasattr(source, "read"):
        reader = csv.DictReader(source)
    elif isinstance(source, str):
        reader = csv.DictReader(StringIO(source))
    else:
        raise ValueError("source must be CSV text or a text stream")

    if reader.fieldnames is None:
        raise ValueError("CSV must contain a header")
    fields = tuple(field.strip() for field in reader.fieldnames if field is not None)
    if fields != REQUIRED_COLUMNS:
        raise ValueError(
            "CSV header must be exactly: " + ",".join(REQUIRED_COLUMNS)
        )

    bars: list[ResearchBar] = []
    for row_number, row in enumerate(reader, start=2):
        if None in row:
            raise ValueError(f"row {row_number}: unexpected extra columns")
        if any(value is None for value in row.values()):
            raise ValueError(f"row {row_number}: missing required field")
        bars.append(
            ResearchBar(
                _parse_timestamp(row["timestamp"], row_number),
                _parse_float(row["open"], "open", row_number),
                _parse_float(row["high"], "high", row_number),
                _parse_float(row["low"], "low", row_number),
                _parse_float(row["close"], "close", row_number),
                _parse_float(row["volume"], "volume", row_number),
            )
        )

    validation = validate_market_data(bars)
    return tuple(bars), validation
