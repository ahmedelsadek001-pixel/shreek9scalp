# SHREEK V5.2 → V6.0 Completion Matrix

This matrix tracks implementation separately from empirical readiness. A software
component can be implemented while its evidence gate remains open.

| Area | Implementation | Evidence required before release |
| --- | --- | --- |
| MAE/MFE | Implemented | Historical dataset results |
| Strategy attribution | Implemented | Sufficient tagged trade sample |
| Regime classification | Implemented | Out-of-sample stability |
| Regime attribution | Implemented | Out-of-sample results |
| Edge matrix | Implemented | Minimum-sample and OOS validation |
| Advanced WFO | Implemented | Multiple chronological OOS windows |
| Monte Carlo / robustness | Implemented | Actual trade-PnL distributions |
| Paper trading | Implemented | Sustained clean paper run |
| Shadow reconciliation | Implemented | Reconciliation evidence |
| Recovery | Implemented | Disconnect/recovery replay evidence |
| Execution quality | Implemented | Realistic fill/slippage samples |
| Security gate | Implemented | Final source/security review |
| Live authorization | Gated | All mandatory evidence + explicit operator approval |

## Release rules

1. Never interpret implementation as proof of profitability.
2. Never promote from development to `main` while a mandatory gate is failing.
3. Never enable broker order routing merely because CI is green.
4. Treat missing, stale, malformed, or conflicting evidence as a failed gate.
5. Preserve chronological separation between training, validation, and test data.
6. Keep research analytics free of broker transport and execution authority.
7. Accept reconciliation evidence only from the reconciler that issued it and
   only when its intent fingerprint exists in the validated ledger. Fabricated,
   copied, edited, or differently bound matches fail closed. This in-process
   correlation check does not authenticate broker evidence.
8. Accept a positive execution-quality decision only from the quality gate and
   only when its intent and execution-report fingerprints match reconciliation.
   Reused or fabricated approvals fail closed; the binding does not prove that
   caller-supplied spread or latency observations came from a broker.

## Final V6.0 acceptance target

V6.0 is considered software-complete only when all required modules, tests, CI,
security checks, documentation, and release gates are green. It is considered
trading-ready only after independent empirical evidence satisfies the release
policy; code quality alone cannot establish that condition.
