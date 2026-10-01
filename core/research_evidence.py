"""Immutable, reproducible evidence records for SHREEK research validation."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from types import MappingProxyType
from typing import Mapping

from core.research_provenance import ResearchProvenance, build_provenance, validate_provenance


def _normalize_metrics(metrics: Mapping[str, float]) -> Mapping[str, float]:
    if not isinstance(metrics, Mapping) or not metrics:
        raise ValueError("metrics must be a non-empty mapping")
    normalized: dict[str, float] = {}
    for raw_key, raw_value in metrics.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError("metric names must be non-empty strings")
        key = raw_key.strip()
        if key in normalized:
            raise ValueError("metric names must be unique after normalization")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError("metric values must be finite numbers")
        try:
            value = float(raw_value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("metric values must be finite numbers") from exc
        if not isfinite(value):
            raise ValueError("metric values must be finite numbers")
        normalized[key] = value
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True)
class ResearchEvidence:
    dataset_id: str
    version: str
    samples: int
    metrics: Mapping[str, float]
    evidence_hash: str
    provenance: ResearchProvenance | None = None

    @property
    def strategy_version(self) -> str:
        """Backward-compatible name for the evidence version."""
        return self.version

    @property
    def sample_size(self) -> int:
        """Backward-compatible name for the number of samples."""
        return self.samples

    @staticmethod
    def _canonical_payload(dataset_id: str, version: str, samples: int,
                          metrics: Mapping[str, float], provenance: ResearchProvenance | None) -> str:
        provenance_payload = None
        if provenance is not None:
            provenance_payload = {
                "data_fingerprint": provenance.data_fingerprint,
                "config_fingerprint": provenance.config_fingerprint,
                "code_revision": provenance.code_revision,
            }
        return json.dumps({
            "dataset_id": dataset_id.strip(),
            "version": version.strip(),
            "samples": samples,
            "metrics": dict(sorted(metrics.items())),
            "provenance": provenance_payload,
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def create(cls, dataset_id: str, version: str, samples: int,
               metrics: Mapping[str, float], *, data: Mapping[str, object] | None = None,
               config: Mapping[str, object] | None = None,
               code_revision: str | None = None) -> "ResearchEvidence":
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise ValueError("dataset_id is required")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("version is required")
        if type(samples) is not int or samples <= 0:
            raise ValueError("samples must be a positive integer")
        normalized = _normalize_metrics(metrics)
        fields = (data, config, code_revision)
        provenance = None
        if any(value is not None for value in fields):
            if not all(value is not None for value in fields):
                raise ValueError("data, config, and code_revision must be supplied together")
            provenance = build_provenance(data=data, config=config, code_revision=code_revision)
        payload = cls._canonical_payload(dataset_id, version, samples, normalized, provenance)
        digest = sha256(payload.encode("utf-8")).hexdigest()
        return cls(dataset_id.strip(), version.strip(), samples, normalized, digest, provenance)


def verify_evidence(evidence: ResearchEvidence) -> bool:
    """Return whether an evidence record is well-formed and its hash is intact."""
    if not isinstance(evidence, ResearchEvidence):
        return False
    try:
        if (not isinstance(evidence.dataset_id, str) or not evidence.dataset_id.strip()
                or not isinstance(evidence.version, str) or not evidence.version.strip()
                or type(evidence.samples) is not int or evidence.samples <= 0
                or not isinstance(evidence.evidence_hash, str) or not evidence.evidence_hash
                or not isinstance(evidence.metrics, Mapping) or not evidence.metrics):
            return False
        if evidence.provenance is not None:
            validate_provenance(evidence.provenance)
        metrics = _normalize_metrics(evidence.metrics)
        payload = ResearchEvidence._canonical_payload(
            evidence.dataset_id, evidence.version, evidence.samples, metrics, evidence.provenance
        )
        return sha256(payload.encode("utf-8")).hexdigest() == evidence.evidence_hash
    except (TypeError, ValueError, AttributeError, OverflowError, RecursionError):
        return False
