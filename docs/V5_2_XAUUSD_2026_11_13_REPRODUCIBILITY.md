# V5.2 XAUUSD reproducibility rerun — 2026-11-13

Status: **DATASET QUALITY PASSED / OOS GATE PASSED / RESEARCH CERTIFICATION FAILED**.

This is a deterministic rerun of the predeclared 0.03-lot Breakout + Retest study
using the latest PR #18 merge-candidate source tree. It is not a new parameter
search, a profitability claim, a broker-executable replay, or release authority.

## Reproducibility identity

- Repository: `ahmedelsadek001-pixel/shreek9scalp`
- CI merge-checkout commit: `c6ec6969ce23904f6f87ddc83f0de9dd62a9753d`
- PR branch head at run time: `0f5ef8c2e90dbbe873938fc83e332afd41caace9`
- Study spec SHA-256: `e6984ea532c3fb4f9e0e3e423cd516495be547b98b96213c7d8fa73eb71cd0c6`
- Research artifact SHA-256: `6094ce0a3fac24731a5e8a4347c8494a90f7cc3fdce84366fa8defb535c5fdc4`
- The exact Git commit object and complete source tree were reconstructed and
  verified locally; the checkout was clean before the CLI run.
- The full specification is stored in
  `docs/xauusd_study_spec_2026_11_13_003lot.json`.

## Source dataset identity

| Timeframe | Source file | Bars | Bytes | SHA-256 |
|---|---|---:|---:|---|
| M5 | `32928412-e740-4035-9546-085c1b894dfe.csv` | 206,371 | 13,026,456 | `572cb9bc78478c4fceacd448c4a4841fb7f3c6d4faa1b2716128e87aad96ce89` |
| M15 | `XAUUSD_M15_raw.csv` | 100,000 | 6,375,831 | `9f38aa866516c0026a89635a5c728dda922c209cff3aaaa63e766cabc729f2cf` |
| H1 | `a1474c58-6317-4909-b652-1b6bba66b383.csv` | 63,263 | 4,054,053 | `ba28cb99ef75c178ccdbcb204b26dfddee5a3023a7ec36492cf10b27559f8bc9` |

The aggregate research dataset identity is
`50eeec8814b323096ba907d46b55ab75ce3997af343712b83b39f3229182ff9e`.
The prior three-timeframe audit reported 100% OHLC aggregation matches over
the overlapping windows and no grid, duplicate or ordering findings. This is
internal consistency, not independent broker-feed provenance.

## Study controls

- Volume: 0.03 lots; starting research equity: 10,000 units.
- WFO: 40,000 train bars, 12-bar purge, 20,000 OOS bars, 20,000 step,
  8 chronological windows.
- Two predeclared candidates; train expectancy selects parameters.
- Monte Carlo: 1,000 simulations, seed 42.
- Block bootstrap: 2,000 simulations, block size 2, 95% confidence.
- Cost assumptions: 19 spread points, 1.5 slippage points, $7 round-turn
  commission per lot. Monte Carlo stress multiplies spread and slippage by 1.5.
- Costs are assumptions, not independently measured broker observations.
  Stress is a P&L proxy, not historical bid/ask execution replay.

## Results

| Measure | Result |
|---|---:|
| OOS trades | 176 |
| OOS net P&L | +307.89 research units |
| OOS expectancy | +1.749375 per trade |
| Positive OOS windows | 5 / 8 (62.5%) |
| 95% expectancy CI | -0.879466 to +4.378216 |
| Bootstrap lower mean | -0.857084 |
| Bootstrap non-positive mean rate | 8.7% |
| Monte Carlo ruin rate | 0.0% |
| Median ending equity | 8,325.87 |
| Worst ending equity | 7,842.01 |
| Median maximum drawdown | 1,685.45 |
| Worst maximum drawdown | 2,169.02 |

The basic OOS gate passed its minimum trade count, positive expectancy and
window-stability checks. Statistical certification still failed three
independent requirements:

1. The 95% confidence interval includes non-positive expectancy.
2. The block-bootstrap lower bound is negative.
3. The bootstrap non-positive expectancy rate (8.7%) exceeds the 5% maximum.

Zero Monte Carlo ruin at this volume does not cure weak statistical evidence.
The model also does not reconstruct historical bid/ask paths.

## Stress-model interpretation requiring follow-up

The existing Monte Carlo helper does not multiply spread and slippage costs
inside each trade. It applies an asymmetric outcome shock to already-net P&L:
positive outcomes are divided by the product of the two multipliers, while
negative outcomes are multiplied by that product. At 1.5x / 1.5x this means
winners are scaled to 44.44% and losses to 225% of their original net values.
This is a deliberately severe P&L shock, not a literal execution-cost replay.

For this fixed 0.03-lot manifest, the backtest's average cost decomposition
is recoverable from the configured economics: spread 0.57, slippage 0.09 and
round-turn commission 0.21 per trade (total 0.87). A separate offline
diagnostic that retains each gross trade outcome and applies 1.5x to spread
and slippage costs while leaving commission unchanged produced:

| Additive cost-only diagnostic | Result |
|---|---:|
| Mean stressed trade P&L | +1.419375 |
| Total stressed OOS P&L | +249.81 |
| Median ending equity | 10,232.11 |
| Worst ending equity | 9,640.45 |
| 5th percentile ending equity | 9,864.22 |
| Median maximum drawdown | 162.98 |
| Worst maximum drawdown | 514.92 |
| Ruin rate | 0.0% |

This diagnostic is **not** part of the official evidence pipeline, is not a
replacement for the existing conservative P&L shock, and must not be used for
promotion. It demonstrates that the two stress concepts are materially
different and should be reported separately after a tested implementation
that preserves gross P&L, spread cost, slippage cost and commission per trade.
Until then, retain the legacy shock and all certification failures.

## Tested execution-cost component primitive

The repository now contains `core.execution_cost_stress.stress_execution_costs`.
It accepts four explicit, same-length per-trade sequences: gross P&L, spread
cost, slippage cost and commission. It scales spread and slippage independently
and leaves commission unchanged. Its tests cover cost arithmetic, baseline
identity, cardinality mismatch, negative/non-finite costs, invalid multipliers,
boolean inputs and aggregate overflow.

This is a tested calculation primitive only. It is **not yet wired into
BacktestTrade generation, WFO robustness evidence or the certification gate**.
The existing official Monte Carlo shock remains unchanged and remains the
conservative certification input. No promotion decision may use this helper
until the backtest engine emits independently auditable cost components and
the full evidence chain is updated and tested.

## Disposition

- Keep V5.2 **not certified**.
- Do not relax the confidence, bootstrap or ruin thresholds to obtain a pass.
- Do not infer that 0.03 lots is safe on a live account from this research-unit
  simulation.
- Obtain independently verified broker export/licence and measured spread,
  slippage and commission observations; then improve the strategy's OOS edge
  under a predeclared methodology and repeat on untouched data.
- DEMO broker reconciliation, sustained paper/shadow, recovery, evidence
  authenticity and human release approval remain separate gates.
- No MT5 terminal, DEMO order or live order was used.
