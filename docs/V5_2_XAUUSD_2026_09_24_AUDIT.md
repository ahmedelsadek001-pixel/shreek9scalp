# V5.2 XAUUSD input audit — 2026-09-24

Status: **FAIL / development diagnostic only**. This is not a research-release
artifact, evidence of an edge, broker-cost verification, or live MT5 authority.
The inputs were supplied as CSV exports; their original broker, license,
server-time policy and contract specification remain unverified. No CSV is
committed to this repository. Reproduce the structural gate with
`python -m research.xauusd_audit_cli --m5 FILE --m15 FILE --h1 FILE`.

## Input fingerprints and coverage

| Submitted file | SHA-256 | Bars | First → last (source offset) | Outcome |
| --- | --- | ---: | --- | --- |
| `XAUUSD_M5_raw(1).csv` | `95775b974f22a0ae0fcc4309fef142dd504e556a12f391ab2df594b3fdf44bec` | 100,000 | 2025-04-29 05:05 → 2026-09-24 10:00 (+03:00) | 513.205 days; fails 1,065-day minimum |
| `XAUUSD_M15_raw.csv` | `9f38aa866516c0026a89635a5c728dda922c209cff3aaaa63e766cabc729f2cf` | 100,000 | 2022-06-30 23:15 → 2026-09-24 09:15 (+03:00) | Passes individual checks |
| `a1474c58-6317-4909-b652-1b6bba66b383.csv` (H1) | `ba28cb99ef75c178ccdbcb204b26dfddee5a3023a7ec36492cf10b27559f8bc9` | 63,263 | 2016-01-04 01:00 → 2026-09-24 09:00 (+03:00) | Passes individual checks |
| `XAUUSD_M5_raw.csv` | `c83cf2ec6a9dbf5a64710a288fa7218272aded0534d849eb1faa58c903e2d712` | 5,568 | 2026-08-27 02:40 → 2026-09-24 09:25 (+03:00) | 28.28 days; not a substitute for historical M5 |
| `xauusd_5m_3years.csv` | `0c79ee4bb1e957b355254a10e4c4f98275c7988e23390a144ecdde92d3728ea9` | 50,000 | 2023-09-15 00:00 → 2024-03-06 14:35 (UTC) | 173.61 days; Saturday bars |
| `xauusd_15m_3years.csv` | `e7cf60687be59a6070f816e655d9cf506858f1f6412246c9096ec495c95a9bd5` | 50,000 | 2025-04-12 04:15 → 2026-09-15 00:00 (UTC) | 520.82 days; Saturday bars |
| `xauusd_1h_3years.csv` | `28f677a0cf91d68a8821b9b1217440eb57803ded689a04f97b51baa68a080e4a` | 26,320 | 2023-09-15 00:00 → 2026-09-15 15:00 (UTC) | Saturday bars; OHLC differs from raw source |

The three raw files match OHLC on all compared *complete* overlapping bars:
33,281/33,281 (M5→M15), 24,950/24,950 (M15→H1), and 8,261/8,261
(M5→H1). Each has over 92% UTC weekday-slot coverage, and none has UTC
Saturday bars or off-grid timestamps. This is strong internal consistency,
but **not** proof of independent or authentic broker provenance. The bundle
still fails because M5 is too short. The files named `3years` have no M5/M15
overlap, 7,200/7,183/3,768 Saturday bars (M5/M15/H1), 0% OHLC agreement
on the comparable M15/H1 and M5/H1 pairs, and a reused M5/M15 volume prefix.
They cannot be spliced into the raw bundle.

## Isolated development WFO diagnostic (not acceptance evidence)

The following run used only the 100,000-bar raw M5 file above; the failed
three-timeframe gate was not overridden for promotion. It is an illustrative
software diagnostic with **assumed**, unverified execution economics:

- Causal Breakout + Retest; `pip_size=0.10`, `volume=1`, `point_value=1`
  (unitless research P&L, **not USD or a broker lot**); spread=0.30 price
  units, per-side slippage=0.10, per-side commission=0.05 per volume unit.
- Two fixed candidate volume multipliers (1.5, 1.2), selected on training
  expectancy only; 20,000-bar train / 12-bar purge and declared label horizon
  / 10,000-bar OOS, 10,000-bar step, 7 non-overlapping OOS windows. No
  pre-OOS signals or future bars are counted in a window's execution.
- Starting equity=10,000 research units; 250 Monte Carlo resamples, seed=42;
  `slippage_multiplier=1.5` and `spread_multiplier=1.5` apply the existing
  **P&L stress proxy** (they do not reprice historical bid/ask fills). A
  95% trade-mean interval and 1,000 moving-block bootstrap resamples of
  length 2 use seed=42.

Observed OOS: 10 trades across 7 windows, only 2 positive windows (28.57%),
and 4 with no trade; aggregate net P&L +18.95 research units and mean +1.895.
The 95% confidence interval is [-3.181, 6.971], block-bootstrap lower mean
-2.799, and non-positive bootstrap mean rate 22.3%. Under stress, median
ending equity is 9,962.80, worst 9,894.01 (250 simulations). The standard
OOS gate fails on trade count and stability; the research certification also
fails on sample size, stability, both uncertainty bounds, bootstrap tail and
train/OOS degradation. Positive aggregate P&L is not a passing edge. The
final ~9,988 M5 bars are outside these WFO OOS windows and are not silently
represented as validation evidence.

Next required evidence: a same-source, timezone-aware M5 export reaching at
least 2023-10-25 through the present with no unexplained gaps, paired with
the M15/H1 files and a verifiable export/source manifest; actual broker
spread, contract value, commissions and slippage observations; then rerun
the predeclared WFO and cost scenarios and retain exact version-bound
artifacts. Keep PR #3 in Draft and live MT5 off until independent empirical,
paper/shadow and release gates all pass.
