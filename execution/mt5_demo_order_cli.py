"""Explicit, one-shot DEMO-only sandbox order. Never a live order command."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import json
import os
from pathlib import Path

from execution.mt5_demo_probe import DemoTerminalConfig
from execution.mt5_demo_clock import configured_demo_server_utc_offset_seconds
from execution.mt5_demo_ledger_preflight import ledger_session_blockers
from execution.mt5_demo_session_journal import exclusive_demo_session
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
    session_guard = ExitStack()
    cleanup_failed = False
    if args.execute_demo and os.environ.get("SHREEK_DEMO_TRADING_ACK") == "DEMO_ONLY":
        try:
            if os.environ.get("SHREEK_DEMO_KILL_SWITCH") != "OFF":
                raise ValueError("DEMO kill switch active")
            login = os.environ.get("SHREEK_DEMO_LOGIN", "")
            if not login.isdecimal():
                raise ValueError("invalid DEMO login")
            config = DemoTerminalConfig(
                os.environ.get("SHREEK_DEMO_TERMINAL_PATH", ""), int(login),
                os.environ.get("SHREEK_DEMO_SERVER", ""),
                symbol=os.environ.get("SHREEK_DEMO_SYMBOL", "XAUUSD"),
                server_utc_offset_seconds=configured_demo_server_utc_offset_seconds(),
            )
            config.validate()
            order = DemoOrder(args.intent_id, config.symbol, args.side, 0.01,
                              args.stop_loss, args.take_profit)
            try:
                session_guard.enter_context(exclusive_demo_session(args.ledger))
            except (OSError, ValueError):
                report = DemoSubmission(False, False, "DEMO session active or lock unavailable")
            else:
                if ledger_session_blockers(args.ledger, config, check_lock=False):
                    report = DemoSubmission(False, False, "DEMO local preflight blocked; inspect ledger and journal")
                else:
                    report = submit_demo_order(demo_only_mt5_runtime(), config, order, args.ledger)
        except (TypeError, ValueError, OverflowError):
            report = DemoSubmission(False, False, "DEMO binding invalid or kill switch active")
        finally:
            try:
                session_guard.close()
            except OSError:
                cleanup_failed = True
    payload = asdict(report)
    if cleanup_failed:
        # Keep the broker outcome even when releasing the local lock fails.
        payload["session_lock_error"] = "DEMO lock cleanup failed; stop and inspect"
    print(json.dumps(payload, sort_keys=True))
    return 0 if report.accepted and not cleanup_failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
