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
python -m execution.mt5_demo_probe_cli
```

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

Broker DEMO order submission and immutable matching of SHREEK signal IDs to
observed broker deals are still to be implemented and independently validated
before the [paper account evidence requirements](PAPER_ACCOUNT_EVIDENCE.md)
can pass. This repository's production security gate continues to block
direct broker order submission; live MT5 trading remains disabled.

Broker references: [Python account_info](https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py),
[account trade modes](https://www.mql5.com/en/docs/constants/environment_state/accountinformation),
and [Python initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py).
