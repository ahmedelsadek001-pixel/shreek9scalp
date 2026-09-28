import json

from research.dataset_audit_cli import main


def write_csv(path, prices, *, offset="Z"):
    rows = ["timestamp,open,high,low,close,volume"]
    for index, price in enumerate(prices):
        minute = index * 15
        hour, minute = divmod(minute, 60)
        rows.append(
            f"2026-01-01T{hour:02d}:{minute:02d}:00{offset},"
            f"{price},{price + 1},{price - 1},{price},10"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_dataset_audit_cli_emits_archivable_pass_report(tmp_path, capsys):
    primary, reference = tmp_path / "primary.csv", tmp_path / "reference.csv"
    write_csv(primary, [100, 101, 102])
    write_csv(reference, [100.01, 101.01, 102.01], offset="+00:00")
    assert main([
        "--primary", str(primary), "--reference", str(reference), "--min-common", "3",
        "--min-history-days", "0.01",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ready_for_research"] is True
    assert output["references"][0]["comparison"]["common_timestamps"] == 3
    assert output["schema_version"] == "2"
    assert output["references"][0]["comparison"]["price_comparison_metric"] == "max_ohlc_pct_per_aligned_bar_v1"
    assert output["primary"]["file"] == "primary.csv"


def test_dataset_audit_cli_denies_materially_different_prices(tmp_path, capsys):
    primary, reference = tmp_path / "primary.csv", tmp_path / "reference.csv"
    write_csv(primary, [3200, 3210, 3220])
    write_csv(reference, [2450, 2460, 2470])
    assert main([
        "--primary", str(primary), "--reference", str(reference), "--min-common", "3"
    ]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ready_for_research"] is False
    assert output["references"][0]["comparison"]["consistent"] is False


def test_dataset_audit_cli_does_not_claim_readiness_without_history_policy(tmp_path, capsys):
    primary, reference = tmp_path / "primary.csv", tmp_path / "reference.csv"
    write_csv(primary, [100, 101, 102])
    write_csv(reference, [100, 101, 102])
    assert main([
        "--primary", str(primary), "--reference", str(reference), "--min-common", "3",
    ]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["references"][0]["comparison"]["consistent"] is True
    assert output["history_check"]["configured"] is False
    assert output["ready_for_research"] is False


def test_dataset_audit_cli_rejects_cross_timeframe_comparison(tmp_path, capsys):
    primary, reference = tmp_path / "primary_m15.csv", tmp_path / "reference_m5.csv"
    write_csv(primary, [100, 101, 102])
    rows = ["timestamp,open,high,low,close,volume"]
    for index, close in enumerate([100, 99, 99, 101, 99, 99, 102]):
        minute = index * 5
        rows.append(
            f"2026-01-01T00:{minute:02d}:00Z,{close},{close + 1},{close - 1},{close},10"
        )
    reference.write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert main([
        "--primary", str(primary), "--reference", str(reference), "--min-common", "3"
    ]) == 1
    output = json.loads(capsys.readouterr().out)
    comparison = output["references"][0]["comparison"]
    assert comparison["median_difference_pct"] == 0.0
    assert comparison["left_interval_seconds"] == 900
    assert comparison["right_interval_seconds"] == 300
    assert comparison["consistent"] is False


def test_dataset_audit_cli_enforces_primary_history_requirement(tmp_path, capsys):
    primary, reference = tmp_path / "primary.csv", tmp_path / "reference.csv"
    write_csv(primary, [100, 101, 102])
    write_csv(reference, [100, 101, 102])
    assert main([
        "--primary", str(primary), "--reference", str(reference),
        "--min-common", "3", "--min-history-days", "1",
    ]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ready_for_research"] is False
    assert output["history_check"]["passed"] is False
    assert output["history_check"]["actual_days"] < 1


def test_dataset_audit_cli_can_fail_closed_on_large_primary_gap(tmp_path, capsys):
    primary, reference = tmp_path / "primary.csv", tmp_path / "reference.csv"
    rows = [
        "timestamp,open,high,low,close,volume",
        "2026-01-01T00:00:00Z,100,101,99,100,10",
        "2026-01-01T01:00:00Z,101,102,100,101,10",
    ]
    primary.write_text("\n".join(rows) + "\n", encoding="utf-8")
    reference.write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert main([
        "--primary", str(primary), "--reference", str(reference),
        "--min-common", "2", "--max-gap-hours", "0.5",
    ]) == 2
    output = json.loads(capsys.readouterr().err)
    assert output["ready_for_research"] is False
    assert "gaps_over_limit=1" in output["error"]


def test_dataset_audit_cli_reports_invalid_csv_as_input_error(tmp_path, capsys):
    primary, reference = tmp_path / "primary.csv", tmp_path / "reference.csv"
    primary.write_text("bad,csv\n", encoding="utf-8")
    reference.write_text("bad,csv\n", encoding="utf-8")
    assert main(["--primary", str(primary), "--reference", str(reference)]) == 2
    output = json.loads(capsys.readouterr().err)
    assert output["ready_for_research"] is False
    assert "header must be exactly" in output["error"]


def test_dataset_audit_cli_requires_reference_source():
    try:
        main(["--primary", "unused.csv"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("reference argument must be required")
