# Authenticated CI provenance

## Purpose

The JSON manifest's SHA-256 digest detects accidental or unauthenticated edits only when compared with a trusted digest. A digest stored beside the manifest is not an authenticity proof. This workflow therefore asks GitHub Actions to issue a build-provenance attestation for both the manifest and the source archive.

## Workflow boundary

- The build matrix and tests run for pull requests as before.
- The release-evidence job runs only for successful `push` events.
- The evidence job receives only the permissions needed to read the repository, inspect workflow metadata, request an OIDC identity token, and publish attestations.
- The attested subjects are the generated provenance manifest and source archive.
- No broker credentials, MT5 terminal, order transport, or live authorization are used.
- A pull-request CI pass is a software check, not an authenticated release-evidence publication.

## Independent verification

Download the exact manifest and source archive from the successful push workflow run, then verify each artifact using GitHub CLI:

```bash
gh attestation verify shreek-ci-provenance.json --repo ahmedelsadek001-pixel/shreek9scalp
gh attestation verify shreek9scalp-v5.1-development-<COMMIT_SHA>.zip --repo ahmedelsadek001-pixel/shreek9scalp
```

Review the verification output. It must identify the expected repository and the approved workflow identity. Also compare the manifest's `commit_sha` with the independently selected candidate commit and confirm that the source archive name contains that same SHA.

Do not accept an artifact merely because its embedded `manifest_sha256` matches. That value is self-reported and is not a signature.

## Acceptance conditions

- [ ] The exact candidate push has a successful build matrix and test suite.
- [ ] The release-evidence job completes only after the build matrix succeeds.
- [ ] Both the JSON manifest and source archive have verifiable GitHub artifact attestations.
- [ ] The attestation identifies this repository and the expected workflow.
- [ ] The manifest commit, archive filename, workflow run, and reviewed candidate SHA agree.
- [ ] A tampered artifact fails attestation verification.
- [ ] Pull-request runs do not publish release attestations.
- [ ] No result grants broker or live-trading authority.

## Limitations

An attestation proves the provenance of the attested artifact under the stated GitHub workflow identity. It does not prove strategy profitability, statistical validity, broker execution, paper-trading duration, or live readiness. Those remain separate evidence gates.
