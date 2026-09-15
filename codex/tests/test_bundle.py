"""Bundler regression tests: a renamed delimiter must fail loudly, never ship silently."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = ROOT / 'codex/plugins/bymax-codex/references/review-checklist.md'


def bundler():
    """Import the bundler by path without running its command-line entrypoint."""
    spec = importlib.util.spec_from_file_location('bundle', ROOT / 'codex/scripts/bundle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BundleSectionTests(unittest.TestCase):
    """Protect the extraction that keeps Claude campaign machinery out of the package."""

    def test_absent_delimiter_fails_instead_of_returning_the_whole_body(self):
        """str.split yields the entire string when its separator is gone, excluding nothing."""
        module = bundler()
        source = 'intro\n## Start\nkept\n## Stop\nexcluded\n'
        self.assertEqual(module.section(source, '## Start', '## Stop'), '\nkept\n')
        for start, stop in (('## Absent', '## Stop'), ('## Start', '## Absent')):
            with self.assertRaises(SystemExit):
                module.section(source, start, stop)

    def test_shipped_checklist_omits_the_claude_campaign_step(self):
        """Codex has no campaign helper and creates no Claude receipt, so it must not be told to."""
        text = CHECKLIST.read_text()
        self.assertIn('## Step 2 — Mechanical gate (deterministic)', text)
        self.assertIn('## Step 5 — Verify before reporting', text)
        self.assertNotIn('## Step 5.5', text)
        for machinery in ('review-protocol.md', 'REVIEW COMPLETE', 'cleared: true'):
            self.assertNotIn(machinery, text)


if __name__ == '__main__':
    unittest.main()
