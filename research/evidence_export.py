"""Deterministic JSON export for SHREEK V5.2 research evidence."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import hmac
from math import isclose, isfinite
from typing import Any

from research.dataset_provenance import DatasetProvenance
from research.dataset_consistency import DatasetConsistency, PRICE_COMPARISON_METRIC
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult, evaluate_oos_evidence
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_report import OOSEvidenceReport, build_oos_evidence_report
from research.dataset_runner import DatasetResearchResult
from research.data_validation import MarketDataValidation
from core.research_metrics import calculate_research_metrics
from core.risk_simulation import monte_carlo


EXPORT_SCHEMA_VERSION = "10"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported evidence export value: {type(value).__name__}")


def build_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> dict[str, Any]:
    """Build a JSON-safe, deterministic evidence payload with its exact gate policy."""
    if not isinstance(result, EvidencePipelineResult):
        raise ValueError("result must be an EvidencePipelineResult")
    if not isinstance(provenance, DatasetProvenance):
        raise ValueError("provenance must be DatasetProvenance")
    provenance.validate()
    result.report.validate()
    result.policy.validate()
    expected_report = build_oos_evidence_report(result.wfo, result.robustness)
    if result.robustness.oos_trade_pnl != result.wfo.oos_trade_pnl:
        raise ValueError("Monte Carlo trade P&L does not match WFO OOS trades")
    result.robustness.validate(require_reproducible=True)
    if len(result.wfo.oos_metrics) != len(result.wfo.oos_results):
        raise ValueError("WFO metrics do not match the number of OOS results")
    for metric, backtest in zip(result.wfo.oos_metrics, result.wfo.oos_results):
        if metric != calculate_research_metrics(backtest):
            raise ValueError("WFO metrics do not match their OOS backtests")
    if result.report != expected_report:
        raise ValueError("evidence report does not match WFO and Monte Carlo results")
    if not isinstance(result.gate, EvidenceGateResult):
        raise ValueError("gate must be an EvidenceGateResult")
    expected_gate = evaluate_oos_evidence(result.report, result.policy)
    if result.gate != expected_gate:
        raise ValueError("gate result does not match report and policy")
    policy_payload = asdict(result.policy)
    if policy_payload["max_worst_drawdown"] == float("inf"):
        # JSON has no representation for infinity. Null means that this
        # optional drawdown ceiling is intentionally unbounded.
        policy_payload["max_worst_drawdown"] = None
    payload = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "dataset": asdict(provenance),
        "evidence": asdict(result.report),
        "gate": asdict(result.gate),
        "gate_policy": policy_payload,
        "wfo_evidence": {
            "oos_windows_trade_pnl": [
                [trade.net_pnl for trade in backtest.trades]
                for backtest in result.wfo.oos_results
            ],
        },
        "monte_carlo_evidence": {
            "oos_trade_pnl": list(result.robustness.oos_trade_pnl),
            "starting_equity": result.robustness.starting_equity,
            "simulations": result.robustness.simulations,
            "seed": result.robustness.seed,
            "slippage_multiplier": result.robustness.slippage_multiplier,
            "spread_multiplier": result.robustness.spread_multiplier,
            "summary": asdict(result.robustness.summary),
        },
    }
    return payload


def build_dataset_evidence_export(result: DatasetResearchResult) -> dict[str, Any]:
    """Export one dataset run with its validation, provenance, evidence, and gate."""
    if not isinstance(result, DatasetResearchResult):
        raise ValueError("result must be a DatasetResearchResult")
    for check in result.consistency_checks:
        if not isinstance(check, DatasetConsistency):
            raise ValueError("dataset consistency checks have an invalid type")
        check.validate()
        if not check.consistent:
            raise ValueError("dataset source consistency must pass before export")
    if not isinstance(result.validation, MarketDataValidation) or not result.validation.valid:
        raise ValueError("dataset validation must pass before export")
    result.provenance.validate()
    minimum_history_seconds = result.minimum_history_seconds
    max_gap_seconds = result.max_gap_seconds
    if minimum_history_seconds is not None and (
        isinstance(minimum_history_seconds, bool)
        or not isinstance(minimum_history_seconds, (int, float))
        or not isfinite(minimum_history_seconds)
        or minimum_history_seconds <= 0
    ):
        raise ValueError("minimum history policy must be finite and positive")
    if max_gap_seconds is not None and (
        isinstance(max_gap_seconds, bool)
        or not isinstance(max_gap_seconds, (int, float))
        or not isfinite(max_gap_seconds)
        or max_gap_seconds <= 0
    ):
        raise ValueError("maximum gap policy must be finite and positive")
    if max_gap_seconds is not None and result.validation.gaps_over_limit != 0:
        raise ValueError("dataset does not satisfy its maximum gap policy")
    actual_history_seconds = (
        result.validation.last_timestamp.astimezone(timezone.utc)
        - result.validation.first_timestamp.astimezone(timezone.utc)
    ).total_seconds()
    if minimum_history_seconds is not None and actual_history_seconds < minimum_history_seconds:
        raise ValueError("dataset does not satisfy its minimum history policy")
    if any(
        check.left_dataset_sha256 != result.provenance.sha256
        for check in result.consistency_checks
    ):
        raise ValueError("dataset consistency fingerprint does not match the primary dataset")
    if (
        result.validation.bar_count != result.provenance.bar_count
        or result.validation.first_timestamp != result.provenance.first_timestamp
        or result.validation.last_timestamp != result.provenance.last_timestamp
    ):
        raise ValueError("dataset validation does not match provenance")
    payload = build_evidence_export(result.evidence, result.provenance)
    payload["dataset_validation"] = asdict(result.validation)
    payload["dataset_coverage_policy"] = {
        "minimum_history_seconds": minimum_history_seconds,
        "max_gap_seconds": max_gap_seconds,
    }
    payload["dataset_consistency"] = [
        {**asdict(check), "price_comparison_metric": PRICE_COMPARISON_METRIC,
         "consistent": check.consistent}
        for check in result.consistency_checks
    ]
    return payload


def serialize_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> str:
    """Serialize evidence deterministically for archival or comparison."""
    payload = build_evidence_export(result, provenance)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default, allow_nan=False)


def fingerprint_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> str:
    """Return SHA-256 identity of the canonical evidence export."""
    canonical = serialize_evidence_export(result, provenance)
    return sha256(canonical.encode("utf-8")).hexdigest()


def serialize_dataset_evidence_export(result: DatasetResearchResult) -> str:
    """Serialize a complete validated-dataset research run deterministically."""
    payload = build_dataset_evidence_export(result)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default, allow_nan=False)


def fingerprint_dataset_evidence_export(result: DatasetResearchResult) -> str:
    """Return SHA-256 identity of the complete dataset research export."""
    canonical = serialize_dataset_evidence_export(result)
    return sha256(canonical.encode("utf-8")).hexdigest()


def verify_serialized_dataset_evidence_export(
    serialized: str,
    expected_sha256: str,
) -> bool:
    """Validate a saved dataset export against a separately retained digest.

    This checks strict JSON shape, dataset/provenance agreement, report and
    gate consistency, and the canonical content hash. The expected digest
    must be retained separately from the artifact to detect later edits.
    """
    if not isinstance(serialized, str) or not isinstance(expected_sha256, str):
        return False
    if (
        len(expected_sha256) != 64
        or any(char not in "0123456789abcdef" for char in expected_sha256)
    ):
        return False

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON number: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            serialized,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
        expected_keys = {
            "schema_version", "dataset", "dataset_validation", "dataset_coverage_policy",
            "dataset_consistency", "evidence",
            "gate", "gate_policy", "wfo_evidence", "monte_carlo_evidence",
        }
        if not isinstance(payload, dict) or set(payload) != expected_keys:
            return False
        if payload["schema_version"] != EXPORT_SCHEMA_VERSION:
            return False

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if not hmac.compare_digest(sha256(canonical).hexdigest(), expected_sha256):
            return False

        dataset = payload["dataset"]
        validation_data = payload["dataset_validation"]
        if (
            not isinstance(dataset, dict)
            or set(dataset) != {"schema_version", "sha256", "bar_count", "first_timestamp", "last_timestamp"}
            or not isinstance(validation_data, dict)
            or set(validation_data) != {
                "bar_count", "first_timestamp", "last_timestamp", "duplicate_timestamps",
                "non_monotonic_pairs", "gaps_over_limit", "maximum_observed_gap_seconds",
            }
        ):
            return False
        provenance = DatasetProvenance(
            dataset["schema_version"],
            dataset["sha256"],
            dataset["bar_count"],
            datetime.fromisoformat(dataset["first_timestamp"]),
            datetime.fromisoformat(dataset["last_timestamp"]),
        )
        provenance.validate()
        coverage_policy = payload["dataset_coverage_policy"]
        if not isinstance(coverage_policy, dict) or set(coverage_policy) != {
            "minimum_history_seconds", "max_gap_seconds",
        }:
            return False
        minimum_history = coverage_policy["minimum_history_seconds"]
        max_gap = coverage_policy["max_gap_seconds"]
        if minimum_history is not None and (
            isinstance(minimum_history, bool)
            or not isinstance(minimum_history, (int, float))
            or not isfinite(minimum_history)
            or minimum_history <= 0
        ):
            return False
        if max_gap is not None and (
            isinstance(max_gap, bool)
            or not isinstance(max_gap, (int, float))
            or not isfinite(max_gap)
            or max_gap <= 0
        ):
            return False
        maximum_observed_gap = validation_data["maximum_observed_gap_seconds"]
        if maximum_observed_gap is not None and (
            isinstance(maximum_observed_gap, bool)
            or not isinstance(maximum_observed_gap, (int, float))
            or not isfinite(maximum_observed_gap)
            or maximum_observed_gap < 0
        ):
            return False
        if (
            max_gap is not None
            and maximum_observed_gap is not None
            and maximum_observed_gap > max_gap
        ):
            return False
        actual_history_seconds = (
            provenance.last_timestamp.astimezone(timezone.utc)
            - provenance.first_timestamp.astimezone(timezone.utc)
        ).total_seconds()
        if minimum_history is not None and actual_history_seconds < minimum_history:
            return False
        validation = MarketDataValidation(
            validation_data["bar_count"],
            datetime.fromisoformat(validation_data["first_timestamp"]),
            datetime.fromisoformat(validation_data["last_timestamp"]),
            validation_data["duplicate_timestamps"],
            validation_data["non_monotonic_pairs"],
            validation_data["gaps_over_limit"],
            maximum_observed_gap,
        )
        if any(
            type(value) is not int
            for value in (
                validation.bar_count,
                validation.duplicate_timestamps,
                validation.non_monotonic_pairs,
                validation.gaps_over_limit,
            )
        ):
            return False
        if (
            not validation.valid
            or (max_gap is not None and validation.gaps_over_limit != 0)
            or validation.bar_count != provenance.bar_count
            or validation.first_timestamp != provenance.first_timestamp
            or validation.last_timestamp != provenance.last_timestamp
        ):
            return False

        consistency = payload["dataset_consistency"]
        if not isinstance(consistency, list):
            return False
        consistency_fields = {
            "common_timestamps", "median_difference_pct", "p95_difference_pct",
            "max_difference_pct", "left_dataset_sha256", "right_dataset_sha256",
            "left_interval_seconds", "right_interval_seconds",
            "allowed_median_pct", "allowed_p95_pct",
            "minimum_common_timestamps", "price_comparison_metric", "consistent",
        }
        for check in consistency:
            if not isinstance(check, dict) or set(check) != consistency_fields:
                return False
            if check["price_comparison_metric"] != PRICE_COMPARISON_METRIC:
                return False
            common = check["common_timestamps"]
            minimum = check["minimum_common_timestamps"]
            if type(common) is not int or common < 0 or type(minimum) is not int or minimum < 1:
                return False
            if type(check["consistent"]) is not bool:
                return False
            for digest_name in ("left_dataset_sha256", "right_dataset_sha256"):
                digest = check[digest_name]
                if not isinstance(digest, str) or len(digest) != 64 or any(
                    char not in "0123456789abcdef" for char in digest
                ):
                    return False
            for interval_name in ("left_interval_seconds", "right_interval_seconds"):
                interval = check[interval_name]
                if interval is not None and (
                    isinstance(interval, bool)
                    or not isinstance(interval, (int, float))
                    or not isfinite(interval)
                    or interval <= 0
                ):
                    return False
            limits = ("allowed_median_pct", "allowed_p95_pct")
            if any(
                isinstance(check[name], bool)
                or not isinstance(check[name], (int, float))
                or not isfinite(check[name])
                or check[name] < 0
                for name in limits
            ):
                return False
            metrics = ("median_difference_pct", "p95_difference_pct", "max_difference_pct")
            values = [check[name] for name in metrics]
            if common == 0 and any(value is not None for value in values):
                return False
            if common > 0 and any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
                for value in values
            ):
                return False
            if common > 0 and not (
                check["median_difference_pct"]
                <= check["p95_difference_pct"]
                <= check["max_difference_pct"]
            ):
                return False
            expected_consistent = (
                check["left_interval_seconds"] is not None
                and check["left_interval_seconds"] == check["right_interval_seconds"]
                and common >= minimum
                and check["median_difference_pct"] is not None
                and check["p95_difference_pct"] is not None
                and check["median_difference_pct"] <= check["allowed_median_pct"]
                and check["p95_difference_pct"] <= check["allowed_p95_pct"]
            )
            if check["consistent"] is not expected_consistent or not expected_consistent:
                return False

        evidence_data = payload["evidence"]
        report_fields = {
            "oos_trade_count", "oos_net_pnl", "oos_expectancy", "oos_stability_pct",
            "positive_oos_windows", "oos_window_count", "ruin_rate_pct",
            "median_ending_equity", "worst_ending_equity", "median_max_drawdown",
            "worst_max_drawdown", "simulations",
        }
        if not isinstance(evidence_data, dict) or set(evidence_data) != report_fields:
            return False
        report_numeric_fields = report_fields - {
            "oos_trade_count", "positive_oos_windows", "oos_window_count", "simulations",
        }
        if any(
            isinstance(evidence_data[name], bool)
            or not isinstance(evidence_data[name], (int, float))
            for name in report_numeric_fields
        ):
            return False
        report = OOSEvidenceReport(**evidence_data)
        report.validate()

        wfo_data = payload["wfo_evidence"]
        if (
            not isinstance(wfo_data, dict)
            or set(wfo_data) != {"oos_windows_trade_pnl"}
            or not isinstance(wfo_data["oos_windows_trade_pnl"], list)
        ):
            return False
        windows = wfo_data["oos_windows_trade_pnl"]
        if len(windows) != report.oos_window_count or any(not isinstance(window, list) for window in windows):
            return False
        for window in windows:
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                for value in window
            ):
                return False
        flattened_pnl = [value for window in windows for value in window]
        if not flattened_pnl or len(flattened_pnl) != report.oos_trade_count:
            return False

        mc_data = payload["monte_carlo_evidence"]
        mc_keys = {
            "oos_trade_pnl", "starting_equity", "simulations", "seed",
            "slippage_multiplier", "spread_multiplier", "summary",
        }
        if not isinstance(mc_data, dict) or set(mc_data) != mc_keys:
            return False
        mc_pnl = mc_data["oos_trade_pnl"]
        if not isinstance(mc_pnl, list) or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            for value in mc_pnl
        ) or flattened_pnl != mc_pnl:
            return False
        starting_equity = mc_data["starting_equity"]
        simulations = mc_data["simulations"]
        seed = mc_data["seed"]
        slippage = mc_data["slippage_multiplier"]
        spread = mc_data["spread_multiplier"]
        if (
            isinstance(starting_equity, bool)
            or not isinstance(starting_equity, (int, float))
            or type(simulations) is not int
            or type(seed) is not int
            or isinstance(slippage, bool)
            or not isinstance(slippage, (int, float))
            or isinstance(spread, bool)
            or not isinstance(spread, (int, float))
        ):
            return False
        expected_mc = asdict(monte_carlo(
            mc_pnl,
            starting_equity=starting_equity,
            simulations=simulations,
            seed=seed,
            slippage_multiplier=slippage,
            spread_multiplier=spread,
        ))
        summary_data = mc_data["summary"]
        if not isinstance(summary_data, dict) or summary_data != expected_mc:
            return False

        total_trades = sum(len(window) for window in windows)
        if total_trades <= 0:
            return False
        wfo_net = sum(sum(window) for window in windows)
        expectancy = wfo_net / total_trades
        positive_windows = sum(sum(window) > 0 for window in windows)
        if not (
            isclose(wfo_net, report.oos_net_pnl, rel_tol=1e-12, abs_tol=1e-12)
            and isclose(expectancy, report.oos_expectancy, rel_tol=1e-12, abs_tol=1e-12)
            and positive_windows == report.positive_oos_windows
            and isclose(
                positive_windows / len(windows) * 100.0,
                report.oos_stability_pct,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            and report.simulations == simulations
            and report.ruin_rate_pct == expected_mc["ruin_rate_pct"]
            and report.median_ending_equity == expected_mc["median_ending_equity"]
            and report.worst_ending_equity == expected_mc["worst_ending_equity"]
            and report.median_max_drawdown == expected_mc["median_max_drawdown"]
            and report.worst_max_drawdown == expected_mc["worst_max_drawdown"]
        ):
            return False

        policy_values = payload["gate_policy"]
        if not isinstance(policy_values, dict) or set(policy_values) != {
            "min_oos_trades", "min_expectancy", "min_oos_stability_pct",
            "max_ruin_rate_pct", "max_worst_drawdown",
        }:
            return False
        policy_values = dict(policy_values)
        if policy_values.get("max_worst_drawdown") is None:
            policy_values["max_worst_drawdown"] = float("inf")
        policy = EvidenceGatePolicy(**policy_values)
        policy.validate()
        gate_data = payload["gate"]
        if (
            not isinstance(gate_data, dict)
            or set(gate_data) != {"passed", "failures"}
            or type(gate_data.get("passed")) is not bool
            or not isinstance(gate_data.get("failures"), list)
            or any(not isinstance(item, str) for item in gate_data["failures"])
        ):
            return False
        gate = EvidenceGateResult(gate_data["passed"], tuple(gate_data["failures"]))
        return gate == evaluate_oos_evidence(report, policy)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OverflowError):
        return False
