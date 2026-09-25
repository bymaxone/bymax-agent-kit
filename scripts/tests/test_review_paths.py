"""The campaign's readers of changed test paths, against paths git quotes when it prints them
one to a line. A quoted path matches no file, so each reader has to ask git for NUL-separated
output, where a path is spelled as itself."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'plugins/bymax-quality/scripts'))
import review_evidence



class QuotedTestPathTests(unittest.TestCase):
    """Git quotes a non-ASCII path it prints one to a line, and every reader of changed tests
    matched the quoted spelling against real ones: tests/test_café.py was no test."""

    def test_each_reader_of_changed_tests_reads_a_quoted_path_as_itself(self):
        where = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, where, True)

        def git(*args):
            return subprocess.run(['git', '-C', str(where), *args], check=True, capture_output=True,
                                  text=True).stdout.strip()
        git('init', '-q', '-b', 'main')
        git('config', 'user.email', 'a@b.invalid')
        git('config', 'user.name', 'A')
        (where / 'tests').mkdir()
        (where / 'tests' / 'test_gone_é.py').write_text('def test_gone(): pass\n')
        git('add', '-A')
        git('commit', '-qm', 'base')
        base = git('rev-parse', 'HEAD')
        git('switch', '-qc', 'side')
        (where / 'tests' / 'test_side_ñ.py').write_text('def test_side(): pass\n')
        git('add', '-A')
        git('commit', '-qm', 'side')
        git('switch', '-q', 'main')
        (where / 'tests' / 'test_café.py').write_text('def test_cafe(): pass\n')
        (where / 'tests' / 'test_gone_é.py').unlink()
        git('add', '-A')
        git('commit', '-qm', 'the correction')
        git('merge', '-q', '--no-ff', '-m', 'merge side', 'side')
        head = git('rev-parse', 'HEAD')
        here = os.getcwd()
        os.chdir(where)
        self.addCleanup(os.chdir, here)
        self.assertEqual(review_evidence.tests_changed(base, head),
                         (['tests/test_café.py'], ['tests/test_gone_é.py']))
        self.assertEqual(review_evidence.merged_in_tests(base, head), ['tests/test_side_ñ.py'])


if __name__ == '__main__':
    unittest.main()
