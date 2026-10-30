# SHREEK Product Architecture and Commercialization Roadmap

Status: design contract only. This document does **not** authorize live trading.

## Product boundary

SHREEK is developed as an evidence-first trading platform, not a distributable source-code bot.

```text
Market / MT5
    |
Local SHREEK Bridge
    |
Execution Safety + Risk + Idempotency
    |
SHREEK Core
    |
Backend API
    +-- Signals
    +-- Evidence / performance
    +-- Entitlements
    +-- Audit log
    |
Dashboard / Notifications / Admin
```

The trading core remains isolated from billing and presentation concerns. A subscription can grant access to a capability, but **cannot** bypass research, risk, execution-safety, or live-readiness gates.

## Delivery stages

1. **Research** — causal backtest, purged WFO, OOS evidence, Monte Carlo, statistical certification and reproducible artifacts.
2. **Signals-only private beta** — no broker execution. Validate reliability, latency, UX and evidence presentation.
3. **Paid Signals / Pro** — subscription entitlements for signals, analytics and evidence. No automatic live authorization.
4. **Shadow / paper bridge** — local bridge observes or simulates intended execution and records broker-quality evidence.
5. **Demo execution** — execution lifecycle, reconciliation, idempotency, kill switch and limits must pass.
6. **Live-readiness review** — explicit release decision backed by V6 evidence. Live remains disabled by default.
7. **Optional live execution product** — only after technical and applicable legal/compliance requirements are satisfied.

## Trust boundaries

### Cloud must never require broker passwords
Prefer a local bridge. Broker credentials remain local where practical. Cloud-issued requests are authenticated instructions, not unconditional orders.

### Entitlements are server-side
UI visibility is not authorization. Every paid capability must be checked by backend entitlement. Expired/revoked entitlement fails closed.

### Trading authorization is separate from subscription authorization
A valid subscription means only that a customer may access the purchased product capability. It never implies:
- strategy certification;
- permission to trade;
- acceptable account risk;
- broker connectivity;
- live-readiness.

### Evidence labels
Performance surfaces must distinguish at minimum:
- backtest;
- OOS/WFO;
- Monte Carlo/statistical evidence;
- paper/shadow;
- demo;
- live.

Do not merge these into a single unlabeled performance curve.

## Initial commercial capabilities

```text
SIGNALS
  read current/archived signals
  read basic evidence

PRO
  SIGNALS +
  advanced analytics
  research evidence views
  risk tooling

AUTO (future, locked)
  PRO +
  bridge capability
  execution controls
```

AUTO is a future entitlement. Its existence in code or billing must not enable live execution.

## Required platform modules

- `platform/auth` — users, sessions/service identities.
- `platform/entitlements` — plan/capability authorization.
- `platform/audit` — append-oriented security and trading audit events.
- `platform/signals` — immutable signal publication and retrieval.
- `platform/evidence` — exposes validated research artifacts without rewriting results.
- `bridge/` — local MT5 adapter with authenticated requests and fail-closed lifecycle.
- `dashboard/` — presentation only; never the security boundary.
- `billing/` — provider adapter; billing state maps to entitlements, not execution permission.

## Commercial safety invariants

1. Billing webhooks are untrusted input until signature/authenticity verification succeeds.
2. Duplicate billing or bridge messages must be idempotent.
3. Revocation/expiry must remove paid capability without deleting audit history.
4. No API response may represent backtest/OOS/paper performance as live.
5. No customer-controlled field may select an arbitrary executable module.
6. Secrets and broker credentials must never be committed to the repository.
7. Live execution must require an explicit execution mode plus all safety gates; default is non-live.
8. A network failure or ambiguous broker result becomes UNKNOWN and blocks replay until reconciled.
9. Commercial/admin controls cannot override execution safety gates.
10. Research certification is evidence, not a profit guarantee or execution authorization.

## Next engineering milestones

### C1 — Commercial foundation
Implement typed capability/entitlement domain model with fail-closed authorization and tests. No payment provider dependency.

### C2 — Signal contract
Define immutable, versioned signal envelope with strategy/version/evidence identity, timestamps, expiry and risk metadata.

### C3 — Audit contract
Define deterministic audit events for entitlement changes, signal publication, bridge requests and execution lifecycle transitions.

### C4 — Local bridge protocol
Authenticated request envelope, nonce/idempotency key, expiry, account binding and explicit execution mode. No live implementation until V5.3/V6 gates permit it.

### C5 — API/dashboard
Expose read-only signals/evidence first. Add paid entitlements after private beta.

### C6 — Billing adapter
Integrate a legally/operationally suitable payment provider behind a provider-neutral interface. Billing never imports or calls MT5 execution code.

## Definition of commercial readiness

Commercial readiness requires evidence for software reliability, security, observability, support/revocation procedures, truthful performance labeling, and applicable legal/compliance review. It is separate from research certification and from live-trading readiness.
