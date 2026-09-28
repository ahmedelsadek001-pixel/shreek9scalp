from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from research.dataset_provenance import DatasetProvenance
from research.evidence_export import (
    build_dataset_evidence_export,
    build_evidence_export,
    fingerprint_dataset_evidence_export,
    fingerprint_evidence_export,
    serialize_dataset_evidence_export,
    serialize_evidence_export,
    verify_serialized_dataset_evidence_export,
)
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult
from research.evidence_pipeline import run_evidence_pipeline
from research.breakout_retest import ResearchBar
from research.dataset_runner import run_dataset_research
from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction


def _provenance():
    return DatasetProvenance(
        "1", "a" * 64, 2,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )


def _backtest(pnl):
    now = datetime(2026, 1, 1)
    trade = BacktestTrade(
        now,
        now + timedelta(minutes=1),
        now + timedelta(minutes=2),
        Direction.BUY,
        100.0,
        100.0 + pnl,
        1.0,
        pnl,
        0.0,
        pnl,
        "TP3",
    )
    stats = BacktestStats(
        10000.0, 10000.0 + pnl, pnl, pnl / 100.0, 1, 1, 0, 100.0,
        float("inf"), pnl, 0.0, 0.0, 0.0,
    )
    return BacktestResult((trade,), (10000.0, 10000.0 + pnl), stats)


def _result(policy=None):
    return run_evidence_pipeline(
        list(range(9)),
        ({"mult": 1.0},),
        lambda rows, params: _backtest(float(len(rows)) * params["mult"]),
        train_size=4,
        test_size=2,
        purge_size=1,
        starting_equity=10000.0,
        step=2,
        simulations=25,
        policy=policy or EvidenceGatePolicy(min_oos_trades=2, min_oos_stability_pct=0.0),
    )


def _dataset_result():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = tuple(
        ResearchBar(
            start + timedelta(minutes=5 * index),
            100.0 + index,
            101.0 + index,
            99.0 + index,
            100.5 + index,
            10.0 + index,
        )
        for index in range(9)
    )
    reference = tuple(
        ResearchBar(
            bar.timestamp,
            bar.open + 0.1,
            bar.high + 0.1,
            bar.low + 0.1,
            bar.close + 0.1,
            bar.volume,
        )
        for bar in bars
    )
    return run_dataset_research(
        bars,
        ({"mult": 1.0},),
        lambda rows, params: _backtest(float(len(rows)) * params["mult"]),
        train_size=4,
        test_size=2,
        purge_size=1,
        starting_equity=10000.0,
        step=2,
        simulations=25,
        policy=EvidenceGatePolicy(min_oos_trades=2, min_oos_stability_pct=0.0),
        comparison_datasets=(reference,),
        comparison_minimum_common_timestamps=9,
        minimum_history=timedelta(minutes=20),
        max_gap=timedelta(minutes=10),
    )


def test_export_is_deterministic():
    result = _result(EvidenceGatePolicy(min_expectancy=1.0))
    first = serialize_evidence_export(result, _provenance())
    second = serialize_evidence_export(result, _provenance())
    assert first == second
    assert fingerprint_evidence_export(result, _provenance()) == fingerprint_evidence_export(result, _provenance())


def test_export_contains_dataset_identity_evidence_and_exact_policy():
    policy = EvidenceGatePolicy(min_oos_trades=2, min_expectancy=1.0, min_oos_stability_pct=0.0)
    payload = build_evidence_export(_result(policy), _provenance())
    assert payload["schema_version"] == "9"
    assert payload["dataset"]["sha256"] == "a" * 64
    assert "oos_expectancy" in payload["evidence"]
    assert payload["gate"]["passed"] is True
    assert payload["gate_policy"]["min_expectancy"] == 1.0
    assert payload["gate_policy"]["max_worst_drawdown"] is None


