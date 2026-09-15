"""Review regression tests: exercise real Git scopes without altering the caller's tree."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/bymax-codex/scripts/review_scope.py'


class ReviewScopeTests(unittest.TestCase):
    """Protect revision, staging, filename and untracked-file review boundaries."""

    def setUp(self):
        """Create an isolated repository with a nonstandard default branch."""
        self.temporary = tempfile.TemporaryDirectory(prefix='bymax-review-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init', '-b', 'trunk')
        self.git('config', 'user.name', 'Fixture User')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.write('app.txt', 'original\n')
        self.git('add', '.')
        self.git('commit', '-m', 'test: initial fixture')
        self.base = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        """Run fixture Git commands and retain stderr on failures."""
        return subprocess.run(['git', *args], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout

    def write(self, path, text):
        """Write a fixture file, including names with spaces and line breaks."""
        (self.root / path).write_text(text)

    def capture(self, *args, success=True):
        """Invoke the actual shipped CLI and parse its evidence or fail-closed error."""
        result = subprocess.run(['python3', str(SCRIPT), *args], cwd=self.root,
                                capture_output=True, text=True)
        if not success:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_working_scope_includes_untracked_without_staging(self):
        """New-file content and unusual paths remain in scope without index mutation."""
        self.write('app.txt', 'changed\n')
        self.write('new file\nname.txt', '++credential-example\n')
        index = (self.root / '.git/index').read_bytes()
        result = self.capture()
        self.assertEqual(result['mode'], 'uncommitted')
        self.assertEqual(result['untracked'][0]['path'], 'new file\nname.txt')
        self.assertIn('++credential-example', result['untracked'][0]['content'])
        self.assertEqual(index, (self.root / '.git/index').read_bytes())

    def test_staged_content_cannot_hide_behind_restored_worktree(self):
        """A staged risky line survives capture even if the worktree equals HEAD."""
        self.write('app.txt', 'staged-only-problem\n')
        self.git('add', 'app.txt')
        self.write('app.txt', 'original\n')
        result = self.capture()
        self.assertEqual(result['diff'], '')
        self.assertIn('staged-only-problem', result['staged_diff'])
        self.assertIn('app.txt', result['changed_files'])

    def test_explicit_other_branch_excludes_current_dirty_tree(self):
        """A branch review reads the requested commit, never the current dirty checkout."""
        self.git('switch', '-c', 'feature')
        self.write('app.txt', 'feature-content\n')
        self.git('commit', '-am', 'test: feature')
        feature = self.git('rev-parse', 'HEAD').strip()
        self.git('switch', 'trunk')
        self.write('app.txt', 'unrelated-dirty-content\n')
        result = self.capture('--mode', 'branch', '--base', 'trunk', '--head', 'feature')
        self.assertEqual(result['head'], feature)
        self.assertIn('feature-content', result['diff'])
        self.assertNotIn('unrelated-dirty-content', result['diff'])
        self.assertEqual(self.git('branch', '--show-current').strip(), 'trunk')

    def test_missing_base_and_invalid_ref_fail_closed(self):
        """A clean repository without upstream cannot become an empty clean review."""
        self.assertIn('comparison base', self.capture(success=False))
        self.assertIn('unavailable', self.capture('--mode', 'branch', '--base', 'missing', success=False))
        self.capture('--mode', 'branch', '--base=', success=False)
        self.capture('--base', 'trunk', success=False)

    def test_added_indicator_preserves_plus_prefixed_content(self):
        """Diff headers never match additions and content beginning with ++ is retained."""
        self.write('app.txt', '++console.log(example)\n')
        result = self.capture()
        self.assertEqual(result['added_lines'], ['++console.log(example)'])

    def test_literal_path_does_not_expand_as_a_git_pattern(self):
        """A literal filename containing brackets does not select other files."""
        self.write('[ab].txt', 'literal\n')
        self.write('a.txt', 'other\n')
        result = self.capture('--path', '[ab].txt')
        self.assertEqual([p['path'] for p in result['untracked']], ['[ab].txt'])
        self.capture('--path', '../outside', success=False)
        self.capture('--path', ':(exclude)*', success=False)

    def test_binary_and_external_symlink_are_not_read_as_text(self):
        """Binary evidence is hashed, and a symlink target outside the repo is not followed."""
        (self.root / 'binary').write_bytes(b'\x00binary')
        os.symlink('/path/that/does/not/exist', self.root / 'link')
        result = self.capture()
        entries = {p['path']: p for p in result['untracked']}
        self.assertTrue(entries['binary']['binary'])
        self.assertIsNone(entries['binary']['content'])
        self.assertTrue(entries['link']['symlink'])
        self.assertEqual(entries['link']['content'], '/path/that/does/not/exist')

    def test_fingerprint_changes_when_new_file_changes(self):
        """Freshness detects new-file edits as well as tracked diff changes."""
        self.write('new.txt', 'one\n')
        first = self.capture()['fingerprint']
        self.assertEqual(first, self.capture()['fingerprint'])
        self.write('new.txt', 'two\n')
        self.assertNotEqual(first, self.capture()['fingerprint'])

    def test_root_commit_and_unborn_repo(self):
        """First commits and staged files before HEAD exists still have a complete scope."""
        result = self.capture('--mode', 'commit', '--head', self.base)
        self.assertIn('original', result['diff'])
        self.git('checkout', '--orphan', 'unborn')
        result = self.capture('--mode', 'uncommitted')
        self.assertIsNone(result['checkout_head'])
        self.assertIn('original', result['staged_diff'])

    def test_endpoint_range_differs_from_merge_base_diff(self):
        """Two-dot endpoint scope does not silently become a three-dot branch scope."""
        self.git('switch', '-c', 'side')
        self.write('side.txt', 'side\n')
        self.git('add', '.')
        self.git('commit', '-m', 'test: side')
        self.git('switch', 'trunk')
        self.write('base.txt', 'base\n')
        self.git('add', '.')
        self.git('commit', '-m', 'test: base')
        branch = self.capture('--mode', 'branch', '--base', 'trunk', '--head', 'side')
        endpoint = self.capture('--mode', 'range', '--base', 'trunk', '--head', 'side')
        self.assertNotIn('base.txt', branch['changed_files'])
        self.assertIn('base.txt', endpoint['changed_files'])


    def test_non_utf8_changes_have_distinct_fingerprints(self):
        """Raw diff hashing detects byte changes even when display decoding is lossy."""
        (self.root / 'app.txt').write_bytes(b'\xff\n')
        first = self.capture()['fingerprint']
        (self.root / 'app.txt').write_bytes(b'\xfe\n')
        self.assertNotEqual(first, self.capture()['fingerprint'])

    def test_unmerged_working_scope_fails_closed(self):
        """Unresolved index stages cannot be reported as a complete working review."""
        self.git('switch', '-c', 'side')
        self.write('app.txt', 'side\n')
        self.git('commit', '-am', 'test: side conflict')
        self.git('switch', 'trunk')
        self.write('app.txt', 'trunk\n')
        self.git('commit', '-am', 'test: trunk conflict')
        result = subprocess.run(['git', 'merge', 'side'], cwd=self.root, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unmerged index entries', self.capture(success=False))


    def test_rename_retains_deleted_and_added_paths(self):
        """A configured rename detector cannot hide the deleted side from changed files."""
        self.git('config', 'diff.renames', 'true')
        self.git('mv', 'app.txt', 'renamed.txt')
        result = self.capture()
        self.assertEqual(result['changed_files'], ['app.txt', 'renamed.txt'])
