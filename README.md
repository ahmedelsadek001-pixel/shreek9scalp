# SHREEK V5.1 → V6.0

نظام تداول آلي موجه أساسًا لـ XAUUSD، مبني على تحليل متعدد الأطر الزمنية، ICT/Price Action، وإدارة مخاطر fail-closed.

## Architecture

`MARKET DATA → DATA INTEGRITY → ICT SIGNAL ENGINE → SETUP QUALITY → ADMISSION FIREWALL → RISK BUDGET → DAILY RISK STATE → PAPER/BACKTEST → SHADOW RECONCILIATION → RECOVERY → RESEARCH ATTRIBUTION → EXECUTION QUALITY → BROKER SAFETY → RELEASE GATE`

## Implemented

### V5.1 Hardening
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
- Duplicate-signal protection, release evidence and security gates.

### V5.2 Research
- MAE/MFE excursion analytics.
- Strategy/setup attribution.
- Deterministic TREND/RANGE/UNKNOWN regime classifier.
- Regime attribution.
- Setup × regime Edge Matrix with sparse-cell filtering.
- Advanced walk-forward stability analytics and parameter-churn measurement.

### V5.3 Execution Safety
- Execution-quality analytics for slippage and spread.
- Broker environment safety policy covering connection, symbol, spread, volume and slippage limits.
- Execution layers remain transport-free and cannot submit broker orders.

### V6.0 Release Boundary
- Final fail-closed live-authorization gate.
- Every mandatory evidence flag must be explicitly boolean `True`.
- Required evidence: CI, historical validation, WFO, robustness, paper trading, security review, shadow validation, recovery validation, broker validation and operator approval.
- Missing or synthetic evidence cannot produce a live-ready result.

## Safety boundary

Passing software tests does not establish profitability, broker compatibility, or live safety by itself. Historical datasets, out-of-sample evidence, shadow observations, recovery exercises and broker validation must be produced and reviewed before any live activation.

## Development rule

`main` is kept stable while development and validation continue on `v5.1-development`. The project optimizes for controlled execution, measurable edge and minimized risk of ruin rather than maximum trade count.
