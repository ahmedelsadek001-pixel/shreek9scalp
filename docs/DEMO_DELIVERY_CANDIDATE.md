# Unified experimental DEMO delivery candidate

The `v5.3-strict-demo-order-fields` Draft collects the execution hardening from
Drafts #4/#13 and the currently reviewed source changes from Drafts #9, #10,
#11 and #12. Development and main remain unchanged. This candidate is for
software review and experimental Windows DEMO evidence collection, not live
trading or phase promotion.

## Integrated source identities

| Draft | Immutable input commit |
| --- | --- |
| #13: execution, including #4 | `248887294f6052297d600cba36dfb7445698e6c2` |
| #9: release evidence | `97b474c6ceff2aabf70739384b22886311fb6e7b` |
| #10: diagnostics and paper audit | `bb5ea9812b142ad6e710df0c177a6ce9fa61f2a0` |
| #11: stop markers | `dfd4404f2367c8c4965b5be54b1a398f5d54e6d0` |
| #12: agent guidance and isolated checker | `afb6e4dc45546c815d9b4e96a80690991072609f` |

Development base: `0ba61270dc742ede396265cf0ee291ac8693c31d`.
The isolated checker merged these original Git commits without conflict and
passed pytest on tree `45f4d12ae20f593cf624139fdc8cb7785e928e91`.
Captured pytest output SHA-256:
`a4bb398b27bf119f5460fe980590ecb1a7e6c3fb4a37bb03f01c4cd83b95dcc4`.
An independently constructed tree matched. Only its source diff is integrated
into the Draft; temporary verification merge commits are not published.

After adding the offline delivery audit, local Python 3.12 checks passed:
2001 full-suite tests, compile/import checks, zero fatal flake8 findings and
a 310-file static security scan with zero findings. The new audit has 41
focused cases. See Draft #13 for the final immutable candidate commit and
matching hosted CI; this local result alone is not Windows/broker evidence.

## Offline delivery report audit

Preserve the source archive and exact successful candidate CI run. Verify the
complete archive against its independently reviewed CI checkout commit using
[the source verification guide](SOURCE_ARCHIVE_VERIFICATION.md). This source
check does not bind saved reports to the running program. On Windows,
retain the redacted JSON objects from the existing read-only doctor, preflight,
local session and report-demo commands as `doctor.json`, `preflight.json`,
`session.json` and `report-demo.json`. Run the local session and report-demo
commands after the watcher has ended, using the same retained journal and
session limit, so both snapshots agree. Do not include terminal prompts in JSON.

The following command reads those four saved files. It works without Windows,
MT5, account binding or an order ledger. Replace the commit label with the
actual immutable candidate SHA reviewed alongside CI:

```powershell
py -m execution.mt5_demo_delivery_audit_cli `
  --candidate-sha CANDIDATE_COMMIT_SHA `
  --doctor doctor.json `
  --preflight preflight.json `
  --session session.json `
  --report-demo report-demo.json
```

It checks doctor/disk consistency, nested historical preflight refusal gates,
read-only transport state, matching session snapshots, latest session identity,
scan relationships, completed-session chronology and a 24-hour session age
limit. It recomputes the handover assessment. Duplicate decoded JSON keys,
non-finite values, oversized files, future/naive times, mismatched snapshots,
unknown submissions and contradictory retained assessments block the audit.
UTF-8, UTF-8 BOM and UTF-16 BOM captures are supported.

The JSON includes canonical report-content SHA-256 digests and allowlisted
session counts. It does not repeat raw reports, file paths, account identifiers
or input exception messages. Digests bind report content; they do not prove its
origin. The supplied candidate SHA is a label, not verified source evidence.
Saved preflight data is historical and cannot authorize a current attempt.

Exit 0 means only `local_evidence_reviewable`. Exit 2 means blocked or
`local_observation_only`, including the existing missing-ledger no-submission
case. All delivery, source, broker-export, paper, release and live acceptance
flags remain false. A no-signal run cannot prove broker order execution.

## Remaining acceptance evidence

Real Windows/terminal verification, independently verified candidate/CI,
broker export and reconciliation, causal OOS/robustness, sustained paper and
shadow runs, disconnect/recovery evidence, final security review and human
release approval remain required. Reports do not synchronize automatically to
ChatGPT. Do not delete journals, reset an uncertain ledger, retry an unknown
submission or relax any execution gate to complete this checklist.
