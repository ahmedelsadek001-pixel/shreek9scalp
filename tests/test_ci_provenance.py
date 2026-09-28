from copy import deepcopy
from datetime import datetime, timezone

import pytest

from research.ci_provenance import build_ci_provenance, verify_ci_provenance


COMMIT = "c" * 40


def make_manifest(root):
    (root / "research").mkdir()
    (root / "research" / "engine.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_engine.py").write_text("assert True\n", encoding="utf-8")
    return build_ci_provenance(
        root,
        workflow="Python package",
        run_id="1234",
        run_attempt="1",
        repository="owner/repo",
        ref="refs/heads/v5.2-research-artifact",
        commit_sha=COMMIT,
        event="push",
        recorded_at=datetime(2026, 9, 26, tzinfo=timezone.utc),
    )


def test_ci_provenance_round_trip_binds_checkout_and_commit(tmp_path):
    payload = make_manifest(tmp_path)
    verify_ci_provenance(payload, root=tmp_path, expected_commit_sha=COMMIT)
    assert [item["path"] for item in payload["python_files"]] == ["research/engine.py"]


def test_ci_provenance_rejects_changed_source_bytes(tmp_path):
    payload = make_manifest(tmp_path)
    (tmp_path / "research" / "engine.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch: research/engine.py"):
        verify_ci_provenance(payload, root=tmp_path)


def test_ci_provenance_rejects_inventory_changes(tmp_path):
    payload = make_manifest(tmp_path)
    (tmp_path / "research" / "new_module.py").write_text("VALUE = 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory does not match"):
        verify_ci_provenance(payload, root=tmp_path)


def test_ci_provenance_rejects_wrong_commit_and_tampered_manifest(tmp_path):
    payload = make_manifest(tmp_path)
    with pytest.raises(ValueError, match="expected commit"):
        verify_ci_provenance(payload, root=tmp_path, expected_commit_sha="d" * 40)
    tampered = deepcopy(payload)
    tampered["event"] = "workflow_dispatch"
    with pytest.raises(ValueError, match="manifest digest mismatch"):
        verify_ci_provenance(tampered, root=tmp_path)


def test_ci_provenance_rejects_unsafe_or_duplicate_paths(tmp_path):
    payload = make_manifest(tmp_path)
    tampered = deepcopy(payload)
    tampered["python_files"][0]["path"] = "../outside.py"
    with pytest.raises(ValueError, match="unique and relative"):
        verify_ci_provenance(tampered, root=tmp_path)
