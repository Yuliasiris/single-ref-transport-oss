"""Disposable local bare repositories only; no network or production credentials."""
import dataclasses
import pathlib
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

import single_ref_transport as common


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="single-ref-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.remote = self.root / "remote.git"
        self.calls = []
        self.git("init", "--bare", str(self.remote))
        self.git("init")
        self.git("config", "user.name", "Synthetic fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.commits = []
        for value in ["A", "B", "C"]:
            (self.work / "synthetic.txt").write_text(value)
            self.git("add", "synthetic.txt")
            self.git("commit", "-m", value)
            self.commits.append(self.git("rev-parse", "HEAD"))
        self.a, self.b, self.c = self.commits
        self.ref = "refs/heads/target"
        self.git("push", str(self.remote), self.a + ":" + self.ref)
        self.binding = common.Binding(str(self.remote), self.ref, self.c, self.a)

    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.work, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode:
            raise AssertionError(r.stderr.decode(errors="replace"))
        return r.stdout.decode().strip()

    def git_runner(self, args, timeout):
        self.calls.append(list(args))
        return subprocess.run(["git", *args], cwd=self.work, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)

    def pushes(self):
        return [a for a in self.calls if a[0] == "push"]

    def test_forward_and_absent_only_with_real_server_cas(self):
        result = common.push_once(self.git_runner, self.binding, self.binding)
        self.assertEqual(result.state, "updated")
        self.assertTrue(result.send_accepted)
        self.assertEqual(result.observed_oid, self.c)
        self.assertIn("--force-with-lease=" + self.ref + ":" + self.a, self.pushes()[0])
        new = dataclasses.replace(self.binding, ref="refs/heads/new", expected_old=None)
        result = common.push_once(self.git_runner, new, new)
        self.assertEqual(result.state, "updated")
        self.assertIn("--force-with-lease=refs/heads/new:", self.pushes()[-1])

    def test_existing_target_cancellation_and_policy_expansion_do_not_send(self):
        same = dataclasses.replace(self.binding, candidate=self.a)
        self.assertEqual(common.push_once(self.git_runner, same, same).state, "observed_candidate")
        self.assertEqual(common.push_once(self.git_runner, self.binding, self.binding, cancelled=True).state, "cancelled")
        for changed in [dataclasses.replace(self.binding, ref="refs/heads/main"),
                        dataclasses.replace(self.binding, repository=str(self.root / "other.git")),
                        dataclasses.replace(self.binding, expected_old=None),
                        dataclasses.replace(self.binding, candidate=self.b)]:
            self.assertEqual(common.push_once(self.git_runner, changed, self.binding).state, "refused")
        self.assertEqual(self.pushes(), [])

    def test_unknown_is_not_absence_and_malformed_ref_is_not_success(self):
        failure = lambda args, timeout: SimpleNamespace(returncode=128, stdout=b"")
        self.assertIsNone(common.observe_ref(failure, str(self.remote), self.ref))
        self.assertEqual(common.push_once(failure, self.binding, self.binding).reason, "preflight_unknown")
        self.assertEqual(common.parse_exact_ref(b"", self.ref), ())
        self.assertIsNone(common.parse_exact_ref((self.a + "\trefs/heads/other\n").encode(), self.ref))
        self.assertIsNone(common.parse_exact_ref(((self.a + "\t" + self.ref + "\n") * 2).encode(), self.ref))

    def test_ancestor_drift_at_send_is_rejected_by_real_server(self):
        def racing(args, timeout):
            if args[0] == "push":
                self.git("push", str(self.remote), self.b + ":" + self.ref)
            return self.git_runner(args, timeout)
        result = common.push_once(racing, self.binding, self.binding)
        self.assertNotEqual(result.state, "updated")
        self.assertEqual(result.observed_oid, self.b)
        self.assertEqual(len(self.pushes()), 1)

    def test_absent_only_creation_race_does_not_overwrite(self):
        new = dataclasses.replace(self.binding, ref="refs/heads/new", expected_old=None)
        def racing(args, timeout):
            if args[0] == "push":
                self.git("push", str(self.remote), self.b + ":" + new.ref)
            return self.git_runner(args, timeout)
        result = common.push_once(racing, new, new)
        self.assertEqual(result.observed_oid, self.b)
        self.assertNotEqual(result.state, "updated")

    def test_rewind_refused_before_send(self):
        self.git("push", str(self.remote), self.c + ":" + self.ref)
        rewind = dataclasses.replace(self.binding, candidate=self.b, expected_old=self.c)
        self.assertEqual(common.push_once(self.git_runner, rewind, rewind).reason, "ancestry_not_proven")
        self.assertEqual(self.pushes(), [])

    def test_lost_response_after_real_update_is_observation_not_ack(self):
        def lost(args, timeout):
            result = self.git_runner(args, timeout)
            if args[0] == "push":
                self.assertEqual(result.returncode, 0)
                raise subprocess.TimeoutExpired("git", timeout)
            return result
        result = common.push_once(lost, self.binding, self.binding)
        self.assertEqual(result.state, "observed_candidate")
        self.assertIsNone(result.send_accepted)
        self.assertEqual(len(self.pushes()), 1)
        resumed = common.reconcile(self.git_runner, self.binding, result)
        self.assertEqual(resumed.state, "observed_candidate")
        self.assertEqual(len(self.pushes()), 1)
        changed = dataclasses.replace(self.binding, candidate=self.b)
        self.assertEqual(common.reconcile(self.git_runner, changed, result).state, "refused")

    def test_later_writer_with_and_without_ack(self):
        binding = dataclasses.replace(self.binding, candidate=self.b)
        for lost in [False, True]:
            # Independent destination, no remote history rewrite for test setup.
            ref = "refs/heads/later-" + str(lost).lower()
            current = dataclasses.replace(binding, ref=ref, expected_old=None)
            def advancing(args, timeout):
                result = self.git_runner(args, timeout)
                if args[0] == "push":
                    self.git("push", str(self.remote), self.c + ":" + ref)
                    if lost:
                        raise subprocess.TimeoutExpired("git", timeout)
                return result
            result = common.push_once(advancing, current, current)
            self.assertEqual(result.state, "observed_descendant" if lost else "advanced_after_ack")

    def test_unknown_readback_then_resume_never_resends(self):
        attempted = False
        def unavailable(args, timeout):
            nonlocal attempted
            if attempted and args[0] == "ls-remote":
                return SimpleNamespace(returncode=128, stdout=b"")
            result = self.git_runner(args, timeout)
            if args[0] == "push":
                attempted = True
            return result
        result = common.push_once(unavailable, self.binding, self.binding)
        self.assertEqual(result.state, "outcome_unknown")
        self.assertTrue(result.send_accepted)
        self.assertEqual(common.reconcile(self.git_runner, self.binding, result).state, "updated")
        self.assertEqual(len(self.pushes()), 1)

    def test_pre_push_hook_remains_enabled(self):
        hook = self.work / ".git" / "hooks" / "pre-push"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="ascii", newline="\n")
        hook.chmod(0o755)
        result = common.push_once(self.git_runner, self.binding, self.binding)
        self.assertNotEqual(result.state, "updated")
        self.assertEqual(result.observed_oid, self.a)
        self.assertNotIn("--no-verify", self.pushes()[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
