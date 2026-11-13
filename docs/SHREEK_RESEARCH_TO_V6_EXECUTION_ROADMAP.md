# SHREEK Research-to-V6 Execution Roadmap
**Status:** Adopted engineering roadmap — documentation proposal  
**Date:** 2026-11-13  
**Repository:** `ahmedelsadek001-pixel/shreek9scalp`  
**Baseline:** PR #18 candidate; this document does not authorize merge, release, broker routing, or live trading.

## 1. Purpose and governing principles

This roadmap converts the approved nine-part proposal into an implementation and evidence sequence aligned with the current SHREEK V5.2/V5.3 architecture.

Non-negotiable rules:

1. Preserve the current strategy implementation as an immutable research baseline. Experimental strategy changes belong in isolated candidates with distinct source/configuration identities.
2. Separate **software implementation**, **research evidence**, **DEMO execution evidence**, and **live authorization**. Passing one does not imply another.
3. Missing, stale, malformed, contradictory, or unauthenticated evidence is a failed gate (fail closed).
4. Never tune thresholds, sample windows, costs, or acceptance criteria after inspecting the final holdout results.
5. No broker order transport or live execution is enabled by this roadmap. DEMO and live authority remain separately gated.
6. No direct edits to `main` or `v5.1-development`; changes proceed through isolated branches and reviewable PRs.

## 2. Current verified baseline and known limitations

The 2026-11-13 PR #18 reproducibility record reports:

- 176 out-of-sample trades and +307.89 research units for the fixed 0.03-lot Breakout + Retest study.
- Statistical certification **FAILED**: the 95% expectancy interval crosses zero, the block-bootstrap lower bound is negative, and the non-positive bootstrap mean rate is 8.7%, above the recorded 5% ceiling.
- The dataset's internal OHLC aggregation checks passed, but independent broker-feed provenance has not been established.
- Spread, slippage, and commission values in the cost ledger are configured assumptions, not independently observed broker execution costs.
- The current stress ledger improves auditability; it does not constitute historical Bid/Ask replay.
- No new OOS study was run using the changed engine semantics described in PR #18.
- No MT5 terminal, DEMO order, or live order was used.

Therefore: V5.2 is not statistically certified; V5.3 remains in progress; V6.0 live-readiness is not established. These facts must remain visible in reports until replaced by newer, source-bound evidence.

## 3. Workstream A — Edge validation (first priority)

### A1. Protect the baseline
- Freeze and identify the current strategy source, configuration, data, and study specification by immutable commit/hash.
- Do not relax the baseline's entry/exit rules in place.
- Create isolated experimental variants for any changed entry, exit, filter, or holding-period rule.
- Ensure each report names the exact strategy implementation and configuration tested.

### A2. Attribute the four strategies independently
- Run each of the four strategy components separately before testing combinations.
- Use identical eligible data periods, cost assumptions, and evaluation conventions where comparison is meaningful.
- Report long and short separately, then combined. Treat the observed long/short difference as a hypothesis to validate, not a permanent rule.
- Retain failed and neutral strategy results; do not silently discard them.
- Test longer holding horizons/timeframes (including the observed 1–4 hour hypothesis) as predeclared candidates, not as a search over unlimited timeframe/parameter combinations.

### A3. Pre-register statistical acceptance
Before any candidate or holdout result is inspected, publish a versioned study specification defining:
- Minimum trade count and how that count was justified (power/precision and dependence assumptions).
- Net expectancy and its uncertainty interval.
- Net Profit Factor and drawdown limits, with costs included.
- Minimum number/proportion of positive chronological OOS windows.
- Bootstrap procedure, block length rationale, simulation count, and random seeds.
- Multiple-testing accounting and Deflated Sharpe Ratio (DSR) procedure.
- Treatment of overlapping trades, serial dependence, regime concentration, and missing data.

Do not invent universal PF or trade-count thresholds. Derive and freeze them from the risk mandate and statistical design before the evaluation. DSR is a correction for selection/multiple testing, not a substitute for untouched OOS validation.

### A4. Certification rule
A strategy is not accepted because aggregate P&L is positive. It must satisfy every pre-registered criterion on untouched chronological evidence after realistic costs. A failed candidate may be researched again only on development data; the final holdout must not be recycled for tuning.

## 4. Workstream B — Data integrity and execution-cost realism

