"""Local read-only DEMO terminal probe. No password or order transport."""
from __future__ import annotations

import json
import os
from dataclasses import asdict

from execution.mt5_demo_probe import DemoTerminalConfig, DemoTerminalProbe, probe_demo_terminal
from utils.mt5_compat import read_only_mt5_runtime


def main() -> int:
    terminal_path = os.environ.get("SHREEK_DEMO_TERMINAL_PATH", "")
    server = os.environ.get("SHREEK_DEMO_SERVER", "")
    login_text = os.environ.get("SHREEK_DEMO_LOGIN", "")
    try:
        if not login_text.isdecimal():
            raise ValueError("expected demo login is not configured")
        config = DemoTerminalConfig(terminal_path, int(login_text), server)
        config.validate()
    except ValueError:
        report = DemoTerminalProbe(False, "DEMO terminal binding is incomplete")
    else:
        report = probe_demo_terminal(read_only_mt5_runtime(), config)
    print(json.dumps(asdict(report), sort_keys=True))
    return 0 if report.connected_demo else 2


if __name__ == "__main__":
    raise SystemExit(main())
