# XAUUSD dataset acceptance

Historical data must pass the multi-timeframe quality gate before it can be
used as V5.2 WFO, robustness, or Monte Carlo evidence.

Required bundle:

- Explicitly timezone-aware 5m, 15m, and 1h OHLCV data.
- At least 1,065 days of coverage in every timeframe.
- At least 80% of the expected UTC Monday–Friday slots in each timeframe;
  a first/last timestamp spanning three years with most bars missing fails.
- No Saturday bars when timestamps are converted to UTC, regardless of the
  timestamp offset recorded by the source.
- Each timestamp must lie on its timeframe's UTC clock grid (5m/15m/1h).
- At least 90 days of overlap between each timeframe pair.
- At least 99% OHLC agreement when lower-timeframe bars are aggregated to the
  corresponding higher timeframe.
- No reused bar-by-bar volume template across separate timeframe datasets.

Run the read-only audit on an explicit three-file bundle (JSON on stdout,
exit code 0 on pass, 2 on a failed audit or malformed input):

```sh
python -m research.xauusd_audit_cli --m5 /path/to/m5.csv \
  --m15 /path/to/m15.csv --h1 /path/to/h1.csv
```

The JSON includes each file's SHA-256 over the exact parsed bytes, observed
timestamp bounds, bar counts, weekday coverage, aligned OHLC comparisons and
all failed checks. Keep the JSON together with a source/broker export manifest
(symbol, server offset and timezone policy, account/contract specifications,
spread and commission observations, export date, and license/permission) for
external verification. Passing OHLC checks cannot prove genuine provenance or
broker-accurate fills. The generic single-timeframe research runner is not a
substitute for this three-timeframe acceptance gate.

`research.xauusd_dataset_quality.require_xauusd_multitimeframe_quality` is the
fail-closed entry gate. A failed audit blocks empirical WFO and robustness
promotion. Rejected files may still be used as explicitly labelled synthetic
software fixtures, but their results are not evidence of profitability.

The gate performs no broker connection, order routing, or live authorization.
