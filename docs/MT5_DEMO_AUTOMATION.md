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
Each new reserved intent also records the explicit DEMO server UTC offset;
older ledger rows migrate with a zero offset and retain their original source.

On the Windows machine, download the latest `v5.1-development` snapshot.
Open the already selected DEMO terminal and configure the four private
`SHREEK_DEMO_TERMINAL_PATH`, `SHREEK_DEMO_LOGIN`, `SHREEK_DEMO_SERVER`, and
`SHREEK_DEMO_SYMBOL=XAUUSD.s` variables as in
[MT5_DEMO_CONNECTION.md](MT5_DEMO_CONNECTION.md). Never put the login or
password into the repository. Use a local ledger directory outside Git:

The default quote clock is UTC. For the observed JustMarkets DEMO feed that
reports tick timestamps three hours ahead of Windows UTC, set
`$env:SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS='10800'` in the same shell.
Only the exact values `0` and `10800` are accepted; verify the broker offset before each
session. The same explicit offset maps completed M5 candle timestamps to UTC
before the last-bar and signal checks. A missing or incorrect offset refuses
stale or future candles; it is never inferred from the tick. The five-second
quote freshness limit remains in force. Only the explicitly mapped +03:00
DEMO feed permits at most one second of future tick skew; UTC mode permits none.
The read-only readiness report shows `observed_filling_policy` and
`observed_tick_utc_offset_seconds` when a currently fresh tick supports one
of those offsets. These observations do not set the offset automatically or
enable order transport. A stale tick leaves the observed offset null.

```powershell
$ledgerDir = Join-Path $env:LOCALAPPDATA 'SHREEK'
New-Item -ItemType Directory -Force -Path $ledgerDir | Out-Null
$ledger = Join-Path $ledgerDir 'demo_orders.sqlite3'
py -m execution.mt5_demo_preflight_cli --ledger $ledger
py -m execution.mt5_demo_readiness_cli
py -m execution.mt5_demo_auto_cli --ledger $ledger
```

The preflight command combines identity, broker readiness, local ledger and
stop-file checks, and a disabled strategy scan in one redacted JSON report.
An existing scan journal is also checked read-only for database integrity and
required tables/columns; a corrupt journal blocks session readiness before
the strategy scan. A missing journal is allowed because the runner creates
it before polling. Preflight does not test writes; the runner independently
refuses polling if journal creation, migration or writes fail.
An existing order ledger is checked read-only for full SQLite integrity,
recognized submission states and the bound DEMO account fingerprint. A ledger
from another account blocks the session, even if its previous attempts were
acknowledged. Restore the matching DEMO binding and inspect broker history;
do not delete or overwrite the ledger to clear a blocker.
An existing `demo_orders.watch.lock` also blocks session readiness. The
opt-in runner creates this lock exclusively before opening MT5 and removes it
after the session end is recorded. A second local opt-in runner refuses to
start while the lock exists. A forced termination can leave the lock behind;
inspect the order ledger, session report and broker history, confirm no
runner is still active, then remove the stale lock manually before a new
preflight. Never remove the lock while a runner is active.
While holding its lock, the opt-in runner also checks the local order ledger,
stop file and scan journal read-only. Any unresolved submission or malformed
local evidence blocks MT5 access. This local check complements the operator's
full read-only broker preflight command above.
`ready_for_demo_attempt` covers the broker environment;
`ready_for_demo_session` also requires no stop file or unresolved ledger
submission. It is read-only even when DEMO execution opt-ins are present in
the shell. A preflight pass is still only a current observation.

The first command diagnoses DEMO permissions, USD account and symbol, FOK/IOC
0.01-lot contract, Bid-based bars, existing exposure, and quote freshness.
It prints no account number and never sends an order. A positive report is an
instantaneous environmental observation, not a signal, broker approval, or
permission to skip the independent order checks in the transport.

The last command is one read-only scan. A missing signal or stale weekend
quote returns a refused JSON response and sends no order. The scan names
missing, interrupted, or stale completed M5 candles without disclosing account
data. After the DEMO
terminal actually permits trading and the operator elects to collect
experimental DEMO fills, a bounded 60-minute watcher is explicitly enabled:

```powershell
$env:SHREEK_DEMO_AUTO_ACK = 'DEMO_ONLY_RESEARCH'
$env:SHREEK_DEMO_KILL_SWITCH = 'OFF'
py -m execution.mt5_demo_auto_cli --execute-demo-auto --watch-minutes 60 --ledger $ledger
```

