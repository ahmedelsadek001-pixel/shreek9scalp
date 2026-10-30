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

Library callers should pass the validated
`research.xauusd_source_manifest.XAUUSDSourceManifest` as
`source_manifest=` to `audit_xauusd_csv_bundle`. The audit then rejects every
CSV whose timestamp offset disagrees with the declared broker/server offset.

`research.xauusd_dataset_quality.require_xauusd_multitimeframe_quality` is the
fail-closed entry gate. A failed audit blocks empirical WFO and robustness
promotion. Rejected files may still be used as explicitly labelled synthetic
software fixtures, but their results are not evidence of profitability.

For a research run, use
`research.dataset_runner.run_audited_xauusd_breakout_retest_research` with the
three CSV paths and a source manifest. It rejects a failed default quality
audit before WFO, passes the exact hashed M5 bar snapshot to the manifest-bound
runner, and embeds the M5/M15/H1 source hashes in the research artifact.
Single-timeframe runners remain useful for diagnostics but do not enforce this
three-timeframe acceptance rule.

To evaluate a `ResearchReleasePackage` for V5.2 promotion, pass its
`source_paths` mapping with the same M5, M15, and H1 CSV files. Promotion
re-reads all three files under the default quality policy, compares their
SHA-256 hashes with the artifact metadata, and compares the independently
fingerprinted M5 bars with the artifact dataset. Missing, changed, invalid,
or insufficient files block promotion. The hashes and quality marker in
artifact metadata alone cannot authorize promotion. This local verification
does not establish external broker provenance, real fills, or profitability.

The gate performs no broker connection, order routing, or live authorization.

An explicit, reproducible read-only WFO run is available through
`python -m research.xauusd_study_cli --spec docs/xauusd_study_spec.example.json
--m5 /path/to/m5.csv --m15 /path/to/m15.csv --h1 /path/to/h1.csv
--output /path/to/new-result.json`. The example describes the earlier
diagnostic assumptions; its broker identity and costs remain unverified.
The command rejects a dirty Git tree, binds the artifact to HEAD and
the SHA-256 of the specification, checks the default three-timeframe audit,
and writes one complete JSON bundle without overwriting existing evidence.
An exit code of zero means a diagnostic bundle was written; inspect
`summary.certification.passed` and `summary.oos_gate.passed` for the actual
research decision. A diagnostic result never permits live trading.
