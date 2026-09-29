"""Read one explicitly selected ref. Never pushes; uses the user's Git environment."""
from pathlib import Path
import json
import os
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from single_ref_transport import observe_ref

def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: python examples/observe.py REPOSITORY refs/heads/BRANCH")
    repository, ref = sys.argv[1:]
    if not repository or repository.startswith("-") or not ref.startswith("refs/heads/"):
        raise SystemExit("an explicit repository and branch ref are required")
    def run(args, timeout):
        return subprocess.run(["git", *args], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0",
                                   "GIT_NO_REPLACE_OBJECTS": "1"}, timeout=timeout)
    result = observe_ref(run, repository, ref)
    print(json.dumps({"state": "unknown" if result is None else "present" if result else "absent",
                      "oids": result, "send_attempted": False}))
    return 2 if result is None else 0

if __name__ == "__main__":
    raise SystemExit(main())
