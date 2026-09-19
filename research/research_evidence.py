"""Reproducible research evidence records for SHREEK V5.2.

This module stores descriptive research metadata and a canonical hash. It has
no trading or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from types import MappingProxyType
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
        return self.samples

    @staticmethod
    def _canonical_payload(
        dataset_id: str,
        version: str,
        samples: int,
        metrics: Mapping[str, float],
        provenance: ResearchProvenance | None,
    ) -> str:
        return json.dumps(
            {
                "dataset_id": dataset_id.strip(),
                "version": version.strip(),
                "samples": samples,
                "metrics": dict(sorted(metrics.items())),
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
            allow_nan=False,
        )

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
            try:
                numeric = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("metric values must be finite numbers") from exc
            if not isfinite(numeric):
                raise ValueError("metric values must be finite")
            normalized[key.strip()] = numeric
        normalized = dict(sorted(normalized.items()))

        provenance: ResearchProvenance | None = None
        fields = (data, config, code_revision)
        if any(value is not None for value in fields):
            if not all(value is not None for value in fields):
                raise ValueError("data, config, and code_revision must be supplied together")
            provenance = build_provenance(data=data, config=config, code_revision=code_revision)
        payload = cls._canonical_payload(dataset_id, version, samples, normalized, provenance)
        digest = sha256(payload.encode("utf-8")).hexdigest()
        return cls(
            dataset_id.strip(),
            version.strip(),
            samples,
            MappingProxyType(normalized),
            digest,
            provenance,
        )


def verify_evidence(evidence: ResearchEvidence) -> bool:
    """Recompute the canonical hash and verify evidence-record integrity."""
    if not isinstance(evidence, ResearchEvidence):
        raise TypeError("evidence must be ResearchEvidence")
    try:
        if evidence.provenance is not None:
            validate_provenance(evidence.provenance)
        metrics: dict[str, float] = {}
        for key, value in evidence.metrics.items():
            if not isinstance(key, str) or not key.strip():
                return False
            numeric = float(value)
            if not isfinite(numeric):
                return False
            metrics[key.strip()] = numeric
        payload = ResearchEvidence._canonical_payload(
            evidence.dataset_id,
            evidence.version,
            evidence.samples,
            dict(sorted(metrics.items())),
            evidence.provenance,
        )
        return sha256(payload.encode("utf-8")).hexdigest() == evidence.evidence_hash
    except (TypeError, ValueError, AttributeError, OverflowError):
        return False
