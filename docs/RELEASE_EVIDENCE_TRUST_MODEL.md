# Release evidence trust boundary

## Current state: fail closed

EvidenceRecord stores a claim (name, passed, source, run_id, timestamp and
commit SHA). ReleaseEvidenceBundle validates the claim's shape, canonical
digest, common commit binding and internal consistency. Those checks detect
later mutation; they do not authenticate the producer or prove that the named
CI run, market-data audit, broker reconciliation, shadow session, recovery
exercise or operator approval actually occurred.

The source and run_id strings are caller-supplied metadata. A caller can
construct all required records with passed=True, an arbitrary source label
and a fabricated run ID. Therefore a self-hashed bundle is not sufficient
evidence of the real-world controls it describes.

Until a trusted verifier is implemented for each evidence class, both V5.1
certification and V6 release authorization deliberately reject an otherwise
complete all-True bundle with:

evidence claims are self-asserted; independent authenticity verification is not implemented

A failed or missing evidence item remains a separate blocker and is reported
as such. No metadata field, bundle digest, expected commit pin, CI green state,
or caller-provided Boolean can override this boundary.

The low-level V6 flag evaluator reports only whether the required claims are
complete. Its authorization field remains false, and the require-style helper
raises even when every Boolean is true. Only a future independent evidence
verifier may create a positive authorization path.

## Requirements to restore a positive release path

Each evidence producer needs a verifiable, immutable artifact and an explicit
trust policy. At minimum:

1. CI and tests: verify a GitHub artifact attestation from the expected
   repository, workflow path, event policy and commit; bind the subject digest.
2. Data integrity and WFO: retain exact dataset and configuration fingerprints,
   run outputs, cost assumptions and independent reproducibility checks. A
   source archive attestation is not research evidence.
3. Robustness: verify the actual Monte Carlo/bootstrap outputs and policy
   version; reject a report that is merely marked passed.
4. Paper/shadow/execution: require broker-origin records, account/time scope,
   fills/deals reconciliation, immutable journal and discrepancy handling.
   Local CSV presence is not broker validation.
5. Recovery: retain fault-injection scenario, timestamps, expected versus
   observed recovery state, and independent pass/fail evaluation.
6. Security: bind a signed review report to the exact code commit and reviewer
   identity.
7. Operator approval: require a separately authenticated approval bound to
   the exact release manifest and commit, with expiry/revocation semantics.

The verifier must validate signer identity, signature, subject digest, source
repository/workflow, commit and policy version. Missing trust roots, stale
attestations, unknown issuers, ambiguous artifacts or mismatched commits must
block. Never accept a verified=True field supplied by the evidence payload.

## Explicit non-authorizations

Passing source archive verification proves source bytes against a commit pin.
It does not prove runtime identity, research edge, broker fills, strategy
profitability, safe operation or live readiness. CI success is software
validation only. DEMO and live order transport remain disabled until every
independent gate is satisfied and separately approved.
