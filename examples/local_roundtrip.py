"""Run a complete one-ref example against temporary local Git repositories.

No network URL or repository argument is accepted. This example owns the fixture
and its approvals; it is not an authorization adapter for arbitrary user input.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from single_ref_transport import Binding, Outcome, push_once, reconcile


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit("usage: python examples/local_roundtrip.py (no arguments)")
    executable = shutil.which("git")
    if executable is None:
        raise SystemExit("Git is required; no repository has been changed.")
    with tempfile.TemporaryDirectory(prefix="one-ref-example-") as directory:
        base = Path(directory)
        home, work, target = (base / name for name in ("home", "work", "target.git"))
        home.mkdir()
        # Isolate only this disposable example, not a user's normal Git runner.
        # No hooks are disabled and no credentials from a real checkout are used.
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GIT_") and key not in ("SSH_ASKPASS",)}
        env.update(HOME=str(home), USERPROFILE=str(home), XDG_CONFIG_HOME=str(home),
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1",
                   GIT_AUTHOR_NAME="Local example", GIT_COMMITTER_NAME="Local example",
                   GIT_AUTHOR_EMAIL="example@example.invalid",
                   GIT_COMMITTER_EMAIL="example@example.invalid")

        def git(args: Sequence[str], *, cwd: Path = base, timeout: int = 30,
                check: bool = True) -> subprocess.CompletedProcess:
            return subprocess.run([executable, *args], cwd=cwd, env=env,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=timeout, check=check)

        git(["init", "--quiet", "--initial-branch=main", "--object-format=sha1", str(work)])
        git(["init", "--quiet", "--bare", "--object-format=sha1", str(target)])
        ref = "refs/heads/example"

        def commit(text: str) -> str:
            (work / "example.txt").write_text(text, encoding="utf-8")
            git(["add", "--", "example.txt"], cwd=work)
            git(["commit", "--quiet", "-m", "Update local example"], cwd=work)
            return git(["rev-parse", "HEAD"], cwd=work).stdout.decode("ascii").strip()

        first = commit("original\n")
        git(["push", "--quiet", str(target), f"{first}:{ref}"], cwd=work)
        second = commit("candidate\n")
        third = commit("next candidate\n")
        push_calls = 0

        def runner(args: Sequence[str], timeout: int) -> subprocess.CompletedProcess:
            nonlocal push_calls
            args = list(args)
            if not args or args[0] not in ("ls-remote", "merge-base", "push"):
                raise ValueError("unexpected command in local-only example")
            if args[0] == "ls-remote" and args != ["ls-remote", "--refs", str(target), ref]:
                raise ValueError("unexpected observation target")
            if args[0] == "push":
                if args[-2] != str(target) or args[-1] != f"{second}:{ref}":
                    raise ValueError("unexpected update target")
                push_calls += 1
            return git(args, cwd=work, timeout=timeout, check=False)

        # The fixture owner independently selected these exact objects and target.
        approved = Binding(str(target), ref, second, first)
        request = Binding(str(target), ref, second, first)
        updated = push_once(runner, request, approved)
        assert updated.state == "updated" and updated.send_accepted is True
        assert updated.observed_oid == second and push_calls == 1

        # Already present is an observation, not another acknowledged send.
        already_present = push_once(runner, request, approved)
        assert already_present.state == "observed_candidate"
        assert already_present.send_attempted is False and push_calls == 1

        # The first commit is no longer the expected remote preimage.
        stale = Binding(str(target), ref, third, first)
        conflict = push_once(runner, stale, stale)
        assert conflict.state == "conflict" and conflict.send_attempted is False

        # Model an uncertain previous acknowledgement without manufacturing an ACK.
        lost_ack = Outcome(request.digest(), "outcome_unknown", send_attempted=True)
        observed = reconcile(runner, request, lost_ack)
        assert observed.state == "observed_candidate" and observed.send_accepted is None
        assert push_calls == 1

        def summary(result: Outcome) -> dict:
            return {key: asdict(result)[key] for key in
                    ("state", "send_attempted", "send_accepted", "observation", "reason")}

        print(json.dumps({"scenario": "temporary local Git only", "network_used": False,
                          "fixture_approval_not_a_production_policy": True,
                          "update": summary(updated), "already_present": summary(already_present),
                          "stale_request": summary(conflict), "lost_ack_readback": summary(observed),
                          "common_runner_push_count": push_calls}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError) as error:
        # Do not print raw Git output that could contain a host path or credentials.
        raise SystemExit(f"Local example failed ({type(error).__name__}); no external repository used.")
