# Isolated development-draft verification

CI on individual drafts does not test their combined source tree. Use this
offline development check before claiming that interacting drafts work together.
It evaluates committed source in a disposable local clone and runs pytest there.

## Inputs

- A Git checkout containing the exact lowercase 40-character development SHA
  and each selected draft SHA, reachable from its local or remote-tracking
  references. A downloaded source archive is insufficient.
- Each draft must contain the requested development base. Refresh/reconcile
  stale drafts separately; this tool does not fetch or rebase them.
- The current Python interpreter must have pytest and the project's CI
  dependencies installed. The tool installs nothing.

From the project root, substitute full commit IDs:

```text
python -m utils.draft_integration_check --repo . --base FULL_DEVELOPMENT_SHA --head FULL_DRAFT_SHA --head ANOTHER_DRAFT_SHA
```

The standalone `utils/draft_integration_check.py` file also accepts an absolute
`--repo` path when the caller is outside the checkout. This avoids relying on
the current PowerShell directory being a Git repository.

## Result and boundaries

Exit code 0 means `software_checks_passed`: every requested draft merged, pytest
returned 0, and tracked candidate source still matches the tested Git tree.
The JSON binds the result to base/head SHAs, the combined tree SHA, pytest's
exit status, and a SHA-256 of captured test output. It does not invent a test
count or print captured Git/test diagnostics. Retain normal CI results separately.

Exit code 2 means blocked: invalid identity, unavailable Git object or pytest,
stale base, merge failure, test failure, timeout, source mutation, or an
unavailable verification environment. It does not authorize an order retry.

The source checkout, its branches, index and uncommitted files are not used as
a merge workspace. Temporary verification commits remain in the disposable
clone and are removed after the run. A local mirror preserves remote-tracking
references, and its detached worktree holds the candidate. It uses copies rather than object
hardlinks and dissociates borrowed object stores; Git hooks and signing are
disabled for verification operations. Git network transports are disabled.
All inherited `GIT_*` overrides are excluded from subprocesses before the
checker supplies its controlled configuration. In particular, `GIT_COMMON_DIR`
must not redirect clone operations to the caller's repository metadata, and
`GIT_TRACE` must not write diagnostics outside the disposable clone. Python
search/test-selection overrides are also excluded.

The tool performs no fetch, push, package installation, broker command or
release authorization. Unit tests must use mocks/offline data under AGENTS.md.
Running a repository's tests executes its committed test code; review the
selected source before checking it. OOS, robustness, paper/shadow, independent
broker evidence, recovery, security review and human approval remain separate
release requirements.

Git reference: [local clone and object-copy options](https://git-scm.com/docs/git-clone).
See also [Git environment variables](https://git-scm.com/docs/git#_environment_variables).
