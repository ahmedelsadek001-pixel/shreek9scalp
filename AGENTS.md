# SHREEK agent guidance

## Scope
- Work from `v5.1-development` in an isolated branch. Leave `main` untouched.
- Inspect current open PRs and their CI before starting. Continue an existing relevant draft before opening another. Keep changes focused and reviewable.
- Treat user corrections as proposed rules: verify them against code and evidence before changing this file.

## Safety
- Fail closed. Never activate live MT5 routing, send broker orders, or run DEMO submission commands in unattended work.
- Use mocks and offline fixtures for execution tests. Do not put credentials, account identifiers, tokens or private broker files in commits, logs or PR bodies.
- A blocked result or exit code 2 is a refusal, not permission to retry an order.

## Verification and phase gates
- Run the smallest relevant tests, then the full suite when the change touches shared safety boundaries. CI runs `pytest -q`, import validation, lint and the static release security gate on Python 3.9, 3.10 and 3.11.
- Report the exact candidate commit and matching CI run. If tests cannot run, disclose that and leave the PR Draft.
- Verify interacting drafts with `python -m utils.draft_integration_check` and immutable current base/head SHAs before reporting combined compatibility. Its temporary merge commits are verification only; never push them.
- Use `docs/V5_1_RELEASE_CHECKLIST.md` and `docs/V5_2_V5_3_V6_COMPLETION_MATRIX.md` for evidence gates. Missing, stale, malformed or conflicting evidence blocks promotion.
- CI success proves software checks only. It does not prove profitability, broker compatibility or release readiness.
- Do not merge a PR, change `main`, promote a phase or enable live trading in unattended work. Preserve explicit human review and empirical paper, shadow, recovery, broker and research evidence gates.

## Report
- Give the cause, files changed, tests run, exact result, PR and CI links, and remaining blockers. If no new verified improvement exists, make no speculative edit.
