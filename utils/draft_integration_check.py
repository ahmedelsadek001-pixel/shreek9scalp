"""Check immutable draft commits in a disposable, local-only Git clone."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Sequence


_SHA = re.compile(r"[0-9a-f]{40}\Z")


def check_draft_integration(repo: Path, base: str, heads: Sequence[str],
                            *, timeout_seconds: int = 300) -> dict[str, Any]:
    """Merge and test committed source without changing the source repository.

    All objects must already exist locally. This performs no fetch, push,
    package installation, broker access, or release authorization.
    """
    report: dict[str, Any] = {
        "state": "blocked", "reason": "invalid integration inputs",
        "base_sha": None, "head_shas": [], "tree_sha": None,
        "blocked_head_sha": None, "pytest_exit_code": None,
        "pytest_log_sha256": None, "release_authorized": False,
    }

    def blocked(reason: str) -> dict[str, Any]:
        report["reason"] = reason
        return report

    if (not isinstance(repo, Path) or not isinstance(base, str) or not _SHA.fullmatch(base)
            or not isinstance(heads, (tuple, list)) or not 1 <= len(heads) <= 16
            or any(not isinstance(head, str) or not _SHA.fullmatch(head) for head in heads)
            or len(set(heads)) != len(heads) or base in heads
            or type(timeout_seconds) is not int or timeout_seconds <= 0):
        return report
    report.update(base_sha=base, head_shas=list(heads))
    heads = tuple(heads)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_") and key not in {
               "PYTHONPATH", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"}}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0")

    def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout_seconds, shell=False)

    try:
        with TemporaryDirectory(prefix="shreek-integration-") as temporary:
            scratch = Path(temporary)
            hooks = scratch / "empty-hooks"
            hooks.mkdir()

            def git(where: Path, *args: str) -> subprocess.CompletedProcess:
                return run(["git", "-c", "core.hooksPath=" + str(hooks),
                            "-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
                            "-c", "commit.gpgsign=false", "-c", "user.name=SHREEK verification",
                            "-c", "user.email=verification@localhost", *args], where)

            root = git(repo, "rev-parse", "--show-toplevel")
            if root.returncode:
                return blocked("source Git repository unavailable")
            if run([sys.executable, "-c", "import pytest"], scratch).returncode:
                return blocked("pytest unavailable for the current Python interpreter")
            store = scratch / "repository.git"
            candidate = scratch / "candidate"
            cloned = git(scratch, "clone", "--quiet", "--local", "--no-hardlinks",
                         "--dissociate", "--mirror", "--", root.stdout.strip(), str(store))
            if cloned.returncode:
                return blocked("local verification clone unavailable")
            for commit in [base, *heads]:
                if git(store, "cat-file", "-e", commit + "^{commit}").returncode:
                    return blocked("requested commit unavailable locally")
            for head in heads:
                if git(store, "merge-base", "--is-ancestor", base, head).returncode:
                    report["blocked_head_sha"] = head
                    return blocked("draft does not include the requested development base")
            if git(store, "worktree", "add", "--quiet", "--detach", str(candidate), base).returncode:
                return blocked("candidate checkout failed")
            for head in heads:
                if git(candidate, "merge", "--quiet", "--no-edit", "--no-ff", head).returncode:
                    report["blocked_head_sha"] = head
                    return blocked("draft merge failed; inspect compatibility independently")
            tree = git(candidate, "rev-parse", "HEAD^{tree}")
            if tree.returncode or not _SHA.fullmatch(tree.stdout.strip()):
                return blocked("combined source tree unavailable")
            report["tree_sha"] = tree.stdout.strip()
            env["PYTHONPATH"] = str(candidate)
            tests = run([sys.executable, "-m", "pytest", "-q"], candidate)
            report["pytest_exit_code"] = tests.returncode
            report["pytest_log_sha256"] = sha256(
                (tests.stdout + "\n" + tests.stderr).encode("utf-8")).hexdigest()
            if tests.returncode:
                return blocked("combined candidate tests failed")
            status = git(candidate, "status", "--porcelain", "--untracked-files=no")
            current_tree = git(candidate, "rev-parse", "HEAD^{tree}")
            if (status.returncode or status.stdout.strip() or current_tree.returncode
                    or current_tree.stdout.strip() != report["tree_sha"]):
                return blocked("tests changed tracked candidate source")
            report.update(state="software_checks_passed", reason="combined source tree passed pytest")
            return report
    except subprocess.TimeoutExpired:
        return blocked("integration verification timed out")
    except (OSError, UnicodeError, ValueError):
        return blocked("integration verification environment unavailable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True, help="immutable development commit SHA")
    parser.add_argument("--head", action="append", required=True, help="immutable draft commit SHA")
    args = parser.parse_args()
    report = check_draft_integration(args.repo, args.base, args.head)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["state"] == "software_checks_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
