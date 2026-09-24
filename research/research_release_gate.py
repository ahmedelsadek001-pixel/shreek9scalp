"""Fail-closed research release gate for SHREEK V5.2.

This gate determines whether the research package has sufficient evidence to
progress toward V5.3. It does not authorize execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from research.research_run_artifact import (
    ResearchRunArtifact,
    validate_strategy_binding,
    validated_evidence_payload,
)
from research.xauusd_source_manifest import XAUUSDSourceManifest


@dataclass(frozen=True)
class ResearchReleaseEvidence:
    ci_green: bool
    sample_coverage: bool
    edge_matrix_validated: bool
    wfo_stability_validated: bool
    purged_wfo_validated: bool
    robustness_validated: bool
    bootstrap_validated: bool
    mae_mfe_validated: bool
    execution_quality_validated: bool
    dataset_provenance_validated: bool = False
    reproducible_artifact_validated: bool = False
    strategy_version_bound: bool = False


@dataclass(frozen=True)
class ResearchReleaseDecision:
    ready: bool
    failures: tuple[str, ...]


def evaluate_research_release(evidence: ResearchReleaseEvidence) -> ResearchReleaseDecision:
    """Return a release decision; every research prerequisite must be explicitly true."""
    if not isinstance(evidence, ResearchReleaseEvidence):
        raise TypeError("evidence must be ResearchReleaseEvidence")
    checks = {
        "CI is not green": evidence.ci_green,
        "sample coverage is insufficient": evidence.sample_coverage,
        "edge matrix is not validated": evidence.edge_matrix_validated,
        "walk-forward stability is not validated": evidence.wfo_stability_validated,
        "purged walk-forward validation is not validated": evidence.purged_wfo_validated,
        "robustness is not validated": evidence.robustness_validated,
        "bootstrap expectancy validation is not validated": evidence.bootstrap_validated,
        "MAE/MFE is not validated": evidence.mae_mfe_validated,
        "execution quality is not validated": evidence.execution_quality_validated,
        "dataset provenance is not validated": evidence.dataset_provenance_validated,
        "reproducible research artifact is not validated": evidence.reproducible_artifact_validated,
        "research artifact is not bound to strategy version": evidence.strategy_version_bound,
    }
    failures = tuple(name for name, passed in checks.items() if type(passed) is not bool or not passed)
    return ResearchReleaseDecision(not failures, failures)



@dataclass(frozen=True)
class ResearchReleasePackage:
    """Promotion input binding empirical release claims to one exact research artifact."""

    evidence: ResearchReleaseEvidence
    artifact: ResearchRunArtifact
    strategy_id: str
    strategy_version: str
    code_revision: str


def _artifact_promotion_failures(artifact: ResearchRunArtifact) -> tuple[str, ...]:
    """Derive promotion-critical claims from the artifact instead of trusting flags."""
    payload = validated_evidence_payload(artifact)
    failures: list[str] = []
    if payload.get("schema_version") != "3":
        failures.append("research artifact does not use statistical evidence schema")
    gate = payload.get("gate")
    if not isinstance(gate, dict) or gate.get("passed") is not True:
        failures.append("research artifact OOS evidence gate did not pass")
    wfo = payload.get("wfo_evidence")
    config = payload.get("research_config")
    if not isinstance(wfo, dict) or not isinstance(config, dict):
        failures.append("research artifact lacks reproducible WFO evidence")
    else:
        timestamps = wfo.get("window_timestamps")
        if not isinstance(timestamps, list) or not timestamps:
            failures.append("research artifact lacks timestamped WFO windows")
        if config.get("purge_size", -1) < config.get("label_horizon", 0):
            failures.append("research artifact purge does not cover label horizon")
        if (
            type(config.get("slippage_multiplier")) not in (int, float)
            or type(config.get("spread_multiplier")) not in (int, float)
            or not isfinite(float(config["slippage_multiplier"]))
            or not isfinite(float(config["spread_multiplier"]))
            or config["slippage_multiplier"] <= 1.0
            or config["spread_multiplier"] <= 1.0
        ):
            failures.append("research artifact lacks adverse execution-cost stress")
    metadata = dict(artifact.metadata)
    cost_keys = {
        "source_broker", "source_server", "source_symbol",
        "source_timezone_offset_minutes", "source_digits", "source_point_size",
        "source_contract_size", "source_minimum_volume", "source_volume_step",
        "source_spread_points", "source_slippage_points",
        "source_round_turn_commission_per_lot",
    }
    if not cost_keys.issubset(metadata):
        failures.append("research artifact lacks complete broker cost provenance")
    else:
        try:
            manifest = XAUUSDSourceManifest(
                metadata["source_broker"],
                metadata["source_server"],
                metadata["source_symbol"],
                int(metadata["source_timezone_offset_minutes"]),
                int(metadata["source_digits"]),
                float(metadata["source_point_size"]),
                float(metadata["source_contract_size"]),
                float(metadata["source_minimum_volume"]),
                float(metadata["source_volume_step"]),
                float(metadata["source_spread_points"]),
                float(metadata["source_round_turn_commission_per_lot"]),
                float(metadata["source_slippage_points"]),
            )
            manifest.validate()
        except (TypeError, ValueError, OverflowError):
            failures.append("research artifact broker cost provenance is malformed")
        else:
            if manifest.observed_spread_points <= 0:
                failures.append("research artifact observed spread must be positive")
    statistical = payload.get("statistical_evidence")
    if not isinstance(statistical, dict):
        failures.append("research artifact lacks statistical certification evidence")
    else:
        certification = statistical.get("certification")
        if not isinstance(certification, dict) or certification.get("passed") is not True:
            failures.append("research artifact statistical certification did not pass")
        bootstrap = statistical.get("block_bootstrap")
        if not isinstance(bootstrap, dict) or bootstrap.get("simulations", 0) <= 0:
            failures.append("research artifact lacks valid block bootstrap evidence")
    return tuple(failures)


def evaluate_research_release_package(package: ResearchReleasePackage) -> ResearchReleaseDecision:
    """Evaluate V5.2 promotion with artifact and strategy identity verified in-process."""
    if not isinstance(package, ResearchReleasePackage):
        raise TypeError("package must be ResearchReleasePackage")
    if not isinstance(package.evidence, ResearchReleaseEvidence):
        return ResearchReleaseDecision(False, ("research release evidence is malformed",))
    if not isinstance(package.artifact, ResearchRunArtifact):
        return ResearchReleaseDecision(False, ("research artifact is malformed",))
    try:
        package.artifact.dataset.validate()
        package.artifact.validate()
        validate_strategy_binding(
            package.artifact,
            strategy_id=package.strategy_id,
            strategy_version=package.strategy_version,
            code_revision=package.code_revision,
        )
        artifact_failures = _artifact_promotion_failures(package.artifact)
    except (TypeError, ValueError):
        return ResearchReleaseDecision(False, ("research artifact identity validation failed",))
    manual = evaluate_research_release(package.evidence)
    failures = manual.failures + tuple(
        failure for failure in artifact_failures if failure not in manual.failures
    )
    return ResearchReleaseDecision(not failures, failures)
