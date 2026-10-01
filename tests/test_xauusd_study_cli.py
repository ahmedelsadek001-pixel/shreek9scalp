import json
from pathlib import Path

import pytest

from research import xauusd_study_cli


EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "xauusd_study_spec.example.json"


def test_study_spec_requires_complete_controls_and_rejects_nonfinite(tmp_path):
    spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert xauusd_study_cli._read_spec(EXAMPLE)[0].symbol == "XAUUSD"
    spec["run"].pop("purge_size")
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="run controls must be complete"):
        xauusd_study_cli._read_spec(path)
    spec["run"]["purge_size"] = float("nan")
    path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite JSON constant"):
        xauusd_study_cli._read_spec(path)
    spec["run"]["purge_size"] = 12
    spec["run"]["seed"] = None
    path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="fixed integer seed"):
        xauusd_study_cli._read_spec(path)


def test_study_rejects_short_sources_without_writing_result(tmp_path, monkeypatch):
    monkeypatch.setattr(xauusd_study_cli, "_repo_revision", lambda: "a" * 40)
    source = tmp_path / "short.csv"
    source.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-01-01T00:00:00+03:00,100,101,99,100,10\n"
        "2026-01-01T00:05:00+03:00,101,102,100,101,11\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.json"
    with pytest.raises(ValueError):
        xauusd_study_cli.run_study(
            EXAMPLE, {"5m": source, "15m": source, "1h": source}, output,
        )
    assert not output.exists()


@pytest.mark.parametrize("status", [
    " M research/dataset_runner.py\n",
    "?? research/untracked_study_code.py\n",
])
def test_research_command_refuses_dirty_tree(monkeypatch, status):
    from subprocess import CompletedProcess

    calls = iter((CompletedProcess([], 0, "a" * 40 + "\n", ""),
                  CompletedProcess([], 0, status, "")))
    monkeypatch.setattr(xauusd_study_cli.subprocess, "run", lambda *a, **kw: next(calls))
    with pytest.raises(ValueError, match="must be clean"):
        xauusd_study_cli._repo_revision()
