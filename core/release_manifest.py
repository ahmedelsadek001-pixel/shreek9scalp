"""Auditable release manifest for SHREEK V5.1 certification."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
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
        """Unambiguous canonical representation for manifest hashing."""
        return json.dumps(
            {
                "version": version,
                "commit_sha": commit_sha,
                "bundle_id": bundle_id,
                "ready": ready,
                "failures": list(failures),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def from_certification(
        cls,
        version: str,
        commit_sha: str,
        result: CertificationResult,
    ) -> "ReleaseManifest":
        if type(version) is not str or not version.strip():
            raise ValueError("version is required")
        version = version.strip()
        if any(ord(char) < 32 for char in version):
            raise ValueError("version must not contain control characters")
        if type(commit_sha) is not str or len(commit_sha) != 40:
            raise ValueError("commit_sha must be a 40-character SHA")
        normalized_sha = commit_sha.lower()
        if any(char not in "0123456789abcdef" for char in normalized_sha):
            raise ValueError("commit_sha must contain only hexadecimal characters")
        if not isinstance(result, CertificationResult):
            raise TypeError("result must be CertificationResult")
        if type(result.ready) is not bool:
            raise TypeError("certification ready must be bool")
        if type(result.bundle_id) is not str or len(result.bundle_id) != 64:
            raise ValueError("bundle_id must be a 64-character SHA-256")
        normalized_bundle = result.bundle_id.lower()
        if any(char not in "0123456789abcdef" for char in normalized_bundle):
            raise ValueError("bundle_id must contain only hexadecimal characters")
        if not isinstance(result.failures, tuple) or any(
            type(item) is not str or not item.strip() for item in result.failures
        ):
            raise TypeError("certification failures must be a tuple of non-empty strings")
        if result.ready != (len(result.failures) == 0):
            raise ValueError("certification readiness contradicts failures")
        if result.commit_sha is not None:
            if type(result.commit_sha) is not str or len(result.commit_sha) != 40:
                raise ValueError("certification commit_sha must be a 40-character SHA")
            certified_sha = result.commit_sha.lower()
            if any(char not in "0123456789abcdef" for char in certified_sha):
                raise ValueError("certification commit_sha must contain only hexadecimal characters")
            if certified_sha != normalized_sha:
                raise ValueError("manifest commit does not match certified evidence commit")

        canonical = cls._canonical(
            version, normalized_sha, normalized_bundle, result.ready, result.failures
        )
        return cls(
            version=version,
            commit_sha=normalized_sha,
            bundle_id=normalized_bundle,
            ready=result.ready,
            failures=result.failures,
            manifest_id=sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def validate(self) -> None:
        if type(self.version) is not str or not self.version.strip() or self.version != self.version.strip():
            raise ValueError("version must be a normalized non-empty string")
        if any(ord(char) < 32 for char in self.version):
            raise ValueError("version must not contain control characters")
        if type(self.commit_sha) is not str or len(self.commit_sha) != 40:
            raise ValueError("commit_sha must be a 40-character SHA")
        if self.commit_sha != self.commit_sha.lower() or any(
            char not in "0123456789abcdef" for char in self.commit_sha
        ):
            raise ValueError("commit_sha must be normalized hexadecimal")
        if type(self.bundle_id) is not str or len(self.bundle_id) != 64:
            raise ValueError("bundle_id must be a 64-character SHA-256")
        if self.bundle_id != self.bundle_id.lower() or any(
            char not in "0123456789abcdef" for char in self.bundle_id
        ):
            raise ValueError("bundle_id must be normalized hexadecimal")
        if type(self.ready) is not bool:
            raise TypeError("manifest ready must be bool")
        if not isinstance(self.failures, tuple) or any(
            type(item) is not str or not item.strip() for item in self.failures
        ):
            raise TypeError("manifest failures must be a tuple of non-empty strings")
        if self.ready != (len(self.failures) == 0):
            raise ValueError("manifest readiness contradicts failures")
        if type(self.manifest_id) is not str or len(self.manifest_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.manifest_id
        ):
            raise ValueError("manifest_id must be a normalized SHA-256")
        expected = sha256(
            self._canonical(
                self.version, self.commit_sha, self.bundle_id, self.ready, self.failures
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
