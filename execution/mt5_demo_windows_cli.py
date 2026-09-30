"""Interactive Windows connection to an explicitly selected local DEMO terminal."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from getpass import getpass
import os
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
    parser.add_argument("--watch-demo", action="store_true",
                        help="after successful preflight, watch up to 60 minutes for one DEMO attempt")
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
        directory.mkdir(parents=True, exist_ok=True)
        ledger = directory / "demo_orders.sqlite3"
        values = {"SHREEK_DEMO_TERMINAL_PATH": str(path), "SHREEK_DEMO_LOGIN": login,
                  "SHREEK_DEMO_SERVER": server, "SHREEK_DEMO_SYMBOL": symbol,
                  "SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS": offset,
                  "SHREEK_DEMO_TRADING_ACK": "", "SHREEK_DEMO_AUTO_ACK": "",
                  "SHREEK_DEMO_KILL_SWITCH": "ON"}
        with _local_binding(values):
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


if __name__ == "__main__":
    raise SystemExit(main())
