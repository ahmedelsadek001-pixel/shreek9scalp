"""Immutable evidence records for SHREEK research validation."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from types import MappingProxyType
from typing import Mapping


def _normalize_metrics(metrics: Mapping[str, float]) -> Mapping[str, float]:
    """Validate and freeze metrics before they become part of an evidence hash."""
    if not isinstance(metrics, Mapping):
        raise ValueError("metrics must be a mapping")

    normalized = {}
    for raw_key, raw_value in metrics.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError("metric names must be non-empty strings")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError("metric values must be real numbers")
        try:
            value = float(raw_value)
        except (OverflowError, ValueError):
            raise ValueError("metric values must be finite numbers") from None
        if not math.isfinite(value):
            raise ValueError("metric values must be finite numbers")
        normalized[raw_key] = value

    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True)
class ResearchEvidence:
    dataset_id: str
    strategy_version: str
    sample_size: int
    metrics: Mapping[str, float]
    evidence_hash: str

    @classmethod
    def create(
        cls,
        dataset_id: str,
        strategy_version: str,
        sample_size: int,
        metrics: Mapping[str, float],
    ) -> "ResearchEvidence":
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise ValueError("dataset_id is required")
        if not isinstance(strategy_version, str) or not strategy_version.strip():
            raise ValueError("strategy_version is required")
        if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size <= 0:
            raise ValueError("sample_size must be a positive integer")

        normalized = _normalize_metrics(metrics)
        canonical = "|".join(
            [dataset_id, strategy_version, str(sample_size)]
            + [f"{key}={normalized[key]:.12g}" for key in normalized]
        )
        digest = sha256(canonical.encode("utf-8")).hexdigest()
        return cls(dataset_id, strategy_version, sample_size, normalized, digest)


def verify_evidence(evidence: ResearchEvidence) -> bool:
    """Return whether an evidence record is valid and its hash is intact."""
    if not isinstance(evidence, ResearchEvidence):
        return False
    try:
        rebuilt = ResearchEvidence.create(
            evidence.dataset_id,
            evidence.strategy_version,
            evidence.sample_size,
            evidence.metrics,
        )
    except (TypeError, ValueError):
        return False
    return rebuilt.evidence_hash == evidence.evidence_hash
