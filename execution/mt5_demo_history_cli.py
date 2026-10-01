"""Read-only broker history for the explicitly bound DEMO account."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

from execution.mt5_demo_probe import DemoTerminalConfig
from execution.mt5_demo_history import DemoHistoryReport, inspect_demo_history
from utils.mt5_compat import read_only_mt5_runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect MT5 DEMO sandbox broker deals")
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        login = os.environ.get("SHREEK_DEMO_LOGIN", "")
        if not login.isdecimal():
            raise ValueError("DEMO binding incomplete")
        config = DemoTerminalConfig(os.environ.get("SHREEK_DEMO_TERMINAL_PATH", ""),
                                    int(login), os.environ.get("SHREEK_DEMO_SERVER", ""),
                                    symbol=os.environ.get("SHREEK_DEMO_SYMBOL", "XAUUSD"))
        report = inspect_demo_history(read_only_mt5_runtime(), config, args.ledger)
    except (TypeError, ValueError, OverflowError):
        report = DemoHistoryReport(False, "DEMO history binding incomplete")
    print(json.dumps(asdict(report), sort_keys=True))
    return 0 if report.verified_demo else 2


if __name__ == "__main__":
    raise SystemExit(main())
