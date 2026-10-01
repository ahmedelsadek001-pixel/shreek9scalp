# Shreek Scalper V5.1 — Development Baseline

## Purpose

This branch is the controlled migration path from the legacy V2 code on `main` to the V5.1 production architecture stored in the project archive.

## Safety policy

- `main` is not modified by this migration.
- No live MT5 order execution is enabled by this branch baseline.
- Missing credentials must fail closed; no hard-coded secrets and no unsafe default lot size.
- Analysis must use closed candles for signal decisions.
- A signal is not a trade. The journal must distinguish signal, accepted setup, executed order, and closed trade.
- Risk gates are authoritative; AI narration cannot override them.

## V5.1 migration order

1. Import the archived V5.1 package and preserve its test suite.
2. Remove generated/runtime artifacts from source control.
3. Move all credentials to environment variables / deployment secrets.
4. Enforce Telegram user authorization centrally.
5. Enforce closed-candle data and deterministic signal timestamps.
6. Harden ICT/SMC detection: structure, liquidity sweep, displacement/MSS, FVG, and order blocks.
7. Harden risk sizing: floor to broker volume step and fail closed on calculation errors.
8. Add spread/volatility/session/news/daily-loss/cooldown hard gates.
9. Keep OpenAI strictly as a constrained analysis/narration layer; deterministic code owns risk and execution decisions.
10. Run the complete automated test suite and CI.
11. Validate with real MT5 historical data using walk-forward/backtest and Monte Carlo analysis.
12. Forward-test on demo before any live execution integration.
13. Only then add and separately test the MT5 execution engine.

## Acceptance criteria

The branch is not considered live-ready until:

- all tests pass;
- no secrets exist in tracked source files or sample configs;
- production startup refuses an empty Telegram allowlist;
- no trade can pass without all hard gates;
- no trade can be opened when risk sizing fails;
- live and backtest position-management logic are shared;
- historical testing uses only information available at each candle timestamp;
- demo forward testing confirms signal stability and order-management behavior.
