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

## Research integrity rules

- Research timestamps must be explicit timezone-aware values; the source timezone is preserved and conversion is explicit.
- Backtest economics require an explicit positive `point_value`; broker-specific contract assumptions are not embedded in the generic research engine.
- Spread, slippage and commission are modeled explicitly and validated as finite non-negative inputs.
- Purged WFO defaults to non-overlapping OOS windows (`step >= test_size`) so observations are not silently reused as independent OOS evidence.
- Parameter selection is train-only; the selected parameter set is evaluated once on each OOS slice.
- Warm-up context may provide prior bars for causal state formation, but trades generated before the OOS boundary are rejected from OOS evidence.
- A green CI run proves software checks passed; it does not prove profitability, statistical significance, broker compatibility or live readiness.

## Version path

### V5.1 — Hardening and safety
Core risk, data-integrity, admission, paper, shadow, reconciliation and recovery layers.

### V5.2 — Research and edge validation
MAE/MFE, regime classification, attribution, edge matrix, WFO stability and robustness analysis.

### V5.3 — Execution engineering
Execution-quality measurement, broker safety boundaries, shadow validation and recovery controls.

### V6.0 — Controlled release
Final release certification, security review, empirical evidence package and live-authorization gate.

## CI/CD

The development branch runs GitHub Actions across Python 3.9, 3.10 and 3.11 with import validation, static release security checks, linting and pytest. Release evidence is generated only after the build matrix succeeds.

The release sequence is documented in `CHANGELOG.md`. Release candidates use semantic-version pre-release tags such as `5.1.0-rc.1`; no RC is considered valid until its required empirical and safety gates pass.

## Safety boundary

Live MT5 execution remains disabled until all mandatory software and empirical gates pass. Passing unit tests or CI does not establish profitability, statistical significance, broker compatibility, or live readiness.

## Development rule

`main` remains stable while development and validation continue on `v5.1-development`. The objective is not maximum trade count; it is measurable edge, controlled execution, and minimized risk of ruin.
