"""Fail-closed provenance primitives for reproducible research evidence."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
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


def _validate_json_value(value: object, path: str = "value") -> None:
    """Reject ambiguous objects and non-finite numbers before hashing."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string mapping key")
            _validate_json_value(nested, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_json_value(nested, f"{path}[{index}]")
        return
    raise ValueError(f"{path} contains an unsupported value type")


def fingerprint_mapping(values: Mapping[str, object]) -> str:
    """Create a deterministic SHA-256 fingerprint from strict JSON-like inputs."""
    if not isinstance(values, Mapping):
        raise ValueError("values must be a mapping")
    _validate_json_value(values)
    try:
        canonical = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("values must be serializable") from exc
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
