"""Deterministic JSON export for SHREEK V5.2 research evidence."""
from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any

from research.dataset_provenance import DatasetProvenance
from research.evidence_pipeline import EvidencePipelineResult


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
    payload = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "dataset": asdict(provenance),
        "evidence": asdict(result.report),
        "gate": asdict(result.gate),
        "gate_policy": asdict(result.policy),
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
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> str:
    """Return SHA-256 identity of the canonical evidence export."""
    canonical = serialize_evidence_export(result, provenance)
    return sha256(canonical.encode("utf-8")).hexdigest()
