"""Explicit, one-shot DEMO-only sandbox order. Never a live order command."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

from execution.mt5_demo_probe import DemoTerminalConfig
from execution.mt5_demo_transport import DemoOrder, DemoSubmission, submit_demo_order
from utils.mt5_compat import demo_only_mt5_runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One DEMO-only MT5 sandbox order")
    parser.add_argument("--execute-demo", action="store_true", help="explicit one-shot DEMO submission")
    parser.add_argument("--intent-id", required=True, help="unique sandbox ID, no account number")
    parser.add_argument("--side", choices=("BUY", "SELL"), required=True)
    parser.add_argument("--stop-loss", type=float, required=True)
    parser.add_argument("--take-profit", type=float, required=True)
    parser.add_argument("--ledger", type=Path, required=True, help="absolute path outside Git checkout")
    args = parser.parse_args(argv)
    report = DemoSubmission(False, False, "DEMO submission explicitly disabled")
    if args.execute_demo and os.environ.get("SHREEK_DEMO_TRADING_ACK") == "DEMO_ONLY":
        try:
            login = os.environ.get("SHREEK_DEMO_LOGIN", "")
            if not login.isdecimal():
                raise ValueError("invalid DEMO login")
            config = DemoTerminalConfig(
                os.environ.get("SHREEK_DEMO_TERMINAL_PATH", ""), int(login),
                os.environ.get("SHREEK_DEMO_SERVER", ""),
                symbol=os.environ.get("SHREEK_DEMO_SYMBOL", "XAUUSD"),
            )
            order = DemoOrder(args.intent_id, config.symbol, args.side, 0.01,
                              args.stop_loss, args.take_profit)
            report = submit_demo_order(demo_only_mt5_runtime(), config, order, args.ledger)
        except (TypeError, ValueError, OverflowError):
            report = DemoSubmission(False, False, "DEMO binding invalid")
    print(json.dumps(asdict(report), sort_keys=True))
    return 0 if report.accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
