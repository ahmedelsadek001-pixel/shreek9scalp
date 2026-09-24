# XAUUSD dataset acceptance

Historical data must pass the multi-timeframe quality gate before it can be
used as V5.2 WFO, robustness, or Monte Carlo evidence.

Required bundle:

- Explicitly timezone-aware 5m, 15m, and 1h OHLCV data.
- At least 1,065 days of coverage in every timeframe.
- No Saturday bars for UTC XAUUSD datasets.
- At least 90 days of overlap between each timeframe pair.
- At least 99% OHLC agreement when lower-timeframe bars are aggregated to the
  corresponding higher timeframe.
- No reused bar-by-bar volume template across separate timeframe datasets.

`research.xauusd_dataset_quality.require_xauusd_multitimeframe_quality` is the
fail-closed entry gate. A failed audit blocks empirical WFO and robustness
promotion. Rejected files may still be used as explicitly labelled synthetic
software fixtures, but their results are not evidence of profitability.

The gate performs no broker connection, order routing, or live authorization.
