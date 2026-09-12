# SHREEK V5.2 → V6.0

نظام تداول آلي موجه أساسًا لـ XAUUSD، مبني على ICT/Price Action، تحليل متعدد الأطر الزمنية، وإدارة مخاطر fail-closed.

## Architecture

`MARKET DATA → DATA INTEGRITY → SIGNAL ENGINE → SETUP QUALITY → REGIME → ADMISSION FIREWALL → RISK BUDGET → DAILY RISK STATE → BACKTEST/WFO → ROBUSTNESS → PAPER → SHADOW → RECONCILIATION → RECOVERY → RELEASE GATE`

## Implemented layers

- Closed-bar chronological market-data validation.
- HTF structure, liquidity, FVG, order-block and PD-array analysis.
- Deterministic M15/M5/M3 execution signals and execution levels.
- Setup-quality scoring and admission threshold.
- High-impact news and session/trading-window controls.
- Position lifecycle with TP1/TP2/TP3, breakeven and trailing behavior.
- Causal backtesting with deterministic costs and next-bar entry.
- Walk-forward and advanced WFO stability analysis.
- Monte Carlo robustness, drawdown and ruin gates.
- Daily risk ledger, risk state machine and deterministic position sizing.
- MAE/MFE research analytics.
- Strategy and regime attribution.
- Setup × regime edge matrix.
- Deterministic paper-trading engine.
- Shadow intents, execution reconciliation and disconnect recovery.
- Execution-quality analytics for slippage and spread.
- Release manifest, release evidence and security/release gates.
- AI advisor remains advisory-only; it cannot authorize, size, or execute trades.

## Version path

### V5.1 — Hardening and safety
Core risk, data-integrity, admission, paper, shadow, reconciliation and recovery layers.

### V5.2 — Research and edge validation
MAE/MFE, regime classification, attribution, edge matrix, WFO stability and robustness analysis.

### V5.3 — Execution engineering
Execution-quality measurement, broker safety boundaries, shadow validation and recovery controls.

### V6.0 — Controlled release
Final release certification, security review, empirical evidence package and live-authorization gate.

## Safety boundary

Live MT5 execution remains disabled until all mandatory software and empirical gates pass. Passing unit tests or CI does not establish profitability, statistical significance, broker compatibility, or live readiness.

## Development rule

`main` remains stable while development and validation continue on `v5.1-development`. The objective is not maximum trade count; it is measurable edge, controlled execution, and minimized risk of ruin.
