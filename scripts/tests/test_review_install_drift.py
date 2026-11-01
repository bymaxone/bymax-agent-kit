"""Regression layer: a campaign started in a checkout of this toolkit says when the installed
runtime is not the one the checkout ships.

A merged fix stayed absent from the installed copy, and a hand patch to the installed copy was
never carried back; nothing said so until an audit diffed them.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FLOW, FlowBench


class DriftTests(FlowBench):
    """What start prints about the runtime it is, against the checkout it runs in."""

    def ship(self, change=None):
        """Put this runtime's own scripts in the fixture's base where the toolkit keeps them, so
        the candidate under review is the fixture's ordinary one-file change."""
        shipped = self.repo / 'plugins/bymax-quality/scripts'
        shutil.copytree(FLOW.parent, shipped, ignore=shutil.ignore_patterns('__pycache__'))
        if change:
            (shipped / change).write_text((shipped / change).read_text() + '\n# shipped since\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'ship the runtime')
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('the candidate after the runtime shipped')

    def start_stderr(self):
        """start in the fixture, returning what it printed beside the state."""
        run = subprocess.run([sys.executable, str(FLOW), 'start', '--base', self.base, '--context',
                              str(self.context)], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return run.stderr

    def test_a_runtime_behind_the_checkout_names_the_file_and_the_remedy(self):
        """The file that differs is named, with the command that installs the checkout's copy,
        and the campaign starts anyway."""
        self.ship(change='review_rebase.py')
        printed = self.start_stderr()
        self.assertIn('differs from this checkout in review_rebase.py', printed)
        self.assertIn('install-review-flow.py', printed)

    def test_a_runtime_matching_the_checkout_says_nothing(self):
        """No drift, no notice."""
        self.ship()
        self.assertNotIn('installed review runtime differs', self.start_stderr())


if __name__ == '__main__':
    unittest.main()