The watcher polls every 30 seconds, scans completed candles, and stops after
at most one broker submission or 60 minutes. It retries only known passive
observations: unavailable bars, a stale or unfinished last bar, or no unique
current signal. A session gap, detected signal without submission, or any
other safety refusal ends the watch and records `safety_refusal`; correct the
underlying condition before a new preflight. A refused scan is not a trade.
For the current Breakout + Retest settings, the gap check covers the most
recent 39 completed M5 candles (about 3 hours and 15 minutes). This includes
the detector's volume, consolidation and maximum retest lookback. A market
reopen or missing broker bar inside that window stops the watch; do not
disable the continuity check to force a signal.
Failed MT5 shutdown overrides any pending scan outcome and stops the watch;
it never permits a broker submission from that scan.
Each poll is also committed to `demo_orders.scans.sqlite3` beside the order
ledger, including no-signal and rejected scans. The session journal contains
UTC timestamps, a local session ID and the redacted result; it contains no
login or password and is not independent broker-fill evidence. An unavailable
journal prevents polling. If a write fails after submission, the command
preserves the actual `sent` outcome and stops without retrying.
The journal also records the UTC session end and its reason, including Ctrl+C,
stop-file stops and attempted submissions. Ctrl+C during a broker call does not
claim that nothing was sent; inspect the order ledger and broker history before
retrying. A process forcibly killed or a failed final journal write can leave
the session without an end record.

Read the five most recent local sessions without MT5 or account variables:

```powershell
py -m execution.mt5_demo_session_report_cli --ledger $ledger
```

The report includes scan/signal counts, submission and acceptance observations,
the last scan result and the session end reason. Use `--limit 20` for more
sessions (maximum 100). It opens the journal read-only and does not create a
missing file. Older journals remain readable and gain end columns on the next
runner session. `end_recorded=false` means no end was recorded: a watcher may
still be running, the process may have been killed, or the session may predate
end tracking. It does not prove a crash. Submission counts are local
observations, not independently verified fills or profitability evidence.

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
advertised FOK/IOC filling, there is another account position, or the risk budget is exceeded,
it fails closed. The account's DEMO currency and the symbol profit currency
must both be USD.

To investigate scans with no confirmed signal, audit a local XAUUSD M5 CSV
without attaching MT5:

```powershell
py -m execution.mt5_demo_signal_audit_cli --csv .\XAUUSD_M5_raw.csv
```

The header must be `timestamp,open,high,low,close,volume`, with one closed
M5 candle per row and explicit timestamp offsets. The JSON records the source
SHA-256, the first and last UTC timestamps, and the counts of eligible 80-bar
windows and signals confirmed on their last bar. It shares the runner's
39-bar continuity gate, including the detector's full warm-up and retest
lookback. Older gaps outside that context are allowed. This offline audit
does not check current quote freshness, bind a broker account or submit an
order. Its counts do not establish broker fills or profitability. Do not
loosen the strategy thresholds to force a signal.

To observe broker deals after a DEMO attempt, run the read-only
`execution.mt5_demo_history_cli --ledger $ledger`. A broker acknowledgement
or an observed closed deal does not establish the strategy's profitability.
The history report checks opening deal timestamps against the local reservation
and reports the observed deal clock offset separately from the stored tick/bar
offset. An unbound clock or a future/chronologically inconsistent deal blocks
the report. This read-only check cannot authenticate a broker export by itself.
Opening deals must also agree between the order and position history queries:
a matching ticket with a different symbol, strategy identifier, timestamp,
volume, price or financial amount blocks the entire report. Consistent split
fills may be returned in a different order without blocking the report.
An exit deal must have the direction opposite to the bound opening. Same-side
or unsupported exit types, or missing/ambiguous direction constants, block
the report before closing volume or net amounts are calculated.
Repeated deal tickets in the bound position's reported deals block the entire
report before closing volume or net amounts are calculated, even when the
repeated rows differ. Distinct deal tickets may share one broker order; valid
split fills and partial closes remain observable. Deal ticket uniqueness is
defined in the [MetaQuotes deal properties](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties).
Failure to close the history inspection session overrides every result,
including earlier refusals or an empty ledger. The report returns
`verified_demo=false`, no attempts and `DEMO history shutdown failed` without
exposing terminal error details; investigate the session before retrying.
The separate research and paper-account evidence gates stay FAILED until
independent out-of-sample and broker export audits pass.

MetaQuotes references: [closed-bar indices](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py),
[DEMO account mode](https://www.mql5.com/en/docs/constants/environment_state/accountinformation),
[DEMO order result](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py).
