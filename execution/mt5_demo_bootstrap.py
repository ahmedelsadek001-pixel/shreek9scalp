"""Prepare the isolated Windows DEMO runtime and launch one explicit mode.

The doctor is read-only and never requests account binding. All diagnostic
output uses fixed reason codes; no paths, login numbers or exception text.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import venv


SETUP_FREE_BYTES = 300 * 1024 * 1024
RUN_FREE_BYTES = 64 * 1024 * 1024


def _environment() -> tuple[Path | None, str | None]:
    if platform.system() != "Windows":
        return None, "WINDOWS_REQUIRED"
    if sys.version_info < (3, 9):
        return None, "PYTHON_3_9_REQUIRED"
    local = os.environ.get("LOCALAPPDATA", "")
    directory = Path(local)
    if not local or not directory.is_absolute() or not directory.is_dir():
        return None, "LOCALAPPDATA_UNAVAILABLE"
    return directory, None


def _status() -> tuple[dict[str, object], Path | None]:
    local, reason = _environment()
    report: dict[str, object] = {
        "schema": "shreek.demo-bootstrap.v1",
        "ready_to_prepare": False,
        "runtime_present": False,
        "reason": reason,
    }
    if local is None:
        return report, None
    runtime = local / "SHREEK" / "mt5-runtime"
    runtime_python = runtime / "Scripts" / "python.exe"
    present = runtime_python.is_file()
    report["runtime_present"] = present
    try:
        free = shutil.disk_usage(local).free
    except OSError:
        report["reason"] = "DISK_STATUS_UNAVAILABLE"
        return report, None
    required = RUN_FREE_BYTES if present else SETUP_FREE_BYTES
    report["available_free_mib"] = free // (1024 * 1024)
    report["required_free_mib"] = required // (1024 * 1024)
    if free < required:
        report["reason"] = "INSUFFICIENT_LOCALAPPDATA_SPACE"
        return report, None
    report["ready_to_prepare"] = True
    report["reason"] = None
    return report, runtime_python


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare SHREEK Windows MT5 DEMO runtime")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--doctor", action="store_true", help="read-only setup diagnosis")
    mode.add_argument("--watch-demo", action="store_true", help="start a bounded DEMO watcher")
    mode.add_argument("--report-demo", action="store_true", help="read session and broker reports")
    args = parser.parse_args(argv)
    report, runtime_python = _status()
    if args.doctor or runtime_python is None:
        print(json.dumps(report, sort_keys=True))
        return 0 if report["ready_to_prepare"] else 2
    if not report["runtime_present"]:
        try:
            venv.create(str(runtime_python.parent.parent), with_pip=True)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            print(json.dumps({"reason": "RUNTIME_CREATION_FAILED"}, sort_keys=True))
            return 2
        if not runtime_python.is_file():
            print(json.dumps({"reason": "RUNTIME_CREATION_FAILED"}, sort_keys=True))
            return 2
    try:
        probe = subprocess.run(
            [str(runtime_python), "-c", "import MetaTrader5"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if probe.returncode != 0:
            install = subprocess.run(
                [str(runtime_python), "-m", "pip", "install", "--disable-pip-version-check", "MetaTrader5"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if install.returncode != 0:
                print(json.dumps({"reason": "MT5_PACKAGE_INSTALL_FAILED"}, sort_keys=True))
                return 2
            verified = subprocess.run(
                [str(runtime_python), "-c", "import MetaTrader5"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if verified.returncode != 0:
                print(json.dumps({"reason": "MT5_PACKAGE_IMPORT_FAILED"}, sort_keys=True))
                return 2
        # Venv creation or package installation may have consumed the reserve.
        fresh_status, _ = _status()
        if not fresh_status["ready_to_prepare"]:
            print(json.dumps(fresh_status, sort_keys=True))
            return 2
        child_args = [str(runtime_python), "-m", "execution.mt5_demo_windows_cli"]
        if args.watch_demo:
            child_args.append("--watch-demo")
        elif args.report_demo:
            child_args.append("--report-demo")
        result = subprocess.run(child_args, check=False)
        return 0 if result.returncode == 0 else 2
    except OSError:
        print(json.dumps({"reason": "RUNTIME_LAUNCH_FAILED"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
