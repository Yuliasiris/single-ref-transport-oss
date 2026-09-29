# Security boundary

This module reduces mistakes inside a trusted host. It is not an adversarial
sandbox. Host/server authorization remains mandatory.

The host must supply an independently approved binding and a stable Git runner.
Use full candidate commit IDs, isolate the intended worktree, verify real object
ancestry (do not trust replace/graft overlays), control repository URL rewrites,
redirects and helpers, and preserve required hooks/signing. Exact lease comparison
and ancestry are different checks; neither can be omitted merely because the other
passed. Default Git configuration can change endpoint and object interpretation.

`Outcome` omits raw stdout/stderr, but runner logs and exception logging may contain
private URLs or credentials. Redact them at the host. Never place tokens in URLs.
The digest is unsigned. Tamper-resistant receipts require a host mechanism outside
this package. Do not reuse a result after its binding or policy changes.

A timeout is not proof that nothing happened. Reconcile the same binding read-only.
A descendant or unreadable result must not cause an automatic overwrite or resend.
Rollback means restoring local software, not rewinding remote history.

## Reporting a vulnerability

Use GitHub's **Security → Report a vulnerability** flow for this repository.
Do not disclose sensitive vulnerability details, credentials, or private URLs in a
public issue. If the private reporting flow is unavailable, avoid public disclosure
until a private maintainer channel is available.

The release qualification described in README.md is scoped to the documented
version; it is not a broader platform security certification.
