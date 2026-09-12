"""Reproducible research evidence records for SHREEK V5.2.

This module stores descriptive research metadata and a canonical hash. It has
no trading or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Mapping, Any


@dataclass(frozen=True)
class ResearchEvidence:
    dataset_id: str
    version: str
    samples: int
    metrics: Mapping[str, float]
    evidence_hash: str

    @classmethod
    def create(
        cls,
        dataset_id: str,
        version: str,
        samples: int,
        metrics: Mapping[str, float],
    ) -> "ResearchEvidence":
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise ValueError("dataset_id is required")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("version is required")
        if type(samples) is not int or samples <= 0:
            raise ValueError("samples must be a positive integer")
        if not isinstance(metrics, Mapping) or not metrics:
            raise ValueError("metrics are required")
        normalized = {}
        for key, value in metrics.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("metric names must be non-empty strings")
            numeric = float(value)
            if not isfinite(numeric):
                raise ValueError("metric values must be finite")
            normalized[key.strip()] = numeric
        canonical = json.dumps(
            {"dataset_id": dataset_id.strip(), "version": version.strip(), "samples": samples, "metrics": dict(sorted(normalized.items()))},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = sha256(canonical.encode("utf-8")).hexdigest()
        return cls(dataset_id.strip(), version.strip(), samples, dict(sorted(normalized.items())), digest)


def verify_evidence(evidence: ResearchEvidence) -> bool:
    """Recompute the canonical hash and verify integrity of the evidence record."""
    if not isinstance(evidence, ResearchEvidence):
        raise TypeError("evidence must be ResearchEvidence")
    try:
        rebuilt = ResearchEvidence.create(
            evidence.dataset_id,
            evidence.version,
            evidence.samples,
            evidence.metrics,
        )
    except (TypeError, ValueError):
        return False
    return rebuilt.evidence_hash == evidence.evidence_hash
