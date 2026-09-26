# Changelog

All notable changes to SHREEK AI Trading System are documented here.

## [Unreleased] — v5.1-development

### Hardening

- Enforced non-overlapping Purged WFO OOS windows by requiring `step >= test_size`.
- Added fail-closed validation for nested Breakout + Retest research configuration.
- Enforced explicit backtest `point_value`; broker-specific dollar contract assumptions remain outside the research engine.
- Added validation for spread, slippage, commission and timeframe inputs.
- Added explicit OOS-boundary checks when warm-up context is supplied to the backtest WFO evaluator.
- Preserved the rule that parameter selection uses train data only and each selected OOS slice is evaluated once.
- Validate causal liquidity boundaries before any early return.
- Align the Sharpe unit test with the unannualized sample-statistic definition and exclude initial equity baseline from returns.
- Strengthen robustness evidence validation and correct the tampering test to alter the intended worst-tail field.
- Reorder OOS overlap validation to report the targeted overlap error before unrelated boundary checks.

### Backtest economics

- Separated gross market P&L from execution costs.
- Applied spread and slippage at entry and exit.
- Applied commission to executed volume.
- Added unit coverage for point-value scaling, volume scaling and invalid cost models.

### CI/CD

- CI validates Python 3.9, 3.10 and 3.11.
- CI runs import validation, static release security checks, flake8 and pytest.
- Release evidence is generated only after the build matrix succeeds and binds provenance to the GitHub Actions run and commit.
- CI run `35440718877` passed the build matrix and release-evidence job for commit `62761a4a5ec375ff7d696804b4107de932d61180` (Python 3.9, 3.10 and 3.11).

### Safety

- `main` remains the protected/stable integration target; development continues on `v5.1-development`.
- Live MT5 execution remains disabled by architecture and is not enabled by CI success.

## Planned release sequence

1. Complete V5.1 hardening and obtain reproducible green CI evidence.
2. Complete V5.2 research validation: WFO, robustness, MAE/MFE, regime and attribution evidence.
3. Complete V5.3 execution safety and reconciliation validation.
4. Produce an RC only after the empirical evidence package and release gates are complete.
5. V6.0 release certification requires all mandatory authorization gates, including operator approval; CI success alone is insufficient.

## Versioning policy

Use semantic versioning for release tags (`MAJOR.MINOR.PATCH`). Pre-release candidates use `-rc.N`, for example `5.1.0-rc.1`. Development commits remain on the development branch until the corresponding release candidate gates pass.
