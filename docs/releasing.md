# Preparing a release

This repository is a clean public-source lineage. Do not import private Git objects,
old distribution bundles, Issue/PR conversations, CI logs, private test corpora,
or credentials into this history. Preserve private origins separately when needed
for provenance and audit.

Run the tests and examples documented in README.md, then build the runtime archive.

```sh
python build.py ./dist
```

The ZIP manifest records every payload member's length and SHA-256. Compare the
archive checksum against a separately trusted pin before loading any code. A checksum
authenticates neither its publisher nor the repository from which it was obtained.

Identical inputs rebuild identically. An existing archive is never overwritten
with different bytes under the same version. LICENSE, NOTICE, metadata, examples,
and documentation are release inputs too: changing any of them requires a new
version. Build source archives from an explicit allowlist rather than recursively
zipping a developer checkout.

The release is licensed under MIT. If a future upstream NOTICE or other attribution
requirement is discovered, preserve it before redistributing affected versions.
The builder includes a NOTICE file when one is present.

## Consumer updates and rollback

Publishing this component does not automatically change a private consumer pin.
Consumers should review and adopt a public release as a distinct source identity.
A clean-root source must not impersonate an older provider's parentage.

Rollback restores the previous software and pin; it does not restore an old data
snapshot over newer saved user data or rewrite remote Git history.