def test_serialized_export_uses_strict_json_without_nonstandard_numbers():
    serialized = serialize_evidence_export(_result(), _provenance())
    assert "Infinity" not in serialized

    def reject_constant(value):
        raise ValueError(value)

    parsed = json.loads(
        serialized,
        parse_constant=reject_constant,
    )
    assert parsed["schema_version"] == "9"


def test_export_rejects_invalid_policy():
    invalid = EvidenceGatePolicy(min_oos_trades=0)
    with pytest.raises(ValueError, match="min_oos_trades"):
        build_evidence_export(_result(invalid), _provenance())


@pytest.mark.parametrize(
    "gate",
    [
        EvidenceGateResult(False, ("forged failure",)),
        EvidenceGateResult(True, ("OOS trade count below minimum",)),
    ],
)
def test_export_rejects_gate_that_disagrees_with_report_and_policy(gate):
    result = replace(_result(), gate=gate)
    with pytest.raises(ValueError, match="does not match report and policy"):
        build_evidence_export(result, _provenance())


def test_export_rejects_report_that_disagrees_with_pipeline_components():
    result = _result()
    forged_report = replace(result.report, oos_net_pnl=result.report.oos_net_pnl + 100.0)
    forged_gate = EvidenceGateResult(False, ("OOS expectancy below minimum",))
    forged = replace(result, report=forged_report, gate=forged_gate)
    with pytest.raises(ValueError, match="report does not match"):
        build_evidence_export(forged, _provenance())


def test_export_rejects_monte_carlo_trade_pnl_detached_from_wfo():
    result = _result()
    robustness = replace(
        result.robustness,
        oos_trade_pnl=tuple(value + 100.0 for value in result.robustness.oos_trade_pnl),
    )
    forged = replace(result, robustness=robustness)
    with pytest.raises(ValueError, match="does not match WFO"):
        build_evidence_export(forged, _provenance())


def test_dataset_export_binds_validation_provenance_and_evidence():
    result = _dataset_result()
    payload = build_dataset_evidence_export(result)
    assert payload["dataset"]["sha256"] == result.provenance.sha256
    assert payload["dataset_validation"]["bar_count"] == 9
    assert payload["evidence"]["oos_trade_count"] == 2
    assert payload["dataset_consistency"][0]["consistent"] is True
    assert payload["dataset_consistency"][0]["left_dataset_sha256"] == result.provenance.sha256
    assert len(payload["dataset_consistency"][0]["right_dataset_sha256"]) == 64
    assert payload["dataset_coverage_policy"]["minimum_history_seconds"] == 1200.0
    assert payload["dataset_coverage_policy"]["max_gap_seconds"] == 600.0
    assert payload["dataset_validation"]["maximum_observed_gap_seconds"] == 300.0
    assert serialize_dataset_evidence_export(result) == serialize_dataset_evidence_export(result)
    assert fingerprint_dataset_evidence_export(result) == fingerprint_dataset_evidence_export(result)


def test_dataset_export_rejects_validation_detached_from_provenance():
    result = _dataset_result()
    invalid_validation = replace(
        result.validation,
        first_timestamp=result.validation.first_timestamp - timedelta(days=1),
    )
    with pytest.raises(ValueError, match="does not match provenance"):
        build_dataset_evidence_export(replace(result, validation=invalid_validation))


def test_dataset_export_rejects_failed_source_consistency_check():
    result = _dataset_result()
    failed = replace(result.consistency_checks[0], allowed_median_pct=0.0)
    with pytest.raises(ValueError, match="consistency must pass"):
        build_dataset_evidence_export(replace(result, consistency_checks=(failed,)))


def test_saved_dataset_export_verifies_against_independent_fingerprint():
    result = _dataset_result()
    serialized = serialize_dataset_evidence_export(result)
    digest = fingerprint_dataset_evidence_export(result)
    assert verify_serialized_dataset_evidence_export(serialized, digest) is True


