"""CLI for validating and cross-checking local research OHLCV CSV files."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import timedelta, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any

from research.breakout_retest import ResearchBar
from research.csv_adapter import load_ohlcv_csv
from research.dataset_consistency import PRICE_COMPARISON_METRIC, compare_overlapping_datasets
from research.dataset_provenance import fingerprint_bars
from research.data_validation import validate_market_data


def _inspect(path: Path) -> tuple[tuple[ResearchBar, ...], dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"dataset file is missing or not regular: {path.name}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"dataset file could not be read: {path.name}") from exc
    bars, validation = load_ohlcv_csv(text)
    provenance = fingerprint_bars(bars, validation)
    return bars, {
        "file": path.name,
        "bar_count": validation.bar_count,
        "first_timestamp": validation.first_timestamp.isoformat(),
        "last_timestamp": validation.last_timestamp.isoformat(),
        "dataset_sha256": provenance.sha256,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate OHLCV CSV files and check same-timeframe price consistency"
    )
    parser.add_argument("--primary", required=True, type=Path)
    parser.add_argument(
        "--reference", required=True, action="append", type=Path,
        help="same-symbol, same-timeframe reference CSV; may be repeated",
    )
    parser.add_argument("--min-common", type=int, default=100)
    parser.add_argument("--max-median-diff-pct", type=float, default=0.5)
    parser.add_argument("--max-p95-diff-pct", type=float, default=1.0)
    parser.add_argument(
        "--min-history-days", type=float,
        help="require the primary dataset to span at least this many days",
    )
    parser.add_argument(
        "--max-gap-hours", type=float,
        help="reject any adjacent primary bars farther apart than this many hours",
    )
    args = parser.parse_args(argv)

    try:
        primary_bars, primary_info = _inspect(args.primary)
        if args.max_gap_hours is not None and (
            not math.isfinite(args.max_gap_hours) or args.max_gap_hours <= 0
        ):
            raise ValueError("max-gap-hours must be a finite positive number")
        if args.max_gap_hours is not None:
            validate_market_data(primary_bars, max_gap=timedelta(hours=args.max_gap_hours))
        primary_history_days = (
            primary_bars[-1].timestamp.astimezone(timezone.utc)
            - primary_bars[0].timestamp.astimezone(timezone.utc)
        ).total_seconds() / 86400.0
        if args.min_history_days is not None and (
            not math.isfinite(args.min_history_days) or args.min_history_days <= 0
        ):
            raise ValueError("min-history-days must be a finite positive number")
        history_passed = (
            args.min_history_days is not None
            and primary_history_days >= args.min_history_days
        )
        references = []
        for reference_path in args.reference:
            reference_bars, reference_info = _inspect(reference_path)
            check = compare_overlapping_datasets(
                primary_bars,
                reference_bars,
                minimum_common_timestamps=args.min_common,
                max_median_difference_pct=args.max_median_diff_pct,
                max_p95_difference_pct=args.max_p95_diff_pct,
            )
            check.validate()
            references.append({
                **reference_info,
                "comparison": {**asdict(check), "price_comparison_metric": PRICE_COMPARISON_METRIC,
                               "consistent": check.consistent},
            })
        ready = (
            bool(references)
            and history_passed
            and all(item["comparison"]["consistent"] for item in references)
        )
        output = {
            "schema_version": "2",
            "ready_for_research": ready,
            "primary": primary_info,
            "history_check": {
                "minimum_days": args.min_history_days,
                "actual_days": primary_history_days,
                "configured": args.min_history_days is not None,
                "passed": history_passed,
            },
            "references": references,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0 if ready else 1
    except (OSError, UnicodeError, TypeError, ValueError, OverflowError) as exc:
        print(
            json.dumps({"schema_version": "2", "ready_for_research": False, "error": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
