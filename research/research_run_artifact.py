"""Deterministic, reproducible artifact for one SHREEK research run."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from research.dataset_provenance import DatasetProvenance
from research.evidence_export import serialize_evidence_export
from research.evidence_pipeline import EvidencePipelineResult


ARTIFACT_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class ResearchRunArtifact:
    """Immutable archival identity for one validated research run."""

    schema_version: str
    dataset: DatasetProvenance
    evidence_export_sha256: str
    evidence_export: str
    metadata: tuple[tuple[str, str], ...] = ()

    def validate(self) -> None:
        if self.schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError("unsupported research artifact schema version")
        if not isinstance(self.dataset, DatasetProvenance):
            raise ValueError("dataset must be DatasetProvenance")
        self.dataset.validate()
        if len(self.evidence_export_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.evidence_export_sha256
        ):
            raise ValueError("evidence_export_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.evidence_export, str) or not self.evidence_export:
            raise ValueError("evidence_export must be non-empty text")
        expected = sha256(self.evidence_export.encode("utf-8")).hexdigest()
        if expected != self.evidence_export_sha256:
            raise ValueError("evidence export fingerprint mismatch")
        if type(self.metadata) is not tuple:
            raise ValueError("metadata must be a tuple")
        for item in self.metadata:
            if type(item) is not tuple or len(item) != 2 or any(
                type(value) is not str or not value for value in item
            ):
                raise ValueError("metadata must contain non-empty string key/value pairs")
        if tuple(sorted(self.metadata)) != self.metadata:
            raise ValueError("metadata must be canonically sorted")


def build_research_run_artifact(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
    *,
    metadata: Mapping[str, str] | None = None,
) -> ResearchRunArtifact:
    """Bind dataset provenance to the exact canonical evidence export."""
    if not isinstance(result, EvidencePipelineResult):
        raise ValueError("result must be an EvidencePipelineResult")
    if not isinstance(provenance, DatasetProvenance):
        raise ValueError("provenance must be DatasetProvenance")
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata must be a mapping")
        if any(
            type(key) is not str or not key or type(value) is not str or not value
            for key, value in metadata.items()
        ):
            raise ValueError("metadata must contain non-empty string key/value pairs")
        normalized = tuple(sorted(metadata.items()))
    else:
        normalized = ()
    evidence_export = serialize_evidence_export(result, provenance)
    artifact = ResearchRunArtifact(
        ARTIFACT_SCHEMA_VERSION,
        provenance,
        sha256(evidence_export.encode("utf-8")).hexdigest(),
        evidence_export,
        normalized,
    )
    artifact.validate()
    return artifact


def serialize_research_run_artifact(artifact: ResearchRunArtifact) -> str:
    """Serialize the complete artifact deterministically."""
    if not isinstance(artifact, ResearchRunArtifact):
        raise ValueError("artifact must be a ResearchRunArtifact")
    artifact.validate()
    payload: dict[str, Any] = {
        "schema_version": artifact.schema_version,
        "dataset": asdict(artifact.dataset),
        "evidence_export_sha256": artifact.evidence_export_sha256,
        "evidence_export": artifact.evidence_export,
        "metadata": dict(artifact.metadata),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_research_run_artifact(artifact: ResearchRunArtifact) -> str:
    """Return the stable SHA-256 identity of the canonical run artifact."""
    return sha256(serialize_research_run_artifact(artifact).encode("utf-8")).hexdigest()
