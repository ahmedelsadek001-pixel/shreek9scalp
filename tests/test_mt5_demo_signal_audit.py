"""The offline replay must count only signals the live M5 scan could inspect."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

from execution.mt5_demo_signal_audit_cli import audit_m5_bars, main
from execution.mt5_demo_auto import CONTEXT_BARS
from research.breakout_retest import ResearchBar


def _bars():
    first = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    bars = [ResearchBar(first + timedelta(minutes=5 * i), 4000.0,
                        4001.0, 3999.0, 4000.0, 100.0)
            for i in range(80)]
    bars[-2] = replace(bars[-2], open=4000.0, high=4002.0, low=3999.9,
                       close=4001.8, volume=200.0)
    bars[-1] = replace(bars[-1], open=4001.0, high=4001.7, low=4000.5,
                       close=4001.5)
    return bars


def test_replays_real_last_bar_detector_and_never_counts_warmup():
    bars = _bars()
    assert audit_m5_bars(bars[:-1])["candidate_windows"] == 0
    report = audit_m5_bars(bars)
    assert report["candidate_windows"] == report["eligible_windows"] == 1
    assert report["confirmed_signal_bars"] == 1
    assert report["signals_by_side"] == {"BUY": 1, "SELL": 0}
    assert report["latest_signal_utc"] == bars[-1].timestamp.isoformat()
    extended = audit_m5_bars(bars + [ResearchBar(
        bars[-1].timestamp + timedelta(minutes=5), 4000.0, 4001.0,
        3999.0, 4000.0, 100.0)])
    assert extended["eligible_windows"] == 2
    assert extended["confirmed_signal_bars"] == 1


def test_live_context_gap_blocks_historical_signal_but_old_gap_does_not():
    bars = _bars()
    bars[60] = replace(bars[60], timestamp=bars[60].timestamp + timedelta(minutes=1))
    report = audit_m5_bars(bars)
    assert report["skipped_gap_windows"] == 1
    assert report["eligible_windows"] == report["confirmed_signal_bars"] == 0
    bars = _bars()
    bars[20] = replace(bars[20], timestamp=bars[20].timestamp + timedelta(minutes=1))
    assert audit_m5_bars(bars)["confirmed_signal_bars"] == 1


def test_audit_keeps_complete_strategy_context_when_latest_33_bars_are_clean():
    bars = _bars()
    assert CONTEXT_BARS == 39
    for i, bar in enumerate(bars[:-35]):
        bars[i] = replace(bar, timestamp=bar.timestamp - timedelta(minutes=5))
    report = audit_m5_bars(bars)
    assert report["skipped_gap_windows"] == 1
    assert report["eligible_windows"] == report["confirmed_signal_bars"] == 0

    bars = _bars()
    for i, bar in enumerate(bars[:-CONTEXT_BARS]):
        bars[i] = replace(bar, timestamp=bar.timestamp - timedelta(minutes=5))
    assert audit_m5_bars(bars)["confirmed_signal_bars"] == 1


def test_cli_reads_strict_csv_and_reports_reproducible_source_hash(tmp_path, capsys):
    csv = tmp_path / "M5.csv"
    rows = ["timestamp,open,high,low,close,volume"]
    for bar in _bars():
        rows.append(",".join(str(value) for value in (
            bar.timestamp.isoformat(), bar.open, bar.high, bar.low,
            bar.close, bar.volume)))
    data = ("\n".join(rows) + "\n").encode("utf-8")
    csv.write_bytes(data)
    assert main(["--csv", str(csv)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source_sha256"] == sha256(data).hexdigest()
    assert report["confirmed_signal_bars"] == 1
    assert report["last_bar_utc"] == _bars()[-1].timestamp.isoformat()
    csv.write_text("timestamp,open,high,low,close,volume\ninvalid\n", encoding="utf-8")
    assert main(["--csv", str(csv)]) == 2
    assert "error" in json.loads(capsys.readouterr().out)
