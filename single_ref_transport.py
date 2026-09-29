"""Small, dependency-free Git observation primitive. Policy belongs to the caller."""
from __future__ import annotations

import re
import hashlib
import json
import subprocess
from dataclasses import dataclass, replace
from typing import Callable, Sequence, Any

__version__ = "0.2.2"
OID = re.compile(r"[0-9a-f]{40}")


def parse_exact_ref(stdout: bytes, ref: str) -> tuple[str, ...] | None:
    """Retain the donor's distinction between absent () and unreadable (None)."""
    if not isinstance(stdout, bytes):
        return None
    values = []
    for line in stdout.splitlines():
        try:
            oid, actual_ref = line.decode("ascii").split("\t")
        except (UnicodeError, ValueError):
            return None
        if OID.fullmatch(oid) is None or actual_ref != ref:
            return None
        values.append(oid)
    return tuple(values) if len(values) <= 1 else None


def observe_ref(run: Callable[[Sequence[str], int], Any], repository: str,
                ref: str) -> tuple[str, ...] | None:
    try:
        completed = run(["ls-remote", "--refs", repository, ref], 45)
    except (OSError, TimeoutError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return parse_exact_ref(completed.stdout, ref)


@dataclass(frozen=True)
class Binding:
    """Exact caller-approved request. This value is not an authorization source."""
    repository: str
    ref: str
    candidate: str
    expected_old: str | None  # None means absent-only, never implicit force.

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.__dict__, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Outcome:
    transaction_digest: str
    state: str
    send_attempted: bool = False
    send_accepted: bool | None = None
    observed_oid: str | None = None
    observation: str = "not_read"
    reason: str | None = None


def _valid(binding: Binding) -> bool:
    # Bound strings only; the caller must supply an independently approved Binding.
    return (isinstance(binding.repository, str) and bool(binding.repository)
            and not binding.repository.startswith("-")
            and not any(c in binding.repository for c in "\r\n\x00")
            and ("://" not in binding.repository or
                 (binding.repository.startswith("https://")
                  and "@" not in binding.repository and "?" not in binding.repository
                  and "#" not in binding.repository))
            and isinstance(binding.ref, str) and binding.ref.startswith("refs/heads/")
            and re.fullmatch(r"refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]*", binding.ref) is not None
            and not any(s in binding.ref for s in ["..", "//", ".lock"])
            and not binding.ref.endswith(("/", "."))
            and isinstance(binding.candidate, str) and OID.fullmatch(binding.candidate) is not None
            and (binding.expected_old is None or
                 (isinstance(binding.expected_old, str) and OID.fullmatch(binding.expected_old) is not None)))


def _ancestor(run, old: str, new: str) -> bool | None:
    try:
        result = run(["merge-base", "--is-ancestor", old, new], 30)
    except (OSError, TimeoutError, subprocess.SubprocessError):
        return None
    return True if result.returncode == 0 else False if result.returncode == 1 else None


def reconcile(run, binding: Binding, previous: Outcome) -> Outcome:
    """Read only. Never retries a send, including after an unknown outcome."""
    if not _valid(binding) or previous.transaction_digest != binding.digest():
        return Outcome(binding.digest(), "refused", reason="transaction_binding_mismatch")
    observed = observe_ref(run, binding.repository, binding.ref)
    if observed is None:
        return replace(previous, state="outcome_unknown", observation="unreadable", observed_oid=None)
    if not observed:
        return replace(previous, state="outcome_unknown" if previous.send_attempted else "not_sent",
                       observation="absent", observed_oid=None)
    oid = observed[0]
    if oid == binding.candidate:
        state = "updated" if previous.send_accepted is True else "observed_candidate"
    elif _ancestor(run, binding.candidate, oid) is True:
        state = "advanced_after_ack" if previous.send_accepted is True else "observed_descendant"
    else:
        state = "outcome_unknown" if previous.send_attempted else "conflict"
    return replace(previous, state=state, observation="present", observed_oid=oid)


def push_once(run, request: Binding, approved: Binding, *, cancelled: bool = False) -> Outcome:
    """One exact ref, ancestry + explicit server CAS, then observation. No retry."""
    result = Outcome(request.digest(), "not_sent")
    if request != approved or not _valid(request):
        return replace(result, state="refused", reason="request_not_bound_to_approved_identity")
    if cancelled:
        return replace(result, state="cancelled")
    observed = observe_ref(run, request.repository, request.ref)
    if observed is None:
        return replace(result, state="not_sent", observation="unreadable", reason="preflight_unknown")
    if observed == (request.candidate,):
        return replace(result, state="observed_candidate", observation="present", observed_oid=request.candidate)
    expected = () if request.expected_old is None else (request.expected_old,)
    if observed != expected:
        return replace(result, state="conflict", observation="present" if observed else "absent",
                       observed_oid=observed[0] if observed else None, reason="preimage_mismatch")
    if request.expected_old is not None and _ancestor(run, request.expected_old, request.candidate) is not True:
        return replace(result, state="refused", reason="ancestry_not_proven")
    lease = "--force-with-lease=" + request.ref + ":" + (request.expected_old or "")
    result = replace(result, send_attempted=True, state="outcome_unknown")
    try:
        sent = run(["push", "--porcelain", "--no-follow-tags", lease, request.repository,
                    request.candidate + ":" + request.ref], 180)
        result = replace(result, send_accepted=True if sent.returncode == 0 else None)
    except (OSError, TimeoutError, subprocess.SubprocessError):
        pass  # A timeout is not proof that no update happened.
    return reconcile(run, request, result)
