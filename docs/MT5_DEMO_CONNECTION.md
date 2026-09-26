# MT5 DEMO connection: read-only preflight

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

Strategy-driven DEMO order submission and immutable matching of SHREEK signal IDs
to observed broker deals are still to be implemented and independently validated
before the [paper account evidence requirements](PAPER_ACCOUNT_EVIDENCE.md)
can pass. The production security gate blocks all broker send calls except
the exact reviewed DEMO-only sandbox module; live MT5 trading remains disabled.

## Isolated DEMO order sandbox

The optional `execution.mt5_demo_order_cli` sends **one manually specified**
0.01-lot DEMO market order only when `--execute-demo` and the separate local
`SHREEK_DEMO_TRADING_ACK=DEMO_ONLY` flag are present. This does not prove a
strategy signal and does not qualify as a paper-account strategy trade. Do not
use this command when the terminal reports `trade_allowed=false`; the broker
or operator must permit DEMO trading before a sandbox send can succeed.

The transport checks actual account mode, exact login/server, terminal and
account trading permissions, exact broker symbol, IOC filling, fresh quote,
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
other currencies are refused instead of being mislabeled USD. A manual
close is marked `manual_intervention=true`. `closed_observed` means the broker
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
