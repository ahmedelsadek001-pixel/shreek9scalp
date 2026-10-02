import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from utils import draft_integration_check as checker


def git(repo, *args):
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    return subprocess.check_output(
        ["git", "-c", "user.name=Integration fixture", "-c", "user.email=fixture@localhost",
         "-c", "commit.gpgsign=false", "-C", str(repo), *args], env=env, text=True).strip()


def commit(repo, message):
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def drafts(tmp_path):
    repo = tmp_path / "source with spaces"
    repo.mkdir()
    git(repo, "init", "--quiet", "-b", "development")
    (repo / "README.md").write_text("Fixture source\n")
    ancestor = commit(repo, "initial source")
    (repo / "left_value.py").write_text("VALUE = 0\n")
    (repo / "right_value.py").write_text("VALUE = 0\n")
    (repo / "tests").mkdir()
    (repo / "tests/test_candidate.py").write_text(
        "import left_value, right_value\n"
        "def test_combined_changes():\n"
        "    assert left_value.VALUE + right_value.VALUE == 3\n")
    base = commit(repo, "development base")
    git(repo, "checkout", "--quiet", "-b", "left", base)
    (repo / "left_value.py").write_text("VALUE = 1\n")
    left = commit(repo, "left draft")
    git(repo, "checkout", "--quiet", "-b", "right", base)
    (repo / "right_value.py").write_text("VALUE = 2\n")
    right = commit(repo, "right draft")
    git(repo, "checkout", "--quiet", "development")
    return repo, base, left, right, ancestor


def test_combines_committed_drafts_without_changing_dirty_source(drafts):
    repo, base, left, right, _ = drafts
    (repo / "left_value.py").write_text("VALUE = 777\n")
    (repo / "keep.txt").write_text("uncommitted user work\n")
    before = git(repo, "status", "--porcelain")
    report = checker.check_draft_integration(repo, base, [left, right])
    assert report["state"] == "software_checks_passed"
    assert report["pytest_exit_code"] == 0
    assert len(report["tree_sha"]) == 40
    assert len(report["pytest_log_sha256"]) == 64
    assert report["release_authorized"] is False
    assert git(repo, "rev-parse", "HEAD") == base
    assert git(repo, "status", "--porcelain") == before
    assert (repo / "left_value.py").read_text() == "VALUE = 777\n"
    assert (repo / "keep.txt").read_text() == "uncommitted user work\n"


def test_conflicting_drafts_block_before_tests(drafts):
    repo, base, left, _, _ = drafts
    git(repo, "checkout", "--quiet", "-b", "conflict", base)
    (repo / "left_value.py").write_text("VALUE = 5\n")
    other = commit(repo, "conflicting draft")
    git(repo, "checkout", "--quiet", "development")
    report = checker.check_draft_integration(repo, base, [left, other])
    assert report["state"] == "blocked"
    assert report["blocked_head_sha"] == other
    assert report["pytest_exit_code"] is None
    assert report["tree_sha"] is None
    assert git(repo, "rev-parse", "HEAD") == base
    assert git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize("passing_candidate", [False, True])
def test_inherited_common_directory_does_not_change_source(drafts, monkeypatch, passing_candidate):
    repo, base, left, right, _ = drafts
    config = (repo / ".git/config").read_bytes()
    before = git(repo, "worktree", "list", "--porcelain")
    (repo / "left_value.py").write_text("VALUE = 777\n")
    with monkeypatch.context() as inherited:
        inherited.setenv("GIT_COMMON_DIR", str(repo / ".git"))
        heads = [left, right] if passing_candidate else [left]
        report = checker.check_draft_integration(repo, base, heads)
    assert (repo / ".git/config").read_bytes() == config
    assert git(repo, "worktree", "list", "--porcelain") == before
    assert git(repo, "rev-parse", "HEAD") == base
    assert (repo / "left_value.py").read_text() == "VALUE = 777\n"
    assert report["pytest_exit_code"] == (0 if passing_candidate else 1)
    assert report["state"] == ("software_checks_passed" if passing_candidate else "blocked")
    assert report["release_authorized"] is False


def test_inherited_git_trace_does_not_write_outside_verification_clone(drafts, monkeypatch):
    repo, base, left, right, _ = drafts
    trace = repo / "caller-trace.log"
    with monkeypatch.context() as inherited:
        inherited.setenv("GIT_TRACE", str(trace))
        report = checker.check_draft_integration(repo, base, [left, right])
    assert not trace.exists()
    assert report["state"] == "software_checks_passed"
    assert report["pytest_exit_code"] == 0
    assert git(repo, "status", "--porcelain") == ""


