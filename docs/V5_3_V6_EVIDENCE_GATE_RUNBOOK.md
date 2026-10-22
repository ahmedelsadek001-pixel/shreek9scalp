# V5.3 / V6.0 Evidence Gate Runbook

Status: acceptance procedure only; no release or broker authority is granted by this document.

## Operating constraints

- Keep `main` unchanged and keep all candidate work in a reviewable draft pull request.
- Keep live order routing disabled. Do not send a broker order as part of CI, research, or this runbook.
- A green test suite establishes only the properties exercised by those tests.
- Bind every report to the exact source commit, configuration digest, dataset digest, symbol, timeframe, timezone policy, and run interval.
- Missing, stale, malformed, non-independent, or conflicting evidence fails the gate.

## Gate A — candidate identity and reproducibility

- [ ] Record the full candidate commit SHA and verify the checked-out tree is clean.
- [ ] Record Python/runtime versions and dependency lock or environment inventory.
- [ ] Record strategy/configuration identity and hashes of every dataset input.
- [ ] Re-run the full test suite and security gate on this exact commit.
- [ ] Preserve raw logs and machine-readable reports; do not copy results from a parent commit.
- [ ] Confirm no CI job can enable broker transport or live authorization.

**Pass condition:** all artifacts identify the same candidate and configuration; no result is silently attributed across revisions.

## Gate B — causal research and out-of-sample robustness

- [ ] Define chronological train, validation, and untouched test windows before examining results.
- [ ] Run walk-forward optimization over multiple chronological folds with leakage checks.
- [ ] Verify features, labels, normalization, and parameter selection use no future information.
- [ ] Evaluate the exact candidate detector and configuration on the held-out windows.
- [ ] Report net results after spread, commission, slippage assumptions, and any applicable swap.
- [ ] Report trade count, expectancy, profit factor, drawdown, MAE/MFE, and per-fold dispersion.
- [ ] Run parameter-neighborhood and regime sensitivity checks.
- [ ] Run Monte Carlo on trade-level outcomes and document the resampling method and limitations.
- [ ] Preserve losing, empty, and rejected windows; do not filter them out of aggregate reporting.
- [ ] Independently review the evidence manifest and reproduce the headline metrics.

**Pass condition:** predefined acceptance criteria are met on untouched chronological evidence, with adequate sample size and no unresolved leakage or provenance defect. A favorable aggregate alone is insufficient.

## Gate C — broker DEMO observation and reconciliation

- [ ] Run doctor and preflight; capture the complete machine-readable outputs.
- [ ] Verify broker, account mode, symbol mapping, contract size, volume limits, filling policy, timezone, and quote freshness from the connected terminal.
- [ ] Start a bounded DEMO/shadow session with live routing disabled.
- [ ] Capture every scan, signal, refusal, intent, and terminal observation with timestamps and stable identifiers.
- [ ] Export broker history independently from the terminal/account interface.
- [ ] Reconcile the export against the local journal; record unmatched, duplicated, rejected, partial, and unknown outcomes.
- [ ] Test disconnect, stale quote, terminal restart, duplicate intent, timeout, and uncertain broker outcome using safe test doubles or an explicitly bounded DEMO procedure.
- [ ] Verify recovery fails closed when broker state cannot be established.
- [ ] Keep zero-signal or zero-order sessions as valid observations, not proof of execution success.

**Pass condition:** broker-derived evidence is independently checked and reconciles with the journal; all unknown outcomes remain blocked pending resolution.

## Gate D — release and authorization

- [ ] Complete source-bound security review and inspect changed production code.
- [ ] Verify source archive and provenance artifacts against an independently obtained commit pin.
- [ ] Confirm all required research, DEMO, reconciliation, and recovery evidence is current and candidate-bound.
- [ ] Review every unresolved risk and record the operator's explicit decision.
- [ ] Keep the pull request in Draft until all required evidence has been reviewed.
- [ ] Require a separate, explicit human authorization process before any live-trading capability can be considered.

**Pass condition:** every mandatory gate has independently verifiable evidence and a named approval. CI success or source-archive integrity alone cannot authorize release or trading.

## Evidence index template

For each run, preserve:

| Field | Required value |
| --- | --- |
| Candidate | Full commit SHA and tree SHA |
| Configuration | Strategy/configuration ID and digest |
| Data | Dataset identifiers, hashes, time span, timezone |
| Runtime | OS, Python, dependency versions, terminal/broker build when applicable |
| Execution mode | Research / offline fake broker / DEMO shadow; explicitly state routing status |
| Outputs | Report paths, hashes, logs, test results |
| Exceptions | Missing data, refusals, unknown outcomes, reconciliation differences |
| Decision | Pass / fail / blocked, rationale, reviewer, timestamp |

Never replace a blocked result with a pass merely because the next run succeeds; retain both records and explain the change.
