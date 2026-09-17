"""Reproducible research evidence records for SHREEK V5.2.

This module stores descriptive research metadata and a canonical hash. It has
no trading or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Mapping

from core.research_provenance import ResearchProvenance, build_provenance, validate_provenance


@dataclass(frozen=True)
class ResearchEvidence:
    dataset_id: str
    version: str
    samples: int
    metrics: Mapping[str, float]
    evidence_hash: str
    provenance: ResearchProvenance | None = None

    @property
    def sample_size(self) -> int:
        """Compatibility alias for the canonical ``samples`` field."""
        return self.samples

    @classmethod
    def create(
        cls,
        dataset_id: str,
        version: str,
        samples: int,
        metrics: Mapping[str, float],
        *,
        data: Mapping[str, object] | None = None,
        config: Mapping[str, object] | None = None,
        code_revision: str | None = None,
    ) -> "ResearchEvidence":
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise ValueError("dataset_id is required")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("version is required")
        if type(samples) is not int or samples <= 0:
            raise ValueError("samples must be a positive integer")
        if not isinstance(metrics, Mapping) or not metrics:
            raise ValueError("metrics are required")
        normalized: dict[str, float] = {}
        for key, value in metrics.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("metric names must be non-empty strings")
            numeric = float(value)
            if not isfinite(numeric):
                raise ValueError("metric values must be finite")
            normalized[key.strip()] = numeric
        normalized = dict(sorted(normalized.items()))

        provenance: ResearchProvenance | None = None
        provenance_fields = (data, config, code_revision)
        if any(value is not None for value in provenance_fields):
            if not all(value is not None for value in provenance_fields):
                raise ValueError("data, config, and code_revision must be supplied together")
            provenance = build_provenance(data=data, config=config, code_revision=code_revision)
            validate_provenance(provenance)

        canonical = json.dumps(
            {
                "dataset_id": dataset_id.strip(),
                "version": version.strip(),
                "samples": samples,
                "metrics": normalized,
                "provenance": (
                    {
                        "data_fingerprint": provenance.data_fingerprint,
                        "config_fingerprint": provenance.config_fingerprint,
                        "code_revision": provenance.code_revision,
                    }
                    if provenance is not None
                    else None
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = sha256(canonical.encode("utf-8")).hexdigest()
        return cls(dataset_id.strip(), version.strip(), samples, normalized, digest, provenance)


def verify_evidence(evidence: ResearchEvidence) -> bool:
    """Recompute the canonical hash and verify evidence-record integrity."""
    if not isinstance(evidence, ResearchEvidence):
        raise TypeError("evidence must be ResearchEvidence")
    if evidence.provenance is not None:
        try:
            validate_provenance(evidence.provenance)
        except ValueError:
            return False
    try:
        rebuilt = ResearchEvidence.create(
            evidence.dataset_id,
            evidence.version,
            evidence.samples,
            evidence.metrics,
            data=(
                {"fingerprint": evidence.provenance.data_fingerprint}
                if evidence.provenance is not None
                else None
            ),
            config=(
                {"fingerprint": evidence.provenance.config_fingerprint}
                if evidence.provenance is not None
                else None
            ),
            code_revision=(evidence.provenance.code_revision if evidence.provenance is not None else None),
        )
    except (TypeError, ValueError):
        return False
    if evidence.provenance is not None:
        # The stored provenance fingerprints are already identities; do not
        # reinterpret them as source data. Rebuild the hash using the exact
        # stored provenance fields so verification remains deterministic.
        canonical = json.dumps(
            {
                "dataset_id": evidence.dataset_id.strip(),
                "version": evidence.version.strip(),
                "samples": evidence.samples,
                "metrics": dict(sorted((str(k).strip(), float(v)) for k, v in evidence.metrics.items())),
                "provenance": {
                    "data_fingerprint": evidence.provenance.data_fingerprint,
                    "config_fingerprint": evidence.provenance.config_fingerprint,
                    "code_revision": evidence.provenance.code_revision,
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(canonical.encode("utf-8")).hexdigest() == evidence.evidence_hash
    return rebuilt.evidence_hash == evidence.evidence_hash
