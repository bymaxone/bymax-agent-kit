"""Gate layer for the standup skill's shell block: how it claims the arguments another turn
wrote, and what it refuses.

The block is run as the model runs it, from SKILL.md, in a fake HOME, so each case pins what the
shell does rather than what the document says it does.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest

# The bench is test_report_collect's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_report_collect import ROOT, CollectBench, isolated


class SkillBlockTests(CollectBench):
    """The block, from the arguments file through the collect."""

    def skill_block(self):
        text = (ROOT / 'plugins/bymax-report/skills/standup/SKILL.md').read_text()
        import re
        return re.search(r'```bash\n(.*?)```', text, re.S).group(1)

    ARGS_DIR = '.claude/bymax-report-args.d'

    def run_block(self, home, args_lines, tmpdir=None, plugin=None, path=None, name='2026-09-22T09-05-01-k7qz3f', extra=None,
                  nonfile=None):
        home.mkdir(parents=True, exist_ok=True)
        waiting = home / self.ARGS_DIR
        if args_lines is not None:
            waiting.mkdir(parents=True, exist_ok=True)
            (waiting / name).write_text('\n'.join(args_lines) + '\n')
        if extra is not None:
            waiting.mkdir(parents=True, exist_ok=True)
            (waiting / extra).write_text('last-week\n/somewhere/else\n\n')
        # Everything above writes a regular file, which is the one shape `[ ! -f ]` never
        # objects to; a directory left in the waiting place is what tells the two guards
        # apart, so a case that needs one asks for it here.
        if nonfile is not None:
            (waiting / nonfile).mkdir(parents=True, exist_ok=True)
        env = {**isolated(), 'HOME': str(home), 'TMPDIR': tmpdir or str(home / 'tmp'),
               'CLAUDE_PLUGIN_ROOT': str(plugin or ROOT / 'plugins/bymax-report')}
        if path:
            env['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
        (home / 'tmp').mkdir(exist_ok=True)
        return subprocess.run(['bash', '-c', self.skill_block()], cwd=str(self.repo), env=env,
                              capture_output=True, text=True)

    def test_the_skill_block_claims_the_arguments_before_it_reads_them(self):
        """The arguments wait in a directory both runs can write to, so reading a file in place
        left a window where a second run could overwrite it between the first run's reads, mixing
        one run's period with another's repository. The block claims it with a rename first, which
        is atomic, and reads the file where the rename put it. Measured by a `sed` on PATH that
        records which path it was handed: one inside the directory means the window is open."""
        home = self.tmp / 'h-claim'; home.mkdir(parents=True, exist_ok=True)
        binx = self.tmp / 'claim-bin'; binx.mkdir(parents=True, exist_ok=True)
        seen = home / 'sed-was-given'
        fake = binx / 'sed'
        fake.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" >> ' + str(seen) + '\nexec /usr/bin/sed "$@"\n')
        fake.chmod(0o755)
        done = self.run_block(home, ['2026-09-14..2026-09-20', str(self.repo), ''], path=str(binx))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        waiting = str(home / self.ARGS_DIR)
        handed = seen.read_text().split()
        self.assertTrue(handed, 'the fake sed was never called')
        self.assertFalse([h for h in handed if h.startswith(waiting + '/')],
                         'the block read the waiting handoff in place: %r' % handed)
        second = self.run_block(home, None, path=str(binx))
        self.assertNotEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(sorted((home / self.ARGS_DIR).iterdir()), [])
        self.assertEqual(sorted((home / '.claude').glob('bymax-report-args.d.claimed.*')), [])

    def test_two_standups_waiting_at_once_make_the_block_refuse_both(self):
        """Nothing can stop two runs writing their arguments at the same moment: the file tool
        has no create-if-absent that another turn cannot race, and a rename only owns what is
        already there. So the block does not try to pick a winner. It refuses while more than
        one is waiting, claims neither, and says how many it saw. Refusing costs a wait;
        reporting on another run's repository costs the report."""
        home = self.tmp / 'h-two'
        done = self.run_block(home, ['2026-09-14..2026-09-20', str(self.repo), ''], extra='run-2')
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('2 entries are waiting', done.stderr)
        self.assertEqual(sorted(p.name for p in (home / self.ARGS_DIR).iterdir()),
                         ['2026-09-22T09-05-01-k7qz3f', 'run-2'])
        self.assertEqual(done.stdout.strip(), '', done.stdout)

    def test_something_that_is_not_an_arguments_file_does_not_hide_one_waiting_behind_it(self):
        """The waiting place is a directory, so what sits in it is not always a file a run wrote:
        a leftover directory, or anything else the block cannot read three lines from, sorts by
        name like any entry. Asking `[ ! -f ]` before counting answers about the first entry and
        calls the place empty, so a real one waiting behind it is reported as absent and the model
        writes another. Counting first says how many are there, which is true of the directory
        either way, and the file test then speaks only when there is exactly one entry to speak
        about."""
        alone = self.tmp / 'h-nonfile-alone'
        done = self.run_block(alone, None, nonfile='0-left-behind')
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('No arguments file in', done.stderr)
        self.assertEqual(done.stdout.strip(), '', done.stdout)

        behind = self.tmp / 'h-nonfile-behind'
        done = self.run_block(behind, ['2026-09-14..2026-09-20', str(self.repo), ''], nonfile='0-left-behind')
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('2 entries are waiting', done.stderr)
        self.assertNotIn('No arguments file', done.stderr,
                         'the block called the place empty while an arguments file waited in it')
        self.assertEqual(sorted(p.name for p in (behind / self.ARGS_DIR).iterdir()),
                         ['0-left-behind', '2026-09-22T09-05-01-k7qz3f'])
        self.assertEqual(done.stdout.strip(), '', done.stdout)

    def test_a_claim_that_cannot_be_written_names_both_places_it_needs(self):
        """The claim is a rename out of the waiting directory into the one above it, so it needs
        to unlink in the first and create in the second, and either can be the one refusing. The
        message named only the waiting directory, which in the reproduced case is writable: a
        reader following it inspects a directory that is fine and never looks at the one that is
        not. Both are named now, and this case is what keeps them named."""
        home = self.tmp / 'h-unclaimable'
        waiting = home / self.ARGS_DIR
        waiting.mkdir(parents=True, exist_ok=True)
        (waiting / 'a-run').write_text('2026-09-14..2026-09-20\n%s\n\n' % self.repo)
        above = home / '.claude'
        above.chmod(0o555)
        self.addCleanup(above.chmod, 0o755)
        probe = above / 'probe'
        try:
            probe.touch()
        except OSError:
            pass
        else:
            probe.unlink()
            self.skipTest('this runner can write a directory it has no write bit for')

        done = self.run_block(home, None)
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('Could not claim the arguments', done.stderr)
        self.assertIn(str(waiting), done.stderr)
        self.assertIn('directory above it', done.stderr,
                      'the message names only the waiting directory, which here is the writable one')
        self.assertEqual(done.stdout.strip(), '', done.stdout)
        # The rename failed, so the arguments are still there. Telling the reader to write them
        # again here puts a second entry in the directory, after which the count refuses every
        # run until someone removes one -- so the advice has to say which of the two causes it
        # is for.
        self.assertTrue((waiting / 'a-run').exists(), 'the refusal cost the run its arguments')
        # Whole, because the advice is the part that does harm and any clause can carry it: a
        # message keeping the right sentence and adding "Either way, write yours again now."
        # passed a check for one clause. A reword changes this text too, where a reviewer sees it.
        self.assertEqual(done.stderr,
                         'Could not claim the arguments: another run took them first, or %s or the\n'
                         'directory above it cannot be written -- the claim moves the file from one into the\n'
                         'other. Check both. If yours is still waiting, run this block again once they can be\n'
                         'written; if another run took it, write it again first.\n' % waiting)

    def test_the_skill_block_stops_when_there_is_no_temporary_directory(self):
        """An unchecked `mktemp -d` leaves the variable empty, and the collector is then
        told to write `/collect.json`: outside the run's own directory, outside its cleanup,
        and against this skill's promise that a run leaves nothing on disk. The block
        exited 0 while printing a blank path, so nothing downstream could tell."""
        # The collector is a stub that records being called, because the real one fails on
        # `--out /collect.json` for anyone who cannot write to the root directory, and then
        # the unguarded block stops for that reason instead of this one. What the guard
        # must do is stop before the collector, whoever is running.
        home = self.tmp / 'h-notmp'; home.mkdir(parents=True, exist_ok=True)
        plugin = self.tmp / 'stub-plugin'; (plugin / 'scripts').mkdir(parents=True)
        called, out = home / 'called', home / 'out-path'
        (plugin / 'scripts/collect.py').write_text(
            'import sys, pathlib\n'
            'pathlib.Path(%r).write_text("yes")\n' % str(called) +
            'pathlib.Path(%r).write_text(sys.argv[sys.argv.index("--out") + 1])\n' % str(out))
        done = self.run_block(home, ['2026-09-14..2026-09-20', str(self.repo), ''],
                              tmpdir=str(self.tmp / 'nowhere' / 'deeper'), plugin=plugin)
        self.assertFalse(called.exists(),
                         'the collector ran with --out %s' % (out.read_text() if out.exists() else '?'))
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.strip(), 'claimed 2026-09-22T09-05-01-k7qz3f', done.stdout)

    def test_the_skill_block_refuses_a_missing_args_file_and_runs_with_one(self):
        """The handoff file carries what the user typed; without it the block used to run the
        collect on defaults and exit 0, dropping an explicit period and author silently. The
        positive control proves the refusal is not just any refusal: with the file, the block
        runs the collect, deletes the file, and prints the temporary directory."""
        home = self.tmp / 'h1'
        missing = self.run_block(home, None)
        self.assertNotEqual(missing.returncode, 0, missing.stdout + missing.stderr)
        home2 = self.tmp / 'h2'
        with_file = self.run_block(home2, ['2026-09-14..2026-09-20', str(self.repo), ''])
        self.assertEqual(with_file.returncode, 0, with_file.stdout + with_file.stderr)
        # The name is the one the helper wrote, so the case pins the output to the file that was
        # claimed: asserting only `claimed` would pass while the block echoed any name at all.
        self.assertIn('claimed 2026-09-22T09-05-01-k7qz3f\n', with_file.stdout)
        self.assertEqual(sorted((home2 / self.ARGS_DIR).iterdir()), [])
        work = with_file.stdout.strip().splitlines()[-1]
        self.assertTrue((Path(work) / 'collect.json').exists(), with_file.stdout)
        self.assertIn('(2026-09-14 .. 2026-09-20)', with_file.stdout)
        # Without the repository here a run cannot check what it read against what it asked for.
        self.assertIn(str(self.repo), with_file.stdout)


    def test_the_skill_block_carries_a_failed_collect_and_leaves_nothing_behind(self):
        """A collect that cannot run left the block at exit 0 printing a directory with no
        collect.json in it, so the reader took that path for a successful collection and the
        directory stayed on disk. The positive control is the other half: a collect that runs
        still gets its directory and its zero, so the refusal is this failure and not any failure."""
        home = self.tmp / 'h3'
        bad = self.run_block(home, ['7d', '/no/such/repo', ''])
        self.assertNotEqual(bad.returncode, 0, bad.stdout + bad.stderr)
        self.assertEqual(sorted((home / 'tmp').glob('bymax-report.*')), [])
        home2 = self.tmp / 'h4'
        good = self.run_block(home2, ['2026-09-14..2026-09-20', str(self.repo), ''])
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        made = sorted((home2 / 'tmp').glob('bymax-report.*'))
        self.assertEqual(len(made), 1, made)
        self.assertTrue((made[0] / 'collect.json').exists())


if __name__ == '__main__':
    unittest.main()