def test_saved_dataset_export_rejects_internally_forged_consistency_result():
    result = _dataset_result()
    payload = build_dataset_evidence_export(result)
    check = payload["dataset_consistency"][0]
    check["median_difference_pct"] = 99.0
    forged = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=lambda value: value.isoformat()
    )
    forged_digest = sha256(forged.encode("utf-8")).hexdigest()
    assert verify_serialized_dataset_evidence_export(forged, forged_digest) is False


def test_saved_dataset_export_rejects_unsatisfied_coverage_policy():
    result = _dataset_result()
    payload = build_dataset_evidence_export(result)
    payload["dataset_coverage_policy"]["minimum_history_seconds"] = 3600.0
    forged = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=lambda value: value.isoformat()
    )
    forged_digest = sha256(forged.encode("utf-8")).hexdigest()
    assert verify_serialized_dataset_evidence_export(forged, forged_digest) is False


def test_saved_dataset_export_rejects_gap_policy_below_observed_gap():
    payload = build_dataset_evidence_export(_dataset_result())
    payload["dataset_coverage_policy"]["max_gap_seconds"] = 250.0
    forged = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=lambda value: value.isoformat()
    )
    forged_digest = sha256(forged.encode("utf-8")).hexdigest()
    assert verify_serialized_dataset_evidence_export(forged, forged_digest) is False


def test_saved_dataset_export_rejects_tampering_and_forged_gate():
    result = _dataset_result()
    serialized = serialize_dataset_evidence_export(result)
    digest = fingerprint_dataset_evidence_export(result)
    changed_text = serialized.replace('"oos_net_pnl":', '"oos_net_pnl":0, "discarded":')
    assert verify_serialized_dataset_evidence_export(changed_text, digest) is False

    payload = json.loads(serialized)
    payload["gate"]["passed"] = not payload["gate"]["passed"]
    forged = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    forged_digest = sha256(forged.encode("utf-8")).hexdigest()
    assert verify_serialized_dataset_evidence_export(forged, forged_digest) is False


def test_saved_dataset_export_rejects_duplicate_json_keys():
    result = _dataset_result()
    serialized = serialize_dataset_evidence_export(result)
    digest = fingerprint_dataset_evidence_export(result)
    duplicated = serialized.replace('{"dataset":', '{"schema_version":"3","dataset":', 1)
    assert verify_serialized_dataset_evidence_export(duplicated, digest) is False


def test_saved_dataset_export_rejects_boolean_report_metric_even_with_new_hash():
    result = _dataset_result()
    payload = json.loads(serialize_dataset_evidence_export(result))
    payload["evidence"]["oos_net_pnl"] = True
    malformed = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = sha256(malformed.encode("utf-8")).hexdigest()
    assert verify_serialized_dataset_evidence_export(malformed, digest) is False


def test_saved_dataset_export_recomputes_monte_carlo_summary():
    result = _dataset_result()
    payload = json.loads(serialize_dataset_evidence_export(result))
    payload["monte_carlo_evidence"]["summary"]["worst_ending_equity"] += 50.0
    forged = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = sha256(forged.encode("utf-8")).hexdigest()
    assert verify_serialized_dataset_evidence_export(forged, digest) is False


def test_export_requires_fixed_monte_carlo_seed_for_reproducible_artifact():
    result = _result()
    unseeded_robustness = replace(result.robustness, seed=None)
    unseeded = replace(result, robustness=unseeded_robustness)
    with pytest.raises(ValueError, match="fixed Monte Carlo seed"):
        build_evidence_export(unseeded, _provenance())


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"sha256": None}, "lowercase SHA-256"),
        ({"bar_count": True}, "bar_count must be positive"),
        ({"first_timestamp": datetime(2026, 1, 1)}, "timezone-aware datetime"),
    ],
)
def test_export_rejects_malformed_provenance(changes, message):
    invalid = replace(_provenance(), **changes)
    with pytest.raises(ValueError, match=message):
        build_evidence_export(_result(), invalid)
