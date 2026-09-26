"""Local read-only DEMO attempt diagnostics; never sends orders."""
from __future__ import annotations

from dataclasses import asdict
import json
import os

from execution.mt5_demo_probe import DemoTerminalConfig
from execution.mt5_demo_readiness import DemoReadiness, inspect_demo_readiness
from utils.mt5_compat import read_only_mt5_runtime


def main() -> int:
    try:
        login = os.environ.get("SHREEK_DEMO_LOGIN", "")
        if not login.isdecimal():
            raise ValueError("DEMO login missing")
        config = DemoTerminalConfig(os.environ.get("SHREEK_DEMO_TERMINAL_PATH", ""), int(login),
                                    os.environ.get("SHREEK_DEMO_SERVER", ""),
                                    symbol=os.environ.get("SHREEK_DEMO_SYMBOL", "XAUUSD"))
        report = inspect_demo_readiness(read_only_mt5_runtime(), config)
    except (TypeError, ValueError, OverflowError):
        report = DemoReadiness(False, ("DEMO binding incomplete",))
    print(json.dumps(asdict(report), sort_keys=True))
    return 0 if report.ready_for_demo_attempt else 2


if __name__ == "__main__":
    raise SystemExit(main())
