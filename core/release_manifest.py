"""Auditable release manifest for SHREEK V5.1 certification."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping

from core.release_certification import CertificationResult


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    commit_sha: str
    bundle_id: str
    ready: bool
    failures: tuple[str, ...]
    manifest_id: str

    @classmethod
    def from_certification(
        cls,
        version: str,
        commit_sha: str,
        result: CertificationResult,
    ) -> "ReleaseManifest":
        if not version.strip():
            raise ValueError("version is required")
        if not commit_sha or len(commit_sha) != 40:
            raise ValueError("commit_sha must be a 40-character SHA")
        if not isinstance(result, CertificationResult):
            raise TypeError("result must be CertificationResult")
        canonical = "|".join(
            (version, commit_sha.lower(), result.bundle_id, str(result.ready), *result.failures)
        )
        return cls(
            version=version,
            commit_sha=commit_sha.lower(),
            bundle_id=result.bundle_id,
            ready=result.ready,
            failures=result.failures,
            manifest_id=sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def as_dict(self) -> Mapping[str, object]:
        return {
            "version": self.version,
            "commit_sha": self.commit_sha,
            "bundle_id": self.bundle_id,
            "ready": self.ready,
            "failures": self.failures,
            "manifest_id": self.manifest_id,
        }