- Acquire broker-specific XAUUSD tick data containing Bid and Ask, with source, symbol, server timezone, retrieval interval, and integrity metadata.
- Validate monotonic timestamps, duplicates, gaps, invalid/crossed quotes, stale quotes, session boundaries, and symbol contract metadata.
- Preserve raw data immutably and hash every dataset and derived dataset.
- Use Bid/Ask-side fills according to order direction and exit direction; OHLC-only tests remain diagnostic, not execution proof.
- Model spread as time- and condition-dependent using observed quotes. Model slippage from observed or explicitly conservative distributions; include commission and swap where applicable.
- Separate assumed, simulated, and independently observed costs in every report.
- Build historical quote replay and reconcile gross P&L, spread, slippage, commission, swap, and net P&L trade by trade.
- Run chronological walk-forward windows and reserve a final untouched holdout.
- Use block/bootstrap or other dependence-aware Monte Carlo methods; do not assume independent shuffled trades when serial dependence or regime clustering is material.

**Gate B:** no claim of broker-realistic execution until the source and completeness of the quote data are independently checked and the replay reconciles.

## 5. Workstream C — Risk controls enforced in code

Risk controls must sit outside and above strategy logic. A strategy must never override them.

Required controls:
- Allowlisted instrument/symbol identity; reject all non-approved symbols.
- Configurable daily trade-count limit, daily loss limit, total drawdown/equity stop, consecutive-loss stop, maximum open positions, and aggregate exposure cap.
- Position sizing from a configured risk fraction and validated stop distance, contract size, tick value, volume step/minimum, and account currency conversion; apply an independent maximum-lot cap.
- Spread ceiling, quote freshness/age limit, valid market/session checks, and rejection of malformed or out-of-order ticks.
- Manual and automatic kill switches with durable state and explicit reset policy.
- Fail closed on unknown account state, stale prices, invalid contract metadata, missing stop, or risk-calculation failure.
- Test boundary values, rounding, partial fills, gaps, rejected orders, and restart behavior.

Do not use a fixed lot as the primary risk model. A hard maximum lot may exist as a secondary safety ceiling.

## 6. Workstream D — Execution state, idempotency, and recovery

- Persist each trade intent before attempting transport and assign a unique internal intent identifier.
- Treat client identifiers, comments, or magic numbers as correlation aids, not proof of exactly-once execution.
- Implement an explicit state machine, including at least: CREATED, SUBMITTED, ACKNOWLEDGED, PARTIALLY_FILLED, FILLED, REJECTED, CANCELLED, and UNKNOWN.
- After timeout, restart, or disconnect, do not blindly resubmit. Reconcile broker orders, deals, and positions first.
- Treat broker-confirmed state as authoritative for actual positions; preserve the local durable event ledger for intent and audit history.
- Reconcile at startup, reconnect, and after every uncertain submission/fill transition.
- Test internet loss, terminal shutdown, process crash, delayed acknowledgements, partial fills, duplicate callbacks, and broker-side manual position changes.
- Demonstrate that recovery cannot create duplicate exposure or silently forget an open position.

**Gate D:** all uncertainty paths must end in a safe blocked/reconciled state, never an automatic duplicate submission.

## 7. Workstream E — AI boundary

- Keep AI advisory-only and outside the order authorization path.
- Deterministic strategy, risk, and execution code owns all decisions and broker commands.
- AI output may annotate context or explain a signal, but cannot bypass symbol, risk, quote, session, or kill-switch gates.
- If AI is unavailable, use a documented deterministic fallback; if a workflow explicitly requires AI, fail closed rather than silently substituting behavior.
- Log model/provider/version, request timestamp, prompt/template version, input references, response, latency, and errors with secrets and personal data excluded.
- Temperature zero is a variance-reduction setting, not a determinism guarantee.
- Do not feed live/future-derived information into historical backtests. Historical AI-assisted tests require timestamped, archived inputs and outputs available as of the simulated decision time; otherwise exclude AI from the backtest.

## 8. Workstream F — DEMO forward/shadow validation

Before starting, freeze the DEMO protocol:
- Minimum calendar duration and minimum eligible trades, justified in advance.
- Required market sessions and conditions.
- Exact source/config/data identities and broker account/server/symbol metadata.
- Allowed order types, volume ceiling, risk limits, and explicit DEMO-only transport controls.
- Acceptance criteria for order acknowledgement, fill quality, rejections, partial fills, latency, spread, slippage, reconciliation, and recovery.

Measure implementation shortfall from decision/reference price to actual broker fill, with direction and quantity handled correctly. Compare the observed distribution with the backtest's assumptions and stress limits. A material mismatch invalidates the execution model and returns the project to Workstream B.

DEMO success is not permission for live trading. Any future real-money pilot requires a separate written proposal, independent risk limits, and explicit human approval.

## 9. Workstream G — Monitoring and operational controls

- Add heartbeat and health status for process, data feed, terminal connection, and reconciliation loop.
- Add Telegram alerts only after secret-safe configuration, least-privilege handling, and delivery-failure behavior are tested.
- Persist structured decision, risk, order, fill, and reconciliation journals.
- Track rolling expectancy, drawdown, fill/slippage deviation, rejection rate, stale-data events, and system availability.
- Define monitoring windows and statistically defensible drift thresholds before use.
- Stop new entries automatically on hard safety violations or confirmed execution/data drift; do not stop on a short noisy expectancy fluctuation alone.
- Alerts are not a substitute for local fail-safe controls.

