# SHREEK experimental DEMO delivery: 1 October 2026

Target: Thursday, 1 October 2026, Africa/Tripoli. This is an experimental
Windows DEMO delivery, not research certification or live-trading approval.
Source branch: `v5.1-development`. Keep the downloaded source archive and
record its commit alongside the exact successful CI run before acceptance.

## Operator sequence

1. Extract the development archive into a new directory on the Windows PC.
   Keep the existing `%LOCALAPPDATA%\SHREEK` ledger and scan journal.
2. Open the dedicated, already logged-in DEMO terminal. Install Python 3.9+
   with the Windows `py` launcher if missing. Run
   `.\connect_mt5_demo.cmd --doctor` from PowerShell and require
   `ready_to_prepare=true`. Diagnose local disk space before entering the
   hidden account number; keep the existing ledger and scan journal.
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
   quotes would refuse a new trading preflight. The envelope also includes
   `handover_assessment`: `observation_only` means no order was submitted in
   the latest clean session; `manual_review_required` means a submitted
   intent matches local broker history but still lacks independent evidence;
   `blocked` means the reports are missing, inconsistent or need inspection.
   No state marks paper trading validated or grants live authority.
   An existing runtime can read this report even if the local disk reserve
   blocks another session; the watcher remains blocked until space is freed.
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
When MT5 is unavailable, `--report-local` can recover the local session
observations without installing the package or accessing the broker. It is
insufficient to reconcile an order or mark paper trading validated.

### No-submission session without an order ledger

A clean latest opt-in session with zero signals/submissions and no order IDs
can be classified `local_observation_only` when broker reporting specifically
returns `durable DEMO ledger unavailable`. This describes only the retained
local session, not the account's complete trading history. Broker verification
and paper validation remain false; the report still exits 2 because broker
history is unavailable. Never create an empty replacement ledger to clear this
condition. Any recorded submission, ambiguous outcome, incomplete session,
safety refusal, conflicting identifier or other broker error remains blocked.
