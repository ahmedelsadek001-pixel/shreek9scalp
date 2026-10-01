# MT5 DEMO connection: read-only preflight

## Windows connection launcher

On the Windows PC containing the already logged-in DEMO terminal, download
the latest `v5.1-development` source and extract it. Open PowerShell in that
folder. The launcher keeps the result visible and waits for a key after it
finishes; set `SHREEK_NO_PAUSE=1` only for an unattended caller. First run the
read-only setup diagnosis:

```powershell
.\connect_mt5_demo.cmd --doctor
```

It never prompts for a login, creates a runtime, installs a package or
contacts the terminal. `ready_to_prepare=true` means only that Windows,
Python and a conservative local disk reserve passed. It does not mean MT5 is
connected or that a trade can be sent. A fresh runtime needs at least 300 MiB
free on the drive containing `%LOCALAPPDATA%`; an existing runtime needs at
least 64 MiB. `INSUFFICIENT_LOCALAPPDATA_SPACE` identifies that drive as the
blocker. Free space there and run the diagnosis again; do not delete the
existing `%LOCALAPPDATA%\SHREEK` order ledger or scan journal.
If a runtime with MetaTrader5 is already installed, `--report-demo` can read
existing sessions and broker history while this reserve is unavailable. It
does not install packages or authorize a new session. The report can still
fail if Windows or MT5 cannot read the local records; inspect that failure
without retrying an uncertain order.

When the diagnosis passes, run:

```powershell
.\connect_mt5_demo.cmd
```

Python 3.9 or newer and the Windows `py` launcher must already be installed.
The command prepares a local Python environment under `%LOCALAPPDATA%\SHREEK`,
installs the native MetaTrader5 package if it is missing, and prompts for the exact terminal
path, hidden expected login, server, symbol and verified UTC offset.
Existing `SHREEK_DEMO_*` binding variables are accepted instead of prompts.
Inputs stay in the child process; no password is requested or saved.
The bootstrap prints fixed reason codes on setup failure, without paths,
account numbers or broker credentials. `MT5_PACKAGE_INSTALL_FAILED` and
`MT5_PACKAGE_IMPORT_FAILED` block the connection and watcher; resolve the
local Python package installation before attempting a session.
The default mode prints the redacted, read-only preflight JSON and sends no order.
Check `connected_demo` separately from `ready_for_demo_session`: attachment
can succeed while permissions, exposure, local evidence or quotes block trading.

For the previously authorized experimental DEMO watcher, run:

```powershell
.\connect_mt5_demo.cmd --watch-demo
```

This mode starts the existing bounded watcher only after successful preflight.
It stops after one submission attempt or 60 minutes and needs a valid current
strategy signal. It cannot guarantee a trade. Both modes use the same local
ledger and lock. This connects the project to the terminal on your Windows PC;
it does not create remote access from ChatGPT or convert the Linux workspace
into Windows. A remote connection requires a separately configured reachable
Windows endpoint and an authorized access method.

## Manual environment binding

After a session, collect both read-only reports with
`.\connect_mt5_demo.cmd --report-demo`. This mode cannot be combined with
`--watch-demo` and does not require a new trading-readiness pass.
If MT5 or its Python package is unavailable, run
`.\connect_mt5_demo.cmd --report-local` in PowerShell to read only the
existing local session journal. It requires no login, package install,
runtime, free-space reserve or broker connection; it never verifies a broker
fill. A missing or malformed journal returns `journal_readable=false` and
does not create a replacement. Preserve the original ledger and journal.
See [the 1 October DEMO handover](DEMO_DELIVERY_2026_10_01.md) for the delivery
sequence and acceptance evidence.

SHREEK's current MT5 boundary can check a local, already logged-in DEMO
terminal without passwords or trading authority. It requires an explicit
terminal path, expected login and exact server name. These values live only
in the operator's local environment; do not put them in Git, screenshots,
issue comments, or chat. The probe compares the **actual MT5 trade mode** to
`ACCOUNT_TRADE_MODE_DEMO`; a server name containing “demo” is insufficient.

On the Windows PC with the dedicated MT5 DEMO terminal and the MetaTrader5
Python package installed, set `SHREEK_DEMO_TERMINAL_PATH`, `SHREEK_DEMO_LOGIN`
and `SHREEK_DEMO_SERVER` privately, then run:

```powershell
$env:SHREEK_DEMO_TERMINAL_PATH = Read-Host 'Path to DEMO terminal64.exe'
$env:SHREEK_DEMO_LOGIN = Read-Host 'DEMO account login number'
$env:SHREEK_DEMO_SERVER = Read-Host 'Exact DEMO server name'
$env:SHREEK_DEMO_SYMBOL = 'XAUUSD.s' # use the exact symbol from the DEMO terminal
python -m execution.mt5_demo_probe_cli
```

The symbol defaults to `XAUUSD` if `SHREEK_DEMO_SYMBOL` is unset. Brokers may
use suffixes such as `XAUUSD.s`; use the exact DEMO symbol. A missing symbol
rejects the probe. The CLI never guesses a replacement instrument.

First open that dedicated terminal and log into the DEMO account there.
Do not supply the broker password to SHREEK or paste any of these values into
a repository. The environment values above last only for this PowerShell
session. No such Windows terminal exists in Linux CI, so CI checks the probe
against fake MT5 sessions and expects the actual local probe to stay blocked.

