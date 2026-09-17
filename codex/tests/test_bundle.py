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
    """What belongs in the package, and what a wrong answer is allowed to cost.

    These cases were rewritten when the mechanism was. The bundler used to ask git which files
    the repository ships and derive the package from that answer. Every way that answer can be
    wrong makes the set SMALLER, and a set that is too small does not fail — it deletes the
    mirror and reports success: measured on this package at 111 files to 0, and 111 to 30. It
    now walks the disk, which is what the bundle mirrors, and asks git only which resources to
    leave out. A wrong answer there makes the set too LARGE, which is a diff somebody reads.

    So three cases that used to demand a refusal now demand correct output instead, and each
    says so where it stands.
    """

    def package(self, ignore=None):
        """A checkout-shaped fixture with two shipped resources under a bundled directory."""
        root = Path(tempfile.mkdtemp())
        (root / 'plugins/demo/commands').mkdir(parents=True)
        (root / 'plugins/demo/commands/one.md').write_text('shipped\n')
        (root / 'plugins/demo/commands/two.md').write_text('also shipped\n')
        if ignore:
            (root / '.gitignore').write_text(ignore + '\n')
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        subprocess.run(['git', '-C', str(root), 'add', '-A'], check=True)
        return root

    def names(self, module):
        """The package-relative resource names the bundler would ship."""
        return sorted(str(path.relative_to(module.ROOT / 'plugins')) for path in module.source_files())

    def test_a_resource_git_ignores_is_not_shipped(self):
        """The defect that started this: running the suite writes .pytest_cache under
        plugins/bymax-quality/scripts, and walking the disk made those four files canonical
        resources and four manifest entries. The manifest then verified on the machine that
        produced it and was stale in every clone, which is what CI reported. Ignored is the
        property that distinguishes them, and it is the only thing git is asked."""
        module = bundler()
        module.ROOT = self.package()
        stray = module.ROOT / 'plugins/demo/commands/.pytest_cache/nodeids'
        stray.parent.mkdir(parents=True)
        stray.write_text('what a local run leaves behind\n')
        # The shape this repository really has: pytest writes the marker, and until this round
        # nothing else excluded the cache. A fixture that put `.pytest_cache/` in the root
        # ignore file tested a rule the repository did not own.
        (stray.parent / '.gitignore').write_text('# Created by pytest automatically.\n*\n')
        self.assertTrue(stray.is_file())          # the case must be the case before it asserts
        self.assertEqual(self.names(module), ['demo/commands/one.md', 'demo/commands/two.md'])

    def test_the_index_vetoes_an_ignore_rule(self):
        """The one fact the inversion rests on, and the reason asking about ignores is safe at
        all: git check-ignore consults the index, so a TRACKED resource is never reported
        ignored however the patterns read. Without this the question could still remove shipped
        files and the redesign would only have moved the failure. Nothing in the suite noticed
        when the property was mutated away, which is how a design becomes unchangeable."""
        module = bundler()
        root = self.package()
        # The rule arrives AFTER the files are tracked, which is the only way to build the case
        # this names. Writing it first means git never adds them and they are untracked, so the
        # veto is never reached — which is what an earlier version of this fixture did.
        (root / '.gitignore').write_text('commands/\n')
        module.ROOT = root
        tracked = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', 'plugins'],
                                 capture_output=True).stdout
        self.assertIn(b'one.md', tracked)          # tracked, and matched by the rule above
        self.assertEqual(self.names(module), ['demo/commands/one.md', 'demo/commands/two.md'])

    def test_an_ignore_from_an_enclosing_repository_cannot_shrink_the_package(self):
        """Measured on the real package while this was open: a copy unpacked inside a
        repository whose .gitignore holds `templates/` gave 111 -> 85, exit 0, 'verified: 85',
        twenty-six mirror files deleted. The index that vetoes patterns is the enclosing one,
        which knows none of these paths, so every pattern applies. An answer from an index that
        does not describe this tree is not an answer about this package."""
        module = bundler()
        outer = Path(tempfile.mkdtemp())
        subprocess.run(['git', 'init', '-q', str(outer)], check=True)
        (outer / '.gitignore').write_text('commands/\n')
        inner = outer / 'unpacked-copy'
        (inner / 'plugins/demo/commands').mkdir(parents=True)
        (inner / 'plugins/demo/commands/one.md').write_text('shipped\n')
        module.ROOT = inner
        self.assertEqual(self.names(module), ['demo/commands/one.md'])

    def test_an_untracked_resource_is_still_shipped(self):
        """Expectation moved with the mechanism, and this is the direction that matters. Under
        the old mechanism an untracked file was absent from git's answer and silently left out
        of the package; a new resource added before its first commit would have shipped as a
        stale mirror. The disk decides what exists, so it ships, and only an ignore leaves it
        out."""
        module = bundler()
        module.ROOT = self.package()
        fresh = module.ROOT / 'plugins/demo/commands/three.md'
        fresh.write_text('added but not yet committed\n')
        self.assertIn('demo/commands/three.md', self.names(module))

    def test_a_partial_index_does_not_truncate_the_package(self):
        """Measured before the rewrite: a re-inited checkout with one subdirectory added took
        the real mirror from 111 files to 30, with exit 0 and 'verified: 30 canonical
        resources'. The index no longer decides what the package contains, so it cannot shrink
        it. This case used to demand a refusal; demanding the right answer is stronger."""
        module = bundler()
        root = self.package()
        subprocess.run(['rm', '-rf', str(root / '.git')], check=True)
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        module.ROOT = root
        self.assertEqual(self.names(module), ['demo/commands/one.md', 'demo/commands/two.md'])

    def test_a_copy_inside_another_repository_still_ships_what_it_holds(self):
        """The shape that deleted the whole mirror: `git ls-files plugins` exits 0 and prints
        nothing when the index that answers belongs to an enclosing repository. Measured at
        111 files to 0 with 'verified: 0 canonical resources'. Nothing here reads that index
        for the set any more, and an unpacked copy holds a complete package on disk."""
        module = bundler()
        outer = Path(tempfile.mkdtemp())
        subprocess.run(['git', 'init', '-q', str(outer)], check=True)
        inner = outer / 'unpacked-copy'
        (inner / 'plugins/demo/commands').mkdir(parents=True)
        (inner / 'plugins/demo/commands/one.md').write_text('shipped\n')
        module.ROOT = inner
        self.assertEqual(self.names(module), ['demo/commands/one.md'])

    def test_a_carriage_return_in_a_name_survives(self):
        """-z is asked for so a name is delimited by NUL and nothing else, and reading that
        stream with universal newlines rewrites a CR inside a name before the split.

        The file must be UNTRACKED for this to mean anything. A tracked path is vetoed by the
        index before any pattern is consulted, so an earlier version of this case added the
        file and asserted a property it could never reach: reintroducing the exact mangling it
        names left the whole suite green.
        """
        module = bundler()
        root = self.package(ignore='ignored-entirely.md')
        odd = root / 'plugins/demo/commands/carriage\rreturn.md'
        odd.write_text('shipped, and never added\n')
        module.ROOT = root
        self.assertEqual(subprocess.run(['git', '-C', str(root), 'ls-files', '--error-unmatch',
                                         str(odd.relative_to(root))], capture_output=True).returncode,
                         1)                       # untracked, so the ignore answer decides it
        self.assertIn('demo/commands/carriage\rreturn.md', self.names(module))

    def test_git_that_cannot_run_is_reported_rather_than_raised(self):
        """git is consulted for the ignore list, so its absence is an answer the bundler must
        give in its own words instead of a FileNotFoundError from inside a helper."""
        module = bundler()
        module.ROOT = self.package()
        original = os.environ.get('PATH', '')
        os.environ['PATH'] = str(Path(tempfile.mkdtemp()))
        self.addCleanup(os.environ.__setitem__, 'PATH', original)
        with self.assertRaises(SystemExit):
            module.source_files()

    def test_plugins_that_is_not_a_directory_is_refused(self):
        """rglob over a missing directory yields nothing rather than raising, so an incomplete
        checkout used to produce an empty set and delete the mirror while printing verified."""
        module = bundler()
        root = self.package()
        subprocess.run(['rm', '-rf', str(root / 'plugins')], check=True)
        module.ROOT = root
        with self.assertRaises(SystemExit):
            module.source_files()

    def test_an_empty_canonical_set_is_never_a_package(self):
        """The one guard this mechanism still needs: nothing above can make the set smaller
        than the disk, so an empty set means the resources are not there to read — and
        synchronising against it would delete every file in the mirror."""
        module = bundler()
        root = self.package()
        subprocess.run(['rm', '-rf', str(root / 'plugins/demo/commands')], check=True)
        module.ROOT = root
        with self.assertRaises(SystemExit):
            module.expected_files()

    def test_a_healthy_checkout_still_bundles(self):
        """The guards must not refuse the case they exist to protect."""
        module = bundler()
        module.ROOT = self.package()
        self.assertEqual(sorted(str(p) for p in module.expected_files()),
                         ['demo/commands/one.md', 'demo/commands/two.md'])


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
