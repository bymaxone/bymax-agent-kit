"""The prose pass as the review runtime runs it: a fresh reader corrects a committed
candidate's prose, the envelope decides whether what it left is prose, and start() holds the
candidate to a record bound to its own text. Driven through the CLI in a fixture repository."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

# The bench is test_review_flow's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_flow import FlowBench


class ProsePassTests(FlowBench):
    """What the prose pass records, what it refuses, and what start() then demands."""

    PROSE = ('LIMIT = 10\n'
             '# Six attempts at this rule, and it guards the limit.\n'
             'def over(value):\n'
             '    """Whether value exceeds the limit."""\n'
             '    return value > LIMIT\n')
    CORRECTED = '# Guards the limit because callers pass unbounded input.'

    def fake_claude(self, edit):
        """A stand-in `claude` on $PATH that ignores its task and applies one edit to thing.py."""
        binary_dir = self.root / 'claude-bin'
        binary_dir.mkdir(exist_ok=True)
        binary = binary_dir / 'claude'
        binary.write_text('#!/bin/sh\ncat > /dev/null\n%s - <<\'EOF\'\nfrom pathlib import Path\n'
                          'p = Path("thing.py"); p.write_text(p.read_text().replace(%r, %r))\nEOF\n'
                          'echo \'{"is_error": false}\'\n' % (sys.executable, *edit))
        binary.chmod(0o755)
        return binary_dir

    def add_prose(self, text=None):
        (self.repo / 'thing.py').write_text(text or self.PROSE)
        self.git('add', '-A')
        self.git('commit', '-qm', 'a candidate that adds prose')

    def test_the_prose_pass_refuses_a_dirty_worktree(self):
        """The envelope compares the worktree to HEAD, so with the author's own edits in the
        tree the pass's edits would be indistinguishable from them."""
        (self.repo / 'thing.py').write_text(self.PROSE)
        self.assertIn('worktree is dirty', self.prose('--base', self.base, ok=False).stderr)

    def test_a_delta_that_adds_no_prose_records_a_skipped_pass_and_needs_none(self):
        self.commit('code only')
        record = self.prose('--base', self.base)
        self.assertEqual(record['outcome'], 'skipped')
        self.start()
        self.checks()
        self.assertIn('added no prose, so no prose pass ran', self.flow('prompt').stdout)

    def test_the_prose_pass_records_what_a_correcting_reader_left(self):
        """The whole mechanism end to end: a fresh Claude corrects a comment, the envelope
        holds, the record binds to the text it left, and the candidate carrying that text
        starts with a brief telling the logic reviewers wording is not theirs."""
        self.add_prose()
        record = self.prose('--base', self.base, claude=self.fake_claude(
            ('# Six attempts at this rule, and it guards the limit.', self.CORRECTED)))
        self.assertEqual((record['outcome'], record['changed'], record['files']),
                         ('corrected', ['thing.py'], ['thing.py']))
        self.assertIn(self.CORRECTED, (self.repo / 'thing.py').read_text())
        self.git('commit', '-qam', 'prose corrected before the freeze')
        self.assertEqual(self.start()['prose']['outcome'], 'corrected')
        self.checks()
        brief = self.flow('prompt').stdout
        # What the record proves, not more: the runtime never observes the reader, so the
        # note may not say 'a fresh reader corrected', a reading it cannot show.
        self.assertIn('The prose pass ran before the freeze', brief)
        self.assertIn('the record proves the text and not the reading', brief)
        self.assertIn('Wording is still not yours to review', brief)

    def test_a_pass_that_edits_code_is_refused_and_touches_nothing(self):
        """The one outcome worse than the defect: reviewers are told the pass touched no
        behaviour. Refused, with no record — and the tree left exactly as the reader left it,
        because putting it back can destroy what a git listing hides, and the author can
        see what is theirs where the runtime cannot."""
        self.add_prose()
        refused = self.prose('--base', self.base, ok=False,
                             claude=self.fake_claude(('value > LIMIT', 'value >= LIMIT')))
        self.assertIn('left the envelope', refused.stderr)
        self.assertIn('behaviour changed', refused.stderr)
        self.assertIn('nothing was put back', refused.stderr)
        self.assertIn('value >= LIMIT', (self.repo / 'thing.py').read_text())
        self.assertEqual(list((self.repo / '.git').glob('bymax-review/*/prose-*.json')), [])

    def test_a_candidate_that_deletes_or_renames_a_file_binds_what_it_still_has(self):
        """Without renames a deletion and a rename's old side are touched paths the candidate
        no longer has; a record that digested them could never be written, so start refused
        every such candidate. The record binds the touched files that exist."""
        (self.repo / 'gone.py').write_text('G = 1\n')
        (self.repo / 'moved.md').write_text('# Moved\n\nA note.\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'files this candidate removes')
        self.base = self.git('rev-parse', 'HEAD')
        self.git('rm', '-q', 'gone.py')
        self.git('mv', 'moved.md', 'renamed.md')
        self.add_prose()
        self.assertEqual(self.read_prose()['files'], ['renamed.md', 'thing.py'])
        self.assertEqual(self.start()['round'], 1)

    def test_start_refuses_a_candidate_whose_prose_no_pass_read(self):
        self.add_prose()
        self.assertIn('no prose pass read it', self.start(ok=False).stderr)

    def test_start_refuses_a_record_bound_to_other_text(self):
        """The author edits the prose again after the pass: the record's digest no longer
        matches the candidate, so what the reviewers would be handed was never read."""
        self.add_prose()
        self.prose('--base', self.base, claude=self.fake_claude(
            ('# Six attempts at this rule, and it guards the limit.', self.CORRECTED)))
        self.git('commit', '-qam', 'prose corrected')
        (self.repo / 'thing.py').write_text(self.PROSE.replace('Six attempts', 'Seven attempts'))
        self.git('commit', '-qam', 'and then edited again by hand')
        self.assertIn('bound to other text', self.start(ok=False).stderr)

    def test_inside_claude_the_pass_prepares_and_verifies_in_two_stages(self):
        """A Claude cannot start a Claude, so inside one the runtime hands the task out and
        checks what came back, and the record is the same either way."""
        self.add_prose()
        self.assertIn('Inside Claude', self.prose('--base', self.base, nested=True, ok=False).stderr)
        task = self.prose('--base', self.base, '--stage', 'prepare', nested=True).stdout
        self.assertIn('Keep every sentence that says WHY', task)
        self.assertIn('--- thing.py', task)
        (self.repo / 'thing.py').write_text(self.PROSE.replace(
            '# Six attempts at this rule, and it guards the limit.', self.CORRECTED))
        record = self.prose('--base', self.base, '--stage', 'verify', nested=True)
        self.assertEqual(record['outcome'], 'corrected')
        self.git('commit', '-qam', 'prose corrected by a subagent')
        self.assertEqual(self.start()['round'], 1)

    def test_verify_without_a_prepare_at_this_head_is_refused(self):
        """Without the marker, verify on a dirty tree would bless the author's own edits as
        a pass that changed only prose."""
        self.add_prose()
        (self.repo / 'thing.py').write_text(self.PROSE.replace('Six attempts', 'Seven attempts'))
        refused = self.prose('--stage', 'verify', nested=True, ok=False).stderr
        self.assertIn('Nothing was prepared', refused)
        # The remedy says what the marker proves and nothing about who edited since.
        self.assertIn('proves the tree was clean when the task was handed out', refused)

    def test_start_refuses_a_record_that_covers_other_files(self):
        """The record digested the files the pass saw,
        so prose committed afterwards in a file outside that set reached the reviewers under
        a note saying a reader had seen it. The candidate's own touched set must be the
        record's."""
        self.add_prose()
        self.read_prose()
        (self.repo / 'NOTES.md').write_text('# Notes\n\nover() never returns for negative input.\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'prose in a file no reader saw')
        self.assertIn('in these files', self.start(ok=False).stderr)

    def test_after_a_cleared_campaign_the_pass_reads_from_the_given_base(self):
        """start treats a cleared, non-autonomous campaign as no campaign and opens a first
        round from the merge-base; the pass read from the cleared head instead, so the
        record's base never matched and start's own remedy looped."""
        self.start()
        self.complete()
        self.flow('finish')
        self.add_prose()
        record = self.read_prose()
        self.assertEqual(record['base'], self.base)
        self.assertEqual(self.start()['round'], 1)

    def test_a_refusal_leaves_the_tree_as_the_reader_left_it(self):
        """A staged edit, a staged addition and an untracked directory, all still there after
        the refusal, and no record: the runtime writes to the tree through nothing."""
        self.add_prose()
        self.prose('--base', self.base, '--stage', 'prepare', nested=True)
        (self.repo / 'thing.py').write_text(self.PROSE.replace('value > LIMIT', 'value >= LIMIT'))
        (self.repo / 'NEW.py').write_text('X = 1\n')
        self.git('add', 'thing.py', 'NEW.py')
        (self.repo / 'newdir').mkdir()
        (self.repo / 'newdir/x.md').write_text('# x\n')
        before = self.git('status', '--porcelain', '--untracked-files=all')
        refused = self.prose('--stage', 'verify', nested=True, ok=False).stderr
        self.assertIn('left the envelope', refused)
        self.assertIn('nothing was put back', refused)
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=all'), before)
        # Only prepare's own marker exists; nothing says the pass produced a candidate.
        records = [json.loads(p.read_text())['outcome'] for p in (self.repo / '.git').glob('bymax-review/*/prose-*.json')]
        self.assertEqual(records, ['prepared'])
        self.assertIn('worktree is dirty', self.prose('--stage', 'prepare', nested=True, ok=False).stderr)

    def test_a_reader_that_fails_leaves_its_edits_and_says_so(self):
        """A reader that edited code and then exited non-zero: the failure names the log and
        says the tree holds what the reader left; the edit is there, and no record."""
        self.add_prose()
        binary_dir = self.fake_claude(('value > LIMIT', 'value >= LIMIT'))
        script = (binary_dir / 'claude').read_text().replace('echo \'{"is_error": false}\'', 'exit 1')
        (binary_dir / 'claude').write_text(script)
        refused = self.prose('--base', self.base, ok=False, claude=binary_dir)
        self.assertIn('The prose pass failed', refused.stderr)
        self.assertIn('nothing was put back', refused.stderr)
        self.assertIn('value >= LIMIT', (self.repo / 'thing.py').read_text())
        self.assertEqual(list((self.repo / '.git').glob('bymax-review/*/prose-*.json')), [])

    def test_a_hidden_untracked_file_makes_the_tree_dirty(self):
        """status.showUntrackedFiles=no hides untracked files from a plain listing, so a pass
        could begin on the author's draft. The precondition asks for every untracked file."""
        self.add_prose()
        self.git('config', 'status.showUntrackedFiles', 'no')
        (self.repo / 'draft.py').write_text('draft = 1\n')
        refused = self.prose('--base', self.base, '--stage', 'prepare', nested=True, ok=False)
        self.assertIn('worktree is dirty', refused.stderr)
        self.assertTrue((self.repo / 'draft.py').exists())

    def test_an_edit_inside_an_ignored_submodule_is_seen(self):
        """submodule.<name>.ignore hid a reader's code edit inside a submodule from the listing,
        and the pass was recorded as inside the envelope. Seen and refused — and, like
        everything else, left where it is."""
        sub = self.root / 'sub-origin'
        subprocess.run(['git', 'init', '-q', str(sub)], check=True)
        (sub / 's.txt').write_text('s\n')
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A', 'commit', '-qm', 's']):
            subprocess.run(['git', '-C', str(sub), *args], check=True)
        self.git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(sub), 'sub')
        self.git('config', '-f', '.gitmodules', 'submodule.sub.ignore', 'dirty')
        self.git('add', '-A')
        self.git('commit', '-qm', 'ignore the submodule')
        self.add_prose()
        self.prose('--base', self.base, '--stage', 'prepare', nested=True)
        (self.repo / 'sub/s.txt').write_text('READER EDITED CODE\n')
        self.assertIn('left the envelope', self.prose('--stage', 'verify', nested=True, ok=False).stderr)
        self.assertEqual((self.repo / 'sub/s.txt').read_text(), 'READER EDITED CODE\n')

    def test_an_assume_unchanged_edit_makes_the_tree_dirty(self):
        """The clean gate asks the envelope's own listing: an author's edit under the
        assume-unchanged bit is invisible to git status and would start a pass."""
        self.add_prose()
        self.git('update-index', '--assume-unchanged', 'thing.py')
        (self.repo / 'thing.py').write_text(self.PROSE + 'LOCAL = True\n')
        self.assertIn('worktree is dirty', self.prose('--base', self.base, '--stage', 'prepare', nested=True, ok=False).stderr)

    def test_the_clean_gate_and_the_envelope_list_alike(self):
        """An author's edit inside an ignore=dirty submodule: the envelope saw it and the clean
        gate did not, so prepare admitted the tree and verify blamed a reader that edited
        nothing. One listing for both."""
        sub = self.root / 'sub-origin'
        subprocess.run(['git', 'init', '-q', str(sub)], check=True)
        (sub / 's.txt').write_text('s\n')
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A', 'commit', '-qm', 's']):
            subprocess.run(['git', '-C', str(sub), *args], check=True)
        self.git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(sub), 'sub')
        self.git('config', '-f', '.gitmodules', 'submodule.sub.ignore', 'dirty')
        self.git('add', '-A')
        self.git('commit', '-qm', 'ignore the submodule')
        self.add_prose()
        (self.repo / 'sub/s.txt').write_text('THE AUTHOR IS WORKING HERE\n')
        self.assertIn('worktree is dirty', self.prose('--base', self.base, '--stage', 'prepare', nested=True, ok=False).stderr)

    def test_an_ignored_file_created_between_prepare_and_verify_is_refused(self):
        """prepare records the ignored files present; verify names one that appeared. One that
        was there before is not the reader's and is not refused."""
        (self.repo / '.gitignore').write_text('*.env\n')
        self.git('add', '.gitignore')
        self.git('commit', '-qm', 'ignore env files')
        (self.repo / 'old.env').write_text('old\n')
        self.add_prose()
        self.prose('--base', self.base, '--stage', 'prepare', nested=True)
        (self.repo / 'new.env').write_text('new\n')
        refused = self.prose('--stage', 'verify', nested=True, ok=False).stderr
        self.assertIn('new.env is ignored and new', refused)
        self.assertNotIn('old.env', refused)

    def test_a_marker_without_a_snapshot_compares_nothing(self):
        """A marker the previous runtime wrote carries no ignored snapshot; an empty default
        made every ignored file that predates the pass a new one."""
        (self.repo / '.gitignore').write_text('*.env\n')
        self.git('add', '.gitignore')
        self.git('commit', '-qm', 'ignore env files')
        (self.repo / 'old.env').write_text('old\n')
        self.add_prose()
        self.prose('--base', self.base, '--stage', 'prepare', nested=True)
        marker = next((self.repo / '.git').glob('bymax-review/*/prose-*.json'))
        kept = json.loads(marker.read_text()); kept.pop('ignored'); marker.write_text(json.dumps(kept))
        self.assertEqual(self.prose('--stage', 'verify', nested=True)['outcome'], 'unchanged')

    def test_a_correction_round_reads_prose_since_the_frozen_head(self):
        """No --base once a campaign is frozen: the delta is what changed since that head.
        And on the frozen head itself the pass refuses, because editing what reviewers were
        handed invalidates their reading rather than improving it."""
        self.start()
        self.report('claude')
        self.report('codex')
        self.triage()
        frozen = self.git('rev-parse', 'HEAD')
        self.assertIn('frozen under review', self.prose(ok=False).stderr)
        self.add_prose()
        record = self.prose('--stage', 'prepare', nested=True)
        self.assertIn('--- thing.py', record.stdout)
        self.assertEqual(self.prose('--stage', 'verify', nested=True)['base'], frozen)

    def test_the_matrix_runs_before_the_first_start(self):
        """Round one has no campaign to read, and the documents say commit, matrix, start:
        the measurement the author takes on the first candidate must not be refused with
        "No review campaign", which is true and not what was wrong."""
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_first.py').write_text('from values import ONE\ndef test_first(): assert ONE == 1\n')
        self.commit('a first candidate with a test')
        run = self.matrix('tests/test_first.py', [('ONE = 1', 'ONE = 2', 'test_first')],
                          where='values.py', enumeration='echo 1')
        self.assertIn('1 mutant(s), all caught', run.stdout)
        head = self.git('rev-parse', 'HEAD')
        self.assertTrue(list((self.repo / '.git').glob('bymax-review/*/matrix-%s.json' % head)))
        self.assertEqual(self.start()['round'], 1)


if __name__ == '__main__':
    unittest.main()
