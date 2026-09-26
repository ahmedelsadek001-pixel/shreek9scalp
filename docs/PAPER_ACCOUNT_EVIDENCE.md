# V5.2/V5.3 DEMO account evidence

The historical XAUUSD CSV files are market data, and local `PaperTradingEngine`
fills are simulations. Neither is an observed DEMO broker fill. Previously
uploaded OW Markets/Myfxbook account statements identify the account as **REAL**;
they are excluded from paper account validation and must not be committed here.
The owner's later REAL account report is registered as private-source context
in [REAL_ACCOUNT_OBSERVATION_2026_09_26.md](REAL_ACCOUNT_OBSERVATION_2026_09_26.md);
ownership confirmation does not turn it into DEMO or strategy evidence.

`python -m research.audit_paper_account --manifest manifest.json --intents intents.csv --fills fills.csv`
is read-only. It requires two independent UTF-8 CSV exports, one for the SHREEK
order intents and one for observed DEMO broker executions. It checks complete
one-to-one matching, symbol, side, size, ordered timestamps, net P&L against
declared contract size and commission, sample coverage, entry slippage, delay,
and the raw export hashes. Defaults: at least 30 closed trades across 10 distinct
days, absolute entry slippage no more than 1.00 price unit and fill delay no more
than 30 seconds. The CLI exits nonzero if the export is incomplete or exceeds a
limit; it returns JSON without raw account identifiers.

The manifest is JSON with *exactly* the following string keys:

| Key | Value |
| --- | --- |
| `account_mode`, `source` | `DEMO`, `broker_export` (exact spelling) |
| `account_fingerprint` | lower-case SHA-256 of the privately held account ID |
| `symbol`, `currency` | exact broker symbol, e.g. `XAUUSD.s`; account currency must be `USD` |
| `strategy_id`, `strategy_version` | explicit identity of the running strategy |
| `contract_size` | positive decimal units per lot, e.g. `100` |
| `intents_sha256`, `fills_sha256` | lower-case SHA-256 hashes of the untouched CSV bytes |

`intents.csv` must have this exact ordered header:

```csv
intent_id,symbol,side,volume,requested_price,sent_at
```

`fills.csv` must have this exact ordered header:

```csv
intent_id,broker_order_id,symbol,side,volume,entry_price,exit_price,commission,net_pnl,filled_at,closed_at
```

Timestamps must be timezone-aware ISO 8601; `BUY`/`SELL` are the allowed sides.
One closed broker order per intent is required; partial fills must first be
normalized into full orders with verifiable original records. Commission is
nonnegative in the account currency and is subtracted from gross P&L. A maximum
absolute reconciliation difference of 0.01 account-currency units is allowed.
Non-USD account currency is refused; swap, financing, currency conversion, and deposits require a documented
reconciliation extension before such exports can qualify. Do not include
account numbers, names, credentials, or raw statements in Git.

A structurally reconciled report has `eligible_for_external_review=true`, but
`paper_trading_validated=false` always. SHA-256 catches accidental changes to
the pinned exports; the manifest itself and a self-declared `DEMO` label cannot
prove broker provenance or prevent fabricated records. Independent verification
of account type, broker origin, strategy attribution, costs, operating window,
and an operator's signed review remains required before any release evidence
can be marked true. Passing CI or the local audit is not trading profitability.
`build_paper_account_evidence` emits a negative V5.1 release evidence record
even when the CSV audit passes, so this local route cannot promote a phase.
Live MT5 order routing stays disabled.

The isolated DEMO-only order sandbox is a manual broker-transport check. Its
durable SQLite acknowledgements do not attribute orders to SHREEK strategy
signals, provide independent broker-exported closed fills, or change
`paper_trading_validated=false`.
The optional read-only DEMO history report cross-checks those acknowledgements
against MT5 deal and position tickets. It remains observational and does not
replace a retained independent broker export or audited strategy intents.
