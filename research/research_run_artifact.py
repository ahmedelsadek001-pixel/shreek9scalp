"""Deterministic, reproducible artifact for one SHREEK research run."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from research.dataset_provenance import DatasetProvenance
from research.evidence_export import serialize_evidence_export
from research.evidence_pipeline import EvidencePipelineResult


ARTIFACT_SCHEMA_VERSION = "1"


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
    numeric_policy = ("min_expectancy", "min_oos_stability_pct", "max_ruin_rate_pct", "max_worst_drawdown")
    if type(policy.get("min_oos_trades")) is not int or policy["min_oos_trades"] <= 0:
        raise ValueError("evidence export gate policy trade minimum is invalid")
    if any(type(policy.get(name)) not in (int, float) for name in numeric_policy):
        raise ValueError("evidence export gate policy numeric values are invalid")
    if type(evidence.get("oos_trade_count")) is not int or evidence["oos_trade_count"] < 0:
        raise ValueError("evidence export OOS trade count is invalid")
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
        if evidence.get("worst_max_drawdown") > policy["max_worst_drawdown"]:
            raise ValueError("passing gate contradicts drawdown maximum")
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
            passed = certification.get("passed")
            failures = certification.get("failures")
            if type(passed) is not bool or not isinstance(failures, list):
                raise ValueError("embedded certification is malformed")
            if passed != (len(failures) == 0):
                raise ValueError("embedded certification pass state is inconsistent")
            if any(type(item) is not str or not item for item in failures):
                raise ValueError("embedded certification failures are malformed")
            cert_policy = statistical["certification_policy"]
            required_policy = {
                "min_oos_trades", "min_oos_windows", "min_oos_stability_pct",
                "require_positive_ci_lower", "require_positive_bootstrap_lower",
                "max_bootstrap_non_positive_rate_pct", "max_ruin_rate_pct",
            }
            if not required_policy.issubset(cert_policy):
                raise ValueError("embedded certification policy is incomplete")
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
            export_payload = json.loads(self.evidence_export)
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
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_research_run_artifact(artifact: ResearchRunArtifact) -> str:
    """Return the stable SHA-256 identity of the canonical run artifact."""
    return sha256(serialize_research_run_artifact(artifact).encode("utf-8")).hexdigest()
