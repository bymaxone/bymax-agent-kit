"""Bundler regression tests: a renamed delimiter must fail loudly, never ship silently."""

import importlib.util
import os
import subprocess
import tempfile
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


    def fixture(self, inside_another_repo=False):
        """A tree with one shipped resource, optionally untracked inside another repo."""
        root = Path(tempfile.mkdtemp())
        if inside_another_repo:
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            root = root / 'unpacked-copy'
        (root / 'plugins/demo/commands').mkdir(parents=True)
        (root / 'plugins/demo/commands/thing.md').write_text('a shipped resource\n')
        return root

    def test_git_answering_with_nothing_is_not_an_answer(self):
        """`git ls-files plugins` exits 0 and prints nothing when the index has no plugins/
        entry while the directory is fully populated — an unpacked copy inside another repo,
        a re-inited checkout before the first add, a foreign GIT_DIR. Treating that as the
        canonical set makes it empty, and a write run then deletes every bundled file and
        reports success. Measured on the real package: 111 files under references/upstream
        before, 0 after, rc=0, 'verified: 0 canonical resources'."""
        module = bundler()
        module.ROOT = self.fixture(inside_another_repo=True)
        listing = subprocess.run(['git', '-C', str(module.ROOT), 'ls-files', '-z', 'plugins'],
                                 capture_output=True)
        self.assertEqual((listing.returncode, listing.stdout), (0, b''))  # the case must be the case
        with self.assertRaises(SystemExit):
            module.shipped()

    def test_git_that_cannot_run_is_reported_rather_than_raised(self):
        """The bundler depends on git now, so the absence of git is its own answer and must
        read as one instead of a FileNotFoundError from the middle of a helper."""
        module = bundler()
        module.ROOT = self.fixture()
        original = os.environ.get('PATH', '')
        os.environ['PATH'] = str(Path(tempfile.mkdtemp()))
        self.addCleanup(os.environ.__setitem__, 'PATH', original)
        with self.assertRaises(SystemExit):
            module.shipped()

    def test_a_carriage_return_in_a_tracked_name_survives_the_listing(self):
        """-z is asked for so a name is delimited by NUL and nothing else. Reading that
        stream with universal newlines rewrites a CR inside a name before the split, and the
        file it belongs to vanishes from the canonical set without a word."""
        module = bundler()
        root = self.fixture()
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        odd = root / 'plugins/demo/commands/carriage\rreturn.md'
        odd.write_text('also shipped\n')
        subprocess.run(['git', '-C', str(root), 'add', '-A'], check=True)
        module.ROOT = root
        self.assertIn(odd.resolve(), module.shipped())


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
