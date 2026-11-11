"""Regression checks for the public walkthrough, not remote-agent acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent

class WalkthroughTests(unittest.TestCase):
    def invoke(self, *args, env=None):
        return subprocess.run([sys.executable, *args, str(ROOT / 'examples/recovery_walkthrough.py'), '--json'],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)

    def test_four_real_git_cases(self):
        p = self.invoke()
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout)
        self.assertEqual([r['state'] for r in data['cases']],
                         ['updated', 'conflict', 'observed_candidate', 'observed_candidate'])
        self.assertEqual([r['pushes'] for r in data['cases']], [1, 0, 1, 0])
        self.assertIsNone(data['cases'][2]['send_accepted'])
        self.assertIsNone(data['cases'][3]['send_accepted'])
        self.assertFalse(data['remote_agent_started'])

    def test_checks_survive_python_optimization(self):
        p = self.invoke('-O')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(json.loads(p.stdout)['cases']), 4)

    def test_inherited_git_environment_is_not_used(self):
        env = dict(os.environ, GIT_DIR='/definitely/missing/git', GIT_WORK_TREE='/missing/work',
                   GIT_CONFIG_COUNT='invalid', GIT_CONFIG_GLOBAL='/missing/config')
        p = self.invoke(env=env)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_caller_cannot_select_a_repository(self):
        p = subprocess.run([sys.executable, str(ROOT / 'examples/recovery_walkthrough.py'),
                            '--repository', 'https://example.invalid/never'],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 2)
        self.assertIn('unrecognized arguments', p.stderr)

if __name__ == '__main__':
    unittest.main()
