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


class ShippedResourceTests(unittest.TestCase):
    """The canonical set is what the repository ships, not what the disk happens to hold."""

    def test_an_untracked_file_under_plugins_is_not_a_canonical_resource(self):
        """Running the suite here writes .pytest_cache under plugins/bymax-quality/scripts.
        Walking the working tree made those four files canonical resources and four manifest
        entries, so the bundle verified on the machine that produced it and was stale in
        every clone — which is exactly what CI reported. The set must come from git."""
        module = bundler()
        stray = ROOT / 'plugins/bymax-quality/scripts/.bundle-regression-probe/nodeids'
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text('what a local run leaves behind\n')
        self.addCleanup(lambda: (stray.unlink(missing_ok=True),
                                 stray.parent.rmdir() if stray.parent.is_dir() else None))
        self.assertTrue(stray.is_file())          # the case must be the case before it asserts

        # The behavioural assertion comes first, so this fails on what the bundler DOES
        # rather than on a helper it does not have yet.
        canonical = {path.resolve() for path in module.source_files()}
        self.assertNotIn(stray.resolve(), canonical)

        # And a file the repository really does ship is still in the set.
        tracked = ROOT / 'plugins/bymax-quality/scripts/review_flow.py'
        self.assertIn(tracked.resolve(), canonical)


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
