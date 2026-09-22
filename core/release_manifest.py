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

    @staticmethod
    def _canonical(
        version: str,
        commit_sha: str,
        bundle_id: str,
        ready: bool,
        failures: tuple[str, ...],
    ) -> str:
        return "|".join((version, commit_sha, bundle_id, str(ready), *failures))

    @classmethod
    def from_certification(
        cls,
        version: str,
        commit_sha: str,
        result: CertificationResult,
    ) -> "ReleaseManifest":
        if not isinstance(version, str) or not version.strip():
            raise ValueError("version is required")
        if not isinstance(commit_sha, str) or len(commit_sha) != 40:
            raise ValueError("commit_sha must be a 40-character SHA")
        normalized_sha = commit_sha.lower()
        if any(char not in "0123456789abcdef" for char in normalized_sha):
            raise ValueError("commit_sha must contain only hexadecimal characters")
        if not isinstance(result, CertificationResult):
            raise TypeError("result must be CertificationResult")
        if type(result.ready) is not bool:
            raise TypeError("certification ready must be bool")
        if not isinstance(result.bundle_id, str) or len(result.bundle_id) != 64:
            raise ValueError("bundle_id must be a 64-character SHA-256")
        if any(char not in "0123456789abcdef" for char in result.bundle_id.lower()):
            raise ValueError("bundle_id must contain only hexadecimal characters")
        if not isinstance(result.failures, tuple) or any(
            type(item) is not str or not item.strip() for item in result.failures
        ):
            raise TypeError("certification failures must be a tuple of non-empty strings")
        if result.ready != (len(result.failures) == 0):
            raise ValueError("certification readiness contradicts failures")
        canonical = cls._canonical(
            version,
            normalized_sha,
            result.bundle_id.lower(),
            result.ready,
            result.failures,
        )
        return cls(
            version=version,
            commit_sha=normalized_sha,
            bundle_id=result.bundle_id.lower(),
            ready=result.ready,
            failures=result.failures,
            manifest_id=sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def validate(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version is required")
        if not isinstance(self.commit_sha, str) or len(self.commit_sha) != 40:
            raise ValueError("commit_sha must be a 40-character SHA")
        if any(char not in "0123456789abcdef" for char in self.commit_sha.lower()):
            raise ValueError("commit_sha must contain only hexadecimal characters")
        if not isinstance(self.bundle_id, str) or len(self.bundle_id) != 64:
            raise ValueError("bundle_id must be a 64-character SHA-256")
        if any(char not in "0123456789abcdef" for char in self.bundle_id.lower()):
            raise ValueError("bundle_id must contain only hexadecimal characters")
        if type(self.ready) is not bool:
            raise TypeError("manifest ready must be bool")
        if not isinstance(self.failures, tuple) or any(
            type(item) is not str or not item.strip() for item in self.failures
        ):
            raise TypeError("manifest failures must be a tuple of non-empty strings")
        if self.ready != (len(self.failures) == 0):
            raise ValueError("manifest readiness contradicts failures")
        expected = sha256(
            self._canonical(
                self.version,
                self.commit_sha.lower(),
                self.bundle_id.lower(),
                self.ready,
                self.failures,
            ).encode("utf-8")
        ).hexdigest()
        if self.manifest_id != expected:
            raise ValueError("manifest_id does not match manifest contents")

    def as_dict(self) -> Mapping[str, object]:
        self.validate()
        return {
            "version": self.version,
            "commit_sha": self.commit_sha,
            "bundle_id": self.bundle_id,
            "ready": self.ready,
            "failures": self.failures,
            "manifest_id": self.manifest_id,
        }
