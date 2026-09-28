# V5.2 Dataset Evidence Export

Use the dataset-level exporter to archive one validated research run as a single
deterministic JSON record. It carries the input validation summary and dataset
provenance alongside WFO results, Monte Carlo evidence, the research gate, and
the exact gate policy.

```python
from research.dataset_runner import run_csv_research
from research.evidence_export import (
    fingerprint_dataset_evidence_export,
    serialize_dataset_evidence_export,
    verify_serialized_dataset_evidence_export,
)

run = run_csv_research(
    "xauusd_m5.csv",
    parameter_sets,
    evaluator,
    reference_csv_paths=("xauusd_m5_second_source.csv",),
    train_size=1200,
    test_size=240,
    purge_size=20,
    starting_equity=10_000.0,
)
record = serialize_dataset_evidence_export(run)
record_sha256 = fingerprint_dataset_evidence_export(run)
# Store record_sha256 separately from record, then verify after loading it.
is_valid = verify_serialized_dataset_evidence_export(record, record_sha256)
```

The serialized record includes the dataset hash, bar count and timestamp bounds,
validation counters, each WFO OOS window's trade P&L, Monte Carlo inputs and
summary, the OOS report, gate decision, and policy. Export rejects
validation/provenance mismatches and recomputes report and gate consistency
from the WFO and Monte Carlo inputs. A fixed Monte Carlo seed is required for
an auditable export; seedless experiments can still run but cannot be exported
as reproducible evidence.

When a same-symbol, same-timeframe reference feed is available, pass it through
`reference_csv_paths`. The runner compares exact UTC-aligned timestamps before
starting the evidence pipeline and stops on insufficient overlap or a price
difference above the default limits (median 0.5%, P95 1.0%, and at least
100 common timestamps). They also require the inferred modal bar intervals to
match, which blocks an M5-to-M15 comparison. These conservative alarms detect
source disagreement but do not prove either feed is correct. Each successful
comparison archives fingerprints for both bar series. Review broker, contract, and
timestamp conventions before relaxing them. Do not compare different
timeframes as if they were identical feeds.
For each aligned bar, the comparison uses the largest percentage difference
among open, high, low, and close; matching closes alone cannot hide different
wicks that would change a breakout or retest. Volume is broker-specific and
is excluded from the price comparison. The OHLC comparison scales finite inputs
before computing percentage differences, so numerical overflow cannot turn a
large disagreement into 0%. Each comparison records its method as
`max_ohlc_pct_per_aligned_bar_v1`. Dataset evidence exports use schema 10 and
the standalone audit uses schema 2; existing schema 9 exports must be regenerated
from the raw data before they can satisfy the stricter comparison policy.

Run the same check without starting WFO or writing to a dataset with:

```sh
python -m research.dataset_audit_cli \
  --primary XAUUSD_M15_raw.csv \
  --reference xauusd_15m_reference.csv \
  --min-history-days 1095
```

Repeat `--reference` for additional same-timeframe feeds. A minimum history
policy is required for `ready_for_research` to pass; without `--min-history-days`,
the CLI may report source comparisons but will fail closed on readiness. The command prints
JSON with each dataset's bar count, time bounds, fingerprint, and comparison
statistics. Exit `0` means all source checks passed, `1` means at least one
comparison failed, and `2` means an input file or CSV schema was invalid.
Use `--min-history-days 1095` when the primary series must cover at least three
years; the same minimum can be set in `run_csv_research` with
`minimum_history=timedelta(days=1095)`. The runner blocks before WFO if the
primary dataset is shorter, and the selected minimum is retained in the export.

For datasets that should not contain gaps over a known interval, use
`--max-gap-hours 2` in the audit CLI or pass `max_gap=timedelta(hours=2)` to
`run_csv_research`. This is opt-in because session closures and weekends create
legitimate gaps; choose a threshold appropriate for the instrument and timeframe.
The selected threshold and the largest observed adjacent-bar interval are retained
in schema version 10 evidence exports; the verifier rejects a threshold below that
observed interval.

Schema version 10 uses strict JSON and archives coverage policy plus successful cross-source
consistency checks with dataset evidence. An unbounded `max_worst_drawdown` policy is
encoded as `null`, since JSON has no standard numeric infinity value.

The verifier returns `False` for malformed, edited, schema-mismatched, or
internally inconsistent artifacts. Keep the expected SHA-256 separately from
the JSON file; a digest stored beside a modifiable artifact does not protect it.

The SHA-256 value identifies the serialized record; it is not a digital
signature, proof of external data origin, independent audit, or profitability
claim. A passing research gate does not authorize paper or live execution.
