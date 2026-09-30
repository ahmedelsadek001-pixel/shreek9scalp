# SHREEK experimental DEMO delivery: 1 October 2026

Target: Thursday, 1 October 2026, Africa/Tripoli. This is an experimental
Windows DEMO delivery, not research certification or live-trading approval.
Source branch: `v5.1-development`. Keep the downloaded source archive and
record its commit alongside the exact successful CI run before acceptance.

## Operator sequence

1. Extract the development archive into a new directory on the Windows PC.
   Keep the existing `%LOCALAPPDATA%\SHREEK` ledger and scan journal.
2. Open the dedicated, already logged-in DEMO terminal. Install Python 3.9+
   with the Windows `py` launcher if missing.
3. Open PowerShell in the extracted project folder. Run
   `.\connect_mt5_demo.cmd` and enter the local terminal binding. Use the
   exact symbol and verified broker clock offset. Never send credentials
   to chat or commit them to Git.
4. Require `connected_demo=true`, `ready_for_demo_session=true` and empty
   local/broker blockers. A strategy scan refusal is not a fill. Session
   gaps require inspection; do not disable the continuity gate.
5. Start one experimental session using
   `.\connect_mt5_demo.cmd --watch-demo`. Keep this one watcher open.
   The session stops after one submission attempt or 60 minutes.
6. After it ends, run `.\connect_mt5_demo.cmd --report-demo`. This prints
   one JSON envelope with local sessions and broker history, with execution
   opt-ins disabled. It can inspect history even when current positions or
   quotes would refuse a new trading preflight.
7. Review the report locally and provide only the redacted JSON for review.
   Reports do not automatically synchronize to ChatGPT. Reconcile any
   submitted attempt against an independent broker history export.

## Acceptance evidence

| Item | Required observation |
| --- | --- |
| Exact source | Commit and successful CI for that commit |
| Native connection | Real Windows DEMO preflight JSON |
| Session | Persisted scans and recorded end reason |
| Submission, if present | Local intent matched to broker history and independent export |
| No signal | Explicit no-signal result, no submission, recorded session end |
| Unknown outcome | Stop, inspect ledger and broker history, no retry |
| Security incident | Review the GitGuardian file/line before resolving or dismissing |

No-signal sessions can demonstrate connection, polling and journaling. They
do not demonstrate order execution. An actual broker fill remains pending
unless independently evidenced. CI and fake-MT5 tests do not prove strategy
profitability or Windows execution. This checklist does not close V5.1,
V5.2, V5.3 or V6.0 certification gates by assertion.

## Stop and recovery

Use Ctrl+C or create `%LOCALAPPDATA%\SHREEK\demo_orders.stop` to stop future
scans. Do not delete the ledger, journal or an active session lock. After a
crash, inspect broker history and confirm no watcher is active before
manually removing a stale lock. Do not retry a sent or uncertain attempt.
The report command returns status 2 if either report is unavailable. This
does not mean a previous order was unsent and does not authorize a retry.
