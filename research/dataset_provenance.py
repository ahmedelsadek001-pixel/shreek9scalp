"""Deterministic provenance for SHREEK research datasets."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from hashlib import sha256
from typing import Sequence

from research.breakout_retest import ResearchBar
from research.data_validation import MarketDataValidation


PROVENANCE_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class DatasetProvenance:
    """Immutable identity and validation evidence for a research dataset."""

    schema_version: str
    sha256: str
    bar_count: int
    first_timestamp: datetime
    last_timestamp: datetime

    def validate(self) -> None:
        if self.schema_version != PROVENANCE_SCHEMA_VERSION:
            raise ValueError("unsupported provenance schema version")
        if type(self.sha256) is not str:
            raise ValueError("dataset sha256 must be a string")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise ValueError("dataset sha256 must be a lowercase SHA-256 digest")
        if type(self.bar_count) is not int or self.bar_count <= 0:
            raise ValueError("dataset bar_count must be positive")
        for value in (self.first_timestamp, self.last_timestamp):
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValueError("dataset timestamps must be timezone-aware datetimes")
            if not isfinite(float(value.timestamp())):
                raise ValueError("dataset timestamps must be finite")
        if self.first_timestamp >= self.last_timestamp:
            raise ValueError("dataset timestamps must span a positive interval")


def fingerprint_bars(
    bars: Sequence[ResearchBar],
    validation: MarketDataValidation,
) -> DatasetProvenance:
    """Fingerprint validated bars using a deterministic canonical representation."""
    if not validation.valid:
        raise ValueError("dataset validation must pass before fingerprinting")
    if len(bars) != validation.bar_count:
        raise ValueError("validation bar_count does not match dataset")

    payload = [f"schema={PROVENANCE_SCHEMA_VERSION}\n"]
    for bar in bars:
        payload.append(
            f"{bar.timestamp.isoformat()}|{bar.open:.17g}|{bar.high:.17g}|"
            f"{bar.low:.17g}|{bar.close:.17g}|{bar.volume:.17g}\n"
        )
    digest = sha256("".join(payload).encode("utf-8")).hexdigest()
    result = DatasetProvenance(
        PROVENANCE_SCHEMA_VERSION,
        digest,
        validation.bar_count,
        validation.first_timestamp,
        validation.last_timestamp,
    )
    result.validate()
    return result
