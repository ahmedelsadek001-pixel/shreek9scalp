# SHREEK V5.1

نظام تداول آلي موجه أساسًا لـ XAUUSD، مبني على تحليل متعدد الأطر الزمنية، ICT/Price Action، وإدارة مخاطر fail-closed.

## Architecture

`MARKET DATA → DATA INTEGRITY → ICT SIGNAL ENGINE → SETUP QUALITY → ADMISSION FIREWALL → RISK BUDGET → DAILY RISK STATE → PAPER/BACKTEST → SHADOW RECONCILIATION → RECOVERY → RELEASE GATE`

## Implemented

- Closed-bar, chronological market-data validation.
- HTF structure, liquidity, FVG, order-block and PD-array analysis.
- Deterministic M15/M5/M3 execution signals and execution levels.
- Setup-quality score with explicit admission threshold.
- High-impact news firewall with timezone-aware windows.
- Session/trading-window controls.
- Position lifecycle: TP1/TP2/TP3, breakeven and trailing behavior.
- Causal backtesting with next-bar entry and deterministic costs.
- Walk-forward parameter selection with out-of-sample evaluation.
- Monte Carlo robustness and drawdown/ruin gates.
- Daily realized-risk ledger and explicit risk state machine.
- Deterministic risk budget and stop-distance position sizing; no execution authority.
- Deterministic paper-trading engine; no broker routing.
- Shadow execution intents and fail-closed reconciliation.
- Disconnect/recovery state machine that blocks submission until pending shadow orders reconcile.
- Decision journal and automated tests.
- AI advisor is advisory-only; it cannot authorize, size, or execute trades.

## Safety boundary

Live MT5 execution remains disabled until CI, historical validation, walk-forward, Monte Carlo, paper trading, reconciliation, shadow validation, recovery validation, and final security review all pass. Passing tests do not establish profitability or broker compatibility.

## Development rule

`main` is kept stable while V5.1 is validated on `v5.1-development`. The goal is not maximum trade count; the goal is controlled execution with measurable edge and minimized risk of ruin.
