from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import hashlib
import json

import pytest

from core.block_bootstrap import BlockBootstrapSummary
from core.research_certification import ResearchCertification, ResearchCertificationPolicy
from core.statistical_evidence import MeanConfidenceInterval
from research.dataset_provenance import DatasetProvenance
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_report import OOSEvidenceReport
from research.research_run_artifact import (
    ResearchRunArtifact,
    build_research_run_artifact,
    fingerprint_research_run_artifact,
    serialize_research_run_artifact,
)


def _provenance():
    return DatasetProvenance(
        "1", "a" * 64, 2,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )


def _result(policy=None):
    report = OOSEvidenceReport(
        30, 100.0, 3.333333, 75.0, 3, 4, 0.0,
        10100.0, 10000.0, 50.0, 100.0, 1000,
    )
    policy = policy or EvidenceGatePolicy()
    return EvidencePipelineResult(
        object(), object(), report, EvidenceGateResult(True, ()), policy
    )


def _statistical_result():
    base = _result()
    return replace(
        base,
        interval=MeanConfidenceInterval(30, 3.333333, 0.5, 0.95, 2.0, 4.0),
        bootstrap=BlockBootstrapSummary(30, 2, 100, 0.95, 3.333333, 3.3, 2.0, 4.0, 0.0),
        certification=ResearchCertification(True, (), 30, 4, 75.0, 10.0, 80.0),
        certification_policy=ResearchCertificationPolicy(),
    )


def test_artifact_is_deterministic_and_fingerprinted():
    artifact = build_research_run_artifact(
        _result(), _provenance(), metadata={"run": "1", "source": "local"}
    )
    assert serialize_research_run_artifact(artifact) == serialize_research_run_artifact(artifact)
    assert fingerprint_research_run_artifact(artifact) == fingerprint_research_run_artifact(artifact)
    artifact.validate()


def test_artifact_binds_exact_evidence_export():
    artifact = build_research_run_artifact(
        _result(EvidenceGatePolicy(min_expectancy=1.0)), _provenance()
    )
    assert artifact.evidence_export_sha256 == __import__("hashlib").sha256(
        artifact.evidence_export.encode("utf-8")
    ).hexdigest()
    assert '"gate_policy"' in artifact.evidence_export


def test_artifact_changes_when_metadata_changes():
    first = build_research_run_artifact(_result(), _provenance(), metadata={"run": "1"})
    second = build_research_run_artifact(_result(), _provenance(), metadata={"run": "2"})
    assert fingerprint_research_run_artifact(first) != fingerprint_research_run_artifact(second)


def test_artifact_rejects_tampered_export():
    artifact = build_research_run_artifact(_result(), _provenance())
    tampered = ResearchRunArtifact(
        artifact.schema_version,
        artifact.dataset,
        artifact.evidence_export_sha256,
        artifact.evidence_export + "x",
        artifact.metadata,
    )
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        tampered.validate()


def test_artifact_rejects_rehashed_export_with_different_dataset():
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["dataset"]["sha256"] = "b" * 64
    export = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    tampered = replace(
        artifact,
        evidence_export=export,
        evidence_export_sha256=hashlib.sha256(export.encode("utf-8")).hexdigest(),
    )
    with pytest.raises(ValueError, match="does not match"):
        tampered.validate()


@pytest.mark.parametrize(
    "metadata",
    [
        {"run": 1},
        {1: "run"},
        {"run": None},
        {"run": ""},
        {"": "value"},
    ],
)
def test_artifact_rejects_non_string_or_empty_metadata(metadata):
    with pytest.raises(ValueError, match="metadata"):
        build_research_run_artifact(_result(), _provenance(), metadata=metadata)


def test_artifact_rejects_non_string_metadata_items_after_construction():
    artifact = build_research_run_artifact(_result(), _provenance(), metadata={"run": "1"})
    tampered = ResearchRunArtifact(
        artifact.schema_version,
        artifact.dataset,
        artifact.evidence_export_sha256,
        artifact.evidence_export,
        (("run", 1),),
    )
    with pytest.raises(ValueError, match="metadata"):
        tampered.validate()


def _rehash_artifact(artifact, payload):
    export = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return replace(
        artifact,
        evidence_export=export,
        evidence_export_sha256=sha256(export.encode("utf-8")).hexdigest(),
    )


def test_artifact_rejects_dataset_tampering_even_when_export_is_rehashed():
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["dataset"]["sha256"] = "b" * 64
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="dataset does not match"):
        tampered.validate()


def test_artifact_rejects_schema_tampering_even_when_export_is_rehashed():
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["schema_version"] = "999"
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="unsupported evidence export schema"):
        tampered.validate()


def test_artifact_rejects_rehashed_gate_pass_failure_contradiction():
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["gate"] = {"passed": True, "failures": ["contradiction"]}
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="gate pass state is inconsistent"):
        tampered.validate()


def test_artifact_rejects_rehashed_missing_required_export_section():
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    del payload["gate_policy"]
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="missing required sections"):
        tampered.validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("oos_trade_count", 0, "trade minimum"),
        ("oos_expectancy", -1.0, "expectancy minimum"),
        ("oos_stability_pct", 0.0, "stability minimum"),
        ("ruin_rate_pct", 100.0, "ruin-rate maximum"),
    ],
)
def test_artifact_rejects_rehashed_passing_gate_that_contradicts_evidence(field, value, message):
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["evidence"][field] = value
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match=message):
        tampered.validate()


def test_artifact_rejects_rehashed_passing_gate_that_contradicts_drawdown_policy():
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["gate_policy"]["max_worst_drawdown"] = 1.0
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="drawdown maximum"):
        tampered.validate()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_artifact_rejects_non_finite_rehashed_numeric_evidence(value):
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["evidence"]["oos_expectancy"] = value
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="valid JSON"):
        tampered.validate()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_artifact_rejects_non_finite_rehashed_gate_policy(value):
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["gate_policy"]["min_expectancy"] = value
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="valid JSON"):
        tampered.validate()


def test_artifact_accepts_default_unbounded_drawdown_policy():
    artifact = build_research_run_artifact(_result(), _provenance())
    artifact.validate()




def test_artifact_serializes_unbounded_drawdown_as_json_null():
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    assert payload["gate_policy"]["max_worst_drawdown"] is None
    assert "Infinity" not in artifact.evidence_export
    assert "NaN" not in artifact.evidence_export


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_artifact_rejects_nonstandard_json_constants_anywhere(token):
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["unexpected_numeric_evidence"] = 0
    export = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    export = export.replace('"unexpected_numeric_evidence":0', f'"unexpected_numeric_evidence":{token}')
    tampered = replace(
        artifact,
        evidence_export=export,
        evidence_export_sha256=sha256(export.encode("utf-8")).hexdigest(),
    )
    with pytest.raises(ValueError, match="valid JSON"):
        tampered.validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("oos_expectancy_degradation_pct", 60.0, "expectancy degradation policy"),
        ("parameter_stability_pct", 40.0, "parameter stability policy"),
    ],
)
def test_artifact_rejects_rehashed_passing_certification_that_contradicts_robustness_policy(field, value, message):
    artifact = build_research_run_artifact(_statistical_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["statistical_evidence"]["certification"][field] = value
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match=message):
        tampered.validate()


@pytest.mark.parametrize(
    "field",
    ["max_oos_expectancy_degradation_pct", "min_parameter_stability_pct"],
)
def test_artifact_rejects_missing_required_robustness_certification_policy(field):
    artifact = build_research_run_artifact(_statistical_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    del payload["statistical_evidence"]["certification_policy"][field]
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="certification policy is incomplete"):
        tampered.validate()
