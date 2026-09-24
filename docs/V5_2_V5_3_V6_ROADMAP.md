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
- Disconnect/recovery state machine.
- Execution-quality and slippage analytics.
- Broker safety policy validation.
- Duplicate-order protection and fail-closed submission boundaries.
- Strict broker-bound submission requires an explicit quote-freshness and
  deviation decision; missing quote evidence is rejected before transport.
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
