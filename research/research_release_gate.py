"""Fail-closed, artifact-bound research release gate for SHREEK V5.2.

The decision can progress research toward V5.3 only. It never authorizes
execution or deployment.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
from typing import Mapping


@dataclass(frozen=True)
class ResearchReleaseEvidence:
    ci_green: bool
    sample_coverage: bool
    edge_matrix_validated: bool
    wfo_stability_validated: bool
    purged_wfo_validated: bool
    robustness_validated: bool
    bootstrap_validated: bool
    mae_mfe_validated: bool
    execution_quality_validated: bool


_REQUIRED_EVIDENCE = tuple(ResearchReleaseEvidence.__dataclass_fields__)


def _normalize_sha(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) not in (40, 64):
        raise ValueError(f"{name} must be a 40- or 64-character hexadecimal SHA")
    normalized = value.lower()
    if any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{name} must contain only hexadecimal characters")
    return normalized


def _normalize_digest(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("artifact_sha256 must be a 64-character SHA-256")
    normalized = value.lower()
    if any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError("artifact_sha256 must contain only hexadecimal characters")
    return normalized


@dataclass(frozen=True)
class ResearchReleaseEvidenceRecord:
    """One research gate result tied to a source commit and evidence artifact."""

    name: str
    passed: bool
    source: str
    run_id: str
    recorded_at: datetime
    commit_sha: str
    artifact_sha256: str

    @classmethod
    def from_artifact_bytes(
        cls,
        *,
        name: str,
        passed: bool,
        source: str,
        run_id: str,
        recorded_at: datetime,
        commit_sha: str,
        artifact_bytes: bytes,
    ) -> "ResearchReleaseEvidenceRecord":
        if not isinstance(artifact_bytes, bytes):
            raise TypeError("artifact_bytes must be bytes")
        record = cls(
            name,
            passed,
            source,
            run_id,
            recorded_at,
            commit_sha,
            sha256(artifact_bytes).hexdigest(),
        )
        record.validate()
        return record

    def validate(self) -> None:
        if not isinstance(self.name, str) or self.name not in _REQUIRED_EVIDENCE:
            raise ValueError("unsupported research evidence name")
        if type(self.passed) is not bool:
            raise TypeError("research evidence passed must be bool")
        for name, value in (("source", self.source), ("run_id", self.run_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"research evidence {name} is required")
        if not isinstance(self.recorded_at, datetime) or self.recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must be a timezone-aware datetime")
        _normalize_sha(self.commit_sha, "commit_sha")
        _normalize_digest(self.artifact_sha256)


@dataclass(frozen=True)
class ResearchReleaseEvidenceBundle:
    """Integrity-checked set of research evidence references for one commit."""

    records: tuple[ResearchReleaseEvidenceRecord, ...]
    bundle_sha256: str

    @staticmethod
    def _canonical(records: tuple[ResearchReleaseEvidenceRecord, ...]) -> str:
        payload = [
            {
                "name": record.name,
                "passed": record.passed,
                "source": record.source,
                "run_id": record.run_id,
                "recorded_at": record.recorded_at.astimezone(timezone.utc).isoformat(),
                "commit_sha": record.commit_sha.lower(),
                "artifact_sha256": _normalize_digest(record.artifact_sha256),
            }
            for record in sorted(records, key=lambda item: item.name)
        ]
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_records(
        cls,
        records: tuple[ResearchReleaseEvidenceRecord, ...],
    ) -> "ResearchReleaseEvidenceBundle":
        if not isinstance(records, tuple) or not records:
            raise ValueError("non-empty tuple of research evidence records is required")
        for record in records:
            if not isinstance(record, ResearchReleaseEvidenceRecord):
                raise TypeError("records must contain ResearchReleaseEvidenceRecord values")
            record.validate()
        names = [record.name for record in records]
        if len(names) != len(set(names)):
            raise ValueError("duplicate research evidence names are not allowed")
        commits = {_normalize_sha(record.commit_sha, "commit_sha") for record in records}
        if len(commits) != 1:
            raise ValueError("all research evidence records must bind to the same commit")
        canonical = cls._canonical(records).encode("utf-8")
        return cls(records, sha256(canonical).hexdigest())

    @property
    def commit_sha(self) -> str:
        self.validate()
        return _normalize_sha(self.records[0].commit_sha, "commit_sha")

    def validate(self) -> None:
        rebuilt = self.from_records(self.records)
        if self.bundle_sha256 != rebuilt.bundle_sha256:
            raise ValueError("bundle SHA-256 does not match research evidence records")

    def as_map(self) -> dict[str, ResearchReleaseEvidenceRecord]:
        self.validate()
        return {record.name: record for record in self.records}


@dataclass(frozen=True)
class ResearchReleaseDecision:
    ready: bool
    failures: tuple[str, ...]
    bundle_sha256: str | None = None
    commit_sha: str | None = None
    manifest_sha256: str = ""

    @staticmethod
    def _canonical(
        ready: bool,
        failures: tuple[str, ...],
        bundle_sha256: str | None,
        commit_sha: str | None,
    ) -> str:
        return json.dumps(
            {
                "schema_version": "1",
                "ready": ready,
                "failures": list(failures),
                "bundle_sha256": bundle_sha256,
                "commit_sha": commit_sha,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def validate(self) -> None:
        if type(self.ready) is not bool or not isinstance(self.failures, tuple):
            raise ValueError("research decision fields are malformed")
        if any(not isinstance(item, str) for item in self.failures):
            raise ValueError("research decision failures must be strings")
        if self.ready != (not self.failures):
            raise ValueError("research decision readiness disagrees with failures")
        if self.bundle_sha256 is not None and (
            not isinstance(self.bundle_sha256, str)
            or len(self.bundle_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.bundle_sha256)
        ):
            raise ValueError("research decision bundle SHA-256 is invalid")
        if self.commit_sha is not None:
            _normalize_sha(self.commit_sha, "commit_sha")
        expected = sha256(
            self._canonical(
                self.ready,
                self.failures,
                self.bundle_sha256,
                self.commit_sha,
            ).encode("utf-8")
        ).hexdigest()
        if self.manifest_sha256 != expected:
            raise ValueError("research decision manifest SHA-256 is invalid")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": "1",
            "ready": self.ready,
            "failures": list(self.failures),
            "bundle_sha256": self.bundle_sha256,
            "commit_sha": self.commit_sha,
            "manifest_sha256": self.manifest_sha256,
        }


def _build_decision(
    ready: bool,
    failures: tuple[str, ...],
    bundle_sha256: str | None = None,
    commit_sha: str | None = None,
) -> ResearchReleaseDecision:
    manifest = sha256(
        ResearchReleaseDecision._canonical(
            ready, failures, bundle_sha256, commit_sha
        ).encode("utf-8")
    ).hexdigest()
    return ResearchReleaseDecision(
        ready, failures, bundle_sha256, commit_sha, manifest
    )


def evaluate_research_release(
    evidence: ResearchReleaseEvidence,
    *,
    bundle: ResearchReleaseEvidenceBundle | None = None,
    expected_commit_sha: str | None = None,
    artifact_bytes_by_name: Mapping[str, bytes] | None = None,
) -> ResearchReleaseDecision:
    """Require passing flags, complete artifact references, and an exact commit bind."""
    if not isinstance(evidence, ResearchReleaseEvidence):
        raise TypeError("evidence must be ResearchReleaseEvidence")

    checks = {
        "CI is not green": evidence.ci_green,
        "sample coverage is insufficient": evidence.sample_coverage,
        "edge matrix is not validated": evidence.edge_matrix_validated,
        "walk-forward stability is not validated": evidence.wfo_stability_validated,
        "purged walk-forward validation is not validated": evidence.purged_wfo_validated,
        "robustness is not validated": evidence.robustness_validated,
        "bootstrap expectancy validation is not validated": evidence.bootstrap_validated,
        "MAE/MFE is not validated": evidence.mae_mfe_validated,
        "execution quality is not validated": evidence.execution_quality_validated,
    }
    failures = [
        reason for reason, passed in checks.items()
        if type(passed) is not bool or not passed
    ]

    if bundle is None:
        failures.append("artifact-bound research evidence bundle is missing")
        return _build_decision(False, tuple(failures))
    if not isinstance(bundle, ResearchReleaseEvidenceBundle):
        failures.append("research evidence bundle has an invalid type")
        return _build_decision(False, tuple(failures))
    try:
        bundle.validate()
        records = bundle.as_map()
    except (TypeError, ValueError, OverflowError):
        failures.append("research evidence bundle integrity validation failed")
        return _build_decision(False, tuple(failures))

    if not isinstance(artifact_bytes_by_name, Mapping):
        failures.append("artifact file bytes are required for verification")
        artifact_bytes_by_name = {}
    elif any(
        not isinstance(name, str) or not isinstance(content, bytes)
        for name, content in artifact_bytes_by_name.items()
    ):
        failures.append("artifact files must map evidence names to bytes")
        artifact_bytes_by_name = {}
    extra_artifacts = set(artifact_bytes_by_name) - set(_REQUIRED_EVIDENCE)
    if extra_artifacts:
        failures.append("artifact bytes include unsupported evidence names")

    if expected_commit_sha is None:
        failures.append("expected source commit SHA is missing")
    else:
        try:
            expected_commit = _normalize_sha(expected_commit_sha, "expected_commit_sha")
        except ValueError:
            failures.append("expected source commit SHA is invalid")
        else:
            if bundle.commit_sha != expected_commit:
                failures.append("research evidence bundle is bound to a different commit")

    for name in _REQUIRED_EVIDENCE:
        record = records.get(name)
        if record is None:
            failures.append(f"missing artifact-bound research evidence: {name}")
        elif record.passed is not True:
            failures.append(f"research artifact did not pass: {name}")
        elif getattr(evidence, name) is not record.passed:
            failures.append(f"research evidence flag disagrees with artifact: {name}")
        artifact_bytes = artifact_bytes_by_name.get(name)
        if artifact_bytes is None:
            failures.append(f"research artifact bytes are missing: {name}")
        elif record is not None and not hmac.compare_digest(
            sha256(artifact_bytes).hexdigest(), record.artifact_sha256.lower()
        ):
            failures.append(f"research artifact digest mismatch: {name}")

    unique_failures = tuple(dict.fromkeys(failures))
    return _build_decision(
        not unique_failures,
        unique_failures,
        bundle.bundle_sha256,
        bundle.commit_sha,
    )
