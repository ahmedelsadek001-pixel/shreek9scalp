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
    validate_strategy_binding,
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


def test_artifact_rejects_rehashed_statistical_sample_count_mismatch_with_oos_report():
    artifact = build_research_run_artifact(_statistical_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["evidence"]["oos_trade_count"] = 31
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="samples do not match archived OOS trade count"):
        tampered.validate()


def test_artifact_rejects_rehashed_certification_window_mismatch_with_oos_report():
    artifact = build_research_run_artifact(_statistical_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["statistical_evidence"]["certification"]["oos_windows"] = 3
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="OOS windows do not match archived evidence"):
        tampered.validate()


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        ("confidence_interval", "mean", 9.0, "confidence interval mean"),
        ("block_bootstrap", "observed_mean", 9.0, "bootstrap observed mean"),
        ("certification", "oos_stability_pct", 74.0, "certification OOS stability"),
    ],
)
def test_artifact_rejects_rehashed_statistical_summary_mismatch_with_oos_report(section, field, value, message):
    artifact = build_research_run_artifact(_statistical_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["statistical_evidence"][section][field] = value
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match=message):
        tampered.validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("min_oos_trades", 1, "OOS trade minimum"),
        ("min_oos_windows", 0, "OOS window minimum"),
        ("require_positive_ci_lower", 0, "switches must be bools"),
        ("require_positive_bootstrap_lower", 1, "switches must be bools"),
        ("min_parameter_stability_pct", 101.0, "between 0 and 100"),
        ("max_oos_expectancy_degradation_pct", -1.0, "between 0 and 100"),
    ],
)
def test_artifact_rejects_rehashed_invalid_certification_policy_types_and_ranges(field, value, message):
    artifact = build_research_run_artifact(_statistical_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["statistical_evidence"]["certification_policy"][field] = value
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match=message):
        tampered.validate()


def test_artifact_rejects_rehashed_forged_failing_gate():
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["gate"] = {"passed": False, "failures": ["forged failure"]}
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="gate failures do not match evidence and policy"):
        tampered.validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("min_oos_stability_pct", -1.0, "stability minimum is invalid"),
        ("min_oos_stability_pct", 101.0, "stability minimum is invalid"),
        ("max_ruin_rate_pct", -1.0, "ruin maximum is invalid"),
    ],
)
def test_artifact_rejects_rehashed_invalid_gate_policy_ranges(field, value, message):
    artifact = build_research_run_artifact(_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["gate_policy"][field] = value
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match=message):
        tampered.validate()


def test_artifact_rejects_rehashed_forged_failing_certification():
    artifact = build_research_run_artifact(_statistical_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["statistical_evidence"]["certification"]["passed"] = False
    payload["statistical_evidence"]["certification"]["failures"] = ["forged failure"]
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="certification failures do not match evidence and policy"):
        tampered.validate()


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        ("evidence", "simulations", 0, "requires OOS trades, windows, and simulations"),
        ("confidence_interval", "standard_error", -1.0, "invalid confidence interval"),
        ("block_bootstrap", "block_size", 0, "invalid block size"),
        ("certification", "parameter_stability_pct", 120.0, "parameter stability must be between 0 and 100"),
    ],
)
def test_artifact_rejects_rehashed_structurally_invalid_archived_evidence(section, field, value, message):
    artifact = build_research_run_artifact(_statistical_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    target = payload["evidence"] if section == "evidence" else payload["statistical_evidence"][section]
    target[field] = value
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match=message):
        tampered.validate()


@pytest.mark.parametrize(
    "section",
    ["evidence", "confidence_interval", "block_bootstrap", "certification", "certification_policy"],
)
def test_artifact_rejects_rehashed_unexpected_archived_evidence_fields(section):
    artifact = build_research_run_artifact(_statistical_result(), _provenance())
    payload = json.loads(artifact.evidence_export)
    target = payload["evidence"] if section == "evidence" else payload["statistical_evidence"][section]
    target["unexpected_field"] = "tampered"
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError, match="structure is invalid"):
        tampered.validate()


def test_strategy_binding_accepts_exact_artifact_identity():
    artifact = build_research_run_artifact(
        _result(),
        _provenance(),
        metadata={"strategy_id": "breakout-retest", "strategy_version": "research-v1"},
    )
    validate_strategy_binding(
        artifact,
        strategy_id="breakout-retest",
        strategy_version="research-v1",
    )


