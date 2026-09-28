"""One-shot, opt-in, DEMO-only experimental strategy poll; no live routing."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import time

from execution.mt5_demo_auto import DemoAutoResult, scan_and_submit_demo
from execution.mt5_demo_clock import configured_demo_server_utc_offset_seconds
from execution.mt5_demo_probe import DemoTerminalConfig
from utils.mt5_compat import demo_only_mt5_runtime


# Only these passive observations may be polled again within one watch.
# A detected signal or an unknown/refused safety state requires a new run.
_WATCH_RETRYABLE_REASONS = frozenset({
    "80 completed M5 bars unavailable",
    "last completed M5 candle is stale or not yet closed",
    "no unique current closed-bar strategy signal",
})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check one completed M5 DEMO strategy candle")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--execute-demo-auto", action="store_true")
    parser.add_argument("--watch-minutes", type=int, default=0,
                        help="poll every 30s; stop after one signal, safety refusal or 60 minutes")
    args = parser.parse_args(argv)
    if args.watch_minutes < 0 or args.watch_minutes > 60:
        parser.error("--watch-minutes must be between 0 and 60")
    execute = (args.execute_demo_auto
               and os.environ.get("SHREEK_DEMO_AUTO_ACK") == "DEMO_ONLY_RESEARCH")
    if args.watch_minutes and not execute:
        result = DemoAutoResult(False, False, False, "watching requires explicit DEMO opt-in")
        print(json.dumps(asdict(result), sort_keys=True))
        return 2
    if args.watch_minutes and os.environ.get("SHREEK_DEMO_KILL_SWITCH") != "OFF":
        result = DemoAutoResult(False, False, False, "automatic DEMO kill switch active")
        print(json.dumps(asdict(result), sort_keys=True))
        return 2
    try:
        login = os.environ.get("SHREEK_DEMO_LOGIN", "")
        if not login.isdecimal():
            raise ValueError("DEMO account binding incomplete")
        config = DemoTerminalConfig(os.environ.get("SHREEK_DEMO_TERMINAL_PATH", ""),
                                    int(login), os.environ.get("SHREEK_DEMO_SERVER", ""),
                                    symbol=os.environ.get("SHREEK_DEMO_SYMBOL", "XAUUSD"),
                                    server_utc_offset_seconds=configured_demo_server_utc_offset_seconds())
        api = demo_only_mt5_runtime()
        deadline = time.monotonic() + args.watch_minutes * 60
        while True:
            if args.ledger.with_suffix(".stop").exists():
                result = DemoAutoResult(False, False, False, "automatic DEMO stop file active")
                print(json.dumps(asdict(result), sort_keys=True))
                return 2
            result = scan_and_submit_demo(
                api, config, args.ledger, execute=execute,
                kill_switch_off=os.environ.get("SHREEK_DEMO_KILL_SWITCH") == "OFF",
            )
            print(json.dumps(asdict(result), sort_keys=True), flush=True)
            # Only passive, known no-signal observations permit another scan.
            # Stop after a signal is rejected or any other safety refusal.
            if (result.signal_detected or result.sent
                    or result.reason not in _WATCH_RETRYABLE_REASONS
                    or not args.watch_minutes or time.monotonic() >= deadline):
                return 0 if result.accepted else 2
            time.sleep(min(30, max(0, deadline - time.monotonic())))
    except (TypeError, ValueError, OverflowError):
        result = DemoAutoResult(False, False, False, "automatic DEMO binding incomplete")
    print(json.dumps(asdict(result), sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
