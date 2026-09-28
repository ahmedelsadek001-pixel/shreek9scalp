import json
from hashlib import sha256

from research.research_release_cli import main
from research.research_release_gate import ResearchReleaseEvidence


COMMIT = "a" * 40
NAMES = tuple(ResearchReleaseEvidence.__dataclass_fields__)


def create_manifest(tmp_path, *, passed=True):
    rows = []
    for name in NAMES:
        artifact = f"evidence/{name}.json"
        path = tmp_path / artifact
        path.parent.mkdir(exist_ok=True)
        content = f"evidence for {name}".encode()
        path.write_bytes(content)
        rows.append({
            "name": name,
            "passed": passed,
            "source": f"ci/{name}",
            "run_id": f"run-{name}",
            "recorded_at": "2026-09-26T12:00:00+00:00",
            "commit_sha": COMMIT,
            "artifact_path": artifact,
            "artifact_sha256": sha256(content).hexdigest(),
        })
    manifest = {
        "schema_version": "1",
        "expected_commit_sha": COMMIT,
        "evidence": {name: passed for name in NAMES},
        "records": rows,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, manifest


def test_cli_archives_a_ready_decision_and_exits_zero(tmp_path, capsys):
    manifest_path, _ = create_manifest(tmp_path)
    assert main(["--manifest", str(manifest_path)]) == 0
    captured = capsys.readouterr()
    decision = json.loads(captured.out)
    assert decision["ready"] is True
    assert decision["commit_sha"] == COMMIT
    assert len(decision["bundle_sha256"]) == 64
    assert len(decision["manifest_sha256"]) == 64
    assert captured.err == ""


def test_cli_emits_a_failed_decision_and_nonzero_status(tmp_path, capsys):
    manifest_path, _ = create_manifest(tmp_path, passed=False)
    assert main(["--manifest", str(manifest_path)]) == 1
    decision = json.loads(capsys.readouterr().out)
    assert decision["ready"] is False
    assert decision["failures"]


def test_cli_rejects_changed_artifact_and_reports_manifest_error(tmp_path, capsys):
    manifest_path, _ = create_manifest(tmp_path)
    (tmp_path / "evidence" / f"{NAMES[0]}.json").write_text("changed")
    assert main(["--manifest", str(manifest_path)]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ready"] is False
    assert "SHA-256" in error["error"]


def test_cli_rejects_artifact_path_outside_manifest_directory(tmp_path, capsys):
    manifest_path, manifest = create_manifest(tmp_path)
    manifest["records"][0]["artifact_path"] = "../outside.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert main(["--manifest", str(manifest_path)]) == 2
    error = json.loads(capsys.readouterr().err)
    assert "within the manifest directory" in error["error"]


def test_cli_rejects_non_boolean_evidence_flags(tmp_path, capsys):
    manifest_path, manifest = create_manifest(tmp_path)
    manifest["evidence"][NAMES[0]] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert main(["--manifest", str(manifest_path)]) == 2
    error = json.loads(capsys.readouterr().err)
    assert "booleans" in error["error"]
