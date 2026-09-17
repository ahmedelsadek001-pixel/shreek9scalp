"""Fail-closed provenance primitives for reproducible research evidence."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Mapping


@dataclass(frozen=True)
class ResearchProvenance:
    """Immutable identity for a research run's inputs and configuration."""

    data_fingerprint: str
    config_fingerprint: str
    code_revision: str

    def validate(self) -> None:
        for value, name in (
            (self.data_fingerprint, "data fingerprint"),
            (self.config_fingerprint, "config fingerprint"),
            (self.code_revision, "code revision"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")


def fingerprint_mapping(values: Mapping[str, object]) -> str:
    """Create a deterministic fingerprint from a JSON-like mapping."""
    if not isinstance(values, Mapping):
        raise ValueError("values must be a mapping")
    canonical = repr(sorted((str(key), repr(value)) for key, value in values.items()))
    return sha256(canonical.encode("utf-8")).hexdigest()


def build_provenance(*, data: Mapping[str, object], config: Mapping[str, object], code_revision: str) -> ResearchProvenance:
    """Build and validate provenance before research evidence is accepted."""
    provenance = ResearchProvenance(
        data_fingerprint=fingerprint_mapping(data),
        config_fingerprint=fingerprint_mapping(config),
        code_revision=code_revision,
    )
    provenance.validate()
    return provenance


def validate_provenance(provenance: ResearchProvenance) -> None:
    """Reject missing or malformed provenance before a release gate can pass."""
    if not isinstance(provenance, ResearchProvenance):
        raise ValueError("provenance must be a ResearchProvenance")
    provenance.validate()
