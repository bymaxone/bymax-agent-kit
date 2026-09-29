"""The prose pass's envelope on names and lines that are not UTF-8: a behaviour suite beside
test_review_prose.py, which holds the envelope's Bench."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
sys.path.insert(0, str(ROOT / 'scripts/tests'))
import review_prose as prose
from test_review_prose import Bench


class NotUtf8EnvelopeTests(unittest.TestCase):
    """A name or a line that is not valid UTF-8 — a Latin-1 name committed on Linux, a Latin-1
    source — raised out of a strict read of a git listing, and the envelope stopped instead of
    naming the file. Names keep their bytes as surrogate escapes, as git_raw() reads them."""

    def latin1_head(self, bench):
        """HEAD gains notes-caf\xe9.md, built without the worktree: APFS refuses such a name,
        so the file is absent from the tree and the envelope lists it as deleted."""
        sys.path.insert(0, str(ROOT / 'scripts/tests'))
        from test_review_paths import commit_with
        base = subprocess.run(['git', '-C', str(bench.where), 'rev-parse', 'HEAD'], check=True,
                              capture_output=True, text=True).stdout.strip()
        head = commit_with(bench.where, base, {b'notes-caf\xe9.md': b'# Notes\n'})
        subprocess.run(['git', '-C', str(bench.where), 'update-ref', 'HEAD', head], check=True)

    def test_a_latin1_name_the_tree_lacks_is_listed_by_its_bytes(self):
        bench = Bench(self)
        self.latin1_head(bench)
        self.assertEqual(prose.changed(cwd=str(bench.where)), ['notes-caf\udce9.md'])
        self.assertIn('notes-caf\udce9.md was deleted', ' | '.join(bench.offences()))

    def test_a_sparse_checkout_excuses_a_latin1_name_it_left_out(self):
        """The skip-worktree listing is NUL-delimited names too, read through the same helper."""
        bench = Bench(self)
        self.latin1_head(bench)
        run = lambda *a: subprocess.run(['git', '-C', str(bench.where), *a], check=True, capture_output=True)
        run('read-tree', 'HEAD')
        run('update-index', '--skip-worktree', os.fsdecode(b'notes-caf\xe9.md'))
        run('config', 'core.sparseCheckout', 'true')
        self.assertEqual(bench.offences(), [])

    def test_an_untracked_or_ignored_latin1_name_is_listed(self):
        """APFS cannot hold the name, so a git in front of the real one adds it to each
        --others listing, as git on Linux would print it."""
        real = shutil.which('git')
        shim = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, shim, True)
        (shim / 'git').write_text('#!/bin/sh\n"%s" "$@" || exit\n'
                                  'case " $* " in *" --others "*) printf \'caf\\351.log\\0\' ;; esac\n' % real)
        (shim / 'git').chmod(0o755)
        bench = Bench(self)
        with mock.patch.dict(os.environ, PATH=str(shim) + os.pathsep + os.environ['PATH']):
            self.assertIn('caf\udce9.log', prose.changed(cwd=str(bench.where)))
            self.assertIn('caf\udce9.log', prose.ignored(cwd=str(bench.where)))

    def test_a_latin1_line_in_a_behaviour_change_is_named(self):
        """The refusal quotes the first changed line, read from a diff of a Latin-1 source."""
        bench = Bench(self)
        (bench.where / 'thing.py').write_bytes(b'# -*- coding: latin-1 -*-\nNAME = "caf\xe9"\n')
        for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A', 'commit', '-qm', 'l']):
            subprocess.run(['git', '-C', str(bench.where), *args], check=True)
        (bench.where / 'thing.py').write_bytes(b'# -*- coding: latin-1 -*-\nNAME = "caf\xe8"\n')
        self.assertIn('at line 2: NAME = "caf\udce8"', ' | '.join(bench.offences()))


if __name__ == '__main__':
    unittest.main()
