"""Deterministic JSON export for SHREEK V5.2 research evidence."""
from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any

from research.dataset_provenance import DatasetProvenance
from research.evidence_gate import EvidenceGatePolicy
from research.evidence_pipeline import EvidencePipelineResult


EXPORT_SCHEMA_VERSION = "2"


def build_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
    policy: EvidenceGatePolicy = EvidenceGatePolicy(),
) -> dict[str, Any]:
    """Build a JSON-safe, deterministic evidence payload with full gate context."""
    if not isinstance(result, EvidencePipelineResult):
        raise ValueError("result must be an EvidencePipelineResult")
    if not isinstance(provenance, DatasetProvenance):
        raise ValueError("provenance must be DatasetProvenance")
    if not isinstance(policy, EvidenceGatePolicy):
        raise ValueError("policy must be an EvidenceGatePolicy")
    provenance.validate()
    result.report.validate()
    policy.validate()
    payload = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "dataset": asdict(provenance),
        "evidence": asdict(result.report),
        "gate": asdict(result.gate),
        "gate_policy": asdict(policy),
    }
    return payload


def serialize_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
    policy: EvidenceGatePolicy = EvidenceGatePolicy(),
) -> str:
    """Serialize evidence deterministically for archival or comparison."""
    payload = build_evidence_export(result, provenance, policy)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
    policy: EvidenceGatePolicy = EvidenceGatePolicy(),
) -> str:
    """Return SHA-256 identity of the canonical evidence export."""
    canonical = serialize_evidence_export(result, provenance, policy)
    return sha256(canonical.encode("utf-8")).hexdigest()
