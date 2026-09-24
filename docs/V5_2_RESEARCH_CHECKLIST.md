# SHREEK V5.2 Research Checklist

V5.2 is the evidence-generation phase. Passing software tests does not mean the trading edge has been proven.

The short-M5 diagnostic in [the earlier audit](V5_2_XAUUSD_2026_09_24_AUDIT.md)
is superseded by the full-M5 run in
[V5_2_XAUUSD_2026_09_24_FULL_DATASET.md](V5_2_XAUUSD_2026_09_24_FULL_DATASET.md).
The full bundle passes structural data quality, but its causal WFO and
robustness evidence still fail research certification: the stressed Monte
Carlo ruin rate is 100%, and uncertainty bounds do not exclude a non-positive
expectancy. No empirical release item below is therefore cleared.

## Software gates

- [x] MAE/MFE measurement is deterministic and direction-aware.
- [x] MAE/MFE summary statistics include median and P90 excursions.
- [x] Strategy attribution is deterministic by setup tag.
- [x] Market regime classification is deterministic and execution-free.
- [x] Regime attribution is deterministic and aligned with trade outcomes.
- [x] Setup × regime edge matrix is available with a sample floor.
- [x] Edge selection rejects sparse observations.
- [x] Risk-adjusted selection ranking is research-only.
- [x] Advanced WFO stability measures OOS positivity and parameter churn.
- [x] Performance metrics include expectancy, profit factor, payoff and SQN.
- [x] Research evidence records are hashed and reproducible.
- [x] Reproducible artifacts bind dataset provenance, WFO configuration, and explicit strategy identity/version.
- [x] V5.2 release gate fails closed when provenance, reproducible artifact, or strategy-version binding is missing.
- [x] V5.2 research release gate fails closed on missing evidence.
- [x] Promotion re-derives WFO/statistical pass evidence from the exact strategy-bound artifact; manual flags cannot substitute for it.
- [x] Validation provenance binds label horizon and rejects purge windows smaller than the declared horizon.

## Empirical evidence required

The following must be generated from real historical/paper datasets and retained as evidence:

1. Sufficient sample coverage across intended symbols, sessions and setup types.
2. Out-of-sample WFO results with stable performance across windows.
3. Setup × regime edge matrix using the predefined sample floor.
4. MAE/MFE distributions and stop-efficiency analysis.
5. Robustness results including adverse sequencing and cost stress.
6. Execution-quality observations from paper/shadow operation.
7. A reproducible evidence record bound to dataset and an explicit strategy ID/version; phase labels or branch names are not substitutes for strategy identity.
8. Timestamped WFO windows and the exact candidate/selected parameter sets retained in the artifact.
9. The declared label horizon covered by the purge/embargo used for the retained WFO evidence.

## Promotion rule

V5.2 is not promoted to V5.3 based on a single favorable backtest. Promotion requires the complete evidence bundle and an explicit research release decision. The promotion decision must be evaluated against the exact research artifact and its expected strategy ID/version; manually asserted evidence flags alone are not sufficient promotion evidence.
