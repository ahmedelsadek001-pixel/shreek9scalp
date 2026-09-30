"""Windows setup controls without a native terminal or package installation."""
import json
from types import SimpleNamespace

import pytest

from execution import mt5_demo_bootstrap as bootstrap


def _windows(monkeypatch, tmp_path, *, free=600 * 1024 * 1024, runtime=False):
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(
        bootstrap.shutil, "disk_usage", lambda path: SimpleNamespace(free=free)
    )
    executable = tmp_path / "SHREEK" / "mt5-runtime" / "Scripts" / "python.exe"
    if runtime:
        executable.parent.mkdir(parents=True)
        executable.touch()
    return executable


def test_doctor_reports_insufficient_space_without_creating_runtime_or_exposing_binding(
        monkeypatch, tmp_path, capsys):
    _windows(monkeypatch, tmp_path, free=20 * 1024 * 1024)
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", "123456")
    monkeypatch.setattr(bootstrap.venv, "create", lambda *a, **k: pytest.fail("created runtime"))
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: pytest.fail("ran child"))

    assert bootstrap.main(["--doctor"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reason"] == "INSUFFICIENT_LOCALAPPDATA_SPACE"
    assert report["required_free_mib"] == 300
    assert "123456" not in json.dumps(report)
    assert not (tmp_path / "SHREEK").exists()


def test_existing_runtime_uses_lower_reserve_and_skips_reinstall(monkeypatch, tmp_path):
    executable = _windows(monkeypatch, tmp_path, free=100 * 1024 * 1024, runtime=True)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    monkeypatch.setattr(bootstrap.venv, "create", lambda *a, **k: pytest.fail("recreated runtime"))
    assert bootstrap.main(["--report-demo"]) == 0
    assert calls == [
        [str(executable), "-c", "import MetaTrader5"],
        [str(executable), "-m", "execution.mt5_demo_windows_cli", "--report-demo"],
    ]


def test_full_disk_allows_existing_read_only_report_but_blocks_watch(monkeypatch, tmp_path):
    executable = _windows(monkeypatch, tmp_path, free=1 * 1024 * 1024, runtime=True)
    calls = []
    monkeypatch.setattr(bootstrap.subprocess, "run",
                        lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(bootstrap.venv, "create", lambda *a, **k: pytest.fail("created runtime"))

    assert bootstrap.main(["--report-demo"]) == 0
    assert calls == [[str(executable), "-c", "import MetaTrader5"],
                     [str(executable), "-m", "execution.mt5_demo_windows_cli", "--report-demo"]]
    assert bootstrap.main(["--watch-demo"]) == 2
    assert len(calls) == 2


def test_report_never_installs_missing_mt5_or_creates_runtime(monkeypatch, tmp_path, capsys):
    _windows(monkeypatch, tmp_path, runtime=True)
    calls = []
    monkeypatch.setattr(bootstrap.venv, "create", lambda *a, **k: pytest.fail("created runtime"))
    monkeypatch.setattr(bootstrap.subprocess, "run",
                        lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=1))

    assert bootstrap.main(["--report-demo"]) == 2
    assert len(calls) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "MT5_PACKAGE_IMPORT_FAILED"


def test_report_without_runtime_does_not_install(monkeypatch, tmp_path, capsys):
    _windows(monkeypatch, tmp_path, free=1 * 1024 * 1024)
    monkeypatch.setattr(bootstrap.venv, "create", lambda *a, **k: pytest.fail("created runtime"))
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: pytest.fail("ran child"))

    assert bootstrap.main(["--report-demo"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "DEMO_RUNTIME_NOT_PREPARED"


def test_missing_package_installs_once_then_verifies_before_watch(monkeypatch, tmp_path):
    executable = _windows(monkeypatch, tmp_path)
    calls = []

    def create(directory, *, with_pip):
        assert directory == str(executable.parent.parent) and with_pip
        executable.parent.mkdir(parents=True)
        executable.touch()

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0)

    monkeypatch.setattr(bootstrap.venv, "create", create)
    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    assert bootstrap.main(["--watch-demo"]) == 0
    assert calls == [
        [str(executable), "-c", "import MetaTrader5"],
        [str(executable), "-m", "pip", "install", "--disable-pip-version-check", "MetaTrader5"],
        [str(executable), "-c", "import MetaTrader5"],
        [str(executable), "-m", "execution.mt5_demo_windows_cli", "--watch-demo"],
    ]


def test_failed_package_install_cannot_start_watch(monkeypatch, tmp_path, capsys):
    _windows(monkeypatch, tmp_path, runtime=True)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=2)

    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    assert bootstrap.main(["--watch-demo"]) == 2
    assert len(calls) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "MT5_PACKAGE_INSTALL_FAILED"


def test_full_disk_after_install_blocks_child(monkeypatch, tmp_path, capsys):
    _windows(monkeypatch, tmp_path, runtime=True)
    calls = []
    space = [600 * 1024 * 1024, 1 * 1024 * 1024]
    monkeypatch.setattr(bootstrap.shutil, "disk_usage",
                        lambda path: SimpleNamespace(free=space.pop(0)))
    monkeypatch.setattr(bootstrap.subprocess, "run",
                        lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0))
    assert bootstrap.main(["--watch-demo"]) == 2
    assert len(calls) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "INSUFFICIENT_LOCALAPPDATA_SPACE"


def test_doctor_never_runs_on_linux_or_accepts_conflicting_modes(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Linux")
    assert bootstrap.main(["--doctor"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "WINDOWS_REQUIRED"
    with pytest.raises(SystemExit):
        bootstrap.main(["--watch-demo", "--report-demo"])
