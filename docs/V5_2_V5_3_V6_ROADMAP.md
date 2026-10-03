# SHREEK V5.2 → V6.0 Completion Roadmap

## V5.2 Research
- MAE/MFE excursion analytics.
- Strategy/setup attribution.
- Deterministic market-regime classification.
- Regime attribution.
- Setup × regime Edge Matrix.
- Advanced walk-forward stability analysis.
- Research outputs remain isolated from execution.

## V5.3 Execution Safety
- Paper trading and shadow execution.
- Order reconciliation.
- Reconciliation accepts only typed `BUY`/`SELL` execution directions.
  Matching `RANGE` or `UNKNOWN` labels cannot prove a fill, resolve an unknown
  submission or remove a pending shadow order from the recovery gate.
- Disconnect/recovery state machine.
- Recovery approvals are issued only by their owning state machine and are
  bound to its latest decision plus the current shadow revision. Fabricated,
  copied, edited or superseded approvals—and an environment gate retained
  after a shadow submission or reconciliation change—fail before transport.
  This is an in-process freshness control, not broker evidence or live
  authority.
- Execution-quality and slippage analytics.
- Broker safety policy validation.
- Duplicate-order protection and fail-closed submission boundaries.
- A reservation durably binds its original intent identity, symbol, typed
  direction, exact volume and expected price. Lifecycle outcome, fill and
  presence decisions reject a substituted intent before changing state,
  including after journal restoration and regardless of fill tolerances.
  Legacy journals retain their original bytes/checksums but have no intent
  binding; intent-scoped lifecycle decisions remain blocked for those records.
  This consistency fingerprint and journal checksum do not authenticate broker
  evidence or authorize execution. Low-level identity-only ledger transitions
  still require explicit, independently verified outcome/presence evidence.
- Shadow execution owns detached snapshots of submitted intents and matched
  reports. Mutating the caller's original intent, the submission returned by
  registration, or a later submission listing cannot rewrite the comparison
  used to clear a pending order or reopen the recovery gate. These in-memory
  snapshots remain offline consistency controls, not broker evidence.
- Every stored ledger key must equal its record's canonical order identity.
  Reads, reservations, transitions and journal/recovery snapshots reject a
  mismatched or aliased identity before it can hide a prior transport attempt.
  Identity checks inspect the whole ledger; ordinary input whitespace remains
  normalized at the external API boundary.
- Ledger reads and transitions also require a valid non-`NEW` submission state
  and a positive integer attempt count. Malformed states and zero, negative,
  boolean or fractional counters cannot authorize submission or produce a
  resolved restart snapshot.
- Persisted execution records represent prior reservations. `NEW` is invalid
  in a journal, restored ledger or restart snapshot, even with a matching
  checksum. A fresh identity starts `IN_FLIGHT`; an existing identity cannot
  become retryable by resetting its state to `NEW`.
- Every guarded intent submission requires a quote-freshness and deviation
  decision issued by the quote gate for that intent's exact symbol, side and
  expected price, plus
  an explicit idempotency ledger. A fabricated, missing, or mismatched quote
  and a missing ledger are rejected before transport. Legacy unscoped
  `execute()` calls are blocked, including with an otherwise allowed gate.
- Admission and quote approvals are bound to the exact in-process decision
  object and its original fields. Copying a rejection and changing `allowed`,
  or copying a fresh quote to change its intended price, fails before
  transport. This is an in-process consistency check, not independent broker
  verification or a live authorization credential.
- Issued quote times are detached UTC snapshots. A caller-owned mutable,
  missing or failing timezone offset cannot later make an expired quote appear
  current or escape the quote gate; invalid timing evidence fails closed.
- Caller-supplied positive operational/broker tuples remain diagnostic only.
  Guarded submission requires a policy-evaluated environment decision for
  the same symbol and volume as the intent, and rechecks quote age at the
  instant of submission. These supplied environment facts are still not
  independently observed broker state or live authority.
- Broker symbol policy accepts only an immutable `frozenset` of exact,
  trimmed strings. A raw string cannot turn substring membership into
  authorization for an unlisted symbol.
- Policy-evaluated environment decisions reject observations that are stale
  against evaluation wall time and expire no later than the policy's data-age
  limit. A later fresh quote cannot revive an expired environment approval.
  This bounds caller-supplied facts in time but does not observe a broker or
  replace a fresh adapter snapshot.
- Broker outcome decisions are schema-checked before mutating idempotency
  state; inconsistent retry flags fail closed.
- V5.3 promotion uses an explicit execution-safety evidence gate covering
  quote safety, idempotency, outcomes, reconciliation, recovery, journal
  integrity, and the live-disabled invariant; it grants no MT5 authority.
- V5.2→V5.3 promotion is blocked unless the validated research decision and
  the V5.3 safety decision both pass; a green CI run cannot bypass either.
- The mechanical release-tree audit now requires every V5.3 safety boundary
  and the V5.2→V5.3 promotion gate to exist in the candidate tree.
- A `KILLED` risk state cannot be reset without explicit boolean operator
  approval and a non-empty audit reason; reset is not a live-execution grant.

## V6.0 Release Boundary
- Final release evidence bundle.
- Security review and release-tree audit.
- Explicit live-authorization gate requiring every evidence item to be `True`.
- No live routing is implied by passing unit tests.
- Historical, WFO, robustness, shadow, recovery and broker validation require real evidence before live activation.

## Completion rule
A stage is considered implemented when its software boundary and automated tests exist. A stage is considered empirically validated only when its required real-world evidence is produced and reviewed. The repository must never convert missing evidence into a synthetic `passed=True` result.