@pytest.mark.parametrize(
    ("strategy_id", "strategy_version", "message"),
    [
        ("wrong", "research-v1", "strategy_id"),
        ("breakout-retest", "wrong", "strategy_version"),
    ],
)
def test_strategy_binding_rejects_mismatch(strategy_id, strategy_version, message):
    artifact = build_research_run_artifact(
        _result(),
        _provenance(),
        metadata={"strategy_id": "breakout-retest", "strategy_version": "research-v1"},
    )
    with pytest.raises(ValueError, match=message):
        validate_strategy_binding(
            artifact,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
        )


def test_strategy_binding_rejects_unbound_legacy_artifact():
    artifact = build_research_run_artifact(_result(), _provenance())
    with pytest.raises(ValueError, match="strategy_id"):
        validate_strategy_binding(
            artifact,
            strategy_id="breakout-retest",
            strategy_version="research-v1",
        )


def test_artifact_rejects_duplicate_metadata_keys():
    artifact = build_research_run_artifact(
        _result(),
        _provenance(),
        metadata={"strategy_id": "breakout-retest"},
    )
    ambiguous = replace(
        artifact,
        metadata=(
            ("strategy_id", "breakout-retest"),
            ("strategy_id", "other"),
        ),
    )
    with pytest.raises(ValueError, match="metadata keys must be unique"):
        ambiguous.validate()


def test_strategy_binding_accepts_exact_code_revision():
    revision = "a" * 40
    artifact = build_research_run_artifact(
        _result(),
        _provenance(),
        metadata={
            "strategy_id": "breakout-retest",
            "strategy_version": "research-v1",
            "code_revision": revision,
        },
    )
    validate_strategy_binding(
        artifact,
        strategy_id="breakout-retest",
        strategy_version="research-v1",
        code_revision=revision,
    )


@pytest.mark.parametrize("revision", ["b" * 40, "A" * 40, "short"])
def test_strategy_binding_rejects_wrong_or_malformed_code_revision(revision):
    artifact = build_research_run_artifact(
        _result(),
        _provenance(),
        metadata={
            "strategy_id": "breakout-retest",
            "strategy_version": "research-v1",
            "code_revision": "a" * 40,
        },
    )
    with pytest.raises(ValueError, match="code_revision"):
        validate_strategy_binding(
            artifact,
            strategy_id="breakout-retest",
            strategy_version="research-v1",
            code_revision=revision,
        )


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"strategy_id": " breakout-retest"}, "strategy_id metadata must be normalized"),
        ({"strategy_version": "research-v1 "}, "strategy_version metadata must be normalized"),
        ({"code_revision": "A" * 40}, "code_revision metadata"),
        ({"code_revision": "short"}, "code_revision metadata"),
    ],
)
def test_artifact_rejects_noncanonical_reserved_identity_metadata(metadata, message):
    with pytest.raises(ValueError, match=message):
        build_research_run_artifact(_result(), _provenance(), metadata=metadata)


def test_artifact_embeds_reserved_identity_in_hashed_evidence():
    revision = "a" * 40
    artifact = build_research_run_artifact(
        _result(),
        _provenance(),
        metadata={
            "strategy_id": "breakout-retest",
            "strategy_version": "research-v1",
            "code_revision": revision,
            "note": "not-identity",
        },
    )
    payload = json.loads(artifact.evidence_export)
    assert payload["artifact_identity"] == {
        "code_revision": revision,
        "strategy_id": "breakout-retest",
        "strategy_version": "research-v1",
    }
    assert "note" not in payload["artifact_identity"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("strategy_id", "other"),
        ("strategy_version", "other"),
        ("code_revision", "b" * 40),
    ],
)
def test_strategy_binding_rejects_rehashed_embedded_identity_tampering(field, value):
    revision = "a" * 40
    artifact = build_research_run_artifact(
        _result(),
        _provenance(),
        metadata={
            "strategy_id": "breakout-retest",
            "strategy_version": "research-v1",
            "code_revision": revision,
        },
    )
    payload = json.loads(artifact.evidence_export)
    payload["artifact_identity"][field] = value
    tampered = _rehash_artifact(artifact, payload)
    with pytest.raises(ValueError):
        validate_strategy_binding(
            tampered,
            strategy_id="breakout-retest",
            strategy_version="research-v1",
            code_revision=revision,
        )
