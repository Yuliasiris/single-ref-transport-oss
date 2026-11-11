"""A local-only, credential-free walkthrough of an uncertain Git push.

Run from a source checkout with Python 3.10+ and Git. Temporary repositories are
removed afterwards. No user-selected repository, account, or endpoint is used.
The lost acknowledgement is injected AFTER a real local Git push succeeds.
This is a transport example, not a running AI agent or persistent scheduler.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from single_ref_transport import Binding, Outcome, push_once, reconcile


def run_walkthrough() -> list[dict]:
    git_executable = shutil.which("git")
    if not git_executable:
        raise RuntimeError("Git is required; install it before running this example.")
    rows = []
    with tempfile.TemporaryDirectory(prefix="single-ref-guide-") as directory:
        root = Path(directory)
        work, remote, hooks = root / "work", root / "remote.git", root / "empty-hooks"
        hooks.mkdir()
        # Do not inherit a caller's repository, hooks, signing, or Git config.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="file")
        prefix = [git_executable, "-c", f"core.hooksPath={hooks}",
                  "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false"]

        def git(args, timeout=30, cwd=None, check=False):
            return subprocess.run(prefix + list(args), cwd=cwd or work, env=env,
                                  capture_output=True, timeout=timeout, check=check)

        git(["init", "--bare", "--object-format=sha1", str(remote)], cwd=root, check=True)
        git(["init", "-b", "main", "--object-format=sha1", str(work)], cwd=root, check=True)
        git(["config", "user.name", "Local example"], check=True)
        git(["config", "user.email", "example@example.invalid"], check=True)

        def commit(text):
            (work / "result.txt").write_text(text, encoding="utf-8")
            git(["add", "result.txt"], check=True)
            git(["commit", "-m", text], check=True)
            return git(["rev-parse", "HEAD"], check=True).stdout.decode().strip()

        initial = commit("original")
        git(["push", str(remote), initial + ":refs/heads/main"], check=True)
        candidate = commit("candidate")
        later = commit("later candidate")
        attempts = 0

        def runner(argv, timeout):
            nonlocal attempts
            if argv[0] == "push":
                attempts += 1
            return git(argv, timeout)

        # Separate trusted host decision, not an untrusted request approving itself.
        approved = Binding(str(remote), "refs/heads/main", candidate, initial)
        request = Binding(str(remote), "refs/heads/main", candidate, initial)
        normal = push_once(runner, request, approved)
        if normal.state != "updated" or attempts != 1:
            raise AssertionError("Expected one acknowledged local update.")
        rows.append({"case": "normal", "state": normal.state, "pushes": attempts})

        attempts = 0
        stale = Binding(str(remote), "refs/heads/main", later, initial)
        stale_approval = Binding(str(remote), "refs/heads/main", later, initial)
        conflict = push_once(runner, stale, stale_approval)
        if conflict.state != "conflict" or attempts != 0:
            raise AssertionError("A stale preimage must not send.")
        rows.append({"case": "stale preimage", "state": conflict.state, "pushes": attempts})

        attempts = 0
        def lost_ack_runner(argv, timeout):
            result = runner(argv, timeout)
            if argv[0] == "push" and result.returncode == 0:
                raise TimeoutError("Injected acknowledgement loss after the real local push.")
            return result

        second = Binding(str(remote), "refs/heads/main", later, candidate)
        second_approval = Binding(str(remote), "refs/heads/main", later, candidate)
        uncertain = push_once(lost_ack_runner, second, second_approval)
        if uncertain.state != "observed_candidate" or uncertain.send_accepted is not None or attempts != 1:
            raise AssertionError("Readback must not invent an acknowledgement.")
        rows.append({"case": "injected lost ack", "state": uncertain.state,
                     "pushes": attempts, "send_accepted": uncertain.send_accepted})

        receipt = root / "receipt.json"
        receipt.write_text(json.dumps({"binding": asdict(second), "outcome": asdict(uncertain)}), encoding="utf-8")
        # A different process reads the stored result. Its runner cannot push.
        recovery = r'''
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from single_ref_transport import Binding, Outcome, reconcile
record = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
commands = []
def read_only(argv, timeout):
    if argv[0] not in ("ls-remote", "merge-base"):
        raise RuntimeError("Recovery cannot send")
    commands.append(argv[0])
    return subprocess.run([sys.argv[4], "-c", "core.hooksPath=" + sys.argv[5]] + list(argv),
                          cwd=sys.argv[3], capture_output=True, timeout=timeout)
result = reconcile(read_only, Binding(**record["binding"]), Outcome(**record["outcome"]))
print(json.dumps({"state": result.state, "send_accepted": result.send_accepted, "commands": commands}))
'''
        completed = subprocess.run([sys.executable, "-c", recovery, str(SOURCE), str(receipt),
                                    str(work), git_executable, str(hooks)],
                                   env=env, capture_output=True, text=True, timeout=30, check=True)
        recovered = json.loads(completed.stdout)
        if recovered["state"] != "observed_candidate" or recovered["send_accepted"] is not None or "push" in recovered["commands"]:
            raise AssertionError("Separate-process recovery must only observe.")
        rows.append({"case": "separate-process readback", **recovered, "pushes": 0})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a machine-readable local demonstration result")
    args = parser.parse_args()
    try:
        rows = run_walkthrough()
    except (OSError, RuntimeError, AssertionError, subprocess.SubprocessError) as error:
        print(f"Walkthrough failed: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"kind": "local_git_walkthrough", "cases": rows,
                          "network_requests": 0, "remote_agent_started": False}, indent=2))
    else:
        for row in rows:
            print(f"{row['case']}: {row['state']}; push attempts = {row['pushes']}")
        print("Readback proves what is present, not which caller sent it. No blind resend.")
        print("All repositories were temporary and local. No real AI agent was started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
