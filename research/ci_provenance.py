"""Build and verify reproducible SHREEK CI source provenance manifests."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
from pathlib import Path
from typing import Any, Mapping


_SCHEMA = "shreek.ci-provenance.v1"
_EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", "tests", ".pytest_cache"}
_FIELDS = {
    "schema", "workflow", "run_id", "run_attempt", "repository", "ref",
    "commit_sha", "event", "recorded_at", "python_files",
}


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _source_files(root: Path) -> dict[str, str]:
    root = root.resolve(strict=True)
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        if any(part in _EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        result[relative] = sha256(path.read_bytes()).hexdigest()
    if not result:
        raise ValueError("no production Python source files found")
    return result


def build_ci_provenance(
    root: Path,
    *,
    workflow: str,
    run_id: str,
    run_attempt: str,
    repository: str,
    ref: str,
    commit_sha: str,
    event: str,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Hash the production Python tree and CI run identity into a manifest."""
    for name, value in (
        ("workflow", workflow), ("run_id", run_id), ("run_attempt", run_attempt),
        ("repository", repository), ("ref", ref), ("event", event),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
    if not isinstance(commit_sha, str) or len(commit_sha) != 40 or any(
        char not in "0123456789abcdefABCDEF" for char in commit_sha
    ):
        raise ValueError("commit_sha must be a 40-character hexadecimal SHA")
    recorded_at = recorded_at or datetime.now(timezone.utc)
    if not isinstance(recorded_at, datetime) or recorded_at.utcoffset() is None:
        raise ValueError("recorded_at must be timezone-aware")

    files = _source_files(Path(root))
    payload: dict[str, Any] = {
        "schema": _SCHEMA,
        "workflow": workflow,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "repository": repository,
        "ref": ref,
        "commit_sha": commit_sha.lower(),
        "event": event,
        "recorded_at": recorded_at.astimezone(timezone.utc).isoformat(),
        "python_files": [
            {"path": path, "sha256": digest} for path, digest in sorted(files.items())
        ],
    }
    payload["manifest_sha256"] = _canonical_digest(payload)
    return payload


def verify_ci_provenance(
    payload: Mapping[str, Any],
    *,
    root: Path,
    expected_commit_sha: str | None = None,
) -> None:
    """Raise ValueError unless manifest, commit, inventory, and bytes all match."""
    if not isinstance(payload, Mapping) or set(payload) != _FIELDS | {"manifest_sha256"}:
        raise ValueError("CI provenance manifest has an invalid schema")
    if payload["schema"] != _SCHEMA:
        raise ValueError("unsupported CI provenance schema")
    for name in ("workflow", "run_id", "run_attempt", "repository", "ref", "event"):
        value = payload[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"CI provenance {name} is invalid")
    commit_sha = payload["commit_sha"]
    if not isinstance(commit_sha, str) or len(commit_sha) != 40 or any(
        char not in "0123456789abcdef" for char in commit_sha
    ):
        raise ValueError("CI provenance commit SHA is invalid")
    if expected_commit_sha is not None and not hmac.compare_digest(
        commit_sha, expected_commit_sha.lower()
    ):
        raise ValueError("CI provenance commit does not match the expected commit")
    try:
        timestamp = datetime.fromisoformat(payload["recorded_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("CI provenance timestamp is invalid") from exc
    if timestamp.utcoffset() is None:
        raise ValueError("CI provenance timestamp must include a timezone")

    entries = payload["python_files"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("CI provenance source inventory is empty or malformed")
    declared: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ValueError("CI provenance source entry is malformed")
        path, digest = entry["path"], entry["sha256"]
        if not isinstance(path, str) or not isinstance(digest, str):
            raise ValueError("CI provenance source path or digest is malformed")
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or path in declared:
            raise ValueError("CI provenance source paths must be unique and relative")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("CI provenance source digest is invalid")
        declared[path] = digest

    actual = _source_files(Path(root))
    if set(declared) != set(actual):
        raise ValueError("CI provenance source inventory does not match the checkout")
    for path, expected_digest in declared.items():
        if not hmac.compare_digest(expected_digest, actual[path]):
            raise ValueError(f"CI provenance source digest mismatch: {path}")

    manifest_digest = payload["manifest_sha256"]
    if not isinstance(manifest_digest, str) or len(manifest_digest) != 64 or not hmac.compare_digest(
        manifest_digest, _canonical_digest(payload)
    ):
        raise ValueError("CI provenance manifest digest mismatch")


def main(argv: list[str] | None = None) -> int:
    """Verify a downloaded provenance JSON file against a source checkout."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Verify a SHREEK CI provenance manifest")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-commit-sha")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
        verify_ci_provenance(
            payload, root=args.root, expected_commit_sha=args.expected_commit_sha
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({
        "valid": True,
        "commit_sha": payload["commit_sha"],
        "manifest_sha256": payload["manifest_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
