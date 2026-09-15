"""Deterministic JSON export for SHREEK V5.2 research evidence."""
from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any

from research.dataset_provenance import DatasetProvenance
from research.evidence_pipeline import EvidencePipelineResult


EXPORT_SCHEMA_VERSION = "1"


def build_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> dict[str, Any]:
    """Build a JSON-safe, immutable-style evidence payload with dataset identity."""
    if not isinstance(result, EvidencePipelineResult):
        raise ValueError("result must be an EvidencePipelineResult")
    if not isinstance(provenance, DatasetProvenance):
        raise ValueError("provenance must be DatasetProvenance")
    provenance.validate()
    result.report.validate()
    payload = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "dataset": asdict(provenance),
        "evidence": asdict(result.report),
        "gate": asdict(result.gate),
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
