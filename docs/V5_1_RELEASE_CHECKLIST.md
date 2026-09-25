# SHREEK V5.1 Release Checklist

This checklist is the release boundary for V5.1. A green unit-test suite alone is not sufficient for release.

## Required gates

- [x] Data integrity validation is fail-closed.
- [x] Setup/session/news admission is fail-closed.
- [x] Risk state and daily loss budget are enforced before paper admission.
- [x] Duplicate signal identity is deterministic and concurrency-safe.
- [x] Paper trading has deterministic lifecycle behavior.
- [x] XAUUSD paper risk and net P&L can use the declared contract value and
  round-trip commission; admission and orchestration reject mismatched units.
- [x] Shadow execution has no broker send authority.
- [x] Execution reconciliation validates identity, symbol, direction, volume and price tolerance.
- [x] Disconnect/recovery blocks submission until reconciliation is clean.
- [x] Release Gate requires shadow and recovery validation.
- [x] Release Evidence requires provenance for every release control.
- [x] Release Certification produces a single READY/BLOCKED decision.
- [x] Release Manifest binds certification to an exact commit and evidence bundle.
- [x] CI runs the static security gate.
- [x] CI validates imports, lint and pytest on Python 3.9/3.10/3.11.

## Evidence required before RC approval

The following must be produced from real runs, not manually asserted:

1. CI workflow run for the exact release commit.
2. Full pytest result for the exact release commit.
3. Data-integrity validation result on the release test dataset.
4. Walk-forward result and robustness report from the release dataset/configuration.
5. Paper-trading validation result.
6. Shadow reconciliation result.
7. Recovery validation result, including a disconnect/reconnect scenario.
8. Security scan result for the exact release tree.
9. Human review of strategy assumptions, risk limits and operational controls.

The default `PaperTradingEngine` uses a one-unit synthetic price model for
legacy fixtures and is not XAUUSD broker evidence. Use
`PaperTradingEngine.from_xauusd_manifest(...)` for contract-value and
commission-aware simulations. The caller must supply the matching contract
point value to `TradeOrchestrator`; a mismatch fails closed. The resulting
fills still assume the supplied entry and exit prices are executable and do
not independently measure spread, slippage, broker source, or paper duration.

## Live-trading boundary

V5.1 certification does **not** authorize live MT5 order submission. Live execution remains blocked until a separate shadow-to-live review validates broker connectivity, symbol specifications, spread/slippage behavior, order reconciliation, restart recovery and operational kill-switch behavior.
