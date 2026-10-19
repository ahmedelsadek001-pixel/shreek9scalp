# Verify a complete source delivery archive

CI builds the source ZIP from the original Git objects of its exact checkout
commit. It includes every committed regular file, including documentation,
configuration and Windows launch scripts, with its committed executable mode.
Dirty edits, untracked files and generated CI provenance cannot enter the ZIP.
The CI provenance remains a separate artifact associated with the same run.

The ZIP contains `shreek-source-manifest.json`, which records the original
commit object, complete file inventory, Git blob identities and SHA-256
digests. The verifier reconstructs the entire Git tree and hashes the original
commit object against an independently trusted commit pin. Recalculating the
manifest's digest after changing, adding or removing files cannot make those
bytes match the original pinned tree.

## Obtain the independent pin

Use the exact commit checked out by a successful, independently reviewed CI
run. A pull-request run usually checks out GitHub's temporary merge commit;
that commit can differ from the Draft branch head. Confirm its parents and
tree against the reviewed base and candidate. Record the successful run URL
and checkout identity together. Do not copy the expected pin from an
untrusted ZIP, its filename or its embedded manifest.

Download the source artifact from that run. GitHub wraps the source ZIP in an
artifact ZIP; select the inner `shreek9scalp-source-CI_CHECKOUT_SHA.zip` for
verification. Use the verifier from a separately trusted project checkout.
Verifying or importing a verifier supplied only by an untrusted archive would
not establish an independent check.

```powershell
py -m utils.source_archive verify `
  --archive shreek9scalp-source-CI_CHECKOUT_SHA.zip `
  --expected-commit CI_CHECKOUT_SHA
```

The command reads the ZIP without extracting, executing or importing its
contents. Verification uses the Python standard library; it does not need
Git, network access, Windows, MT5 or a broker connection. It reports only
allowlisted identities, digests and counts. Duplicate ZIP members, decoded
JSON keys, unsafe paths, permission changes, unsupported member types,
missing or extra files, corrupt content and bounded size violations block it.

Exit 0 means `source_content_verified`: all source bytes and Git file modes
match the independently pinned commit and tree. Exit 2 means blocked. The
archive SHA-256 is also returned for retention. A Git SHA-1 identity is used
to compare the existing repository's commit, tree and blobs; per-file and
manifest SHA-256 digests supplement that comparison.

## Build locally from original objects

```powershell
py -m utils.source_archive build `
  --repo . `
  --commit EXACT_COMMIT_SHA `
  --output source-EXACT_COMMIT_SHA.zip
```

Building requires Git and an immutable 40-character lowercase commit SHA.
Replacement references and inherited `GIT_*` settings cannot substitute
different objects. The builder ignores export substitutions and exclusions;
it reads the original committed blobs. It preserves the working tree and
Git configuration, refuses to overwrite an existing output, verifies a new
archive before reporting success and removes its own incomplete output on
failure. Symlinks, submodules, case collisions and the reserved manifest
filename fail closed rather than being silently omitted.

## Limits of source verification

This proves source content against the independent pin. It does not verify a
GPG signature, attest CI success, prove which code is currently running, or
bind the saved doctor/session reports to that runtime. It grants no order,
delivery, release, phase or live authorization. Public author and signature
metadata from the original commit may be present in the embedded commit
object; the CLI does not repeat that payload in its output.

Windows/terminal evidence, broker reconciliation, research robustness,
sustained paper/shadow observation, recovery evidence and human approval
remain separate acceptance requirements.
