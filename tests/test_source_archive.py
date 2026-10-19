import base64
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

from utils import source_archive as source


def git(repo, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.check_output(
        ["git", "-c", "user.name=Source fixture", "-c", "user.email=fixture@localhost",
         "-c", "commit.gpgsign=false", "-C", str(repo), *args], env=env)


def commit(repo, message="source fixture"):
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def packaged(tmp_path):
    repo = tmp_path / "source with spaces"
    repo.mkdir()
    git(repo, "init", "--quiet", "-b", "development")
    contents = {
        "README.md": b"Committed source\n",
        "runner.py": b"VALUE = 1\n",
        "a.txt": b"File before a directory in Git tree ordering\n",
        "a/nested/caf\u00e9.txt": "Unicode source\n".encode(),
        "config/defaults.json": b'{"demo_only":true}\n',
        "docs/Policy.md": b"Source evidence does not authorize execution.\n",
        "scripts/run.cmd": b"@echo off\r\necho DEMO\r\n",
        "scripts/check.sh": b"#!/bin/sh\nexit 0\n",
    }
    for name, data in contents.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    git(repo, "add", "--all")
    git(repo, "update-index", "--chmod=+x", "scripts/check.sh")
    git(repo, "commit", "--quiet", "-m", "public source fixture")
    pin = git(repo, "rev-parse", "HEAD").decode().strip()
    output = tmp_path / "source.zip"
    report = source.build_source_archive(repo, pin, output)
    assert report["state"] == "source_content_verified"
    return repo, pin, output, contents


def read_archive(path):
    with zipfile.ZipFile(path) as archive:
        return [(info, archive.read(info)) for info in archive.infolist()]


def write_archive(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for info, data in entries:
            archive.writestr(info, data)


def sealed(manifest):
    manifest.pop("manifest_sha256", None)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    manifest["manifest_sha256"] = sha256(canonical).hexdigest()
    return json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()


def change_manifest(path, change):
    entries = read_archive(path)
    updated = []
    for info, data in entries:
        if info.filename == source.MANIFEST_NAME:
            manifest = json.loads(data)
            change(manifest)
            data = sealed(manifest)
        updated.append((info, data))
    write_archive(path, updated)


def assert_blocked(report):
    assert report["state"] == "blocked"
    assert report["source_commit_verified"] is False
    assert report["source_tree_verified"] is False
    assert report["commit_sha"] is None
    assert report["tree_sha"] is None
    for key in ("signature_verified", "runtime_source_verified", "order_transport_enabled",
                "release_authorized", "live_authorized"):
        assert report[key] is False


def test_exact_committed_tree_includes_docs_config_and_executable_modes(packaged, tmp_path):
    repo, pin, output, contents = packaged
    report = source.verify_source_archive(output, pin)
    assert report["state"] == "source_content_verified"
    assert report["commit_sha"] == pin
    assert report["tree_sha"] == git(repo, "rev-parse", pin + "^{tree}").decode().strip()
    assert report["file_count"] == len(contents)
    assert report["archive_sha256"] == sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {*contents, source.MANIFEST_NAME}
        manifest = json.loads(archive.read(source.MANIFEST_NAME))
        assert base64.b64decode(manifest["commit_object_base64"]) == git(repo, "cat-file", "commit", pin)
        for entry in manifest["files"]:
            assert archive.read(entry["path"]) == contents[entry["path"]]
            assert entry["git_blob_sha"] == git(repo, "rev-parse", pin + ":" + entry["path"]).decode().strip()
            assert entry["mode"] == ("100755" if entry["path"].endswith(".sh") else "100644")
    for key in ("signature_verified", "runtime_source_verified", "order_transport_enabled",
                "release_authorized", "live_authorized"):
        assert report[key] is False
    duplicate = tmp_path / "second.zip"
    assert source.build_source_archive(repo, pin, duplicate)["state"] == "source_content_verified"
    assert output.read_bytes() == duplicate.read_bytes()


def test_untracked_and_dirty_work_cannot_enter_or_change_the_package(packaged, tmp_path):
    repo, pin, original, _ = packaged
    (repo / "README.md").write_text("Uncommitted edit\n")
    (repo / "untracked-delivery-proof.txt").write_text("Untracked fixture\n")
    (repo / "shreek-ci-provenance.json").write_text('{"untracked":true}\n')
    before = git(repo, "status", "--porcelain")
    config = (repo / ".git/config").read_bytes()
    output = repo / "working-source.zip"
    assert source.build_source_archive(repo, pin, output)["state"] == "source_content_verified"
    assert original.read_bytes() == output.read_bytes()
    output.unlink()
    assert git(repo, "status", "--porcelain") == before
    assert git(repo, "rev-parse", "HEAD").decode().strip() == pin
    assert (repo / ".git/config").read_bytes() == config
    assert (repo / "README.md").read_text() == "Uncommitted edit\n"
    assert (repo / "untracked-delivery-proof.txt").read_text() == "Untracked fixture\n"


def test_git_replacement_refs_and_inherited_git_settings_cannot_substitute_source(packaged, tmp_path, monkeypatch):
    repo, pin, original, _ = packaged
    (repo / "runner.py").write_text("VALUE = 999\n")
    replacement = commit(repo, "different source")
    git(repo, "replace", pin, replacement)
    refs = git(repo, "show-ref")
    config = (repo / ".git/config").read_bytes()
    with monkeypatch.context() as inherited:
        inherited.setenv("GIT_DIR", str(tmp_path / "absent-git-dir"))
        inherited.setenv("GIT_COMMON_DIR", str(tmp_path / "absent-common-dir"))
        inherited.setenv("GIT_CONFIG_COUNT", "1")
        inherited.setenv("GIT_CONFIG_KEY_0", "core.repositoryformatversion")
        inherited.setenv("GIT_CONFIG_VALUE_0", "999")
        output = tmp_path / "original-objects.zip"
        assert source.build_source_archive(repo, pin, output)["state"] == "source_content_verified"
    assert original.read_bytes() == output.read_bytes()
    assert git(repo, "show-ref") == refs
    assert (repo / ".git/config").read_bytes() == config
    assert git(repo, "rev-parse", "HEAD").decode().strip() == replacement


@pytest.mark.parametrize("pin", [None, True, [], "HEAD", "a" * 39, "A" * 40, "g" * 40, "a" * 40 + "\n"])
def test_invalid_independent_commit_pins_block(packaged, pin):
    _, _, output, _ = packaged
    assert_blocked(source.verify_source_archive(output, pin))


def test_wrong_independent_commit_blocks_even_a_valid_archive(packaged):
    _, _, output, _ = packaged
    assert_blocked(source.verify_source_archive(output, "a" * 40))


@pytest.mark.parametrize("name", ["runner.py", "config/defaults.json", "docs/Policy.md", "scripts/run.cmd"])
@pytest.mark.parametrize("operation", ["changed", "missing"])
def test_changes_and_omissions_block_for_python_and_non_python_source(packaged, name, operation):
    _, pin, output, _ = packaged
    entries = []
    for info, data in read_archive(output):
        if info.filename == name:
            if operation == "missing":
                continue
            data += b"Unreviewed change\n"
        entries.append((info, data))
    write_archive(output, entries)
    assert_blocked(source.verify_source_archive(output, pin))


@pytest.mark.parametrize("name", ["untracked.txt", "../escape.txt", "/absolute.txt", "x\\escape.txt"])
def test_extra_archive_members_block_without_extraction(packaged, name):
    _, pin, output, _ = packaged
    entries = read_archive(output)
    info = zipfile.ZipInfo(name)
    info.external_attr = 0o100644 << 16
    entries.append((info, b"Extra fixture\n"))
    write_archive(output, entries)
    assert_blocked(source.verify_source_archive(output, pin))


def test_rehashed_manifest_cannot_hide_an_omitted_committed_file(packaged):
    _, pin, output, _ = packaged
    write_archive(output, [(info, data) for info, data in read_archive(output) if info.filename != "docs/Policy.md"])
    change_manifest(output, lambda manifest: manifest.update(
        files=[entry for entry in manifest["files"] if entry["path"] != "docs/Policy.md"]))
    assert_blocked(source.verify_source_archive(output, pin))


def test_rehashed_manifest_cannot_authorize_changed_blob_bytes(packaged):
    _, pin, output, _ = packaged
    changed = b'{"demo_only":false}\n'
    write_archive(output, [(info, changed if info.filename == "config/defaults.json" else data)
                           for info, data in read_archive(output)])

    def mutate(manifest):
        entry = next(entry for entry in manifest["files"] if entry["path"] == "config/defaults.json")
        entry["sha256"] = sha256(changed).hexdigest()
        entry["git_blob_sha"] = sha1(b"blob " + str(len(changed)).encode() + b"\0" + changed).hexdigest()

    change_manifest(output, mutate)
    assert_blocked(source.verify_source_archive(output, pin))


def test_self_consistent_different_commit_cannot_relabel_itself_as_the_trusted_pin(packaged, tmp_path):
    repo, pin, _, _ = packaged
    (repo / "README.md").write_text("Different committed bytes\n")
    different = commit(repo, "different identity")
    output = tmp_path / "different.zip"
    assert source.build_source_archive(repo, different, output)["state"] == "source_content_verified"
    change_manifest(output, lambda manifest: manifest.update(commit_sha=pin))
    assert_blocked(source.verify_source_archive(output, pin))


def test_original_commit_payload_is_verified_after_manifest_rehash(packaged):
    _, pin, output, _ = packaged

    def mutate(manifest):
        original = base64.b64decode(manifest["commit_object_base64"])
        manifest["commit_object_base64"] = base64.b64encode(original + b"changed\n").decode()

    change_manifest(output, mutate)
    assert_blocked(source.verify_source_archive(output, pin))


@pytest.mark.parametrize("path", ["../runner.py", "/runner.py", "a//file", "a/./file", "a/../file",
                                  ".git/config", "a/.GIT/config", "NUL.txt", "COM1.log", "a/b ",
                                  "a/b.", "a:b", "a\\b", "a?b", "a|b", "a\x00b"])
def test_rehashed_unsafe_manifest_paths_block(packaged, path):
    _, pin, output, _ = packaged
    change_manifest(output, lambda manifest: manifest["files"][0].update(path=path))
    assert_blocked(source.verify_source_archive(output, pin))


@pytest.mark.parametrize("mutation", ["duplicate", "case-collision", "file-directory-collision", "unsorted",
                                       "symlink-mode", "bad-base64", "unknown-field", "bad-digest"])
def test_ambiguous_or_malformed_rehashed_manifests_block(packaged, mutation):
    _, pin, output, _ = packaged

    def mutate(manifest):
        if mutation == "duplicate":
            manifest["files"].append(dict(manifest["files"][0]))
            manifest["files"].sort(key=lambda entry: entry["path"])
        elif mutation in ("case-collision", "file-directory-collision"):
            entry = dict(manifest["files"][0])
            entry["path"] = "readme.md" if mutation == "case-collision" else "a"
            manifest["files"].append(entry)
            manifest["files"].sort(key=lambda item: item["path"])
        elif mutation == "unsorted":
            manifest["files"].reverse()
        elif mutation == "symlink-mode":
            manifest["files"][0]["mode"] = "120000"
        elif mutation == "bad-base64":
            manifest["commit_object_base64"] = "invalid!!"
        elif mutation == "unknown-field":
            manifest["authority"] = True
        else:
            manifest["files"][0]["sha256"] = "not-a-digest"

    change_manifest(output, mutate)
    assert_blocked(source.verify_source_archive(output, pin))


@pytest.mark.parametrize("data", [b'{"schema":"x","\\u0073chema":"x"}', b'{"files":[{"path":"x","path":"x"}]}',
                                 b'{"number":NaN}', b'\xff', b'[]'])
def test_ambiguous_and_invalid_json_block(packaged, data):
    _, pin, output, _ = packaged
    write_archive(output, [(info, data if info.filename == source.MANIFEST_NAME else old)
                           for info, old in read_archive(output)])
    assert_blocked(source.verify_source_archive(output, pin))


def test_duplicate_zip_member_blocks(packaged):
    _, pin, output, _ = packaged
    entries = read_archive(output)
    with pytest.warns(UserWarning, match="Duplicate name"):
        write_archive(output, entries + [entries[0]])
    assert_blocked(source.verify_source_archive(output, pin))


@pytest.mark.parametrize("mode", [0o120777, 0o040755, 0o100755, 0o106644])
def test_archive_permission_or_type_changes_block(packaged, mode):
    _, pin, output, _ = packaged
    entries = read_archive(output)
    next(info for info, _ in entries if info.filename == "runner.py").external_attr = mode << 16
    write_archive(output, entries)
    assert_blocked(source.verify_source_archive(output, pin))


def test_encrypted_zip_flag_blocks(packaged):
    _, pin, output, _ = packaged
    data = bytearray(output.read_bytes())
    # Modify both headers of the first member without relying on ZipFile's
    # writer, which clears the encryption flag for plaintext output.
    data[6] |= 1
    first_central = data.index(b"PK\x01\x02")
    data[first_central + 8] |= 1
    output.write_bytes(data)
    assert_blocked(source.verify_source_archive(output, pin))


@pytest.mark.parametrize("limit", ["MAX_ARCHIVE_BYTES", "MAX_TOTAL_BYTES", "MAX_MANIFEST_BYTES", "MAX_FILE_BYTES", "MAX_FILES"])
def test_archive_resource_limits_block(packaged, monkeypatch, limit):
    _, pin, output, _ = packaged
    monkeypatch.setattr(source, limit, 1)
    assert_blocked(source.verify_source_archive(output, pin))


def test_truncated_archive_blocks(packaged):
    _, pin, output, _ = packaged
    output.write_bytes(output.read_bytes()[:-20])
    assert_blocked(source.verify_source_archive(output, pin))


def test_verifier_needs_no_git_network_or_extraction(packaged, monkeypatch):
    _, pin, output, _ = packaged

    def forbidden(*args, **kwargs):
        raise AssertionError("verification must stay offline and read-only")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extract", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    before = output.read_bytes()
    assert source.verify_source_archive(output, pin)["state"] == "source_content_verified"
    assert output.read_bytes() == before


@pytest.mark.parametrize("unsupported", ["symlink", "gitlink", "reserved-manifest", "case-collision", "empty"])
def test_unsupported_original_trees_fail_without_output(tmp_path, unsupported):
    repo = tmp_path / "unsupported"
    repo.mkdir()
    git(repo, "init", "--quiet", "-b", "development")
    if unsupported == "symlink":
        (repo / "link").symlink_to("target")
    elif unsupported == "reserved-manifest":
        (repo / source.MANIFEST_NAME).write_text("Reserved source filename\n")
    elif unsupported == "case-collision":
        (repo / "README.md").write_text("One\n")
        (repo / "readme.md").write_text("Two\n")
    if unsupported == "gitlink":
        git(repo, "commit", "--quiet", "--allow-empty", "-m", "gitlink target")
        target = git(repo, "rev-parse", "HEAD").decode().strip()
        git(repo, "update-index", "--add", "--cacheinfo", "160000," + target + ",nested")
    else:
        git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "--allow-empty", "-m", "unsupported fixture")
    pin = git(repo, "rev-parse", "HEAD").decode().strip()
    output = tmp_path / "blocked.zip"
    assert_blocked(source.build_source_archive(repo, pin, output))
    assert not output.exists()


def test_existing_output_is_never_overwritten(packaged):
    repo, pin, output, _ = packaged
    before = output.read_bytes()
    assert_blocked(source.build_source_archive(repo, pin, output))
    assert output.read_bytes() == before


def test_failed_post_write_verification_removes_only_the_new_archive(packaged, tmp_path, monkeypatch):
    repo, pin, existing, _ = packaged
    before = existing.read_bytes()
    output = tmp_path / "new.zip"
    monkeypatch.setattr(source, "verify_source_archive", lambda *args: {"state": "blocked"})
    assert_blocked(source.build_source_archive(repo, pin, output))
    assert not output.exists()
    assert existing.read_bytes() == before


def test_cli_success_and_failure_emit_safe_reports(packaged, tmp_path, capsys):
    _, pin, output, _ = packaged
    assert source.main(["verify", "--archive", str(output), "--expected-commit", pin]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["state"] == "source_content_verified"
    private_label = "private-account-path-fixture.zip"
    assert source.main(["verify", "--archive", str(tmp_path / private_label), "--expected-commit", pin]) == 2
    emitted = capsys.readouterr().out
    assert private_label not in emitted
    assert "Source fixture" not in emitted
    assert "fixture@localhost" not in emitted
    assert_blocked(json.loads(emitted))


def test_cli_build_requires_an_immutable_pin_and_preserves_existing_data(packaged, tmp_path, capsys):
    repo, _, _, _ = packaged
    output = tmp_path / "keep.zip"
    output.write_bytes(b"Retained user artifact")
    assert source.main(["build", "--repo", str(repo), "--commit", "HEAD", "--output", str(output)]) == 2
    assert_blocked(json.loads(capsys.readouterr().out))
    assert output.read_bytes() == b"Retained user artifact"
