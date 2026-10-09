"""Read-only historical M5 signal audit using the exact DEMO detector and context gate.

This module never imports the MT5 runtime, submits orders, or changes the
strategy. Historical bar counts do not imply broker fills or current signals.
"""
from __future__ import annotations

import argparse
from datetime import timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence

from execution.mt5_demo_auto import (PIP_SIZE, STRATEGY_ID, STRATEGY_CONFIG,
                                     m5_context_is_contiguous)
from execution.strategy_diagnostics import bounded_diagnostics
from research.breakout_retest import (ResearchBar, SIGNAL_RULES_ID,
                                      detect_breakout_retest)
from research.csv_adapter import load_ohlcv_csv


WINDOW_BARS = 80
SCHEMA_VERSION = 2


def audit_m5_bars(bars: Sequence[ResearchBar]) -> dict:
    """Replay the live last-bar test across valid, completed historical windows."""
    eligible = skipped_gaps = confirmed = ambiguous = 0
    by_side = {"BUY": 0, "SELL": 0}
    latest_signal = None
    rejection_counts = {}
    consumed_windows = 0
    for end in range(WINDOW_BARS - 1, len(bars)):
        window = bars[end - WINDOW_BARS + 1:end + 1]
        if not m5_context_is_contiguous(window):
            skipped_gaps += 1
            continue
        eligible += 1
        diagnostics = {}
        signals = detect_breakout_retest(window, PIP_SIZE, STRATEGY_CONFIG,
                                         min_signal_index=WINDOW_BARS - 1,
                                         diagnostics=diagnostics)
        rejected = bounded_diagnostics(diagnostics)["rejected"]
        for reason, count in rejected.items():
            rejection_counts[reason] = rejection_counts.get(reason, 0) + count
        if rejected.get("first_confirmation_before_evaluation", 0):
            consumed_windows += 1
        if len(signals) == 1 and signals[0].signal_time == window[-1].timestamp:
            confirmed += 1
            by_side[signals[0].direction.value] += 1
            latest_signal = signals[0].signal_time.astimezone(timezone.utc).isoformat()
        elif signals:
            ambiguous += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "signal_rules_id": SIGNAL_RULES_ID,
        "bar_count": len(bars),
        "first_bar_utc": bars[0].timestamp.astimezone(timezone.utc).isoformat() if bars else None,
        "last_bar_utc": bars[-1].timestamp.astimezone(timezone.utc).isoformat() if bars else None,
        "candidate_windows": max(0, len(bars) - WINDOW_BARS + 1),
        "eligible_windows": eligible,
        "skipped_gap_windows": skipped_gaps,
        "confirmed_signal_bars": confirmed,
        "ambiguous_signal_bars": ambiguous,
        "no_signal_windows": eligible - confirmed - ambiguous,
        "previously_confirmed_breakout_windows": consumed_windows,
        "rejection_counts": rejection_counts,
        "signals_by_side": by_side,
        "latest_signal_utc": latest_signal,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit closed M5 DEMO signals in a local CSV")
    parser.add_argument("--csv", type=Path, required=True,
                        help="local timezone-aware timestamp,open,high,low,close,volume CSV")
    args = parser.parse_args(argv)
    try:
        data = args.csv.read_bytes()
        bars, _ = load_ohlcv_csv(data.decode("utf-8-sig"))
        result = audit_m5_bars(bars)
        result["source_sha256"] = sha256(data).hexdigest()
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError):
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "error": "invalid or unreadable M5 CSV"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
