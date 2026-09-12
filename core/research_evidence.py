"""Immutable evidence records for SHREEK research validation."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping


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
        if not dataset_id.strip() or not strategy_version.strip():
            raise ValueError("dataset_id and strategy_version are required")
        if sample_size <= 0:
            raise ValueError("sample_size must be positive")
        normalized = {str(key): float(value) for key, value in sorted(metrics.items())}
        canonical = "|".join(
            [dataset_id, strategy_version, str(sample_size)]
            + [f"{key}={normalized[key]:.12g}" for key in sorted(normalized)]
        )
        return cls(dataset_id, strategy_version, sample_size, normalized, sha256(canonical.encode("utf-8")).hexdigest())


def verify_evidence(evidence: ResearchEvidence) -> bool:
    """Verify the deterministic hash of an evidence record."""
    rebuilt = ResearchEvidence.create(
        evidence.dataset_id,
        evidence.strategy_version,
        evidence.sample_size,
        evidence.metrics,
    )
    return rebuilt.evidence_hash == evidence.evidence_hash
