"""Deterministic, reproducible artifact for one SHREEK research run."""
from __future__ import annotations

import json
from math import isclose, isfinite
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from core.block_bootstrap import BlockBootstrapSummary
from core.research_certification import ResearchCertification, ResearchCertificationPolicy
from core.statistical_evidence import MeanConfidenceInterval
from research.dataset_provenance import DatasetProvenance
from research.evidence_export import serialize_evidence_export
from research.evidence_pipeline import EvidencePipelineResult, ResearchRunConfig
from research.evidence_report import OOSEvidenceReport


ARTIFACT_SCHEMA_VERSION = "1"


def _reject_nonstandard_json_constant(value: str) -> None:
    """Reject NaN/Infinity tokens accepted by Python's permissive JSON parser."""
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def _serialized_dataset(dataset: DatasetProvenance) -> dict[str, Any]:
    """Return the exact JSON representation used by the evidence exporter."""
    return json.loads(json.dumps(asdict(dataset), sort_keys=True, default=str))


def _validate_embedded_export(payload: dict[str, Any]) -> None:
    """Fail closed on malformed or internally inconsistent archived evidence."""
    schema = payload.get("schema_version")
    required = {"schema_version", "dataset", "evidence", "gate", "gate_policy"}
    if not required.issubset(payload):
        raise ValueError("evidence export is missing required sections")
    for name in ("dataset", "evidence", "gate", "gate_policy"):
        if not isinstance(payload[name], dict):
            raise ValueError(f"evidence export {name} must be an object")
    evidence = payload["evidence"]
    gate = payload["gate"]
    policy = payload["gate_policy"]
    numeric_policy = ("min_expectancy", "min_oos_stability_pct", "max_ruin_rate_pct")
    if type(policy.get("min_oos_trades")) is not int or policy["min_oos_trades"] <= 0:
        raise ValueError("evidence export gate policy trade minimum is invalid")
    if any(type(policy.get(name)) not in (int, float) for name in numeric_policy):
        raise ValueError("evidence export gate policy numeric values are invalid")
    finite_policy = numeric_policy
    if any(not isfinite(float(policy[name])) for name in finite_policy):
        raise ValueError("evidence export gate policy numeric values must be finite")
    if not 0.0 <= float(policy["min_oos_stability_pct"]) <= 100.0:
        raise ValueError("evidence export gate policy stability minimum is invalid")
    if float(policy["max_ruin_rate_pct"]) < 0.0:
        raise ValueError("evidence export gate policy ruin maximum is invalid")
    raw_max_drawdown = policy.get("max_worst_drawdown")
    if raw_max_drawdown is None:
        max_drawdown = float("inf")
    elif type(raw_max_drawdown) in (int, float) and isfinite(float(raw_max_drawdown)) and float(raw_max_drawdown) >= 0:
        max_drawdown = float(raw_max_drawdown)
    else:
        raise ValueError("evidence export gate policy drawdown maximum is invalid")
    if type(evidence.get("oos_trade_count")) is not int or evidence["oos_trade_count"] < 0:
        raise ValueError("evidence export OOS trade count is invalid")
    evidence_numeric = ("oos_expectancy", "oos_stability_pct", "ruin_rate_pct", "worst_max_drawdown")
    if any(type(evidence.get(name)) not in (int, float) or not isfinite(float(evidence[name])) for name in evidence_numeric):
        raise ValueError("evidence export numeric evidence must be finite numbers")
    if type(gate.get("passed")) is not bool or not isinstance(gate.get("failures"), list):
        raise ValueError("evidence export gate is malformed")
    if gate["passed"] != (len(gate["failures"]) == 0):
        raise ValueError("evidence export gate pass state is inconsistent")
    if any(type(item) is not str or not item for item in gate["failures"]):
        raise ValueError("evidence export gate failures are malformed")
    if gate["passed"]:
        if evidence["oos_trade_count"] < policy["min_oos_trades"]:
            raise ValueError("passing gate contradicts OOS trade minimum")
        if evidence.get("oos_expectancy") < policy["min_expectancy"]:
            raise ValueError("passing gate contradicts expectancy minimum")
        if evidence.get("oos_stability_pct") < policy["min_oos_stability_pct"]:
            raise ValueError("passing gate contradicts stability minimum")
        if evidence.get("ruin_rate_pct") > policy["max_ruin_rate_pct"]:
            raise ValueError("passing gate contradicts ruin-rate maximum")
        if evidence.get("worst_max_drawdown") > max_drawdown:
            raise ValueError("passing gate contradicts drawdown maximum")
    expected_gate_failures: list[str] = []
    if evidence["oos_trade_count"] < policy["min_oos_trades"]:
        expected_gate_failures.append("OOS trade count below minimum")
    if evidence["oos_expectancy"] < policy["min_expectancy"]:
        expected_gate_failures.append("OOS expectancy below minimum")
    if evidence["oos_stability_pct"] < policy["min_oos_stability_pct"]:
        expected_gate_failures.append("OOS stability below minimum")
    if evidence["ruin_rate_pct"] > policy["max_ruin_rate_pct"]:
        expected_gate_failures.append("Monte Carlo ruin rate above maximum")
    if evidence["worst_max_drawdown"] > max_drawdown:
        expected_gate_failures.append("worst OOS Monte Carlo drawdown above maximum")
    if gate["failures"] != expected_gate_failures:
        raise ValueError("archived gate failures do not match evidence and policy")
    try:
        archived_report = OOSEvidenceReport(**evidence)
    except TypeError as exc:
        raise ValueError("archived OOS evidence structure is invalid") from exc
    archived_report.validate()
    wfo = payload.get("wfo_evidence")
    if wfo is not None:
        if not isinstance(wfo, dict) or set(wfo) != {
            "windows", "train_scores", "test_scores", "selected_parameters"
        }:
            raise ValueError("archived WFO evidence structure is invalid")
        windows = wfo["windows"]
        train_scores = wfo["train_scores"]
        test_scores = wfo["test_scores"]
        selected = wfo["selected_parameters"]
        count = evidence.get("oos_window_count")
        if (
            not isinstance(windows, list)
            or not isinstance(train_scores, list)
            or not isinstance(test_scores, list)
            or not isinstance(selected, list)
            or not len(windows) == len(train_scores) == len(test_scores) == len(selected) == count
        ):
            raise ValueError("archived WFO evidence cardinality does not match OOS report")
        expected_window_fields = {
            "train_start", "train_end", "purge_start", "purge_end", "test_start", "test_end"
        }
        previous_test_end = None
        for window in windows:
            if not isinstance(window, dict) or set(window) != expected_window_fields:
                raise ValueError("archived WFO window structure is invalid")
            if any(type(window[name]) is not int for name in expected_window_fields):
                raise ValueError("archived WFO window boundaries must be integers")
            if not (
                0 <= window["train_start"] < window["train_end"]
                and window["train_end"] == window["purge_start"]
                and window["purge_start"] <= window["purge_end"]
                and window["purge_end"] == window["test_start"]
                and window["test_start"] < window["test_end"]
            ):
                raise ValueError("archived WFO window geometry is invalid")
            if previous_test_end is not None and window["test_start"] < previous_test_end:
                raise ValueError("archived WFO OOS windows must not overlap")
            previous_test_end = window["test_end"]
        for scores in (train_scores, test_scores):
            if any(type(value) not in (int, float) or not isfinite(float(value)) for value in scores):
                raise ValueError("archived WFO scores must be finite numbers")
        for params in selected:
            if not isinstance(params, dict) or any(type(key) is not str or not key for key in params):
                raise ValueError("archived WFO selected parameters are invalid")
    config_payload = payload.get("research_config")
    if (wfo is None) != (config_payload is None):
        raise ValueError("archived WFO evidence and research config must be present together")
    archived_config = None
    if config_payload is not None:
        if not isinstance(config_payload, dict):
            raise ValueError("archived research config must be an object")
        try:
            archived_config = ResearchRunConfig(
                **{
                    **config_payload,
                    "candidate_parameters": tuple(config_payload["candidate_parameters"]),
                }
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("archived research config structure is invalid") from exc
        archived_config.validate()
        if evidence["simulations"] != archived_config.simulations:
            raise ValueError("archived research simulations do not match OOS report")
        candidates = list(archived_config.candidate_parameters)
        if any(params not in candidates for params in selected):
            raise ValueError("archived selected WFO parameters are absent from candidate grid")
        for index, window in enumerate(windows):
            if window["train_end"] - window["train_start"] != archived_config.train_size:
                raise ValueError("archived WFO train size does not match research config")
            if window["test_end"] - window["test_start"] != archived_config.test_size:
                raise ValueError("archived WFO test size does not match research config")
            if window["purge_end"] - window["purge_start"] != archived_config.purge_size:
                raise ValueError("archived WFO purge size does not match research config")
            if index and window["train_start"] - windows[index - 1]["train_start"] != archived_config.step:
                raise ValueError("archived WFO step does not match research config")
    if schema == "3":
        statistical = payload.get("statistical_evidence")
        if statistical is not None:
            if not isinstance(statistical, dict):
                raise ValueError("statistical evidence must be an object")
            names = {"confidence_interval", "block_bootstrap", "certification", "certification_policy"}
            if set(statistical) != names:
                raise ValueError("statistical evidence sections are incomplete")
            if any(not isinstance(statistical[name], dict) for name in names):
                raise ValueError("statistical evidence sections must be objects")
            interval = statistical["confidence_interval"]
            bootstrap = statistical["block_bootstrap"]
            certification = statistical["certification"]
            if type(interval.get("samples")) is not int or interval["samples"] < 1:
                raise ValueError("confidence interval sample count is invalid")
            if bootstrap.get("samples") != interval["samples"]:
                raise ValueError("bootstrap sample count does not match confidence interval")
            if certification.get("oos_trades") != interval["samples"]:
                raise ValueError("certification OOS trades do not match statistical evidence")
            if interval["samples"] != evidence["oos_trade_count"]:
                raise ValueError("statistical evidence samples do not match archived OOS trade count")
            if certification.get("oos_windows") != evidence.get("oos_window_count"):
                raise ValueError("certification OOS windows do not match archived evidence")
            passed = certification.get("passed")
            failures = certification.get("failures")
            if type(passed) is not bool or not isinstance(failures, list):
                raise ValueError("embedded certification is malformed")
            if passed != (len(failures) == 0):
                raise ValueError("embedded certification pass state is inconsistent")
            if any(type(item) is not str or not item for item in failures):
                raise ValueError("embedded certification failures are malformed")
            interval_numeric = ("mean", "lower", "upper")
            if any(type(interval.get(name)) not in (int, float) or not isfinite(float(interval[name])) for name in interval_numeric):
                raise ValueError("confidence interval numeric evidence must be finite")
            bootstrap_numeric = ("observed_mean", "median_mean", "lower_mean", "upper_mean", "non_positive_mean_rate_pct")
            if any(type(bootstrap.get(name)) not in (int, float) or not isfinite(float(bootstrap[name])) for name in bootstrap_numeric):
                raise ValueError("block bootstrap numeric evidence must be finite")
            certification_numeric = ("oos_stability_pct", "oos_expectancy_degradation_pct", "parameter_stability_pct")
            if any(type(certification.get(name)) not in (int, float) or not isfinite(float(certification[name])) for name in certification_numeric):
                raise ValueError("certification numeric evidence must be finite")
            if not isclose(float(certification["oos_stability_pct"]), float(evidence["oos_stability_pct"]), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("certification OOS stability does not match archived evidence")
            if wfo is not None:
                mode_count = max(selected.count(params) for params in selected)
                archived_parameter_stability = mode_count / len(selected) * 100.0
                if not isclose(
                    float(certification["parameter_stability_pct"]),
                    archived_parameter_stability,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    raise ValueError("certification parameter stability does not match archived WFO selections")
            if not isclose(float(interval["mean"]), float(evidence["oos_expectancy"]), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("confidence interval mean does not match archived OOS expectancy")
            if not isclose(float(bootstrap["observed_mean"]), float(evidence["oos_expectancy"]), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("bootstrap observed mean does not match archived OOS expectancy")
            cert_policy = statistical["certification_policy"]
            required_policy = {
                "min_oos_trades", "min_oos_windows", "min_oos_stability_pct",
                "require_positive_ci_lower", "require_positive_bootstrap_lower",
                "max_bootstrap_non_positive_rate_pct", "max_ruin_rate_pct",
                "max_oos_expectancy_degradation_pct", "min_parameter_stability_pct",
            }
            if not required_policy.issubset(cert_policy):
                raise ValueError("embedded certification policy is incomplete")
            if type(cert_policy["min_oos_trades"]) is not int or cert_policy["min_oos_trades"] < 2:
                raise ValueError("certification policy OOS trade minimum is invalid")
            if type(cert_policy["min_oos_windows"]) is not int or cert_policy["min_oos_windows"] < 1:
                raise ValueError("certification policy OOS window minimum is invalid")
            for name in ("require_positive_ci_lower", "require_positive_bootstrap_lower"):
                if type(cert_policy[name]) is not bool:
                    raise ValueError("certification policy switches must be bools")
            cert_policy_numeric = ("min_oos_stability_pct", "max_bootstrap_non_positive_rate_pct", "max_ruin_rate_pct", "max_oos_expectancy_degradation_pct", "min_parameter_stability_pct")
            for name in cert_policy_numeric:
                if type(cert_policy[name]) not in (int, float) or not isfinite(float(cert_policy[name])) or not 0.0 <= float(cert_policy[name]) <= 100.0:
                    raise ValueError("certification policy numeric values must be finite and between 0 and 100")
            if passed:
                if certification["oos_trades"] < cert_policy["min_oos_trades"]:
                    raise ValueError("passing certification contradicts OOS trade minimum")
                if certification.get("oos_windows", 0) < cert_policy["min_oos_windows"]:
                    raise ValueError("passing certification contradicts OOS window minimum")
                if certification.get("oos_stability_pct", -1) < cert_policy["min_oos_stability_pct"]:
                    raise ValueError("passing certification contradicts stability minimum")
                if cert_policy["require_positive_ci_lower"] and interval.get("lower", 0) <= 0:
                    raise ValueError("passing certification contradicts confidence interval policy")
                if cert_policy["require_positive_bootstrap_lower"] and bootstrap.get("lower_mean", 0) <= 0:
                    raise ValueError("passing certification contradicts bootstrap lower policy")
                if bootstrap.get("non_positive_mean_rate_pct", 101) > cert_policy["max_bootstrap_non_positive_rate_pct"]:
                    raise ValueError("passing certification contradicts bootstrap rate policy")
                if evidence.get("ruin_rate_pct") > cert_policy["max_ruin_rate_pct"]:
                    raise ValueError("passing certification contradicts ruin-rate policy")
                if certification["oos_expectancy_degradation_pct"] > cert_policy["max_oos_expectancy_degradation_pct"]:
                    raise ValueError("passing certification contradicts expectancy degradation policy")
                if certification["parameter_stability_pct"] < cert_policy["min_parameter_stability_pct"]:
                    raise ValueError("passing certification contradicts parameter stability policy")
            expected_certification_failures: list[str] = []
            if certification["oos_trades"] < cert_policy["min_oos_trades"]:
                expected_certification_failures.append("insufficient OOS trades")
            if certification["oos_windows"] < cert_policy["min_oos_windows"]:
                expected_certification_failures.append("insufficient OOS windows")
            if certification["oos_stability_pct"] < cert_policy["min_oos_stability_pct"]:
                expected_certification_failures.append("OOS stability below minimum")
            if evidence["oos_expectancy"] <= 0.0:
                expected_certification_failures.append("OOS expectancy is not positive")
            if cert_policy["require_positive_ci_lower"] and interval["lower"] <= 0.0:
                expected_certification_failures.append("confidence interval does not exclude non-positive expectancy")
            if cert_policy["require_positive_bootstrap_lower"] and bootstrap["lower_mean"] <= 0.0:
                expected_certification_failures.append("block bootstrap lower bound is not positive")
            if bootstrap["non_positive_mean_rate_pct"] > cert_policy["max_bootstrap_non_positive_rate_pct"]:
                expected_certification_failures.append("bootstrap non-positive expectancy rate above maximum")
            if evidence["ruin_rate_pct"] > cert_policy["max_ruin_rate_pct"]:
                expected_certification_failures.append("Monte Carlo ruin rate above maximum")
            if certification["oos_expectancy_degradation_pct"] > cert_policy["max_oos_expectancy_degradation_pct"]:
                expected_certification_failures.append("OOS expectancy degradation above maximum")
            if certification["parameter_stability_pct"] < cert_policy["min_parameter_stability_pct"]:
                expected_certification_failures.append("parameter stability below minimum")
            if failures != expected_certification_failures:
                raise ValueError("archived certification failures do not match evidence and policy")
            try:
                archived_interval = MeanConfidenceInterval(**interval)
                archived_bootstrap = BlockBootstrapSummary(**bootstrap)
                archived_certification = ResearchCertification(
                    **{**certification, "failures": tuple(certification["failures"])}
                )
                archived_certification_policy = ResearchCertificationPolicy(**cert_policy)
            except (KeyError, TypeError) as exc:
                raise ValueError("archived statistical evidence structure is invalid") from exc
            archived_interval.validate()
            archived_bootstrap.validate()
            archived_certification.validate()
            archived_certification_policy.validate()
            if archived_config is not None:
                if not isclose(archived_interval.confidence, archived_config.confidence, rel_tol=0.0, abs_tol=0.0):
                    raise ValueError("archived confidence interval does not match research config")
                if archived_bootstrap.block_size != archived_config.bootstrap_block_size:
                    raise ValueError("archived bootstrap block size does not match research config")
                if archived_bootstrap.simulations != archived_config.bootstrap_simulations:
                    raise ValueError("archived bootstrap simulations do not match research config")
                if not isclose(archived_bootstrap.confidence, archived_config.confidence, rel_tol=0.0, abs_tol=0.0):
                    raise ValueError("archived bootstrap confidence does not match research config")


@dataclass(frozen=True)
class ResearchRunArtifact:
    """Immutable archival identity for one validated research run."""

    schema_version: str
    dataset: DatasetProvenance
    evidence_export_sha256: str
    evidence_export: str
    metadata: tuple[tuple[str, str], ...] = ()

    def validate(self) -> None:
        if self.schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError("unsupported research artifact schema version")
        if not isinstance(self.dataset, DatasetProvenance):
            raise ValueError("dataset must be DatasetProvenance")
        self.dataset.validate()
        if len(self.evidence_export_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.evidence_export_sha256
        ):
            raise ValueError("evidence_export_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.evidence_export, str) or not self.evidence_export:
            raise ValueError("evidence_export must be non-empty text")
        expected = sha256(self.evidence_export.encode("utf-8")).hexdigest()
        if expected != self.evidence_export_sha256:
            raise ValueError("evidence export fingerprint mismatch")
        try:
            export_payload = json.loads(self.evidence_export, parse_constant=_reject_nonstandard_json_constant)
        except (TypeError, ValueError) as exc:
            raise ValueError("evidence_export must contain valid JSON") from exc
        if not isinstance(export_payload, dict):
            raise ValueError("evidence_export must contain a JSON object")
        if export_payload.get("dataset") != _serialized_dataset(self.dataset):
            raise ValueError("artifact dataset does not match evidence export dataset")
        if export_payload.get("schema_version") not in {"2", "3"}:
            raise ValueError("unsupported evidence export schema version")
        _validate_embedded_export(export_payload)
        if type(self.metadata) is not tuple:
            raise ValueError("metadata must be a tuple")
        for item in self.metadata:
            if type(item) is not tuple or len(item) != 2 or any(
                type(value) is not str or not value for value in item
            ):
                raise ValueError("metadata must contain non-empty string key/value pairs")
        if tuple(sorted(self.metadata)) != self.metadata:
            raise ValueError("metadata must be canonically sorted")


def build_research_run_artifact(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
    *,
    metadata: Mapping[str, str] | None = None,
) -> ResearchRunArtifact:
    """Bind dataset provenance to the exact canonical evidence export."""
    if not isinstance(result, EvidencePipelineResult):
        raise ValueError("result must be an EvidencePipelineResult")
    if not isinstance(provenance, DatasetProvenance):
        raise ValueError("provenance must be DatasetProvenance")
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata must be a mapping")
        if any(
            type(key) is not str or not key or type(value) is not str or not value
            for key, value in metadata.items()
        ):
            raise ValueError("metadata must contain non-empty string key/value pairs")
        normalized = tuple(sorted(metadata.items()))
    else:
        normalized = ()
    evidence_export = serialize_evidence_export(result, provenance)
    artifact = ResearchRunArtifact(
        ARTIFACT_SCHEMA_VERSION,
        provenance,
        sha256(evidence_export.encode("utf-8")).hexdigest(),
        evidence_export,
        normalized,
    )
    artifact.validate()
    return artifact


def serialize_research_run_artifact(artifact: ResearchRunArtifact) -> str:
    """Serialize the complete artifact deterministically."""
    if not isinstance(artifact, ResearchRunArtifact):
        raise ValueError("artifact must be a ResearchRunArtifact")
    artifact.validate()
    payload: dict[str, Any] = {
        "schema_version": artifact.schema_version,
        "dataset": asdict(artifact.dataset),
        "evidence_export_sha256": artifact.evidence_export_sha256,
        "evidence_export": artifact.evidence_export,
        "metadata": dict(artifact.metadata),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)


def fingerprint_research_run_artifact(artifact: ResearchRunArtifact) -> str:
    """Return the stable SHA-256 identity of the canonical run artifact."""
    return sha256(serialize_research_run_artifact(artifact).encode("utf-8")).hexdigest()
