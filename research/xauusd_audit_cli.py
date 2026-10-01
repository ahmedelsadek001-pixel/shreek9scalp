"""Reproducible, read-only XAUUSD CSV acceptance audit; never runs trades."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

from research.breakout_retest import ResearchBar
from research.csv_adapter import load_ohlcv_csv
from research.xauusd_dataset_quality import (
    XAUUSDDatasetAudit,
    XAUUSDQualityPolicy,
    audit_xauusd_multitimeframe,
)
from research.xauusd_source_manifest import XAUUSDSourceManifest


@dataclass(frozen=True)
class DatasetFileEvidence:
    timeframe: str
    filename: str
    sha256: str
    byte_count: int
    first_timestamp: str
    last_timestamp: str


@dataclass(frozen=True)
class XAUUSDCsvAudit:
    files: tuple[DatasetFileEvidence, ...]
    quality: XAUUSDDatasetAudit


def audit_xauusd_csv_bundle(
    paths: Mapping[str, str | Path], *,
    policy: XAUUSDQualityPolicy = XAUUSDQualityPolicy(),
    source_manifest: XAUUSDSourceManifest | None = None,
) -> XAUUSDCsvAudit:
    """Hash the same bytes that are parsed, then check all three timeframes.

    A passing structural audit is necessary, not sufficient: source identity,
    spread, fills, contract value and broker costs need external evidence.
    """
    audit, _ = load_and_audit_xauusd_csv_bundle(
        paths, policy=policy, source_manifest=source_manifest,
    )
    return audit


def load_and_audit_xauusd_csv_bundle(
    paths: Mapping[str, str | Path], *,
    policy: XAUUSDQualityPolicy = XAUUSDQualityPolicy(),
    source_manifest: XAUUSDSourceManifest | None = None,
) -> tuple[XAUUSDCsvAudit, dict[str, tuple[ResearchBar, ...]]]:
    """Return the validated bars from the exact bytes hashed by the audit.

    Research callers can use this snapshot without reopening a file that may
    change between dataset acceptance and the WFO run.
    """
    if not isinstance(paths, Mapping) or set(paths) != {"5m", "15m", "1h"}:
        raise ValueError("paths must contain exactly 5m, 15m and 1h")
    policy.validate()
    if source_manifest is not None:
        if not isinstance(source_manifest, XAUUSDSourceManifest):
            raise ValueError("source_manifest must be an XAUUSDSourceManifest")
        source_manifest.validate()
    datasets = {}
    file_evidence = []
    for timeframe in ("5m", "15m", "1h"):
        path = Path(paths[timeframe])
        if not path.is_file():
            raise ValueError(f"{timeframe} CSV path must reference an existing file")
        raw = path.read_bytes()
        bars, _ = load_ohlcv_csv(raw.decode("utf-8-sig"))
        if source_manifest is not None:
            source_manifest.validate_bars_timezone(bars)
        datasets[timeframe] = tuple(bars)
        file_evidence.append(DatasetFileEvidence(
            timeframe, path.name, sha256(raw).hexdigest(), len(raw),
            bars[0].timestamp.isoformat(), bars[-1].timestamp.isoformat(),
        ))
    audit = XAUUSDCsvAudit(tuple(file_evidence), audit_xauusd_multitimeframe(datasets, policy=policy))
    return audit, datasets


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only XAUUSD multi-timeframe CSV gate")
    parser.add_argument("--m5", required=True, type=Path)
    parser.add_argument("--m15", required=True, type=Path)
    parser.add_argument("--h1", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit_xauusd_csv_bundle({"5m": args.m5, "15m": args.m15, "1h": args.h1})
    except (ValueError, OSError, UnicodeError) as exc:
        parser.error(f"invalid XAUUSD dataset: {exc}")
    print(json.dumps(asdict(result), sort_keys=True, allow_nan=False))
    return 0 if result.quality.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
