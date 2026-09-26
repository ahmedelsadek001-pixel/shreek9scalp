# Experimental DEMO-only automatic signal runner

**Research status: FAILED, not approved for live trading or profitability
claims.** This optional V5.2 experiment automatically tests the fixed
`breakout-retest-research-v1-pip0.1` detector on JustMarkets DEMO gold. It is
separate from the manual sandbox CLI and cannot turn on live MT5 routing.

The one-shot runner reads 80 M5 bars starting at MT5 index **1** (index 0 is
unfinished), checks the last 33 bars are consecutive, requires the most recent
completed candle to have closed no more than 120 seconds ago, and only accepts
exactly one signal confirmed on that last candle. It never replays a signal
from history. The broker symbol must explicitly report Bid-based chart bars;
an unknown or Last-based chart mode is refused. It checks that the fresh
broker Bid is within 0.10 price units
of the strategy candle close; BUY orders use the fresh Ask. The DEMO-only
transport binds this execution price and rechecks
the account mode/login/server, applies its 0.01-lot and risk/stop/spread gates,
and durably reserves the signal ID before the broker call. After one attempted
broker submission, the bounded watcher stops, including uncertain outcomes.
Repeated scans cannot re-submit the same signal ID.
The local SQLite ledger labels these attempts `strategy_experiment`; manually
entered sandbox attempts are `manual_sandbox`, and migrated older rows remain
`legacy_unattributed`. These local labels help separate observations but are
not broker authentication or independent proof of strategy performance.

On the Windows machine, download the latest `v5.1-development` snapshot.
Open the already selected DEMO terminal and configure the four private
`SHREEK_DEMO_TERMINAL_PATH`, `SHREEK_DEMO_LOGIN`, `SHREEK_DEMO_SERVER`, and
`SHREEK_DEMO_SYMBOL=XAUUSD.s` variables as in
[MT5_DEMO_CONNECTION.md](MT5_DEMO_CONNECTION.md). Never put the login or
password into the repository. Use a local ledger directory outside Git:

```powershell
$ledgerDir = Join-Path $env:LOCALAPPDATA 'SHREEK'
New-Item -ItemType Directory -Force -Path $ledgerDir | Out-Null
$ledger = Join-Path $ledgerDir 'demo_orders.sqlite3'
py -m execution.mt5_demo_readiness_cli
py -m execution.mt5_demo_auto_cli --ledger $ledger
```

The first command diagnoses DEMO permissions, USD account and symbol, IOC
0.01-lot contract, Bid-based bars, existing exposure, and quote freshness.
It prints no account number and never sends an order. A positive report is an
instantaneous environmental observation, not a signal, broker approval, or
permission to skip the independent order checks in the transport.

The last command is one read-only scan. A missing signal or stale weekend
quote returns a refused JSON response and sends no order. After the DEMO
terminal actually permits trading and the operator elects to collect
experimental DEMO fills, a bounded 60-minute watcher is explicitly enabled:

```powershell
$env:SHREEK_DEMO_AUTO_ACK = 'DEMO_ONLY_RESEARCH'
$env:SHREEK_DEMO_KILL_SWITCH = 'OFF'
py -m execution.mt5_demo_auto_cli --execute-demo-auto --watch-minutes 60 --ledger $ledger
```

The watcher polls every 30 seconds, scans completed candles, and stops after
at most one broker submission or 60 minutes. A refused scan is not a trade.
Press Ctrl+C to stop the watcher. A file called `demo_orders.stop` next to the
SQLite ledger stops future scans and blocks submission at the runner boundary:

```powershell
New-Item -ItemType File -Force -Path (Join-Path $ledgerDir 'demo_orders.stop')
```

The external environment variables of an already running PowerShell child
cannot be changed by setting them in another window; use Ctrl+C or the stop
file. Removing that file requires the operator to check account identity and
settings again. The watcher never logs in, creates passwords, opens REAL
positions, or authorizes other strategies. If terminal trading is disabled,
the account changes, the market is closed, quotes are stale, the broker rejects
IOC filling, there is another account position, or the risk budget is exceeded,
it fails closed. The account's DEMO currency and the symbol profit currency
must both be USD.

To observe broker deals after a DEMO attempt, run the read-only
`execution.mt5_demo_history_cli --ledger $ledger`. A broker acknowledgement
or an observed closed deal does not establish the strategy's profitability.
The separate research and paper-account evidence gates stay FAILED until
independent out-of-sample and broker export audits pass.

MetaQuotes references: [closed-bar indices](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py),
[DEMO account mode](https://www.mql5.com/en/docs/constants/environment_state/accountinformation),
[DEMO order result](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py).