The JSON output contains only the verified DEMO status, XAUUSD contract size
and lot limits, and whether the terminal reports trading enabled. A missing
runtime, disconnected terminal, wrong login/server, REAL or CONTEST account,
changed identity, or missing symbol details exits with status 2. The module
closes the terminal connection after every inspection. It never logs in, sends
orders, opens/closes positions, or makes `paper_trading_validated` true.

The experimental strategy runner now reserves each signal ID in the local
ledger and can match acknowledged DEMO attempts to observed broker deals.
An independent broker export and sustained paper run are still required before
the [paper account evidence requirements](PAPER_ACCOUNT_EVIDENCE.md)
can pass. The production security gate blocks all broker send calls except
the exact reviewed DEMO-only sandbox module; live MT5 trading remains disabled.

## Isolated DEMO order sandbox

The optional `execution.mt5_demo_order_cli` sends **one manually specified**
0.01-lot DEMO market order only when `--execute-demo` and the separate local
`SHREEK_DEMO_TRADING_ACK=DEMO_ONLY` flag and
`SHREEK_DEMO_KILL_SWITCH=OFF` are present. The manual command holds the same
exclusive session lock as the automatic runner and checks the local stop
file, unresolved ledger submissions, and scan journal before loading MT5.
Both commands must use the same ledger path for this shared exclusion.
A lock cleanup error preserves the broker outcome and requires inspection;
do not retry an already sent order. This does not prove a
strategy signal and does not qualify as a paper-account strategy trade. Do not
use this command when the terminal reports `trade_allowed=false`; the broker
or operator must permit DEMO trading before a sandbox send can succeed.

The transport checks actual account mode, exact login/server, terminal and
account trading permissions, exact broker symbol, advertised FOK or IOC filling, fresh quote,
spread at most 0.50 in price units, no existing account positions or pending
orders, a stop and target on the correct sides, and a maximum stop loss of
0.5% of DEMO equity. It supports USD account and USD symbol profit currency
only. The protective stop and target are submitted in the same request.
The broker pre-check is followed by another account/quote check. The
submission reserves a unique ID in a durable local SQLite file *before*
calling the broker. Uncertain results remain locked against new attempts;
inspect broker history and reconcile them manually. The command never retries.
No account number, password, or statement is printed or committed to Git.

When the DEMO terminal permits trading and an independently reviewed DEMO
test order is chosen, the operator sets the local opt-in and enters the
appropriate protective prices as local inputs:

```powershell
$env:SHREEK_DEMO_TRADING_ACK = 'DEMO_ONLY'
$env:SHREEK_DEMO_KILL_SWITCH = 'OFF'
$ledgerDir = Join-Path $env:LOCALAPPDATA 'SHREEK'
New-Item -ItemType Directory -Force -Path $ledgerDir | Out-Null
$stop = Read-Host 'Protective stop price (DEMO)'
$target = Read-Host 'Target price (DEMO)'
$intent = [guid]::NewGuid().ToString('N')
py -m execution.mt5_demo_order_cli --execute-demo --intent-id $intent --side BUY --stop-loss $stop --take-profit $target --ledger (Join-Path $ledgerDir 'demo_orders.sqlite3')
```

The CLI also accepts `--side SELL` with the stop above the current bid and
target below it. A broker acknowledgement must still be reconciled against
an independent DEMO broker history export. Live-account order routing is
never authorized by this CLI, and V5.2/V5.3 certification remains blocked.

After a sandbox order, observe the actual DEMO broker deal history in the
same bound terminal, using the durable ledger created above:

```powershell
py -m execution.mt5_demo_history_cli --ledger (Join-Path $ledgerDir 'demo_orders.sqlite3')
```

The read-only report includes the matched opening order, position deals,
broker prices, volumes, and broker profit/commission/swap/fee fields. For a
fully closed position it also reports `realized_net_usd`, the sum of those four
broker deal fields. Both the account and symbol profit currency must be USD;
other currencies are refused instead of being mislabeled USD.
The ledger stores the explicit tick/bar clock offset for each new intent. The
history report separately verifies whether opening deals use UTC or that
recorded DEMO offset by comparing them with the local reservation time. It
reports the observed deal offset and rejects unbound or future deal timestamps;
this local check does not replace an independent broker export.

An order filled across multiple broker deals is reconciled only when their
volumes sum to the reserved DEMO volume, all opening deals share the same
position, and no unrelated opening deal appears in that position history.
A manual close is marked `manual_intervention=true`. `closed_observed` means the broker
history has a matching opening deal and fully offsetting exit volume; it does
not assert strategy authorship or profitability. A history read error, REAL
account, missing DEMO identity, unresolved `UNKNOWN` submission, missing opening
deal, or account switch causes the entire read to fail closed. An uncertain
submission needs independent broker reconciliation; never delete the ledger
or resubmit its intent. Store broker exports and local SQLite records
privately outside the repository; account IDs and passwords never belong in
Git or the chat.

The optional bounded automatic research runner is documented separately in
[MT5_DEMO_AUTOMATION.md](MT5_DEMO_AUTOMATION.md). It remains DEMO-only and
cannot promote failed strategy research to an approved live strategy.

Broker references: [Python account_info](https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py),
[account trade modes](https://www.mql5.com/en/docs/constants/environment_state/accountinformation),
and [Python initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py).

Quote readiness samples current UTC after the broker tick is received, so
terminal initialization latency is not mistaken for a future quote. Explicit
injected test clocks remain fixed. Supported broker offsets and freshness,
spread, permission and account checks are unchanged; this read-only correction
does not grant execution authority or explain prior disconnects by itself.
