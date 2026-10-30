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

## Final V6.0 acceptance target

V6.0 is considered software-complete only when all required modules, tests, CI,
security checks, documentation, and release gates are green. It is considered
trading-ready only after independent empirical evidence satisfies the release
policy; code quality alone cannot establish that condition.
