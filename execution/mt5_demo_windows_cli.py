"""Interactive Windows connection to an explicitly selected local DEMO terminal."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
from getpass import getpass
import os
import io
import json
from pathlib import Path
import platform


@contextmanager
def _local_binding(values: dict[str, str]):
    """Keep prompted account binding and execution flags within this process."""
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Connect SHREEK to your local Windows DEMO MT5")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch-demo", action="store_true",
                        help="after successful preflight, watch up to 60 minutes for one DEMO attempt")
    mode.add_argument("--report-demo", action="store_true",
                      help="read local sessions and broker history without sending orders")
    args = parser.parse_args(argv)
    if platform.system() != "Windows":
        print("Run this command on the Windows PC containing your DEMO terminal.")
        return 2

    from execution.mt5_demo_probe import DemoTerminalConfig
    from execution.mt5_demo_preflight_cli import main as preflight
    from execution.mt5_demo_auto_cli import main as watch
    from utils.mt5_compat import AVAILABLE

    if not AVAILABLE:
        print("MT5 runtime missing. Run connect_mt5_demo.cmd on this Windows PC.")
        return 2
    try:
        terminal = os.environ.get("SHREEK_DEMO_TERMINAL_PATH") or input("DEMO terminal64.exe full path: ").strip()
        terminal = terminal.strip('"')
        path = Path(terminal)
        if not path.is_absolute() or not path.is_file() or path.name.lower() != "terminal64.exe":
            raise ValueError("invalid terminal path")
        login = os.environ.get("SHREEK_DEMO_LOGIN") or getpass("Expected DEMO login (hidden): ")
        server = os.environ.get("SHREEK_DEMO_SERVER") or input("Exact DEMO server: ").strip()
        symbol = os.environ.get("SHREEK_DEMO_SYMBOL") or input("Exact gold symbol, including broker suffix: ").strip()
        offset = os.environ.get("SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS")
        if offset is None:
            offset = input("Verified broker UTC offset in seconds (0 or 10800): ").strip()
        if not login.isdecimal() or offset not in ("0", "10800"):
            raise ValueError("invalid account binding or clock")
        DemoTerminalConfig(str(path), int(login), server, symbol=symbol,
                           server_utc_offset_seconds=int(offset)).validate()
        local_data = os.environ.get("LOCALAPPDATA", "")
        if not local_data or not Path(local_data).is_absolute():
            raise ValueError("local data directory unavailable")
        directory = Path(local_data) / "SHREEK"
        if args.report_demo:
            if not directory.is_dir():
                raise ValueError("local DEMO evidence directory unavailable")
        else:
            directory.mkdir(parents=True, exist_ok=True)
        ledger = directory / "demo_orders.sqlite3"
        values = {"SHREEK_DEMO_TERMINAL_PATH": str(path), "SHREEK_DEMO_LOGIN": login,
                  "SHREEK_DEMO_SERVER": server, "SHREEK_DEMO_SYMBOL": symbol,
                  "SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS": offset,
                  "SHREEK_DEMO_TRADING_ACK": "", "SHREEK_DEMO_AUTO_ACK": "",
                  "SHREEK_DEMO_KILL_SWITCH": "ON"}
        with _local_binding(values):
            if args.report_demo:
                return _read_reports(ledger)
            code = preflight(["--ledger", str(ledger)])
            if code != 0 or not args.watch_demo:
                return code
            os.environ["SHREEK_DEMO_AUTO_ACK"] = "DEMO_ONLY_RESEARCH"
            os.environ["SHREEK_DEMO_KILL_SWITCH"] = "OFF"
            return watch(["--execute-demo-auto", "--watch-minutes", "60", "--ledger", str(ledger)])
    except (EOFError, KeyboardInterrupt):
        print("Windows DEMO connection cancelled; inspect broker history if watching had started.")
        return 2
    except (OSError, TypeError, ValueError, OverflowError):
        # Do not expose paths, account identifiers, or exception payloads.
        print("Windows DEMO binding unavailable or invalid; check local inputs.")
        return 2


def _read_reports(ledger: Path) -> int:
    from execution.mt5_demo_handover import assess_handover
    from execution.mt5_demo_session_report_cli import main as sessions
    from execution.mt5_demo_history_cli import main as history

    report = {"schema": "shreek.demo-handover.v1", "independent_broker_export_verified": False}
    codes = []
    for label, command in (("local_sessions", sessions), ("broker_history", history)):
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                code = command(["--ledger", str(ledger)])
            payload = json.loads(output.getvalue())
            if not isinstance(payload, dict):
                raise ValueError("invalid report")
        except (OSError, TypeError, ValueError):
            code, payload = 2, {"reason": "DEMO report unavailable or malformed"}
        report[label] = {"exit_code": code, "report": payload}
        codes.append(code)
    report["handover_assessment"] = assess_handover(report)
    print(json.dumps(report, sort_keys=True))
    return 0 if all(code == 0 for code in codes) else 2


if __name__ == "__main__":
    raise SystemExit(main())
