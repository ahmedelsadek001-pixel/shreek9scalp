"""Deterministic JSON export for SHREEK V5.2 research evidence."""
from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from math import isclose
from typing import Any

from research.dataset_provenance import DatasetProvenance
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_gate import evaluate_oos_evidence


EXPORT_SCHEMA_VERSION = "3"


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
    expected_gate = evaluate_oos_evidence(result.report, result.policy)
    if result.gate != expected_gate:
        raise ValueError("evidence gate result does not match report and policy")
    payload = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "dataset": asdict(provenance),
        "evidence": asdict(result.report),
        "gate": asdict(result.gate),
        "gate_policy": {**asdict(result.policy), "max_worst_drawdown": (None if result.policy.max_worst_drawdown == float("inf") else result.policy.max_worst_drawdown)},
    }
    statistical = (result.interval, result.bootstrap, result.certification)
    if any(item is not None for item in statistical):
        if any(item is None for item in statistical):
            raise ValueError("statistical certification evidence must be complete")
        result.interval.validate()
        result.bootstrap.validate()
        result.certification.validate()
        result.certification_policy.validate()
        certification = result.certification
        if certification.oos_trades != result.interval.samples:
            raise ValueError("certification OOS trade count does not match statistical evidence")
        if result.bootstrap.samples != result.interval.samples:
            raise ValueError("bootstrap sample count does not match confidence interval")
        if result.interval.samples != result.report.oos_trade_count:
            raise ValueError("statistical sample count does not match OOS report")
        if certification.oos_windows != result.report.oos_window_count:
            raise ValueError("certification OOS windows do not match OOS report")
        if not isclose(certification.oos_stability_pct, result.report.oos_stability_pct, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("certification OOS stability does not match OOS report")
        if not isclose(result.interval.mean, result.report.oos_expectancy, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("confidence interval mean does not match OOS report expectancy")
        if not isclose(result.bootstrap.observed_mean, result.report.oos_expectancy, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("bootstrap observed mean does not match OOS report expectancy")
        expected_failures: list[str] = []
        cert_policy = result.certification_policy
        if certification.oos_trades < cert_policy.min_oos_trades:
            expected_failures.append("insufficient OOS trades")
        if certification.oos_windows < cert_policy.min_oos_windows:
            expected_failures.append("insufficient OOS windows")
        if certification.oos_stability_pct < cert_policy.min_oos_stability_pct:
            expected_failures.append("OOS stability below minimum")
        if result.report.oos_expectancy <= 0.0:
            expected_failures.append("OOS expectancy is not positive")
        if cert_policy.require_positive_ci_lower and result.interval.lower <= 0.0:
            expected_failures.append("confidence interval does not exclude non-positive expectancy")
        if cert_policy.require_positive_bootstrap_lower and result.bootstrap.lower_mean <= 0.0:
            expected_failures.append("block bootstrap lower bound is not positive")
        if result.bootstrap.non_positive_mean_rate_pct > cert_policy.max_bootstrap_non_positive_rate_pct:
            expected_failures.append("bootstrap non-positive expectancy rate above maximum")
        if result.report.ruin_rate_pct > cert_policy.max_ruin_rate_pct:
            expected_failures.append("Monte Carlo ruin rate above maximum")
        if certification.oos_expectancy_degradation_pct > cert_policy.max_oos_expectancy_degradation_pct:
            expected_failures.append("OOS expectancy degradation above maximum")
        if certification.parameter_stability_pct < cert_policy.min_parameter_stability_pct:
            expected_failures.append("parameter stability below minimum")
        if certification.failures != tuple(expected_failures):
            raise ValueError("certification result does not match archived statistical evidence and policy")
        payload["statistical_evidence"] = {
            "confidence_interval": asdict(result.interval),
            "block_bootstrap": asdict(result.bootstrap),
            "certification": asdict(result.certification),
            "certification_policy": asdict(result.certification_policy),
        }
    return payload


def serialize_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> str:
    """Serialize evidence deterministically for archival or comparison."""
    payload = build_evidence_export(result, provenance)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)


def fingerprint_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> str:
    """Return SHA-256 identity of the canonical evidence export."""
    canonical = serialize_evidence_export(result, provenance)
    return sha256(canonical.encode("utf-8")).hexdigest()