## 10. Workstream H — Engineering quality and PR #18

- Keep PR #18 Draft until its code, evidence, and review requirements are satisfied.
- Re-run research artifacts when engine semantics change; old OOS numbers do not automatically certify a changed candidate.
- Preserve source archive, commit/tree identity, study specification, raw/derived dataset hashes, configuration, dependency lock, CI provenance, and captured outputs for each result.
- Add focused tests for strategy attribution, decision path, risk rejection, broker state transitions, idempotency, recovery, and evidence tampering.
- The reported 291 files are the scope of a security scan, not a count of dead files. Do not delete or reduce files based on that number. First produce dependency/reference analysis, dead-code evidence, ownership review, and coverage gaps.
- CI success is necessary but does not prove strategy profitability, broker realism, or live safety.

## 11. Workstream I — V6.0 release gate

Maintain separate statuses:
- **Software complete:** modules, tests, documentation, reproducible builds, and security review are complete.
- **Research certified:** all pre-registered statistical and data-quality gates pass on untouched evidence.
- **DEMO validated:** sustained forward/shadow execution, broker reconciliation, fill quality, and recovery gates pass.
- **Live authorized:** separate explicit approval is recorded after every mandatory gate passes.

Final checklist is binary: PASS / FAIL / NOT VERIFIED. NOT VERIFIED is treated as FAIL. No averaging of scores and no waiver by CI status.

| Gate | Required evidence | Current disposition |
| --- | --- | --- |
| Baseline and candidate identities | Immutable source/config/data hashes | Partial; continue per candidate |
| Four-way strategy attribution | Separate long/short and strategy reports | Not verified in current reproducibility report |
| Pre-registered acceptance rules | Versioned study specification | To be completed before next study |
| DSR / multiple-testing control | Reproducible statistical report | Not evidenced in current report |
| Untouched chronological OOS | Fresh source-bound evaluation | Current study fails statistical certification |
| Broker tick provenance | Independently checked Bid/Ask source | Not verified |
| Historical Bid/Ask replay | Trade-level reconciliation | Not verified |
| Risk controls | Adversarial and boundary test evidence | Implementation/evidence review required |
| Execution idempotency/recovery | Disconnect/restart/replay tests | Not verified end-to-end |
| AI isolation | Architecture and negative tests | Must be verified |
| DEMO forward/shadow | Frozen protocol and broker reconciliation | Not verified |
| Monitoring/drift response | Fault injection and alert evidence | Not verified |
| Security/engineering review | Final review on exact release candidate | Pending |
| Explicit operator approval | Recorded approval after all prior gates | Not granted |

## 12. Ordered implementation sequence

1. **A — Freeze baseline and publish pre-registration template.**
2. **B — Build strategy attribution harness and isolated candidate reports.**
3. **C — Verify broker tick provenance and implement Bid/Ask replay.**
4. **D — Re-run chronological WFO, untouched holdout, DSR, and dependence-aware robustness.**
5. **E — Complete risk-control and execution-recovery test suites.**
6. **F — Verify AI isolation and deterministic fallback.**
7. **G — Run frozen DEMO forward/shadow protocol and reconciliation.**
8. **H — Complete monitoring, security review, and immutable evidence package.**
9. **I — Evaluate the V6.0 gate; require all PASS and separate explicit approval.

No later workstream may be used to bypass an earlier failed gate. Parallel implementation is permitted only where dependencies are respected and no unsafe execution authority is introduced.

## 13. Immediate next task

The next engineering task is **A1/A3: baseline freeze and pre-registered research specification**, followed by the isolated strategy-attribution harness. Do not change production entry/exit logic, merge PR #18, enable broker transport, or run live trading as part of this documentation adoption.

## References

- Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*: https://doi.org/10.3905/jpm.2014.40.5.094
- Perold (1988), *The Implementation Shortfall*: https://doi.org/10.3905/jpm.1988.409150
- MetaTrader 5 Python integration: https://www.mql5.com/en/docs/python_metatrader5
- Current project research evidence: `docs/V5_2_XAUUSD_2026_11_13_REPRODUCIBILITY.md`
- Current completion matrix: `docs/V5_2_V5_3_V6_COMPLETION_MATRIX.md`
- Source archive verification: `docs/SOURCE_ARCHIVE_VERIFICATION.md`

---
**Governance:** This roadmap is a documentation proposal on an isolated branch. It changes no strategy behavior and grants no order, DEMO, release, or live authority.
