"""One-command, read-only DEMO preflight; no broker order transport."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

from execution.mt5_demo_auto import scan_and_submit_demo
from execution.mt5_demo_probe import DemoTerminalConfig, probe_demo_terminal
from execution.mt5_demo_readiness import inspect_demo_readiness
from utils.mt5_compat import read_only_mt5_runtime


def main() -> int:
    report: dict = {"connected_demo": False, "ready_for_demo_attempt": False,
                    "probe": None, "readiness": None, "strategy_scan": None}
    try:
        login = os.environ.get("SHREEK_DEMO_LOGIN", "")
        if not login.isdecimal():
            raise ValueError("DEMO binding incomplete")
        config = DemoTerminalConfig(
            os.environ.get("SHREEK_DEMO_TERMINAL_PATH", ""), int(login),
            os.environ.get("SHREEK_DEMO_SERVER", ""),
            symbol=os.environ.get("SHREEK_DEMO_SYMBOL", "XAUUSD"),
            server_utc_offset_seconds=int(os.environ.get("SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS", "0")),
        )
        config.validate()
        api = read_only_mt5_runtime()
        probe = probe_demo_terminal(api, config)
        report["probe"] = asdict(probe)
        report["connected_demo"] = probe.connected_demo
        if probe.connected_demo:
            readiness = inspect_demo_readiness(api, config)
            report["readiness"] = asdict(readiness)
            report["ready_for_demo_attempt"] = readiness.ready_for_demo_attempt
            if readiness.ready_for_demo_attempt:
                # Explicitly disabled even if execution opt-ins exist in the shell.
                scan = scan_and_submit_demo(api, config, Path("__read_only_preflight__.sqlite3"),
                                            execute=False, kill_switch_off=False)
                report["strategy_scan"] = asdict(scan)
    except (TypeError, ValueError, OverflowError):
        report["reason"] = "DEMO preflight binding incomplete"
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ready_for_demo_attempt"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