def test_clone_is_independent_of_borrowed_object_storage(drafts, monkeypatch):
    repo, base, left, right, _ = drafts
    borrowed = repo.parent / "borrowed checkout"
    git(repo, "clone", "--quiet", "--shared", str(repo), str(borrowed))
    original = subprocess.run
    objects = repo / ".git/objects"
    backup = repo / ".git/objects-paused"

    def lose_borrowed_store(args, **kwargs):
        result = original(args, **kwargs)
        if args[0] == "git" and "clone" in args and result.returncode == 0:
            objects.rename(backup)
        return result

    monkeypatch.setattr(checker.subprocess, "run", lose_borrowed_store)
    try:
        report = checker.check_draft_integration(borrowed, base, [left, right])
    finally:
        if backup.exists():
            backup.rename(objects)
    assert report["state"] == "software_checks_passed"
    assert report["pytest_exit_code"] == 0


@pytest.mark.parametrize("bad_head", ["--force", "a" * 39, "A" * 40, None])
def test_requires_immutable_lowercase_commit_identities(drafts, bad_head):
    repo, base, _, _, _ = drafts
    report = checker.check_draft_integration(repo, base, [bad_head])
    assert report["state"] == "blocked"
    assert report["reason"] == "invalid integration inputs"
    assert report["head_shas"] == []


def test_duplicate_heads_and_missing_commit_are_blocked(drafts):
    repo, base, left, _, _ = drafts
    repeated = checker.check_draft_integration(repo, base, [left, left])
    assert repeated["reason"] == "invalid integration inputs"
    missing = checker.check_draft_integration(repo, base, ["f" * 40])
    assert missing["reason"] == "requested commit unavailable locally"
    assert missing["pytest_exit_code"] is None


def test_stale_draft_without_requested_base_is_blocked(drafts):
    repo, base, _, _, ancestor = drafts
    report = checker.check_draft_integration(repo, base, [ancestor])
    assert report["state"] == "blocked"
    assert report["blocked_head_sha"] == ancestor
    assert "does not include" in report["reason"]


def test_failed_candidate_tests_do_not_authorize_release(drafts):
    repo, base, left, _, _ = drafts
    report = checker.check_draft_integration(repo, base, [left])
    assert report["state"] == "blocked"
    assert report["reason"] == "combined candidate tests failed"
    assert report["pytest_exit_code"] == 1
    assert report["release_authorized"] is False


@pytest.mark.parametrize("commit_mutation", [False, True])
def test_candidate_source_mutation_blocks_even_when_pytest_passes(drafts, commit_mutation):
    repo, base, left, right, _ = drafts
    git(repo, "checkout", "--quiet", "-b", "mutating-tests", base)
    script = "from pathlib import Path\nimport subprocess\ndef test_change_source():\n"
    script += "    Path('left_value.py').write_text('VALUE = 99\\n')\n"
    if commit_mutation:
        script += "    subprocess.check_call(['git', 'add', 'left_value.py'])\n"
        script += ("    subprocess.check_call(['git', '-c', 'user.name=Fixture', '-c', "
                   "'user.email=fixture@localhost', '-c', 'commit.gpgsign=false', "
                   "'commit', '-m', 'mutate candidate'])\n")
    (repo / "tests/test_mutation.py").write_text(script)
    mutation = commit(repo, "mutating candidate tests")
    git(repo, "checkout", "--quiet", "development")
    report = checker.check_draft_integration(repo, base, [left, right, mutation])
    assert report["pytest_exit_code"] == 0
    assert report["state"] == "blocked"
    assert report["reason"] == "tests changed tracked candidate source"
    assert git(repo, "rev-parse", "HEAD") == base


def test_missing_pytest_is_redacted_and_blocks(drafts, monkeypatch):
    repo, base, left, right, _ = drafts
    original = subprocess.run

    def unavailable(args, **kwargs):
        if args[:3] == [sys.executable, "-c", "import pytest"]:
            return subprocess.CompletedProcess(args, 1, "", "private environment details")
        return original(args, **kwargs)

    monkeypatch.setattr(checker.subprocess, "run", unavailable)
    report = checker.check_draft_integration(repo, base, [left, right])
    assert report["state"] == "blocked"
    assert report["reason"] == "pytest unavailable for the current Python interpreter"
    assert "private" not in json.dumps(report)


def test_timeout_is_redacted_and_blocks(drafts, monkeypatch):
    repo, base, left, right, _ = drafts
    original = subprocess.run

    def timed_out(args, **kwargs):
        if args[0] == "git" and "clone" in args:
            raise subprocess.TimeoutExpired(args, 1, output="private environment details")
        return original(args, **kwargs)

    monkeypatch.setattr(checker.subprocess, "run", timed_out)
    report = checker.check_draft_integration(repo, base, [left, right])
    assert report["reason"] == "integration verification timed out"
    assert "private" not in json.dumps(report)


def test_cli_refusal_returns_exit_code_two_without_traceback(tmp_path):
    script = Path(checker.__file__)
    result = subprocess.run(
        [sys.executable, str(script), "--repo", str(tmp_path), "--base", "0" * 40,
         "--head", "1" * 40], capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["state"] == "blocked"
    assert "Traceback" not in result.stderr
