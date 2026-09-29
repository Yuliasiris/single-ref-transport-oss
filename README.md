# Single-ref transport

One caller-approved Git branch update, explicit expected-OID comparison,
and read-only reconciliation after an uncertain result. Not a credential broker,
authorization service, scheduler, or sandbox.

**Version: `0.2.2`. Licensed under the MIT License.**

## Try it without credentials

From a checkout of this source, run:

```sh
python examples/local_roundtrip.py
```

The example creates and deletes its own temporary working and bare repositories.
It accepts no target argument and makes no network requests. Its four scenarios
are: a successful update, a candidate already present, a stale preimage, and a
readback without an acknowledgement. Only the first scenario pushes a new commit.

Python 3.10+ and Git are required; there are no third-party Python dependencies.
Release qualification used Python 3.13.5 and Git 2.47.3 on Linux. This does not
certify all Git versions, hosts, remote servers, or authentication methods.

For a read-only query against a target you explicitly select:

```sh
python examples/observe.py /absolute/path/to/bare.git refs/heads/main
```

That second example uses the caller's Git environment and can access a remote if
you pass one. Use the first, self-contained example to explore the API safely.

## Use it in a host

The host independently resolves the permitted repository, full branch ref,
candidate commit and expected old commit. It supplies a trusted Git runner that
returns a CompletedProcess-like result with byte stdout and a return code.

```python
from single_ref_transport import Binding, push_once

request = Binding(repository, exact_ref, candidate_oid, expected_old_oid)
result = push_once(trusted_git_runner, request, approved_binding)
```

`approved_binding` must not be a copy of an untrusted request used as proof of its
own approval. The host owns the cwd, credentials, hooks, signing, Git configuration
and server permissions. Use argument arrays, not a shell command string.
This module is not a sandbox, credential broker, GitHub bot or scheduler.

| Function | Result or effect |
|---|---|
| `parse_exact_ref(bytes, ref)` | `()` means a successful empty response; a tuple contains the one exact OID; `None` means malformed input. |
| `observe_ref(run, repository, ref)` | One exact read; failed reads remain unknown rather than absent. |
| `push_once(run, request, approved, cancelled=False)` | At most one push after preimage and ancestry checks; then readback. |
| `reconcile(run, binding, previous)` | Reads and local ancestry inspection only. Never sends. |

`expected_old=None` means **create only if the ref is absent**, not unrestricted
force. Branch refs and full 40-hex SHA-1 commit IDs are covered. Tags, deletions,
SHA-256 repositories, multi-ref transactions and history rewrites are not.

## Interpret a result before deciding what to do

| State | What was established |
|---|---|
| `updated` | This invocation's runner acknowledged a send and the candidate was observed. |
| `observed_candidate` | The candidate is present; this invocation has no send acknowledgement. |
| `advanced_after_ack` | A descendant was observed after an acknowledged send. |
| `observed_descendant` | A descendant is present without that acknowledgement. |
| `outcome_unknown` | The evidence is incomplete. Preserve the binding and reconcile; do not blindly resend. |
| `conflict` | The selected update does not match the observed remote state. |
| `not_sent`, `refused`, `cancelled` | This path did not start a permitted send. |

The digest associates a result with a request; it is not a signature. `previous`
is trusted caller metadata, not authenticated history. Current OID equality does
not reveal which of two actors sent that same commit. Do not turn a readback into
an invented acknowledgement.

## Build and verify the exact package

```sh
python -m unittest -v
python examples/local_roundtrip.py
python build.py ./dist
```

The source checkout includes the regression tests and builder. The runtime ZIP
includes the module, examples, README, SECURITY, PROVENANCE, LICENSE, and
release-preparation instructions. It does not contain the builder or tests.
Extract it into a fresh directory and run the same examples there. No network
endpoint or install-time script is needed. Verify its checksum against an
independently trusted pin before importing code.

The builder fixes member order, timestamps and platform metadata. It refuses
same-version different-byte replacement and requires the license document.
A NOTICE file, when present, is included. Changes to documentation, license or
metadata also require a new version. The source and archive are distinct objects.

## Maintenance and provenance

See [release preparation](docs/releasing.md), [security](SECURITY.md) and
[provenance](PROVENANCE.md). The public source tree is intentionally independent
of the earlier private Git history; provenance is retained separately.

The module provides a bounded one-ref Git operation, not endpoint authorization.
Host approval, credentials, configuration, hooks, source identity and decisions
remain with the host. A software rollback does not rewind remote Git history.
No full application compatibility or OS/browser support matrix is implied.
