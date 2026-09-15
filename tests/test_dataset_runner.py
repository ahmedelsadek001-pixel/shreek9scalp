from datetime import datetime, timedelta, timezone

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from research.dataset_runner import run_csv_research, run_dataset_research
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_report import OOSEvidenceReport


CSV = """timestamp,open,high,low,close,volume
2026-01-01T10:00:00Z,100,101,99,100.5,10
2026-01-01T10:05:00Z,100.5,101.5,100,101,12
2026-01-01T10:10:00Z,101,102,100.5,101.5,11
2026-01-01T10:15:00Z,101.5,102.5,101,102,13
2026-01-01T10:20:00Z,102,103,101.5,102.5,14
2026-01-01T10:25:00Z,102.5,103.5,102,103,15
2026-01-01T10:30:00Z,103,104,102.5,103.5,16
2026-01-01T10:35:00Z,103.5,104.5,103,104,17
"""


def _result(pnl: float) -> BacktestResult:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    trade = BacktestTrade(
        now, now + timedelta(minutes=1), now + timedelta(minutes=2),
        Direction.BUY, 100.0, 100.0 + pnl, 1.0, pnl, 0.0, pnl,
        "TP3" if pnl > 0 else "SL",
    )
    stats = BacktestStats(
        10000.0, 10000.0 + pnl, pnl, pnl / 100.0, 1,
        int(pnl > 0), int(pnl < 0), 100.0 if pnl > 0 else 0.0,
        float("inf") if pnl > 0 else 0.0, pnl, max(-pnl, 0.0),
        max(-pnl, 0.0) / 100.0, 0.0,
    )
    return BacktestResult((trade,), (10000.0, 10000.0 + pnl), stats)


def _evidence():
    report = OOSEvidenceReport(30, 100.0, 3.333333, 75.0, 3, 4, 0.0, 10100.0, 10000.0, 50.0, 100.0, 1000)
    policy = EvidenceGatePolicy()
    return EvidencePipelineResult(object(), object(), report, EvidenceGateResult(True, ()), policy)


def test_dataset_runner_validates_before_evidence_pipeline(monkeypatch):
    from research import dataset_runner

    calls = []

    def fake_pipeline(*args, **kwargs):
        calls.append(args[0])
        return _evidence()

    monkeypatch.setattr(dataset_runner, "run_evidence_pipeline", fake_pipeline)
    bars, _ = dataset_runner.load_ohlcv_csv(CSV)
    result = run_dataset_research(
        bars, ({"x": 1},), lambda rows, params: _result(1.0),
        train_size=3, test_size=2, purge_size=1, starting_equity=10000.0,
    )
    assert result.validation.valid is True
    assert result.provenance.bar_count == len(bars)
    assert result.artifact.evidence_export_sha256
    assert calls == [bars]


def test_csv_runner_requires_existing_file(tmp_path):
    with pytest.raises(ValueError, match="existing file"):
        run_csv_research(tmp_path / "missing.csv", ({"x": 1},), lambda rows, params: _result(1.0), train_size=3, test_size=2, purge_size=1, starting_equity=10000.0)


def test_csv_runner_rejects_invalid_dataset(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(CSV.replace("2026-01-01T10:35:00Z", "2026-01-01T10:20:00Z"), encoding="utf-8")
    with pytest.raises(ValueError, match="chronological validation"):
        run_csv_research(path, ({"x": 1},), lambda rows, params: _result(1.0), train_size=3, test_size=2, purge_size=1, starting_equity=10000.0)
