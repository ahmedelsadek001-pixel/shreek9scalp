# V5.2 Research Release Gate

The V5.2 to V5.3 research gate requires all nine research checks plus an
artifact-bound evidence bundle. Each record names one check and includes its
pass result, artifact source, run ID, UTC-capable recording time, source commit,
and the SHA-256 of the artifact. Records must cover every required check and
refer to the same source commit. The caller supplies that commit separately as
`expected_commit_sha`; a stale or incomplete bundle cannot pass.

Use `ResearchReleaseEvidenceRecord.from_artifact_bytes()` to calculate each
record's digest from the exact bytes being reviewed. Pass those same named
bytes to `evaluate_research_release(..., artifact_bytes_by_name=...)`; the gate
recomputes every digest before it can pass. Missing files, changed bytes, or
unrecognized evidence names fail closed.

`ResearchReleaseDecision.as_dict()` emits the decision, bundle digest, source
commit, failures, and a SHA-256 manifest over those fields. Keep the manifest
and evidence bundle with the release record. These hashes are not digital
signatures, and the gate does not fetch or independently attest to CI, data,
or broker artifacts. A passing decision permits only research-stage
consideration; it does not enable paper or live trading.

## Command-line verification

Run the verifier from the repository root:

```sh
python -m research.research_release_cli --manifest path/to/research-release.json
```

The version `1` JSON manifest has four top-level fields: `schema_version`,
`expected_commit_sha`, `evidence`, and `records`. `evidence` maps each of the
nine names from `ResearchReleaseEvidence` to a JSON boolean. `records` has one
entry per name, with `passed`, `source`, `run_id`, timezone-qualified
`recorded_at`, `commit_sha`, `artifact_path`, and `artifact_sha256` fields.
Artifact paths are relative to the manifest and may not resolve outside its
directory. The verifier checks each recorded digest against the exact file
bytes, then emits the archivable decision JSON on stdout.

Exit status `0` means all research checks pass; `1` means the manifest was
valid but the release gate denied readiness; `2` means the manifest or
evidence files were invalid or unreadable. The emitted `ready` result remains
research-only and never authorizes execution.

## Verifying CI provenance

CI provenance is generated and checked with `research.ci_provenance`. To
recheck a downloaded provenance JSON file against the matching source tree:

```sh
python -m research.ci_provenance --manifest shreek-ci-provenance.json \
  --root path/to/source-checkout --expected-commit-sha <40-character-commit>
```

The verifier checks the canonical manifest digest, expected commit, complete
production Python file inventory, and every file digest. It excludes tests
and generated cache/virtual-environment directories from the Python inventory.
This detects accidental changes and incomplete artifacts; SHA-256 alone does
not authenticate who created the manifest.
