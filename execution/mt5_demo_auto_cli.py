"""One-shot, opt-in, DEMO-only experimental strategy poll; no live routing."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import time

from execution.mt5_demo_auto import DemoAutoResult, scan_and_submit_demo
from execution.mt5_demo_probe import DemoTerminalConfig
from execution.mt5_demo_session_journal import DemoSessionJournal
from utils.mt5_compat import demo_only_mt5_runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check one completed M5 DEMO strategy candle")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--execute-demo-auto", action="store_true")
    parser.add_argument("--watch-minutes", type=int, default=0,
                        help="poll one closed M5 candle every 30s, stop after one order or 60 minutes")
    args = parser.parse_args(argv)
    if args.watch_minutes < 0 or args.watch_minutes > 60:
        parser.error("--watch-minutes must be between 0 and 60")
    execute = (args.execute_demo_auto
               and os.environ.get("SHREEK_DEMO_AUTO_ACK") == "DEMO_ONLY_RESEARCH")
    if args.watch_minutes and not execute:
        result = DemoAutoResult(False, False, False, "watching requires explicit DEMO opt-in")
        print(json.dumps(asdict(result), sort_keys=True))
        return 2
    journal = None

    def emit(result):
        payload = asdict(result)
        try:
            if journal is not None:
                journal.record(result)
        except (OSError, sqlite3.Error, ValueError):
            # Preserve any actual submission outcome; never describe a sent
            # order as unsent merely because the observation log failed.
            payload["session_journal_error"] = "scan journal write failed; stop and inspect"
            print(json.dumps(payload, sort_keys=True), flush=True)
            return False
        print(json.dumps(payload, sort_keys=True), flush=True)
        return True

    try:
        login = os.environ.get("SHREEK_DEMO_LOGIN", "")
        if not login.isdecimal():
            raise ValueError("DEMO account binding incomplete")
        config = DemoTerminalConfig(os.environ.get("SHREEK_DEMO_TERMINAL_PATH", ""),
                                    int(login), os.environ.get("SHREEK_DEMO_SERVER", ""),
                                    symbol=os.environ.get("SHREEK_DEMO_SYMBOL", "XAUUSD"),
                                    server_utc_offset_seconds=int(os.environ.get("SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS", "0")))
        config.validate()
        try:
            journal = DemoSessionJournal(args.ledger, execute=execute, watch_minutes=args.watch_minutes)
        except (OSError, sqlite3.Error, ValueError):
            emit(DemoAutoResult(False, False, False, "DEMO scan journal unavailable; execution refused"))
            return 2
    except (TypeError, ValueError, OverflowError):
        result = DemoAutoResult(False, False, False, "automatic DEMO binding incomplete")
        emit(result)
        return 2

    code, end_reason = 2, "aborted"
    try:
        api = demo_only_mt5_runtime()
        deadline = time.monotonic() + args.watch_minutes * 60
        while True:
            if args.ledger.with_suffix(".stop").exists():
                emit(DemoAutoResult(False, False, False, "automatic DEMO stop file active"))
                end_reason = "stop_file"
                break
            result = scan_and_submit_demo(
                api, config, args.ledger, execute=execute,
                kill_switch_off=os.environ.get("SHREEK_DEMO_KILL_SWITCH") == "OFF",
            )
            if not emit(result):
                end_reason = "journal_error"
                break
            if result.sent or not args.watch_minutes or time.monotonic() >= deadline:
                code = 0 if result.accepted else 2
                end_reason = ("submission_attempted" if result.sent else
                              "scan_complete" if not args.watch_minutes else "watch_expired")
                break
            time.sleep(min(30, max(0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        code, end_reason = 130, "interrupted"
        # An interrupt can occur inside submission. Do not invent an unsent result.
        print(json.dumps({"session_status": "interrupted",
                          "reason": "inspect order ledger and broker history before retrying"}), flush=True)
    except (TypeError, ValueError, OverflowError):
        end_reason = "binding_error"
        print(json.dumps({"session_status": "binding_error",
                          "reason": "inspect order ledger and broker history before retrying"}), flush=True)
    finally:
        try:
            journal.finish(end_reason)
        except (OSError, sqlite3.Error, ValueError):
            code = 2
            print(json.dumps({"session_journal_error": "session end write failed; stop and inspect"}), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
