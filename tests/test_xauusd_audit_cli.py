import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from research import dataset_runner
from research.xauusd_audit_cli import (
    audit_xauusd_csv_bundle, load_and_audit_xauusd_csv_bundle, main,
)
from research.xauusd_dataset_quality import XAUUSDQualityPolicy
from research.xauusd_source_manifest import XAUUSDSourceManifest


def _files(tmp_path):
    start = datetime(2026, 9, 21, tzinfo=timezone.utc)
    rows = []
    for index in range(72):
        stamp = start + timedelta(minutes=5 * index)
        rows.append((stamp, 2600.0, 2600.2, 2599.8, 2600.1, index + 1))
    paths = {}
    for timeframe, size in (("5m", 1), ("15m", 3), ("1h", 12)):
        lines = ["timestamp,open,high,low,close,volume"]
        for position in range(0, len(rows), size):
            group = rows[position:position + size]
            lines.append(",".join(str(item) for item in (
                group[0][0].isoformat(), group[0][1], max(bar[2] for bar in group),
                min(bar[3] for bar in group), group[-1][4], sum(bar[5] for bar in group),
            )))
        path = tmp_path / f"{timeframe}.csv"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths[timeframe] = path
    return paths


def test_audit_binds_exact_file_bytes_and_rejects_short_data(tmp_path, capsys):
    paths = _files(tmp_path)
    result = audit_xauusd_csv_bundle(paths)
    assert not result.quality.passed
    assert {finding.code for finding in result.quality.findings} == {
        "insufficient_span", "insufficient_pair_overlap",
    }
    assert result.files[0].sha256 == sha256(paths["5m"].read_bytes()).hexdigest()
    assert all(item.match_pct == 100 for item in result.quality.aggregation)

    exit_code = main(["--m5", str(paths["5m"]), "--m15", str(paths["15m"]),
                      "--h1", str(paths["1h"])])
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["quality"]["passed"] is False
    assert output["files"][0]["sha256"] == result.files[0].sha256


def test_audit_passes_only_with_explicit_test_policy(tmp_path):
    paths = _files(tmp_path)
    result = audit_xauusd_csv_bundle(paths, policy=XAUUSDQualityPolicy(
        minimum_span=timedelta(hours=5), minimum_pair_overlap=timedelta(hours=4),
        minimum_aggregation_bars=4,
    ))
    assert result.quality.passed


def test_audit_rejects_malformed_csv_before_quality_decision(tmp_path):
    paths = _files(tmp_path)
    paths["15m"].write_text("timestamp,open,high,low,close\n", encoding="utf-8")
    with pytest.raises(ValueError, match="CSV header"):
        audit_xauusd_csv_bundle(paths)
    with pytest.raises(ValueError, match="exactly 5m, 15m and 1h"):
        audit_xauusd_csv_bundle({"5m": paths["5m"]})


def test_audit_enforces_source_manifest_timezone(tmp_path):
    paths = _files(tmp_path)
    manifest = XAUUSDSourceManifest(
        "broker", "server", "XAUUSD", 0, 2, 0.01, 100.0,
        0.01, 0.01, 19.0, 7.0, 1.5,
    )
    result = audit_xauusd_csv_bundle(paths, source_manifest=manifest)
    assert result.files[0].timeframe == "5m"
    mismatch = XAUUSDSourceManifest(
        "broker", "server", "XAUUSD", 180, 2, 0.01, 100.0,
        0.01, 0.01, 19.0, 7.0, 1.5,
    )
    with pytest.raises(ValueError, match="offset does not match"):
        audit_xauusd_csv_bundle(paths, source_manifest=mismatch)


def test_audited_research_refuses_short_three_timeframe_bundle(tmp_path):
    paths = _files(tmp_path)
    manifest = XAUUSDSourceManifest(
        "broker", "server", "XAUUSD", 0, 2, 0.01, 100.0,
        0.01, 0.01, 19.0, 7.0, 1.5,
    )
    with pytest.raises(ValueError, match="three-timeframe quality gate failed"):
        dataset_runner.run_audited_xauusd_breakout_retest_research(
            paths, ({"volume_multiplier": 1.5},), source_manifest=manifest,
            pip_size=0.1, train_size=10, test_size=5, purge_size=1,
            starting_equity=10000.0,
        )


def test_audited_research_uses_hashed_bar_snapshot_and_binds_all_sources(tmp_path, monkeypatch):
    paths = _files(tmp_path)
    manifest = XAUUSDSourceManifest(
        "broker", "server", "XAUUSD", 0, 2, 0.01, 100.0,
        0.01, 0.01, 19.0, 7.0, 1.5,
    )
    audit, bars = load_and_audit_xauusd_csv_bundle(
        paths, source_manifest=manifest, policy=XAUUSDQualityPolicy(
            minimum_span=timedelta(hours=5), minimum_pair_overlap=timedelta(hours=4),
            minimum_aggregation_bars=4,
        ),
    )
    assert audit.quality.passed
    captured = {}

    def loaded_snapshot(files, *, source_manifest):
        assert source_manifest is manifest
        files["5m"].write_text("corrupted after audit\n", encoding="utf-8")
        return audit, bars

    def research_run(rows, parameters, **kwargs):
        captured.update(rows=rows, parameters=parameters, kwargs=kwargs)
        return "diagnostic result"

    monkeypatch.setattr(dataset_runner, "load_and_audit_xauusd_csv_bundle", loaded_snapshot)
    monkeypatch.setattr(dataset_runner, "run_xauusd_breakout_retest_research", research_run)
    result = dataset_runner.run_audited_xauusd_breakout_retest_research(
        paths, ({"volume_multiplier": 1.5},), source_manifest=manifest,
        pip_size=0.1, artifact_metadata={"strategy_id": "breakout-retest"},
    )
    assert result.audit is audit
    assert result.research == "diagnostic result"
    assert captured["rows"] is bars["5m"]
    metadata = captured["kwargs"]["artifact_metadata"]
    assert metadata["strategy_id"] == "breakout-retest"
    assert metadata["xauusd_quality_gate"] == "m5-m15-h1-default-v1"
    for item in audit.files:
        assert metadata[f"xauusd_{item.timeframe}_source_sha256"] == item.sha256

    with pytest.raises(ValueError, match="metadata conflicts with XAUUSD audit"):
        dataset_runner.run_audited_xauusd_breakout_retest_research(
            paths, ({},), source_manifest=manifest, pip_size=0.1,
            artifact_metadata={"xauusd_5m_source_sha256": "0" * 64},
        )
