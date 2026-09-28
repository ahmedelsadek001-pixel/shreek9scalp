"""Command-line verifier for an artifact-bound V5.2 research release manifest.

Run with ``python -m research.research_release_cli --manifest release.json``.
The command only evaluates research readiness; it never enables trading.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hmac
import json
from pathlib import Path
import sys
from typing import Any

from research.research_release_gate import (
    ResearchReleaseEvidence,
    ResearchReleaseEvidenceBundle,
    ResearchReleaseEvidenceRecord,
    evaluate_research_release,
)


_EVIDENCE_NAMES = tuple(ResearchReleaseEvidence.__dataclass_fields__)
_TOP_LEVEL = {"schema_version", "expected_commit_sha", "evidence", "records"}
_RECORD_FIELDS = {
    "name", "passed", "source", "run_id", "recorded_at", "commit_sha",
    "artifact_path", "artifact_sha256",
}


class ManifestError(ValueError):
    """The input manifest or one of its referenced artifacts is invalid."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError("manifest contains a duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ManifestError("manifest contains a non-standard JSON number")


def _read_manifest(path: Path) -> tuple[ResearchReleaseEvidence, ResearchReleaseEvidenceBundle, dict[str, bytes], str]:
    try:
        manifest_path = path.resolve(strict=True)
        if not manifest_path.is_file():
            raise ManifestError("manifest path must be a regular file")
        raw = manifest_path.read_text(encoding="utf-8")
        payload = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except ManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError("manifest could not be read as UTF-8 JSON") from exc

    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL:
        raise ManifestError("manifest must contain exactly schema_version, expected_commit_sha, evidence, and records")
    if payload["schema_version"] != "1":
        raise ManifestError("unsupported manifest schema_version")
    expected_commit = payload["expected_commit_sha"]
    if not isinstance(expected_commit, str):
        raise ManifestError("expected_commit_sha must be a string")

    flags = payload["evidence"]
    if not isinstance(flags, dict) or set(flags) != set(_EVIDENCE_NAMES):
        raise ManifestError("evidence must contain exactly the nine required boolean flags")
    if any(type(value) is not bool for value in flags.values()):
        raise ManifestError("evidence flags must be booleans")
    evidence = ResearchReleaseEvidence(**flags)

    records_payload = payload["records"]
    if not isinstance(records_payload, list) or len(records_payload) != len(_EVIDENCE_NAMES):
        raise ManifestError("records must contain exactly one record for each required evidence name")

    base_dir = manifest_path.parent.resolve()
    records: list[ResearchReleaseEvidenceRecord] = []
    artifacts: dict[str, bytes] = {}
    for item in records_payload:
        if not isinstance(item, dict) or set(item) != _RECORD_FIELDS:
            raise ManifestError("each record must contain the exact required metadata and artifact fields")
        name = item["name"]
        if not isinstance(name, str) or name not in _EVIDENCE_NAMES or name in artifacts:
            raise ManifestError("record names must be unique supported evidence names")
        if type(item["passed"]) is not bool:
            raise ManifestError("record passed must be a boolean")
        try:
            recorded_at = datetime.fromisoformat(item["recorded_at"])
        except (TypeError, ValueError) as exc:
            raise ManifestError("record recorded_at must be an ISO-8601 timestamp") from exc
        if recorded_at.utcoffset() is None:
            raise ManifestError("record recorded_at must include a timezone")

        relative = item["artifact_path"]
        if not isinstance(relative, str) or not relative.strip():
            raise ManifestError("artifact_path must be a non-empty relative path")
        artifact_path = (base_dir / relative).resolve()
        try:
            artifact_path.relative_to(base_dir)
        except ValueError as exc:
            raise ManifestError("artifact_path must stay within the manifest directory") from exc
        if not artifact_path.is_file():
            raise ManifestError("artifact_path must point to a regular file")
        try:
            artifact_bytes = artifact_path.read_bytes()
        except OSError as exc:
            raise ManifestError("an evidence artifact could not be read") from exc

        record = ResearchReleaseEvidenceRecord.from_artifact_bytes(
            name=name,
            passed=item["passed"],
            source=item["source"],
            run_id=item["run_id"],
            recorded_at=recorded_at,
            commit_sha=item["commit_sha"],
            artifact_bytes=artifact_bytes,
        )
        expected_digest = item["artifact_sha256"]
        if not isinstance(expected_digest, str) or not hmac.compare_digest(
            record.artifact_sha256, expected_digest.lower()
        ):
            raise ManifestError(f"artifact SHA-256 does not match the manifest: {name}")
        records.append(record)
        artifacts[name] = artifact_bytes

    if set(artifacts) != set(_EVIDENCE_NAMES):
        raise ManifestError("records do not cover every required evidence name")
    try:
        bundle = ResearchReleaseEvidenceBundle.from_records(tuple(records))
    except (TypeError, ValueError) as exc:
        raise ManifestError("research evidence records failed integrity validation") from exc
    return evidence, bundle, artifacts, expected_commit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a V5.2 artifact-bound research release manifest")
    parser.add_argument("--manifest", required=True, type=Path, help="JSON manifest; artifact paths are relative to its directory")
    args = parser.parse_args(argv)
    try:
        evidence, bundle, artifacts, expected_commit = _read_manifest(args.manifest)
    except (ManifestError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"schema_version": "1", "ready": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2

    decision = evaluate_research_release(
        evidence,
        bundle=bundle,
        expected_commit_sha=expected_commit,
        artifact_bytes_by_name=artifacts,
    )
    print(json.dumps(decision.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if decision.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
