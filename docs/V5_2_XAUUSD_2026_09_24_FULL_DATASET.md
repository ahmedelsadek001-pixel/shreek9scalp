# V5.2 XAUUSD full-dataset validation — 2026-09-24

Status: **DATASET ACCEPTED / RESEARCH CERTIFICATION FAILED**.

This report supersedes the earlier short-M5 diagnostic. It does not claim
profitability, broker-executable performance, or live-trading readiness. The
CSV is retained outside Git because its provenance/licence is not independently
verified. The account identifier from the supplied metadata is intentionally
redacted and is not part of repository evidence.

## Source and structural acceptance

The supplied metadata identifies One World Markets, `OWMarkets-Server`,
XAUUSD, UTC+03:00, 2 digits, 0.01 point size, 100-ounce contract size, and
206,371 exported bars from 2023-10-25 01:05 to 2026-09-24 13:45. The exact CSV
bytes were hashed before parsing:

| Timeframe | File | SHA-256 | Bars | Span |
| --- | --- | --- | ---: | ---: |
| M5 | supplied `32928412-e740-4035-9546-085c1b894dfe.csv` | `572cb9bc78478c4fceacd448c4a4841fb7f3c6d4faa1b2716128e87aad96ce89` | 206,371 | 1,065.528 days |
| M15 | existing `XAUUSD_M15_raw.csv` | `9f38aa866516c0026a89635a5c728dda922c209cff3aaaa63e766cabc729f2cf` | 100,000 | 1,546.417 days |
| H1 | existing `a1474c58-6317-4909-b652-1b6bba66b383.csv` | `ba28cb99ef75c178ccdbcb204b26dfddee5a3023a7ec36492cf10b27559f8bc9` | 63,263 | 3,916.333 days |

The three-timeframe quality gate passed:

- M5/M15: 68,530 complete bars compared, 100.000% OHLC match, 1,065.340
  days overlap.
- M15/H1: 24,950 compared, 100.000% match, 1,546.406 days overlap.
- M5/H1: 16,826 compared, 100.000% match, 1,065.330 days overlap.
- Each series had zero duplicate/non-monotonic timestamps, zero unexpected
  interval counts, zero off-grid bars, zero UTC Saturday bars, and about
  92.45–92.66% weekday-slot coverage.

This is strong internal consistency. It is not independent proof that all
three exports came from the same broker feed or that historical bid/ask fills
are recoverable. The source manifest still needs broker export evidence,
licence/permission, and a reproducible server-time policy.

## Causal WFO and robustness run

The run used the existing causal Breakout + Retest research adapter:

- 40,000-bar train, 12-bar purge, 12-bar declared label horizon, 20,000-bar
  non-overlapping OOS test, 20,000-bar step; 8 chronological OOS windows.
- Two predeclared candidates: volume multiplier 1.5 and 1.2. Selection used
  train expectancy only. No live broker or MT5 call was made.
- Starting equity: 10,000 research units. The supplied economics were mapped
  explicitly: point value 100 (100 oz × $1 price move), spread 0.19 price
  units, slippage 0.015 price units (1.5 points), and $3.50 commission per
  execution so entry plus exit represents the supplied $7 round-turn per lot.
- Monte Carlo: 1,000 simulations, seed 42; stress multipliers 1.5 for both
  slippage and spread. Block bootstrap: 2,000 simulations, block size 2,
  seed 42. The stress model is a conservative P&L proxy, not reconstructed
  historical bid/ask data.

Observed OOS results:

| Measure | Result |
| --- | ---: |
| OOS trades | 176 |
| OOS net P&L | +9,057 research units |
| Mean trade expectancy | +51.460 research units |
| Positive OOS windows | 5 / 8 (62.5%) |
| 95% mean CI | -35.815 to +138.735 |
| Bootstrap lower mean | -36.786 |
| Bootstrap non-positive mean rate | 12.1% |
| Monte Carlo ruin rate under stress | 100.0% |
| Median stressed ending equity | -271.44 |
| Worst stressed ending equity | -1,881.64 |

The ordinary evidence gate failed on Monte Carlo ruin rate. Research
certification failed because the confidence interval and bootstrap lower bound
did not exclude non-positive expectancy, the bootstrap non-positive rate was
above its limit, and stressed ruin was 100%. The positive aggregate OOS result
therefore cannot be promoted as a robust edge.

## Required disposition

Keep PR #3 Draft and keep MT5 live execution disabled. The data-quality gate
may be marked structurally passed for this bundle, but V5.2 remains
**not certified** until the exact source manifest is independently verified,
cost/slippage observations are measured rather than assumed, and the strategy
survives a predeclared stress policy without total simulated ruin. CI success
remains software evidence only.

Broker reference for the contract/tick convention: [OW Markets commodities
specification](https://www.owmarkets.com/commodities). The supplied $7
commission and 1.5-point slippage remain user-provided assumptions, not claims
verified by that public page.

The repository now provides `research.xauusd_source_manifest.XAUUSDSourceManifest`
to validate this metadata and convert spread, slippage, contract value and
round-turn commission into the exact research-engine units. It rejects a CSV
whose timezone offset disagrees with the manifest. Account identifiers are not
accepted by this schema. Passing the manifest to `run_csv_research` also binds
the safe source fields into the immutable research artifact, so later evidence
cannot silently change broker-cost assumptions.
